"""Execute an already initialized MuJoCo trial and save physical evidence."""
import csv
import json
from pathlib import Path
import traceback

import cv2
import numpy as np

from .scene import mujoco
from .motion import Robot


def run_trial(model, data, output, *, pose=None, yaw=0., viewer=False, record=False, robot=None,
              shared_viewer=None, record_cameras=("overview",)):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    robot = Robot(model, data) if robot is None else robot
    viewer_handle = shared_viewer
    renderer = None
    writer = None
    view_writers = {}
    next_frame = float(data.time)
    last_stage = None

    def on_frame(m, d, stage):
        nonlocal next_frame, last_stage
        if viewer_handle is not None:
            if not viewer_handle.is_running():
                raise RuntimeError("Viewer was closed before the trial completed")
            viewer_handle.sync()
        if renderer is None or d.time + 1e-8 < next_frame:
            return
        forces, _ = robot.finger_contacts()
        label = f"{stage}   t={d.time:.1f}s   object z={d.xpos[robot.cbid, 2]:.3f}m"
        source = "FoundationPose + calibrated camera" if pose is not None else "Ground-truth control baseline"
        load = f"{source} | Left {forces['left']:.1f} N / Right {forces['right']:.1f} N"
        frames = []
        for camera in record_cameras:
            renderer.update_scene(d, camera=camera)
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
            frame = cv2.cvtColor(renderer.render(), cv2.COLOR_RGB2BGR)
            cv2.putText(frame, label, (12, 25), cv2.FONT_HERSHEY_SIMPLEX, .52, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(frame, load, (12, 48), cv2.FONT_HERSHEY_SIMPLEX, .46, (255, 255, 255), 1, cv2.LINE_AA)
            if len(record_cameras) > 1 or camera != "overview":
                cv2.putText(frame, f"View: {camera}", (12, 71), cv2.FONT_HERSHEY_SIMPLEX, .52,
                            (255, 255, 255), 1, cv2.LINE_AA)
            frames.append(frame)
            if camera in view_writers:
                view_writers[camera].write(frame)
        image = np.concatenate(frames, axis=1)
        writer.write(image)
        if stage != last_stage:
            cv2.imwrite(str(output / f"{stage.lower()}.png"), image)
            last_stage = stage
        next_frame += .04

    try:
        if record:
            if not record_cameras or len(set(record_cameras)) != len(record_cameras):
                raise ValueError("Recording requires distinct named cameras")
            for camera in record_cameras:
                if not camera or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in camera):
                    raise ValueError("Recording camera names must be filename-safe")
                model.camera(camera)  # Validate before planning or moving.
        plan = robot.plan(object_pose=pose, yaw=yaw)
        (output / "plan.json").write_text(json.dumps(plan, indent=2))
        if viewer and viewer_handle is None:
            from mujoco import viewer as mujoco_viewer

            viewer_handle = mujoco_viewer.launch_passive(model, data)
            with viewer_handle.lock():
                viewer_handle.cam.lookat[:] = [.35, 0., .4]
                viewer_handle.cam.distance = 1.7
                viewer_handle.cam.azimuth = 130
                viewer_handle.cam.elevation = -30
        if record:
            renderer = mujoco.Renderer(model, height=480, width=640)
            writer = cv2.VideoWriter(str(output / "physical_pick_place.mp4"),
                                     cv2.VideoWriter_fourcc(*"mp4v"), 25., (640 * len(record_cameras), 480))
            if not writer.isOpened():
                raise RuntimeError("MP4 encoder unavailable")
            if len(record_cameras) > 1:
                for camera in record_cameras:
                    view_writers[camera] = cv2.VideoWriter(str(output / f"view_{camera}.mp4"),
                                                          cv2.VideoWriter_fourcc(*"mp4v"), 25., (640, 480))
                    if not view_writers[camera].isOpened():
                        raise RuntimeError(f"MP4 encoder unavailable for {camera}")
        result = robot.execute(plan, frame_callback=on_frame if viewer_handle is not None or record else None,
                               realtime=viewer_handle is not None)
    except Exception as exc:
        result = {"success": False, "error": str(exc), "traceback": traceback.format_exc(),
                  "max_unexpected_robot_penetration_m": robot.max_robot_penetration,
                  "completed_stages": robot.stage_metrics}
        traceback.print_exc()
    finally:
        if writer is not None:
            writer.release()
        for view_writer in view_writers.values():
            view_writer.release()
        if renderer is not None:
            renderer.close()
        if viewer_handle is not None and shared_viewer is None:
            viewer_handle.close()
    (output / "result.json").write_text(json.dumps(result, indent=2))
    if robot.samples:
        rows = []
        for sample in robot.samples:
            vector_keys = ("cube_position_m", "tcp_position_m", "joint_position_rad")
            row = {key: value for key, value in sample.items() if key not in vector_keys}
            row.update(zip(("cube_x_m", "cube_y_m", "cube_z_m"), sample["cube_position_m"]))
            row.update(zip(("tcp_x_m", "tcp_y_m", "tcp_z_m"), sample["tcp_position_m"]))
            row.update({f"q{i}_rad": value for i, value in enumerate(sample["joint_position_rad"], 1)})
            rows.append(row)
        with (output / "samples.csv").open("w", newline="") as stream:
            csv_writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            csv_writer.writeheader()
            csv_writer.writerows(rows)
    print(json.dumps(result), flush=True)
    return result
