"""Metric, statistical-unit, and loaded-frame acceptance regressions."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
import cv2
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.advanced_scene import set_initial_pose
from ma6216.evaluation import pose_errors, wilson_interval
from ma6216.experiments import control_pose
from ma6216.pose_insertion import transform
from ma6216.reconstructed import validate_bundle
from ma6216.scene import mujoco
from ma6216.motion import Robot
from ma6216.workshop_assets import RACK_FRAME, TOOLS, FRAME_HOOK
from ma6216.workshop_scene import build_workshop_scene, RACK_POSE, RACK_T_FRAME, SPANNER_HANG_ROTATION
from run_workshop import frame_seating_evaluation, physical_evaluation
from ma6216.workshop_scene import rack_assembly_supports
from summarize_benchmark import comparison, interval, flatten
from run_benchmark import assert_valid_run
from ma6216.workshop_scene import label_texture


class Metrics(unittest.TestCase):
    def test_incomplete_initialization_cannot_be_scored_as_task_failure(self):
        with self.assertRaisesRegex(RuntimeError, "Incomplete initialization"):
            assert_valid_run({"success": False, "error": "empty PNG file"}, "broken")
        assert_valid_run(
            {
                "success": True,
                "initial_scene_state_sha256": "hash",
                "execution": {"events": []},
                "timing": {"wall_seconds": 1.0},
            },
            "valid",
        )

    def test_concurrent_texture_readers_only_see_complete_identical_pngs(self):
        def create(_):
            hashes = []

            def read_texture(**kwargs):
                data = Path(kwargs["file"]).read_bytes()
                image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                self.assertIsNotNone(image)
                self.assertEqual(image.shape, (128, 512, 3))
                hashes.append(hashlib.sha256(data).hexdigest())

            spec = SimpleNamespace(
                add_texture=read_texture,
                add_material=lambda **k: SimpleNamespace(name=k["name"], textures={}),
            )
            label_texture(spec, "shared", "CONCURRENT", "CACHE READERS")
            return hashes[0]

        with tempfile.TemporaryDirectory() as folder:
            with patch("ma6216.workshop_scene.project_root", return_value=Path(folder)):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    hashes = list(pool.map(create, range(64)))
        self.assertEqual(len(set(hashes)), 1)

    def test_clearance_guard_rejects_near_contact_without_disabling_collision(self):
        spec = mujoco.MjSpec()
        body = spec.worldbody.add_body(name="robot", pos=[0.0, 0.0, 0.2])
        body.add_freejoint()
        body.add_geom(name="robot_geom", type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[0.01, 0.0, 0.0], mass=1.0)
        spec.worldbody.add_geom(
            name="obstacle",
            type=mujoco.mjtGeom.mjGEOM_SPHERE,
            pos=[0.025, 0.0, 0.2],
            size=[0.01, 0.0, 0.0],
            margin=0.010,
            gap=0.010,
        )
        model = spec.compile()
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        fake = SimpleNamespace(
            model=model,
            scratch=data,
            robot_bodies={model.body("robot").id},
            cgids=set(),
            pad_sides={},
            obstacle_clearances={model.geom("obstacle").id: 0.010},
        )
        self.assertTrue(Robot.collision_contacts(fake))
        fake.obstacle_clearances = {}
        self.assertFalse(Robot.collision_contacts(fake))

    def test_reconstructed_frame_contacts_are_allowed_only_at_hanging_stages(self):
        names = {"target_cube_geom", "target_cube_geom_55"}
        self.assertTrue(names.issubset(rack_assembly_supports("SEAT_EYE", names)))
        self.assertFalse(names.intersection(rack_assembly_supports("TRANSFER_TO_REGRASP", names)))

    def test_geodesic_units_and_joint_accuracy(self):
        pose = transform([0.003, 0.004, 0.0], Rotation.from_euler("z", 90, degrees=True).as_matrix())
        result = pose_errors(pose, np.eye(4))
        self.assertAlmostEqual(result["translation_error_mm"], 5.0)
        self.assertAlmostEqual(result["rotation_error_deg"], 90.0)
        self.assertFalse(result["within_5mm_5deg"])

    def test_zero_and_perfect_success_still_have_uncertainty(self):
        self.assertAlmostEqual(wilson_interval(10, 10)[0], 0.7224672, places=6)
        self.assertAlmostEqual(wilson_interval(0, 10)[1], 0.2775328, places=6)
        self.assertEqual(wilson_interval(0, 0), [None, None])
        diff = comparison([1] * 10, [0] * 10)
        self.assertLess(diff["conservative_ci95"][0], 0.5)
        self.assertEqual(diff["a_only_success"], 10)
        self.assertEqual(interval([1.0, None, 3.0])["n_trials"], 2)

    def test_yaw_ablation_keeps_translation_and_raw_pose_immutable(self):
        raw = transform([0.4, 0.1, 0.5], Rotation.from_euler("zyx", [30, 20, 80], degrees=True).as_matrix())
        original = raw.copy()
        flat = control_pose(raw, "yaw_only")
        np.testing.assert_allclose(raw, original)
        np.testing.assert_allclose(flat[:3, 3], raw[:3, 3])
        np.testing.assert_allclose(flat[:3, 2], [0.0, 0.0, 1.0])
        self.assertGreater(pose_errors(flat, raw)["rotation_error_deg"], 60.0)

    def test_pose_accuracy_counts_missing_targets_and_uses_first_fixed_capture(self):
        def observation(obj, camera="vision_camera", accurate=True):
            return {
                "object_id": obj,
                "camera": camera,
                "raw_estimator_metrics_evaluation_only": {"within_5mm_5deg": accurate},
                "control_pose_metrics_evaluation_only": {"within_5mm_5deg": accurate},
            }

        report = {"task": "rack", "perception": [observation("rack_frame")]}
        self.assertFalse(flatten(report, "test")["pose_initial_raw_all_targets_accurate"])
        report["perception"].append(observation("spanner", "wrist_camera"))
        self.assertFalse(flatten(report, "test")["pose_initial_raw_all_targets_accurate"])
        report["perception"].append(observation("spanner"))
        self.assertTrue(flatten(report, "test")["pose_initial_raw_all_targets_accurate"])
        report["perception"].append(observation("spanner", accurate=False))
        self.assertTrue(flatten(report, "test")["pose_initial_raw_all_targets_accurate"])


class FramePhysics(unittest.TestCase):
    def setUp(self):
        self.scene = build_workshop_scene(rack_assembly=True)

    def test_bundle_and_floating_frame(self):
        manifest, _ = validate_bundle(ROOT / "assets/reconstructed/workshop/rack_frame")
        self.assertEqual(manifest["object_id"], "rack_frame")
        m, d = self.scene.model, self.scene.data
        pose = RACK_POSE @ RACK_T_FRAME
        pose[2, 3] += 0.02
        set_initial_pose(m, d, RACK_FRAME, pose)  # Explicit evaluator fixture, not controller action.
        mujoco.mj_forward(m, d)
        result = frame_seating_evaluation(self.scene)
        self.assertFalse(result["success"])
        self.assertEqual(result["support_force_n"], 0.0)

    def test_seated_frame_really_supports_the_released_spanner(self):
        m, d = self.scene.model, self.scene.data
        frame = RACK_POSE @ RACK_T_FRAME
        set_initial_pose(m, d, RACK_FRAME, frame)
        rotation = frame[:3, :3] @ SPANNER_HANG_ROTATION
        eye = (frame @ np.r_[FRAME_HOOK + [0.0, 0.025, -0.009], 1.0])[:3]
        set_initial_pose(m, d, TOOLS["spanner"], transform(eye - rotation @ [-0.060, 0.0, 0.0], rotation))
        mujoco.mj_forward(m, d)
        for _ in range(2500):
            mujoco.mj_step(m, d)
        support = frame_seating_evaluation(self.scene)
        hanging = physical_evaluation(self.scene, "spanner", assembled_frame=True)
        self.assertTrue(support["success"], support)
        self.assertTrue(hanging["success"], hanging)
        self.assertGreater(support["support_force_n"], 1.5)
        self.assertFalse(hanging["gripper_contact_after_release"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
