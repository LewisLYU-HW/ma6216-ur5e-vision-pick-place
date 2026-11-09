"""Check archived results, original source hashes and full video decodability."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--videos", type=Path, required=True)
    parser.add_argument("--documents", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    protocol = json.loads((args.results / "protocol.json").read_text())
    result = json.loads((args.results / "summary.json").read_text())
    evidence = json.loads((args.results / "evidence_manifest.json").read_text())
    videos = json.loads((args.videos / "manifest.json").read_text())
    config = protocol["config"]
    n_groups = sum(2 * len(spec.get("methods", ["full", spec.get("baseline")])) for spec in config["tasks"].values())
    expected = n_groups * len(config["seeds"])
    assert result["complete"] and result["n_trials"] == expected
    assert result["paired_initial_scene_hashes_verified"]
    assert len(evidence["trials"]) == expected
    assert len(result["groups"]) == n_groups
    assert all(g["n_trials"] == len(config["seeds"]) for g in result["groups"])
    for name, digest in protocol["sources_sha256"].items():
        assert sha(ROOT / name) == digest, f"Control source changed: {name}"
    for name, records in evidence["trials"].items():
        for key, record in records.items():
            if key == "console.log":
                source = args.source / "logs" / (name + ".log")
                archive = args.results / "logs" / (name + ".log")
                assert sha(archive) == record["sha256"], str(archive)
            else:
                source = args.source / "trials" / name / key
            assert sha(source) == record["sha256"], str(source)
        assert sha(args.results / "trials" / (name + ".json")) == records["summary.json"]["sha256"]
        if name in evidence["replay_inputs"]:
            for key in (
                "summary.json",
                "motion/trajectory_evaluation_only.npz",
                "final_state_evaluation_only.npz",
            ):
                archived = args.results / "replay_inputs" / name / key
                assert sha(archived) == records[key]["sha256"], str(archived)
    feedback_observations_verified = None
    feedback_csv = args.results / "visual_feedback_observations.csv"
    if feedback_csv.exists():
        expected_observations = {}
        for path in (args.results / "trials").glob("*.json"):
            for stage in json.loads(path.read_text()).get("visual_servo", []):
                for observation in stage["observations"]:
                    key = (path.stem, stage["object_id"], observation["iteration"])
                    assert key not in expected_observations, f"Duplicate source observation: {key}"
                    expected_observations[key] = observation
        with feedback_csv.open(newline="") as stream:
            observations = list(csv.DictReader(stream))
        assert len(observations) == len(expected_observations)
        for row in observations:
            key = (row["trial"], row["object_id"], int(row["iteration"]))
            original = expected_observations.pop(key)
            fields = {
                "visual_translation_error_mm": original.get("translation_error_mm"),
                "visual_rotation_error_deg": original.get("rotation_error_deg"),
                "true_alignment_translation_error_mm": original.get("alignment_evaluation_only", {}).get("translation_error_mm"),
                "true_alignment_rotation_error_deg": original.get("alignment_evaluation_only", {}).get("rotation_error_deg"),
                "proposed_tcp_translation_mm": original.get("command_translation_mm"),
                "proposed_tcp_rotation_deg": original.get("command_rotation_deg"),
            }
            for field, value in fields.items():
                assert (row[field] == "" if value is None else math.isclose(float(row[field]), value, rel_tol=1e-12, abs_tol=1e-12)), (key, field)
        assert not expected_observations
        feedback_observations_verified = len(observations)
    assert videos["protocol_sha256"] == sha(args.results / "protocol.json")
    hero_audit = None
    audit_path = args.results / "hero_motion_audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        hero = evidence["success_demo"]
        assert audit["trial"] == hero
        assert audit["trajectory_sha256"] == evidence["trials"][hero]["motion/trajectory_evaluation_only.npz"]["sha256"]
        assert audit["final_state_sha256"] == evidence["trials"][hero]["final_state_evaluation_only.npz"]["sha256"]
        hero_audit = {
            "original_state_hashes_verified": True,
            "unexpected_contact_candidates": len(audit["unexpected_robot_contacts_above_0_01mm"]),
            "loaded_gripper_contacts_after_release": len(audit["loaded_gripper_contacts_after_final_release"]),
            "extension_30s_all_checkpoints_passed": all(
                all(step[name]["success"] for name in audit["recorded_final_state"])
                for step in audit["passive_extension_30s_diagnostic_only"]),
        }
    checked_videos = []
    for name, record in videos["videos"].items():
        video = args.videos / name
        assert sha(video) == record["sha256"], str(video)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-xerror", "-threads", "2", "-i", str(video), "-f", "null", "-"],
            check=True,
        )
        checked_videos.append(
            dict(
                video=name,
                frames=record["nb_frames"],
                duration_s=record["duration_s"],
                sha256=record["sha256"],
                complete_decode="pass",
            )
        )
    checks = {}
    for path in (args.results / "validation").glob("*.log"):
        log = path.read_text()
        count = re.search(r"Ran (\d+) tests? in", log)
        assert count and re.search(r"^OK$", log, re.M), str(path)
        checks[path.stem] = int(count.group(1))
    links = 0
    for document in args.documents:
        for target in re.findall(r"\]\(([^\s)]+)(?:\s+[^)]*)?\)", document.read_text()):
            if re.match(r"[a-zA-Z]+:", target) or target.startswith("#"):
                continue
            target = target.split("#", 1)[0]
            if target:
                assert (document.parent / target).exists(), f"Broken link: {document}: {target}"
                links += 1
    output = {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "automated_regression_checks": {**checks, "total": sum(checks.values()), "logs": "validation/"},
        "original_data_hashes_verified_trials": expected,
        "configurations_verified": len(result["groups"]),
        "trials_per_configuration": len(config["seeds"]),
        "configurations_with_10_trials": len(result["groups"]) if len(config["seeds"]) == 10 else None,
        "paired_initial_scene_hashes_verified": True,
        "frozen_control_source_files_verified": len(protocol["sources_sha256"]),
        "original_replay_inputs_verified": len(evidence["replay_inputs"]),
        "feedback_observations_verified": feedback_observations_verified,
        "hero_motion_audit": hero_audit,
        "local_document_links_verified": links,
        "videos": checked_videos,
    }
    (args.results / "validation.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "videos"}))


if __name__ == "__main__":
    main()
