"""Actuator-only manipulation with reconstructed planning geometry and force guards."""
from __future__ import annotations

import json
import math
from pathlib import Path
import time

import cv2
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
import trimesh

from .advanced_scene import build_task_scene, WRIST_CAMERA
from .motion import Robot, MotionFailure
from .parts import Part
from .pose_insertion import transform
from .reconstructed import validate_bundle
from .scene import matrix_to_quat, mujoco


def expected_supports(stage):
    if stage in ("LIFT", "LIFT_SETTLE"):
        return {"source_plate", "worktable", "belt_surface", "cradle_rail_-1", "cradle_rail_1"}
    if stage in ("PLACE_OBSTRUCTION", "PLACE_OBSTRUCTION_SETTLE"):
        return {"obstruction_drop_pad"}
    if stage in ("PLACE_IN_REGRASP_CRADLE", "PLACE_IN_REGRASP_CRADLE_SETTLE"):
        return {"cradle_rail_-1", "cradle_rail_1"}
    if stage.startswith("INSERT_") or stage.startswith("RETRACT_AFTER_CONTACT"):
        return {"tray_bottom", *(f"socket_wall_{i}" for i in range(5))}
    return set()


class ObservedObject:
    def __init__(self, bundle):
        self.bundle = Path(bundle).resolve()
        manifest, mesh_file = validate_bundle(self.bundle)
        self.object_id = manifest["object_id"]
        self.mesh = trimesh.load(str(mesh_file), force="mesh", process=False)
        self.vertices = np.asarray(self.mesh.convex_hull.vertices)
        self.bounds = self.mesh.bounds.copy()
        if self.object_id == "plug":
            self.key, self.body, self.geom, self.joint = "green", "target_cube", "target_cube_geom", "target_cube_freejoint"
            self.rgba, self.hsv = (.12, .80, .34, 1.), ((46, 75, 38), (95, 255, 255))
        elif self.object_id == "blocker":
            self.key, self.body, self.geom, self.joint = "orange", "target_orange", "target_orange_geom", "target_orange_freejoint"
            self.rgba, self.hsv = (.95, .43, .06, 1.), ((5, 100, 50), (29, 255, 255))
        else:
            raise ValueError("Unknown reconstructed task object")

    def planning_part(self):
        return Part(self.key, "RGB-D reconstructed " + self.object_id,
                    tuple(map(tuple, self.vertices * 1000)), self.rgba, *self.hsv,
                    self.body, (.40, -.18), (.48, .17))

    def top_grasp(self):
        position = self.bounds.mean(axis=0)
        position[2] = self.bounds[1, 2] - (.015 if self.object_id == "plug" else .017)
        return transform(position, np.diag([1., -1., -1.]))

    def side_grasp(self):
        # When local +Y is upwards, approach that face and close across local Z.
        position = self.bounds.mean(axis=0)
        position[1] += .003
        rotation = np.column_stack(([1., 0., 0.], [0., 0., 1.], [0., -1., 0.]))
        return transform(position, rotation)

    def upper_face_grasp(self, pose):
        """Choose the upward reconstructed face of a symmetric obstruction.

        A plain box's visually equivalent 180-degree rotations must not turn a
        top approach into an approach through the table. Keep the estimated
        object frame, and express the grasp on whichever face points upward.
        """
        axis = int(np.argmax(np.abs(pose[2, :3])))
        sign = 1. if pose[2, axis] > 0 else -1.
        closing = min((i for i in range(3) if i != axis), key=lambda i: np.ptp(self.bounds[:, i]))
        position = self.bounds.mean(axis=0)
        position[axis] = self.bounds[int(sign > 0), axis] - sign * .017
        z = -sign * np.eye(3)[axis]
        y = np.eye(3)[closing]
        if (pose[:3, :3] @ y)[1] > 0:
            y = -y
        x = np.cross(y, z)
        return transform(position, np.column_stack([x, y, z]))


