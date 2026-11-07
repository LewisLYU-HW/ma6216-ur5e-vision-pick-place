"""Image-only task perception and surveyed marker coordinates.

The wrist camera uses a declared ideal synthetic hand-eye calibration. Robot
forward kinematics provides camera motion; object body poses are never read.
"""
import json
from pathlib import Path

import cv2
import numpy as np

from .advanced_scene import FIXTURE_T_MARKER, MARKER_ID, MARKER_SIZE, WRIST_CAMERA
from .pose_insertion import transform
from .scene import CAMERA_NAME, HEIGHT, WIDTH, mujoco

COLOR_RANGES = {"plug": ((46, 75, 38), (95, 255, 255)),
                "blocker": ((5, 100, 50), (29, 255, 255))}


def foreground(rgb, name):
    low, high = COLOR_RANGES[name]
    mask = cv2.inRange(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV), low, high)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        return np.zeros(rgb.shape[:2], dtype=np.uint8)
    index = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    return (labels == index).astype(np.uint8) * 255


class ImageObserver:
    def __init__(self, model, output, calibration):
        self.model = model
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)
        calibration = Path(calibration)
        self.fixed_K = np.loadtxt(calibration / "cam_K.txt")
        self.fixed_extrinsic = np.loadtxt(calibration / "world_T_camera.txt")
        self.count = 0
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        parameters = cv2.aruco.DetectorParameters()
        parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector = cv2.aruco.ArucoDetector(dictionary, parameters)

    def camera_calibration(self, data, camera):
        if camera == CAMERA_NAME:
            return self.fixed_K.copy(), self.fixed_extrinsic.copy(), "estimated checkerboard calibration"
        if camera != WRIST_CAMERA:
            raise ValueError("Unknown task camera")
        cid = self.model.camera(camera).id
        bid = self.model.cam_bodyid[cid]
        rotation = np.empty(9)
        mujoco.mju_quat2Mat(rotation, self.model.cam_quat[cid])
        body_T_camera = transform(self.model.cam_pos[cid], rotation.reshape(3, 3) @ np.diag([1., -1., -1.]))
        world_T_body = transform(data.xpos[bid], data.xmat[bid].reshape(3, 3))
        focal = .5 * HEIGHT / np.tan(np.deg2rad(self.model.cam_fovy[cid]) / 2)
        K = np.array([[focal, 0., (WIDTH - 1) / 2], [0., focal, (HEIGHT - 1) / 2], [0., 0., 1.]])
        return K, world_T_body @ body_T_camera, "ideal synthetic intrinsics/hand-eye mount plus robot forward kinematics"

    def capture(self, data, *, camera=CAMERA_NAME, object_id="plug"):
        self.count += 1
        folder = self.output / f"{self.count:05d}_{camera}_{object_id}"
        folder.mkdir()
        self.renderer.update_scene(data, camera=camera)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
        rgb = self.renderer.render().copy()
        mask = foreground(rgb, object_id)
        self.renderer.enable_depth_rendering()
        try:
            depth = self.renderer.render().astype(np.float32)
        finally:
            self.renderer.disable_depth_rendering()
        cv2.imwrite(str(folder / "rgb.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(folder / "mask.png"), mask)
        np.save(folder / "depth.npy", depth)
        K, extrinsic, calibration_kind = self.camera_calibration(data, camera)
        metadata = {"capture_time_s": float(data.time), "camera": camera, "K": K.tolist(),
                    "world_T_camera": extrinsic.tolist(), "calibration": calibration_kind,
                    "foreground_pixels": int(np.count_nonzero(mask)), "object_id": object_id}
        (folder / "capture.json").write_text(json.dumps(metadata, indent=2) + "\n")
        return {"frame": {"rgb": folder / "rgb.png", "depth": folder / "depth.npy", "mask": folder / "mask.png"},
                "rgb": rgb, "depth": depth, "mask": mask, "K": K, "world_T_camera": extrinsic,
                "capture_time_s": float(data.time), "metadata": metadata, "folder": folder}

    def fixture_pose(self, capture):
        corners, ids, _ = self.detector.detectMarkers(capture["rgb"])
        if ids is None or MARKER_ID not in ids.ravel():
            raise RuntimeError("Assembly marker is not visible in the selected camera")
        index = list(ids.ravel()).index(MARKER_ID)
        pixels = corners[index].reshape(4, 2).astype(np.float64)
        half = MARKER_SIZE / 2
        points = np.array([[-half, half, 0.], [half, half, 0.],
                           [half, -half, 0.], [-half, -half, 0.]])
        ok, rvec, tvec = cv2.solvePnP(points, pixels, capture["K"], np.zeros(5), flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if not ok:
            raise RuntimeError("Marker pose estimation failed")
        rvec, tvec = cv2.solvePnPRefineLM(points, pixels, capture["K"], np.zeros(5), rvec, tvec)
        reprojection, _ = cv2.projectPoints(points, rvec, tvec, capture["K"], np.zeros(5))
        error = float(np.sqrt(np.mean((reprojection.reshape(4, 2) - pixels) ** 2)))
        if error > 1.5 or tvec[2, 0] <= 0:
            raise RuntimeError(f"Marker reprojection failed: {error:.3f} pixels")
        # Small far-field markers have a weak monocular depth constraint.
        # Fit the observed depth plane, intersect the corner rays with it,
        # and align the surveyed square to those RGB-D points without scale.
        region = np.zeros(capture["depth"].shape, dtype=np.uint8)
        cv2.fillConvexPoly(region, np.rint(pixels).astype(np.int32), 255)
        region = cv2.erode(region, np.ones((5, 5), dtype=np.uint8))
        ys, xs = np.where((region > 0) & np.isfinite(capture["depth"]) & (capture["depth"] > .05))
        if len(xs) < 40:
            raise RuntimeError("Not enough marker depth samples for a plane estimate")
        inverse_K = np.linalg.inv(capture["K"])
        rays = np.c_[xs, ys, np.ones(len(xs))] @ inverse_K.T
        cloud = rays * capture["depth"][ys, xs, None]
        centre = np.median(cloud, axis=0)
        _, _, vt = np.linalg.svd(cloud - centre, full_matrices=False)
        normal = vt[-1]
        plane_rmse = float(np.sqrt(np.mean(((cloud - centre) @ normal) ** 2)))
        if plane_rmse > .002:
            raise RuntimeError("Marker region is not a valid observed depth plane")
        corner_rays = np.c_[pixels, np.ones(4)] @ inverse_K.T
        corner_xyz = corner_rays * ((normal @ centre) / (corner_rays @ normal))[:, None]
        u, _, vt = np.linalg.svd(points.T @ (corner_xyz - corner_xyz.mean(axis=0)))
        rotation = vt.T @ u.T
        if np.linalg.det(rotation) < 0:
            vt[-1] *= -1
            rotation = vt.T @ u.T
        camera_T_marker = transform(corner_xyz.mean(axis=0), rotation)
        pose = capture["world_T_camera"] @ camera_T_marker @ np.linalg.inv(FIXTURE_T_MARKER)
        evidence = {"method": "ArUco corners + observed RGB-D plane + metric rigid alignment; surveyed marker mount",
                    "initial_pnp_reprojection_rmse_px": error, "depth_plane_rmse_mm": plane_rmse * 1000,
                    "world_T_fixture": pose.tolist(),
                    "capture_time_s": capture["capture_time_s"], "camera": capture["metadata"]["camera"]}
        (capture["folder"] / "fixture_estimate.json").write_text(json.dumps(evidence, indent=2) + "\n")
        return pose, evidence

    def close(self):
        self.renderer.close()
