"""English report for the complete estimated-wrist replication; no new statistics."""
import argparse
from collections import Counter
import json
from pathlib import Path


def interval(value, digits=2, scale=1):
    if not value or value.get("mean") is None:
        return "N/A"
    lo, hi = value["ci95"]
    if lo is None or hi is None:
        return f"{value['mean']*scale:.{digits}f} [CI unavailable], n={value['n_trials']}"
    return f"{value['mean']*scale:.{digits}f} [{lo*scale:.{digits}f}, {hi*scale:.{digits}f}], n={value['n_trials']}"


def write_report(folder):
    s = json.loads((folder / "summary.json").read_text())
    p = json.loads((folder / "protocol.json").read_text())
    if not s["complete"] or s["n_trials"] != 48 or not s["paired_initial_scene_hashes_verified"]:
        raise ValueError("A complete, paired 48-trial matrix is required")
    wrist = s["calibration"]["wrist_hand_eye"]
    if not wrist.get("measured_error"):
        raise ValueError("This report requires estimated wrist calibration")
    reports = [json.loads(f.read_text()) for f in sorted((folder / "trials").glob("*.json"))]
    if len(reports) != 48:
        raise ValueError("Publish all 48 raw summaries before writing the report")
    lines = []

    def add(text=""):
        lines.extend([text, ""])

    def table(headers, rows):
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join("---" for _ in headers) + "|")
        for row in rows:
            lines.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in row) + " |")
        lines.append("")

    def label(g):
        return [g["method"], g["disturbance"]]

    def metric(g, name):
        return interval(g["metrics"].get(name))

    add("# Estimated-wrist visual feedback: 48 paired trials")
    add("Three feedback modes × two disturbance conditions × eight seeds = 48 complete-sequence attempts. "
        "The seeds 400–407 were used previously; seed400 also supported integration checks. "
        "This is a paired replication with estimated camera calibration, not a new unseen holdout. "
        "Historical ideal-wrist results and the two integration demonstrations are not pooled into this study.")
    add(f"Frozen control parent: `{p['git_parent']}`. Protocol timestamp: `{p['created_utc']}`. "
        f"{p['runtime']['parallel_trials']} CPU simulations share serial GPU inference. "
        "The protocol records exact control/calibration hashes; failures remain in the denominator.")
    add("[Protocol](protocol.json) · [Hardware](hardware.json) · [All trial metrics](trials.csv) · "
        "[Pose observations](pose_observations.csv) · [Feedback observations](visual_feedback_observations.csv) · "
        "[All raw summaries](trials/) · [Technical selection](../../LITERATURE_AND_SELECTION.md)")
    add("## Manipulation success")
    table(["Mode", "Disturbance", "Success / attempts", "Rate", "Wilson 95% CI", "Disturbance delivered"],
          [label(g) + [f"{g['successes']}/{g['n_trials']}", f"{g['success_rate']:.1%}",
                      f"{g['success_ci95'][0]:.1%}–{g['success_ci95'][1]:.1%}", g["disturbance_delivered_trials"]]
           for g in s["groups"]])
    add("Success requires the final physical acceptance of all four objects after release. "
        "Earlier-stage completion does not replace final whole-sequence acceptance. "
        "Trials failing before a scheduled disturbance still count; delivery is reported separately.")
    add("![Success and uncertainty](figures/success_rates.png)")
    add("## Paired comparisons and disturbance robustness")
    for title, key in [("Feedback modes", "paired_module_comparisons"), ("Disturbance versus none", "dynamic_robustness")]:
        add(f"### {title}")
        table(["Comparison / context", "Pairs", "Success difference A−B", "Conservative 95% CI", "A-only / B-only", "Exact p", "Holm p"],
              [[f"{r['a']} vs {r['b']} / {r.get('disturbance',r.get('method'))}", r["n_pairs"],
                f"{100*r['success_difference']:.1f} pp", f"{100*r['conservative_ci95'][0]:.1f} to {100*r['conservative_ci95'][1]:.1f} pp",
                f"{r['a_only_success']} / {r['b_only_success']}", f"{r['exact_mcnemar_p_unadjusted']:.4f}",
                f"{r['exact_mcnemar_p_holm_within_family']:.4f}"] for r in s[key]])
    if all(r["exact_mcnemar_p_holm_within_family"] >= .05 for r in s["paired_module_comparisons"]):
        add("None of the feedback-method comparisons passes the Holm-adjusted 0.05 threshold. "
            "These data do not establish superiority or equivalence. Report observed differences with their wide intervals.")
    add("![Paired differences](figures/paired_differences.png)")
    add("## Stage acceptance and reachability")
    stage_rows = []
    for g in s["groups"]:
        n = g["n_trials"]
        for obj in ("hammer", "screwdriver", "rack_frame", "spanner"):
            r = g["phase_success"].get(obj, {"entered": 0, "successes": 0, "n_trials": n,
                "ci95": [0., 1.959963984540054**2 / (n + 1.959963984540054**2)]})
            stage_rows.append(label(g) + [obj, r["entered"], f"{r['successes']}/{r['n_trials']}",
                                         f"{r['ci95'][0]:.1%}–{r['ci95'][1]:.1%}"])
    table(["Mode", "Disturbance", "Object/stage", "Entered", "Accepted / all attempts", "Wilson 95% CI"], stage_rows)
    add("These are stage outcomes within the same complete sequences, not independent task experiments.")
    sections = [
        ("6D pose estimation", [("Translation / mm", "pose_initial_raw_translation_error_mm"),
            ("Rotation / deg", "pose_initial_raw_rotation_error_deg"), ("ADD / mm", "pose_initial_raw_add_mm"),
            ("ADD-S / mm", "pose_initial_raw_adds_mm")]),
        ("Execution accuracy", [("TCP RMSE / mm", "tcp_tracking_translation_mm_rmse"),
            ("TCP RMSE / deg", "tcp_tracking_rotation_deg_rmse"),
            ("Endpoint mean / mm", "move_endpoint_translation_mm_mean"),
            ("Endpoint mean / deg", "move_endpoint_rotation_deg_mean")]),
        ("Frequency, latency and cost", [("Pose calls / wall s", "pose_calls_per_wall_second_including_waits"),
            ("Inference / s", "inference_latency_seconds"), ("Wall time / s", "wall_seconds"),
            ("Simulation / s", "simulation_seconds")]),
        ("Iterative feedback activity", [("Observations", "feedback_observations"), ("Corrections", "feedback_corrections"),
            ("Feedback wall time / s", "feedback_wall_seconds"), ("Feedback sim time / s", "feedback_simulation_seconds")]),
        ("Iterative observation timing", [("Updates / wall s", "feedback_updates_per_wall_second"),
            ("Cycle wall time / s", "feedback_cycle_wall_seconds"),
            ("Measurement age / sim s", "feedback_measurement_age_simulation_s")]),
        ("Visual recovery after delivered disturbances", [
            ("Screwdriver / sim s", "feedback_screwdriver_visual_recovery_simulation_seconds"),
            ("Rack / sim s", "feedback_rack_frame_visual_recovery_simulation_seconds"),
            ("Spanner / sim s", "feedback_spanner_visual_recovery_simulation_seconds")]),
    ]
    for title, metrics in sections:
        add("## " + title)
        table(["Mode", "Disturbance"] + [name for name, _ in metrics],
              [label(g) + [metric(g, key) for _, key in metrics] for g in s["groups"]])
        if title == "6D pose estimation":
            table(["Mode", "Disturbance", "All initial targets within 5 mm / 5 deg", "Wilson 95% CI"],
                  [label(g) + [f"{g['initial_pose_accuracy']['raw']['passed_trials']}/{g['n_trials']}",
                              f"{g['initial_pose_accuracy']['raw']['ci95'][0]:.1%}–{g['initial_pose_accuracy']['raw']['ci95'][1]:.1%}"] for g in s["groups"]])
    add("Continuous entries are means [bootstrap 95% CI] with their available trial count. "
        "Each trajectory is summarized before resampling; frames are not independent replicates. "
        "Initial pose metrics use the first fixed-camera observation of each required object. "
        "All-observation metrics have different observation schedules and are diagnostic only.")
    add("500 Hz is the physics/joint-control step rate, not the visual feedback rate. "
        "Inference/queue/planning pauses and shared GPU resources preclude a real-time hardware claim. "
        "End-to-end wall time also includes evaluation diagnostics, including downstream mask rendering; it is not isolated controller latency. "
        "The fixed virtual feedback delay is 0.15 s; moving-pickup observations use 1.0 s. "
        "Short failed trials must not be described as efficient task completion. Zero iterative-loop counters in staged mode do not mean no staged observations. "
        "Visual recovery times apply only to delivered disturbances followed by observed convergence; unavailable values are not zero recovery times, and convergence is not final physical success.")
    add("## Independent true alignment before and after feedback")
    rows = []
    for g in s["groups"]:
        for obj in ("screwdriver", "rack_frame", "spanner"):
            keys = [f"alignment_{obj}_{when}_{kind}_error_{unit}" for kind, unit in [("translation", "mm"), ("rotation", "deg")] for when in ("before", "after")]
            if any(g["metrics"].get(k) for k in keys):
                rows.append(label(g) + [obj] + [metric(g, k) for k in keys])
    table(["Mode", "Disturbance", "Stage", "Before / mm", "After / mm", "Before / deg", "After / deg"], rows)
    add("These conditional diagnostics include only reached stages. Different reachability prevents treating them as an unconditional causal comparison. "
        "Ground truth is used for scoring, not correction targets. Estimated residuals can decrease without improving true alignment. "
        "There is no matched-duration passive-wait fourth arm; changes during zero-action observations can reflect settling.")
    add("## Camera calibration")
    e = wrist["measured_error"]; fixed = s["calibration"]["fixed_extrinsic"]
    table(["Camera", "Translation error / mm", "Rotation error / deg", "Origin"],
          [["Fixed", f"{fixed['translation_error_mm']:.3f}", f"{fixed['rotation_error_deg']:.4f}", "Estimated 3D–2D calibration"],
           ["Wrist", f"{e['translation_error_mm']:.3f}", f"{e['rotation_error_deg']:.4f}", "Image/FK AX=XB estimation"]])
    add("The same calibration is reused throughout, not independently recalibrated 48 times. "
        "[Calibration images, splits and reproduction](../wrist-calibration-v1/README.md) · "
        "[Independent localization experiment](../workshop-localization-v1/README.md).")
    add("## Failures and evidence")
    failures = Counter((r["method"], r["disturbance"], r.get("last_stage"), r.get("error")) for r in reports if not r["success"])
    table(["Mode", "Disturbance", "Last stage", "Count", "Recorded reason"],
          [[*key[:3], count, key[3]] for key, count in sorted(failures.items(), key=lambda item: str(item[0]))])
    add("[Evidence selection and hashes](evidence_manifest.json) · [Original trial replays](../../videos/visual-feedback-calibrated-v1/README.md). "
        "Failure examples follow the protocol's seed-order rule; matched iterative trials are retained regardless of outcome. "
        "Replays do not rerun inference or replace failed attempts.")
    add("## Scope and engineering conclusions")
    add("The system connects independently estimated manipulation-camera calibration, image-based localization, reconstructed object references, "
        "6D pose estimation and physical manipulation. Overall success also depends on motion planning, pickup contacts and release stability. "
        "The evaluation compares feedback modules, not external pose estimators. Narrow layout variation, eight trials per configuration, ideal FK/depth, "
        "synthetic reference calibration and known pickup stations limit generalization. No task result is excluded to produce a favorable comparison.")
    add("All remaining per-group metrics, including terminal geometry, delivered-disturbance recovery and observation timing, "
        "are preserved with sample counts in [summary.json](summary.json) and [trials.csv](trials.csv).")
    add("## Independent publication checks")
    add("[Recomputed counts, intervals and calibration provenance](independent_counts_validation.json) · "
        "[Original main-video motion and passive-stability audit](hero_motion_audit.json) · "
        "[Data, source, feedback CSV and video validation](validation.json). "
        "The motion audit evaluates the saved 25 Hz states and a separate 30-second passive extension; "
        "it does not inspect every 500 Hz physics step or change the original trial outcome.")
    (folder / "README.md").write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    write_report(parser.parse_args().results)
