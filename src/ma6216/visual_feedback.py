"""Bounded SE(3) visual feedback; accepts visual poses and robot FK only.

Simulation truth, mesh geometry and acceptance tests are deliberately absent
from this controller. The caller retains collision, grasp and force guards.
"""

from dataclasses import asdict, dataclass

import numpy as np
from scipy.spatial.transform import Rotation


FEEDBACK_MODES = ("legacy", "open_loop", "staged", "iterative")


@dataclass(frozen=True)
class ServoSettings:
    gain: float = 0.65
    translation_step_m: float = 0.004
    rotation_step_deg: float = 2.0
    translation_tolerance_m: float = 0.0015
    rotation_tolerance_deg: float = 1.5
    maximum_translation_error_m: float = 0.025
    maximum_rotation_error_deg: float = 15.0
    maximum_corrections: int = 8
    required_consecutive_observations: int = 2

    def as_dict(self):
        return asdict(self)


def checked_pose(value):
    pose = np.asarray(value, dtype=float)
    if (pose.shape != (4, 4) or not np.isfinite(pose).all()
            or not np.allclose(pose[3], [0, 0, 0, 1])
            or not np.allclose(pose[:3, :3].T @ pose[:3, :3], np.eye(3), atol=1e-4)
            or not np.isclose(np.linalg.det(pose[:3, :3]), 1.0, atol=1e-4)):
        raise ValueError("Visual feedback requires finite rigid SE(3) poses")
    return pose


def bounded_command(tcp, measured_object, desired_object, settings=ServoSettings()):
    """Return a collision-plannable TCP step and visual residual diagnostics.

    Translation and rotation are separately bounded at the TCP. A full
    six-dimensional error is used, including roll/pitch. Large visual jumps
    are rejected rather than silently replaced by a simulated object pose.
    """
    tcp, measured, desired = map(checked_pose, (tcp, measured_object, desired_object))
    translation = float(np.linalg.norm(desired[:3, 3] - measured[:3, 3]))
    rotation = float(np.rad2deg(Rotation.from_matrix(desired[:3, :3] @ measured[:3, :3].T).magnitude()))
    if translation > settings.maximum_translation_error_m or rotation > settings.maximum_rotation_error_deg:
        raise ValueError(f"Visual pose outside correction envelope: {translation * 1000:.2f} mm, {rotation:.2f} deg")
    converged = (translation <= settings.translation_tolerance_m
                 and rotation <= settings.rotation_tolerance_deg)
    object_in_tool = np.linalg.inv(tcp) @ measured
    target = desired @ np.linalg.inv(object_in_tool)
    offset = (target[:3, 3] - tcp[:3, 3]) * settings.gain
    offset *= min(1.0, settings.translation_step_m / max(np.linalg.norm(offset), 1e-12))
    rotvec = Rotation.from_matrix(target[:3, :3] @ tcp[:3, :3].T).as_rotvec() * settings.gain
    rotvec *= min(1.0, np.deg2rad(settings.rotation_step_deg) / max(np.linalg.norm(rotvec), 1e-12))
    command = tcp.copy()
    command[:3, 3] += offset
    command[:3, :3] = Rotation.from_rotvec(rotvec).as_matrix() @ tcp[:3, :3]
    return command, {
        "translation_error_mm": translation * 1000,
        "rotation_error_deg": rotation,
        "within_tolerance": bool(converged),
        "command_translation_mm": float(np.linalg.norm(offset) * 1000),
        "command_rotation_deg": float(np.rad2deg(np.linalg.norm(rotvec))),
    }


def stationary_target_update(previous, candidate, depth_refinement):
    """Reject occlusion-induced drift of a released, stationary support.

    A support is never moved by this function. Fresh visual geometry must
    agree with both the observed depth surface and its last accepted pose.
    """
    previous, candidate = map(checked_pose, (previous, candidate))
    displacement = float(np.linalg.norm(candidate[:3, 3] - previous[:3, 3]))
    angle = float(np.rad2deg(Rotation.from_matrix(candidate[:3, :3] @ previous[:3, :3].T).magnitude()))
    plane_error = depth_refinement.get("plane_rmse_mm")
    accepted = bool(depth_refinement.get("accepted")
                    and depth_refinement.get("inliers", 0) >= 120
                    and plane_error is not None and plane_error <= 1.5
                    and displacement <= 0.008 and angle <= 5.0)
    return accepted, {"accepted": accepted, "translation_jump_mm": displacement * 1000,
                      "rotation_jump_deg": angle, "plane_rmse_mm": plane_error,
                      "policy": "valid depth alignment and stationary support continuity"}
