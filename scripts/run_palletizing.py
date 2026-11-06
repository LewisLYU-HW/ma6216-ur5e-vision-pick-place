"""Build two stacks using FoundationPose, estimated calibration and contact physics."""
import argparse
import json
from pathlib import Path
import sys
import traceback

import cv2
import numpy as np

SCRIPTS=Path(__file__).resolve().parent
sys.path.insert(0,str(SCRIPTS.parent/'src'))
from ma6216.config import project_root
from ma6216.palletizing import PARTS,SUPPORTS,BY_KEY,build_pallet_scene,PalletRobot,truth_poses,block_outcome
from ma6216.runner import run_trial
from ma6216.scene import CAMERA_NAME,mujoco
from ma6216.vision import make_renderer
from run_multi_pick_place import perceive_remaining,merge_videos


def save_scene(model,data,path):
    renderer=make_renderer(model)
    try:
        renderer.update_scene(data,camera=CAMERA_NAME)
        renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW]=False
        cv2.imwrite(str(path),cv2.cvtColor(renderer.render(),cv2.COLOR_RGB2BGR))
    finally:
        renderer.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--calibration',type=Path,default=project_root()/'demo_data/calibration/estimated')
    parser.add_argument('--layout',type=int,choices=(0,1),default=0)
    parser.add_argument('--ground-truth',action='store_true',help='Diagnostic physics baseline; skips FoundationPose')
    parser.add_argument('--record',action='store_true')
    parser.add_argument('--viewer',action='store_true')
    args=parser.parse_args()
    if not args.ground_truth:
        for name in ('cam_K.txt','world_T_camera.txt'):
            if not (args.calibration/name).is_file():parser.error(f'Missing estimated calibration: {name}')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    summary={'success':False,'application':'two-column two-layer palletizing','layout':args.layout,
             'object_count':4,'columns':2,'layers':2,
             'control_source':'ground_truth_control_baseline' if args.ground_truth else 'FoundationPose + estimated calibration',
             'picks':[]}
    viewer=None;videos=[];known={};placed_evaluations={}
    try:
        model,data=build_pallet_scene(args.layout)
        for _ in range(775):mujoco.mj_step(model,data)
        save_scene(model,data,output/'initial_scene.png')
        for index,part in enumerate(PARTS):
            step=output/f'pick_{index+1:02d}_{part.key}';step.mkdir()
            if args.ground_truth:
                known=truth_poses(model,data);evaluations=[]
            else:
                observe=list(PARTS[index:])
                if SUPPORTS[part.key]:observe.append(BY_KEY[SUPPORTS[part.key]])
                estimates,evaluations=perceive_remaining(model,data,observe,step,args.calibration)
                known.update(estimates)
            if args.viewer and viewer is None:
                from mujoco import viewer as mj_viewer
                viewer=mj_viewer.launch_passive(model,data)
                with viewer.lock():
                    viewer.cam.lookat[:]=[.44,0,.41];viewer.cam.distance=1.65
                    viewer.cam.azimuth=130;viewer.cam.elevation=-35
            robot=PalletRobot(model,data,part,known,ground_truth=args.ground_truth)
            result=run_trial(model,data,step/'motion',pose=None if args.ground_truth else known[part.key],
                             robot=robot,record=args.record,shared_viewer=viewer)
            summary['picks'].append({'id':part.key,'success':result['success'],
                                     'perception_evaluation_only':evaluations,'motion':result})
            (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            if not result['success']:raise RuntimeError(f"Palletizing failed for {part.key}: {result.get('error')}")
            plan=json.loads((step/'motion/plan.json').read_text())
            known[part.key]=np.asarray(plan['placed_pose_command'])
            placed_evaluations[part.key]=data.xpos[model.body(part.body).id].copy()
            save_scene(model,data,step/'stack_after_release.png')
            if args.record:videos.append(step/'motion/physical_pick_place.mp4')
        before=truth_poses(model,data)  # Independent stability evaluation only.
        max_drift={part.key:0. for part in PARTS}
        for tick in range(2500):
            mujoco.mj_step(model,data)
            if tick%50==0:
                for part in PARTS:
                    p=data.xpos[model.body(part.body).id]
                    max_drift[part.key]=max(max_drift[part.key],float(np.linalg.norm(p-before[part.key][:3,3])))
                if viewer is not None:viewer.sync()
        outcomes=[block_outcome(model,data,part) for part in PARTS]
        for item in outcomes:
            item['five_second_max_drift_mm']=1000*max_drift[item['id']]
            item['displacement_since_placement_mm']=1000*float(np.linalg.norm(
                np.asarray(item['position_m'])-placed_evaluations[item['id']]))
        summary['final_evaluation_only']=outcomes
        summary['success']=all(item['success'] and item['five_second_max_drift_mm']<1. and
                               item['displacement_since_placement_mm']<5. for item in outcomes)
        summary['simulation_time_s']=float(data.time)
        save_scene(model,data,output/'final_scene.png')
        if args.record:merge_videos(videos,output/'palletizing.mp4')
    except Exception as exc:
        summary['error']=f'{type(exc).__name__}: {exc}';summary['traceback']=traceback.format_exc()
        traceback.print_exc()
    finally:
        if viewer is not None:viewer.close()
        (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'success':summary['success'],'completed_picks':len(summary['picks']),
                      'error':summary.get('error')}),flush=True)
    return 0 if summary['success'] else 1


if __name__=='__main__':raise SystemExit(main())
