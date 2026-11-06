"""Existing UR5e/2F85 workcell, with a fixed RGB-D camera and calibration target.

Geometry and physical parameters match the audited MA6216 workcell. Robot
assets are resolved separately through MA6216_MENAGERIE_DIR. Only trial
initial conditions are changed before physics starts.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from .config import ensure_mujoco_available, project_root

ensure_mujoco_available()

import mujoco
import numpy as np
from .workcell import build_workcell_spec

ROOT = project_root()
# Optional compatibility path for checking a historical local scene.
_original_scene = os.environ.get("MA6216_ORIGINAL_SCENE")
ORIGINAL_SCENE = Path(_original_scene).expanduser() if _original_scene else None
WIDTH, HEIGHT = 1280, 960
BOARD_COLS, BOARD_ROWS, SQUARE = 9, 6, 0.028
CAMERA_NAME = "vision_camera"
TRIAL_LAYOUTS = ((.46, -.18, 0.), (.43, -.16, 0.), (.48, -.20, 0.),
                 (.45, -.19, np.pi / 12), (.47, -.15, -np.pi / 6), (.44, -.21, np.pi / 4))


def matrix_to_quat(matrix):
    q = np.empty(4)
    mujoco.mju_mat2Quat(q, np.asarray(matrix, dtype=float).ravel())
    return q


def look_at_quat(eye, target):
    z = np.asarray(eye, float) - np.asarray(target, float)
    z /= np.linalg.norm(z)
    x = np.cross([0., 0., 1.], z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return matrix_to_quat(np.column_stack([x, y, z]))


def board_points():
    """Known, surveyed checker corner coordinates in target frame, in metres."""
    x, y = np.meshgrid(np.arange(1, BOARD_COLS + 1), np.arange(1, BOARD_ROWS + 1))
    points = np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)]) * SQUARE
    points[:, 0] -= (BOARD_COLS + 1) * SQUARE / 2
    points[:, 1] -= (BOARD_ROWS + 1) * SQUARE / 2
    points[:, 2] = 0.001
    return points.astype(np.float32)


def build_scene(cube_xy=(0.46, -0.18), cube_yaw=0., *, calibration_board=True,
                configure_spec=None, object_z=.401):
    if ORIGINAL_SCENE is None:
        spec = build_workcell_spec()
    else:
        source = ORIGINAL_SCENE.read_text()
        tree = ast.parse(source, filename=str(ORIGINAL_SCENE))
        prefix = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "model" for t in node.targets):
                break
            prefix.append(node)
        else:
            raise RuntimeError("Original scene compilation boundary not found; audit required")
        namespace = {"__file__": str(ORIGINAL_SCENE)}
        exec(compile(ast.Module(body=prefix, type_ignores=[]), str(ORIGINAL_SCENE), "exec"), namespace)
        spec = namespace["spec"]
    spec.modelname = "MA6216 audited UR5e physical and vision workcell"
    spec.body("target_cube").pos = [*cube_xy, object_z]
    spec.body("target_cube").quat = [np.cos(cube_yaw / 2), 0, 0, np.sin(cube_yaw / 2)]
    if configure_spec is not None:
        configure_spec(spec)
    spec.worldbody.add_camera(name=CAMERA_NAME, pos=[1.05, -1.05, 1.20],
                              quat=look_at_quat([1.05, -1.05, 1.20], [0.45, 0., 0.43]), fovy=45.)
    spec.worldbody.add_camera(name="overview", pos=[1.35, -1.5, 1.15],
                              quat=look_at_quat([1.35, -1.5, 1.15], [0.40, 0., 0.43]), fovy=50.)
    spec.visual.global_.offwidth = 1280
    spec.visual.global_.offheight = 960
    if calibration_board:
        board = spec.worldbody.add_body(name="calibration_board", mocap=True, pos=[0, 0, -10])
        w, h = (BOARD_COLS + 1) * SQUARE, (BOARD_ROWS + 1) * SQUARE
        common = dict(type=mujoco.mjtGeom.mjGEOM_BOX, contype=0, conaffinity=0)
        board.add_geom(name="checker_backing", pos=[0, 0, -0.003], size=[w/2+.025, h/2+.025, .003], rgba=[1,1,1,1], **common)
        for row in range(BOARD_ROWS + 1):
            for col in range(BOARD_COLS + 1):
                value = .02 if (row + col) % 2 == 0 else .98
                board.add_geom(name=f"checker_{row}_{col}", pos=[(col+.5)*SQUARE-w/2, (row+.5)*SQUARE-h/2, 0],
                               size=[SQUARE/2, SQUARE/2, .001], rgba=[value,value,value,1], **common)
        board.add_geom(name="checker_origin_marker", type=mujoco.mjtGeom.mjGEOM_CYLINDER,
                       pos=[-w/2-.012, -h/2-.012, .001], size=[.008,.001,0],
                       rgba=[1,0,1,1], contype=0, conaffinity=0)
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, model.key("home").id)
    data.ctrl[:6] = [-1.5708, -1.5708, 1.5708, -1.5708, -1.5708, 0]
    data.ctrl[model.actuator("gripper_fingers_actuator").id] = 0
    # The original home key was defined before adding the free object.
    adr = model.jnt_qposadr[model.joint("target_cube_freejoint").id]
    data.qpos[adr:adr+3] = [*cube_xy, object_z]
    data.qpos[adr+3:adr+7] = [np.cos(cube_yaw/2),0,0,np.sin(cube_yaw/2)]
    mujoco.mj_forward(model, data)
    return model, data


def camera_ground_truth(model, data, width=WIDTH, height=HEIGHT):
    """Evaluation/acquisition reference only; never an estimated calibration."""
    cid = model.camera(CAMERA_NAME).id
    f = .5 * height / np.tan(np.deg2rad(model.cam_fovy[cid]) / 2)
    K = np.array([[f,0,(width-1)/2], [0,f,(height-1)/2], [0,0,1.]])
    T = np.eye(4)
    T[:3,:3] = data.cam_xmat[cid].reshape(3,3) @ np.diag([1.,-1.,-1.])
    T[:3,3] = data.cam_xpos[cid]
    return K, T
