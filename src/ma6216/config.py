"""Discover local dependencies without embedding a developer's home directory."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def menagerie_dir() -> Path:
    """Find the external Menagerie checkout containing both robot assets."""
    configured = os.environ.get("MA6216_MENAGERIE_DIR")
    candidates = ([Path(configured).expanduser()] if configured else [
        project_root() / "third_party/mujoco_menagerie",
        Path.home() / "mujoco/mujoco_menagerie",
        Path.home() / "projects/mujoco_menagerie",
    ])
    for candidate in candidates:
        if (candidate / "universal_robots_ur5e/scene.xml").is_file() and (candidate / "robotiq_2f85/2f85.xml").is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "MuJoCo Menagerie assets were not found. Clone mujoco_menagerie into "
        "third_party/mujoco_menagerie or set MA6216_MENAGERIE_DIR to its checkout."
    )


def foundationpose_dir() -> Path:
    """Find the separately installed official FoundationPose implementation."""
    configured = os.environ.get("MA6216_FOUNDATIONPOSE_DIR")
    candidates = ([Path(configured).expanduser()] if configured else [
        project_root() / "third_party/FoundationPose",
        Path.home() / "projects/FoundationPose",
        Path.home() / "FoundationPose",
    ])
    for candidate in candidates:
        if (candidate / "estimater.py").is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "FoundationPose was not found. Clone the official repository into "
        "third_party/FoundationPose or set MA6216_FOUNDATIONPOSE_DIR to its checkout."
    )


def ensure_mujoco_available() -> None:
    """Prefer the active environment, retaining an explicit compatibility bridge.

    The original workstation has separate FoundationPose and MuJoCo Python 3.11
    environments. A fresh installation can install MuJoCo in its active Python.
    MA6216_MUJOCO_PYTHONPATH optionally points at an existing compatible package
    directory; multiple entries use the platform's normal path separator.
    """
    if importlib.util.find_spec("mujoco") is not None:
        return
    configured = os.environ.get("MA6216_MUJOCO_PYTHONPATH")
    if configured:
        candidates = [Path(part).expanduser() for part in configured.split(os.pathsep) if part]
    else:
        version = f"python{sys.version_info.major}.{sys.version_info.minor}"
        candidates = [Path.home() / "miniconda3/envs/mujoco-env/lib" / version / "site-packages"]
    for candidate in candidates:
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.append(str(candidate))
    importlib.invalidate_caches()
    if importlib.util.find_spec("mujoco") is None:
        raise ModuleNotFoundError(
            "MuJoCo is unavailable in this Python. Install mujoco==3.17.0 in "
            "the active environment, or set MA6216_MUJOCO_PYTHONPATH to a "
            "compatible existing site-packages directory."
        )
