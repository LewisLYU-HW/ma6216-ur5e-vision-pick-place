"""Texture-independent RGB-D segmentation and reconstructed tool features.

Pickup stations supply broad 3D search regions. All foreground pixels and
object poses come from sensor images; simulator IDs/poses are not used here.
"""

import json

import cv2
import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from .scene import CAMERA_NAME, mujoco
from .task_perception import ImageObserver
from .workshop_scene import PICK_REGIONS, WORKSHOP_T_MARKER


class ObservationUnavailable(RuntimeError):
    """Sensor foreground is occluded/absent; not a GPU infrastructure error."""


def refine_depth_pose(capture, mesh, initial):
    """Bounded, robust point-to-plane alignment of reference RGB-D geometry.

    The only inputs are the reconstructed mesh, measured pixels/calibration,
    and the visual pose. Occluded back faces and distant foreground clutter
    are rejected. This is a local correction, not a global pose initializer.
    """
    import time

    started = time.perf_counter()
    y, x = np.where((capture["mask"] > 0) & np.isfinite(capture["depth"]))
    keep = np.linspace(0, len(x) - 1, min(len(x), 6000), dtype=int)
    x, y = x[keep], y[keep]
    points = np.c_[x, y, np.ones(len(x))] @ np.linalg.inv(capture["K"]).T
    points *= capture["depth"][y, x, None]
    camera = capture["world_T_camera"]
    points = points @ camera[:3, :3].T + camera[:3, 3]
    vertices, vertex_normals = np.asarray(mesh.vertices), np.asarray(mesh.vertex_normals)
    tree = cKDTree(vertices)
    pose = np.asarray(initial).copy()
    best_pose, best_error = pose.copy(), float("inf")
    errors, inliers = [], 0
    for _ in range(30):
        local = (points - pose[:3, 3]) @ pose[:3, :3]
        distance, indices = tree.query(local)
        surface = vertices[indices] @ pose[:3, :3].T + pose[:3, 3]
        normals = vertex_normals[indices] @ pose[:3, :3].T
        view = camera[:3, 3] - surface
        visible = np.sum(normals * view, axis=1) > 0.05 * np.linalg.norm(view, axis=1)
        valid = (distance < 0.006) & visible
        if np.count_nonzero(valid) < 120:
            break
        surface, normals, observed = surface[valid], normals[valid], points[valid]
        residual = np.sum(normals * (observed - surface), axis=1)
        weights = np.minimum(1.0, 0.0015 / np.maximum(abs(residual), 1e-9))
        error = float(np.sqrt(np.average(residual**2, weights=weights)) * 1000)
        if error < best_error:
            best_pose, best_error = pose.copy(), error
        A = np.c_[np.cross(surface - pose[:3, 3], normals), normals]
        delta, *_ = np.linalg.lstsq(A * np.sqrt(weights[:, None]), residual * np.sqrt(weights), rcond=None)
        delta[:3] *= min(1.0, np.deg2rad(2.0) / max(np.linalg.norm(delta[:3]), 1e-9))
        delta[3:] *= min(1.0, 0.002 / max(np.linalg.norm(delta[3:]), 1e-9))
        proposed = pose.copy()
        proposed[:3, :3] = Rotation.from_rotvec(delta[:3]).as_matrix() @ pose[:3, :3]
        proposed[:3, 3] += delta[3:]
        angle = Rotation.from_matrix(proposed[:3, :3] @ initial[:3, :3].T).magnitude()
        if angle > np.deg2rad(12.0) or np.linalg.norm(proposed[:3, 3] - initial[:3, 3]) > 0.008:
            break
        pose = proposed
        errors.append(error)
        inliers = len(residual)
        if np.linalg.norm(delta[:3]) < 1e-5 and np.linalg.norm(delta[3:]) < 1e-6:
            break
    accepted = len(errors) > 1 and best_error < errors[0]
    return (best_pose if accepted else initial.copy()), {
        "method": "robust local point-to-plane ICP on reference reconstruction and measured RGB-D",
        "accepted": accepted,
        "iterations": len(errors),
        "inliers": inliers,
        "plane_rmse_mm": best_error if errors else None,
        "initial_plane_rmse_mm": errors[0] if errors else None,
        "wall_seconds": time.perf_counter() - started,
        "object_ground_truth_used": False,
    }


