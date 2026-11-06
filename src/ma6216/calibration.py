"""Image-based calibration. Estimators never receive simulator camera truth.

Follows the supplied MA6216 Week 4 demo: detected checker corners ->
calibrateCamera -> solvePnP. A magenta physical mark disambiguates indexing.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .scene import BOARD_COLS, BOARD_ROWS, board_points


def detect_checker(bgr):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCornersSB(gray, (BOARD_COLS, BOARD_ROWS),
                                              flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
    if not found:
        return None
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (135, 100, 70), (175, 255, 255))
    n, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return None
    marker = centers[1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])]
    grid = corners.reshape(BOARD_ROWS, BOARD_COLS, 2)
    # Image row direction need not equal the surveyed target +Y direction.
    # Use the observed origin marker to resolve both row and column flips.
    choices = [(False,False),(False,True),(True,False),(True,True)]
    flip_row,flip_col = min(choices,key=lambda f: np.linalg.norm(grid[-1 if f[0] else 0,-1 if f[1] else 0]-marker))
    if flip_row: grid = grid[::-1]
    if flip_col: grid = grid[:,::-1]
    points = grid.reshape(-1,2).copy()
    return points.astype(np.float32)


def transform_points(T, points):
    return np.asarray(points) @ np.asarray(T)[:3,:3].T + np.asarray(T)[:3,3]


def estimate_calibration(data_dir, output_dir):
    """Only RGB images and surveyed board coordinates enter this function."""
    data_dir, output_dir = Path(data_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    survey = json.loads((data_dir / "survey.json").read_text())
    detected = []
    for frame in survey["frames"]:
        bgr = cv2.imread(str(data_dir / frame["image"]))
        points = detect_checker(bgr)
        frame = dict(frame, detected=points is not None)
        if points is not None:
            frame["corners"] = points.tolist()
            vis = bgr.copy()
            cv2.drawChessboardCorners(vis, (BOARD_COLS, BOARD_ROWS), points.reshape(-1,1,2), True)
            cv2.circle(vis, tuple(np.rint(points[0]).astype(int)), 7, (0,0,255), 2)
            cv2.imwrite(str(output_dir / (Path(frame["image"]).stem + "_corners.png")), vis)
        detected.append(frame)
    (output_dir / "detected_corners.json").write_text(json.dumps(detected, indent=2))
    intr = [f for f in detected if f["split"] == "intrinsic_train" and f["detected"]]
    if len(intr) < 12:
        raise RuntimeError(f"Only {len(intr)} intrinsic training views detected, need 12")
    planar = board_points().copy()
    planar[:,2] = 0  # board-face coordinates, same dimensions; pose absorbs .001m offset
    flags = cv2.CALIB_ZERO_TANGENT_DIST | cv2.CALIB_FIX_K1 | cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3
    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        [planar] * len(intr), [np.asarray(f["corners"],np.float32) for f in intr],
        tuple(survey["image_size"]), None, None, flags=flags)
    np.savetxt(output_dir / "cam_K.txt", K)
    np.savetxt(output_dir / "distortion.txt", dist)
    ext = [f for f in detected if f["split"] == "extrinsic_train" and f["detected"]]
    if len(ext) < 3:
        raise RuntimeError("Need at least 3 independent surveyed extrinsic target placements")
    world_points = np.concatenate([transform_points(f["world_T_board"], board_points()) for f in ext]).astype(np.float64)
    image_points = np.concatenate([np.asarray(f["corners"], np.float64) for f in ext])
    ok, rv, tv = cv2.solvePnP(world_points, image_points, K, dist, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise RuntimeError("Extrinsic solvePnP failed")
    camera_T_world = np.eye(4)
    camera_T_world[:3,:3] = cv2.Rodrigues(rv)[0]
    camera_T_world[:3,3] = tv.ravel()
    world_T_camera = np.linalg.inv(camera_T_world)
    np.savetxt(output_dir / "world_T_camera.txt", world_T_camera)
    # Menagerie base body has a known fixed pi rotation about world Z, from XML.
    world_T_base_body = np.diag([-1.,-1.,1.,1.])
    np.savetxt(output_dir / "base_body_T_camera.txt", np.linalg.inv(world_T_base_body) @ world_T_camera)
    errors = []
    for f in detected:
        if not f["detected"]:
            continue
        points = np.asarray(f["corners"],np.float32)
        if f["split"].startswith("intrinsic"):
            # Held-out target pose is fitted; K is frozen, as standard intrinsic validation.
            ok, r, t = cv2.solvePnP(planar, points, K, dist)
            projected = cv2.projectPoints(planar,r,t,K,dist)[0].reshape(-1,2)
        else:
            # Extrinsic validation freezes both K and world_T_camera; no per-view re-fit.
            wp = transform_points(f["world_T_board"],board_points())
            projected = cv2.projectPoints(wp,rv,tv,K,dist)[0].reshape(-1,2)
        norms = np.linalg.norm(points-projected,axis=1)
        errors.append(dict(id=f["id"],split=f["split"],rmse_px=float(np.sqrt(np.mean(norms**2))),
                           mean_px=float(norms.mean()),max_px=float(norms.max())))
    summary = dict(status="estimated", method="RGB checker detection + calibrateCamera + surveyed world-point solvePnP",
                   camera_model="MuJoCo distortion-free pinhole; all distortion coefficients fixed to zero",
                   input_gt_camera_used=False, width=survey["image_size"][0],height=survey["image_size"][1],
                   intrinsic_train_count=len(intr),extrinsic_train_count=len(ext),
                   intrinsic_train_rms_px=float(rms),K=K.tolist(),world_T_camera=world_T_camera.tolist(),
                   coordinate_frames="world is mounting-origin planning frame; Menagerie base body is world rotated pi about Z",
                   views=errors,failed_detection_ids=[f["id"] for f in detected if not f["detected"]])
    for split in ("intrinsic_train","intrinsic_validation","extrinsic_train","extrinsic_validation"):
        vals=[f["rmse_px"] for f in errors if f["split"]==split]
        summary[split] = dict(count=len(vals),mean_rmse_px=float(np.mean(vals)) if vals else None,
                              max_rmse_px=float(np.max(vals)) if vals else None)
    (output_dir / "calibration.json").write_text(json.dumps(summary,indent=2))
    return summary
