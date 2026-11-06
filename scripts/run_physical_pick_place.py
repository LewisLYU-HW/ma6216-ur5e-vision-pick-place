"""Run physical Pick-and-Place from a baseline or an estimated world pose."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ma6216.scene import build_scene
from ma6216.runner import run_trial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/physical"))
    parser.add_argument("--cube-xy", nargs=2, type=float, default=[.46, -.18])
    parser.add_argument("--cube-yaw", type=float, default=0., help="Initial cube yaw in radians")
    parser.add_argument("--pose-file", type=Path, help="Estimated world_T_object 4x4 matrix")
    parser.add_argument("--trials", type=int, default=1)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--viewer", action="store_true", help="Show live MuJoCo viewer")
    mode.add_argument("--headless", action="store_true", help="Run without a viewer (default)")
    parser.add_argument("--record", action="store_true", help="Save an offscreen MP4")
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    pose = np.loadtxt(args.pose_file) if args.pose_file else None
    args.output.mkdir(parents=True, exist_ok=False)
    outcomes = []
    for trial in range(args.trials):
        model, data = build_scene(args.cube_xy, args.cube_yaw, calibration_board=False)
        outcomes.append(run_trial(model, data, args.output / f"trial_{trial:03d}",
                                  pose=pose, yaw=args.cube_yaw, viewer=args.viewer, record=args.record))
    successes = sum(result["success"] for result in outcomes)
    summary = {"trials": args.trials, "successes": successes, "results": outcomes}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    return 0 if successes == args.trials else 1


if __name__ == "__main__":
    raise SystemExit(main())
