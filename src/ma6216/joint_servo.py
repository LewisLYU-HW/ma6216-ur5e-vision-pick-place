"""Velocity feedforward for the workcell's affine position actuators."""

import numpy as np

from .motion import MotionFailure
from .scene import mujoco


def position_velocity_command(model, actuator_ids, reference, velocity):
    """Cancel the known actuator damping without changing motor gains or limits.

    For tau = kp * (u - q) - kv * qdot, use u = q_ref + kv/kp * qdot_ref.
    The collision-checked path and evaluation reference remain q_ref.
    """
    ids = np.asarray(actuator_ids, dtype=int)
    kp = model.actuator_gainprm[ids, 0]
    bias = model.actuator_biasprm[ids]
    if (
        np.any(kp <= 0)
        or not np.allclose(bias[:, 1], -kp)
        or np.any(bias[:, 2] > 0)
        or not np.allclose(model.actuator_gear[ids, 0], 1.0)
        or np.any(model.actuator_gaintype[ids] != mujoco.mjtGain.mjGAIN_FIXED)
        or np.any(model.actuator_biastype[ids] != mujoco.mjtBias.mjBIAS_AFFINE)
        or np.any(model.actuator_dyntype[ids] != mujoco.mjtDyn.mjDYN_NONE)
        or np.any(model.actuator_trntype[ids] != mujoco.mjtTrn.mjTRN_JOINT)
    ):
        raise MotionFailure("Velocity feedforward requires unit-gear affine position actuators")
    command = np.asarray(reference) - bias[:, 2] / kp * np.asarray(velocity)
    limits = model.actuator_ctrlrange[ids]
    limited = model.actuator_ctrllimited[ids].astype(bool)
    if not np.isfinite(command).all() or np.any(
        limited & ((command < limits[:, 0]) | (command > limits[:, 1]))
    ):
        raise MotionFailure("Velocity feedforward command exceeds the actuator range")
    return command
