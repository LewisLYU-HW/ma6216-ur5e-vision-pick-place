"""One open-loop trial in the same MuJoCo instance from capture through placement."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS.parent / "src"))
from ma6216.scene import build_scene, mujoco
from ma6216.vision import capture_observation, compose_world_pose, make_renderer, prepare_observation_dir
from ma6216.runner import run_trial
from ma6216.config import project_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calibration", type=Path,
                        default=project_root() / "demo_data/calibration/estimated")
    parser.add_argument("--cube-xy", type=float, nargs=2, default=[.46, -.18],
                        help="Simulator trial initialization only, never passed to the motion planner")
    parser.add_argument("--cube-yaw", type=float, default=0., help="Initial yaw in radians")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--viewer", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    summary = {"success": False, "status": "capture", "control_source": "FoundationPose RGB-D + estimated calibration",
               "simulation_initial_conditions": {"cube_xy_m": args.cube_xy, "cube_yaw_rad": args.cube_yaw}}
    try:
        model, data = build_scene(args.cube_xy, args.cube_yaw, calibration_board=False)
        for _ in range(775):
            mujoco.mj_step(model, data)
        observations = output / "observation"
        prepare_observation_dir(observations, args.calibration)
        renderer = make_renderer(model)
        try:
            capture_observation(renderer, data, observations, "000000")
        finally:
            renderer.close()
        capture_time = float(data.time)
        summary["capture_simulation_time_s"] = capture_time
        summary["status"] = "foundationpose_inference"
        inference = output / "foundationpose"
        command = [sys.executable, "-u", str(SCRIPTS / "run_foundationpose.py"),
                   "--dataset", str(observations), "--mesh", str(observations / "mesh/cube.obj"),
                   "--intrinsics-source", "calibration", "--cube-symmetry", "--output", str(inference)]
        with (output / "foundationpose.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        summary["status"] = "vision_pose_composition"
        pose = compose_world_pose(inference / "poses/000000.txt", observations / "world_T_camera_estimated.txt")
        np.savetxt(output / "world_T_object_estimated.txt", pose)
        summary["world_T_object_estimated"] = pose.tolist()
        summary["status"] = "physical_execution"
        if float(data.time) != capture_time:
            raise RuntimeError("Simulation advanced between image capture and planning")
        motion_result = run_trial(model, data, output / "motion", pose=pose, viewer=args.viewer, record=args.record)
        summary.update(success=motion_result["success"],
                       status="completed" if motion_result["success"] else "motion_failed", motion=motion_result)
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        print(summary["error"], file=sys.stderr)
    finally:
        (output / "summary.json").write_text(json.dumps(summary, indent=2))
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
