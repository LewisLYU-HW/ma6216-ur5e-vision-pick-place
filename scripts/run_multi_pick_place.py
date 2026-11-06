"""Perceive and pick three different objects in one continuous physical scene."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import traceback

import numpy as np
from scipy.spatial.transform import Rotation

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS.parent/"src"))
from ma6216.config import project_root
from ma6216.parts import PARTS
from ma6216.multi_object import MultiRobot, build_multi_scene, physical_outcomes
from ma6216.scene import CAMERA_NAME, mujoco
from ma6216.vision import capture_observation, compose_world_pose, make_renderer, prepare_observation_dir
from ma6216.runner import run_trial


def perceive_remaining(model, data, remaining, output, calibration):
    """Images and known CAD feed inference; ground truth is read only afterward."""
    renderer = make_renderer(model)
    datasets = []
    try:
        for part in remaining:
            dataset = output/part.key/"observation"
            mesh = prepare_observation_dir(dataset, calibration, export_target_mesh=part.export_mesh)
            mask, _ = capture_observation(renderer, data, dataset, "000000", segment=part.mask)
            renderer.enable_segmentation_rendering()
            try:
                seg = renderer.render()
            finally:
                renderer.disable_segmentation_rendering()
            body_geoms=np.flatnonzero(model.geom_bodyid==model.body(part.body).id)
            gt_mask = (np.isin(seg[..., 0],body_geoms) &
                       (seg[..., 1] == int(mujoco.mjtObj.mjOBJ_GEOM)))
            iou = float(np.count_nonzero((mask>0)&gt_mask)/max(1, np.count_nonzero((mask>0)|gt_mask)))
            datasets.append((part, dataset, mesh, iou))
    finally:
        renderer.close()

    poses, metrics = {}, []
    for part, dataset, mesh, iou in datasets:
        result_dir = output/part.key/"foundationpose"
        command = [sys.executable, "-u", str(SCRIPTS/"run_foundationpose.py"),
                   "--dataset", str(dataset), "--mesh", str(mesh), "--output", str(result_dir),
                   "--intrinsics-source", "calibration", "--upright-extrinsic",
                   str(dataset/"world_T_camera_estimated.txt")]
        with (output/part.key/"foundationpose.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        pose = compose_world_pose(result_dir/"poses/000000.txt", dataset/"world_T_camera_estimated.txt")
        np.savetxt(output/part.key/"world_T_object_estimated.txt", pose)
        poses[part.key] = pose
        body = model.body(part.body).id
        raw_rotation=float(np.rad2deg(Rotation.from_matrix(
            pose[:3,:3]@data.xmat[body].reshape(3,3).T).magnitude()))
        from ma6216.object_library import rotation_error
        metrics.append({"id": part.key, "mask_iou": iou,
                        "translation_error_mm": float(1000*np.linalg.norm(pose[:3, 3]-data.xpos[body])),
                        "rotation_error_deg": rotation_error(part,pose[:3,:3],data.xmat[body].reshape(3,3)),
                        "raw_rotation_error_deg": raw_rotation,
                        "orientation_observable": not getattr(part,"sphere",False)})
        print(f"PERCEIVED {part.key}: {metrics[-1]}", flush=True)
    return poses, metrics


def merge_videos(paths, output):
    import cv2
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), 25., (640, 480))
    if not writer.isOpened():
        raise RuntimeError("Cannot encode combined video")
    try:
        for path in paths:
            cap = cv2.VideoCapture(str(path))
            try:
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    writer.write(frame)
            finally:
                cap.release()
    finally:
        writer.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, default=project_root()/"demo_data/calibration/estimated")
    parser.add_argument("--ground-truth", action="store_true", help="Diagnostic physics baseline only")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--viewer", action="store_true")
    parser.add_argument("--collection", choices=("workpieces","diverse"), default="workpieces")
    args = parser.parse_args()
    if args.collection == "diverse":
        from ma6216.object_library import DIVERSE_PARTS
        parts=DIVERSE_PARTS
    else:
        parts=PARTS
    if not args.ground_truth:
        for name in ("cam_K.txt", "world_T_camera.txt"):
            if not (args.calibration/name).is_file():
                parser.error(f"Missing estimated calibration: {args.calibration/name}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    summary = {"success": False, "mode": "multi-object planar pick-and-place",
               "control_source": "ground_truth_control_baseline" if args.ground_truth else "FoundationPose + estimated calibration",
               "object_count": len(parts), "collection": args.collection, "picks": []}
    viewer = None
    videos = []
    try:
        model, data = build_multi_scene(parts)
        for _ in range(775):
            mujoco.mj_step(model, data)
        renderer = make_renderer(model)
        try:
            import cv2
            renderer.update_scene(data, camera=CAMERA_NAME)
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
            cv2.imwrite(str(output/"initial_scene.png"), cv2.cvtColor(renderer.render(), cv2.COLOR_RGB2BGR))
        finally:
            renderer.close()
        known = {}
        for index, selected in enumerate(parts):
            step = output/f"pick_{index+1:02d}_{selected.key}"
            step.mkdir()
            if args.ground_truth:
                for part in parts:
                    body = model.body(part.body).id
                    pose = np.eye(4)
                    pose[:3, :3] = data.xmat[body].reshape(3, 3)
                    pose[:3, 3] = data.xpos[body]
                    known[part.key] = pose
                evaluations = []
            else:
                new_poses, evaluations = perceive_remaining(model, data, parts[index:], step, args.calibration)
                known.update(new_poses)
            if args.viewer and viewer is None:
                from mujoco import viewer as mj_viewer
                viewer = mj_viewer.launch_passive(model, data)
                with viewer.lock():
                    viewer.cam.lookat[:] = [.42, 0, .4]
                    viewer.cam.distance = 1.65
                    viewer.cam.azimuth = 130
                    viewer.cam.elevation = -35
            robot = MultiRobot(model, data, selected, known, ground_truth=args.ground_truth, parts=parts)
            pose_arg = None if args.ground_truth else known[selected.key]
            result = run_trial(model, data, step/"motion", pose=pose_arg, robot=robot,
                               shared_viewer=viewer, record=args.record)
            summary["picks"].append({"id": selected.key, "success": result["success"],
                                     "perception_evaluation_only": evaluations, "motion": result})
            (output/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
            if not result["success"]:
                raise RuntimeError(f"Physical pick failed for {selected.key}: {result.get('error')}")
            if args.record:
                videos.append(step/"motion/physical_pick_place.mp4")
            # The next plan uses the commanded placed pose as an obstacle,
            # with known tray support height. It does not read its true position.
            placed = known[selected.key].copy()
            placed[:3, 3] = [*selected.destination_xy, .389+selected.half_height]
            known[selected.key] = placed
        for _ in range(1000):
            mujoco.mj_step(model, data)
        summary["final_outcomes_evaluation_only"] = physical_outcomes(model, data, parts)
        summary["success"] = all(row["success"] for row in summary["final_outcomes_evaluation_only"])
        summary["simulation_time_s"] = float(data.time)
        renderer = make_renderer(model)
        try:
            renderer.update_scene(data, camera=CAMERA_NAME)
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
            cv2.imwrite(str(output/"final_scene.png"), cv2.cvtColor(renderer.render(), cv2.COLOR_RGB2BGR))
        finally:
            renderer.close()
        if args.record:
            merge_videos(videos, output/"multi_pick_place.mp4")
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["traceback"] = traceback.format_exc()
        traceback.print_exc()
    finally:
        if viewer is not None:
            viewer.close()
        (output/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps({"success": summary["success"], "completed_picks": len(summary["picks"]),
                      "error": summary.get("error")}), flush=True)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
