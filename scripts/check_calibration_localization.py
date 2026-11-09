"""Check calibration observability, frame direction, truth isolation and mask failures."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np
from scipy.spatial.transform import Rotation
from ma6216.wrist_calibration import solve_hand_eye, detect_wrist_checker
from ma6216.pose_insertion import transform
from ma6216.task_perception import ImageObserver
from ma6216.advanced_scene import WRIST_CAMERA
from ma6216.localization_evaluation import mask_metrics


class CalibrationChecks(unittest.TestCase):
    def test_marker_rejects_shifted_lattice_even_if_grid_is_planar(self):
        import cv2
        from ma6216.scene import board_points
        image = np.zeros((960, 1280, 3), np.uint8)
        cv2.circle(image, (448, 290), 8, (255, 0, 255), -1)
        corners = (board_points()[:, :2] * 1000 + [600., 400.]).astype(np.float32)
        with patch("ma6216.wrist_calibration.detect_checker", return_value=corners):
            points, quality = detect_wrist_checker(image)
            self.assertIsNotNone(points)
            self.assertTrue(quality["accepted"])
        with patch("ma6216.wrist_calibration.detect_checker", return_value=corners + [28., 0.]):
            points, quality = detect_wrist_checker(image)
            self.assertIsNone(points)
            self.assertGreater(quality["marker_error_px"], 20.)

    def test_recovers_unknown_mount_without_world_board_prior(self):
        rng = np.random.default_rng(17)
        X = transform([.07, -.01, .03], Rotation.from_euler("xyz", [15., 28., -73.], degrees=True).as_matrix())
        Y = transform([.4, -.1, .3], Rotation.from_euler("xyz", [0., 20., 35.], degrees=True).as_matrix())
        G = [transform(rng.uniform(-.5, .5, 3), Rotation.random(random_state=rng).as_matrix()) for _ in range(14)]
        C = [np.linalg.inv(g @ X) @ Y for g in G]
        actual, _ = solve_hand_eye(G, C)
        np.testing.assert_allclose(actual, X, atol=1e-10)
        Z = transform([.8, .7, .6], Rotation.from_euler("x", 42., degrees=True).as_matrix())
        reexpressed, _ = solve_hand_eye([Z @ g for g in G], C)
        np.testing.assert_allclose(reexpressed, X, atol=1e-10)

    def test_rejects_translation_only_and_single_axis_sequences(self):
        for rotation in [False, True]:
            G = [transform([0., 0., i * .01], Rotation.from_euler("z", i * .07 if rotation else 0).as_matrix()) for i in range(8)]
            with self.assertRaisesRegex(ValueError, "nonparallel"):
                solve_hand_eye(G, [np.linalg.inv(g) for g in G])

    def test_estimated_runtime_never_reads_simulator_camera_parameters(self):
        class Model:
            def body(self, name):
                assert name == "gripper_base"
                return SimpleNamespace(id=0)
            def __getattr__(self, name):
                raise AssertionError("Simulator camera truth accessed: " + name)
        observer = ImageObserver.__new__(ImageObserver)
        observer.model, observer.ideal_wrist = Model(), False
        observer.wrist_gripper_body = "gripper_base"
        observer.wrist_K = np.diag([500., 501., 1.])
        observer.gripper_T_camera = transform([.07, 0., .03], Rotation.from_euler("y", .3).as_matrix())
        G = transform([.4, -.1, .6], Rotation.from_euler("xyz", [.2, -.1, .5]).as_matrix())
        data = SimpleNamespace(xpos=np.array([G[:3, 3]]), xmat=np.array([G[:3, :3].ravel()]))
        K, pose, label = observer.camera_calibration(data, WRIST_CAMERA)
        np.testing.assert_allclose(pose, G @ observer.gripper_T_camera)
        self.assertIn("estimated", label)
        K[0, 0] = 0.
        self.assertEqual(observer.wrist_K[0, 0], 500.)


class LocalizationChecks(unittest.TestCase):
    def test_missing_target_is_not_perfect_iou_and_false_positive_is_counted(self):
        empty = np.zeros((20, 20), bool)
        missing = mask_metrics(empty, empty)
        self.assertIsNone(missing["iou"])
        self.assertFalse(missing["localized_iou50"])
        false = mask_metrics(np.ones_like(empty), empty)
        self.assertTrue(false["false_positive_on_invisible"])

    def test_missed_and_wrong_component_are_failures(self):
        truth = np.zeros((20, 20), bool)
        truth[:10] = True
        for pred in [np.zeros_like(truth), ~truth]:
            r = mask_metrics(pred, truth)
            self.assertEqual(r["iou"], 0.)
            self.assertEqual(r["recall"], 0.)
            self.assertFalse(r["localized_iou50"])
        r = mask_metrics(np.ones_like(truth), truth)
        self.assertEqual(r["iou"], .5)
        self.assertEqual(r["precision"], .5)
        self.assertEqual(r["recall"], 1.)


if __name__ == "__main__":
    unittest.main(verbosity=2)
