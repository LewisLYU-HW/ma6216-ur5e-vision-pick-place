"""Validate the image-reconstruction bundle shared by perception and planning."""
import hashlib
import json
from pathlib import Path


def validate_bundle(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder / "model_free.json").read_text())
    if (not manifest.get("success") or manifest.get("cad_used_for_reconstruction") is not False
            or manifest.get("object_pose_ground_truth_input") is not False):
        raise ValueError("A successful image-only reconstructed model is required")
    mesh = (folder / manifest["mesh_file"]).resolve()
    if folder not in mesh.parents or manifest["mesh_file"] not in manifest["files_sha256"]:
        raise ValueError("Reconstructed mesh must be a checksummed bundle member")
    for relative, expected in manifest["files_sha256"].items():
        path = (folder / relative).resolve()
        if folder not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Reconstructed asset integrity failure: {relative}")
    return manifest, mesh
