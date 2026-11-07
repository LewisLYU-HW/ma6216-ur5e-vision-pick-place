"""Six-DoF pick, reorientation and physical seating in a keyed shallow nest.

The palletizing block and UR5e/2F-85 are reused. A fixed inclined plate
presents the free workpiece with nonzero roll/pitch. Only image estimates
enter the normal planner; fixture geometry is surveyed workcell geometry.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .direct_route import configure_direct_table, set_front_ready
from .foundationpose import validate_rigid_transform
from .motion import MotionFailure, Robot
from .palletizing import FOOTPRINT, PARTS
from .parts import configure_parts
from .scene import build_scene, look_at_quat, matrix_to_quat, mujoco


BLOCK = PARTS[0]
FLOOR_Z = .389
WALL_HEIGHT = .008
WALL_THICKNESS = .006
RELEASE_GAP = .012
TRANSFER_Z = .56
WRIST_CAMERA = "wrist_camera"
# x, y, z, roll, pitch, yaw; angles in degrees. These are scene initial
# conditions, never supplied to FoundationPose or the visual grasp planner.
LAYOUTS = (
    (.42, -.18, .430, 0., 0., 18.),
    (.43, -.19, .440, 10., -8., 22.),
    (.35, -.14, .435, -18., 16., -18.),
    (.38, -.20, .435, 20., 14., -25.),
)


def transform(position, rotation=None):
    pose = np.eye(4)
    pose[:3, 3] = position
    if rotation is not None:
        pose[:3, :3] = rotation
    return pose


def set_object_pose(qpos, model, pose):
    """Initialization/private planner data; never called on live execution data."""
    adr = model.jnt_qposadr[model.joint(BLOCK.joint).id]
    qpos[adr:adr + 3] = pose[:3, 3]
    qpos[adr + 3:adr + 7] = matrix_to_quat(pose[:3, :3])


def object_pose(model, data):
    """Explicit ground-truth baseline or independent evaluation only."""
    body = model.body(BLOCK.body).id
    return transform(data.xpos[body].copy(), data.xmat[body].reshape(3, 3).copy())


def expanded_footprint(clearance):
    """Offset every polygon edge outward by the specified per-side clearance."""
    if not np.isfinite(clearance) or not .0005 <= clearance <= .003:
        raise ValueError("Nest clearance must be between 0.5 and 3 mm per side")
    points = np.asarray(FOOTPRINT, dtype=float) / 1000
    edges = np.roll(points, -1, axis=0) - points
    normals = np.c_[edges[:, 1], -edges[:, 0]]
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    offsets = np.einsum("ij,ij->i", normals, points) + clearance
    corners = np.array([np.linalg.solve(normals[[i - 1, i]], offsets[[i - 1, i]])
                        for i in range(len(points))])
    return corners, normals, offsets


@dataclass(frozen=True)
class Nest:
    clearance: float = .0025
    xy: tuple = (.49, .18)
    yaw_deg: float = 0.

    @property
    def target_pose(self):
        return transform([*self.xy, FLOOR_Z + .020],
                         Rotation.from_euler("z", self.yaw_deg, degrees=True).as_matrix())


def build_insertion_scene(layout=1, nest=None):
    nest = nest or Nest()
    if layout not in range(len(LAYOUTS)):
        raise ValueError(f"layout must be in 0..{len(LAYOUTS) - 1}")
    x, y, z, roll, pitch, yaw = LAYOUTS[layout]
    source_rotation = Rotation.from_euler("xyz", [roll, pitch, yaw], degrees=True).as_matrix()
    initial = transform([x, y, z], source_rotation)
    polygon, normals, _ = expanded_footprint(nest.clearance)

    def configure(spec):
        configure_direct_table(spec)
        configure_parts(spec, (BLOCK,))
        # Set before compilation so MuJoCo builds gravity-compensation terms.
        for body in spec.bodies:
            if body.name not in ("world", BLOCK.body, "target_tray"):
                body.gravcomp = 1.
        spec.option.impratio = 10.
        spec.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
        # Observation-only virtual camera rigidly mounted beside the gripper.
        # Its local pose stays fixed; it never tracks the workpiece's truth pose.
        camera_position = [.075, 0., .035]
        spec.body("gripper_base").add_camera(
            name=WRIST_CAMERA, pos=camera_position,
            quat=look_at_quat(camera_position, [0., 0., .145]), fovy=80.,
            mode=mujoco.mjtCamLight.mjCAMLIGHT_FIXED)
        # Keep the inherited tray and support height; enlarge its footprint.
        spec.body("target_tray").pos = [*nest.xy, .375]
        spec.geom("tray_bottom").size = [.16, .10, .007]
        for name, sign in (("left", -1), ("right", 1)):
            spec.geom("tray_wall_" + name).pos = [sign * .155, 0, .034]
        for name in ("front", "back"):
            spec.geom("tray_wall_" + name).size = [.16, .005, .02]
        plate = spec.worldbody.add_body(name="source_fixture", pos=initial[:3, 3],
                                        quat=matrix_to_quat(source_rotation))
        plate.add_geom(name="source_plate", type=mujoco.mjtGeom.mjGEOM_BOX,
                       pos=[0, 0, -.028], size=[.047, .032, .008],
                       rgba=[.40, .43, .47, 1], friction=[1.2, .01, .001])
        # A fixed pedestal makes the support visible; it has no connection to
        # the workpiece, which retains its original free joint.
        height = (z - .375) / source_rotation[2, 2] - .036
        plate.add_geom(name="source_pedestal", type=mujoco.mjtGeom.mjGEOM_CYLINDER,
                       pos=[0, 0, -.036 - height / 2], size=[.012, height / 2, 0],
                       rgba=[.3, .32, .35, 1])
        holder = spec.worldbody.add_body(name="keyed_nest", pos=[*nest.xy, FLOOR_Z],
                                         quat=matrix_to_quat(nest.target_pose[:3, :3]))
        for i, start in enumerate(polygon):
            end = polygon[(i + 1) % len(polygon)]
            edge = end - start
            centre = (start + end) / 2 + normals[i] * WALL_THICKNESS / 2
            holder.add_geom(name=f"nest_wall_{i}", type=mujoco.mjtGeom.mjGEOM_BOX,
                            pos=[*centre, WALL_HEIGHT / 2],
                            quat=matrix_to_quat(Rotation.from_euler("z", np.arctan2(edge[1], edge[0])).as_matrix()),
                            size=[np.linalg.norm(edge) / 2 + WALL_THICKNESS / 2,
                                  WALL_THICKNESS / 2, WALL_HEIGHT / 2],
                            rgba=[.25, .28, .33, 1], friction=[.8, .01, .001])

    model, data = build_scene((x, y), calibration_board=False, configure_spec=configure, object_z=z)
    initial[:3, 3] += source_rotation[:, 2] * .001
    set_object_pose(data.qpos, model, initial)
    set_front_ready(model, data)
    mujoco.mj_forward(model, data)
    return model, data, nest


def grasp_transform(estimated_pose, mode="full"):
    """Use all six pose components. yaw-only is an explicitly labelled ablation."""
    pose = validate_rigid_transform(estimated_pose).copy()
    if mode == "yaw-only":
        pose[:3, :3] = Rotation.from_euler("z", np.arctan2(pose[1, 0], pose[0, 0])).as_matrix()
    elif mode != "full":
        raise ValueError("pose mode must be full or yaw-only")
    object_T_tcp = transform([0, 0, BLOCK.grasp_offset_z], np.diag([1., -1., -1.]))
    return pose, pose @ object_T_tcp


def insertion_outcome(model, data, nest):
    """Acceptance uses physical state only, downstream of control."""
    actual = object_pose(model, data)
    target = nest.target_pose
    relative = np.linalg.inv(target) @ actual
    vertices = BLOCK.vertices @ relative[:3, :3].T + relative[:3, 3]
    _, normals, offsets = expanded_footprint(nest.clearance)
    clearance = float(np.min(offsets[:, None] - normals @ vertices[:, :2].T))
    angle = float(np.rad2deg(Rotation.from_matrix(relative[:3, :3]).magnitude()))
    error = float(np.linalg.norm(relative[:3, 3]))
    bottom_gap = float(np.min(vertices[:, 2]) + .020)
    body = model.body(BLOCK.body).id
    dof = model.jnt_dofadr[model.joint(BLOCK.joint).id]
    linear_speed = float(np.linalg.norm(data.qvel[dof:dof + 3]))
    angular_speed = float(np.linalg.norm(data.qvel[dof + 3:dof + 6]))
    target_geom, bottom = model.geom(BLOCK.geom).id, model.geom("tray_bottom").id
    force, penetration = 0., 0.
    for i, contact in enumerate(data.contact):
        if target_geom not in (int(contact.geom1), int(contact.geom2)):
            continue
        penetration = max(penetration, float(-contact.dist))
        if {int(contact.geom1), int(contact.geom2)} == {target_geom, bottom}:
            wrench = np.zeros(6)
            mujoco.mj_contactForce(model, data, i, wrench)
            force += max(0., float(wrench[0]))
    success = (error < .003 and angle < 5. and clearance > -.0003 and
               abs(bottom_gap) < .0015 and force > .2 and
               linear_speed < .005 and angular_speed < .05)
    return {"success": bool(success), "position_error_mm": 1000 * error,
            "rotation_error_deg": angle, "bottom_gap_mm": 1000 * bottom_gap,
            "minimum_wall_clearance_mm": 1000 * clearance, "bottom_support_force_n": force,
            "linear_speed_m_s": linear_speed, "angular_speed_rad_s": angular_speed,
            "max_workpiece_penetration_mm": 1000 * penetration,
            "world_T_object": actual.tolist(), "world_T_target": target.tolist(),
            "body_com_m": data.xipos[body].tolist()}


class InsertionRobot(Robot):
    def __init__(self, model, data, estimate, nest, *, ground_truth=False, pose_mode="full"):
        super().__init__(model, data, target_vertices=BLOCK.vertices,
                         target_body=BLOCK.body, target_geom=BLOCK.geom, target_joint=BLOCK.joint)
        self.estimate = validate_rigid_transform(estimate).copy()
        self.nest, self.ground_truth, self.pose_mode = nest, ground_truth, pose_mode
        set_object_pose(self.initial_qpos, model, self.estimate)

    def collision_contacts(self, data=None, allow_cube=False, penetration=.0005):
        bad = super().collision_contacts(data, allow_cube, penetration)
        if data is self.data:
            intended = {self.model.geom(name).id for name in
                        ["source_plate", "tray_bottom"] + [f"nest_wall_{i}" for i in range(5)]}
            for c in data.contact:
                g1, g2 = int(c.geom1), int(c.geom2)
                if self.cgid not in (g1, g2) or c.dist >= -penetration:
                    continue
                other = g2 if g1 == self.cgid else g1
                if other in intended or int(self.model.geom_bodyid[other]) in self.robot_bodies:
                    continue
                bad.append({"geom1": self.model.geom(g1).name, "geom2": self.model.geom(g2).name,
                            "penetration_m": float(-c.dist), "reason": "unexpected payload contact"})
        return bad

    def plan(self, object_pose=None, yaw=0.):
        estimate = self.estimate if object_pose is None else object_pose
        source, grasp = grasp_transform(estimate, self.pose_mode)
        xyz = source[:3, 3]
        if not (.30 < xyz[0] < .63 and -.30 < xyz[1] < -.04 and .39 < xyz[2] < .49):
            raise MotionFailure(f"Estimated source outside fixture workspace: {xyz}")
        if source[2, 2] < .80:
            raise MotionFailure("This task validates source tilts below about 37 degrees")
        tool_T_object = np.linalg.inv(grasp) @ source
        target = self.nest.target_pose
        release = target.copy()
        release[2, 3] += RELEASE_GAP
        release_tcp = release @ np.linalg.inv(tool_T_object)
        approach = grasp.copy()
        approach[:3, 3] += source[:3, 2] * .12
        lift = grasp.copy()
        lift[:3, 3] += source[:3, 2] * .15
        hover = release_tcp.copy()
        hover[2, 3] = TRANSFER_Z
        targets = [("APPROACH", approach), ("GRASP", grasp), ("LIFT", lift),
                   ("HOVER_TRAY", hover), ("PLACE", release_tcp), ("RETREAT", hover)]
        original = self.initial_qpos.copy()
        set_object_pose(self.initial_qpos, self.model, source)
        q = self.data.ctrl[self.aids].copy()
        self.scratch.qpos[:] = self.initial_qpos
        start_p, start_r = self.fk(q)
        waypoints = []
        try:
            for stage, destination in targets:
                carrying = stage in ("LIFT", "HOVER_TRAY", "PLACE")
                if stage == "RETREAT":
                    set_object_pose(self.initial_qpos, self.model, target)
                distance = np.linalg.norm(destination[:3, 3] - start_p)
                turn = Rotation.from_matrix(destination[:3, :3] @ start_r.T).magnitude()
                segments = max(1, math.ceil(distance / .012), math.ceil(turn / .06))
                interpolator = Slerp([0., 1.], Rotation.from_matrix([start_r, destination[:3, :3]]))
                path, samples = [q.tolist()], 0
                for index in range(1, segments + 1):
                    fraction = index / segments
                    tcp = transform((1 - fraction) * start_p + fraction * destination[:3, 3],
                                    interpolator(fraction).as_matrix())
                    if carrying:
                        set_object_pose(self.initial_qpos, self.model, tcp @ tool_T_object)
                    next_q, error = self.solve(tcp[:3, 3], tcp[:3, :3], q)
                    if np.max(np.abs(next_q - q)) > .30:
                        raise MotionFailure(f"IK branch change in {stage}")
                    count = max(2, math.ceil(float(np.max(np.abs(next_q - q))) / .025) + 1)
                    for u in np.linspace(0, 1, count):
                        self.scratch.qpos[:] = self.initial_qpos
                        position, rotation = self.fk((1 - u) * q + u * next_q)
                        if carrying:
                            set_object_pose(self.scratch.qpos, self.model,
                                            transform(position, rotation) @ tool_T_object)
                            mujoco.mj_forward(self.model, self.scratch)
                        bad = self.collision_contacts(allow_cube=carrying or stage == "GRASP")
                        if bad:
                            raise MotionFailure(f"{stage} robot collision: {bad}")
                        if carrying:
                            for c in self.scratch.contact:
                                if self.cgid not in (int(c.geom1), int(c.geom2)) or c.dist >= -.0005:
                                    continue
                                other = int(c.geom2) if int(c.geom1) == self.cgid else int(c.geom1)
                                if other in self.pad_sides:
                                    continue
                                # Expected source support during lift-off. All
                                # destination walls remain collision obstacles.
                                if stage == "LIFT" and self.model.geom(other).name == "source_plate":
                                    continue
                                raise MotionFailure(f"{stage} payload collision with {self.model.geom(other).name}")
                        samples += 1
                    q = next_q
                    path.append(q.tolist())
                waypoints.append({"name": stage, "q": q.tolist(), "path_q": path,
                                  "tcp_position": destination[:3, 3].tolist(),
                                  "tcp_rotation": destination[:3, :3].tolist(), "ik": error,
                                  "collision_check": {"samples": samples, "cartesian_segments": segments}})
                start_p, start_r = destination[:3, 3], destination[:3, :3]
        finally:
            self.initial_qpos[:] = original
        return {"source": "ground_truth_control_baseline" if self.ground_truth else "vision_pose_file",
                "route": "six_dof_keyed_nest", "pose_mode": self.pose_mode,
                "world_T_source_estimated": self.estimate.tolist(), "world_T_source_used": source.tolist(),
                "tool_T_object": tool_T_object.tolist(), "world_T_target": target.tolist(),
                "release_gap_m": RELEASE_GAP, "nest_clearance_m": self.nest.clearance,
                "waypoints": waypoints}

    def evaluate_placement(self, plan):
        outcome = insertion_outcome(self.model, self.data, self.nest)
        forces, _ = self.finger_contacts()
        result = {"success": outcome["success"] and max(forces.values()) < .05,
                  "control_source": plan["source"], "pose_mode": self.pose_mode,
                  "placement_evaluation_only": outcome,
                  "final_finger_normal_forces_n": forces,
                  "bilateral_loaded_contact_fraction": self.loaded_bilateral_steps / max(1, self.holding_steps),
                  "max_joint_tracking_error_rad": self.max_tracking_error,
                  "max_unexpected_robot_penetration_m": self.max_robot_penetration,
                  "stages": self.stage_metrics, "simulation_time_s": float(self.data.time)}
        if not result["success"]:
            raise MotionFailure(f"Keyed-nest seating failed: {result}")
        return result
