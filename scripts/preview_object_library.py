"""Inspect four diverse objects; this viewer does not execute any grasp."""
import argparse
from pathlib import Path
import sys
import time

import cv2

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from ma6216.object_library import DIVERSE_PARTS,SCREWDRIVER
from ma6216.multi_object import build_multi_scene
from ma6216.scene import CAMERA_NAME,mujoco
from ma6216.vision import make_renderer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--viewer",action="store_true")
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    model,data=build_multi_scene((*DIVERSE_PARTS,SCREWDRIVER))
    for _ in range(775):mujoco.mj_step(model,data)
    renderer=make_renderer(model)
    try:
        renderer.update_scene(data,camera=CAMERA_NAME)
        renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW]=False
        cv2.imwrite(str(args.output/"object_library.png"),cv2.cvtColor(renderer.render(),cv2.COLOR_RGB2BGR))
    finally:
        renderer.close()
    if args.viewer:
        from mujoco import viewer
        with viewer.launch_passive(model,data) as handle:
            with handle.lock():
                handle.cam.lookat[:]=[.48,0,.4]
                handle.cam.distance=1.6
                handle.cam.azimuth=130
                handle.cam.elevation=-35
            while handle.is_running():
                started=time.monotonic()
                mujoco.mj_step(model,data)
                handle.sync()
                time.sleep(max(0,model.opt.timestep-(time.monotonic()-started)))
    print("Saved object_library.png; preview only, no manipulation performed")


if __name__=="__main__":
    main()
