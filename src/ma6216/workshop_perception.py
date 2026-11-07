"""Texture-independent RGB-D segmentation and reconstructed tool features.

Pickup stations supply broad 3D search regions. All foreground pixels and
object poses come from sensor images; simulator IDs/poses are not used here.
"""

import json

import cv2
import numpy as np

from .scene import CAMERA_NAME, mujoco
from .task_perception import ImageObserver
from .workshop_scene import PICK_REGIONS, WORKSHOP_T_MARKER


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
        raise RuntimeError("No observed RGB-D foreground in pickup station")
    chosen = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    mask = (labels == chosen).astype(np.uint8) * 255
    if np.count_nonzero(mask) < 40:
        raise RuntimeError("Too few foreground pixels for tool registration")
    return mask


class WorkshopObserver(ImageObserver):
    def __init__(self, model, output, calibration, background_depth=None):
        super().__init__(model, output, calibration)
        self.fixture_T_marker = WORKSHOP_T_MARKER
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
