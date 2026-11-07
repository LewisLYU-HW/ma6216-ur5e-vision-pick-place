"""Persistent official FoundationPose worker with reconstructed-model provenance."""
import argparse
import contextlib
import json
from pathlib import Path
import sys
import time
import traceback

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.foundationpose import FoundationPoseAdapter, validate_rigid_transform
from ma6216.reconstructed import validate_bundle

PREFIX = "MA6216_REPLY "


def reply(value):
    print(PREFIX + json.dumps(value), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--debug-dir", required=True, type=Path)
    args = parser.parse_args()
    args.debug_dir.mkdir(parents=True, exist_ok=True)
    models, histories = {}, {}
    reply({"ready": True})
    for line in sys.stdin:
        started = time.perf_counter()
        request = {}
        try:
            request = json.loads(line)
            if request.get("operation") == "shutdown":
                return
            bundle = Path(request["model_bundle"]).resolve()
            key = str(bundle)
            if key not in models:
                manifest, mesh = validate_bundle(bundle)
                with contextlib.redirect_stdout(sys.stderr):
                    adapter = FoundationPoseAdapter(args.repository, mesh,
                                                   args.debug_dir / manifest["object_id"])
                models[key] = (adapter, manifest)
            adapter, manifest = models[key]
            sequence = (key, request.get("sequence", "default"))
            prior = request.get("camera_T_object_prior")
            register = bool(request.get("register", False) or (sequence not in histories and prior is None))
            if request.get("operation") == "load":
                reply({"id": request["id"], "success": True, "operation": "load",
                       "wall_seconds": time.perf_counter() - started})
                continue
            rgb = cv2.imread(request["rgb"])
            depth = np.load(request["depth"]).astype(np.float32)
            mask = cv2.imread(request["mask"], 0) if request.get("mask") else None
            K = np.asarray(request["K"], dtype=np.float32)
            if rgb is None or rgb.shape[:2] != depth.shape or K.shape != (3, 3):
                raise ValueError("Invalid RGB-D or camera intrinsics")
            original_size = [rgb.shape[1], rgb.shape[0]]
            # The official full SO(3) crop batch otherwise exhausts this 16 GB
            # GPU at 1280x960. Resize all image inputs with matching intrinsics;
            # the separate fixture estimator retains the original resolution.
            scale = min(1., 800. / rgb.shape[1])
            if scale < 1.:
                size = (round(rgb.shape[1] * scale), round(rgb.shape[0] * scale))
                rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
                depth = cv2.resize(depth, size, interpolation=cv2.INTER_NEAREST)
                mask = cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST) if mask is not None else None
                K[:2, :] *= scale
                K[:2, 2] += (scale - 1.) / 2
            if register and (mask is None or np.count_nonzero(mask) < 40):
                raise ValueError("Registration requires a visible foreground mask")
            if prior is not None and not register:
                prior = validate_rigid_transform(np.asarray(prior))
                center_transform = adapter.estimator.get_tf_to_centered_mesh().detach().cpu().numpy()
                centered = prior @ np.linalg.inv(center_transform)
                adapter.estimator.pose_last = adapter.torch.as_tensor(centered, dtype=adapter.torch.float32, device="cuda")
            elif not register:
                adapter.estimator.pose_last = histories[sequence].clone()
            with contextlib.redirect_stdout(sys.stderr):
                pose, elapsed = adapter.estimate(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB), depth, K,
                                                 mask, register, 5 if register else 2)
            histories[sequence] = adapter.estimator.pose_last.clone()
            camera_T_object = validate_rigid_transform(pose)
            result = {"id": request["id"], "success": True, "operation": "register" if register else "track",
                      "capture_time_s": request["capture_time_s"], "camera_T_object": camera_T_object.tolist(),
                      "inference_seconds": elapsed, "wall_seconds": time.perf_counter() - started,
                      "original_image_size": original_size, "inference_image_size": [rgb.shape[1], rgb.shape[0]],
                      "model_sha256": manifest["files_sha256"][manifest["mesh_file"]],
                      "model_free": True, "cad_used_for_reconstruction": False,
                      "visual_kinematic_prior_used": prior is not None,
                      "object_pose_ground_truth_input": False}
            reply(result)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            reply({"id": request.get("id"), "success": False,
                   "error": f"{type(exc).__name__}: {exc}", "wall_seconds": time.perf_counter() - started})


if __name__ == "__main__":
    main()
