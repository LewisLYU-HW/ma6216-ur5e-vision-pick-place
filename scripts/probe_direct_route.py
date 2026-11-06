"""Re-run both routes on the same cube and the same saved vision estimate."""
import argparse
import json
from pathlib import Path

import numpy as np

from run_front_pick_place import FrontRobot, path_metrics
from ma6216.direct_route import FRONT_READY, configure_direct_table, set_front_ready
from ma6216.motion import Robot
from ma6216.runner import run_trial
from ma6216.scene import build_scene, mujoco
from ma6216.config import project_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pose", type=Path, default=project_root()/"demo_data/reference_cube_world_pose.txt")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    pose = np.loadtxt(args.pose)
    results = {"pose_file": str(args.pose.resolve()), "runs": {}}
    for name, direct in [("legacy", False), ("front", True)]:
        model, data = build_scene(calibration_board=False,
                                  configure_spec=configure_direct_table if direct else None)
        original_robot = Robot(model, data)
        ready_ok, ready_detail = original_robot.check_path(original_robot.home, FRONT_READY)
        if direct:
            set_front_ready(model, data)
        for _ in range(775):
            mujoco.mj_step(model, data)
        robot = FrontRobot(model, data, workpiece=False) if direct else Robot(model, data)
        result = run_trial(model, data, output / name, pose=pose, robot=robot)
        tcp_x = [sample["tcp_position_m"][0] for sample in robot.samples]
        results["runs"][name] = {
            "success": result["success"],
            "motion_seconds": float(result.get("simulation_time_s", data.time)) - 775 * model.opt.timestep,
            "min_tcp_x_m": min(tcp_x) if tcp_x else None,
            "bilateral_loaded_contact_fraction": result.get("bilateral_loaded_contact_fraction"),
            "max_unexpected_robot_penetration_m": result.get("max_unexpected_robot_penetration_m"),
            "old_home_to_front_ready_single_joint_segment": {"passes": ready_ok, "detail": ready_detail},
            "route_metrics": path_metrics(robot.samples),
        }
    (output / "comparison.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    return 0 if all(result["success"] for result in results["runs"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
