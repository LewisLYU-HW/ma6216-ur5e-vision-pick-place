"""Downstream measurements only; no ground-truth values return to control."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation


def state_fingerprint(data):
    """Audit identical starts across paired trials; never supplied to control."""
    digest = hashlib.sha256()
    for name in ("qpos", "qvel", "ctrl", "mocap_pos", "mocap_quat"):
        digest.update(np.ascontiguousarray(getattr(data, name)).tobytes())
    return digest.hexdigest()


def pose_errors(estimate, truth, vertices=None):
    estimate, truth = np.asarray(estimate), np.asarray(truth)
    translation = float(np.linalg.norm(estimate[:3, 3] - truth[:3, 3]) * 1000)
    rotation = float(np.rad2deg(Rotation.from_matrix(estimate[:3, :3] @ truth[:3, :3].T).magnitude()))
    result = {
        "translation_error_mm": translation,
        "rotation_error_deg": rotation,
        "within_5mm_5deg": translation <= 5.0 and rotation <= 5.0,
    }
    if vertices is not None:
        vertices = np.asarray(vertices)
        # A fixed deterministic sample limits evaluation overhead identically
        # across methods. ADD-S is reported separately, not as task success.
        v = vertices[np.linspace(0, len(vertices) - 1, min(1024, len(vertices)), dtype=int)]
        a = v @ estimate[:3, :3].T + estimate[:3, 3]
        b = v @ truth[:3, :3].T + truth[:3, 3]
        add = float(np.mean(np.linalg.norm(a - b, axis=1)))
        adds = float(np.mean(cKDTree(b).query(a)[0]))
        diameter = float(np.linalg.norm(np.ptp(vertices, axis=0)))
        result.update(
            add_mm=add * 1000,
            adds_mm=adds * 1000,
            reference_bbox_diagonal_m=diameter,
            adds_below_10pct_bbox_diagonal=adds < 0.1 * diameter,
            surface="fixed sampled reference reconstruction; not simulator CAD",
        )
    return result


def camera_metrics(model, data, observer, calibration):
    from .scene import camera_ground_truth

    K, T = camera_ground_truth(model, data)
    result = {
        "fixed_extrinsic": pose_errors(observer.fixed_extrinsic, T),
        "focal_relative_error": (np.diag(observer.fixed_K)[:2] / np.diag(K)[:2] - 1).tolist(),
        "principal_point_error_px": (observer.fixed_K[:2, 2] - K[:2, 2]).tolist(),
        "wrist_hand_eye": {
            "status": "ideal synthetic mount, not independently estimated",
            "measured_error": None,
        },
        "calibration_files_sha256": {},
    }
    folder = Path(calibration)
    for name in ("cam_K.txt", "world_T_camera.txt"):
        result["calibration_files_sha256"][name] = hashlib.sha256((folder / name).read_bytes()).hexdigest()
    file = folder / "calibration.json"
    if (
        not file.exists()
        and folder.resolve() == Path(__file__).resolve().parents[2] / "demo_data/calibration/estimated"
    ):
        file = Path(__file__).resolve().parents[2] / "docs/results/calibration.json"
    if file.exists():
        saved = json.loads(file.read_text())
        result["checkerboard_reprojection"] = {
            k: saved[k]
            for k in ("intrinsic_train", "intrinsic_validation", "extrinsic_train", "extrinsic_validation")
            if k in saved
        }
        result["checkerboard_report_sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
    return result


def distribution(values):
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if not len(v):
        return {"count": 0, "mean": None, "rmse": None, "median": None, "p95": None, "max": None}
    return {
        "count": len(v),
        "mean": float(v.mean()),
        "rmse": float(np.sqrt(np.mean(v * v))),
        "median": float(np.median(v)),
        "p95": float(np.percentile(v, 95)),
        "max": float(v.max()),
    }


def wilson_interval(successes, total):
    if total == 0:
        return [None, None]
    z = 1.959963984540054
    p = successes / total
    den = 1 + z * z / total
    middle = (p + z * z / (2 * total)) / den
    half = z * np.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / den
    return [max(0.0, float(middle - half)), min(1.0, float(middle + half))]


def timing_metrics(report, robot, started):
    import time
    import os

    samples = report.get("perception", [])
    infer = [r["inference_seconds"] for r in samples if "inference_seconds" in r]
    wall = time.perf_counter() - started
    return {
        "benchmark_parallel_trials": int(os.environ.get("MA6216_BENCHMARK_PARALLEL_TRIALS", "1")),
        "shared_gpu_worker": any(s.get("shared_gpu_worker", False) for s in samples),
        "wall_seconds": wall,
        "controller_setpoint_hz_simulation": 1 / robot.model.opt.timestep,
        "logged_execution_sample_hz_simulation": 1 / (10 * robot.model.opt.timestep),
        "executed_control_steps": robot.ticks,
        "effective_steps_per_wall_second": robot.ticks / wall,
        "physics_seconds_executed": robot.ticks * robot.model.opt.timestep,
        "real_time_factor": robot.ticks * robot.model.opt.timestep / wall,
        "pose_calls_per_wall_second_including_waits": len(infer) / wall,
        "inference_latency_seconds": distribution(infer),
        "register_latency_seconds": distribution(
            [
                r["inference_seconds"]
                for r in samples
                if r.get("operation") == "register" and "inference_seconds" in r
            ]
        ),
        "track_latency_seconds": distribution(
            [
                r["inference_seconds"]
                for r in samples
                if r.get("operation") == "track" and "inference_seconds" in r
            ]
        ),
        "depth_refinement_latency_seconds": distribution(
            [r["depth_refinement"]["wall_seconds"] for r in samples if "depth_refinement" in r]
        ),
        "warning": "Simulation step rate, neural inference throughput, and achieved closed-loop frequency are different quantities; vision is intermittent.",
    }
