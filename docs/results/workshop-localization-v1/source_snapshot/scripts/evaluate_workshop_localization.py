"""Frozen RGB-D localization audit, with simulator masks exclusively downstream.

50 scene observations: 10 paired seeds x 5 conditions, four target queries each.
This is a perception test, not 50 new manipulation trials or pose-network runs.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
from ma6216.advanced_scene import set_initial_pose
from ma6216.evaluation import wilson_interval
from ma6216.localization_evaluation import mask_metrics
from ma6216.pose_insertion import transform
from ma6216.scene import mujoco, CAMERA_NAME, WIDTH, HEIGHT
from ma6216.workshop_assets import COMPLETE_TOOLS
from ma6216.workshop_scene import build_workshop_scene, PICK_REGIONS
from ma6216.workshop_perception import depth_region_mask, ObservationUnavailable

CONDITIONS = ("nominal", "position_orientation", "partial_occlusion", "depth_noise", "target_absent")
REGIONS = {name: "rack_frame" if name == "rack_frame" else "complete_" + name for name in COMPLETE_TOOLS}


def render(renderer, data):
    renderer.update_scene(data, camera=CAMERA_NAME)
    renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
    renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
    rgb = renderer.render().copy()
    renderer.enable_depth_rendering()
    try:
        depth = renderer.render().copy()
    finally:
        renderer.disable_depth_rendering()
    return rgb, depth


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def evaluate(output, calibration):
    output.mkdir(parents=True, exist_ok=False)
    (output / "scenes").mkdir()
    (output / "examples").mkdir()
    (output / "backgrounds").mkdir()
    K, WTC = np.loadtxt(calibration / "cam_K.txt"), np.loadtxt(calibration / "world_T_camera.txt")
    sources = ["scripts/evaluate_workshop_localization.py", "src/ma6216/localization_evaluation.py",
               "src/ma6216/workshop_perception.py", "src/ma6216/workshop_scene.py",
               "demo_data/calibration/estimated/cam_K.txt", "demo_data/calibration/estimated/world_T_camera.txt"]
    protocol = {"seeds": list(range(500, 510)), "conditions": list(CONDITIONS),
        "objects": list(COMPLETE_TOOLS), "localization_success": "visible GT >=40 pixels and prediction >=40 pixels and visible-mask IoU >=0.5",
        "position_orientation": "independent world XY +/-10 mm and yaw +/-20 degrees per object, then 0.5 s physical settling",
        "partial_occlusion": "four 50x50 mm opaque non-contact screens, 12% along each object-to-camera ray with 10 mm lateral offset; true geometry used only to construct the test condition",
        "depth_noise": "zero-mean Gaussian sigma 2 mm plus 2% independently missing depth pixels; background unchanged",
        "target_absent": "all four tools removed; fixture/support geometry remains; count false positives",
        "ground_truth_boundary": "predict every mask before rendering simulator segmentation; GT and IDs never enter localization",
        "background_protocol": "commission an empty workcell for each seed, matching production run_workshop; supports vary with the seed, so a universal seed-0 background is invalid",
        "uncertainty": "Wilson intervals per object (10 independent scenes); bootstrap 10000 of seed-level four-object means for aggregate IoU",
        "failure_selection": "first failure in seed order per condition/object; all rows retained",
        "source_sha256": {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in sources}}
    write_json(output / "protocol.json", protocol)
    for source in sources:
        destination = output / "source_snapshot" / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / source).read_bytes())
    rows, examples = [], {}
    for seed in protocol["seeds"]:
        empty = build_workshop_scene(seed, empty=True, complete_task=True)
        with mujoco.Renderer(empty.model, height=HEIGHT, width=WIDTH) as rr:
            _, background = render(rr, empty.data)
        np.save(output / "backgrounds" / f"{seed}.npy", background)
        def extra(spec):
            for name in COMPLETE_TOOLS:
                spec.worldbody.add_geom(name="audit_screen_" + name, type=mujoco.mjtGeom.mjGEOM_BOX,
                    pos=[0., 0., -10.], size=[.025, .025, .002], rgba=[.34, .35, .36, 1.], contype=0, conaffinity=0)
        scene = build_workshop_scene(seed, complete_task=True, configure_extra=extra)
        m, d = scene.model, scene.data
        for _ in range(1000):
            mujoco.mj_step(m, d)
        qpos, qvel, ctrl, start_time = d.qpos.copy(), d.qvel.copy(), d.ctrl.copy(), d.time
        nominal_poses = {name: transform(d.xpos[m.body(t.body).id], d.xmat[m.body(t.body).id].reshape(3, 3))
                         for name, t in COMPLETE_TOOLS.items()}
        nominal_pixels = {}
        with mujoco.Renderer(m, height=HEIGHT, width=WIDTH) as renderer:
            for condition in CONDITIONS:
                d.qpos[:], d.qvel[:], d.ctrl[:], d.time = qpos, qvel, ctrl, start_time
                rng = np.random.default_rng(seed)
                for name, tool in COMPLETE_TOOLS.items():
                    pose = nominal_poses[name].copy()
                    screen = m.geom("audit_screen_" + name).id
                    m.geom_pos[screen] = [0., 0., -10.]
                    if condition == "position_orientation":
                        pose[:2, 3] += rng.uniform(-.010, .010, 2)
                        pose[:3, :3] = Rotation.from_euler("z", rng.uniform(-20., 20.), degrees=True).as_matrix() @ pose[:3, :3]
                    elif condition == "partial_occlusion":
                        m.geom_pos[screen] = pose[:3, 3] + .12 * (np.array([1.05, -1.05, 1.20]) - pose[:3, 3]) + [.010, 0., 0.]
                    elif condition == "target_absent":
                        pose[2, 3] = -5.
                    set_initial_pose(m, d, tool, pose)
                mujoco.mj_forward(m, d)
                if condition == "position_orientation":
                    for _ in range(250):
                        mujoco.mj_step(m, d)
                rgb, depth = render(renderer, d)
                if condition == "depth_noise":
                    depth += rng.normal(0., .002, depth.shape).astype(np.float32)
                    depth[rng.random(depth.shape) < .02] = 0.
                folder = output / "scenes" / f"{condition}__{seed}"
                folder.mkdir()
                cv2.imwrite(str(folder / "rgb.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
                np.save(folder / "depth.npy", depth)
                predictions, failures = {}, {}
                # Actual localization API receives images/calibration/declared station bounds only.
                for name in COMPLETE_TOOLS:
                    try:
                        predictions[name] = depth_region_mask(depth, K, WTC, PICK_REGIONS[REGIONS[name]], background)
                    except ObservationUnavailable as exc:
                        predictions[name] = np.zeros(depth.shape, np.uint8)
                        failures[name] = str(exc)
                    cv2.imwrite(str(folder / (name + "_prediction.png")), predictions[name])
                # GT access starts AFTER all four predictions have been saved.
                renderer.enable_segmentation_rendering()
                try:
                    seg = renderer.render().copy()
                finally:
                    renderer.disable_segmentation_rendering()
                state = {}
                for name, tool in COMPLETE_TOOLS.items():
                    bid = m.body(tool.body).id
                    gids = np.flatnonzero(m.geom_bodyid == bid)
                    truth = np.isin(seg[..., 0], gids) & (seg[..., 1] == int(mujoco.mjtObj.mjOBJ_GEOM))
                    metric = mask_metrics(predictions[name], truth)
                    if condition == "nominal":
                        nominal_pixels[name] = metric["visible_truth_pixels"]
                    metric["visible_fraction_of_nominal"] = metric["visible_truth_pixels"] / max(1, nominal_pixels[name])
                    row = {"seed": seed, "condition": condition, "object": name, **metric,
                           "failure_reason": failures.get(name, ""), "input": str(folder.relative_to(output)),
                           "input_depth_sha256": hashlib.sha256((folder / "depth.npy").read_bytes()).hexdigest()}
                    rows.append(row)
                    cv2.imwrite(str(folder / (name + "_truth_evaluation_only.png")), truth.astype(np.uint8) * 255)
                    state[name] = transform(d.xpos[bid], d.xmat[bid].reshape(3, 3)).tolist()
                    failed = metric["false_positive_on_invisible"] if condition == "target_absent" else not metric["localized_iou50"]
                    key = condition + "__" + name + ("__failure" if failed else "__sample")
                    if (failed or (condition == "nominal" and seed == 500)) and key not in examples:
                        picture = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                        pred = predictions[name] > 0
                        colours = np.zeros_like(picture)
                        colours[truth & ~pred], colours[pred & ~truth], colours[pred & truth] = [255, 80, 0], [0, 0, 255], [0, 200, 0]
                        active = truth | pred
                        picture[active] = (picture[active] * .45 + colours[active] * .55).astype(np.uint8)
                        cv2.rectangle(picture, (0, 0), (WIDTH, 85), (20, 20, 20), -1)
                        label = f"{condition} | {name} | seed {seed} | IoU {metric['iou']}"
                        cv2.putText(picture, label[:110], (18, 30), cv2.FONT_HERSHEY_SIMPLEX, .60, (255,255,255), 1, cv2.LINE_AA)
                        cv2.putText(picture, "GREEN overlap | RED false positive | BLUE missed target", (18, 63), cv2.FONT_HERSHEY_SIMPLEX, .60, (255,255,255), 1, cv2.LINE_AA)
                        path = "examples/" + key + f"__{seed}.jpg"
                        cv2.imwrite(str(output / path), picture, [cv2.IMWRITE_JPEG_QUALITY, 90])
                        examples[key] = {"path": path, "failed": failed, "seed": seed, "condition": condition, "object": name}
                write_json(folder / "evaluation_only_object_poses.json", state)
                print(f"{seed} {condition} complete", flush=True)
    with (output / "observations.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    groups = []
    for condition in CONDITIONS:
        for name in COMPLETE_TOOLS:
            rr = [r for r in rows if r["condition"] == condition and r["object"] == name]
            positive = condition != "target_absent"
            n = len(rr)
            count = sum(r["localized_iou50"] if positive else r["false_positive_on_invisible"] for r in rr)
            groups.append({"condition": condition, "object": name, "n": n,
                "count_type": "localized_iou50" if positive else "false_positive_on_absent", "count": count,
                "wilson95": wilson_interval(count, n),
                **{key + "_mean": float(np.mean(v)) if (v := [r[key] for r in rr if r[key] is not None]) else None
                   for key in ("iou", "precision", "recall", "visible_fraction_of_nominal")},
                "mask_returned": sum(r["mask_returned"] for r in rr)})
    aggregates = []
    for condition in CONDITIONS[:-1]:
        per_seed = [np.mean([r["iou"] for r in rows if r["condition"] == condition and r["seed"] == seed and r["iou"] is not None])
                    for seed in protocol["seeds"]]
        rng = np.random.default_rng(6216)
        means = np.array(per_seed)[rng.integers(0, len(per_seed), (10000, len(per_seed)))].mean(axis=1)
        aggregates.append({"condition": condition, "independent_scenes": len(per_seed),
                           "mean_iou": float(np.mean(per_seed)), "bootstrap95": np.quantile(means, [.025, .975]).tolist()})
    summary = {"scene_observations": 50, "object_queries": len(rows), "groups": groups,
               "scene_level_aggregates": aggregates, "examples": list(examples.values()),
               "scope": "fixed task camera and current four-tool pickup segmentation; wrist ROI and object-class recognition not evaluated"}
    write_json(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--calibration", type=Path, default=ROOT / "demo_data/calibration/estimated")
    args = p.parse_args()
    evaluate(args.output, args.calibration)
