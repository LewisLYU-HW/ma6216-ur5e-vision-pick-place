"""Check archived results, original source hashes and full video decodability."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
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
    expected = 4 * len(config["tasks"]) * len(config["seeds"])
    assert result["complete"] and result["n_trials"] == expected
    assert result["paired_initial_scene_hashes_verified"]
    assert len(evidence["trials"]) == expected
    assert len(result["groups"]) == 4 * len(config["tasks"])
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
    assert videos["protocol_sha256"] == sha(args.results / "protocol.json")
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
        "configurations_with_10_trials": len(result["groups"]) if len(config["seeds"]) == 10 else None,
        "paired_initial_scene_hashes_verified": True,
        "frozen_control_source_files_verified": len(protocol["sources_sha256"]),
        "original_replay_inputs_verified": len(evidence["replay_inputs"]),
        "local_document_links_verified": links,
        "videos": checked_videos,
    }
    (args.results / "validation.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "videos"}))


if __name__ == "__main__":
    main()
