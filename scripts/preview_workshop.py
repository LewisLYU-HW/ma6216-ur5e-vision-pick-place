"""Render the textured repair bench, optionally opening the MuJoCo viewer."""

import argparse
from pathlib import Path
import sys
import time

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.workshop_scene import build_workshop_scene
from ma6216.scene import mujoco


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "artifacts/workshop_preview")
    p.add_argument("--viewer", action="store_true")
    p.add_argument(
        "--rack-assembly", action="store_true", help="Preview the independent support assembly task"
    )
    p.add_argument("--complete-task", action="store_true", help="Preview the continuous four-object task")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    scene = build_workshop_scene(rack_assembly=args.rack_assembly, complete_task=args.complete_task)
    for _ in range(1000):
        mujoco.mj_step(scene.model, scene.data)
    with mujoco.Renderer(scene.model, height=960, width=1280) as renderer:
        for camera in ("overview", "vision_camera", "wrist_camera"):
            renderer.update_scene(scene.data, camera=camera)
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = True
            rgb = renderer.render()
            cv2.imwrite(str(args.output / (camera + ".png")), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    print(args.output)
    if args.viewer:
        from mujoco import viewer as interactive_viewer

        with interactive_viewer.launch_passive(scene.model, scene.data) as viewer:
            while viewer.is_running():
                mujoco.mj_step(scene.model, scene.data)
                viewer.sync()
                time.sleep(scene.model.opt.timestep)


if __name__ == "__main__":
    main()
