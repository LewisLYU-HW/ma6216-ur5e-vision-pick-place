"""Render the original recorded physics trajectory, without rerunning a trial."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.advanced_scene import build_task_scene
from ma6216.scene import mujoco
from ma6216.task_control import TaskRecorder
from ma6216.workshop_control import WorkshopRecorder
from ma6216.workshop_scene import build_workshop_scene


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trial", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--export", type=Path, help="H.264 combined overview/wrist MP4 destination")
    p.add_argument("--export-wrist", type=Path)
    args = p.parse_args()
    report = json.loads((args.trial / "summary.json").read_text())
    path = args.trial / "motion/trajectory_evaluation_only.npz"
    trace = np.load(path, allow_pickle=False)
    task, seed = report["task"], report["seed"]
    workshop = task in ("all", "insert", "hang", "rack", "complete")
    scene = (
        build_workshop_scene(
            seed, rack_assembly=task in ("rack", "complete"), complete_task=task == "complete"
        )
        if workshop
        else build_task_scene(task, seed)
    )
    m, d = scene.model, scene.data
    status = "SUCCESS" if report["success"] else "FAILURE"
    error = report.get("error") or ""
    if report["success"]:
        detail = "Trial outcome: SUCCESS; original state replay"
    elif "offline IK" in error:
        detail = "Trial outcome: FAILURE; no collision-free IK"
    elif "contact guard" in error.lower():
        detail = "Trial outcome: FAILURE; insertion force guard"
    elif "Unexpected robot contact" in error:
        detail = "Trial outcome: FAILURE; unexpected robot contact"
    else:
        detail = "Trial outcome: FAILURE; see original trial log"
    source = (
        f"RECORDED RUN | {report.get('method', 'full')} | seed {seed} | {report.get('disturbance', 'none')}"
    )
    if report.get("control_source") == "ground_truth_diagnostic":
        source = "GROUND TRUTH DIAGNOSTIC | " + status
    recorder = (
        WorkshopRecorder(m, args.output, source=source)
        if workshop
        else TaskRecorder(m, args.output, task, source=source)
    )
    current = None
    if workshop:
        recorder.pose_provider = lambda: current
    start, end = float(trace["time"][0]), float(trace["time"][-1])
    times = start + np.arange(max(1, round((end - start) * 25) + 1)) / 25
    phase_events = []
    events_path = args.trial / "motion/events.json"
    all_events = json.loads(events_path.read_text()) if events_path.exists() else []
    feedback_events = [event for event in all_events if event["event"] == "visual_servo_observation"]
    phase_labels = {
        "park_hammer": "1 OF 4 - HAMMER PARKING",
        "moving_driver_insertion": "2 OF 4 - MOVING DRIVER + TILTED INSERTION",
        "install_frame": "3 OF 4 - RACK ASSEMBLY",
        "regrasp_and_hang_spanner": "4 OF 4 - SPANNER REGRASP + HANG",
    }
    if task == "complete":
        phase_events = [
            event
            for event in all_events
            if event["event"] == "task_phase"
        ]
    try:
        for number, timestamp in enumerate(times):
            index = min(
                len(trace["time"]) - 1,
                max(0, int(np.searchsorted(trace["time"], timestamp, side="right") - 1)),
            )
            if number == len(times) - 1:
                index = len(trace["time"]) - 1
            for key in ("qpos", "qvel", "ctrl", "mocap_pos", "mocap_quat"):
                getattr(d, key)[:] = trace[key][index]
            d.time = float(timestamp)
            mujoco.mj_forward(m, d)
            estimate = trace["estimated_pose"][index]
            current = (str(trace["object_id"][index]), estimate) if np.isfinite(estimate).all() else None
            stage = str(trace["stage"][index])
            frame_detail = detail
            if stage.startswith("VISUAL_"):
                available = [event for event in feedback_events
                             if event["simulation_time_s"] <= timestamp
                             and event.get("object_id") == str(trace["object_id"][index])]
                if available:
                    observation = available[-1]
                    frame_detail = (f"{status} run | VISION residual: "
                                    f"{observation['translation_error_mm']:.2f} mm / "
                                    f"{observation['rotation_error_deg']:.2f} deg | "
                                    f"observation {observation['iteration'] + 1}")
            phases = [event for event in phase_events if event["simulation_time_s"] <= timestamp]
            if phases:
                stage = phase_labels[phases[-1]["phase"]] + "  |  " + stage.replace("_", " ")
            recorder.capture(d, stage, frame_detail)
    finally:
        recorder.close()
    metadata = {
        "trial": args.trial.name,
        "task": task,
        "method": report.get("method"),
        "seed": seed,
        "disturbance": report.get("disturbance"),
        "success": report["success"],
        "error": report.get("error"),
        "video_explanation": detail,
        "trajectory_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "summary_sha256": hashlib.sha256((args.trial / "summary.json").read_bytes()).hexdigest(),
        "simulation_start_s": start,
        "simulation_end_s": end,
        "frames": recorder.frames,
        "fps": 25,
        "replay": "Original 25 Hz state snapshots; no new inference or physics stepping; timestamps are simulation time",
        "files": {},
    }
    for name, target in (("overview_wrist", args.export), ("wrist", args.export_wrist)):
        if target is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-n",
                "-i",
                str(args.output / (name + ".mp4")),
                "-c:v",
                "libx264",
                "-crf",
                "23",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(target),
            ],
            check=True,
        )
        metadata["files"][target.name] = {
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "bytes": target.stat().st_size,
        }
    (args.output / "replay.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