def depth_region_mask(depth, K, world_T_camera, bounds, background=None):
    ys, xs = np.indices(depth.shape)
    rays = np.stack(((xs - K[0, 2]) / K[0, 0], (ys - K[1, 2]) / K[1, 1], np.ones_like(xs)), axis=-1)
    world = (rays * depth[..., None]) @ world_T_camera[:3, :3].T + world_T_camera[:3, 3]
    low, high = np.asarray(bounds)
    mask = (np.isfinite(depth) & (depth > 0.02) & np.all((world >= low) & (world <= high), axis=-1)).astype(
        np.uint8
    ) * 255
    if background is not None:
        mask[depth >= background - 0.0015] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        raise ObservationUnavailable("No observed RGB-D foreground in pickup station")
    chosen = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    mask = (labels == chosen).astype(np.uint8) * 255
    if np.count_nonzero(mask) < 40:
        raise ObservationUnavailable("Too few foreground pixels for tool registration")
    return mask


class WorkshopObserver(ImageObserver):
    def __init__(self, model, output, calibration, background_depth=None, fixture_T_marker=WORKSHOP_T_MARKER):
        super().__init__(model, output, calibration)
        self.fixture_T_marker = fixture_T_marker
        self.background_depth = background_depth

    def capture(self, data, *, camera=CAMERA_NAME, object_id="rack", region=None, prior=None, vertices=None):
        self.count += 1
        folder = self.output / f"{self.count:05d}_{camera}_{object_id}"
        folder.mkdir()
        self.renderer.update_scene(data, camera=camera)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
        rgb = self.renderer.render().copy()
        self.renderer.enable_depth_rendering()
        try:
            depth = self.renderer.render().astype(np.float32)
        finally:
            self.renderer.disable_depth_rendering()
        K, extrinsic, kind = self.camera_calibration(data, camera)
        method = "rack RGB-D marker observation"
        if object_id == "rack":
            mask = np.zeros(depth.shape, dtype=np.uint8)
        elif prior is None:
            mask = depth_region_mask(
                depth, K, extrinsic, PICK_REGIONS[region or object_id], self.background_depth
            )
            method = "empty-station RGB-D background subtraction within surveyed pickup region"
        else:
            # Held-tool tracking uses an uncertainty-expanded region from the
            # previous visual estimate and FK, not a simulator object pose.
            cloud = np.asarray(vertices) @ prior[:3, :3].T + prior[:3, 3]
            bounds = np.array([cloud.min(axis=0) - 0.009, cloud.max(axis=0) + 0.009])
            mask = depth_region_mask(depth, K, extrinsic, bounds)
            method = "observed depth inside previous visual/kinematic tool region"
        cv2.imwrite(str(folder / "rgb.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(folder / "mask.png"), mask)
        np.save(folder / "depth.npy", depth)
        overlay = rgb.copy()
        overlay[mask > 0] = (
            overlay[mask > 0].astype(float) * 0.65 + np.array([0.0, 220.0, 170.0]) * 0.35
        ).astype(np.uint8)
        cv2.imwrite(str(folder / "mask_overlay.png"), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
        metadata = {
            "capture_time_s": float(data.time),
            "camera": camera,
            "object_id": object_id,
            "K": K.tolist(),
            "world_T_camera": extrinsic.tolist(),
            "calibration": kind,
            "foreground_pixels": int(np.count_nonzero(mask)),
            "segmentation": method,
            "simulation_segmentation_ids_used": False,
            "object_pose_ground_truth_input": False,
        }
        (folder / "capture.json").write_text(json.dumps(metadata, indent=2) + "\n")
        return {
            "frame": {"rgb": folder / "rgb.png", "depth": folder / "depth.npy", "mask": folder / "mask.png"},
            "rgb": rgb,
            "depth": depth,
            "mask": mask,
            "K": K,
            "world_T_camera": extrinsic,
            "capture_time_s": float(data.time),
            "metadata": metadata,
            "folder": folder,
        }
