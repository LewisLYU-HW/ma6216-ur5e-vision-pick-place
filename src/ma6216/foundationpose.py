"""Headless adapter to the user's existing NVIDIA FoundationPose checkout.

Input depth and mesh units are metres. The output T_C_O maps the original
mesh frame into the OpenCV camera frame (+x right, +y down, +z forward).
No simulator state or annotated object poses are read by this module.
"""

from __future__ import annotations

import csv
import hashlib
import importlib
from itertools import permutations, product
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def cube_symmetry_transforms():
    """Proper rotations of a centred, unmarked cube in its model frame."""
    transforms = []
    for permutation in permutations(range(3)):
        for signs in product((-1, 1), repeat=3):
            rotation = np.eye(3)[:, permutation] * signs
            if np.linalg.det(rotation) > 0:
                transform = np.eye(4)
                transform[:3, :3] = rotation
                transforms.append(transform)
    return np.asarray(transforms, dtype=np.float32)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_rigid_transform(pose: np.ndarray) -> np.ndarray:
    pose = np.asarray(pose, dtype=np.float64)
    if pose.shape != (4, 4) or not np.isfinite(pose).all():
        raise ValueError("FoundationPose did not return a finite 4x4 transform")
    if not np.allclose(pose[3], [0, 0, 0, 1], atol=1e-5):
        raise ValueError("Invalid homogeneous-transform last row")
    rotation = pose[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-3):
        raise ValueError("FoundationPose rotation is not orthogonal")
    if not np.isclose(np.linalg.det(rotation), 1, atol=1e-3):
        raise ValueError("FoundationPose rotation determinant is not +1")
    return pose


def validate_pose(pose: np.ndarray) -> np.ndarray:
    pose = validate_rigid_transform(pose)
    if pose[2, 3] <= 0:
        raise ValueError("Estimated object origin is behind the camera")
    return pose


def upright_yaw_grid(world_T_camera):
    """Cover every tabletop heading when model +Z is the known support normal."""
    camera_R_world = validate_rigid_transform(world_T_camera)[:3, :3].T
    rotations = []
    for degrees in range(0, 360, 15):
        yaw = np.deg2rad(degrees)
        c, s = np.cos(yaw), np.sin(yaw)
        world_R_object = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        camera_T_object = np.eye(4)
        camera_T_object[:3, :3] = camera_R_world @ world_R_object
        rotations.append(camera_T_object)
    return np.asarray(rotations, dtype=np.float32)


def bounded_sampled_diameter(model_pts=None, mesh=None, n_sample=1000):
    """Same maximum sampled pair distance as Utils.py, with bounded RAM.

    The official implementation materializes N*N*3 differences for 10k
    sampled vertices. Row blocks preserve the sample and mathematical result.
    """
    from scipy.spatial.distance import cdist

    if mesh is not None:
        raise ValueError("This adapter's bounded diameter requires model_pts")
    points = np.asarray(model_pts, dtype=np.float64)
    if n_sample is not None:
        selected = np.random.choice(len(points), size=min(n_sample, len(points)), replace=False)
        points = points[selected]
    maximum = 0.0
    for start in range(0, len(points), 128):
        distances = cdist(points[start:start + 128], points, metric="sqeuclidean")
        maximum = max(maximum, float(distances.max()))
    return float(np.sqrt(maximum))


def pose_overlay(rgb, K, pose, mesh_bounds):
    """Return a uint8 RGB preview without opening an OpenCV GUI."""
    import cv2

    output = rgb.copy()
    lower, upper = np.asarray(mesh_bounds)
    corners = np.array([[upper[axis] if (index >> axis) & 1 else lower[axis]
                         for axis in range(3)] for index in range(8)])

    def project(points):
        points = (pose[:3, :3] @ np.asarray(points).T).T + pose[:3, 3]
        if np.any(points[:, 2] <= 0):
            return None
        projected = (K @ points.T).T
        return np.rint(projected[:, :2] / projected[:, 2:]).astype(np.int32)

    pixels = project(corners)
    if pixels is not None:
        for index in range(8):
            for axis in range(3):
                other = index ^ (1 << axis)
                if index < other:
                    cv2.line(output, tuple(pixels[index]), tuple(pixels[other]),
                             (40, 255, 40), 2, cv2.LINE_AA)
    length = float(np.max(upper - lower)) * 0.7
    axes = project(np.vstack([np.zeros(3), np.eye(3) * length]))
    if axes is not None:
        for axis, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
            cv2.line(output, tuple(axes[0]), tuple(axes[axis + 1]), color, 2, cv2.LINE_AA)
    return output


