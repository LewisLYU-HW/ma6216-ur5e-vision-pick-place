"""Three printable convex parts with CAD, colour and grasp configuration."""
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial import ConvexHull
import trimesh

from .workpiece import WORKPIECE


@dataclass(frozen=True)
class Part:
    key: str
    title: str
    vertices_mm: tuple
    rgba: tuple
    hsv_lower: tuple
    hsv_upper: tuple
    body: str
    xy: tuple
    destination_xy: tuple
    mass_kg: float = .10
    grasp_offset_z: float = .003

    @property
    def vertices(self):
        return np.asarray(self.vertices_mm, dtype=float) / 1000

    @property
    def half_height(self):
        return float(-self.vertices[:, 2].min())

    @property
    def geom(self):
        return "target_cube_geom" if self.key == "green" else self.body + "_geom"

    @property
    def joint(self):
        return "target_cube_freejoint" if self.key == "green" else self.body + "_freejoint"

    def mesh(self):
        points = self.vertices
        hull = ConvexHull(points)
        faces = hull.simplices.copy()
        triangles = points[faces]
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        inward = np.einsum("ij,ij->i", normals, hull.equations[:, :3]) < 0
        faces[inward] = faces[inward][:, [0, 2, 1]]
        mesh = trimesh.Trimesh(vertices=points, faces=faces, process=False)
        mesh.visual.vertex_colors = np.tile(np.rint(255*np.asarray(self.rgba)).astype(np.uint8), (len(points), 1))
        return mesh

    def export_mesh(self, path):
        self.mesh().export(str(path))

    def mask(self, rgb):
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        binary = cv2.inRange(hsv, self.hsv_lower, self.hsv_upper)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
        if count < 2:
            raise RuntimeError(f"No visible {self.key} target")
        chosen = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        if stats[chosen, cv2.CC_STAT_AREA] < 40:
            raise RuntimeError(f"Too few {self.key} target pixels")
        return labels == chosen


green_vertices = tuple(map(tuple, WORKPIECE.vertices * 1000))
shoulder_profile = ((-32, -21), (32, -21), (32, 7), (11, 21), (-17, 21), (-32, 8))
orange_vertices = tuple((x, y, z) for y in (-19, 19) for x, z in shoulder_profile)
purple_bottom = ((-34, -21), (20, -21), (34, -6), (34, 21), (-34, 21))
purple_top = ((-24, -21), (12, -21), (28, -4), (28, 21), (-24, 21))
purple_vertices = tuple((x, y, -24) for x, y in purple_bottom) + tuple((x, y, 24) for x, y in purple_top)

PARTS = (
    Part("green", "Asymmetric double-bevel part", green_vertices, WORKPIECE.rgba,
         (46, 75, 38), (95, 255, 255), "target_cube", (.37, -.18), (.37, .18)),
    Part("orange", "Shouldered hexagonal prism", orange_vertices, (.95, .43, .06, 1.),
         (5, 100, 50), (29, 255, 255), "target_orange", (.47, -.18), (.47, .18)),
    Part("purple", "Chamfered tapered locator", purple_vertices, (.58, .16, .76, 1.),
         (125, 80, 40), (168, 255, 255), "target_purple", (.57, -.18), (.57, .18)),
)


def configure_parts(spec):
    from .scene import mujoco
    for part in PARTS:
        mesh = part.mesh()
        mesh_name = part.key + "_part_mesh"
        spec.add_mesh(name=mesh_name, uservert=mesh.vertices.ravel().tolist(), userface=mesh.faces.ravel().tolist())
        if part.key == "green":
            geom = spec.geom(part.geom)
            geom.type = mujoco.mjtGeom.mjGEOM_MESH
            geom.meshname = mesh_name
            geom.rgba = part.rgba
            geom.mass = part.mass_kg
        else:
            body = spec.worldbody.add_body(name=part.body, pos=[*part.xy, .375+part.half_height+.001])
            body.add_freejoint(name=part.joint)
            body.add_geom(name=part.geom, type=mujoco.mjtGeom.mjGEOM_MESH, meshname=mesh_name,
                          mass=part.mass_kg, rgba=part.rgba, friction=[1.2, .01, .001])


def export_parts(output):
    """OBJ in model metres; STL in print millimetres, translated onto Z=0."""
    import hashlib
    import json

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for part in PARTS:
        mesh = part.mesh()
        if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0:
            raise ValueError(f"Invalid printable solid: {part.key}")
        obj = output / f"{part.key}_model_m.obj"
        stl = output / f"{part.key}_print_mm.stl"
        mesh.export(str(obj))
        printable = mesh.copy()
        printable.apply_scale(1000.)
        printable.apply_translation([0, 0, -printable.bounds[0, 2]])
        printable.export(str(stl))
        loaded = trimesh.load(str(stl), force="mesh")
        if not loaded.is_watertight or not np.allclose(loaded.extents, mesh.extents*1000, atol=1e-4):
            raise ValueError(f"STL round-trip failed: {part.key}")
        records.append({"id": part.key, "title": part.title, "size_mm": (mesh.extents*1000).tolist(),
                        "watertight": True, "volume_mm3": float(mesh.volume*1e9),
                        "simulation_mass_kg": part.mass_kg, "obj_units": "metres", "stl_units": "millimetres",
                        "print_translation_mm": [0, 0, part.half_height*1000],
                        "files": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in (obj, stl)}})
    (output/"manifest.json").write_text(json.dumps(records, indent=2)+"\n")
    return records
