"""Textured simulation props. These meshes never enter the pose estimator.

GSO source files retain their original UVs and CC-BY attribution. The ring
spanner is an original parametric workshop prop, with a real collision hole.
"""

from dataclasses import dataclass
from functools import cached_property

import numpy as np
import trimesh

from .config import project_root
from .scene import mujoco


def ring_mesh(centre, outer, inner, thickness, segments=64):
    angles = np.arange(segments) * 2 * np.pi / segments
    xy = np.c_[np.cos(angles), np.sin(angles)]
    vertices = np.vstack(
        [
            np.c_[xy * r + centre, np.full(segments, z)]
            for z in (-thickness / 2, thickness / 2)
            for r in (outer, inner)
        ]
    )
    faces, pieces = [], []
    n = segments
    for i in range(n):
        j = (i + 1) % n
        quads = [
            (i, j, n + j, n + i),
            (2 * n + i, 3 * n + i, 3 * n + j, 2 * n + j),
            (i, 2 * n + i, 2 * n + j, j),
            (n + i, n + j, 3 * n + j, 3 * n + i),
        ]
        for a, b, c, d in quads:
            faces.extend(((a, b, c), (a, c, d)))
        pieces.append(
            trimesh.convex.convex_hull(
                vertices[[i, j, n + i, n + j, 2 * n + i, 2 * n + j, 3 * n + i, 3 * n + j]]
            )
        )
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    mesh.fix_normals()
    return mesh, pieces


def spanner_geometry():
    ring, sectors = ring_mesh([-0.060, 0.0], 0.026, 0.014, 0.012)
    handle = trimesh.creation.box([0.105, 0.022, 0.012])
    handle.apply_translation([0.009, 0.0, 0.0])
    # Rounded open jaw, open at its far end. Independent convex sectors keep
    # both the hanging eye and jaw physically open, not just visually hollow.
    _, jaw_sectors = ring_mesh([0.065, 0.0], 0.024, 0.014, 0.012)
    keep = [i for i in range(64) if np.cos((i + 0.5) * 2 * np.pi / 64) < 0.60]
    jaw_sectors = [jaw_sectors[i] for i in keep]
    return trimesh.util.concatenate([ring, handle, *jaw_sectors]), [*sectors, handle, *jaw_sectors]


@dataclass(frozen=True)
class WorkshopTool:
    object_id: str
    body: str
    folder: str | None = None
    scale: float = 0.5
    mass_kg: float = 0.10

    @property
    def joint(self):
        return self.body + "_freejoint"

    @property
    def geom(self):
        return self.body + "_geom"

    @cached_property
    def geometry(self):
        if self.folder is None:
            return spanner_geometry()
        directory = project_root() / "assets/library/gso" / self.folder
        mesh = trimesh.load(directory / "model.obj", force="mesh", process=False)
        centre = mesh.bounds.mean(axis=0)
        mesh.vertices = (mesh.vertices - centre) * self.scale
        pieces = []
        for index in range(32):
            piece = trimesh.load(directory / f"model_collision_{index}.obj", force="mesh", process=False)
            piece.vertices = (piece.vertices - centre) * self.scale
            pieces.append(piece)
        return mesh, pieces

    @property
    def vertices(self):
        return self.geometry[0].vertices

    @property
    def collision_names(self):
        return tuple(self.geom if i == 0 else self.geom + f"_{i}" for i in range(len(self.geometry[1])))

    def add_visual(self, spec, body, *, name=None):
        name = name or self.object_id
        mesh = self.geometry[0]
        kwargs = dict(
            name=name + "_visual_mesh",
            uservert=mesh.vertices.ravel().tolist(),
            userface=mesh.faces.ravel().tolist(),
            smoothnormal=True,
        )
        if self.folder:
            # Inline MjSpec texture coordinates use image-down V, while the
            # source OBJ / trimesh UVs use image-up V. Keep source PNG intact.
            uv = mesh.visual.uv.copy()
            uv[:, 1] = 1.0 - uv[:, 1]
            kwargs["usertexcoord"] = uv.ravel().tolist()
            kwargs["userfacetexcoord"] = mesh.faces.ravel().tolist()
            texture = name + "_texture"
            spec.add_texture(
                name=texture,
                type=mujoco.mjtTexture.mjTEXTURE_2D,
                file=str(project_root() / "assets/library/gso" / self.folder / "texture.png"),
            )
            material = spec.add_material(name=name + "_material", specular=0.22, shininess=0.3)
            material.textures[1] = texture
        else:
            material = spec.add_material(
                name=name + "_material", rgba=[0.63, 0.67, 0.70, 1.0], specular=0.65, shininess=0.65
            )
        spec.add_mesh(**kwargs)
        body.add_geom(
            name=name + "_visual",
            type=mujoco.mjtGeom.mjGEOM_MESH,
            meshname=name + "_visual_mesh",
            material=material.name,
            contype=0,
            conaffinity=0,
            mass=0,
            group=2,
        )
        if not self.folder:
            # The handle strip is appearance only. Physics is supplied by
            # the solid steel body.
            body.add_geom(
                name=name + "_handle_inset",
                type=mujoco.mjtGeom.mjGEOM_BOX,
                pos=[0.004, 0.0, 0.00605],
                size=[0.028, 0.006, 0.00005],
                rgba=[0.26, 0.29, 0.32, 1.0],
                contype=0,
                conaffinity=0,
                mass=0,
            )

    def configure(self, spec):
        body = spec.body(self.body)
        if body is None:
            body = spec.worldbody.add_body(name=self.body)
            body.add_freejoint(name=self.joint)
        self.add_visual(spec, body)
        for i, piece in enumerate(self.geometry[1]):
            name = self.collision_names[i]
            geom = spec.geom(name)
            if geom is None:
                geom = body.add_geom(name=name)
            mesh_name = self.object_id + f"_collision_{i}"
            spec.add_mesh(
                name=mesh_name,
                uservert=piece.vertices.ravel().tolist(),
                userface=piece.faces.ravel().tolist(),
            )
            geom.type = mujoco.mjtGeom.mjGEOM_MESH
            geom.meshname = mesh_name
            geom.mass = self.mass_kg / len(self.geometry[1])
            geom.friction = [1.2, 0.01, 0.001]
            geom.group = 3
            geom.rgba = [0.5, 0.5, 0.5, 0.0]


TOOLS = {
    "hammer": WorkshopTool("hammer", "target_cube", "Cole_Hardware_Hammer_Black"),
    "screwdriver": WorkshopTool(
        "screwdriver", "target_screwdriver", "Craftsman_Grip_Screwdriver_Phillips_Cushion", scale=0.75
    ),
    "spanner": WorkshopTool("spanner", "target_spanner"),
}
