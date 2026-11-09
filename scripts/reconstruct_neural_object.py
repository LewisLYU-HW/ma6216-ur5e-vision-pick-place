"""Train the official FoundationPose Neural Object Field from RGB-D references.

Run in the FoundationPose Python environment. No simulator or CAD module is
imported. The only object-specific inputs are the captured reference dataset.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

import cv2
import numpy as np
import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", required=True, type=Path)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--mesh-resolution-mm", type=float, default=.8)
    parser.add_argument("--optimize-reference-poses", action="store_true",
                        help="Enable official pose refinement; default keeps the calibrated synthetic scan rig fixed")
    args = parser.parse_args()
    if args.steps < 100 or not .3 <= args.mesh_resolution_mm <= 3.:
        parser.error("Use >=100 steps and 0.3..3 mm mesh resolution")
    refs, repo, output = args.references.resolve(), args.repository.resolve(), args.output.resolve()
    manifest = json.loads((refs / "references.json").read_text())
    if manifest.get("cad_exported_to_reconstruction") is not False:
        raise ValueError("Reference dataset must explicitly declare no CAD export")
    for relative, expected in manifest["files_sha256"].items():
        path = (refs / relative).resolve()
        if refs not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Reference input integrity failure: {relative}")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    summary = {"success": False, "method": "official FoundationPose few-shot Neural Object Field",
               "inputs": "RGB + metric depth + foreground masks + calibrated reference camera poses",
               "cad_used_for_reconstruction": False, "object_pose_ground_truth_input": False,
               "reference_manifest_sha256": hashlib.sha256((refs / "references.json").read_bytes()).hexdigest(),
               "reference_views": manifest["scan_views"], "object_id": manifest["object_id"]}
    try:
        sys.path.insert(0, str(repo))
        sys.path.insert(0, str(repo / "bundlesdf"))
        from run_nerf import run_neural_object_field
        import torch
        rgbs, depths, masks, poses = [], [], [], []
        K = np.loadtxt(refs / "cam_K.txt")
        for frame in manifest["frames"]:
            name = frame["id"]
            rgb = cv2.imread(str(refs / "rgb" / f"{name}.png"))
            mask = cv2.imread(str(refs / "masks" / f"{name}.png"), 0)
            depth = np.load(refs / "depth" / f"{name}.npy")
            pose = np.loadtxt(refs / "scan_T_camera" / f"{name}.txt")
            if rgb is None or mask is None or depth.shape != mask.shape or not np.isfinite(depth).all():
                raise ValueError(f"Invalid RGB-D reference frame {name}")
            rgbs.append(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB))
            depths.append(depth)
            masks.append(mask)
            poses.append(pose)
        cfg = yaml.safe_load((repo / "bundlesdf/config_ycbv.yml").read_text())
        # Resource settings for the 16 GB workstation; preserve official
        # losses, pose refinement, neural field and texturing algorithms.
        cfg.update(n_step=args.steps, N_rand=512, N_samples=64, N_samples_around_depth=64,
                   log2_hashmap_size=19, finest_res=256, netchunk=65536,
                   mesh_resolution=args.mesh_resolution_mm / 1000,
                   dbscan_eps=.01, dbscan_eps_min_samples=1,
                   i_print=100, i_img=100000, i_mesh=100000, i_weights=100000,
                   i_pose=100000, i_nerf_normals=100000, i_save_ray=100000)
        # The official export helper requires a PoseArray even for a calibrated
        # rig. Keep that identity array, but freeze its optimizer when requested.
        cfg["optimize_poses"] = 1
        if not args.optimize_reference_poses:
            cfg["lrate_pose"] = 0.
            cfg["pose_optimize_start"] = args.steps + 1
        summary["reference_pose_refinement_enabled"] = args.optimize_reference_poses
        (output / "neural_field_config.yml").write_text(yaml.safe_dump(cfg))
        summary["repository_commit"] = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        summary["gpu"] = torch.cuda.get_device_name(0)
        mesh = run_neural_object_field(cfg, K, rgbs, depths, masks, poses,
                                      save_dir=str(output / "training"), debug=0)
        if mesh is None or len(mesh.vertices) < 20 or not np.isfinite(mesh.vertices).all():
            raise RuntimeError("Official neural field did not yield a usable surface")
        extent = np.ptp(mesh.vertices, axis=0)
        if min(extent) < .005 or max(extent) > 1.:
            raise RuntimeError(f"Reconstructed surface has implausible metric scale: {extent}")
        mesh.export(str(output / "model.obj"))
        import trimesh
        round_trip = trimesh.load(str(output / "model.obj"), force="mesh", process=False)
        if not np.isfinite(round_trip.vertices).all() or not np.allclose(round_trip.bounds, mesh.bounds, atol=1e-7):
            raise RuntimeError("Reconstructed mesh failed export/import validation")
        torch.cuda.synchronize()
        summary.update(success=True, mesh_file="model.obj", mesh_vertices=len(mesh.vertices),
                       mesh_faces=len(mesh.faces), observed_extents_m=extent.tolist(),
                       bounds_m=mesh.bounds.tolist(), training_steps=args.steps,
                       model_frame="reference scanner frame", mesh_resolution_mm=args.mesh_resolution_mm)
        summary["export_round_trip_validated"] = True
        summary["worker_exit_strategy"] = "one-shot process; skip native interpreter finalizers after synchronized export"
        summary["files_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in output.iterdir() if p.is_file() and p.suffix in (".obj", ".mtl", ".png")}
    except Exception as exc:
        summary.update(error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        summary["wall_clock_seconds"] = time.perf_counter() - started
        (output / "model_free.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({k: summary.get(k) for k in ("success", "method", "error", "wall_clock_seconds")}))
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    # This workstation's CUDA/OpenGL extension combination can abort in native
    # interpreter finalizers after a successful export (free: invalid pointer).
    # The worker is deliberately one-shot. Validate/close files and synchronize
    # CUDA above, flush logs, then let the OS reclaim its native resources.
    status = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
