"""Compose a saved camera pose with the estimated eye-to-hand calibration."""
import argparse
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ma6216.vision import compose_world_pose


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-pose", type=Path, required=True)
    parser.add_argument("--estimated-extrinsic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pose = compose_world_pose(args.camera_pose, args.estimated_extrinsic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        np.savetxt(output, pose)
    print(f"Estimated world target: {pose[:3, 3]} m")


if __name__ == "__main__":
    main()
