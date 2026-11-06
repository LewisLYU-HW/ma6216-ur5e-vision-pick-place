"""Read-only dependency and model checks for a fresh MA6216 checkout."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ma6216.config import ensure_mujoco_available, foundationpose_dir, menagerie_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--simulation-only", action="store_true", help="Check simulation dependencies (default)")
    mode.add_argument("--vision", action="store_true", help="Also check FoundationPose, CUDA and pretrained weights")
    parser.add_argument("--json", action="store_true", help="Print machine-readable check results")
    args = parser.parse_args()
    checks = []

    def check(name, operation):
        try:
            detail = operation()
            checks.append({"name": name, "ok": True, "detail": str(detail)})
            return detail
        except Exception as exc:
            checks.append({"name": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
            return None

    checks.append({"name": "Python", "ok": True, "detail": f"{sys.version.split()[0]} at {sys.executable}"})
    def mujoco_import_path():
        ensure_mujoco_available()
        return importlib.import_module("mujoco").__file__
    check("MuJoCo import path", mujoco_import_path)
    for name in ("numpy", "scipy", "cv2", "trimesh", "mujoco"):
        check(name, lambda name=name: getattr(importlib.import_module(name), "__version__", "imported"))
    assets = check("Menagerie robot assets", menagerie_dir)
    if assets is not None and all(item["ok"] for item in checks):
        def compile_model():
            from ma6216.scene import build_scene

            model, _ = build_scene(calibration_board=False)
            return f"Compiled UR5e + Robotiq, nq={model.nq}, nv={model.nv}, actuators={model.nu}"
        check("Workcell compilation", compile_model)

    if args.vision:
        repository = check("FoundationPose repository", foundationpose_dir)
        for name in ("torch", "nvdiffrast.torch", "pytorch3d"):
            check(name, lambda name=name: getattr(importlib.import_module(name), "__version__", "imported"))
        def cuda_device():
            import torch

            if not torch.cuda.is_available():
                raise RuntimeError("CUDA is unavailable to the active PyTorch installation")
            return torch.cuda.get_device_name(0)
        check("CUDA device", cuda_device)
        if repository is not None:
            for relative in ("weights/2023-10-28-18-33-37/model_best.pth",
                             "weights/2024-01-11-20-02-45/model_best.pth"):
                def weight_file(relative=relative):
                    path = repository / relative
                    if not path.is_file() or path.stat().st_size == 0:
                        raise FileNotFoundError(f"Download the official weight file to {path}")
                    return path
                check(relative, weight_file)

    successful = all(item["ok"] for item in checks)
    if args.json:
        print(json.dumps({"ok": successful, "vision": args.vision, "checks": checks}, indent=2))
    else:
        for item in checks:
            print(f"[{'OK' if item['ok'] else 'FAIL'}] {item['name']}: {item['detail']}")
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
