"""CPU regressions for provenance, delayed visual prediction, and seating checks."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.advanced_scene import build_task_scene, set_initial_pose
from ma6216.online_pose import PoseHistory
from ma6216.pose_insertion import transform
from ma6216.reconstructed import validate_bundle
from ma6216.scene import mujoco
from ma6216.simulation_objects import PLUG
from ma6216.task_control import ObservedObject
from run_model_free_task import seating_evaluation


class ReconstructionProvenance(unittest.TestCase):
    def test_bundled_assets_match_reconstruction_checksums(self):
        for name in ("plug", "blocker"):
            manifest, mesh = validate_bundle(ROOT / "assets/reconstructed" / name)
            self.assertEqual(manifest["object_id"], name)
            self.assertGreater(mesh.stat().st_size, 1000)
            import hashlib
            references = mesh.parent / "reference_capture.json"
            self.assertEqual(hashlib.sha256(references.read_bytes()).hexdigest(),
                             manifest["reference_manifest_sha256"])

    def test_modified_geometry_and_cad_declared_bundle_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "bundle"
            shutil.copytree(ROOT / "assets/reconstructed/plug", folder)
            mesh = folder / "model.obj"
            original = mesh.read_bytes()
            mesh.write_bytes(original + b"\n# unexpected edit\n")
            with self.assertRaisesRegex(ValueError, "integrity"):
                validate_bundle(folder)
            mesh.write_bytes(original)
            manifest_file = folder / "model_free.json"
            manifest = json.loads(manifest_file.read_text())
            manifest["cad_used_for_reconstruction"] = True
            manifest_file.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "image-only"):
                validate_bundle(folder)


class CaptureTimePrediction(unittest.TestCase):
    def test_predicts_at_contact_time_including_inference_delay(self):
        history = PoseHistory()
        velocity = np.array([0., .004, 0.])
        rotation = Rotation.from_euler("xyz", [12., -8., 27.], degrees=True).as_matrix()
        for timestamp in [2., 3.5, 5.]:
            history.add(timestamp, transform(np.array([.4, -.2, .44]) + velocity * timestamp, rotation))
        # Last image was captured at t=5; inference completes at 6, contact at 9.
        predicted = history.predict(9.)
        np.testing.assert_allclose(predicted[:3, 3], np.array([.4, -.2, .44]) + velocity * 9., atol=1e-12)
        np.testing.assert_allclose(predicted[:3, :3], rotation, atol=1e-12)

    def test_stale_nonfinite_and_out_of_range_predictions_fail(self):
        history = PoseHistory()
        with self.assertRaises(ValueError):
            history.predict(0.)
        history.add(1., np.eye(4))
        for timestamp in (1., 0., float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                history.add(timestamp, np.eye(4))
        for timestamp in (0., 14.):
            with self.assertRaises(ValueError):
                history.predict(timestamp)
        history.add(2., transform([.10, 0., 0.]))
        with self.assertRaisesRegex(ValueError, "velocity"):
            history.predict(3.)

    def test_box_frame_ambiguity_does_not_reverse_approach(self):
        blocker = ObservedObject(ROOT / "assets/reconstructed/blocker")
        for roll in (0., 90., 180., 270.):
            pose = transform([.46, -.22, .40], Rotation.from_euler("x", roll, degrees=True).as_matrix())
            grasp = pose @ blocker.upper_face_grasp(pose)
            self.assertLess(grasp[2, 2], -.99)
            self.assertGreater(grasp[2, 3], pose[2, 3])


class PhysicalSeating(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = build_task_scene("assembly")
        cls.model, cls.data = cls.scene.model, cls.scene.data

    def place_for_diagnostic(self, pose):
        # These tests explicitly initialize diagnostic states. The task runner
        # never writes a live object's qpos after its initial scene setup.
        set_initial_pose(self.model, self.data, PLUG, pose)
        self.data.qvel[:] = 0.
        mujoco.mj_forward(self.model, self.data)

    def test_supported_correct_pose_passes_after_settling(self):
        self.place_for_diagnostic(self.scene.fixture_initial @ transform([0., 0., .035]))
        for _ in range(1500):
            mujoco.mj_step(self.model, self.data)
        result = seating_evaluation(self.scene)
        self.assertTrue(result["success"], result)
        self.assertGreater(result["support_force_n"], .2)

    def test_floating_and_wrong_heading_do_not_count_as_assembly(self):
        fixture = self.scene.fixture_initial
        self.place_for_diagnostic(fixture @ transform([0., 0., .075]))
        result = seating_evaluation(self.scene)
        self.assertFalse(result["success"], result)
        self.assertEqual(result["support_force_n"], 0.)
        self.place_for_diagnostic(fixture @ transform([0., 0., .035], Rotation.from_euler("z", 180., degrees=True).as_matrix()))
        result = seating_evaluation(self.scene)
        self.assertFalse(result["success"], result)
        self.assertGreater(result["rotation_error_deg"], 170.)


if __name__ == "__main__":
    unittest.main()
