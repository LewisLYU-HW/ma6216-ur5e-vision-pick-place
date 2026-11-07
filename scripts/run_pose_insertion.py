"""Estimate a tilted block's full 6D pose, reorient it and seat it in a keyed nest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.pose_insertion import (BLOCK, LAYOUTS, WRIST_CAMERA, InsertionRobot, Nest,
                                   build_insertion_scene, insertion_outcome, object_pose)
from ma6216.runner import run_trial
from ma6216.scene import CAMERA_NAME, mujoco
from ma6216.vision import capture_observation, compose_world_pose, make_renderer, prepare_observation_dir


def observe(model, data, output, calibration):
    dataset = output / "observation"
    mesh = prepare_observation_dir(dataset, calibration, export_target_mesh=BLOCK.export_mesh)
    renderer = make_renderer(model)
    try:
        capture_observation(renderer, data, dataset, "000000", segment=BLOCK.mask)
    finally:
        renderer.close()
    return dataset, mesh


def snapshot(model, data, path):
    import cv2
    renderer = make_renderer(model)
    try:
        renderer.update_scene(data, camera=CAMERA_NAME)
        cv2.imwrite(str(path), cv2.cvtColor(renderer.render(), cv2.COLOR_RGB2BGR))
    finally:
        renderer.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory; previous evidence is preserved")
    parser.add_argument("--layout", type=int, choices=range(len(LAYOUTS)), default=1)
    parser.add_argument("--calibration", type=Path, default=ROOT / "demo_data/calibration/estimated")
    parser.add_argument("--clearance-mm", type=float, default=2.5, help="Per-side nest clearance, 0.5 to 3 mm")
    parser.add_argument("--target-yaw-deg", type=float, default=0.)
    parser.add_argument("--pose-mode", choices=("full", "yaw-only"), default="full",
                        help="yaw-only discards estimated roll/pitch for an explicit ablation")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ground-truth", action="store_true", help="Diagnostic physics baseline; skips vision")
    mode.add_argument("--capture-only", action="store_true", help="Save RGB-D, mask and CAD without moving the robot")
    parser.add_argument("--foundationpose-python", type=Path,
                        help="Optional separate Python executable with official FoundationPose CUDA dependencies")
    parser.add_argument("--foundationpose-repository", type=Path,
                        help="Official checkout; otherwise use the existing repository path configuration")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--record-view", choices=("overview", "wrist", "both"), default="overview",
                        help="Recorded camera view; both saves a synchronized pair plus each view separately")
    parser.add_argument("--viewer", action="store_true")
    args = parser.parse_args()
    if args.record_view != "overview" and not args.record:
        parser.error("--record-view requires --record")
    record_cameras = {"overview": ("overview",), "wrist": (WRIST_CAMERA,),
                      "both": ("overview", WRIST_CAMERA)}[args.record_view]
    if not np.isfinite(args.target_yaw_deg) or abs(args.target_yaw_deg) > 30:
        parser.error("Target yaw must be within [-30, 30] degrees")
    if not np.isfinite(args.clearance_mm) or not .5 <= args.clearance_mm <= 3:
        parser.error("Per-side nest clearance must be within [0.5, 3] mm")
    if not args.ground_truth:
        for name in ("cam_K.txt", "world_T_camera.txt"):
            if not (args.calibration / name).is_file():
                parser.error(f"Missing estimated calibration: {args.calibration / name}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    summary = {"success": False, "application": "6D-pose-guided keyed shallow-nest seating",
               "status": "running", "layout": args.layout, "pose_mode": args.pose_mode,
               "control_source": "ground_truth_control_baseline" if args.ground_truth else "FoundationPose + estimated calibration",
               "rotation_initialization": "not run (physics baseline)" if args.ground_truth else "official full SO(3) grid; no upright prior",
               "nest_clearance_mm_per_side": args.clearance_mm,
               "robot_self_gravity_compensation": True,
               "recording_cameras": list(record_cameras) if args.record else [],
               "perception_camera": None if args.ground_truth else CAMERA_NAME,
               "scope": "Four deterministic fixture layouts; shallow gravity seating, not force-controlled precision insertion"}
    exit_code = 1
    try:
        nest = Nest(clearance=args.clearance_mm / 1000, yaw_deg=args.target_yaw_deg)
        model, data, nest = build_insertion_scene(args.layout, nest)
        for _ in range(round(1.55 / model.opt.timestep)):
            mujoco.mj_step(model, data)
        if args.ground_truth:
            estimate = object_pose(model, data)
        else:
            dataset, mesh = observe(model, data, output, args.calibration)
            if args.capture_only:
                summary.update(status="observation_captured", success=None)
                exit_code = 0
                return exit_code
            command = [str(args.foundationpose_python.resolve()) if args.foundationpose_python else sys.executable,
                       "-u", str(ROOT / "scripts/run_foundationpose.py"),
                       "--dataset", str(dataset), "--mesh", str(mesh), "--output", str(output / "foundationpose"),
                       "--intrinsics-source", "calibration", "--max-frames", "1"]
            if args.foundationpose_repository:
                command += ["--repository", str(args.foundationpose_repository.resolve())]
            # Deliberately omit --upright-extrinsic: roll and pitch must be estimated.
            with (output / "foundationpose.log").open("w") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            estimate = compose_world_pose(output / "foundationpose/poses/000000.txt",
                                          dataset / "world_T_camera_estimated.txt")
            inference = json.loads((output / "foundationpose/summary.json").read_text())
            summary["foundationpose_provenance"] = {
                key: inference.get(key) for key in ("repository_commit", "status", "mesh_sha256",
                    "intrinsics_sha256", "registration_candidate_count", "ground_truth_used_for_inference",
                    "gpu", "torch_version", "cuda_runtime")}
        np.savetxt(output / "world_T_object_estimated.txt", estimate)
        # Simulator truth is read only after the estimate is frozen, for evaluation.
        actual = object_pose(model, data)
        summary["perception_evaluation_only"] = {
            "translation_error_mm": float(1000 * np.linalg.norm(estimate[:3, 3] - actual[:3, 3])),
            "rotation_error_deg": float(np.rad2deg(Rotation.from_matrix(estimate[:3, :3] @ actual[:3, :3].T).magnitude())),
            "actual_roll_pitch_yaw_deg": Rotation.from_matrix(actual[:3, :3]).as_euler("xyz", degrees=True).tolist(),
            "estimated_roll_pitch_yaw_deg": Rotation.from_matrix(estimate[:3, :3]).as_euler("xyz", degrees=True).tolist()}
        if args.record:
            snapshot(model, data, output / "initial_scene.png")
        robot = InsertionRobot(model, data, estimate, nest, ground_truth=args.ground_truth, pose_mode=args.pose_mode)
        motion = run_trial(model, data, output / "motion", robot=robot,
                           pose=None if args.ground_truth else estimate, record=args.record, viewer=args.viewer,
                           record_cameras=record_cameras)
        summary["motion"] = motion
        if not motion["success"]:
            summary["failure_evaluation_only"] = insertion_outcome(model, data, nest)
            if args.record:
                snapshot(model, data, output / "failed_scene.png")
            raise RuntimeError(motion.get("error", "Physical execution failed"))
        before = object_pose(model, data)
        maximum_drift = 0.
        for tick in range(round(5. / model.opt.timestep)):
            mujoco.mj_step(model, data)
            if tick % 25 == 0:
                maximum_drift = max(maximum_drift, float(np.linalg.norm(object_pose(model, data)[:3, 3] - before[:3, 3])))
        final = insertion_outcome(model, data, nest)
        final["five_second_max_drift_mm"] = maximum_drift * 1000
        summary["final_evaluation_only"] = final
        summary["success"] = final["success"] and maximum_drift < .001
        summary["status"] = "completed" if summary["success"] else "acceptance_failed"
        summary["simulation_time_s"] = float(data.time)
        if args.record:
            snapshot(model, data, output / "final_scene.png")
        exit_code = 0 if summary["success"] else 1
    except Exception as exc:
        summary.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        summary["wall_clock_seconds_including_inference"] = time.perf_counter() - started
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: summary.get(key) for key in ("success", "status", "layout", "pose_mode", "error")}), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
