"""Regression checks for reconstructed holes and physical tool-rack outcomes."""

import hashlib
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.advanced_scene import set_initial_pose
from ma6216.pose_insertion import transform
from ma6216.reconstructed import validate_bundle
from ma6216.scene import mujoco
from ma6216.task_control import TaskRobot
from ma6216.motion import MotionFailure
from ma6216.workshop_assets import TOOLS
from ma6216.workshop_control import FeedPoseHistory, ReconstructedTool
from ma6216.workshop_scene import (
    build_workshop_scene,
    RACK_POSE,
    HOOK_CENTRE,
    SPANNER_HANG_ROTATION,
)
from run_workshop import physical_evaluation


class WorkshopGeometry(unittest.TestCase):
    def test_feed_prediction_does_not_extrapolate_off_rail_depth_noise(self):
        history = FeedPoseHistory()
        for t, x, z in ((0.0, 0.390, 0.428), (1.0, 0.391, 0.429), (2.0, 0.392, 0.427)):
            history.add(t, transform([x, -0.245 + 0.003 * t, z]))
        predicted = history.predict(12.0)
        np.testing.assert_allclose(predicted[:3, 3], [0.392, -0.209, 0.427], atol=1e-10)
        np.testing.assert_allclose(history.velocity, [0.0, 0.003, 0.0], atol=1e-10)
        self.assertGreater(abs(history.unconstrained_velocity[2]), 0.0001)

    def test_reference_provenance(self):
        for name in TOOLS:
            bundle = ROOT / "assets/reconstructed/workshop" / name
            manifest, _ = validate_bundle(bundle)
            refs = bundle / "reference_capture.json"
            self.assertEqual(
                hashlib.sha256(refs.read_bytes()).hexdigest(), manifest["reference_manifest_sha256"]
            )
            self.assertEqual(
                json.loads(refs.read_text())["foreground_method"], "isolated scanner depth threshold"
            )

    def test_reconstructed_eye_has_empty_centre_and_solid_rim(self):
        tool = ReconstructedTool(ROOT / "assets/reconstructed/workshop/spanner")
        spec = mujoco.MjSpec()
        spec.option.gravity = [0.0, 0.0, 0.0]
        tool.configure(spec)
        probe_body = spec.worldbody.add_body(name="probe_body", mocap=True, pos=tool.eye)
        probe_body.add_geom(name="probe", type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[0.004, 0.025, 0.0])
        m = spec.compile()
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        probe = m.geom("probe").id
        self.assertFalse(any(probe in (c.geom1, c.geom2) and c.dist < 0 for c in d.contact))
        d.mocap_pos[0, 1] += 0.020
        mujoco.mj_forward(m, d)
        self.assertTrue(any(probe in (c.geom1, c.geom2) and c.dist < 0 for c in d.contact))

    def test_disabled_contact_pipeline_is_rejected_before_planning(self):
        for flag in (mujoco.mjtDisableBit.mjDSBL_CONSTRAINT, mujoco.mjtDisableBit.mjDSBL_CONTACT):
            spec = mujoco.MjSpec()
            spec.option.disableflags = int(flag)
            fake = SimpleNamespace(planning_scene=SimpleNamespace(model=spec.compile()))
            with self.assertRaisesRegex(MotionFailure, "remain enabled"):
                TaskRobot.prepare_planner(fake)


class RackAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = build_workshop_scene()

    def reset_pose(self, name, pose):
        m, d = self.scene.model, self.scene.data
        d.qvel[:] = 0.0
        set_initial_pose(m, d, TOOLS[name], pose)
        mujoco.mj_forward(m, d)

    def test_floating_eye_is_not_success(self):
        centre = (RACK_POSE @ np.r_[HOOK_CENTRE + [0.0, 0.025, 0.0], 1.0])[:3]
        rotation = RACK_POSE[:3, :3] @ SPANNER_HANG_ROTATION
        self.reset_pose("spanner", transform(centre - rotation @ [-0.060, 0.0, 0.0], rotation))
        self.assertFalse(physical_evaluation(self.scene, "spanner")["success"])

    def test_ring_can_rest_physically_on_peg(self):
        centre = (RACK_POSE @ np.r_[HOOK_CENTRE + [0.0, 0.025, -0.009], 1.0])[:3]
        rotation = RACK_POSE[:3, :3] @ SPANNER_HANG_ROTATION
        self.reset_pose("spanner", transform(centre - rotation @ [-0.060, 0.0, 0.0], rotation))
        for _ in range(2500):
            mujoco.mj_step(self.scene.model, self.scene.data)
        result = physical_evaluation(self.scene, "spanner")
        self.assertTrue(result["success"], result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
