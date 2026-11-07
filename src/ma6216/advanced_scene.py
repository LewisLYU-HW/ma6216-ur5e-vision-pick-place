"""Physical workcells for assembly, occlusion/regrasp, and conveyor tasks."""
from dataclasses import dataclass

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from .direct_route import configure_direct_table, set_front_ready
from .parts import configure_parts
from .pose_insertion import expanded_footprint, transform
from .scene import build_scene, look_at_quat, matrix_to_quat, mujoco
from .simulation_objects import PLUG, BLOCKER

WRIST_CAMERA = "wrist_camera"
MARKER_ID = 7
MARKER_SIZE = .060
FIXTURE_T_MARKER = transform([.105, 0., .0015])
SOCKET_DEPTH = .025
SOCKET_CLEARANCE = .003
TABLE_Z = .375
CRADLE_POSITION = np.array([.32, 0., .440])
OBSTRUCTION_DROP_POSITION = np.array([.58, .015, .385])


@dataclass
class TaskScene:
    model: object
    data: object
    task: str
    seed: int
    fixture_initial: np.ndarray
    parts: tuple
    belt_speed: float

    def disturb_fixture(self, dx=.012, dy=.004, yaw_deg=7.):
        """An environmental intervention, never passed to the controller."""
        pose = self.fixture_initial.copy()
        pose[:3, 3] += [dx, dy, 0.]
        pose[:3, :3] = Rotation.from_euler("z", yaw_deg, degrees=True).as_matrix() @ pose[:3, :3]
        mid = self.model.body_mocapid[self.model.body("target_tray").id]
        self.data.mocap_pos[mid] = pose[:3, 3]
        self.data.mocap_quat[mid] = matrix_to_quat(pose[:3, :3])


def add_marker(body):
    pattern = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),
                                            MARKER_ID, 6)
    centre = FIXTURE_T_MARKER[:3, 3]
    body.add_geom(name="marker_backing", type=mujoco.mjtGeom.mjGEOM_BOX,
                  pos=centre - [0., 0., .0005], size=[.04, .04, .0005],
                  rgba=[1., 1., 1., 1.], contype=0, conaffinity=0)
    cell = MARKER_SIZE / 6
    for row, col in zip(*np.where(pattern == 0)):
        position = centre + [(col + .5 - 3) * cell, (3 - row - .5) * cell, .00005]
        body.add_geom(name=f"marker_{row}_{col}", type=mujoco.mjtGeom.mjGEOM_BOX,
                      pos=position, size=[cell / 2, cell / 2, .00005],
                      rgba=[.01, .01, .01, 1.], contype=0, conaffinity=0)


def set_initial_pose(model, data, part, pose):
    adr = model.jnt_qposadr[model.joint(part.joint).id]
    data.qpos[adr:adr + 3] = pose[:3, 3]
    data.qpos[adr + 3:adr + 7] = matrix_to_quat(pose[:3, :3])


