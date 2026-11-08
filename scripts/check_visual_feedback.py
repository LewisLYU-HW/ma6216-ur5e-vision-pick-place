"""Check closed-loop convergence, frame invariance and disturbance isolation."""

from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.visual_feedback import ServoSettings, bounded_command, stationary_target_update
from ma6216.experiments import AlignmentImpulse
from ma6216.pose_insertion import transform
from run_benchmark import archive_observations
from summarize_benchmark import summarize


class VisualFeedback(unittest.TestCase):
    def test_recovers_translation_and_roll_pitch_with_bounded_steps(self):
        settings = ServoSettings()
        tcp = transform([0.45, 0.1, 0.55])
        grip = transform([0.04, 0.01, -0.03], Rotation.from_euler("xyz", [3, -4, 2], degrees=True).as_matrix())
        goal = transform([0.48, 0.12, 0.52])
        for _ in range(20):
            command, error = bounded_command(tcp, tcp @ grip, goal, settings)
            self.assertLessEqual(error["command_translation_mm"], 4.0 + 1e-8)
            self.assertLessEqual(error["command_rotation_deg"], 2.0 + 1e-8)
            if error["within_tolerance"]:
                break
            tcp = command
        self.assertTrue(error["within_tolerance"], error)
        self.assertLess(error["rotation_error_deg"], 1.5)

    def test_equivariant_under_change_of_world_frame(self):
        tcp = transform([0.4, 0.1, 0.6])
        measured = transform([0.45, 0.1, 0.56])
        desired = transform([0.46, 0.095, 0.56], Rotation.from_euler("x", 5, degrees=True).as_matrix())
        frame = transform([0.7, -0.1, 0.2], Rotation.from_euler("zyx", [50, -20, 30], degrees=True).as_matrix())
        first, _ = bounded_command(tcp, measured, desired)
        second, _ = bounded_command(frame @ tcp, frame @ measured, frame @ desired)
        np.testing.assert_allclose(second, frame @ first, atol=1e-12)

    def test_occluded_target_cannot_replace_last_reliable_support_pose(self):
        good_depth = {"accepted": True, "inliers": 2000, "plane_rmse_mm": 0.8}
        previous = transform([0.5, 0.2, 0.4])
        candidate = previous.copy()
        candidate[0, 3] += 0.02
        self.assertFalse(stationary_target_update(previous, candidate, good_depth)[0])
        candidate[0, 3] = 0.502
        self.assertFalse(stationary_target_update(previous, candidate, {"accepted": False})[0])
        self.assertTrue(stationary_target_update(previous, candidate, good_depth)[0])
        np.testing.assert_array_equal(previous, transform([0.5, 0.2, 0.4]))

    def test_rejects_large_pose_jumps_and_invalid_measurements(self):
        for desired in [transform([0.04, 0, 0]),
                        transform([0, 0, 0], Rotation.from_euler("x", 30, degrees=True).as_matrix())]:
            with self.assertRaisesRegex(ValueError, "outside correction envelope"):
                bounded_command(np.eye(4), np.eye(4), desired)
        for measured in [np.full((4, 4), np.nan), np.zeros((4, 4)), np.eye(3)]:
            with self.assertRaisesRegex(ValueError, r"SE\(3\)"):
                bounded_command(np.eye(4), measured, np.eye(4))

    def test_disturbance_is_physical_one_shot_and_clears_force(self):
        events = []
        robot = SimpleNamespace(
            target=SimpleNamespace(object_id="screwdriver"),
            objects={"screwdriver": SimpleNamespace(body="driver")},
            model=SimpleNamespace(body=lambda name: SimpleNamespace(id=0)),
            data=SimpleNamespace(time=1., xfrc_applied=np.zeros((1, 6))),
            event=lambda name, **kw: events.append((name, kw)),
        )
        pulse = AlignmentImpulse(robot)
        pulse("GRASP")
        self.assertEqual(len(events), 0)
        pulse("ALIGN_DRIVER_SETTLE")
        self.assertGreater(np.linalg.norm(robot.data.xfrc_applied), 0)
        robot.data.time += 0.13
        pulse("UNRELATED_STAGE")
        np.testing.assert_array_equal(robot.data.xfrc_applied, 0)
        pulse("ALIGN_DRIVER_SETTLE")
        self.assertEqual([e[0] for e in events], ["external_alignment_impulse_started", "external_alignment_impulse_finished"])

    def test_observation_archive_is_lossless_and_restorable(self):
        import tarfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "observations/frame").mkdir(parents=True)
            payload = np.random.default_rng(8).bytes(4000)
            (root / "observations/frame/depth.npy").write_bytes(payload)
            archive_observations(root)
            self.assertFalse((root / "observations").exists())
            with tarfile.open(root / "observations.tar.gz") as archive:
                self.assertEqual(archive.extractfile("observations/frame/depth.npy").read(), payload)

    def test_three_way_evaluation_retains_failures_and_rejects_unpaired_scene(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source", root / "results"
            source.mkdir()
            methods = ["open_loop", "staged", "iterative"]
            config = {"tasks": {"hang": {"methods": methods, "reference": "iterative", "disturbance": "alignment_impulse"}}, "seeds": [1]}
            (source / "protocol.json").write_text(json.dumps({"config": config}))
            for method in methods:
                for condition in ("none", "alignment_impulse"):
                    trial = source / "trials" / f"hang__{method}__{condition}__1"
                    trial.mkdir(parents=True)
                    report = {"task": "hang", "method": method, "seed": 1,
                              "disturbance": condition, "success": method == "iterative",
                              "initial_scene_state_sha256": "same", "model_free": True,
                              "control_source": "vision", "execution": {"events": []},
                              "timing": {"wall_seconds": 1.}}
                    (trial / "summary.json").write_text(json.dumps(report))
            result = summarize(source, output)
            self.assertEqual(result["n_trials"], 6)
            self.assertEqual(len(result["groups"]), 6)
            self.assertEqual(len(result["paired_module_comparisons"]), 4)
            self.assertEqual(sum(g["successes"] for g in result["groups"]), 2)
            path = source / "trials/hang__staged__none__1/summary.json"
            report = json.loads(path.read_text())
            report["initial_scene_state_sha256"] = "different"
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(RuntimeError, "Unmatched initial scene"):
                summarize(source, output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
