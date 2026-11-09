"""Estimate wrist intrinsics and hand-eye from pixels and robot FK only.

G_i X C_i = Y: G is world_T_gripper, C is camera_T_board from PnP,
X is the unknown gripper_T_camera and Y the unknown stationary board pose.
No simulator camera parameters or surveyed board world pose enter estimation.
"""
import hashlib
import json
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .calibration import detect_checker
from .scene import board_points, BOARD_COLS, BOARD_ROWS, SQUARE


def detect_wrist_checker(bgr):
    """Reject partial-board false matches using its observed origin marker.

    A shifted chess lattice can fit PnP very well. Verify its known marker-to-
    grid relationship in the IMAGE using a planar homography before calibration.
    """
    points = detect_checker(bgr)
    if points is None:
        return None, {"accepted": False, "reason": "checker or origin marker not detected"}
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (135, 100, 70), (175, 255, 255))
    _, _, stats, centres = cv2.connectedComponentsWithStats(mask)
    observed_marker = centres[1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])]
    board_xy = board_points()[:, :2].astype(float)
    H, _ = cv2.findHomography(board_xy, points, 0)
    if H is None:
        return None, {"accepted": False, "reason": "singular board homography"}
    def map_points(xy):
        h = np.c_[xy, np.ones(len(xy))] @ H.T
        return h[:, :2] / h[:, 2:]
    marker_xy = [[-(BOARD_COLS + 1) * SQUARE / 2 - .012,
                  -(BOARD_ROWS + 1) * SQUARE / 2 - .012]]
    marker_error = float(np.linalg.norm(map_points(marker_xy)[0] - observed_marker))
    grid_rmse = float(np.sqrt(np.mean(np.sum((map_points(board_xy) - points) ** 2, axis=1))))
    accepted = marker_error <= 3. and grid_rmse <= .25
    return (points if accepted else None), {"accepted": accepted, "marker_error_px": marker_error,
        "grid_homography_rmse_px": grid_rmse, "reason": "accepted" if accepted else "inconsistent marker/grid geometry"}


def pack(T):
    return np.r_[Rotation.from_matrix(T[:3, :3]).as_rotvec(), T[:3, 3]]


def unpack(v):
    T = np.eye(4)
    T[:3, :3] = Rotation.from_rotvec(v[:3]).as_matrix()
    T[:3, 3] = v[3:]
    return T


def solve_hand_eye(gripper_poses, camera_board_poses):
    """AX=XB rotation-log SVD and linear translation; reject deficient motions."""
    if len(gripper_poses) < 6 or len(gripper_poses) != len(camera_board_poses):
        raise ValueError("Hand-eye calibration needs at least six paired poses")
    pairs = [(np.linalg.inv(gripper_poses[j]) @ gripper_poses[i],
              camera_board_poses[j] @ np.linalg.inv(camera_board_poses[i]))
             for i, j in combinations(range(len(gripper_poses)), 2)]
    a = np.array([Rotation.from_matrix(A[:3, :3]).as_rotvec() for A, B in pairs])
    b = np.array([Rotation.from_matrix(B[:3, :3]).as_rotvec() for A, B in pairs])
    singular = np.linalg.svd(b, compute_uv=False)
    if singular[1] < 0.1 or singular[1] / singular[0] < 0.05:
        raise ValueError("Hand-eye motion lacks two nonparallel rotation axes")
    u, _, vt = np.linalg.svd(a.T @ b)
    R = u @ np.diag([1., 1., np.linalg.det(u @ vt)]) @ vt
    lhs = np.concatenate([A[:3, :3] - np.eye(3) for A, B in pairs])
    rhs = np.concatenate([R @ B[:3, 3] - A[:3, 3] for A, B in pairs])
    t, _, rank, _ = np.linalg.lstsq(lhs, rhs, rcond=None)
    if rank != 3:
        raise ValueError("Hand-eye translation is unobservable")
    X = np.eye(4)
    X[:3, :3], X[:3, 3] = R, t
    return X, {"rotation_excitation_singular_values": singular.tolist(), "translation_rank": int(rank)}


def project(T, points, K):
    return cv2.projectPoints(points, Rotation.from_matrix(T[:3, :3]).as_rotvec(),
                             T[:3, 3], K, np.zeros(5))[0].reshape(-1, 2)


