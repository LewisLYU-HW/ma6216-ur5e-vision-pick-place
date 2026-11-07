"""Vision-guided tool service: clear, intercept, insert, regrasp, and hang."""

import argparse
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.advanced_scene import WRIST_CAMERA
from ma6216.motion import MotionFailure
from ma6216.online_pose import PoseWorker
from ma6216.pose_insertion import transform
from ma6216.scene import CAMERA_NAME, mujoco
from ma6216.task_control import TaskRobot
from ma6216.evaluation import pose_errors, camera_metrics, timing_metrics, state_fingerprint
from ma6216.experiments import METHODS, control_pose, GraspImpulse
from ma6216.workshop_control import FeedPoseHistory, ReconstructedTool, WorkshopRecorder
from ma6216.workshop_perception import WorkshopObserver, refine_depth_pose
from ma6216.workshop_scene import (
    build_workshop_scene,
    workshop_supports,
    CRADLE,
    PARK,
    HOOK_CENTRE,
    HOOK_RADIUS,
    SOCKET_POSE,
    SOCKET_DEPTH,
    SOCKET_INNER,
    SPANNER_HANG_ROTATION,
    WORKSHOP_T_MARKER,
    ASSEMBLY_T_MARKER,
    RACK_T_FRAME,
    FRAME_CLEARANCE,
    rack_assembly_supports,
)


def evaluation_pose(model, data, body):
    """Used solely by diagnostics and outcome reports, never visual targets."""
    bid = model.body(body).id
    return transform(data.xpos[bid].copy(), data.xmat[bid].reshape(3, 3).copy())


def physical_evaluation(scene, name, *, assembled_frame=False):
    # Import simulator geometry only inside the explicitly isolated evaluator.
    from ma6216.workshop_assets import TOOLS, RACK_FRAME, FRAME_HOOK

    m, d = scene.model, scene.data
    tool = TOOLS[name]
    actual = evaluation_pose(m, d, tool.body)
    rack = evaluation_pose(m, d, "target_tray")
    relative = np.linalg.inv(rack) @ actual
    hook_centre = HOOK_CENTRE
    if assembled_frame and name == "spanner":
        relative = np.linalg.inv(evaluation_pose(m, d, RACK_FRAME.body)) @ actual
        hook_centre = FRAME_HOOK
    ids = {m.geom(n).id for n in tool.collision_names}
    normal_force = 0.0
    gripper_contact = False
    contacts = []
    for i, c in enumerate(d.contact):
        pair = {int(c.geom1), int(c.geom2)}
        if not ids.intersection(pair):
            continue
        other = next(iter(pair - ids), None)
        if other is None:
            continue
        geom = m.geom(other).name
        if geom.startswith("gripper_"):
            gripper_contact = True
        hook_contact = (
            geom in RACK_FRAME.collision_names[3:] if assembled_frame else geom.startswith("rack_hook")
        )
        if (name == "spanner" and hook_contact) or (
            name == "screwdriver" and geom.startswith("driver_socket_")
        ):
            wrench = np.zeros(6)
            mujoco.mj_contactForce(m, d, i, wrench)
            normal_force += max(0.0, float(wrench[0]))
            contacts.append(geom)
    dof = m.jnt_dofadr[m.joint(tool.joint).id]
    linear = float(np.linalg.norm(d.qvel[dof : dof + 3]))
    angular = float(np.linalg.norm(d.qvel[dof + 3 : dof + 6]))
    result = {
        "support_force_n": normal_force,
        "support_contacts": sorted(set(contacts)),
        "gripper_contact_after_release": gripper_contact,
        "linear_speed_m_s": linear,
        "angular_speed_rad_s": angular,
        "world_T_object": actual.tolist(),
    }
    if name == "spanner":
        eye = (relative @ np.array([-0.060, 0.0, 0.0, 1.0]))[:3]
        offset = eye - hook_centre
        plane_angle = float(np.rad2deg(np.arccos(np.clip(abs(relative[1, 2]), 0.0, 1.0))))
        result.update(eye_offset_from_hook_mm=(offset * 1000).tolist(), eye_plane_error_deg=plane_angle)
        geometric = (
            -0.006 < offset[1] < 0.060
            and -0.014 < offset[2] < 0.002
            and abs(offset[0]) < 0.012
            and plane_angle < 20.0
        )
    else:
        v = tool.vertices
        shaft = v[v[:, 0] < v[:, 0].min() + 0.38 * np.ptp(v[:, 0])]
        centre = shaft.mean(axis=0)
        _, _, vt = np.linalg.svd(shaft - centre, full_matrices=False)
        axis = vt[0] if vt[0, 0] > 0 else -vt[0]
        tip = centre + axis * np.percentile((shaft - centre) @ axis, 0.5)
        socket_T_tool = np.linalg.inv(SOCKET_POSE) @ relative
        point = (socket_T_tool @ np.r_[tip, 1.0])[:3]
        angle = float(np.rad2deg(np.arccos(np.clip((socket_T_tool[:3, :3] @ axis)[2], -1.0, 1.0))))
        result.update(
            tip_in_socket_mm=(point * 1000).tolist(),
            shaft_axis_error_deg=angle,
            insertion_depth_mm=float(-point[2] * 1000),
        )
        geometric = np.linalg.norm(point[:2]) < SOCKET_INNER and -0.039 < point[2] < -0.022 and angle < 12.0
    result["success"] = bool(
        geometric and normal_force > 0.2 and not gripper_contact and linear < 0.005 and angular < 0.08
    )
    return result


