"""Render real RGB-D, segment by image colour; keep simulator GT separate."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import numpy as np
from ma6216.scene import TRIAL_LAYOUTS, build_scene, camera_ground_truth, mujoco
from ma6216.vision import capture_observation, make_renderer, prepare_observation_dir
from ma6216.config import project_root


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,default=Path("artifacts/vision_inputs"))
    p.add_argument("--calibration",type=Path,default=project_root()/"demo_data/calibration/estimated");args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    gt_dir=args.output.parent/(args.output.name+"_evaluation_only")
    gt_dir.mkdir(exist_ok=False)
    evaluations=[]
    for trial,(x,y,yaw) in enumerate(TRIAL_LAYOUTS):
        folder=args.output/f"trial_{trial:02d}"
        prepare_observation_dir(folder, args.calibration)
        model,data=build_scene((x,y),yaw)
        for _ in range(750): mujoco.mj_step(model,data)
        renderer=make_renderer(model)
        frames=[]
        try:
            for index in range(3 if trial==0 else 1):
                for _ in range(25): mujoco.mj_step(model,data)
                frame=f"{index:06d}"
                mask, depth = capture_observation(renderer, data, folder, frame)
                renderer.enable_segmentation_rendering()
                seg=renderer.render()
                renderer.disable_segmentation_rendering()
                truth_mask=(seg[...,0]==model.geom("target_cube_geom").id)&(seg[...,1]==int(mujoco.mjtObj.mjOBJ_GEOM))
                pred=mask>0
                union=np.count_nonzero(pred|truth_mask)
                iou=np.count_nonzero(pred&truth_mask)/max(1,union)
                bid=model.body("target_cube").id
                T=np.eye(4);T[:3,:3]=data.xmat[bid].reshape(3,3);T[:3,3]=data.xpos[bid]
                _,WTC=camera_ground_truth(model,data)
                frames.append(dict(id=frame,simulation_time_s=float(data.time),world_T_object=T.tolist(),
                    camera_T_object=(np.linalg.inv(WTC)@T).tolist(),mask_iou=float(iou),
                    mask_pixels=int(pred.sum()),depth_min_m=float(depth[pred].min()),depth_max_m=float(depth[pred].max())))
                print(f"CAPTURE trial={trial} frame={frame} IoU={iou:.5f}",flush=True)
        finally:renderer.close()
        # Initial scene conditions identify reproducible trials but are NOT opened by pose inference.
        (gt_dir/f"trial_{trial:02d}.json").write_text(json.dumps(dict(cube_xy=[x,y],cube_yaw_rad=yaw,frames=frames),indent=2))
        (folder/"input_provenance.json").write_text(json.dumps(dict(
            rgb_source="MuJoCo native Renderer RGB",depth_source="MuJoCo metric depth, metres float32; no depth noise",
            mask_source="HSV red threshold + largest connected component from RGB only",
            intrinsics_source=str(args.calibration/"cam_K.txt"),camera_extrinsic_source=str(args.calibration/"world_T_camera.txt"),
            mesh_source="50 mm cube CAD, origin at volume centre, matching scene geometry",units="metres",
            observations="static target; trial_00 includes three temporally adjacent physics frames"),indent=2))
        evaluations.append(dict(trial=trial,frames=len(frames),mask_iou_mean=float(np.mean([f["mask_iou"] for f in frames]))))
    (gt_dir/"segmentation_summary.json").write_text(json.dumps(evaluations,indent=2))

if __name__=="__main__":main()