def estimate_wrist(data_dir, output):
    data_dir, output = Path(data_dir), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest_path = data_dir / "observations.json"
    manifest = json.loads(manifest_path.read_text())
    points = board_points().astype(float)
    planar = points.copy()
    planar[:, 2] = 0.
    rows, sources = [], {"observations.json": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    for f in manifest["frames"]:
        path = data_dir / f["image"]
        sources[f["image"]] = hashlib.sha256(path.read_bytes()).hexdigest()
        im = cv2.imread(str(path))
        corners, quality = detect_wrist_checker(im)
        row = dict(f, detected=corners is not None, image_quality=quality)
        if corners is not None:
            row["corners"] = corners.tolist()
        rows.append(row)
    intrinsic = [r for r in rows if r["split"] == "intrinsic_train" and r["detected"]]
    if len(intrinsic) < 12:
        raise ValueError(f"Only {len(intrinsic)} usable intrinsic views")
    flags = cv2.CALIB_ZERO_TANGENT_DIST | cv2.CALIB_FIX_K1 | cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3
    rms, K, dist, _, _ = cv2.calibrateCamera(
        [planar.astype(np.float32)] * len(intrinsic),
        [np.array(r["corners"], np.float32) for r in intrinsic], tuple(manifest["image_size"]),
        None, None, flags=flags)
    for r in rows:
        if not r["detected"]:
            continue
        ok, rv, tv = cv2.solvePnP(points, np.array(r["corners"]), K, dist)
        if not ok:
            raise ValueError("PnP failed for " + r["id"])
        C = unpack(np.r_[rv.ravel(), tv.ravel()])
        r["camera_T_board"] = C.tolist()
        r["pnp_reprojection_rmse_px"] = float(np.sqrt(np.mean(np.sum(
            (project(C, points, K) - np.array(r["corners"])) ** 2, axis=1))))
    train = [r for r in rows if r["split"] == "hand_eye_train" and r["detected"]]
    G = [np.array(r["world_T_gripper"]) for r in train]
    C = [np.array(r["camera_T_board"]) for r in train]
    X, excitation = solve_hand_eye(G, C)
    ys = [g @ X @ c for g, c in zip(G, C)]
    Y = np.eye(4)
    Y[:3, :3] = Rotation.from_matrix(np.array([y[:3, :3] for y in ys])).mean().as_matrix()
    Y[:3, 3] = np.mean([y[:3, 3] for y in ys], axis=0)
    initial_X = X.copy()
    def residual(v):
        x, y = unpack(v[:6]), unpack(v[6:])
        return np.concatenate([(project(np.linalg.inv(g @ x) @ y, points, K)
                                - np.array(r["corners"])).ravel() for g, r in zip(G, train)])
    fit = least_squares(residual, np.r_[pack(X), pack(Y)], max_nfev=200,
                        xtol=1e-12, ftol=1e-12, gtol=1e-12)
    if not fit.success:
        raise ValueError("Hand-eye reprojection refinement did not converge")
    X, Y = unpack(fit.x[:6]), unpack(fit.x[6:])
    for r in rows:
        if not r["detected"]:
            continue
        # K, X, Y are frozen. No validation-frame pose is fitted for this metric.
        predicted = np.linalg.inv(np.array(r["world_T_gripper"]) @ X) @ Y
        r["frozen_chain_reprojection_rmse_px"] = float(np.sqrt(np.mean(np.sum(
            (project(predicted, points, K) - np.array(r["corners"])) ** 2, axis=1))))
    splits = {}
    for split in ["intrinsic_train", "intrinsic_validation", "hand_eye_train", "hand_eye_validation"]:
        rr = [r for r in rows if r["split"] == split]
        detected = [r for r in rr if r["detected"]]
        if len(detected) < (6 if split.startswith("hand_eye") else 4):
            raise ValueError("Insufficient independent views in " + split)
        metric = "frozen_chain_reprojection_rmse_px" if split.startswith("hand_eye") else "pnp_reprojection_rmse_px"
        splits[split] = {"attempted": len(rr), "detected": len(detected), "metric": metric,
                         "mean_rmse_px": float(np.mean([r[metric] for r in detected])),
                         "max_rmse_px": float(max(r[metric] for r in detected))}
    result = {"status": "estimated", "camera": "wrist_camera", "gripper_body": "gripper_base",
              "image_size": manifest["image_size"], "input_gt_camera_used": False,
              "method": "checkerboard calibrateCamera; PnP; AX=XB log-SVD; train-only joint X/Y reprojection refinement",
              "distortion_model": "known distortion-free pinhole; coefficients fixed to zero",
              "image_quality_gate": "origin marker homography error <=3 px; grid homography RMSE <=0.25 px; independent of FK and simulator truth",
              "K": K.tolist(), "gripper_T_camera": X.tolist(), "world_T_board_estimated": Y.tolist(),
              "initial_AX_XB_gripper_T_camera": initial_X.tolist(), "intrinsic_rms_px": rms,
              "motion_excitation": excitation, "splits": splits,
              "failed_detection_ids": [r["id"] for r in rows if not r["detected"]],
              "source_sha256": sources, "views": rows}
    np.savetxt(output / "cam_K.txt", K)
    np.savetxt(output / "distortion.txt", dist)
    np.savetxt(output / "gripper_T_camera.txt", X)
    (output / "calibration.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
