"""Check full-pose grasp geometry and reject wrong-orientation/floating seating."""
import json
from pathlib import Path
import sys

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ma6216.pose_insertion import (BLOCK, build_insertion_scene, grasp_transform,
                                   insertion_outcome, object_pose, set_object_pose, transform)
from ma6216.scene import mujoco


def main():
    supplied = transform([.42, -.18, .44], Rotation.from_euler("xyz", [10, -8, 22], degrees=True).as_matrix())
    used, tcp = grasp_transform(supplied)
    projected, _ = grasp_transform(supplied, "yaw-only")
    assert np.allclose(used, supplied)
    assert not np.allclose(projected[:3, :3], used[:3, :3])
    assert np.allclose(tcp[:3, 2], -supplied[:3, 2])
    # The same object-to-tool relationship must reconstruct a completely
    # different target pose, including its orientation and grasp-point offset.
    target = transform([.49, .18, .409], Rotation.from_euler("xyz", [0, 0, -15], degrees=True).as_matrix())
    tool_T_object = np.linalg.inv(tcp) @ used
    desired_tcp = target @ np.linalg.inv(tool_T_object)
    assert np.allclose(desired_tcp @ tool_T_object, target)

    model, data, nest = build_insertion_scene(1)
    assert model.body_gravcomp[model.body(BLOCK.body).id] == 0.
    assert model.body_gravcomp[model.body("upper_arm_link").id] == 1.
    for _ in range(750):
        mujoco.mj_step(model, data)
    rpy = Rotation.from_matrix(object_pose(model, data)[:3, :3]).as_euler("xyz", degrees=True)
    assert abs(rpy[0]) > 5 and abs(rpy[1]) > 5, rpy

    # Test fixtures may initialize object qpos. The controller never does this.
    floating = nest.target_pose.copy()
    floating[2, 3] += .012
    set_object_pose(data.qpos, model, floating)
    data.qvel[:] = 0.
    mujoco.mj_forward(model, data)
    outcome = insertion_outcome(model, data, nest)
    assert not outcome["success"] and outcome["bottom_support_force_n"] == 0.

    wrong = nest.target_pose.copy()
    wrong[:3, :3] = Rotation.from_euler("z", 180, degrees=True).as_matrix()
    set_object_pose(data.qpos, model, wrong)
    mujoco.mj_forward(model, data)
    outcome = insertion_outcome(model, data, nest)
    assert not outcome["success"] and outcome["rotation_error_deg"] > 170.
    assert outcome["minimum_wall_clearance_mm"] < 0.

    seated = nest.target_pose.copy()
    seated[2, 3] += .001
    set_object_pose(data.qpos, model, seated)
    data.qvel[:] = 0.
    for _ in range(1500):
        mujoco.mj_step(model, data)
    outcome = insertion_outcome(model, data, nest)
    assert outcome["success"], outcome
    print(json.dumps({"full_pose_geometry": True, "tilted_source_rpy_deg": rpy.tolist(),
                      "floating_rejected": True, "wrong_heading_rejected": True,
                      "correct_physical_seating_accepted": True, "seated": outcome}))


if __name__ == "__main__":
    main()
