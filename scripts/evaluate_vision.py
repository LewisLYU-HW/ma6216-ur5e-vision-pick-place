"""Evaluate saved RGB-D pose predictions and control outcomes; GT only here."""
import argparse
import csv
from itertools import product
import json
from pathlib import Path
import sys

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ma6216.foundationpose import cube_symmetry_transforms


CUBE_SYMMETRIES = cube_symmetry_transforms()[:, :3, :3]
CUBE_CORNERS = np.array(list(product((-.025, .025), repeat=3)))


def rotation_angle(R):
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))


def pose_errors(estimated, truth):
    R, t = estimated[:3, :3], estimated[:3, 3]
    R_gt, t_gt = truth[:3, :3], truth[:3, 3]
    estimated_corners = CUBE_CORNERS @ R.T + t
    return {
        "translation_mm": float(np.linalg.norm(t - t_gt) * 1000),
        "rotation_raw_deg": rotation_angle(R @ R_gt.T),
        "rotation_cube_sym_deg": min(rotation_angle(R @ (R_gt @ S).T) for S in CUBE_SYMMETRIES),
        "mssd_cube_sym_mm": min(float(np.linalg.norm(estimated_corners - (CUBE_CORNERS @ (R_gt @ S).T + t_gt), axis=1).max())
                                for S in CUBE_SYMMETRIES) * 1000,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--control", type=Path, default=Path("artifacts/vision_control_pinch_above"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/vision_evaluation"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    truth_dir = args.artifacts / "vision_inputs_evaluation_only"
    trials, frames = [], []
    for truth_file in sorted(truth_dir.glob("trial_*.json")):
        trial = truth_file.stem
        inference_dir = args.artifacts / "foundationpose_cube" / trial
        truth = json.loads(truth_file.read_text())
        estimated_extrinsic = np.loadtxt(args.artifacts / "vision_inputs" / trial / "world_T_camera_estimated.txt")
        inference_summary = inference_dir / "summary.json"
        if inference_summary.exists():
            inference = json.loads(inference_summary.read_text())
            inference_status = inference["status"]
        else:
            inference_status = "missing"
        timing_path = inference_dir / "frames.csv"
        timings = {}
        if timing_path.exists():
            with timing_path.open(newline="") as timing_file:
                timings = {row["frame"]: row for row in csv.DictReader(timing_file)}
        for sample in truth["frames"]:
            frame = sample["id"]
            camera_pose = inference_dir / "poses" / f"{frame}.txt"
            row = {"trial": trial, "frame": frame, "mask_iou": sample["mask_iou"], "pose_available": camera_pose.is_file()}
            if camera_pose.is_file():
                estimate = np.loadtxt(camera_pose)
                camera_errors = pose_errors(estimate, np.asarray(sample["camera_T_object"]))
                world_errors = pose_errors(estimated_extrinsic @ estimate, np.asarray(sample["world_T_object"]))
                row.update({f"camera_{k}": v for k, v in camera_errors.items()})
                row.update({f"world_{k}": v for k, v in world_errors.items()})
                if frame in timings:
                    row["operation"] = timings[frame]["operation"]
                    row["inference_seconds"] = float(timings[frame]["seconds"])
            frames.append(row)
        control_summary = args.control / trial / "summary.json"
        motion = None
        if control_summary.exists():
            motion = json.loads(control_summary.read_text())["results"][0]
        outcome = {"trial": trial, "cube_xy_m": truth["cube_xy"], "cube_yaw_rad": truth["cube_yaw_rad"],
                   "inference_status": inference_status, "control": motion}
        if motion and motion["success"]:
            centre = np.asarray(motion["final_cube_position_m"][:2])
            outcome["placement_xy_error_mm"] = float(np.linalg.norm(centre - [.5, .18]) * 1000)
        trials.append(outcome)
    registered = [row for row in frames if row.get("operation") == "register"]
    attempted = [trial for trial in trials if trial["control"] is not None]
    succeeded = [trial for trial in attempted if trial["control"]["success"]]
    stats = {}
    for metric in ("mask_iou", "camera_translation_mm", "camera_rotation_cube_sym_deg", "world_translation_mm",
                   "world_rotation_raw_deg", "world_rotation_cube_sym_deg", "world_mssd_cube_sym_mm", "inference_seconds"):
        source = [row for row in frames if row["frame"] == "000000"] if metric == "mask_iou" else registered
        vals = [row[metric] for row in source if metric in row]
        if vals:
            stats[metric] = {"n": len(vals), "mean": float(np.mean(vals)), "min": min(vals), "max": max(vals)}
    summary = {"distinct_initial_scenes": len(trials), "image_frames": len(frames), "valid_pose_frames": sum(row["pose_available"] for row in frames),
               "registrations": len(registered), "physical_vision_attempts": len(attempted), "physical_vision_successes": len(succeeded),
               "successful_placement_xy_error_mm": [trial["placement_xy_error_mm"] for trial in succeeded],
               "cube_rotation_equivalence_count": len(CUBE_SYMMETRIES), "aggregate": stats, "trials": trials}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    columns = sorted({key for row in frames for key in row})
    with (args.output / "frames.csv").open("w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()
        writer.writerows(frames)
    print(json.dumps({key: value for key, value in summary.items() if key != "trials"}, indent=2))


if __name__ == "__main__":
    main()
