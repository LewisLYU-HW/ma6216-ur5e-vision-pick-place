"""Pick and place a CAD workpiece or the reference cube using a front-side route."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.spatial.transform import Rotation

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS.parent / "src"))
from ma6216.scene import build_scene, mujoco
from ma6216.direct_route import configure_direct_table, plan_direct, set_front_ready
from ma6216.foundationpose import validate_pose
from ma6216.motion import Robot
from ma6216.runner import run_trial
from ma6216.vision import capture_observation, compose_world_pose, make_renderer, prepare_observation_dir
from ma6216.workpiece import WORKPIECE, configure_workpiece, export_mesh, workpiece_mask
from ma6216.config import project_root


class FrontRobot(Robot):
    def __init__(self, model, data, workpiece):
        super().__init__(model, data, target_vertices=WORKPIECE.vertices if workpiece else None)
        self.workpiece = workpiece

    def plan(self, object_pose=None, yaw=0.):
        if object_pose is None:
            xyz = self.data.xpos[self.cbid].copy()
            heading = yaw
            source = "ground_truth_control_baseline"
        else:
            pose = validate_pose(object_pose)
            xyz = pose[:3, 3]
            axes = pose[:3, :3]
            if self.workpiece:
                if axes[2, 2] < .85:
                    raise ValueError("Estimated workpiece is not upright enough for a top-down grasp")
                axis = 0  # The CAD X axis runs parallel to both grasp faces.
            else:
                axis = int(np.argmax(np.linalg.norm(axes[:2, :], axis=0)))
            heading = float(np.arctan2(axes[1, axis], axes[0, axis]))
            source = "vision_pose_file"

        if not (.32 < xyz[0] < .56 and -.27 < xyz[1] < -.06 and .36 < xyz[2] < .46):
            raise ValueError(f"Target is outside the tested front pick area: {xyz}")
        # Swapping the left and right pads preserves a two-finger grasp.
        # The asymmetric workpiece itself retains its original estimated heading.
        period = np.pi if self.workpiece else np.pi / 2
        grasp_yaw = (heading + period / 2) % period - period / 2
        min_centre_z = WORKPIECE.object_z - .001 if self.workpiece else .400
        offset_z = WORKPIECE.grasp_offset_z if self.workpiece else .003
        grasp_z = float(xyz[2] + offset_z)
        planning_centre_z = float(max(xyz[2], min_centre_z))
        if object_pose is not None:
            adr = self.cube_qposadr
            self.initial_qpos[adr:adr+3] = [*xyz[:2], planning_centre_z]
            object_yaw = heading if self.workpiece else grasp_yaw
            self.initial_qpos[adr+3:adr+7] = [np.cos(object_yaw/2), 0., 0., np.sin(object_yaw/2)]
        # The final approach is a low release above the existing tray floor.
        place_z = .437 if self.workpiece else .44
        plan = plan_direct(self, xyz, grasp_yaw, grasp_z, place_z,
                           planning_centre_z - grasp_z, source)
        plan["estimated_object_heading_rad"] = heading
        plan["planning_object_qpos"] = self.initial_qpos[self.cube_qposadr:self.cube_qposadr+7].tolist()
        return plan


def path_metrics(samples):
    points = np.asarray([row["tcp_position_m"] for row in samples])
    joints = np.asarray([row["joint_position_rad"] for row in samples])
    transfers = [i for i, row in enumerate(samples) if row["stage"].startswith("HOVER_TRAY")]
    if len(transfers) < 2:
        return {}
    # Include the last sample of the lift as the start of the lateral segment.
    indexes = [max(0, transfers[0] - 1), *transfers]
    transfer = points[indexes]
    offset = transfer[:, :2] - transfer[0, :2]
    chord = offset[-1]
    norm = np.linalg.norm(chord)
    lateral_deviation = np.abs(offset[:, 0] * chord[1] - offset[:, 1] * chord[0]) / norm if norm > 0 else np.linalg.norm(offset, axis=1)
    return {
        "total_tcp_travel_m": float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum()),
        "transfer_tcp_travel_m": float(np.linalg.norm(np.diff(transfer, axis=0), axis=1).sum()),
        "transfer_xy_displacement_m": float(norm),
        "transfer_max_xy_line_deviation_m": float(lateral_deviation.max()),
        "transfer_z_span_m": float(np.ptp(transfer[:, 2])),
        "transfer_joint_travel_deg": np.rad2deg(np.abs(np.diff(joints[indexes], axis=0)).sum(axis=0)).tolist(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("workpiece", "cube"), default="workpiece")
    parser.add_argument("--xy", type=float, nargs=2, default=(.46, -.18))
    parser.add_argument("--yaw-deg", type=float, default=0.)
    parser.add_argument("--calibration", type=Path,
                        default=project_root() / "demo_data/calibration/estimated")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ground-truth", action="store_true", help="Diagnostic physical baseline; skip vision")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--viewer", action="store_true")
    args = parser.parse_args()
    if not args.ground_truth:
        for name in ("cam_K.txt", "world_T_camera.txt"):
            if not (args.calibration / name).is_file():
                parser.error(f"Missing estimated calibration: {args.calibration / name}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    workpiece = args.target == "workpiece"
    yaw = np.deg2rad(args.yaw_deg)
    summary = {"success": False, "status": "scene", "target": args.target,
               "control_source": "ground_truth_control_baseline" if args.ground_truth else "FoundationPose + estimated calibration",
               "initial_xy_m": list(args.xy), "initial_yaw_deg": args.yaw_deg}

    def configure(spec):
        configure_direct_table(spec)
        if workpiece:
            configure_workpiece(spec)

    try:
        model, data = build_scene(args.xy, yaw, calibration_board=False,
                                  configure_spec=configure, object_z=WORKPIECE.object_z if workpiece else .401)
        set_front_ready(model, data)
        for _ in range(775):
            mujoco.mj_step(model, data)
        pose = None
        if not args.ground_truth:
            summary["status"] = "capture"
            observations = output / "observation"
            mesh = prepare_observation_dir(observations, args.calibration,
                                           export_target_mesh=export_mesh if workpiece else None)
            renderer = make_renderer(model)
            try:
                kwargs = {"segment": workpiece_mask} if workpiece else {}
                mask, _ = capture_observation(renderer, data, observations, "000000", **kwargs)
                summary["mask_pixels"] = int(np.count_nonzero(mask))
            finally:
                renderer.close()
            summary["status"] = "foundationpose"
            inference = output / "foundationpose"
            command = [sys.executable, "-u", str(SCRIPTS / "run_foundationpose.py"),
                       "--dataset", str(observations), "--mesh", str(mesh),
                       "--intrinsics-source", "calibration", "--output", str(inference)]
            if workpiece:
                command.extend(("--upright-extrinsic", str(observations / "world_T_camera_estimated.txt")))
            else:
                command.append("--cube-symmetry")
            with (output / "foundationpose.log").open("w") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            pose = compose_world_pose(inference / "poses/000000.txt", observations / "world_T_camera_estimated.txt")
            np.savetxt(output / "world_T_object_estimated.txt", pose)
            # Simulator truth is recorded for evaluation only, after pose inference.
            body = model.body("target_cube").id
            true_rotation = data.xmat[body].reshape(3, 3)
            summary["pose_evaluation_only"] = {
                "translation_error_mm": float(1000 * np.linalg.norm(pose[:3, 3] - data.xpos[body])),
                "raw_rotation_error_deg": float(np.rad2deg(Rotation.from_matrix(pose[:3, :3] @ true_rotation.T).magnitude())),
            }
        summary["status"] = "physical_execution"
        robot = FrontRobot(model, data, workpiece)
        result = run_trial(model, data, output / "motion", pose=pose, yaw=yaw,
                           viewer=args.viewer, record=args.record, robot=robot)
        summary.update(success=result["success"], status="completed" if result["success"] else "motion_failed",
                       motion=result, route_metrics=path_metrics(robot.samples))
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        print(summary["error"], file=sys.stderr)
    finally:
        (output / "summary.json").write_text(json.dumps(summary, indent=2))
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