def build_task_scene(task="assembly", seed=0, *, belt_speed=.004, planning_parts=None):
    if task not in ("assembly", "clutter", "conveyor"):
        raise ValueError("Unknown manipulation task")
    rng = np.random.default_rng(seed)
    roll, pitch, yaw = (12., -10., 20.) + rng.uniform([-2., -2., -4.], [2., 2., 4.])
    source = transform([.40, -.18, .440], Rotation.from_euler("xyz", [roll, pitch, yaw], degrees=True).as_matrix())
    if task == "clutter":
        source = transform([.40, -.16, TABLE_Z + .025 + .001],
                           Rotation.from_euler("xyz", [90., 0., -8.], degrees=True).as_matrix())
    elif task == "conveyor":
        source = transform([.40, -.23, .405 + PLUG.half_height + .001],
                           Rotation.from_euler("z", 15., degrees=True).as_matrix())
    fixture = transform([.48, .17, .399],
                        Rotation.from_euler("xyz", [0., 5., -10.], degrees=True).as_matrix())
    fixture[:2, 3] += rng.uniform(-.005, .005, 2)
    physical_parts = (PLUG, BLOCKER) if task == "clutter" else (PLUG,)
    parts = physical_parts if planning_parts is None else planning_parts
    polygon, normals, _ = expanded_footprint(SOCKET_CLEARANCE)

    def configure(spec):
        configure_direct_table(spec)
        configure_parts(spec, parts)
        for body in spec.bodies:
            if body.name not in ("world", "target_cube", "target_orange", "target_tray"):
                body.gravcomp = 1.
        spec.option.impratio = 10.
        spec.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
        gripper = spec.body("gripper_base")
        eye = [.075, 0., .035]
        gripper.add_camera(name=WRIST_CAMERA, pos=eye, quat=look_at_quat(eye, [0., 0., .145]), fovy=80.)
        gripper.add_site(name="wrist_ft_site", pos=[0., 0., 0.], size=[.001, 0., 0.])
        for name, sensor_type in (("wrist_force", mujoco.mjtSensor.mjSENS_FORCE),
                                  ("wrist_torque", mujoco.mjtSensor.mjSENS_TORQUE)):
            spec.add_sensor(name=name, type=sensor_type, objtype=mujoco.mjtObj.mjOBJ_SITE,
                            objname="wrist_ft_site")
        tray = spec.body("target_tray")
        tray.mocap = True
        tray.pos = fixture[:3, 3]
        tray.quat = matrix_to_quat(fixture[:3, :3])
        bottom = spec.geom("tray_bottom")
        bottom.pos = [.045, 0., -.006]
        bottom.size = [.115, .075, .006]
        bottom.rgba = [.14, .24, .38, 1.]
        for name in ("left", "right", "front", "back"):
            old = spec.geom("tray_wall_" + name)
            old.contype = old.conaffinity = 0
            old.rgba = [0., 0., 0., 0.]
        for i, start in enumerate(polygon):
            end = polygon[(i + 1) % len(polygon)]
            edge = end - start
            centre = (start + end) / 2 + normals[i] * .003
            tray.add_geom(name=f"socket_wall_{i}", type=mujoco.mjtGeom.mjGEOM_BOX,
                          pos=[*centre, SOCKET_DEPTH / 2],
                          quat=matrix_to_quat(Rotation.from_euler("z", np.arctan2(edge[1], edge[0])).as_matrix()),
                          size=[np.linalg.norm(edge) / 2 + .003, .003, SOCKET_DEPTH / 2],
                          rgba=[.25, .31, .42, 1.], friction=[.6, .01, .001])
        add_marker(tray)
        if task == "assembly":
            plate = spec.worldbody.add_body(name="source_fixture", pos=source[:3, 3],
                                            quat=matrix_to_quat(source[:3, :3]))
            plate.add_geom(name="source_plate", type=mujoco.mjtGeom.mjGEOM_BOX,
                           pos=[0., 0., -.043], size=[.048, .033, .008],
                           rgba=[.38, .41, .45, 1.], friction=[1.2, .01, .001])
        elif task == "clutter":
            # Two rails leave the underside and front open for a horizontal
            # side grasp to release before a top grasp takes over.
            cradle = spec.worldbody.add_body(name="regrasp_cradle", pos=CRADLE_POSITION)
            for sign in (-1, 1):
                cradle.add_geom(name=f"cradle_rail_{sign}", type=mujoco.mjtGeom.mjGEOM_BOX,
                                pos=[sign * .034, 0., -.005], size=[.005, .033, .005],
                                rgba=[.50, .53, .59, 1.], friction=[1., .01, .001])
                cradle.add_geom(name=f"cradle_leg_{sign}", type=mujoco.mjtGeom.mjGEOM_BOX,
                                pos=[sign * .034, 0., -.035], size=[.005, .025, .030],
                                rgba=[.30, .32, .36, 1.])
            spec.worldbody.add_geom(name="obstruction_drop_pad", type=mujoco.mjtGeom.mjGEOM_BOX,
                                   pos=OBSTRUCTION_DROP_POSITION - [0., 0., .005],
                                   size=[.055, .04, .005], rgba=[.55, .45, .30, 1.])
        else:
            belt = spec.worldbody.add_body(name="conveyor", pos=[.40, -.20, .397], gravcomp=1.)
            belt.add_joint(name="belt_slide", type=mujoco.mjtJoint.mjJNT_SLIDE,
                           axis=[0., 1., 0.], damping=5.)
            belt.add_geom(name="belt_surface", type=mujoco.mjtGeom.mjGEOM_BOX,
                          size=[.10, .14, .008], mass=20., rgba=[.15, .18, .22, 1.],
                          friction=[1.2, .01, .001])
            spec.add_actuator(name="belt_drive", target="belt_slide", trntype=mujoco.mjtTrn.mjTRN_JOINT,
                              dyntype=mujoco.mjtDyn.mjDYN_NONE,
                              gaintype=mujoco.mjtGain.mjGAIN_FIXED, gainprm=[1000., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
                              biastype=mujoco.mjtBias.mjBIAS_AFFINE, biasprm=[0., 0., -1000., 0., 0., 0., 0., 0., 0., 0.])
            # Visual stripes move with the physically actuated belt surface.
            for i in range(7):
                belt.add_geom(name=f"belt_stripe_{i}", type=mujoco.mjtGeom.mjGEOM_BOX,
                              pos=[0., -.12 + .04 * i, .0081], size=[.098, .0015, .0001],
                              rgba=[.52, .57, .59, 1.], contype=0, conaffinity=0)

    model, data = build_scene(tuple(source[:2, 3]), calibration_board=False,
                              configure_spec=configure, object_z=float(source[2, 3]))
    set_initial_pose(model, data, PLUG, source)
    if task == "clutter":
        blocker_pose = transform([.46, -.235, TABLE_Z + BLOCKER.half_height + .001])
        set_initial_pose(model, data, BLOCKER, blocker_pose)
    set_front_ready(model, data)
    mujoco.mj_forward(model, data)
    return TaskScene(model, data, task, seed, fixture, physical_parts, belt_speed)
