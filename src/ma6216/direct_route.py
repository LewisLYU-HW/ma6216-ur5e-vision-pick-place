"""Continuous front-facing Cartesian waypoints for the UR5e workcell."""
from __future__ import annotations

import math

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .scene import mujoco
from .motion import ACTUATOR_NAMES, JOINT_NAMES, MotionFailure, Robot


# TCP about (0.34, -0.10, 0.60) m, with vertical approach axis. The same
# elbow/wrist branch reaches both front-table destinations on the new layout.
FRONT_READY = np.array([.10169, -1.44147, -.93557, -2.33535, 1.57080, .10169])
TABLE_FRONT_X = .26
TRANSFER_Z = .56
SAMPLE_SPACING_M = .015


def configure_direct_table(spec):
    """Give the upper arm clearance, preserving top height and far edge."""
    table = spec.geom("worktable")
    position, half_size = np.asarray(table.pos).copy(), np.asarray(table.size).copy()
    far_edge = position[0] + half_size[0]
    position[0] = (far_edge + TABLE_FRONT_X) / 2
    half_size[0] = (far_edge - TABLE_FRONT_X) / 2
    table.pos, table.size = position, half_size


def set_front_ready(model, data):
    """Select the new starting keyframe before stepping simulation physics."""
    joints = np.asarray([model.joint(name).id for name in JOINT_NAMES])
    actuators = np.asarray([model.actuator(name).id for name in ACTUATOR_NAMES])
    low = np.maximum(model.jnt_range[joints, 0], model.actuator_ctrlrange[actuators, 0])
    high = np.minimum(model.jnt_range[joints, 1], model.actuator_ctrlrange[actuators, 1])
    if np.any(FRONT_READY < low) or np.any(FRONT_READY > high):
        raise MotionFailure("Front-ready posture falls outside the arm limits")
    scratch = mujoco.MjData(model)
    scratch.qpos[:] = data.qpos
    scratch.qpos[model.jnt_qposadr[joints]] = FRONT_READY
    mujoco.mj_forward(model, scratch)
    robot = Robot(model, data)
    if contacts := robot.collision_contacts(scratch, penetration=0.):
        raise MotionFailure(f"Front-ready posture has unexpected contact: {contacts}")
    data.qpos[model.jnt_qposadr[joints]] = FRONT_READY
    data.qvel[model.jnt_dofadr[joints]] = 0.
    data.ctrl[actuators] = FRONT_READY
    mujoco.mj_forward(model, data)


def plan_direct(robot, xyz, yaw, grasp_z, place_z, carry_offset_z, source, *, destination_xy=None,
                payload_destination_xy=None):
    """Plan a vertical pick, horizontal loaded transfer, and vertical place.

    Every IK sample is seeded from the previous configuration. Collision
    checks include the swept payload when carrying. No live qpos is written.
    """
    xyz = np.asarray(xyz, dtype=float)
    rotation = Rotation.from_euler("z", yaw).as_matrix() @ np.diag([1., -1., -1.])
    tray = (robot.model.body("target_tray").pos[:2].copy() if destination_xy is None
            else np.asarray(destination_xy, dtype=float))
    pick_hover = np.r_[xyz[:2], TRANSFER_Z]
    tray_hover = np.r_[tray, TRANSFER_Z]
    positions = [
        ("APPROACH", pick_hover),
        ("GRASP", np.r_[xyz[:2], grasp_z]),
        ("LIFT", pick_hover),
        ("HOVER_TRAY", tray_hover),
        ("PLACE", np.r_[tray, place_z]),
        ("RETREAT", tray_hover),
    ]
    original_qpos = robot.initial_qpos.copy()
    object_adr = robot.cube_qposadr
    robot.scratch.qpos[:] = original_qpos
    q = robot.data.ctrl[robot.aids].copy()
    start_position, start_rotation = robot.fk(q)
    ready_position = start_position.copy()
    waypoints = []
    try:
        for stage, destination in positions:
            if stage == "RETREAT":
                # Check withdrawal against the object after release at the tray.
                robot.initial_qpos[object_adr:object_adr + 2] = (tray if payload_destination_xy is None
                                                               else payload_destination_xy)
                robot.initial_qpos[object_adr + 2] += .014  # tray floor above tabletop
            length = float(np.linalg.norm(destination - start_position))
            segments = max(16 if stage == "HOVER_TRAY" else 1, math.ceil(length / SAMPLE_SPACING_M))
            path = [q.tolist()]
            path_samples = 0
            max_joint_step = 0.
            interpolate_rotation = Slerp([0., 1.], Rotation.from_matrix([start_rotation, rotation]))
            for index in range(1, segments + 1):
                fraction = index / segments
                position = (1 - fraction) * start_position + fraction * destination
                attitude = interpolate_rotation(fraction).as_matrix()
                next_q, error = robot.solve(position, attitude, q)
                joint_step = float(np.max(np.abs(next_q - q)))
                if joint_step > .30:
                    raise MotionFailure(f"IK branch change in {stage} sample {index}/{segments}: {joint_step:.3f} rad")
                carrying = stage in ("LIFT", "HOVER_TRAY", "PLACE")
                ok, check = robot.check_path(q, next_q, allow_cube=carrying or stage == "GRASP",
                                             carry_offset_z=carry_offset_z if carrying else None)
                if not ok:
                    raise MotionFailure(f"Direct path collision in {stage} sample {index}/{segments}: {check}")
                path_samples += check["samples"]
                max_joint_step = max(max_joint_step, joint_step)
                q = next_q
                path.append(q.tolist())
            waypoints.append({
                "name": stage, "q": q.tolist(), "tcp_position": destination.tolist(),
                "path_q": path, "ik": error,
                "collision_check": {"samples": path_samples, "cartesian_segments": segments,
                                    "max_joint_step_rad": max_joint_step},
            })
            start_position, start_rotation = destination, rotation
    finally:
        robot.initial_qpos[:] = original_qpos
    return {"source": source, "route": "front_cartesian", "ready_tcp_m": ready_position.tolist(),
            "object_position": xyz.tolist(), "object_yaw_rad": float(yaw),
            "planning_cube_qpos": original_qpos[object_adr:object_adr + 7].tolist(),
            "pinch_rotation": rotation.tolist(), "waypoints": waypoints}
