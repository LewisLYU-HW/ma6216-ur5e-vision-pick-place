"""Run the existing FoundationPose environment on rendered RGB-D inputs."""

from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ma6216.foundationpose import run_sequence
from ma6216.config import foundationpose_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--mesh", type=Path, required=True,
                        help="CAD mesh matching the rendered object, in metres")
    parser.add_argument("--output", type=Path, required=True,
                        help="New/empty output directory; existing evidence is preserved")
    parser.add_argument("--repository", type=Path,
                        help="Official checkout; otherwise resolve MA6216_FOUNDATIONPOSE_DIR or third_party/FoundationPose")
    parser.add_argument("--intrinsics", type=Path,
                        help="Estimated pinhole K; defaults to dataset/cam_K.txt")
    parser.add_argument("--intrinsics-source", choices=["calibration", "provided", "simulator_reference"],
                        default="provided")
    parser.add_argument("--depth-scale", type=float, default=0.001,
                        help="Metres per unit for uint16 PNG depth; float NPY is always metres")
    parser.add_argument("--mode", choices=["register-track", "register-each"], default="register-track")
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--registration-iterations", type=int, default=5)
    parser.add_argument("--tracking-iterations", type=int, default=2)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--cube-symmetry", action="store_true",
                        help="Supply the 24 proper symmetries of a centred unmarked cube")
    parser.add_argument("--upright-extrinsic", type=Path,
                        help="Estimated world_T_camera; initialize yaw across 360 degrees for an upright object")
    args = parser.parse_args()
    if args.repository is None:
        args.repository = foundationpose_dir()
    summary = run_sequence(**vars(args))
    print(json.dumps({key: summary[key] for key in ["status", "selected_frames", "completed_frames"]}))


if __name__ == "__main__":
    main()
