"""Inspect recorded rack motion and independently extend its final state.

This is an evaluation-only diagnostic. It never changes a trial's outcome,
reruns perception, or substitutes a new trajectory for the original one.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.motion import JOINT_NAMES
from ma6216.scene import mujoco
from ma6216.workshop_assets import RACK_TOOLS
from ma6216.workshop_scene import build_workshop_scene
from run_workshop import frame_seating_evaluation, physical_evaluation


def subtree(model, root):
    bodies = {model.body(root).id}
    for body in range(1, model.nbody):
        if int(model.body_parentid[body]) in bodies:
            bodies.add(body)
    return bodies


def restore(data, state, index=None):
    for key in ("qpos", "qvel", "ctrl", "mocap_pos", "mocap_quat"):
        getattr(data, key)[:] = state[key] if index is None else state[key][index]
    data.time = float(state["time"] if index is None else state["time"][index])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.trial / "summary.json").read_text())
    if report["task"] != "rack":
        parser.error("This diagnostic requires a rack trial")
    path = args.trial / "motion/trajectory_evaluation_only.npz"
    trace = np.load(path, allow_pickle=False)
    scene = build_workshop_scene(report["seed"], rack_assembly=True)
    model, data = scene.model, scene.data
    robot = subtree(model, "base")
    gripper = subtree(model, "gripper_base")
    tools = {model.geom(n).id for tool in RACK_TOOLS.values() for n in tool.collision_names}
    pads = {model.geom(f"gripper_{side}_pad{i}").id for side in ("left", "right") for i in (1, 2)}
    contacts, loaded_after_release = {}, []
    for index, timestamp in enumerate(trace["time"]):
        restore(data, trace, index)
        mujoco.mj_forward(model, data)
        stage = str(trace["stage"][index])
        for contact_index, contact in enumerate(data.contact):
            pair = (int(contact.geom1), int(contact.geom2))
            bodies = {int(model.geom_bodyid[g]) for g in pair}
            penetration = -float(contact.dist) * 1000
            intended_pad_contact = bool(pads.intersection(pair) and tools.intersection(pair))
            if robot.intersection(bodies) and not intended_pad_contact and penetration > 0.01:
                key = " / ".join(model.geom(g).name or f"geom_{g}" for g in pair)
                if key not in contacts or penetration > contacts[key]["penetration_mm"]:
                    contacts[key] = dict(time_s=float(timestamp), stage=stage, penetration_mm=penetration)
            if (
                stage in ("CHECK_HANG_STABILITY", "TOOLS_READY")
                and gripper.intersection(bodies)
                and tools.intersection(pair)
            ):
                wrench = np.zeros(6)
                mujoco.mj_contactForce(model, data, contact_index, wrench)
                if wrench[0] > 0.001:
                    loaded_after_release.append(dict(time_s=float(timestamp), normal_n=float(wrench[0])))
    joints = [model.jnt_qposadr[model.joint(name).id] for name in JOINT_NAMES]
    measured = trace["qpos"][:, joints]
    stages = {}
    for stage in dict.fromkeys(trace["stage"].tolist()):
        indices = np.flatnonzero(trace["stage"] == stage)
        values = measured[indices]
        stages[stage] = {
            "first_s": float(trace["time"][indices[0]]),
            "last_s": float(trace["time"][indices[-1]]),
            "sampled_duration_s": float(trace["time"][indices[-1]] - trace["time"][indices[0]]),
            "joint_start_deg": np.rad2deg(values[0]).tolist(),
            "joint_end_deg": np.rad2deg(values[-1]).tolist(),
            "joint_travel_deg": np.rad2deg(np.abs(np.diff(values, axis=0)).sum(axis=0)).tolist(),
        }
    final_path = args.trial / "final_state_evaluation_only.npz"
    restore(data, np.load(final_path, allow_pickle=False))
    mujoco.mj_forward(model, data)

    def outcome():
        return dict(
            rack_frame=frame_seating_evaluation(scene),
            spanner=physical_evaluation(scene, "spanner", assembled_frame=True),
        )

    recorded_final = outcome()
    extension = []
    start = data.time
    for index in range(round(30 / model.opt.timestep)):
        mujoco.mj_step(model, data)
        if (index + 1) % round(5 / model.opt.timestep) == 0:
            extension.append(dict(additional_seconds=float(data.time - start), **outcome()))
    result = {
        "trial": args.trial.name,
        "seed": report["seed"],
        "original_success": report["success"],
        "control_source": report["control_source"],
        "trajectory_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "final_state_sha256": hashlib.sha256(final_path.read_bytes()).hexdigest(),
        "audited_snapshots": len(trace["time"]),
        "simulation_duration_s": float(trace["time"][-1] - trace["time"][0]),
        "unexpected_robot_contacts_above_0_01mm": contacts,
        "loaded_gripper_contacts_after_final_release": loaded_after_release,
        "joint_names": JOINT_NAMES,
        "stages": stages,
        "recorded_final_state": recorded_final,
        "passive_extension_30s_diagnostic_only": extension,
        "note": "Contacts inspected at recorded 25 Hz snapshots, not all 500 Hz physics steps. The controller separately guards every step. The passive extension is a separate diagnostic; original trial and aggregate outcomes stay unchanged.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "trial": args.trial.name,
                "robot_contacts": contacts,
                "loaded_gripper_contacts": len(loaded_after_release),
                "extension_success": all(
                    x["rack_frame"]["success"] and x["spanner"]["success"] for x in extension
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
