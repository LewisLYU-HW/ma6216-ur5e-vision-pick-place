"""Tool operations parameterized exclusively by reconstructed surfaces."""

from pathlib import Path

import cv2
import numpy as np
import trimesh

from .pose_insertion import transform
from .online_pose import PoseHistory
from .reconstructed import validate_bundle
from .scene import mujoco
from .task_control import TaskRecorder


class FeedPoseHistory(PoseHistory):
    """Visual velocity constrained to the feed carriage's surveyed rail axis.

    Keep the most recent measured height and full orientation. Extrapolating
    submillimetre depth noise over a long approach can drive the closed pads
    into the tray. No commanded speed or simulator object position is used.
    """

    def __init__(self, axis=(0.0, 1.0, 0.0)):
        super().__init__()
        axis = np.asarray(axis, dtype=float)
        if axis.shape != (3,) or not np.isfinite(axis).all() or np.linalg.norm(axis) < 1e-8:
            raise ValueError("Feed axis must be a finite nonzero 3-vector")
        self.axis = axis / np.linalg.norm(axis)

    @property
    def unconstrained_velocity(self):
        return super().velocity

    @property
    def velocity(self):
        return self.axis * (self.axis @ self.unconstrained_velocity)


def local_convex_parts(mesh, *, planar_holes=False):
    """Clip observed triangles into local cells before convexification.

    A single hull would fill the spanner eye. Small spatial cells preserve
    empty regions without consulting CAD or a hand-entered hole position.
    """
    lower, upper = mesh.bounds
    pieces = []
    step = 0.010 if planar_holes else 0.014
    xs = np.arange(np.floor(lower[0] / step) * step, upper[0] + step, step)
    ys = (
        np.arange(np.floor(lower[1] / step) * step, upper[1] + step, step)
        if planar_holes
        else [lower[1] - 1.0, upper[1] + 1.0]
    )
    for x0, x1 in zip(xs[:-1], xs[1:]):
        strip = mesh.slice_plane([x0, 0.0, 0.0], [1.0, 0.0, 0.0]).slice_plane(
            [x1, 0.0, 0.0], [-1.0, 0.0, 0.0]
        )
        for y0, y1 in zip(ys[:-1], ys[1:]):
            part = strip.slice_plane([0.0, y0, 0.0], [0.0, 1.0, 0.0]).slice_plane(
                [0.0, y1, 0.0], [0.0, -1.0, 0.0]
            )
            if len(part.vertices) < 4 or np.min(np.ptp(part.vertices, axis=0)) < 0.0001:
                continue
            hull = part.convex_hull
            if hull.volume > 1e-11:
                pieces.append(hull)
    if not pieces:
        raise ValueError("Reconstructed surface did not yield collision parts")
    return pieces