def frame_seating_evaluation(scene):
    from ma6216.workshop_assets import RACK_FRAME, FRAME_PROFILE, FRAME_DEPTH

    m, d = scene.model, scene.data
    actual = evaluation_pose(m, d, RACK_FRAME.body)
    expected = evaluation_pose(m, d, "target_tray") @ RACK_T_FRAME
    relative = np.linalg.inv(expected) @ actual
    stem = RACK_FRAME.geometry[1][0].vertices @ relative[:3, :3].T + relative[:3, 3]
    margins = []
    for i, a in enumerate(FRAME_PROFILE):
        edge = FRAME_PROFILE[(i + 1) % len(FRAME_PROFILE)] - a
        normal = np.array([edge[1], -edge[0]]) / np.linalg.norm(edge)
        margins.extend(normal @ a + FRAME_CLEARANCE - stem[:, :2] @ normal)
    force, gripper = 0.0, False
    ids = {m.geom(n).id for n in RACK_FRAME.collision_names}
    for i, c in enumerate(d.contact):
        pair = {int(c.geom1), int(c.geom2)}
        if not ids.intersection(pair):
            continue
        for other in pair - ids:
            name = m.geom(other).name
            gripper |= name.startswith("gripper_")
            if name.startswith("frame_socket_"):
                wrench = np.zeros(6)
                mujoco.mj_contactForce(m, d, i, wrench)
                force += max(0.0, float(wrench[0]))
    adr = m.jnt_dofadr[m.joint(RACK_FRAME.joint).id]
    linear = float(np.linalg.norm(d.qvel[adr : adr + 3]))
    angular = float(np.linalg.norm(d.qvel[adr + 3 : adr + 6]))
    result = pose_errors(actual, expected)
    result.update(
        bottom_gap_mm=float((stem[:, 2].min() + FRAME_DEPTH) * 1000),
        minimum_wall_clearance_mm=float(min(margins) * 1000),
        support_force_n=force,
        gripper_contact_after_release=gripper,
        linear_speed_m_s=linear,
        angular_speed_rad_s=angular,
    )
    result["success"] = bool(
        result["translation_error_mm"] < 4.0
        and result["rotation_error_deg"] < 8.0
        and abs(result["bottom_gap_mm"]) < 2.0
        and min(margins) > -0.0007
        and force > 0.2
        and not gripper
        and linear < 0.005
        and angular < 0.08
    )
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", choices=("all", "insert", "hang", "rack"), default="all")
    p.add_argument("--method", choices=METHODS, default="full")
    p.add_argument("--disturbance", choices=("none", "grasp_impulse"), default="none")
    p.add_argument("--models", type=Path, default=ROOT / "assets/reconstructed/workshop")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--ground-truth", action="store_true", help="Physics diagnostic; never a vision result")
    p.add_argument("--record", action="store_true")
    p.add_argument("--trace", action="store_true", help="Save original 25 Hz states for exact failure replay")
    p.add_argument(
        "--sensor-delay",
        type=float,
        default=None,
        help="Fixed simulated moving-camera latency for paired benchmarks; default uses wall-clock waits",
    )
    p.add_argument("--stationary-feed", action="store_true")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--foundationpose-python", type=Path, default=Path(sys.executable))
    p.add_argument("--foundationpose-repository", type=Path, default=ROOT / "third_party/FoundationPose")
    p.add_argument("--calibration", type=Path, default=ROOT / "demo_data/calibration/estimated")
    args = p.parse_args()
    if args.sensor_delay is not None and args.sensor_delay < 0:
        p.error("sensor-delay must be nonnegative")
    if args.method == "no_recovery" or (
        args.method == "no_prediction" and args.task not in ("insert", "all")
    ):
        p.error("This ablation is not applicable to the selected workshop task")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    robot = observer = worker = recorder = None
    report = {
        "success": False,
        "task": args.task,
        "seed": args.seed,
        "method": args.method,
        "disturbance": args.disturbance,
        "fixed_virtual_sensor_delay_s": args.sensor_delay,
        "perception": [],
        "rack_observations": [],
        "outcomes": {},
        "control_source": (
            "ground_truth_diagnostic"
            if args.ground_truth
            else "FoundationPose official reference reconstruction"
        ),
        "model_free": not args.ground_truth,
        "simulation_segmentation_ids_used": False,
        "segmentation": "RGB-D pickup regions; held-object ROI from visual estimate plus FK",
        "reference_protocol": "calibrated RGB-D scan; object CAD excluded from pose estimation and payload planning; surveyed station geometry",
        "command": " ".join(sys.argv),
    }
    try:
        assembling = args.task == "rack"
        objects = {
            name: ReconstructedTool(args.models / name)
            for name in (("rack_frame", "spanner") if assembling else ("hammer", "screwdriver", "spanner"))
        }
        report["reconstructed_features"] = {k: v.features for k, v in objects.items()}
        scene = build_workshop_scene(args.seed, rack_assembly=assembling)
        planning = build_workshop_scene(args.seed, planning_parts=objects.values(), rack_assembly=assembling)
        m, d = scene.model, scene.data
        for _ in range(1000):
            mujoco.mj_step(m, d)
        report["initial_scene_state_sha256"] = state_fingerprint(d)
        recorder = WorkshopRecorder(
            m,
            out / "video",
            args.record,
            source="GROUND TRUTH DIAGNOSTIC" if args.ground_truth else "REFERENCE RGB-D / FOUNDATIONPOSE",
        )
        # Commissioning observation of the empty station. Its actual depth
        # image (not segmentation IDs or CAD silhouettes) is the background.
        empty = build_workshop_scene(args.seed, empty=True, rack_assembly=assembling)
        with mujoco.Renderer(empty.model, height=960, width=1280) as renderer:
            renderer.update_scene(empty.data, camera=CAMERA_NAME)
            renderer.enable_depth_rendering()
            background = renderer.render().copy()
        np.save(out / "empty_station_depth.npy", background)
        observer = WorkshopObserver(
            m,
            out / "observations",
            args.calibration,
            background_depth=background,
            fixture_T_marker=ASSEMBLY_T_MARKER if assembling else WORKSHOP_T_MARKER,
        )
        report["calibration_evaluation_only"] = camera_metrics(m, d, observer, args.calibration)
        robot = TaskRobot(
            scene,
            objects,
            recorder,
            out / "motion",
            planning_scene=planning,
            initial_target="rack_frame" if assembling else "hammer",
            supports=(
                (
                    lambda stage: rack_assembly_supports(
                        stage,
                        [
                            objects["rack_frame"].geom + (f"_{i}" if i else "")
                            for i in range(len(objects["rack_frame"].pieces))
                        ],
                    )
                )
                if assembling
                else workshop_supports
            ),
        )
        if args.disturbance == "grasp_impulse":
            target = "rack_frame" if assembling else "spanner" if args.task == "hang" else "screwdriver"
            robot.environment_hook = GraspImpulse(robot, target)
        robot.trace_enabled = args.trace
        robot.joint_velocity_feedforward = assembling

        def displayed_estimate():
            name = robot.target.object_id
            pose = robot.tcp_pose() @ robot.tool_T_object if robot.carrying else robot.known.get(name)
            return None if pose is None else (name, pose)

        recorder.pose_provider = displayed_estimate
        if not args.ground_truth:
            worker = PoseWorker(
                args.foundationpose_python, args.foundationpose_repository, out / "pose_worker"
            )
            for obj in objects.values():
                worker.wait(worker.submit(model_bundle=obj.bundle))

        def observe(
            name, camera=CAMERA_NAME, *, region=None, track=False, prior=None, moving=False, register=False
        ):
            if assembling and name == "spanner" and region is None and prior is None:
                region = "rack_spanner"
            cap = observer.capture(
                d, camera=camera, object_id=name, region=region, prior=prior, vertices=objects[name].vertices
            )
            truth = evaluation_pose(m, d, objects[name].body)
            if args.ground_truth:
                pose = truth.copy()
                info = {"operation": "ground_truth_diagnostic"}
            else:
                request = worker.submit(
                    model_bundle=objects[name].bundle,
                    sequence=name + "_" + camera,
                    frame=cap["frame"],
                    K=cap["K"],
                    world_T_camera=cap["world_T_camera"],
                    capture_time_s=cap["capture_time_s"],
                    register=register or (not track and prior is None),
                    world_T_object_prior=prior,
                )
                info = worker.wait(
                    request,
                    on_wait=(
                        (lambda: robot.tick(stage="TRACK_FEED", realtime=True))
                        if moving and args.sensor_delay is None
                        else None
                    ),
                )
                if moving and args.sensor_delay is not None:
                    robot.hold(args.sensor_delay, "TRACK_FEED")
                    info["fixed_virtual_sensor_delay_s"] = args.sensor_delay
                pose = np.asarray(info["world_T_object"])
            raw_pose = pose.copy()
            if (
                not args.ground_truth
                and name == "rack_frame"
                and (camera == WRIST_CAMERA or prior is not None)
            ):
                pose, info["depth_refinement"] = refine_depth_pose(cap, objects[name].mesh, pose)
            if not args.ground_truth and name == "rack_frame" and camera == CAMERA_NAME and prior is not None:
                # Co-observe the installed part and marker. Express their
                # relative pose in the most recent wrist-localized fixture
                # frame, cancelling their shared fixed-camera extrinsic error.
                try:
                    same_view_fixture, anchor = observer.fixture_pose(cap)
                    pose = robot.fixture_estimate @ np.linalg.inv(same_view_fixture) @ pose
                    info["fixture_relative_anchor"] = anchor
                except RuntimeError as exc:
                    info["fixture_relative_anchor_unavailable"] = str(exc)
            pose = control_pose(pose, args.method)
            info["control_world_T_object"] = pose.tolist()
            info["capture_truth_evaluation_only"] = truth.tolist()
            info["raw_estimator_metrics_evaluation_only"] = pose_errors(
                raw_pose, truth, objects[name].vertices
            )
            info["control_pose_metrics_evaluation_only"] = pose_errors(pose, truth, objects[name].vertices)
            info.update(
                object_id=name,
                camera=camera,
                foreground_pixels=cap["metadata"]["foreground_pixels"],
                capture_time_s=cap["capture_time_s"],
                segmentation=cap["metadata"]["segmentation"],
                translation_error_mm_evaluation_only=float(np.linalg.norm(pose[:3, 3] - truth[:3, 3]) * 1000),
                rotation_error_deg_evaluation_only=float(
                    np.rad2deg(Rotation.from_matrix(pose[:3, :3] @ truth[:3, :3].T).magnitude())
                ),
            )
            report["perception"].append(info)
            robot.known[name] = pose.copy()
            robot.event("object_localized", object_id=name, camera=camera, pixels=info["foreground_pixels"])
            return pose, cap["capture_time_s"]

        def locate_rack(camera=CAMERA_NAME):
            if args.ground_truth:
                pose = evaluation_pose(m, d, "target_tray")
                info = {"method": "ground_truth_diagnostic"}
            else:
                cap = observer.capture(d, camera=camera)
                try:
                    pose, info = observer.fixture_pose(cap)
                except RuntimeError:
                    if camera != WRIST_CAMERA:
                        raise
                    K, extrinsic, _ = observer.camera_calibration(d, camera)
                    point = (np.linalg.inv(extrinsic) @ robot.fixture_estimate @ observer.fixture_T_marker)[
                        :3, 3
                    ]
                    initial = robot.tcp_pose()
                    found = False
                    for pixel in ([300.0, 210.0], [980.0, 210.0], [300.0, 380.0], [980.0, 380.0]):
                        ray = np.linalg.inv(K) @ np.r_[pixel, 1.0]
                        A = extrinsic[:3, :3].T[:, :2]
                        delta = np.linalg.solve(A[:2] - ray[:2, None] * A[2], point[:2] - ray[:2] * point[2])
                        survey = initial.copy()
                        survey[:2, 3] += delta
                        try:
                            robot.plan_move(survey, "SURVEY_RACK")
                            robot.move(survey, "SURVEY_RACK")
                            cap = observer.capture(d, camera=camera)
                            pose, info = observer.fixture_pose(cap)
                            found = True
                            break
                        except (MotionFailure, RuntimeError) as exc:
                            robot.event("rack_view_rejected", reason=str(exc)[:180])
                    if not found:
                        raise RuntimeError("No safe wrist view could localize the tool rack")
            robot.fixture_estimate = pose.copy()
            info["camera"] = camera
            truth = evaluation_pose(m, d, "target_tray")
            info["translation_error_mm_evaluation_only"] = float(
                np.linalg.norm(pose[:3, 3] - truth[:3, 3]) * 1000
            )
            info["rotation_error_deg_evaluation_only"] = pose_errors(pose, truth)["rotation_error_deg"]
            report["rack_observations"].append(info)
            robot.event("rack_localized", camera=camera)
            return pose

        locate_rack()
        for name in objects:
            observe(name)
        robot.hold(0.6, "INSPECT_WORKBENCH")

        def held_refinement():
            if args.method == "no_wrist":
                robot.event("wrist_refinement_disabled", object_id=robot.target.object_id)
                return
            robot.hold(0.3, "WRIST_INSPECT_TOOL")
            prior = robot.tcp_pose() @ robot.tool_T_object
            pose, _ = observe(robot.target.object_id, WRIST_CAMERA, prior=prior)
            robot.tool_T_object = np.linalg.inv(robot.tcp_pose()) @ pose
            locate_rack(WRIST_CAMERA)

        if assembling:
            robot.select("rack_frame")
            robot.grasp(robot.known["rack_frame"])
            held_refinement()
            tool = objects["rack_frame"]
            goal = robot.fixture_estimate @ RACK_T_FRAME
            # Seating offset uses the observed bottom of the reconstructed tenon.
            goal[:3, 3] += goal[:3, 2] * (-0.036 - tool.bounds[0, 2] + 0.0015)
            tcp = goal @ np.linalg.inv(robot.tool_T_object)
            axis = goal[:3, 2]
            high = tcp.copy()
            high[:3, 3] += axis * 0.12
            robot.move(high, "ORIENT_RACK_FRAME", joint_space=True)
            if args.method != "no_wrist":
                prior = robot.tcp_pose() @ robot.tool_T_object
                held, _ = observe("rack_frame", WRIST_CAMERA, prior=prior)
                robot.tool_T_object = np.linalg.inv(robot.tcp_pose()) @ held
                tcp = goal @ np.linalg.inv(robot.tool_T_object)
            pre = tcp.copy()
            pre[:3, 3] += axis * 0.06
            robot.move(pre, "ALIGN_RACK_FRAME")
            robot.hold(0.3, "TARE_FRAME_INSERTION")
            bias = robot.wrench()
            for distance in np.linspace(0.06, 0.0, 31)[1:]:
                step = tcp.copy()
                step[:3, 3] += axis * distance
                if not robot.move(step, "INSERT_FRAME", allow_support=True, force_bias=bias, force_limit=7.0):
                    retreat = robot.tcp_pose()
                    retreat[:3, 3] += axis * 0.05
                    robot.move(retreat, "RETRACT_FRAME", allow_support=True)
                    raise MotionFailure("Rack frame insertion contact guard triggered")
            robot.release(retreat_distance=0.085)
            robot.known["rack_frame"] = goal
            robot.obstacle_clearances["rack_frame"] = 0.004
            clear = transform([0.43, -0.04, 0.64], np.diag([-1.0, 1.0, -1.0]))
            robot.move(clear, "CLEAR_ASSEMBLED_FRAME", joint_space=True)
            robot.hold(2.0, "CHECK_FRAME_SEATING")
            result = frame_seating_evaluation(scene)
            report["outcomes"]["rack_frame"] = result
            if not result["success"]:
                raise MotionFailure(f"Rack frame seating failed: {result}")
            # Locate the free assembled support after release, rather than
            # assuming its actual position equals the commanded seat pose.
            observe("rack_frame", prior=goal)
            robot.obstacle_clearances["rack_frame"] = 0.004

        if args.task in ("all", "insert"):
            robot.select("hammer")
            robot.grasp(robot.known["hammer"])
            pose = robot.known["hammer"].copy()
            pose[:3, :3] = Rotation.from_euler("z", 145.0, degrees=True).as_matrix()
            zmin = (objects["hammer"].vertices @ pose[:3, :3].T)[:, 2].min()
            pose[:3, 3] = PARK + [0.0, 0.0, -zmin + 0.003]
            target = pose @ np.linalg.inv(robot.tool_T_object)
            hover = target.copy()
            hover[2, 3] = 0.535
            robot.move(hover, "CLEAR_TOOL_ACCESS")
            robot.move(target, "PARK_HAMMER", allow_support=True)
            robot.release(retreat_distance=0.07)
            robot.known["hammer"] = pose
            report["hammer_cleared"] = True

            robot.select("screwdriver")
            if args.stationary_feed:
                pose, _ = observe("screwdriver")
            else:
                d.ctrl[m.actuator("belt_drive").id] = scene.belt_speed
                robot.hold(0.4, "START_FEED", realtime=True)
                history = FeedPoseHistory()
                for i in range(3):
                    observed, stamp = observe("screwdriver", track=i > 0, moving=True)
                    history.add(stamp, observed)
                    if i < 2:
                        robot.hold(0.35, "TRACK_FEED", realtime=True)
                horizon = 5.0
                for _ in range(3):
                    pose = (
                        history.samples[-1][1].copy()
                        if args.method == "no_prediction"
                        else history.predict(float(d.time) + horizon)
                    )
                    robot.known["screwdriver"] = pose
                    approach = pose @ objects["screwdriver"].acquisition_grasp(pose)
                    approach[:3, 3] -= approach[:3, 2] * 0.10
                    _, duration = robot.plan_move(approach, "PLAN_INTERCEPT")
                    horizon = duration + 0.25 + 2.0 + 0.25 + 0.35
                pose = (
                    history.samples[-1][1].copy()
                    if args.method == "no_prediction"
                    else history.predict(float(d.time) + horizon)
                )
                report["feed"] = {
                    "visual_velocity_m_s": history.velocity.tolist(),
                    "unconstrained_visual_velocity_m_s": history.unconstrained_velocity.tolist(),
                    "motion_constraint": "surveyed feed rail axis; speed estimated only from vision",
                    "prediction_horizon_s": horizon,
                    "commanded_speed_m_s": scene.belt_speed,
                    "physics_steps_during_inference": not args.ground_truth,
                }
            robot.grasp(pose)
            report.setdefault("feed", {})["belt_command_at_pickup_m_s"] = float(
                d.ctrl[m.actuator("belt_drive").id]
            )
            d.ctrl[m.actuator("belt_drive").id] = 0.0
            held_refinement()
            tool = objects["screwdriver"]
            socket = robot.fixture_estimate @ SOCKET_POSE
            rotation = (
                socket[:3, :3] @ Rotation.from_euler("y", -90, degrees=True).as_matrix() @ tool.shaft_basis.T
            )
            tip = (socket @ np.array([0.0, 0.0, -SOCKET_DEPTH + 0.003, 1.0]))[:3]
            object_goal = transform(tip - rotation @ tool.tip, rotation)
            tcp = object_goal @ np.linalg.inv(robot.tool_T_object)
            axis = socket[:3, 2]
            pre = tcp.copy()
            pre[:3, 3] += axis * (SOCKET_DEPTH + 0.020)
            high = pre.copy()
            high[2, 3] = max(0.60, pre[2, 3] + 0.035)
            robot.move(high, "ORIENT_DRIVER")
            robot.hold(0.4, "SETTLE_ORIENTED_DRIVER")
            prior = robot.tcp_pose() @ robot.tool_T_object
            if args.method != "no_wrist":
                held, _ = observe("screwdriver", WRIST_CAMERA, prior=prior)
                robot.tool_T_object = np.linalg.inv(robot.tcp_pose()) @ held
            tcp = object_goal @ np.linalg.inv(robot.tool_T_object)
            pre = tcp.copy()
            pre[:3, 3] += axis * (SOCKET_DEPTH + 0.020)
            robot.move(pre, "ALIGN_DRIVER")
            robot.hold(0.3, "TARE_INSERTION_FORCE")
            bias = robot.wrench()
            inserted = True
            for distance in np.linspace(SOCKET_DEPTH + 0.020, 0.0, 29)[1:]:
                step = tcp.copy()
                step[:3, 3] += axis * distance
                if not robot.move(
                    step, "INSERT_DRIVER", allow_support=True, force_bias=bias, force_limit=7.0
                ):
                    inserted = False
                    break
            if not inserted:
                retreat = robot.tcp_pose()
                retreat[:3, 3] += axis * 0.04
                robot.move(retreat, "RETRACT_DRIVER", allow_support=True)
                raise MotionFailure("Driver insertion contact guard stopped the task")
            robot.release()
            robot.known["screwdriver"] = object_goal
            robot.hold(2.0, "CHECK_DRIVER_STABILITY")
            result = physical_evaluation(scene, "screwdriver")
            report["outcomes"]["screwdriver"] = result
            if not result["success"]:
                raise MotionFailure(f"Driver seating failed: {result}")

        if args.task in ("all", "hang", "rack"):
            robot.select("spanner")
            pose, _ = observe("spanner")
            acquisition = objects["spanner"].acquisition_grasp(pose)
            if assembling:
                # Use the other antipodal grasp through both pickups so that
                # the wrist orientation stays compatible with the seated frame.
                acquisition[:3, :3] = acquisition[:3, :3] @ np.diag([-1.0, -1.0, 1.0])
                approach = pose @ acquisition
                approach[:3, 3] -= approach[:3, 2] * 0.10
                robot.move(approach, "ROUTE_TO_SPANNER", joint_space=True)
            robot.grasp(pose, acquisition)
            # Put the tool on two physical rails, open, withdraw, reobserve,
            # and grasp a different part of the handle. No attachment weld.
            flat = transform(CRADLE + [0.0, 0.0, -objects["spanner"].bounds[0, 2] + 0.0015])
            target = flat @ np.linalg.inv(robot.tool_T_object)
            high = target.copy()
            high[2, 3] = 0.57
            robot.move(high, "TRANSFER_TO_REGRASP", joint_space=assembling)
            robot.move(target, "PLACE_REGRASP", allow_support=True)
            robot.release()
            robot.known["spanner"] = flat
            pose, _ = observe("spanner", region="cradle")
            regrasp = objects["spanner"].top_grasp(regrasp=True)
            if assembling:
                regrasp[:3, :3] = regrasp[:3, :3] @ np.diag([-1.0, -1.0, 1.0])
            robot.grasp(pose, regrasp)
            report["physical_regrasp_executed"] = True
            held_refinement()
            tool = objects["spanner"]
            mount = robot.known["rack_frame"] if assembling else robot.fixture_estimate
            hook = objects["rack_frame"].hook if assembling else HOOK_CENTRE
            rotation = mount[:3, :3] @ SPANNER_HANG_ROTATION

            def eye_goal(y, z):
                hole = (mount @ np.r_[hook + [0.0, y, z], 1.0])[:3]
                return transform(hole - rotation @ tool.eye, rotation)

            standoff, thread_depth = (0.060, 0.015) if assembling else (0.035, 0.025)
            approach_object = eye_goal(-standoff, 0.0)
            approach = approach_object @ np.linalg.inv(robot.tool_T_object)
            robot.move(approach, "REORIENT_AND_APPROACH_RACK", joint_space=True)
            robot.hold(0.3, "TARE_HANG_FORCE")
            bias = robot.wrench()
            for y in np.linspace(-standoff, thread_depth, 25)[1:]:
                goal = eye_goal(y, 0.0) @ np.linalg.inv(robot.tool_T_object)
                if not robot.move(goal, "THREAD_EYE", allow_support=True, force_bias=bias, force_limit=7.0):
                    raise MotionFailure("Hanging eye contact guard triggered")
            # Position the eye just above the peg's support surface. Gravity
            # finishes seating after release, with contact checked below.
            drop = max(0.0, tool.eye_radius - HOOK_RADIUS - 0.0015)
            final_object = eye_goal(thread_depth, -drop)
            robot.move(final_object @ np.linalg.inv(robot.tool_T_object), "SEAT_EYE", allow_support=True)
            robot.release(retreat_distance=0.10)
            robot.known["spanner"] = final_object
            robot.hold(4.0, "CHECK_HANG_STABILITY")
            result = physical_evaluation(scene, "spanner", assembled_frame=assembling)
            report["outcomes"]["spanner"] = result
            if not result["success"]:
                raise MotionFailure(f"Hanging failed: {result}")
            if assembling:
                report["outcomes"]["rack_frame_loaded"] = frame_seating_evaluation(scene)
                if not report["outcomes"]["rack_frame_loaded"]["success"]:
                    raise MotionFailure("Assembled frame did not remain stable under the hanging tool load")

        robot.hold(1.0, "TOOLS_READY")
        report["success"] = all(v["success"] for v in report["outcomes"].values())
        report["simulation_seconds"] = float(d.time)
    except KeyboardInterrupt:
        report.update(error="KeyboardInterrupt: run interrupted before verification", interrupted=True)
    except Exception as exc:
        report.update(error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        traceback.print_exc()
        if observer is not None:
            for camera in (CAMERA_NAME, WRIST_CAMERA):
                try:
                    observer.capture(d, camera=camera)
                except Exception:
                    pass
    finally:
        if robot is not None:
            if args.task == "rack":
                report["terminal_outcomes_evaluation_only"] = {
                    "rack_frame": frame_seating_evaluation(scene),
                    "spanner": physical_evaluation(scene, "spanner", assembled_frame=True),
                }
            else:
                names = (
                    ("screwdriver", "spanner")
                    if args.task == "all"
                    else (("screwdriver",) if args.task == "insert" else ("spanner",))
                )
                report["terminal_outcomes_evaluation_only"] = {
                    name: physical_evaluation(scene, name) for name in names
                }
            report["execution"] = robot.save()
            report["timing"] = timing_metrics(report, robot, started)
            report["last_stage"] = robot.stage
            report["simulation_seconds"] = float(d.time)
            np.savez(
                out / "final_state_evaluation_only.npz",
                qpos=d.qpos,
                qvel=d.qvel,
                ctrl=d.ctrl,
                mocap_pos=d.mocap_pos,
                mocap_quat=d.mocap_quat,
                time=d.time,
            )
        if worker is not None:
            worker.close()
        if observer is not None:
            observer.close()
        if recorder is not None:
            report["video_frames"] = recorder.frames
            recorder.close()
        report["wall_seconds"] = time.perf_counter() - started
        (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps({k: report.get(k) for k in ("success", "task", "error", "wall_seconds")}), flush=True
        )
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
