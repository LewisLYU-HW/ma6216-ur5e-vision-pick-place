"""Aggregate complete paired trials; uncertainty units are runs, never frames."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from scipy.stats import beta, binomtest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.evaluation import wilson_interval
from run_benchmark import trial_id, assert_valid_run, configured_methods

PRIMARY = {
    "assembly": ("plug",),
    "clutter": ("plug",),
    "conveyor": ("plug",),
    "insert": ("screwdriver",),
    "hang": ("spanner",),
    "rack": ("rack_frame", "spanner"),
    "complete": ("hammer", "screwdriver", "rack_frame", "spanner"),
}


def interval(values):
    x = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if not len(x):
        return {"n_trials": 0, "mean": None, "ci95": [None, None]}
    samples = np.random.default_rng(6216).choice(x, (10000, len(x)), replace=True).mean(axis=1)
    return {
        "n_trials": len(x),
        "mean": float(x.mean()),
        "ci95": np.percentile(samples, [2.5, 97.5]).tolist() if len(x) > 1 else [None, None],
    }


def comparison(a, b):
    if len(a) != len(b) or not len(a):
        raise ValueError("A comparison requires all seed-matched observations")
    a, b = np.asarray(a, dtype=int), np.asarray(b, dtype=int)
    n = len(a)

    def marginal(x):
        k = int(x.sum())
        return (
            0.0 if k == 0 else float(beta.ppf(0.0125, k, n - k + 1)),
            1.0 if k == n else float(beta.ppf(0.9875, k + 1, n - k)),
        )

    la, ua = marginal(a)
    lb, ub = marginal(b)
    wins, losses = int(np.sum(a > b)), int(np.sum(a < b))
    return {
        "n_pairs": n,
        "success_difference": float(np.mean(a - b)),
        "conservative_ci95": [la - ub, ua - lb],
        "a_only_success": wins,
        "b_only_success": losses,
        "exact_mcnemar_p_unadjusted": float(binomtest(wins, wins + losses).pvalue) if wins + losses else 1.0,
        "note": "Exploratory multiple comparisons; no multiplicity-adjusted superiority claim.",
    }


def mean(values):
    values = [v for v in values if v is not None]
    return float(np.mean(values)) if values else None


def flatten(report, name):
    row = {
        "trial": name,
        **{k: report.get(k) for k in ("task", "method", "disturbance", "seed", "success", "last_stage")},
        "error": report.get("error", ""),
    }
    samples = report.get("perception", [])
    initial = {}
    for s in samples:
        if s["camera"] == "vision_camera" and s["object_id"] in PRIMARY[report["task"]]:
            initial.setdefault(s["object_id"], s)
    for kind, key in (
        ("raw", "raw_estimator_metrics_evaluation_only"),
        ("control", "control_pose_metrics_evaluation_only"),
    ):
        row[f"pose_initial_{kind}_all_targets_accurate"] = len(initial) == len(
            PRIMARY[report["task"]]
        ) and all(s.get(key, {}).get("within_5mm_5deg", False) for s in initial.values())
    for subset, observations in (("initial", list(initial.values())), ("all_observations", samples)):
        for kind, key in (
            ("raw", "raw_estimator_metrics_evaluation_only"),
            ("control", "control_pose_metrics_evaluation_only"),
        ):
            for metric in (
                "translation_error_mm",
                "rotation_error_deg",
                "add_mm",
                "adds_mm",
                "within_5mm_5deg",
            ):
                row[f"pose_{subset}_{kind}_{metric}"] = mean(
                    [s.get(key, {}).get(metric) for s in observations]
                )
    row["pose_observation_count"] = len(samples)
    execution = report.get("execution", {})
    for key in (
        "tcp_tracking_translation_mm",
        "tcp_tracking_rotation_deg",
        "joint_tracking_rmse_rad",
        "move_endpoint_translation_mm",
        "move_endpoint_rotation_deg",
    ):
        for stat in ("mean", "rmse", "p95"):
            row[f"{key}_{stat}"] = execution.get(key, {}).get(stat)
    timing = report.get("timing", {})
    for key in (
        "wall_seconds",
        "effective_steps_per_wall_second",
        "real_time_factor",
        "pose_calls_per_wall_second_including_waits",
    ):
        row[key] = timing.get(key)
    for kind in ("inference", "register", "track", "depth_refinement"):
        row[f"{kind}_latency_seconds"] = timing.get(f"{kind}_latency_seconds", {}).get("mean")
    outcomes = report.get(
        "terminal_outcomes_evaluation_only", {"plug": report.get("final_evaluation_only", {})}
    )
    for obj, result in outcomes.items():
        for key, value in result.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                row[f"final_{obj}_{key}"] = value
    events = execution.get("events", [])
    row["disturbance_delivered"] = any(
        e["event"] in ("external_grasp_impulse_started", "environment_fixture_displaced", "external_alignment_impulse_started") for e in events
    )
    row["force_guard_count"] = sum(e["event"] == "force_guard_triggered" for e in events)
    row["simulation_seconds"] = report.get("simulation_seconds", report.get("simulation_time_s"))
    if report.get("visual_feedback", "legacy") != "legacy":
        stages = report.get("visual_servo", [])
        row["feedback_reached_stages"] = len(stages)
        row["feedback_observations"] = sum(len(s["observations"]) for s in stages)
        row["feedback_corrections"] = sum(s["corrections"] for s in stages)
        row["feedback_wall_seconds"] = sum(s["wall_seconds"] for s in stages)
        row["feedback_simulation_seconds"] = sum(s["simulation_seconds"] for s in stages)
        row["feedback_updates_per_wall_second"] = (
            row["feedback_observations"] / row["feedback_wall_seconds"]
            if row["feedback_observations"] and row["feedback_wall_seconds"] else None
        )
        observations = [o for s in stages for o in s["observations"]]
        row["feedback_measurement_age_simulation_s"] = mean([o["measurement_age_simulation_s"] for o in observations])
        row["feedback_cycle_wall_seconds"] = mean([o.get("cycle_wall_seconds") for o in observations])
        for stage in stages:
            name = stage["object_id"]
            row[f"feedback_{name}_converged"] = stage["converged"]
            row[f"feedback_{name}_corrections"] = stage["corrections"]
            row[f"feedback_{name}_wall_seconds"] = stage["wall_seconds"]
            row[f"feedback_{name}_visual_recovery_simulation_seconds"] = stage.get("visual_recovery_simulation_seconds")
            for point in ("before", "after"):
                for metric in ("translation_error_mm", "rotation_error_deg"):
                    row[f"alignment_{name}_{point}_{metric}"] = stage[point + "_evaluation_only"][metric]
        phase_map = {"hammer": "park_hammer", "screwdriver": "moving_driver_insertion",
                     "rack_frame": "install_frame", "spanner": "regrasp_and_hang_spanner"}
        for name, phase in phase_map.items():
            row[f"phase_{name}_entered"] = any(e["event"] == "task_phase" and e.get("phase") == phase for e in events)
            row[f"phase_{name}_success"] = report.get("outcomes", {}).get(name, {}).get("success", False)
    return row


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def summarize(source, output, *, allow_partial=False):
    protocol = json.loads((source / "protocol.json").read_text())
    config = protocol["config"]
    output.mkdir(parents=True, exist_ok=True)
    (output / "trials").mkdir(exist_ok=True)
    shutil.copy2(source / "protocol.json", output / "protocol.json")
    rows, reports, missing = [], {}, []
    for task, spec in config["tasks"].items():
        for method in configured_methods(spec):
            for condition in ("none", spec["disturbance"]):
                for seed in config["seeds"]:
                    name = trial_id(task, method, condition, seed)
                    path = source / "trials" / name / "summary.json"
                    if not path.exists():
                        missing.append(name)
                        continue
                    report = json.loads(path.read_text())
                    assert_valid_run(report, name)
                    if (report["task"], report["method"], report["disturbance"], report["seed"]) != (task, method, condition, seed):
                        raise ValueError(f"Trial labels do not match the scheduled configuration: {name}")
                    if (
                        report.get("control_source") == "ground_truth_diagnostic"
                        or report.get("model_free") is not True
                    ):
                        raise ValueError("Ground-truth diagnostics must never enter the visual benchmark")
                    reports[name] = report
                    rows.append(flatten(report, name))
                    shutil.copy2(path, output / "trials" / (name + ".json"))
    if missing and not allow_partial:
        raise RuntimeError(f"Evaluation incomplete: {len(missing)} missing trials")
    for task in config["tasks"]:
        for seed in config["seeds"]:
            fingerprints = {
                r.get("initial_scene_state_sha256")
                for r in reports.values()
                if r["task"] == task and r["seed"] == seed
            }
            if fingerprints and (None in fingerprints or len(fingerprints) != 1):
                raise RuntimeError(f"Unmatched initial scene in paired trial: {task}, seed {seed}")
    groups, pairs, robustness = [], [], []
    for task, spec in config["tasks"].items():
        methods = configured_methods(spec)
        reference = spec.get("reference", "full")
        for method in methods:
            for condition in ("none", spec["disturbance"]):
                subset = [
                    r for r in rows if (r["task"], r["method"], r["disturbance"]) == (task, method, condition)
                ]
                n, k = len(subset), sum(bool(r["success"]) for r in subset)
                metrics = sorted(
                    {
                        key
                        for r in subset
                        for key, value in r.items()
                        if key not in ("seed", "success")
                        and not key.endswith("within_5mm_5deg")
                        and isinstance(value, (int, float))
                        and not isinstance(value, bool)
                    }
                )
                groups.append(
                    {
                        "task": task,
                        "method": method,
                        "disturbance": condition,
                        "n_trials": n,
                        "successes": k,
                        "success_rate": k / n if n else None,
                        "success_ci95": wilson_interval(k, n),
                        "disturbance_delivered_trials": sum(r["disturbance_delivered"] for r in subset),
                        "initial_pose_accuracy": {
                            kind: {
                                "passed_trials": sum(
                                    r[f"pose_initial_{kind}_all_targets_accurate"] for r in subset
                                ),
                                "n_trials": n,
                                "rate": (
                                    sum(r[f"pose_initial_{kind}_all_targets_accurate"] for r in subset) / n
                                    if n
                                    else None
                                ),
                                "ci95": wilson_interval(
                                    sum(r[f"pose_initial_{kind}_all_targets_accurate"] for r in subset), n
                                ),
                                "criterion": "Every required initial target is estimated within 5 mm and 5 degrees; missing predictions fail",
                            }
                            for kind in ("raw", "control")
                        },
                        "metrics": {key: interval([r.get(key) for r in subset]) for key in metrics},
                        "phase_success": {
                            obj: {"successes": sum(bool(r.get(f"phase_{obj}_success")) for r in subset),
                                  "entered": sum(bool(r.get(f"phase_{obj}_entered")) for r in subset),
                                  "n_trials": n,
                                  "ci95": wilson_interval(sum(bool(r.get(f"phase_{obj}_success")) for r in subset), n)}
                            for obj in ("hammer", "screwdriver", "rack_frame", "spanner")
                            if obj in PRIMARY[task] and any(r.get(f"phase_{obj}_entered") for r in subset)
                        },
                    }
                )

        def outcomes(method, condition):
            return [reports[trial_id(task, method, condition, seed)]["success"] for seed in config["seeds"]]

        try:
            for condition in ("none", spec["disturbance"]):
                for baseline in methods:
                    if baseline == reference:
                        continue
                    pairs.append(
                        {
                            "task": task,
                            "disturbance": condition,
                            "a": reference,
                            "b": baseline,
                            **comparison(outcomes(reference, condition), outcomes(baseline, condition)),
                        }
                    )
            for method in methods:
                robustness.append(
                    {
                        "task": task,
                        "method": method,
                        "a": spec["disturbance"],
                        "b": "none",
                        **comparison(outcomes(method, spec["disturbance"]), outcomes(method, "none")),
                    }
                )
        except KeyError:
            pass
    for family in (pairs, robustness):
        running = 0.0
        for rank, index in enumerate(
            sorted(range(len(family)), key=lambda i: family[i]["exact_mcnemar_p_unadjusted"])
        ):
            running = max(
                running, min(1.0, (len(family) - rank) * family[index]["exact_mcnemar_p_unadjusted"])
            )
            family[index]["exact_mcnemar_p_holm_within_family"] = running
    selected = []
    for full, limit in ((True, 2), (False, 4)):
        candidates = []
        for task, spec in config["tasks"].items():
            reference = spec.get("reference", "full")
            for method in configured_methods(spec):
                if (method == reference) != full:
                    continue
                failed = [r for r in rows if r["task"] == task and r["method"] == method and not r["success"]]
                failed.sort(key=lambda r: (r["disturbance"] != "none", r["seed"]))
                if failed:
                    candidates.append(failed[0])
        selected.extend(candidates[:limit])
    result = {
        "paired_initial_scene_hashes_verified": True,
        "complete": not missing,
        "n_trials": len(rows),
        "missing_trials": missing,
        "groups": groups,
        "paired_module_comparisons": pairs,
        "dynamic_robustness": robustness,
        "failure_demos": [
            {k: row[k] for k in ("trial", "task", "method", "disturbance", "seed", "last_stage", "error")}
            for row in selected
        ],
        "calibration": next(iter(reports.values())).get("calibration_evaluation_only") if reports else None,
        "metric_notes": [
            "Success denominators retain every task failure; missing runs are never failures or successes.",
            "Primary pose metrics use first fixed-camera target observation per trial; all-observation metrics are diagnostic and depend on executed stages.",
            "Primary pose accuracy requires every initial target within 5 mm and 5 degrees, with a Wilson interval over trials. Per-observation threshold averages in trials.csv are descriptive only.",
            "Continuous intervals bootstrap trial means, not dependent video frames. Missing measurements have explicit n_trials.",
            "Final errors include failed terminal states where measurable. Simulation depth and wrist hand-eye calibration are ideal.",
            "Shared GPU serializes inference. Wall throughput includes CPU contention and queueing; fixed virtual sensor latency is separate.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    write_csv(output / "trials.csv", rows)
    pose_rows = []
    for name, report in reports.items():
        for index, s in enumerate(report.get("perception", [])):
            row = {
                "trial": name,
                "observation": index,
                **{
                    k: s.get(k)
                    for k in ("object_id", "camera", "operation", "capture_time_s", "inference_seconds")
                },
            }
            for kind in ("raw_estimator", "control_pose"):
                row.update(
                    {
                        f"{kind}_{k}": v
                        for k, v in s.get(kind + "_metrics_evaluation_only", {}).items()
                        if isinstance(v, (int, float, bool))
                    }
                )
            pose_rows.append(row)
    write_csv(output / "pose_observations.csv", pose_rows)
    print(json.dumps({"complete": result["complete"], "trials": len(rows), "failures": len(selected)}))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--allow-partial", action="store_true")
    args = p.parse_args()
    summarize(args.source, args.output, allow_partial=args.allow_partial)


if __name__ == "__main__":
    main()
