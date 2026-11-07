"""Run assembly recovery, occlusion/regrasp, or moving-conveyor manipulation."""
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
from ma6216.advanced_scene import (build_task_scene, SOCKET_DEPTH, SOCKET_CLEARANCE, WRIST_CAMERA,
                                 CRADLE_POSITION, OBSTRUCTION_DROP_POSITION, FIXTURE_T_MARKER)
from ma6216.online_pose import PoseHistory, PoseWorker
from ma6216.motion import MotionFailure
from ma6216.pose_insertion import expanded_footprint, transform
from ma6216.scene import CAMERA_NAME, mujoco
from ma6216.simulation_objects import PLUG
from ma6216.task_control import ObservedObject, TaskRecorder, TaskRobot
from ma6216.task_perception import ImageObserver
from ma6216.evaluation import pose_errors, camera_metrics, timing_metrics, state_fingerprint
from ma6216.experiments import METHODS, control_pose, GraspImpulse


def evaluation_pose(model, data, body):
    """Explicit truth baseline or downstream evaluation; not visual targets."""
    bid = model.body(body).id
    return transform(data.xpos[bid].copy(), data.xmat[bid].reshape(3, 3).copy())


def seating_evaluation(scene):
    model, data = scene.model, scene.data
    fixture = evaluation_pose(model, data, "target_tray")
    actual = evaluation_pose(model, data, PLUG.body)
    expected = fixture @ transform([0., 0., PLUG.half_height])
    relative = np.linalg.inv(fixture) @ actual
    vertices = PLUG.vertices @ relative[:3, :3].T + relative[:3, 3]
    _, normals, offsets = expanded_footprint(SOCKET_CLEARANCE)
    margin = float(np.min(offsets[:, None] - normals @ vertices[:, :2].T))
    position = float(np.linalg.norm(actual[:3, 3] - expected[:3, 3]))
    rotation = float(np.rad2deg(Rotation.from_matrix(expected[:3, :3].T @ actual[:3, :3]).magnitude()))
    bottom = float(vertices[:, 2].min())
    dof = model.jnt_dofadr[model.joint(PLUG.joint).id]
    linear = float(np.linalg.norm(data.qvel[dof:dof + 3]))
    angular = float(np.linalg.norm(data.qvel[dof + 3:dof + 6]))
    force = 0.
    gid = model.geom(PLUG.geom).id
    floor = model.geom("tray_bottom").id
    for i, c in enumerate(data.contact):
        if {int(c.geom1), int(c.geom2)} == {gid, floor}:
            wrench = np.zeros(6)
            mujoco.mj_contactForce(model, data, i, wrench)
            force += max(0., wrench[0])
    return {"success": bool(position < .004 and rotation < 5. and margin > -.0005 and abs(bottom) < .0015
                             and force > .2 and linear < .005 and angular < .05),
            "position_error_mm": position * 1000, "rotation_error_deg": rotation,
            "bottom_gap_mm": bottom * 1000, "minimum_wall_clearance_mm": margin * 1000,
            "insertion_depth_mm": (SOCKET_DEPTH - bottom) * 1000,
            "support_force_n": float(force), "linear_speed_m_s": linear, "angular_speed_rad_s": angular}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=("assembly", "clutter", "conveyor"), required=True)
    parser.add_argument("--plug-model", required=True, type=Path)
    parser.add_argument("--blocker-model", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--ground-truth", action="store_true", help="Diagnostic control baseline, not a vision result")
    parser.add_argument("--foundationpose-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--foundationpose-repository", type=Path, default=ROOT / "third_party/FoundationPose")
    parser.add_argument("--calibration", type=Path, default=ROOT / "demo_data/calibration/estimated")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--sensor-delay", type=float, default=None)
    parser.add_argument("--method", choices=METHODS, default="full")
    parser.add_argument("--disturbance", choices=("default", "none", "fixture_shift", "grasp_impulse"), default="default")
    parser.add_argument("--no-disturbance", action="store_true")
    parser.add_argument("--disable-recovery", action="store_true", help="Explicit failure-recovery ablation")
    parser.add_argument("--belt-speed", type=float, default=.004)
    args = parser.parse_args()
    if args.sensor_delay is not None and args.sensor_delay < 0:
        parser.error("sensor-delay must be nonnegative")
    if args.disable_recovery:
        args.method = "no_recovery"
    args.disable_recovery = args.method == "no_recovery"
    if args.disturbance == "default":
        args.disturbance = "fixture_shift" if args.task == "assembly" and not args.no_disturbance else "none"
    if args.disturbance == "fixture_shift" and args.task != "assembly":
        parser.error("fixture_shift is defined only for the assembly task")
    if args.task == "clutter" and not args.blocker_model:
        parser.error("Clutter task requires --blocker-model")
    if not .001 <= args.belt_speed <= .010:
        parser.error("Belt speed must be in 1..10 mm/s")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    worker = observer = recorder = robot = None
    summary = {"success": False, "task": args.task, "seed": args.seed,
               "method": args.method, "disturbance": args.disturbance,
               "fixed_virtual_sensor_delay_s": args.sensor_delay,
               "control_source": "ground_truth_diagnostic" if args.ground_truth else "FoundationPose official reconstructed-model inference",
               "model_free": not args.ground_truth, "reconstruction_input": "reference RGB-D, masks, calibrated scan poses; no CAD",
               "wrist_calibration": "ideal synthetic hand-eye mount and robot kinematics",
               "fixture_perception": "RGB-D ArUco marker plane and surveyed marker mounting",
               "recovery_enabled": not args.disable_recovery, "perception": [], "fixture_perception_samples": [],
               "assembly_attempts": [], "command": " ".join(sys.argv),
               "scope": "Synthetic calibrated references, deterministic workcells, ideal depth and wrist hand-eye calibration"}
    try:
        objects = {"plug": ObservedObject(args.plug_model)}
        if args.task == "clutter":
            objects["blocker"] = ObservedObject(args.blocker_model)
        scene = build_task_scene(args.task, args.seed, belt_speed=args.belt_speed)
        model, data = scene.model, scene.data
        for _ in range(775):
            mujoco.mj_step(model, data)
        summary["initial_scene_state_sha256"] = state_fingerprint(data)
        recorder = TaskRecorder(model, output / "video", args.task, args.record,
                                source="Ground-truth diagnostic" if args.ground_truth else "RGB-D references -> Neural Object Field -> FoundationPose")
        observer = ImageObserver(model, output / "observations", args.calibration)
        summary["calibration_evaluation_only"] = camera_metrics(model, data, observer, args.calibration)
        robot = TaskRobot(scene, objects, recorder, output / "motion")
        robot.trace_enabled = args.trace
        impulse = GraspImpulse(robot, "plug") if args.disturbance == "grasp_impulse" else None
        robot.environment_hook = impulse
        if not args.ground_truth:
            worker = PoseWorker(args.foundationpose_python, args.foundationpose_repository, output / "pose_worker")
            for obj in objects.values():
                worker.wait(worker.submit(model_bundle=obj.bundle))

        def observe_object(key, camera=CAMERA_NAME, *, track=False, prior=None):
            capture = observer.capture(data, camera=camera, object_id=key)
            # Captured truth is retained only for the separate error report.
            actual_at_capture = evaluation_pose(model, data, objects[key].body)
            if args.ground_truth:
                pose = actual_at_capture.copy()
                info = {"operation": "ground_truth_diagnostic", "capture_time_s": capture["capture_time_s"]}
            else:
                request = worker.submit(model_bundle=objects[key].bundle, sequence=key + "_" + camera,
                                        frame=capture["frame"], K=capture["K"], world_T_camera=capture["world_T_camera"],
                                        capture_time_s=capture["capture_time_s"], register=not track and prior is None,
                                        world_T_object_prior=prior)
                moving = args.task == "conveyor" and not robot.carrying
                on_wait = (lambda: robot.tick(stage="TRACK_MOVING_OBJECT", realtime=True)) if moving and args.sensor_delay is None else None
                info = worker.wait(request, on_wait=on_wait)
                if moving and args.sensor_delay is not None:
                    robot.hold(args.sensor_delay, "TRACK_MOVING_OBJECT")
                    info["fixed_virtual_sensor_delay_s"] = args.sensor_delay
                pose = np.asarray(info["world_T_object"])
            raw_pose = pose.copy()
            pose = control_pose(pose, args.method)
            info["control_world_T_object"] = pose.tolist()
            info["capture_truth_evaluation_only"] = actual_at_capture.tolist()
            info["raw_estimator_metrics_evaluation_only"] = pose_errors(raw_pose, actual_at_capture, objects[key].mesh.vertices)
            info["control_pose_metrics_evaluation_only"] = pose_errors(pose, actual_at_capture, objects[key].mesh.vertices)
            info.update(object_id=key, camera=camera, foreground_pixels=capture["metadata"]["foreground_pixels"],
                        translation_error_mm_evaluation_only=float(np.linalg.norm(pose[:3, 3] - actual_at_capture[:3, 3]) * 1000),
                        rotation_error_deg_evaluation_only=float(np.rad2deg(Rotation.from_matrix(pose[:3, :3] @ actual_at_capture[:3, :3].T).magnitude())))
            summary["perception"].append(info)
            robot.known[key] = pose.copy()
            robot.event("visual_pose" if not args.ground_truth else "diagnostic_pose", object_id=key, camera=camera,
                        capture_time_s=capture["capture_time_s"], foreground_pixels=capture["metadata"]["foreground_pixels"])
            return pose, capture["capture_time_s"]

        def observe_fixture(camera=CAMERA_NAME):
            if args.ground_truth:
                pose = evaluation_pose(model, data, "target_tray")
                info = {"method": "ground_truth_diagnostic"}
            else:
                capture = observer.capture(data, camera=camera)
                try:
                    pose, info = observer.fixture_pose(capture)
                except RuntimeError:
                    if camera != WRIST_CAMERA:
                        raise
                    # Survey the marker with the actual hand-mounted camera.
                    # Its coarse location comes from the previous image, never
                    # from the live mocap body or the disturbance parameters.
                    K, world_T_camera, _ = observer.camera_calibration(data, camera)
                    marker_world = (robot.fixture_estimate @ FIXTURE_T_MARKER)[:3, 3]
                    marker_camera = (np.linalg.inv(world_T_camera) @ np.r_[marker_world, 1.])[:3]
                    # Try both sides of the held object's silhouette. The IK
                    # and collision checks choose a reachable view; translation
                    # stays horizontal to preserve payload clearance.
                    camera_R_world_xy = world_T_camera[:3, :3].T[:, :2]
                    initial_tcp = robot.tcp_pose()
                    localized = False
                    for wanted in ([300., 210.], [980., 210.], [300., 380.], [980., 380.]):
                        ray = np.linalg.inv(K) @ np.r_[wanted, 1.]
                        system = camera_R_world_xy[:2] - ray[:2, None] * camera_R_world_xy[2]
                        delta_xy = np.linalg.solve(system, marker_camera[:2] - ray[:2] * marker_camera[2])
                        survey = initial_tcp.copy()
                        survey[:2, 3] += delta_xy
                        try:
                            robot.plan_move(survey, "WRIST_SURVEY_FIXTURE")
                        except MotionFailure as exc:
                            robot.event("wrist_view_rejected", pixel_target=wanted, reason=str(exc)[:200])
                            continue
                        robot.move(survey, "WRIST_SURVEY_FIXTURE")
                        capture = observer.capture(data, camera=camera)
                        try:
                            pose, info = observer.fixture_pose(capture)
                            localized = True
                            break
                        except RuntimeError:
                            continue
                    if not localized:
                        raise RuntimeError("No reachable wrist view exposed the complete fixture marker")
            robot.fixture_estimate = pose.copy()
            fixture_truth = evaluation_pose(model, data, "target_tray")
            info.update(camera=camera,
                        translation_error_mm_evaluation_only=float(np.linalg.norm(pose[:3, 3] - fixture_truth[:3, 3]) * 1000),
                        rotation_error_deg_evaluation_only=float(np.rad2deg(Rotation.from_matrix(pose[:3, :3] @ fixture_truth[:3, :3].T).magnitude())))
            summary["fixture_perception_samples"].append(info)
            robot.event("fixture_localized", camera=camera, method=info["method"])
            return pose

        observe_fixture()
        if args.task == "conveyor":
            data.ctrl[model.actuator("belt_drive").id] = args.belt_speed
            robot.hold(.5, "BELT_ACCELERATE", realtime=True)
            history = PoseHistory()
            for index in range(3):
                pose, stamp = observe_object("plug", track=index > 0)
                history.add(stamp, pose)
                if index < 2:
                    robot.hold(.4, "TRACK_MOVING_OBJECT", realtime=True)
            horizon = 5.
            for _ in range(3):
                predicted = (history.samples[-1][1].copy() if args.method == "no_prediction"
                             else history.predict(float(data.time) + horizon))
                robot.known["plug"] = predicted
                approach = predicted @ objects["plug"].top_grasp()
                approach[:3, 3] -= approach[:3, 2] * .10
                _, duration = robot.plan_move(approach, "PREDICT_INTERCEPT")
                horizon = duration + .25 + 2. + .25 + .35
            predicted = (history.samples[-1][1].copy() if args.method == "no_prediction"
                         else history.predict(float(data.time) + horizon))
            summary["conveyor"] = {"visual_velocity_m_s": history.velocity.tolist(), "prediction_horizon_s": horizon,
                                   "last_visual_capture_time_s": history.samples[-1][0],
                                   "predicted_contact_time_s": float(data.time) + horizon,
                                   "commanded_belt_speed_m_s": args.belt_speed,
                                   "physics_continues_during_inference": not args.ground_truth and args.sensor_delay is None,
                                   "fixed_virtual_sensor_delay_s": args.sensor_delay}
            robot.event("intercept_planned", **summary["conveyor"])
            robot.grasp(predicted)
            # The belt remains in motion through contact, closure, and lift.
            summary["conveyor"]["belt_command_at_pickup_m_s"] = float(data.ctrl[model.actuator("belt_drive").id])
            data.ctrl[model.actuator("belt_drive").id] = 0.
        else:
            plug_pose, _ = observe_object("plug")
            if args.task == "clutter":
                blocked_pixels = summary["perception"][-1]["foreground_pixels"]
                blocker_pose, _ = observe_object("blocker")
                robot.select("blocker")
                robot.grasp(blocker_pose)
                blocker_min_z = (objects["blocker"].vertices @ blocker_pose[:3, :3].T)[:, 2].min()
                drop = transform(OBSTRUCTION_DROP_POSITION + [0., 0., -blocker_min_z + .010], blocker_pose[:3, :3])
                tcp = drop @ np.linalg.inv(robot.tool_T_object)
                high = tcp.copy(); high[2, 3] = .56
                robot.move(high, "CLEAR_OBSTRUCTION")
                robot.move(tcp, "PLACE_OBSTRUCTION", allow_support=True)
                robot.release()
                robot.known["blocker"] = drop
                robot.select("plug")
                plug_pose, _ = observe_object("plug")
                clear_pixels = summary["perception"][-1]["foreground_pixels"]
                summary["occlusion"] = {"before_clear_pixels": blocked_pixels, "after_clear_pixels": clear_pixels}
                robot.grasp(plug_pose, objects["plug"].side_grasp())
                upright = transform(CRADLE_POSITION + [0., 0., -objects["plug"].bounds[0, 2] + .006])
                tcp = upright @ np.linalg.inv(robot.tool_T_object)
                high = tcp.copy(); high[2, 3] = .56
                robot.move(high, "REORIENT_FOR_REGRASP")
                robot.move(tcp, "PLACE_IN_REGRASP_CRADLE", allow_support=True)
                robot.release(retreat_distance=.10, lower_open_hand=.008)
                upright_pose, _ = observe_object("plug")
                summary["regrasp"] = {"executed": True, "upright_pose_estimated": upright_pose.tolist()}
                robot.grasp(upright_pose)
            else:
                robot.grasp(plug_pose)

        # Orient above the current visual target, then use the wrist image to
        # measure the actual held-object/tool relationship and fixture pose.
        bottom = -objects["plug"].bounds[0, 2]
        target_object = robot.fixture_estimate @ transform([0., 0., bottom])
        target_tcp = target_object @ np.linalg.inv(robot.tool_T_object)
        hover = target_tcp.copy(); hover[2, 3] = .56
        robot.move(hover, "ASSEMBLY_HOVER")
        if args.method != "no_wrist":
            robot.hold(.3, "WRIST_OBSERVE")
            # Full close-range registration can resolve the nearly rectangular
            # silhouette's 180-degree ambiguity in the distant first view.
            held_pose, _ = observe_object("plug", WRIST_CAMERA)
            robot.tool_T_object = np.linalg.inv(robot.tcp_pose()) @ held_pose
            observe_fixture(WRIST_CAMERA)
        else:
            robot.event("wrist_refinement_disabled", object_id="plug")
        disturbance_done = False

        def environment(stage):
            nonlocal disturbance_done
            if impulse is not None:
                impulse(stage)
            if args.disturbance == "fixture_shift" and not disturbance_done and stage == "INSERT_1":
                scene.disturb_fixture()
                disturbance_done = True
                robot.event("environment_fixture_displaced", controller_receives_delta=False)

        robot.environment_hook = environment
        inserted = False
        for attempt in range(1, 4):
            target_object = robot.fixture_estimate @ transform([0., 0., bottom])
            target_tcp = target_object @ np.linalg.inv(robot.tool_T_object)
            axis = robot.fixture_estimate[:3, 2]
            orient = target_tcp.copy(); orient[2, 3] = .56
            robot.move(orient, f"ORIENT_FOR_INSERTION_{attempt}")
            preinsert = target_tcp.copy()
            preinsert[:3, 3] += axis * (SOCKET_DEPTH + .015)
            robot.move(preinsert, f"ALIGN_{attempt}")
            robot.hold(.4, "TARE_FORCE")
            bias = robot.wrench()
            completed = True
            for distance in np.linspace(SOCKET_DEPTH + .015, 0., 21)[1:]:
                goal = target_tcp.copy(); goal[:3, 3] += axis * distance
                if not robot.move(goal, f"INSERT_{attempt}", allow_support=True, force_bias=bias, force_limit=8.):
                    completed = False
                    break
            summary["assembly_attempts"].append({"attempt": attempt, "reached_target": completed,
                                                  "wrist_force_delta_n": float(np.linalg.norm(robot.wrench()[:3] - bias[:3]))})
            if completed:
                inserted = True
                robot.event("reached_visual_insertion_target", attempt=attempt)
                break
            if args.disable_recovery:
                raise RuntimeError("Insertion contact guard triggered; recovery ablation stops here")
            retreat = robot.tcp_pose(); retreat[:3, 3] += axis * .05
            robot.move(retreat, "RETRACT_AFTER_CONTACT", allow_support=True)
            observe_fixture(CAMERA_NAME if args.method == "no_wrist" else WRIST_CAMERA)
            if args.method != "no_wrist":
                held_pose, _ = observe_object("plug", WRIST_CAMERA, prior=robot.tcp_pose() @ robot.tool_T_object)
                robot.tool_T_object = np.linalg.inv(robot.tcp_pose()) @ held_pose
            robot.event("relocalized_for_retry", attempt=attempt + 1)
        if not inserted:
            raise RuntimeError("Assembly did not complete within three contact-limited attempts")
        summary["before_release_evaluation_only"] = seating_evaluation(scene)
        robot.release()
        robot.hold(3., "FINAL_STABILITY")
        outcome = seating_evaluation(scene)
        summary.update(success=outcome["success"], final_evaluation_only=outcome,
                       fixture_disturbance_executed=disturbance_done, simulation_time_s=float(data.time))
        if not summary["success"]:
            raise RuntimeError(f"Final physical seating failed: {outcome}")
    except Exception as exc:
        summary.update(error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        if robot is not None:
            summary["execution"] = robot.save()
            summary["timing"] = timing_metrics(summary, robot, started)
            summary["last_stage"] = robot.stage
            summary["simulation_seconds"] = float(data.time)
            summary.setdefault("final_evaluation_only", seating_evaluation(scene))
            np.savez(output / "final_state_evaluation_only.npz", qpos=data.qpos, qvel=data.qvel,
                     ctrl=data.ctrl, mocap_pos=data.mocap_pos, mocap_quat=data.mocap_quat, time=data.time)
            summary["fixture_disturbance_executed"] = any(
                item["event"] == "environment_fixture_displaced" for item in robot.events)
        if worker is not None:
            worker.close()
        if observer is not None:
            observer.close()
        if recorder is not None:
            summary["video_frames"] = recorder.frames
            recorder.close()
        summary["wall_seconds"] = time.perf_counter() - started
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({k: summary.get(k) for k in ("success", "task", "error", "wall_seconds")}))
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
