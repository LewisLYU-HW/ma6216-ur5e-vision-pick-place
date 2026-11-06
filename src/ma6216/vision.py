"""RGB-D observation, image mask, and estimated camera-to-world pose chain."""
from pathlib import Path
import shutil

import cv2
import numpy as np
import trimesh

from .scene import CAMERA_NAME, HEIGHT, WIDTH, mujoco
from .foundationpose import validate_pose


def image_mask(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    red = cv2.inRange(hsv, (0, 100, 70), (10, 255, 255))
    red |= cv2.inRange(hsv, (170, 100, 70), (179, 255, 255))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(red)
    if count < 2:
        raise RuntimeError("No red target visible")
    target = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    if stats[target, cv2.CC_STAT_AREA] < 40:
        raise RuntimeError("Too few target image pixels")
    return (labels == target).astype(np.uint8) * 255


def prepare_observation_dir(folder, calibration, *, export_target_mesh=None):
    """Calibration directory contains estimated camera parameters only."""
    folder, calibration = Path(folder), Path(calibration)
    folder.mkdir(parents=True, exist_ok=False)
    for name in ("rgb", "depth", "masks", "mesh"):
        (folder / name).mkdir()
    if export_target_mesh is None:
        mesh_file = folder / "mesh/cube.obj"
        mesh = trimesh.creation.box(extents=[.05, .05, .05])
        mesh.visual.vertex_colors = np.tile([242, 20, 20, 255], (len(mesh.vertices), 1))
        mesh.export(str(mesh_file))
    else:
        mesh_file = folder / "mesh/workpiece.obj"
        export_target_mesh(mesh_file)
    shutil.copyfile(calibration / "cam_K.txt", folder / "cam_K.txt")
    shutil.copyfile(calibration / "world_T_camera.txt", folder / "world_T_camera_estimated.txt")
    return mesh_file


def make_renderer(model):
    return mujoco.Renderer(model, height=HEIGHT, width=WIDTH)


def capture_observation(renderer, data, folder, frame, *, segment=image_mask):
    """Only rendered image and depth enter the perception branch."""
    renderer.update_scene(data, camera=CAMERA_NAME)
    renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
    renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
    rgb = renderer.render()
    mask = (np.asarray(segment(rgb)) > 0).astype(np.uint8) * 255
    renderer.enable_depth_rendering()
    try:
        depth = renderer.render().astype(np.float32)
    finally:
        renderer.disable_depth_rendering()
    cv2.imwrite(str(folder / f"rgb/{frame}.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(folder / f"masks/{frame}.png"), mask)
    np.save(folder / f"depth/{frame}.npy", depth)
    return mask, depth


def compose_world_pose(camera_pose_file, estimated_extrinsic_file):
    """T_W_O = estimated T_W_C @ FoundationPose T_C_O; no truth is accepted."""
    camera_T_object = validate_pose(np.loadtxt(camera_pose_file))
    world_T_camera = validate_pose(np.loadtxt(estimated_extrinsic_file))
    return world_T_camera @ camera_T_object