def eye_from_reconstruction(mesh):
    """Find the largest enclosed hole in an XY projection of observed faces."""
    scale = 0.00035
    origin = mesh.bounds[0, :2] - 0.004
    pixels = np.rint((mesh.vertices[:, :2] - origin) / scale).astype(np.int32)
    shape = pixels.max(axis=0) + 12
    silhouette = np.zeros((shape[1], shape[0]), dtype=np.uint8)
    for triangle in pixels[mesh.faces]:
        cv2.fillConvexPoly(silhouette, triangle, 255)
    contours, hierarchy = cv2.findContours(silhouette, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    holes = [c for i, c in enumerate(contours) if hierarchy[0, i, 3] >= 0 and cv2.contourArea(c) > 50]
    if not holes:
        raise ValueError("Reference reconstruction has no open hanging eye")
    contour = max(holes, key=cv2.contourArea)
    (cx, cy), radius = cv2.minEnclosingCircle(contour)
    centre = np.r_[origin + np.array([cx, cy]) * scale, mesh.bounds[:, 2].mean()]
    radius *= scale
    if not 0.009 < radius < 0.022:
        raise ValueError(f"Unusable reconstructed eye radius {radius}")
    return centre, float(radius)


class ReconstructedTool:
    def __init__(self, bundle):
        self.bundle = Path(bundle).resolve()
        manifest, path = validate_bundle(self.bundle)
        self.object_id = manifest["object_id"]
        self.body = {
            "hammer": "target_cube",
            "screwdriver": "target_screwdriver",
            "spanner": "target_spanner",
            "rack_frame": "target_cube",
        }[self.object_id]
        self.geom = self.body + "_geom"
        self.joint = self.body + "_freejoint"
        self.mesh = trimesh.load(path, force="mesh", process=False)
        self.vertices = self.mesh.vertices.copy()
        self.bounds = self.mesh.bounds.copy()
        if self.object_id == "rack_frame":
            # Slice along the long upright and the hook; a single XY strip
            # would incorrectly fill the empty inside corner of this L shape.
            scan = self.mesh.copy()
            swap = transform([0.0, 0.0, 0.0], np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]))
            scan.apply_transform(swap)
            self.pieces = local_convex_parts(scan, planar_holes=True)
            for piece in self.pieces:
                piece.apply_transform(np.linalg.inv(swap))
        else:
            self.pieces = local_convex_parts(self.mesh, planar_holes=self.object_id == "spanner")
        self.features = {"source": "RGB-D reconstruction in reference scan frame"}
        if self.object_id == "spanner":
            self.eye, self.eye_radius = eye_from_reconstruction(self.mesh)
            self.features.update(eye_centre_m=self.eye.tolist(), eye_radius_m=self.eye_radius)
        elif self.object_id == "rack_frame":
            front = self.vertices[self.vertices[:, 1] < self.bounds[0, 1] + 0.008]
            design = np.c_[2 * front, np.ones(len(front))]
            solution, *_ = np.linalg.lstsq(design, np.sum(front * front, axis=1), rcond=None)
            self.hook = solution[:3]
            radius = float(np.sqrt(max(0.0, solution[3] + self.hook @ self.hook)))
            if not 0.003 < radius < 0.012:
                raise ValueError(f"Unusable reconstructed hook tip: radius {radius}")
            post = self.vertices[(self.vertices[:, 2] > 0.06) & (self.vertices[:, 2] < 0.11)]
            self.frame_grasp = np.r_[np.median(post[:, :2], axis=0), 0.085]
            self.features.update(
                hook_centre_m=self.hook.tolist(),
                hook_tip_radius_m=radius,
                stem_bottom_z_m=float(self.bounds[0, 2]),
                grasp_point_m=self.frame_grasp.tolist(),
            )
        elif self.object_id == "screwdriver":
            shaft = self.vertices[self.vertices[:, 0] < self.bounds[0, 0] + 0.38 * np.ptp(self.bounds[:, 0])]
            centre = shaft.mean(axis=0)
            _, _, vt = np.linalg.svd(shaft - centre, full_matrices=False)
            axis = vt[0] if vt[0, 0] > 0 else -vt[0]
            projection = (shaft - centre) @ axis
            self.tip = centre + axis * np.percentile(projection, 0.5)
            y = np.array([0.0, 1.0, 0.0])
            y -= axis * (y @ axis)
            y /= np.linalg.norm(y)
            self.shaft_basis = np.column_stack([axis, y, np.cross(axis, y)])
            self.features.update(shaft_tip_m=self.tip.tolist(), shaft_axis=axis.tolist())

    def planning_part(self):
        return self

    def configure(self, spec):
        body = spec.body(self.body)
        if body is None:
            body = spec.worldbody.add_body(name=self.body)
            body.add_freejoint(name=self.joint)
        for i, piece in enumerate(self.pieces):
            name = self.geom if i == 0 else self.geom + f"_{i}"
            geom = spec.geom(name)
            if geom is None:
                geom = body.add_geom(name=name)
            mesh_name = self.object_id + f"_observed_cell_{i}"
            spec.add_mesh(
                name=mesh_name,
                uservert=piece.vertices.ravel().tolist(),
                userface=piece.faces.ravel().tolist(),
            )
            geom.type = mujoco.mjtGeom.mjGEOM_MESH
            geom.meshname = mesh_name
            geom.mass = 0.1 / len(self.pieces)
            geom.rgba = [0.5, 0.7, 0.7, 1.0]
            geom.group = 3

    def top_grasp(self, *, regrasp=False):
        if self.object_id == "spanner":
            position = np.array([-0.010 if regrasp else 0.015, 0.0, self.bounds[:, 2].mean() + 0.001])
        else:
            lo, hi = self.bounds[:, 0]
            x = hi - (0.018 if self.object_id == "hammer" else 0.038)
            band = self.vertices[np.abs(self.vertices[:, 0] - x) < 0.006]
            position = np.r_[x, (band.min(axis=0) + band.max(axis=0))[1:] / 2]
            position[2] += 0.005
        return transform(position, np.diag([1.0, -1.0, -1.0]))

    def acquisition_grasp(self, pose):
        if self.object_id == "rack_frame":
            point = (pose @ np.r_[self.frame_grasp, 1.0])[:3] + [0.0, 0.0, 0.002]
            x = -pose[:3, 2].copy()
            x[2] = 0.0
            if np.linalg.norm(x) < 1e-6:
                x = pose[:3, 0].copy()
                x[2] = 0.0
            x /= np.linalg.norm(x)
            z = np.array([0.0, 0.0, -1.0])
            y = np.cross(z, x)
            return np.linalg.inv(pose) @ transform(point, np.column_stack([x, y, z]))
        if self.object_id != "screwdriver":
            return self.top_grasp()
        # A nearly cylindrical handle has a weakly observable axial roll.
        # Locate its reconstructed centre and shaft axis using the full pose,
        # then choose a top approach instead of following that ambiguous roll.
        centre = self.top_grasp()[:3, 3] - [0.0, 0.0, 0.005]
        point = pose[:3, :3] @ centre + pose[:3, 3] + [0.0, 0.0, 0.005]
        x = pose[:3, :3] @ self.shaft_basis[:, 0]
        x[2] = 0.0
        x /= np.linalg.norm(x)
        z = np.array([0.0, 0.0, -1.0])
        y = np.cross(z, x)
        return np.linalg.inv(pose) @ transform(point, np.column_stack([x, y, z]))


