"""Archive all trial logs and the original trajectories selected for video replay."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def digest(path):
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--results", type=Path, required=True)
    args = p.parse_args()
    result = json.loads((args.results / "summary.json").read_text())
    if not result["complete"]:
        raise RuntimeError("Package evidence only after every scheduled trial has completed")
    reports = {p.stem: json.loads(p.read_text()) for p in sorted((args.results / "trials").glob("*.json"))}
    config = json.loads((args.results / "protocol.json").read_text())["config"]
    hero_task = "complete" if "complete" in config["tasks"] else "rack"
    reference = config["tasks"].get(hero_task, {}).get("reference", "full")
    rack_successes = sorted(
        (
            r
            for r in reports.values()
            if r["task"] == hero_task and r["method"] == reference and r["disturbance"] == "none" and r["success"]
        ),
        key=lambda r: r["seed"],
    )
    hero = f"{hero_task}__{reference}__none__{rack_successes[0]['seed']}" if rack_successes else None
    selected = [r["trial"] for r in result["failure_demos"]] + ([hero] if hero else [])
    paired_controls = {}
    for demo in result["failure_demos"]:
        reference = config["tasks"][demo["task"]].get("reference", "full")
        if demo["method"] != reference:
            full = f"{demo['task']}__{reference}__{demo['disturbance']}__{demo['seed']}"
            if full not in reports:
                raise RuntimeError(f"Missing paired full-method trial: {full}")
            paired_controls[demo["trial"]] = full
            selected.append(full)  # Include the matched outcome whether it succeeds or fails.
    selected = list(dict.fromkeys(selected))
    evidence = {
        "source_directory": str(args.source),
        "rack_success_demo": hero,
        "success_demo": hero,
        "paired_full_method_replays": paired_controls,
        "replay_inputs": selected,
        "trials": {},
        "note": "All raw RGB-D, motion measurements and trajectories remain in source_directory. "
        "All summaries and console logs, plus original selected video trajectories, are committed.",
    }
    (args.results / "logs").mkdir(exist_ok=True)
    for name in reports:
        source = args.source / "trials" / name
        if digest(source / "summary.json") != digest(args.results / "trials" / (name + ".json")):
            raise RuntimeError(f"Summary changed after aggregation: {name}")
        files = (
            "summary.json",
            "motion/trajectory_evaluation_only.npz",
            "final_state_evaluation_only.npz",
            "motion/samples.json",
            "motion/endpoints.json",
            "motion/events.json",
            "observations.tar.gz",
            "observations_archive.json",
        )
        hashes = {key: digest(source / key) for key in files if (source / key).exists()}
        if "motion/trajectory_evaluation_only.npz" not in hashes:
            raise RuntimeError(f"Missing original trajectory: {name}")
        log = args.source / "logs" / (name + ".log")
        shutil.copy2(log, args.results / "logs" / log.name)
        hashes["console.log"] = digest(log)
        evidence["trials"][name] = hashes
        if name in selected:
            destination = args.results / "replay_inputs" / name
            (destination / "motion").mkdir(parents=True, exist_ok=True)
            for key in (
                "summary.json",
                "motion/trajectory_evaluation_only.npz",
                "final_state_evaluation_only.npz",
                "motion/events.json",
                "motion/endpoints.json",
            ):
                shutil.copy2(source / key, destination / key)
    shutil.copy2(args.source / "schedule.json", args.results / "schedule.json")
    if (args.source / "hardware.json").exists():
        shutil.copy2(args.source / "hardware.json", args.results / "hardware.json")
    if (args.source / "infrastructure_incidents").exists():
        shutil.copytree(
            args.source / "infrastructure_incidents",
            args.results / "infrastructure_incidents",
            dirs_exist_ok=True,
        )
    (args.results / "evidence_manifest.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"trials": len(reports), "original_replay_inputs": selected}))


if __name__ == "__main__":
    main()
