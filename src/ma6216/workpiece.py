"""Metric, asymmetric workpiece shared by MuJoCo and FoundationPose."""
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial import ConvexHull
import trimesh

from .scene import mujoco


@dataclass(frozen=True)
class Workpiece:
    size_m: tuple[float, float, float] = (.074, .040, .044)
    object_z: float = .398
    grasp_offset_z: float = .003
    grasp_axis: int = 1
    mass_kg: float = .10
    rgba: tuple[float, float, float, float] = (.08, .68, .33, 1.)

    @property
    def vertices(self):
        """The +X/-Y corner is cropped and the -X top edge is beveled."""
        footprint = [(-37, -20), (18, -20), (37, -5), (37, 20), (-37, 20)]
        base = [(x, y, -22) for x, y in footprint]
        top = [(x, y, 8 if x == -37 else 22) for x, y in footprint]
        bevel = [(-20, -20, 22), (-20, 20, 22)]
        return np.asarray(base + top + bevel, dtype=float) / 1000.

    def mesh(self):
        vertices = self.vertices
        hull = ConvexHull(vertices)
        faces = hull.simplices.copy()
        # Qhull's simplices need a consistent outward triangle winding.
        triangles = vertices[faces]
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        inward = np.einsum("ij,ij->i", normals, hull.equations[:, :3]) < 0
        faces[inward] = faces[inward][:, [0, 2, 1]]
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        mesh.visual.vertex_colors = np.tile(np.rint(255 * np.asarray(self.rgba)).astype(np.uint8), (len(vertices), 1))
        return mesh


WORKPIECE = Workpiece()


def configure_workpiece(spec):
    """Replace the legacy target geom before compilation; the joint stays free."""
    mesh = WORKPIECE.mesh()
    spec.add_mesh(name="chamfered_workpiece", uservert=mesh.vertices.ravel().tolist(),
                  userface=mesh.faces.ravel().tolist())
    geom = spec.geom("target_cube_geom")
    geom.type = mujoco.mjtGeom.mjGEOM_MESH
    geom.meshname = "chamfered_workpiece"
    geom.rgba = WORKPIECE.rgba
    geom.mass = WORKPIECE.mass_kg


def export_mesh(path):
    """Save the same metric triangles used by the simulator, with vertex colour."""
    path = Path(path)
    if path.suffix.lower() != ".obj":
        raise ValueError("The workpiece exporter requires an .obj path")
    WORKPIECE.mesh().export(str(path))


def workpiece_mask(rgb):
    """Select the green component using the rendered RGB image only."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    green = cv2.inRange(hsv, (46, 75, 38), (95, 255, 255))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(green)
    if count < 2:
        raise RuntimeError("No green workpiece visible")
    component = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    if stats[component, cv2.CC_STAT_AREA] < 40:
        raise RuntimeError("Too few workpiece image pixels")
    return labels == component