class WorkshopRecorder(TaskRecorder):
    def __init__(self, model, output, enabled=True, source="REFERENCE RGB-D / FOUNDATIONPOSE"):
        self.model = model
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.renderer = mujoco.Renderer(model, height=720, width=960) if enabled else None
        self.writers = {}
        self.source = source
        self.next_frame = 0.0
        self.frames = 0
        self.last_stage = None
        self.pose_provider = None
        if enabled:
            for name, width in (("overview_wrist", 1920), ("overview", 960), ("wrist", 960)):
                self.writers[name] = cv2.VideoWriter(
                    str(self.output / (name + ".mp4")), cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (width, 720)
                )
                if not self.writers[name].isOpened():
                    self.close()
                    raise RuntimeError("Workshop video encoder failed")

    def capture(self, data, stage, details=""):
        if self.renderer is None or data.time + 1e-8 < self.next_frame:
            return
        frames = []
        for name, camera in (("overview", "overview"), ("wrist", "wrist_camera")):
            self.renderer.update_scene(data, camera=camera)
            self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = True
            frame = cv2.cvtColor(self.renderer.render(), cv2.COLOR_RGB2BGR)
            estimate = self.pose_provider() if self.pose_provider is not None else None
            if estimate is not None:
                object_id, pose = estimate
                cid = self.model.camera(camera).id
                camera_R_world = data.cam_xmat[cid].reshape(3, 3).T
                points = np.array([[0.0, 0.0, 0.0], [0.025, 0.0, 0.0], [0.0, 0.025, 0.0], [0.0, 0.0, 0.025]])
                world = points @ pose[:3, :3].T + pose[:3, 3]
                camera_points = (world - data.cam_xpos[cid]) @ camera_R_world.T
                camera_points *= np.array([1.0, -1.0, -1.0])
                if np.all(camera_points[:, 2] > 0.02):
                    focal = 360.0 / np.tan(np.deg2rad(self.model.cam_fovy[cid]) / 2)
                    pixels = np.rint(
                        camera_points[:, :2] / camera_points[:, 2, None] * focal + [479.5, 359.5]
                    ).astype(int)
                    if np.max(np.abs(pixels)) < 10000:
                        for endpoint, colour in zip(
                            pixels[1:], ((60, 70, 245), (85, 220, 85), (245, 130, 65))
                        ):
                            cv2.line(frame, tuple(pixels[0]), tuple(endpoint), colour, 2, cv2.LINE_AA)
                        cv2.putText(
                            frame,
                            object_id,
                            tuple(pixels[0] + [8, -8]),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45,
                            (250, 250, 250),
                            1,
                            cv2.LINE_AA,
                        )
            cv2.rectangle(frame, (0, 0), (960, 58), (29, 37, 43), -1)
            cv2.rectangle(frame, (0, 0), (7, 58), (65, 179, 231), -1)
            cv2.putText(
                frame,
                "MA6216  /  TOOL SERVICE",
                (22, 25),
                cv2.FONT_HERSHEY_DUPLEX,
                0.60,
                (239, 242, 244),
                1,
                cv2.LINE_AA,
            )
            tag = "DIAGNOSTIC POSE" if "DIAGNOSTIC" in self.source else "ESTIMATED TOOL POSE"
            cv2.putText(
                frame, tag, (710, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (165, 206, 221), 1, cv2.LINE_AA
            )
            cv2.putText(
                frame,
                stage.replace("_", " "),
                (22, 47),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.47,
                (165, 206, 221),
                1,
                cv2.LINE_AA,
            )
            cv2.rectangle(frame, (0, 690), (960, 720), (29, 37, 43), -1)
            cv2.putText(
                frame,
                f"{name.upper()}   |   {data.time:05.1f} s   |   {details}",
                (15, 710),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.47,
                (216, 226, 233),
                1,
                cv2.LINE_AA,
            )
            self.writers[name].write(frame)
            frames.append(frame)
        combined = np.concatenate(frames, axis=1)
        self.writers["overview_wrist"].write(combined)
        if stage != self.last_stage:
            cv2.imwrite(str(self.output / f"{self.frames:05d}_{stage.lower()}.png"), combined)
            self.last_stage = stage
        self.frames += 1
        self.next_frame = float(data.time) + 0.04 - 1e-8