@dataclass
class RGBDDataset:
    root: Path
    intrinsics: Path | None = None
    depth_scale: float = 0.001

    def __post_init__(self) -> None:
        self.root = self.root.expanduser().resolve()
        self.intrinsics = (self.intrinsics or self.root / "cam_K.txt").resolve()
        # Official CUDA crop generation multiplies K by float32 tensors.
        self.K = np.loadtxt(self.intrinsics, dtype=np.float32)
        if self.K.shape != (3, 3) or not np.isfinite(self.K).all():
            raise ValueError("Intrinsics must be a finite 3x3 matrix")
        if self.K[0, 0] <= 0 or self.K[1, 1] <= 0:
            raise ValueError("Focal lengths must be positive")
        if not np.allclose(self.K[2], [0, 0, 1], atol=1e-8):
            raise ValueError("Intrinsics last row must be [0,0,1]")
        if not np.isfinite(self.depth_scale) or self.depth_scale <= 0:
            raise ValueError("PNG depth scale must be positive metres per unit")
        self.rgb_files = sorted((self.root / "rgb").glob("*.png"))
        if not self.rgb_files:
            raise FileNotFoundError(f"No RGB PNG frames in {self.root / 'rgb'}")

    def read(self, index: int, require_mask: bool = True):
        import cv2

        rgb_file = self.rgb_files[index]
        frame_id = rgb_file.stem
        bgr = cv2.imread(str(rgb_file), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError(f"Cannot read RGB frame {rgb_file}")
        rgb = np.ascontiguousarray(bgr[..., ::-1])
        npy_file = self.root / "depth" / f"{frame_id}.npy"
        png_file = self.root / "depth" / f"{frame_id}.png"
        if npy_file.is_file():
            raw_depth = np.load(npy_file, allow_pickle=False)
            if not np.issubdtype(raw_depth.dtype, np.floating):
                raise ValueError(f"NPY metric depth must have a float dtype: {npy_file}")
            depth = raw_depth.astype(np.float32)
            depth_file = npy_file
        else:
            raw_depth = cv2.imread(str(png_file), cv2.IMREAD_UNCHANGED)
            if raw_depth is None or raw_depth.ndim != 2 or raw_depth.dtype != np.uint16:
                raise ValueError(f"Missing float NPY / uint16 PNG depth for frame {frame_id}")
            depth = raw_depth.astype(np.float32) * self.depth_scale
            depth_file = png_file
        if depth.shape != rgb.shape[:2]:
            raise ValueError(f"RGB and depth size mismatch for frame {frame_id}")
        if not np.isfinite(depth).all() or np.any(depth < 0):
            raise ValueError(f"Depth contains nonfinite or negative values: {depth_file}")
        mask_file = self.root / "masks" / f"{frame_id}.png"
        mask = None
        if mask_file.is_file():
            mask_image = cv2.imread(str(mask_file), cv2.IMREAD_GRAYSCALE)
            if mask_image is None or mask_image.shape != depth.shape:
                raise ValueError(f"Invalid or mismatched mask: {mask_file}")
            mask = mask_image > 0
        if require_mask:
            if mask is None:
                raise FileNotFoundError(f"Registration requires an image-derived mask: {mask_file}")
            valid = mask & (depth >= 0.001)
            if np.count_nonzero(valid) < 16:
                raise ValueError(f"Fewer than 16 valid masked depth pixels: {frame_id}")
            if np.count_nonzero(mask) >= 0.8 * mask.size:
                raise ValueError(f"Mask covers almost the entire image: {frame_id}")
        return frame_id, rgb, np.ascontiguousarray(depth), mask, {
            "rgb": str(rgb_file), "depth": str(depth_file),
            "mask": str(mask_file) if mask is not None else None,
            "rgb_sha256": sha256(rgb_file), "depth_sha256": sha256(depth_file),
            "mask_sha256": sha256(mask_file) if mask is not None else None,
        }


class FoundationPoseAdapter:
    def __init__(self, repository: Path, mesh_file: Path, debug_dir: Path,
                 cube_symmetry: bool = False, rotation_grid: np.ndarray | None = None):
        repository = repository.expanduser().resolve()
        mesh_file = mesh_file.expanduser().resolve()
        if not (repository / "estimater.py").is_file():
            raise FileNotFoundError(f"Existing FoundationPose estimater.py not found: {repository}")
        if not mesh_file.is_file():
            raise FileNotFoundError(mesh_file)
        sys.path.insert(0, str(repository))
        # Use the official local implementation and already installed predictors.
        implementation = importlib.import_module("estimater")
        import torch
        import trimesh
        import nvdiffrast.torch as dr

        if not torch.cuda.is_available():
            raise RuntimeError("The existing FoundationPose environment requires a CUDA GPU")
        mesh = trimesh.load(str(mesh_file), force="mesh", process=False)
        if not isinstance(mesh, trimesh.Trimesh) or len(mesh.vertices) < 4 or len(mesh.faces) < 4:
            raise ValueError("Mesh must be a triangulated nonempty Trimesh in metres")
        if not np.isfinite(mesh.vertices).all():
            raise ValueError("Mesh vertices are not finite")
        extent = np.ptp(mesh.vertices, axis=0)
        if np.min(extent) <= 0 or np.max(extent) > 5:
            raise ValueError("Mesh dimensions must be nonzero and in metres (max 5 m)")
        self.mesh_extents_m = extent.tolist()
        self.mesh_bounds_m = mesh.bounds.copy()
        symmetry_tfs = None
        if cube_symmetry:
            if not np.allclose(extent, extent[0], atol=1e-6) or not np.allclose(mesh.bounds.mean(axis=0), 0, atol=1e-6):
                raise ValueError("Cube symmetry requires a centred cube in the CAD frame")
            symmetry_tfs = cube_symmetry_transforms()
        implementation.set_seed(0)
        original_diameter = implementation.compute_mesh_diameter
        implementation.compute_mesh_diameter = bounded_sampled_diameter
        try:
            self.estimator = implementation.FoundationPose(
                model_pts=mesh.vertices, model_normals=mesh.vertex_normals, mesh=mesh, symmetry_tfs=symmetry_tfs,
                scorer=implementation.ScorePredictor(),
                refiner=implementation.PoseRefinePredictor(),
                glctx=dr.RasterizeCudaContext(), debug=0, debug_dir=str(debug_dir),
            )
        finally:
            implementation.compute_mesh_diameter = original_diameter
        if rotation_grid is not None:
            self.estimator.rot_grid = torch.as_tensor(rotation_grid, device="cuda", dtype=torch.float32)
        self.torch = torch

    def estimate(self, rgb, depth, K, mask, register: bool, iterations: int):
        self.torch.cuda.synchronize()
        start = time.perf_counter()
        if register:
            pose = self.estimator.register(K=K, rgb=rgb, depth=depth,
                                           ob_mask=mask, iteration=iterations)
            # The official code returns a fallback if too little filtered depth
            # remains. It has no pose_last in that case: do not report success.
            if self.estimator.pose_last is None:
                raise RuntimeError("Registration returned a fallback without a scored pose")
        else:
            pose = self.estimator.track_one(rgb=rgb, depth=depth, K=K, iteration=iterations)
        self.torch.cuda.synchronize()
        return validate_pose(pose), time.perf_counter() - start


def run_sequence(*, dataset: Path, repository: Path, mesh: Path, output: Path,
                 intrinsics: Path | None = None, intrinsics_source: str = "provided",
                 depth_scale: float = 0.001, mode: str = "register-track",
                 max_frames: int | None = None, registration_iterations: int = 5,
                 tracking_iterations: int = 2, validate_only: bool = False, cube_symmetry: bool = False,
                 upright_extrinsic: Path | None = None) -> dict:
    if mode not in ("register-track", "register-each"):
        raise ValueError(f"Unknown sequence mode: {mode}")
    if registration_iterations < 1 or tracking_iterations < 1:
        raise ValueError("Refinement iterations must be positive")
    if max_frames is not None and max_frames < 1:
        raise ValueError("max_frames must be positive")
    rotation_grid = None
    if upright_extrinsic is not None:
        if cube_symmetry:
            raise ValueError("Choose cube symmetry or the upright yaw prior")
        upright_extrinsic = upright_extrinsic.expanduser().resolve()
        rotation_grid = upright_yaw_grid(np.loadtxt(upright_extrinsic))
    reader = RGBDDataset(dataset, intrinsics=intrinsics, depth_scale=depth_scale)
    count = len(reader.rgb_files) if max_frames is None else min(max_frames, len(reader.rgb_files))
    # Check every selected input before reserving the GPU or producing results.
    inputs = [reader.read(i, require_mask=(i == 0 or mode == "register-each"))[4]
              for i in range(count)]
    mesh = mesh.expanduser().resolve()
    if not mesh.is_file():
        raise FileNotFoundError(mesh)
    output = output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output must be new or empty to preserve evidence: {output}")
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "inputs_validated" if validate_only else "running",
        "dataset": str(reader.root), "repository": str(repository.expanduser().resolve()),
        "mesh": str(mesh), "mesh_sha256": sha256(mesh),
        "intrinsics": str(reader.intrinsics), "intrinsics_source": intrinsics_source,
        "intrinsics_sha256": sha256(reader.intrinsics), "K": reader.K.tolist(),
        "depth_unit": "metre", "png_depth_scale_m_per_unit": depth_scale,
        "pose_convention": "T_C_O: original mesh to OpenCV camera; x right,y down,z forward",
        "mode": mode, "selected_frames": count, "completed_frames": 0,
        "registration_iterations": registration_iterations,
        "tracking_iterations": tracking_iterations,
        "cube_symmetry_transforms": 24 if cube_symmetry else 1,
        "mesh_diameter_algorithm": "same 10000-vertex random sample; blockwise exact maximum pair distance",
        "ground_truth_used_for_inference": False, "inputs": inputs,
    }
    if upright_extrinsic is not None:
        summary["rotation_initialization"] = {
            "prior": "model +Z aligned with tabletop +Z; all 360 degrees of yaw sampled",
            "yaw_step_deg": 15, "estimated_world_T_camera": str(upright_extrinsic),
            "estimated_world_T_camera_sha256": sha256(upright_extrinsic),
        }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if validate_only:
        return summary
    try:
        git = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=False)
        summary["repository_commit"] = git.stdout.strip() if git.returncode == 0 else None
        adapter = FoundationPoseAdapter(repository, mesh, output / "debug", cube_symmetry=cube_symmetry,
                                        rotation_grid=rotation_grid)
        logging.getLogger().addHandler(logging.FileHandler(output / "inference.log", encoding="utf-8"))
        summary["mesh_extents_m"] = adapter.mesh_extents_m
        summary["torch_version"] = adapter.torch.__version__
        summary["cuda_runtime"] = adapter.torch.version.cuda
        summary["gpu"] = adapter.torch.cuda.get_device_name(0)
        summary["registration_candidate_count"] = len(adapter.estimator.rot_grid)
        (output / "poses").mkdir()
        (output / "previews").mkdir()
        with (output / "frames.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "frame", "operation", "seconds", "mask_pixels", "tx_m", "ty_m", "tz_m"])
            writer.writeheader()
            for i in range(count):
                register = i == 0 or mode == "register-each"
                frame_id, rgb, depth, mask, _ = reader.read(i, require_mask=register)
                pose, elapsed = adapter.estimate(
                    rgb, depth, reader.K, mask, register,
                    registration_iterations if register else tracking_iterations)
                np.savetxt(output / "poses" / f"{frame_id}.txt", pose, fmt="%.10f")
                import cv2
                preview = pose_overlay(rgb, reader.K, pose, adapter.mesh_bounds_m)
                cv2.imwrite(str(output / "previews" / f"{frame_id}.png"), preview[..., ::-1])
                writer.writerow({"frame": frame_id,
                                 "operation": "register" if register else "track",
                                 "seconds": elapsed,
                                 "mask_pixels": int(mask.sum()) if mask is not None else "",
                                 "tx_m": pose[0, 3], "ty_m": pose[1, 3], "tz_m": pose[2, 3]})
                handle.flush()
                summary["completed_frames"] = i + 1
                summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
                print(f"POSE {frame_id}: {('register' if register else 'track')} "
                      f"{elapsed:.3f}s t_m={pose[:3, 3].tolist()}", flush=True)
        summary["status"] = "inference_completed"
        summary["peak_cuda_allocated_bytes"] = adapter.torch.cuda.max_memory_allocated()
        summary["accuracy_validated"] = False
    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
