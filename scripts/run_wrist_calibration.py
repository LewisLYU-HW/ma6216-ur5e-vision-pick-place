"""Acquire a stationary checkerboard with varied robot FK, estimate, then validate."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
from ma6216.advanced_scene import WRIST_CAMERA
from ma6216.direct_route import configure_direct_table, set_front_ready
from ma6216.motion import Robot, MotionFailure
from ma6216.pose_insertion import transform
from ma6216.scene import build_scene, look_at_quat, matrix_to_quat, mujoco, WIDTH, HEIGHT
from ma6216.wrist_calibration import estimate_wrist, detect_wrist_checker
from ma6216.evaluation import pose_errors


def acquire(folder, seed=621609):
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "images").mkdir()
    def configure(spec):
        configure_direct_table(spec)
        # Dedicated calibration station: remove unrelated tray from the board view.
        spec.body("target_tray").pos = [-2., 0., -2.]
        eye = [.075, 0., .035]
        spec.body("gripper_base").add_camera(name=WRIST_CAMERA, pos=eye,
            quat=look_at_quat(eye, [0., 0., .145]), fovy=80.)
    m, d = build_scene(cube_xy=(-2., -2.), configure_spec=configure)
    set_front_ready(m, d)
    # Stationary target on a surveyed stand. Its world pose is NOT given to estimator.
    mid = m.body_mocapid[m.body("calibration_board").id]
    d.mocap_pos[mid] = [.46, -.02, .405]
    d.mocap_quat[mid] = matrix_to_quat(Rotation.from_euler("z", 90, degrees=True).as_matrix())
    mujoco.mj_forward(m, d)
    robot = Robot(m, d)
    bid = m.body("gripper_base").id
    body = transform(d.xpos[bid], d.xmat[bid].reshape(3, 3))
    pinch = transform(d.site_xpos[robot.sid], d.site_xmat[robot.sid].reshape(3, 3))
    body_T_pinch = np.linalg.inv(body) @ pinch
    rng = np.random.default_rng(seed)
    splits = ["intrinsic_train"] * 24 + ["intrinsic_validation"] * 8 + ["hand_eye_train"] * 24 + ["hand_eye_validation"] * 10
    rows, rejected = [], []
    accepted, i = 0, -1
    with mujoco.Renderer(m, height=HEIGHT, width=WIDTH) as renderer:
        while accepted < len(splits):
            i += 1
            if i >= 300:
                raise RuntimeError("Insufficient visible checkerboards after 300 acquisition attempts")
            split = splits[accepted]
            # Nominal operator-specified gripper poses, independent of camera truth.
            target = transform([.29, -.02, .83] + rng.uniform([-.025, -.04, -.04], [.025, .04, .04]),
                Rotation.from_euler("xyz", [180., -34., 0.], degrees=True).as_matrix()
                @ Rotation.from_euler("xyz", rng.uniform([-12., -12., -30.], [12., 12., 30.]), degrees=True).as_matrix())
            tcp = target @ body_T_pinch
            try:
                q, _ = robot.solve(tcp[:3, 3], tcp[:3, :3], robot.home, multistart=False)
            except MotionFailure as exc:
                rejected.append({"id": str(i), "reason": str(exc)[:300], "split": split})
                print(f"IK rejected {i}", flush=True)
                continue
            # Static acquisition configurations, not manipulation trajectories.
            d.qpos[robot.qids] = q
            d.qvel[:] = 0.
            mujoco.mj_forward(m, d)
            renderer.update_scene(d, camera=WRIST_CAMERA)
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
            image = f"images/{i:04d}.png"
            bgr = cv2.cvtColor(renderer.render(), cv2.COLOR_RGB2BGR)
            cv2.imwrite(str(folder / image), bgr)
            corners, quality = detect_wrist_checker(bgr)
            detected = corners is not None
            rows.append({"id": f"{i:04d}", "split": split, "image": image,
                         "joint_position_rad": q.tolist(), "acquisition_checker_visible": detected,
                         "acquisition_image_quality": quality,
                         "world_T_gripper": transform(d.xpos[bid], d.xmat[bid].reshape(3, 3)).tolist()})
            accepted += int(detected)
            print(f"ACQUIRED attempt {i + 1} valid {accepted}/{len(splits)} {split}", flush=True)
    (folder / "observations.json").write_text(json.dumps({"image_size": [WIDTH, HEIGHT],
        "seed": seed, "acquisition": "static robot calibration configurations; stationary checkerboard",
        "gripper_body": "gripper_base", "frames": rows, "ik_rejections": rejected}, indent=2) + "\n")
    return m, d


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seed", type=int, default=621610)
    p.add_argument("--estimate-only", type=Path, help="Existing data directory; no simulator truth evaluation")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if args.estimate_only:
        result = estimate_wrist(args.estimate_only, args.output / "estimated")
    else:
        m, d = acquire(args.output / "data", seed=args.seed)
        result = estimate_wrist(args.output / "data", args.output / "estimated")
        # Access camera truth ONLY after saving the estimated calibration.
        cid, bid = m.camera(WRIST_CAMERA).id, m.body("gripper_base").id
        WTC = transform(d.cam_xpos[cid], d.cam_xmat[cid].reshape(3, 3) @ np.diag([1., -1., -1.]))
        WTG = transform(d.xpos[bid], d.xmat[bid].reshape(3, 3))
        truth_X = np.linalg.inv(WTG) @ WTC
        focal = .5 * HEIGHT / np.tan(np.deg2rad(m.cam_fovy[cid]) / 2)
        truth_K = np.array([[focal, 0., (WIDTH - 1) / 2], [0., focal, (HEIGHT - 1) / 2], [0., 0., 1.]])
        K = np.array(result["K"])
        evaluation = {"calibration_frozen_before_gt_evaluation": True,
            "gripper_T_camera_error": pose_errors(result["gripper_T_camera"], truth_X),
            "focal_relative_error": (np.diag(K)[:2] / np.diag(truth_K)[:2] - 1).tolist(),
            "principal_point_error_px": (K[:2, 2] - truth_K[:2, 2]).tolist()}
        (args.output / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
        (args.output / "evaluation_only_camera_truth.json").write_text(json.dumps(
            {"K": truth_K.tolist(), "gripper_T_camera": truth_X.tolist()}, indent=2) + "\n")
        print(json.dumps(evaluation, indent=2), flush=True)
    print(json.dumps(result["splits"], indent=2), flush=True)


if __name__ == "__main__":
    main()