class TaskRecorder:
    def __init__(self, model, output, task, enabled=True, source="Model-free FoundationPose"):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.renderer = mujoco.Renderer(model, height=480, width=640) if enabled else None
        self.writers = {}
        self.task, self.source = task, source
        self.next_frame = 0.
        self.frames = 0
        self.last_stage = None
        if enabled:
            for name, width in (("overview_wrist", 1280), ("wrist", 640), ("overview", 640)):
                writer = cv2.VideoWriter(str(self.output / f"{name}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 25., (width, 480))
                self.writers[name] = writer
                if not writer.isOpened():
                    self.close()
                    raise RuntimeError("Task video encoder failed")

    def capture(self, data, stage, details=""):
        if self.renderer is None or data.time + 1e-8 < self.next_frame:
            return
        views = []
        for name, camera in (("overview", "overview"), ("wrist", WRIST_CAMERA)):
            self.renderer.update_scene(data, camera=camera)
            self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
            self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
            frame = cv2.cvtColor(self.renderer.render(), cv2.COLOR_RGB2BGR)
            cv2.rectangle(frame, (0, 0), (640, 86), (25, 25, 25), -1)
            for i, text in enumerate((f"{self.task.upper()} | {stage} | t={data.time:.1f}s",
                                      self.source, f"{name.title()} view | {details}")):
                cv2.putText(frame, text, (10, 23 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX, .48,
                            (240, 240, 240), 1, cv2.LINE_AA)
            self.writers[name].write(frame)
            views.append(frame)
        combined = np.concatenate(views, axis=1)
        self.writers["overview_wrist"].write(combined)
        if stage != self.last_stage:
            cv2.imwrite(str(self.output / f"{self.frames:05d}_{stage.lower()}.png"), combined)
            self.last_stage = stage
        self.frames += 1
        self.next_frame = float(data.time) + .04 - 1e-8

    def close(self):
        for writer in self.writers.values():
            writer.release()
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None


class TaskRobot:
    def __init__(self, scene, objects, recorder, output):
        self.scene, self.model, self.data = scene, scene.model, scene.data
        self.objects, self.recorder = objects, recorder
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        parts = tuple(obj.planning_part() for obj in objects.values())
        self.planning_scene = build_task_scene(scene.task, scene.seed, planning_parts=parts)
        self.known = {}
        self.fixture_estimate = None
        self.target = None
        self.robot = None
        self.planner = None
        self.carrying = False
        self.tool_T_object = None
        self.events = []
        self.samples = []
        self.ticks = 0
        self.moves = 0
        self.environment_hook = None
        self.stage = "INITIALIZE"
        self.peak_force = 0.
        self.loaded_steps = 0
        self.holding_steps = 0
        self.select("plug")

    def select(self, object_id):
        if self.carrying:
            raise MotionFailure("Cannot change target while carrying")
        self.target = self.objects[object_id]
        kw = dict(target_vertices=self.target.vertices, target_body=self.target.body,
                  target_geom=self.target.geom, target_joint=self.target.joint)
        self.robot = Robot(self.model, self.data, **kw)
        self.planner = Robot(self.planning_scene.model, self.planning_scene.data, **kw)

    def tcp_pose(self):
        return transform(self.data.site_xpos[self.robot.sid].copy(), self.data.site_xmat[self.robot.sid].reshape(3, 3).copy())

    def wrench(self):
        return np.r_[self.data.sensor("wrist_force").data, self.data.sensor("wrist_torque").data].copy()

    def event(self, name, **values):
        entry = {"event": name, "simulation_time_s": float(self.data.time), **values}
        self.events.append(entry)
        print(json.dumps(entry), flush=True)
        (self.output / "events.json").write_text(json.dumps(self.events, indent=2) + "\n")

    def tick(self, q=None, stage=None, *, realtime=False, allow_target=True):
        started = time.perf_counter()
        if q is not None:
            self.data.ctrl[self.robot.aids] = q
        if stage is not None:
            self.stage = stage
        if self.environment_hook is not None:
            self.environment_hook(self.stage)
        mujoco.mj_step(self.model, self.data)
        self.ticks += 1
        bad = self.robot.collision_contacts(self.data, allow_cube=allow_target)
        if bad:
            raise MotionFailure(f"Unexpected robot contact at {self.stage}: {bad}")
        error = float(np.max(np.abs(self.data.qpos[self.robot.qids] - self.data.ctrl[self.robot.aids])))
        if error > .30 or not np.isfinite(self.data.qpos).all():
            raise MotionFailure(f"Joint execution failure at {self.stage}: {error}")
        if self.carrying:
            forces, opposition = self.robot.finger_contacts()
            self.holding_steps += 1
            loaded = min(forces.values()) > .1 and opposition is not None and opposition < -.8
            self.loaded_steps += int(loaded)
            if not loaded:
                raise MotionFailure(f"Lost physical bilateral grasp at {self.stage}: {forces}")
            # The simulated contact safety monitor also checks the payload,
            # independently of the reconstructed planning geometry.
            for contact in self.data.contact:
                pair = (int(contact.geom1), int(contact.geom2))
                if self.robot.cgid not in pair or contact.dist >= -.0005:
                    continue
                other = pair[1] if pair[0] == self.robot.cgid else pair[0]
                if other in self.robot.pad_sides or self.model.geom(other).name in expected_supports(self.stage):
                    continue
                raise MotionFailure(f"Unexpected physical payload contact at {self.stage}: {self.model.geom(other).name}")
        if self.ticks % 10 == 0:
            wrench = self.wrench()
            self.peak_force = max(self.peak_force, float(np.linalg.norm(wrench[:3])))
            self.samples.append({"time_s": float(self.data.time), "stage": self.stage,
                                 "tcp_pose": self.tcp_pose().tolist(), "wrist_wrench": wrench.tolist(),
                                 "gripper_command": float(self.data.ctrl[self.robot.gid])})
            self.recorder.capture(self.data, self.stage, f"wrist force {np.linalg.norm(wrench[:3]):.1f} N")
        if realtime:
            time.sleep(max(0., self.model.opt.timestep - (time.perf_counter() - started)))

    def hold(self, seconds, stage=None, realtime=False):
        for _ in range(round(seconds / self.model.opt.timestep)):
            self.tick(stage=stage, realtime=realtime)

    def prepare_planner(self):
        pm = self.planning_scene.model
        # Proprioception supplies robot/belt coordinates; every free object's
        # coordinates are overwritten by visual estimates before FK/collision.
        self.planner.initial_qpos[:] = self.data.qpos
        for key, obj in self.objects.items():
            if key not in self.known:
                raise MotionFailure(f"Object {key} has not been visually localized")
            adr = pm.jnt_qposadr[pm.joint(obj.joint).id]
            pose = self.known[key]
            self.planner.initial_qpos[adr:adr + 3] = pose[:3, 3]
            self.planner.initial_qpos[adr + 3:adr + 7] = matrix_to_quat(pose[:3, :3])
        if self.fixture_estimate is None:
            raise MotionFailure("Fixture has not been visually localized")
        mid = pm.body_mocapid[pm.body("target_tray").id]
        self.planner.scratch.mocap_pos[mid] = self.fixture_estimate[:3, 3]
        self.planner.scratch.mocap_quat[mid] = matrix_to_quat(self.fixture_estimate[:3, :3])
        self.planner.scratch.qpos[:] = self.planner.initial_qpos

    def plan_move(self, destination, stage, *, allow_support=False):
        self.prepare_planner()
        planner = self.planner
        q = self.data.ctrl[self.robot.aids].copy()
        start_p, start_r = planner.fk(q)
        distance = np.linalg.norm(destination[:3, 3] - start_p)
        angle = Rotation.from_matrix(destination[:3, :3] @ start_r.T).magnitude()
        count = max(1, math.ceil(distance / .012), math.ceil(angle / .06))
        slerp = Slerp([0., 1.], Rotation.from_matrix([start_r, destination[:3, :3]]))
        path = [q.copy()]
        for i in range(1, count + 1):
            fraction = i / count
            tcp = transform((1 - fraction) * start_p + fraction * destination[:3, 3], slerp(fraction).as_matrix())
            if self.carrying:
                pose = tcp @ self.tool_T_object
                adr = planner.cube_qposadr
                planner.initial_qpos[adr:adr + 3] = pose[:3, 3]
                planner.initial_qpos[adr + 3:adr + 7] = matrix_to_quat(pose[:3, :3])
            q_next, _ = planner.solve(tcp[:3, 3], tcp[:3, :3], q)
            if np.max(np.abs(q_next - q)) > .30:
                raise MotionFailure(f"IK branch change at {stage}")
            # Sample the actual joint interpolation, including its payload.
            for u in np.linspace(0., 1., max(2, math.ceil(np.max(np.abs(q_next - q)) / .025) + 1)):
                planner.scratch.qpos[:] = planner.initial_qpos
                position, rotation = planner.fk(q + u * (q_next - q))
                if self.carrying:
                    pose = transform(position, rotation) @ self.tool_T_object
                    adr = planner.cube_qposadr
                    planner.scratch.qpos[adr:adr + 3] = pose[:3, 3]
                    planner.scratch.qpos[adr + 3:adr + 7] = matrix_to_quat(pose[:3, :3])
                    mujoco.mj_forward(planner.model, planner.scratch)
                bad = planner.collision_contacts(allow_cube=True)
                if bad:
                    raise MotionFailure(f"Offline robot collision at {stage}: {bad}")
                if self.carrying:
                    for contact in planner.scratch.contact:
                        pair = (int(contact.geom1), int(contact.geom2))
                        if planner.cgid not in pair or contact.dist >= -.001:
                            continue
                        other = pair[1] if pair[0] == planner.cgid else pair[0]
                        if other in planner.pad_sides:
                            continue
                        name = planner.model.geom(other).name
                        expected = expected_supports(stage) if allow_support else set()
                        if name not in expected:
                            raise MotionFailure(f"Offline payload collision at {stage}: {name}, penetration {-contact.dist * 1000:.3f} mm")
            path.append(q_next.copy())
            q = q_next
        path = np.asarray(path)
        minimum_duration = .15 if distance < .01 and angle < .04 else 1.2
        duration = max(minimum_duration, float(np.max(np.abs(np.diff(path, axis=0)))) * (len(path) - 1) / .35)
        return path, duration

    def move(self, destination, stage, *, min_duration=0., allow_support=False, force_bias=None, force_limit=None):
        path, duration = self.plan_move(destination, stage, allow_support=allow_support)
        duration = max(duration, min_duration)
        self.moves += 1
        (self.output / f"move_{self.moves:03d}_{stage}.json").write_text(json.dumps(
            {"stage": stage, "target_tcp": destination.tolist(), "path_q": path.tolist(), "duration_s": duration}, indent=2) + "\n")
        steps = max(1, round(duration / self.model.opt.timestep))
        for step in range(steps + 1):
            u = step / steps
            progress = (10 * u**3 - 15 * u**4 + 6 * u**5) * (len(path) - 1)
            index = min(int(progress), len(path) - 2)
            q = path[index] + (progress - index) * (path[index + 1] - path[index])
            self.tick(q, stage)
            if force_limit is not None and np.linalg.norm(self.wrench()[:3] - force_bias[:3]) > force_limit:
                if self.carrying:
                    self.known[self.target.object_id] = self.tcp_pose() @ self.tool_T_object
                self.event("force_guard_triggered", stage=stage, force_delta_n=float(np.linalg.norm(self.wrench()[:3] - force_bias[:3])))
                return False
        self.hold(.25, stage + "_SETTLE")
        if self.carrying:
            self.known[self.target.object_id] = self.tcp_pose() @ self.tool_T_object
        return True

    def grasp(self, pose, object_T_tcp=None):
        self.known[self.target.object_id] = pose.copy()
        if object_T_tcp is None:
            object_T_tcp = (self.target.upper_face_grasp(pose) if self.target.object_id == "blocker"
                            else self.target.top_grasp())
        grasp = pose @ object_T_tcp
        approach = grasp.copy()
        approach[:3, 3] -= grasp[:3, 2] * .10
        self.move(approach, "PICK_APPROACH")
        self.move(grasp, "GRASP", min_duration=2.)
        self.data.ctrl[self.robot.gid] = 255.
        self.hold(1.5, "CLOSE_GRIPPER")
        force, opposition = self.robot.finger_contacts()
        if min(force.values()) < .1 or opposition is None or opposition > -.8:
            raise MotionFailure(f"No bilateral grasp: {force}")
        self.tool_T_object = np.linalg.inv(grasp) @ pose
        self.carrying = True
        self.event("physical_grasp", object_id=self.target.object_id, forces_n=force)
        lift = grasp.copy()
        lift_distance = min(.135, max(.08, (.585 - grasp[2, 3]) / max(.5, -grasp[2, 2])))
        lift[:3, 3] -= grasp[:3, 2] * lift_distance
        self.move(lift, "LIFT", allow_support=True)

    def release(self, *, retreat_distance=.12, lower_open_hand=0.):
        self.carrying = False
        self.data.ctrl[self.robot.gid] = 0.
        self.hold(1.2, "RELEASE")
        self.event("released", object_id=self.target.object_id)
        if lower_open_hand:
            # A horizontal hand can still support the object on its lower pad.
            # Let the cradle carry it, then lower that pad before withdrawing.
            clear = self.tcp_pose()
            clear[2, 3] -= lower_open_hand
            self.move(clear, "CLEAR_LOWER_FINGER", allow_support=True)
        retreat = self.tcp_pose()
        retreat[:3, 3] -= retreat[:3, 2] * retreat_distance
        self.move(retreat, "RETREAT", allow_support=True)
        self.hold(.5, "SETTLE")

    def save(self):
        (self.output / "samples.json").write_text(json.dumps(self.samples) + "\n")
        return {"loaded_bilateral_fraction": self.loaded_steps / max(1, self.holding_steps),
                "peak_wrist_force_n": self.peak_force, "events": self.events,
                "controller_uses_live_object_qpos_writes": False,
                "planning_object_geometry": "convex hulls of RGB-D neural reconstructions"}
