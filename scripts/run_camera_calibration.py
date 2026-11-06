"""Acquire real rendered targets, calibrate from pixels, then separately evaluate."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from ma6216.scene import *
import cv2
from scipy.spatial.transform import Rotation
from ma6216.calibration import estimate_calibration


def acquire(out):
    out.mkdir(parents=True,exist_ok=False)
    (out/"images").mkdir()
    model,data=build_scene()
    # Settle physical scene once; board is non-colliding calibration equipment.
    for _ in range(500): mujoco.mj_step(model,data)
    K_gt,T_gt=camera_ground_truth(model,data)
    renderer=mujoco.Renderer(model,height=HEIGHT,width=WIDTH)
    rng=np.random.default_rng(6216)
    # Target presentation orientation uses a nominal fixture direction, not fitted camera data.
    R0=Rotation.from_quat(look_at_quat([1.05,-1.05,1.20],[.45,0,.43])[[1,2,3,0]]).as_matrix()
    frames=[]
    mocap=model.body_mocapid[model.body("calibration_board").id]
    splits=["intrinsic_train"]*20+["intrinsic_validation"]*6+["extrinsic_train"]*5+["extrinsic_validation"]*5
    try:
        for i,split in enumerate(splits):
            R=R0@Rotation.from_euler("xyz",rng.uniform([-.4,-.5,-.6],[.4,.5,.6])).as_matrix()
            pos=np.array([.45,0,.56])+rng.uniform([-.12,-.13,-.08],[.13,.13,.12])
            data.mocap_pos[mocap]=pos
            data.mocap_quat[mocap]=matrix_to_quat(R)
            mujoco.mj_forward(model,data)
            renderer.update_scene(data,camera=CAMERA_NAME)
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW]=False
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION]=False
            rgb=renderer.render()
            name=f"images/{i:04d}.png"
            cv2.imwrite(str(out/name),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
            T=np.eye(4);T[:3,:3]=R;T[:3,3]=pos
            frames.append(dict(id=f"{i:04d}",image=name,split=split,world_T_board=T.tolist()))
            print(f"ACQUIRED {i+1}/{len(splits)} {split}",flush=True)
    finally: renderer.close()
    (out/"survey.json").write_text(json.dumps(dict(image_size=[WIDTH,HEIGHT],square_m=SQUARE,
        pattern=[BOARD_COLS,BOARD_ROWS],survey_source="Known physical target fixture poses in world mounting-origin frame; not camera GT",frames=frames),indent=2))
    # Kept outside data directory; the estimator cannot open a GT file through its inputs.
    return dict(K=K_gt.tolist(),world_T_camera=T_gt.tolist())


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,default=Path("artifacts/calibration"));args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    gt=acquire(args.output/"data")
    result=estimate_calibration(args.output/"data",args.output/"estimated")
    # Evaluation is downstream and never modifies calibration output.
    K=np.asarray(result["K"]);T=np.asarray(result["world_T_camera"])
    Kgt=np.asarray(gt["K"]);Tgt=np.asarray(gt["world_T_camera"])
    angle=Rotation.from_matrix(T[:3,:3]@Tgt[:3,:3].T).magnitude()*180/np.pi
    metrics=dict(focal_relative_error=(np.diag(K)[:2]/np.diag(Kgt)[:2]-1).tolist(),
        principal_error_px=(K[:2,2]-Kgt[:2,2]).tolist(),
        extrinsic_translation_error_mm=float(np.linalg.norm(T[:3,3]-Tgt[:3,3])*1000),
        extrinsic_rotation_error_deg=float(angle),calibration_frozen_before_gt_evaluation=True)
    (args.output/"evaluation_only_camera_gt.json").write_text(json.dumps(gt,indent=2))
    (args.output/"evaluation.json").write_text(json.dumps(metrics,indent=2))
    print(json.dumps({"calibration":result,"evaluation":metrics},indent=2))

if __name__=="__main__":main()
