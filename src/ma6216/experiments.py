"""Explicit module ablations and reproducible environmental interventions.

No method sees simulator object truth. The disturbance engine may actuate
the environment but does not transmit its displacement to the controller.
"""

import numpy as np
from scipy.spatial.transform import Rotation

METHODS = ("full", "no_wrist", "yaw_only", "no_prediction", "no_recovery")


def control_pose(pose, method):
    pose = np.asarray(pose).copy()
    if method == "yaw_only":
        yaw = np.arctan2(pose[1, 0], pose[0, 0])
        pose[:3, :3] = Rotation.from_euler("z", yaw).as_matrix()
    return pose


class GraspImpulse:
    """Same timed force/torque pulse for both members of a paired trial."""

    def __init__(self, robot, target):
        self.robot, self.target = robot, target
        self.started = None
        self.finished = False
        self.duration = 0.12
        self.wrench = np.array([1.5, 0.0, 0.0, 0.0, 0.03, 0.0])

    def __call__(self, stage):
        if self.finished:
            return
        r = self.robot
        if self.started is None:
            if r.target.object_id != self.target or stage != "LIFT_SETTLE":
                return
            self.started = float(r.data.time)
            r.event(
                "external_grasp_impulse_started",
                object_id=self.target,
                world_wrench=self.wrench.tolist(),
                duration_s=self.duration,
                controller_receives_object_pose=False,
            )
        bid = r.model.body(r.objects[self.target].body).id
        if r.data.time - self.started < self.duration:
            r.data.xfrc_applied[bid] = self.wrench
        else:
            r.data.xfrc_applied[bid] = 0.0
            self.finished = True
            r.event("external_grasp_impulse_finished", object_id=self.target)
