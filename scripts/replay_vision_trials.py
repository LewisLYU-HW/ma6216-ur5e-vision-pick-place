"""Run physical tests on the six rendered scenes, with the same scene presets."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ma6216.scene import TRIAL_LAYOUTS, build_scene, mujoco
from ma6216.runner import run_trial
from ma6216.vision import compose_world_pose


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=Path("artifacts/vision_inputs"))
    parser.add_argument("--inference", type=Path, default=Path("artifacts/foundationpose_cube"))
    parser.add_argument("--baseline", action="store_true", help="Use ground truth for the comparison baseline")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    outcomes = []
    for index, (x, y, yaw) in enumerate(TRIAL_LAYOUTS):
        trial = f"trial_{index:02d}"
        output = args.output / trial
        output.mkdir()
        pose = None
        if not args.baseline:
            pose = compose_world_pose(args.inference / trial / "poses/000000.txt",
                                      args.inputs / trial / "world_T_camera_estimated.txt")
            np.savetxt(output / "world_T_object_estimated.txt", pose)
        model, data = build_scene((x, y), yaw, calibration_board=False)
        for _ in range(775):
            mujoco.mj_step(model, data)
        result = run_trial(model, data, output / "trial_000", pose=pose, yaw=yaw if args.baseline else 0.)
        (output / "summary.json").write_text(json.dumps({"trials": 1, "successes": int(result["success"]),
                                                        "results": [result]}, indent=2))
        outcomes.append({"trial": trial, "result": result})
    successes = sum(trial["result"]["success"] for trial in outcomes)
    (args.output / "summary.json").write_text(json.dumps({"trials": len(outcomes), "successes": successes,
                                                        "outcomes": outcomes}, indent=2))
    print(f"PHYSICAL TRIALS: {successes}/{len(outcomes)}", flush=True)
    return 0 if successes == len(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
