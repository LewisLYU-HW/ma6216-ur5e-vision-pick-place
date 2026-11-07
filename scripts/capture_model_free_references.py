"""Render calibrated reference RGB-D views; never export the simulator CAD."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ma6216.scene import look_at_quat, mujoco
from ma6216.simulation_objects import OBJECTS
from ma6216.workshop_assets import TOOLS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object", choices=(*OBJECTS, *TOOLS), default="plug")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--size", type=int, default=320)
    args = parser.parse_args()
    if not 160 <= args.size <= 960:
        parser.error("Reference image size must be in 160..960")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for folder in ("rgb", "depth", "masks", "scan_T_camera"):
        (output / folder).mkdir()
    workshop = args.object in TOOLS
    part = TOOLS[args.object] if workshop else OBJECTS[args.object]
    # The simulator needs geometry to generate observations. Only images and
    # calibrated scanner extrinsics cross into the reconstruction process.
    spec = mujoco.MjSpec()
    if workshop:
        part.add_visual(spec, spec.worldbody, name="reference_object")
    else:
        mesh = part.mesh()
        spec.add_mesh(name="simulated_object", uservert=mesh.vertices.ravel().tolist(),
                      userface=mesh.faces.ravel().tolist())
        spec.worldbody.add_geom(name="reference_object", type=mujoco.mjtGeom.mjGEOM_MESH,
                               meshname="simulated_object", rgba=part.rgba)
    radius = max(.22, float(np.linalg.norm(np.ptp(part.vertices, axis=0))) * 1.6)
    spec.worldbody.add_camera(name="scan_camera", pos=[.22, 0., 0.],
                              quat=look_at_quat([.22, 0., 0.], [0., 0., 0.]), fovy=45.)
    spec.visual.global_.offwidth = args.size
    spec.visual.global_.offheight = args.size
    spec.visual.headlight.ambient = [.5, .5, .5]
    spec.visual.headlight.diffuse = [.5, .5, .5]
    model = spec.compile()
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, height=args.size, width=args.size)
    cid = model.camera("scan_camera").id
    focal = .5 * args.size / np.tan(np.deg2rad(22.5))
    K = np.array([[focal, 0., (args.size - 1) / 2],
                  [0., focal, (args.size - 1) / 2], [0., 0., 1.]])
    np.savetxt(output / "cam_K.txt", K)
    frames = []
    try:
        for elevation in (-45., 0., 45.):
            for azimuth in np.arange(0., 360., 45.):
                a, e = np.deg2rad([azimuth, elevation])
                eye = radius * np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
                model.cam_pos[cid] = eye
                model.cam_quat[cid] = look_at_quat(eye, np.zeros(3))
                mujoco.mj_forward(model, data)
                renderer.update_scene(data, camera="scan_camera")
                renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
                renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
                rgb = renderer.render().copy()
                renderer.enable_depth_rendering()
                depth = renderer.render().astype(np.float32)
                renderer.disable_depth_rendering()
                # An isolated scan against a distant background admits an
                # ordinary metric-depth foreground mask, irrespective of UVs.
                mask = ((depth < 2 * radius) if workshop else part.mask(rgb)).astype(np.uint8) * 255
                # Ideal scanner calibration is explicitly part of this
                # synthetic reference protocol, not an object-pose label.
                rotation = np.empty(9)
                mujoco.mju_quat2Mat(rotation, model.cam_quat[cid])
                scan_T_camera = np.eye(4)
                scan_T_camera[:3, :3] = rotation.reshape(3, 3) @ np.diag([1., -1., -1.])
                scan_T_camera[:3, 3] = eye
                frame = f"{len(frames):06d}"
                cv2.imwrite(str(output / "rgb" / f"{frame}.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
                cv2.imwrite(str(output / "masks" / f"{frame}.png"), mask)
                np.save(output / "depth" / f"{frame}.npy", depth)
                np.savetxt(output / "scan_T_camera" / f"{frame}.txt", scan_T_camera)
                frames.append({"id": frame, "foreground_pixels": int(np.count_nonzero(mask))})
    finally:
        renderer.close()
    files = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(output.rglob("*")) if p.is_file()}
    manifest = {"object_id": args.object, "protocol": "synthetic calibrated multi-view RGB-D",
                "depth_units": "metres", "camera_convention": "OpenCV +x right, +y down, +z forward",
                "reference_frame": "stationary scanner frame; object remains fixed during capture",
                "camera_calibration": "ideal known synthetic scan rig; no object-pose files",
                "scan_views": len(frames), "frames": frames, "files_sha256": files,
                "cad_exported_to_reconstruction": False,
                "simulation_geometry_used_only_for_rendering": True}
    manifest["foreground_method"] = "isolated scanner depth threshold" if workshop else "HSV foreground"
    (output / "references.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(output), "views": len(frames), "CAD_exported": False}))


if __name__ == "__main__":
    main()
