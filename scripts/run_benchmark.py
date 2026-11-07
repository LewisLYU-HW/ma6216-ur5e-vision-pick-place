"""Run a frozen, paired evaluation matrix without replacing unsuccessful trials."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CONTROL_FILES = [
    "scripts/run_model_free_task.py",
    "scripts/run_workshop.py",
    "scripts/serve_model_free_pose.py",
    "scripts/serve_pose_pool.py",
    *[str(p.relative_to(ROOT)) for p in sorted((ROOT / "src/ma6216").glob("*.py"))],
    *[str(p.relative_to(ROOT)) for p in sorted((ROOT / "assets/reconstructed").rglob("model_free.json"))],
    "demo_data/calibration/estimated/cam_K.txt",
    "demo_data/calibration/estimated/world_T_camera.txt",
]


def manifest():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in CONTROL_FILES}


def trial_id(task, method, condition, seed):
    return f"{task}__{method}__{condition}__{seed}"


def assert_valid_run(report, name):
    required = ("initial_scene_state_sha256", "execution", "timing")
    missing = [key for key in required if not report.get(key)]
    if missing:
        raise RuntimeError(f"Incomplete initialization is not a task failure: {name}; missing {missing}")
    message = report.get("error") or ""
    infrastructure = (
        "CUDA out of memory",
        "Pose worker exited",
        "Shared GPU worker",
        "did not initialize",
        "Connection refused",
        "ModuleNotFoundError",
        "Pose request ",
        "empty PNG file",
    )
    if any(token in message for token in infrastructure):
        raise RuntimeError(f"Infrastructure failure must be investigated, not scored: {name}: {message}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=ROOT / "configs/evaluation_v1.json")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--tasks", nargs="+")
    p.add_argument(
        "--foundationpose-python", type=Path, default=Path("/home/arm-pc/miniconda3/envs/any6d/bin/python")
    )
    p.add_argument("--timeout", type=int, default=1200)
    args = p.parse_args()
    if args.jobs < 1 or (args.jobs > 1 and not os.environ.get("MA6216_POSE_SOCKET")):
        p.error("Use --jobs 1 or a shared MA6216_POSE_SOCKET to avoid GPU memory contention")
    if os.environ.get("MA6216_POSE_SOCKET") and not Path(os.environ["MA6216_POSE_SOCKET"]).exists():
        p.error("The shared GPU socket does not exist; start serve_pose_pool.py first")
    config = json.loads(args.config.read_text())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    frozen = {
        "config": config,
        "sources_sha256": manifest(),
        "git_parent": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    }
    path = output / "protocol.json"
    if path.exists():
        previous = json.loads(path.read_text())
        if previous["config"] != frozen["config"] or previous["sources_sha256"] != frozen["sources_sha256"]:
            raise RuntimeError("Protocol or control code changed; use a new evaluation directory")
    else:
        frozen["created_utc"] = datetime.now(timezone.utc).isoformat()
        frozen["runtime"] = {
            "python": sys.version,
            "platform": platform.platform(),
            "parallel_trials": args.jobs,
            "foundationpose_python": str(args.foundationpose_python),
            "versions": {name: version(name) for name in ("mujoco", "numpy", "scipy", "trimesh")},
        }
        frozen["network_weights_sha256"] = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "third_party/FoundationPose/weights").rglob("*")
            if p.is_file()
        }
        path.write_text(json.dumps(frozen, indent=2) + "\n")
    schedule = []
    for task, spec in config["tasks"].items():
        if args.tasks and task not in args.tasks:
            continue
        for seed in config["seeds"]:
            for condition in ("none", spec["disturbance"]):
                for method in ("full", spec["baseline"]):
                    schedule.append((task, method, condition, seed))
    random.Random(config["schedule_seed"]).shuffle(schedule)
    (output / "schedule.json").write_text(json.dumps(schedule, indent=2) + "\n")
    (output / "logs").mkdir(exist_ok=True)
    environment = dict(
        os.environ,
        MUJOCO_GL="egl",
        PYOPENGL_PLATFORM="egl",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MA6216_BENCHMARK_PARALLEL_TRIALS=str(args.jobs),
    )

    def run(item):
        task, method, condition, seed = item
        name = trial_id(*item)
        folder = output / "trials" / name
        result_file = folder / "summary.json"
        if result_file.exists():
            result = json.loads(result_file.read_text())
            assert_valid_run(result, name)
            return name, result.get("success", False), "retained existing trial"
        if folder.exists():
            raise RuntimeError(f"Incomplete trial must be investigated before resume: {folder}")
        if manifest() != frozen["sources_sha256"]:
            raise RuntimeError("Control source changed during the frozen benchmark")
        runner = (
            "run_model_free_task.py" if task in ("assembly", "clutter", "conveyor") else "run_workshop.py"
        )
        command = [
            sys.executable,
            str(ROOT / "scripts" / runner),
            "--task",
            task,
            "--method",
            method,
            "--disturbance",
            condition,
            "--seed",
            str(seed),
            "--trace",
            "--sensor-delay",
            str(config["fixed_virtual_sensor_delay_s"]),
            "--output",
            str(folder),
            "--foundationpose-python",
            str(args.foundationpose_python),
        ]
        if runner == "run_model_free_task.py":
            command += ["--plug-model", str(ROOT / "assets/reconstructed/plug")]
            if task == "clutter":
                command += ["--blocker-model", str(ROOT / "assets/reconstructed/blocker")]
        with (output / "logs" / (name + ".log")).open("w") as log:
            child = subprocess.Popen(
                command,
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                child.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=20)
        if not result_file.exists():
            raise RuntimeError(
                f"Infrastructure failure (not scored as task failure): {name}; inspect its log"
            )
        result = json.loads(result_file.read_text())
        assert_valid_run(result, name)
        return name, result["success"], result.get("last_stage")

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {executor.submit(run, item): item for item in schedule}
        completed = 0
        for future in as_completed(futures):
            name, success, stage = future.result()
            completed += 1
            print(
                json.dumps(
                    {
                        "completed": completed,
                        "total": len(schedule),
                        "trial": name,
                        "success": success,
                        "stage": stage,
                        "elapsed_s": time.monotonic() - started,
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
