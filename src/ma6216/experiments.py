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


class AlignmentImpulse:
    """Identical force/torque pulse after nominal alignment, before feedback.

    One intervention per applicable tool, including all three in a complete
    run. Does not change qpos or disclose the resulting displacement.
    """

    stages = {
        "screwdriver": "ALIGN_DRIVER_SETTLE",
        "rack_frame": "ALIGN_RACK_FRAME_SETTLE",
        "spanner": "REORIENT_AND_APPROACH_RACK_SETTLE",
    }

    def __init__(self, robot):
        self.robot = robot
        self.delivered = set()
        self.active = None
        self.duration = 0.12
        self.wrench = np.array([1.5, 0.0, 0.0, 0.0, 0.03, 0.0])

    def __call__(self, stage):
        r = self.robot
        target = r.target.object_id
        if self.active is None and target not in self.delivered and stage == self.stages.get(target):
            self.active = (target, float(r.data.time))
            self.delivered.add(target)
            r.event("external_alignment_impulse_started", object_id=target,
                    world_wrench=self.wrench.tolist(), duration_s=self.duration,
                    controller_receives_object_pose=False)
        if self.active is None:
            return
        target, started = self.active
        bid = r.model.body(r.objects[target].body).id
        if r.data.time - started < self.duration:
            r.data.xfrc_applied[bid] = self.wrench
        else:
            r.data.xfrc_applied[bid] = 0.0
            r.event("external_alignment_impulse_finished", object_id=target)
            self.active = None
