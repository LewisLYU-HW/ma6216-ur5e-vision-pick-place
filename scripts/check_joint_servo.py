"""Physical tracking regressions for the damped position-servo command."""

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ma6216.scene import mujoco
from ma6216.joint_servo import position_velocity_command
from ma6216.motion import MotionFailure


class ServoTracking(unittest.TestCase):
    def setUp(self):
        self.model = mujoco.MjModel.from_xml_string(
            """<mujoco><option timestep="0.002" integrator="implicitfast" gravity="0 0 0"/>
            <worldbody><body><joint name="hinge" type="hinge" axis="0 0 1"/>
            <geom type="capsule" fromto="0 0 0 0.15 0 0" size="0.01" mass="0.1"/>
            </body></worldbody><actuator><general joint="hinge" gaintype="fixed"
            biastype="affine" gainprm="100" biasprm="0 -100 -20"
            ctrllimited="true" ctrlrange="-1 1"/></actuator></mujoco>"""
        )

    def test_feedforward_tracks_a_moving_reference_without_changing_the_motor(self):
        errors = []
        original_gain = self.model.actuator_gainprm.copy()
        original_bias = self.model.actuator_biasprm.copy()
        for enabled in (False, True):
            data = mujoco.MjData(self.model)
            trajectory_errors = []
            for step in range(1000):
                reference = np.array([0.15 * data.time])
                command = (
                    position_velocity_command(self.model, [0], reference, [0.15]) if enabled else reference
                )
                data.ctrl[:] = command
                mujoco.mj_step(self.model, data)
                if step >= 500:
                    trajectory_errors.append(abs(data.qpos[0] - 0.15 * data.time))
            errors.append(float(np.mean(trajectory_errors)))
        self.assertGreater(errors[0], 0.02)
        self.assertLess(errors[1], 0.001)
        np.testing.assert_array_equal(self.model.actuator_gainprm, original_gain)
        np.testing.assert_array_equal(self.model.actuator_biasprm, original_bias)

    def test_unsupported_or_out_of_range_commands_are_rejected(self):
        with self.assertRaisesRegex(MotionFailure, "actuator range"):
            position_velocity_command(self.model, [0], [0.95], [1.0])
        self.model.actuator_biasprm[0, 1] = -50
        with self.assertRaisesRegex(MotionFailure, "affine position"):
            position_velocity_command(self.model, [0], [0.0], [0.1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
