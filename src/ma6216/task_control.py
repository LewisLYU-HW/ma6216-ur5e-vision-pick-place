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
from .evaluation import pose_errors, distribution


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
    def __init__(self, scene, objects, recorder, output, *, planning_scene=None,
                 initial_target="plug", supports=expected_supports):
        self.scene, self.model, self.data = scene, scene.model, scene.data
        self.objects, self.recorder = objects, recorder
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        parts = tuple(obj.planning_part() for obj in objects.values())
        self.planning_scene = (planning_scene if planning_scene is not None else
                               build_task_scene(scene.task, scene.seed, planning_parts=parts))
        self.supports = supports
        self.known = {}
        self.fixture_estimate = None
        self.target = None
        self.robot = None
        self.planner = None
        self.carrying = False
        self.tool_T_object = None
        self.events = []
        self.samples = []
        self.endpoints = []
        self.tracking_data = mujoco.MjData(self.model)
        self.trace = []
        self.trace_enabled = False
        self.next_trace_time = float(self.data.time)
        self.wall_started = time.perf_counter()
        self.ticks = 0
        self.moves = 0
        self.environment_hook = None
        self.obstacle_clearances = {}
        self.stage = "INITIALIZE"
        self.peak_force = 0.
        self.loaded_steps = 0
        self.holding_steps = 0
        self.select(initial_target)

    def select(self, object_id):
        if self.carrying:
            raise MotionFailure("Cannot change target while carrying")
        self.target = self.objects[object_id]
        kw = dict(target_vertices=self.target.vertices, target_body=self.target.body,
                  target_geom=self.target.geom, target_joint=self.target.joint)
        physical_names = [self.model.geom(i).name for i in range(self.model.ngeom)
                          if self.model.geom_bodyid[i] == self.model.body(self.target.body).id
                          and (self.model.geom_contype[i] or self.model.geom_conaffinity[i])]
        planning_names = [self.planning_scene.model.geom(i).name for i in range(self.planning_scene.model.ngeom)
                          if self.planning_scene.model.geom_bodyid[i] == self.planning_scene.model.body(self.target.body).id
                          and (self.planning_scene.model.geom_contype[i] or self.planning_scene.model.geom_conaffinity[i])]
        self.robot = Robot(self.model, self.data, target_geoms=physical_names, **kw)
        self.planner = Robot(self.planning_scene.model, self.planning_scene.data, target_geoms=planning_names, **kw)

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
        # Evaluation-only trajectory snapshots allow failure videos to replay
        # the original measured run without re-running stochastic perception.
        if self.trace_enabled and self.data.time + 1e-8 >= self.next_trace_time:
            self.capture_trace()
            self.next_trace_time += .04
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
                if not self.robot.cgids.intersection(pair) or contact.dist >= -.0005:
                    continue
                other = pair[1] if pair[0] in self.robot.cgids else pair[0]
                if other in self.robot.cgids or other in self.robot.pad_sides or self.model.geom(other).name in self.supports(self.stage):
                    continue
                raise MotionFailure(f"Unexpected physical payload contact at {self.stage}: {self.model.geom(other).name}")
        if self.ticks % 10 == 0:
            wrench = self.wrench()
            self.peak_force = max(self.peak_force, float(np.linalg.norm(wrench[:3])))
            self.tracking_data.qpos[:] = self.data.qpos
            mujoco.mj_kinematics(self.model, self.tracking_data)
            measured = transform(self.tracking_data.site_xpos[self.robot.sid].copy(),
                                 self.tracking_data.site_xmat[self.robot.sid].reshape(3, 3).copy())
            self.tracking_data.qpos[self.robot.qids] = self.data.ctrl[self.robot.aids]
            mujoco.mj_kinematics(self.model, self.tracking_data)
            command = transform(self.tracking_data.site_xpos[self.robot.sid].copy(),
                                self.tracking_data.site_xmat[self.robot.sid].reshape(3, 3).copy())
            metrics = pose_errors(measured, command)
            joint_errors = self.data.qpos[self.robot.qids] - self.data.ctrl[self.robot.aids]
            self.samples.append({"time_s": float(self.data.time), "stage": self.stage,
                                 "wall_time_s": time.perf_counter()-self.wall_started,
                                 "tcp_pose": measured.tolist(), "wrist_wrench": wrench.tolist(),
                                 "tracking_translation_mm": metrics["translation_error_mm"],
                                 "tracking_rotation_deg": metrics["rotation_error_deg"],
                                 "joint_tracking_rmse_rad": float(np.sqrt(np.mean(joint_errors**2))),
                                 "joint_tracking_max_rad": float(np.max(np.abs(joint_errors))),
                                 "gripper_command": float(self.data.ctrl[self.robot.gid])})
            self.recorder.capture(self.data, self.stage, f"wrist force {np.linalg.norm(wrench[:3]):.1f} N")
        if realtime:
            time.sleep(max(0., self.model.opt.timestep - (time.perf_counter() - started)))

    def hold(self, seconds, stage=None, realtime=False):
        for _ in range(round(seconds / self.model.opt.timestep)):
            self.tick(stage=stage, realtime=realtime)

    def capture_trace(self):
        pose = self.tcp_pose() @ self.tool_T_object if self.carrying else self.known.get(self.target.object_id)
        self.trace.append((float(self.data.time), self.stage, self.data.qpos.copy(), self.data.qvel.copy(),
                           self.data.ctrl.copy(), self.data.mocap_pos.copy(), self.data.mocap_quat.copy(),
                           self.target.object_id, np.full((4, 4), np.nan) if pose is None else pose.copy()))

    def prepare_planner(self, clearance_scale=1.):
        pm = self.planning_scene.model
        if pm.opt.disableflags & (int(mujoco.mjtDisableBit.mjDSBL_CONSTRAINT) | int(mujoco.mjtDisableBit.mjDSBL_CONTACT)):
            raise MotionFailure("Collision planning requires contact and constraint stages to remain enabled")
        # Proprioception supplies robot/belt coordinates; every free object's
        # coordinates are overwritten by visual estimates before FK/collision.
        self.planner.initial_qpos[:] = self.data.qpos
        self.planner.obstacle_clearances = {}
        for key, obj in self.objects.items():
            if key not in self.known:
                raise MotionFailure(f"Object {key} has not been visually localized")
            adr = pm.jnt_qposadr[pm.joint(obj.joint).id]
            pose = self.known[key]
            self.planner.initial_qpos[adr:adr + 3] = pose[:3, 3]
            self.planner.initial_qpos[adr + 3:adr + 7] = matrix_to_quat(pose[:3, :3])
            if key in self.obstacle_clearances:
                clearance = self.obstacle_clearances[key] * clearance_scale
                body = pm.body(obj.body).id
                for geom in range(pm.ngeom):
                    if pm.geom_bodyid[geom] == body and (pm.geom_contype[geom] or pm.geom_conaffinity[geom]):
                        pm.geom_margin[geom] = clearance
                        pm.geom_gap[geom] = clearance
                        self.planner.obstacle_clearances[geom] = clearance
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
                        if not planner.cgids.intersection(pair):
                            continue
                        other = pair[1] if pair[0] in planner.cgids else pair[0]
                        clearance = planner.obstacle_clearances.get(other, -.001)
                        if contact.dist >= clearance:
                            continue
                        if other in planner.cgids or other in planner.pad_sides:
                            continue
                        name = planner.model.geom(other).name
                        expected = self.supports(stage) if allow_support else set()
                        if name not in expected:
                            raise MotionFailure(f"Offline payload collision at {stage}: {name}, penetration {-contact.dist * 1000:.3f} mm")
            path.append(q_next.copy())
            q = q_next
        path = np.asarray(path)
        minimum_duration = .15 if distance < .01 and angle < .04 else 1.2
        duration = max(minimum_duration, float(np.max(np.abs(np.diff(path, axis=0)))) * (len(path) - 1) / .35)
        return path, duration

    def plan_joint_move(self, destination, stage, *, max_iterations=1200):
        """Collision-checked RRT-Connect for large free-space reorientations.

        Cartesian approach/insertion still uses plan_move. This planner uses
        only the private estimated scene and reconstructed payload geometry.
        """
        self.prepare_planner(clearance_scale=5.)
        planner = self.planner
        start = self.data.ctrl[self.robot.aids].copy()
        if self.carrying:
            pose = destination @ self.tool_T_object
            adr = planner.cube_qposadr
            planner.initial_qpos[adr : adr + 3] = pose[:3, 3]
            planner.initial_qpos[adr + 3 : adr + 7] = matrix_to_quat(pose[:3, :3])
        goal, _ = planner.solve(destination[:3, 3], destination[:3, :3], start, multistart=True)
        forearm = [
            i
            for i in range(planner.model.ngeom)
            if planner.model.body(int(planner.model.geom_bodyid[i])).name == "forearm_link"
            and (planner.model.geom_contype[i] or planner.model.geom_conaffinity[i])
        ]
        gripper = [
            i
            for i in range(planner.model.ngeom)
            if planner.model.body(int(planner.model.geom_bodyid[i])).name.startswith("gripper_")
            and (planner.model.geom_contype[i] or planner.model.geom_conaffinity[i])
        ]
        checked = 0

        def valid(q):
            nonlocal checked
            checked += 1
            planner.scratch.qpos[:] = planner.initial_qpos
            p, r = planner.fk(q)
            if self.carrying:
                pose = transform(p, r) @ self.tool_T_object
                adr = planner.cube_qposadr
                planner.scratch.qpos[adr : adr + 3] = pose[:3, 3]
                planner.scratch.qpos[adr + 3 : adr + 7] = matrix_to_quat(pose[:3, :3])
                mujoco.mj_forward(planner.model, planner.scratch)
            if planner.collision_contacts(allow_cube=True, penetration=0.0):
                return False
            # Leave clearance for actuator tracking error during wrist turns.
            for a in forearm:
                for b in gripper:
                    if mujoco.mj_geomDistance(planner.model, planner.scratch, a, b, 0.003, None) < 0.003:
                        return False
            if self.carrying:
                for c in planner.scratch.contact:
                    pair = (int(c.geom1), int(c.geom2))
                    if not planner.cgids.intersection(pair):
                        continue
                    other = pair[1] if pair[0] in planner.cgids else pair[0]
                    if c.dist >= planner.obstacle_clearances.get(other, -0.0005):
                        continue
                    if other not in planner.cgids and other not in planner.pad_sides:
                        return False
            return True

        def edge(a, b):
            n = max(1, math.ceil(np.max(np.abs(b - a)) / 0.025))
            return all(valid(a + (b - a) * u) for u in np.linspace(0.0, 1.0, n + 1))

        if not valid(start) or not valid(goal):
            raise MotionFailure(f"Joint planner start/goal lacks clearance at {stage}")
        route = None
        if edge(start, goal):
            route = [start, goal]
        direct_route = route is not None
        rng = np.random.default_rng(617 + self.moves)
        low = np.maximum(planner.low, np.minimum(start, goal) - 1.3)
        high = np.minimum(planner.high, np.maximum(start, goal) + 1.3)
        nodes = [[start], [goal]]
        parents = [[-1], [-1]]

        def extend(which, target):
            tree = nodes[which]
            nearest = int(np.argmin([np.linalg.norm(q - target) for q in tree]))
            delta = target - tree[nearest]
            length = np.max(np.abs(delta))
            proposal = target.copy() if length <= 0.18 else tree[nearest] + delta * (0.18 / length)
            if not edge(tree[nearest], proposal):
                return None, False
            tree.append(proposal)
            parents[which].append(nearest)
            return len(tree) - 1, length <= 0.18

        def trace(which, index):
            result = []
            while index >= 0:
                result.append(nodes[which][index])
                index = parents[which][index]
            return result[::-1]

        for iteration in range(max_iterations if route is None else 0):
            a = iteration % 2
            b = 1 - a
            target = nodes[b][-1] if rng.random() < 0.25 else rng.uniform(low, high)
            index, _ = extend(a, target)
            if index is None:
                continue
            point = nodes[a][index]
            for _ in range(80):
                other, reached = extend(b, point)
                if other is None:
                    break
                if reached:
                    first, second = trace(a, index), trace(b, other)
                    route = first + second[-2::-1] if a == 0 else second + first[-2::-1]
                    break
            if route is not None:
                break
        if route is None:
            raise MotionFailure(f"No collision-free joint route at {stage} after {checked} checks")
        for _ in range(60):
            if len(route) < 3:
                break
            i, j = sorted(rng.choice(len(route), 2, replace=False))
            if j > i + 1 and edge(route[i], route[j]):
                route = route[: i + 1] + route[j:]
        dense = [route[0]]
        for a, b in zip(route[:-1], route[1:]):
            n = max(1, math.ceil(np.max(np.abs(b - a)) / 0.025))
            dense.extend(a + (b - a) * u for u in np.linspace(0.0, 1.0, n + 1)[1:])
        path = np.asarray(dense)
        duration = max(1.2, float(np.sum(np.max(np.abs(np.diff(path, axis=0)), axis=1))) / 0.22)
        self.event(
            "joint_route_planned",
            stage=stage,
            collision_checks=checked,
            waypoints=len(path),
            method="joint interpolation" if direct_route else "RRT-Connect",
            reconstructed_payload=True,
            self_clearance_mm=3.0,
            obstacle_clearance_mm={key: value * 5000 for key, value in self.obstacle_clearances.items()},
        )
        return path, duration

    def move(
        self,
        destination,
        stage,
        *,
        min_duration=0.0,
        allow_support=False,
        force_bias=None,
        force_limit=None,
        joint_space=False,
    ):
        path, duration = (
            self.plan_joint_move(destination, stage)
            if joint_space
            else self.plan_move(destination, stage, allow_support=allow_support)
        )
        duration = max(duration, min_duration)
        self.moves += 1
        (self.output / f"move_{self.moves:03d}_{stage}.json").write_text(
            json.dumps(
                {
                    "stage": stage,
                    "target_tcp": destination.tolist(),
                    "path_q": path.tolist(),
                    "duration_s": duration,
                    "joint_space": joint_space,
                },
                indent=2,
            )
            + "\n"
        )
        steps = max(1, round(duration / self.model.opt.timestep))
        retimed_steps = 0
        for step in range(steps + 1):
            u = step / steps
            progress = (10 * u**3 - 15 * u**4 + 6 * u**5) * (len(path) - 1)
            index = min(int(progress), len(path) - 2)
            q = path[index] + (progress - index) * (path[index + 1] - path[index])
            self.tick(q, stage)
            if joint_space and self.obstacle_clearances:
                # Slow progress along the already checked path when actuator
                # tracking lags. Only joint encoders and the current command
                # are used; no payload truth is available to this controller.
                for _ in range(1000):
                    if np.max(np.abs(self.data.qpos[self.robot.qids]-q)) <= .010:
                        break
                    self.tick(stage=stage)
                    retimed_steps += 1
                else:
                    raise MotionFailure(f"Joint tracking failed to settle at {stage}")
            if force_limit is not None and np.linalg.norm(self.wrench()[:3] - force_bias[:3]) > force_limit:
                if self.carrying:
                    self.known[self.target.object_id] = self.tcp_pose() @ self.tool_T_object
                self.event(
                    "force_guard_triggered",
                    stage=stage,
                    force_delta_n=float(np.linalg.norm(self.wrench()[:3] - force_bias[:3])),
                )
                return False
        self.hold(0.25, stage + "_SETTLE")
        if retimed_steps:
            self.event("joint_path_retimed", stage=stage, extra_steps=retimed_steps, joint_error_limit_rad=.010)
        self.endpoints.append({"stage": stage, "time_s": float(self.data.time),
                               **pose_errors(self.tcp_pose(), destination)})
        if self.carrying:
            self.known[self.target.object_id] = self.tcp_pose() @ self.tool_T_object
        return True

    def grasp(self, pose, object_T_tcp=None):
        self.known[self.target.object_id] = pose.copy()
        if object_T_tcp is None:
            if hasattr(self.target, "acquisition_grasp"):
                object_T_tcp = self.target.acquisition_grasp(pose)
            else:
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
            raise MotionFailure(f"No bilateral grasp: {force}; opposing normal dot={opposition}")
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
        if self.trace_enabled:
            self.capture_trace()
            keys = ("time", "stage", "qpos", "qvel", "ctrl", "mocap_pos", "mocap_quat", "object_id", "estimated_pose")
            np.savez_compressed(self.output / "trajectory_evaluation_only.npz",
                                **{key: np.asarray(values) for key, values in zip(keys, zip(*self.trace))})
        (self.output / "samples.json").write_text(json.dumps(self.samples) + "\n")
        (self.output / "endpoints.json").write_text(json.dumps(self.endpoints, indent=2) + "\n")
        return {"loaded_bilateral_fraction": self.loaded_steps / max(1, self.holding_steps),
                "tcp_tracking_translation_mm": distribution([s["tracking_translation_mm"] for s in self.samples]),
                "tcp_tracking_rotation_deg": distribution([s["tracking_rotation_deg"] for s in self.samples]),
                "joint_tracking_rmse_rad": distribution([s["joint_tracking_rmse_rad"] for s in self.samples]),
                "joint_tracking_max_rad": distribution([s["joint_tracking_max_rad"] for s in self.samples]),
                "move_endpoint_translation_mm": distribution([s["translation_error_mm"] for s in self.endpoints]),
                "move_endpoint_rotation_deg": distribution([s["rotation_error_deg"] for s in self.endpoints]),
                "tracking_reference": "commanded-joint FK versus measured TCP; task outcome evaluated separately",
                "peak_wrist_force_n": self.peak_force, "events": self.events,
                "controller_uses_live_object_qpos_writes": False,
                "planning_object_geometry": "convex hulls of RGB-D neural reconstructions"}
