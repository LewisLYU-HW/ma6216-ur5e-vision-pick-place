"""A true sphere, a hollow hex nut, and a scanned household hammer.

Scanned assets: Google Scanned Objects (CC BY 4.0), MuJoCo conversion by
Kevin Zakka. See assets/library/gso/SOURCE.json for the pinned source files.
"""
from dataclasses import dataclass
from functools import cached_property

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from .config import project_root
from .parts import Part
from .scene import mujoco


def hex_ring():
    """Watertight hexagonal outside and 48-sided circular through-hole."""
    count = 48
    corners = np.c_[np.cos(np.arange(6)*np.pi/3), np.sin(np.arange(6)*np.pi/3)]*.030
    outer = np.array([(1-(i%8)/8)*corners[i//8] + ((i%8)/8)*corners[(i//8+1)%6]
                      for i in range(count)])
    angle = np.arctan2(outer[:, 1], outer[:, 0])
    inner = .013*np.c_[np.cos(angle), np.sin(angle)]
    rings = [np.c_[points, np.full(count, z)] for z in (-.020, .020) for points in (outer, inner)]
    vertices = np.vstack(rings)
    faces = []
    for i in range(count):
        j = (i+1) % count
        for quad in [(i,j,count+j,count+i), (2*count+i,3*count+i,3*count+j,2*count+j),
                     (i,2*count+i,2*count+j,j), (count+i,count+j,3*count+j,3*count+i)]:
            a,b,c,d=quad
            faces.extend(((a,b,c),(a,c,d)))
    mesh=trimesh.Trimesh(vertices, faces, process=False)
    mesh.fix_normals()
    # Each wall sector is convex. The central hole has no collision geometry.
    pieces=[]
    for i in range(count):
        j=(i+1)%count
        points=vertices[[i,j,count+i,count+j,2*count+i,2*count+j,3*count+i,3*count+j]]
        pieces.append(trimesh.convex.convex_hull(points))
    return mesh,pieces


@dataclass(frozen=True)
class LibraryPart:
    key: str
    title: str
    rgba: tuple
    hsv_lower: tuple
    hsv_upper: tuple
    body: str
    xy: tuple
    destination_xy: tuple
    mass_kg: float = .10
    grasp_offset_z: float = .003
    grasp_offset: tuple = (0.,0.,0.)
    yaw_period: float = np.pi
    sphere: bool = False

    @cached_property
    def geometry(self):
        if self.key == "sphere":
            mesh=trimesh.creation.icosphere(subdivisions=3, radius=.025)
            return mesh, [mesh]
        if self.key == "hex_nut":
            return hex_ring()
        folders={"hammer":"Cole_Hardware_Hammer_Black",
                 "screwdriver":"Craftsman_Grip_Screwdriver_Phillips_Cushion"}
        folder=project_root()/"assets/library/gso"/folders[self.key]
        if not (folder/"model.obj").is_file():
            raise FileNotFoundError("Scanned tool assets missing; see docs/OBJECT_LIBRARY.md")
        mesh=trimesh.load(folder/"model.obj",force="mesh",process=False,skip_materials=True)
        # Uniform half scale, so the full scanned tool fits the existing table.
        centre=mesh.bounds.mean(axis=0)
        mesh.vertices=(mesh.vertices-centre)*.5
        pieces=[]
        for index in range(32):
            piece=trimesh.load(folder/f"model_collision_{index}.obj",force="mesh",process=False)
            piece.vertices=(piece.vertices-centre)*.5
            pieces.append(piece)
        return mesh,pieces

    def mesh(self):
        mesh=self.geometry[0].copy()
        # Matte colour makes the existing image-only segmentation reproducible;
        # the downloaded original texture is retained, not used as a mask oracle.
        mesh.visual=trimesh.visual.ColorVisuals(mesh=mesh,vertex_colors=np.tile(
            np.rint(255*np.asarray(self.rgba)).astype(np.uint8),(len(mesh.vertices),1)))
        return mesh

    @property
    def vertices(self):
        return self.geometry[0].vertices

    @property
    def half_height(self):
        return float(-self.vertices[:,2].min())

    @property
    def geom(self):
        return "target_cube_geom" if self.body == "target_cube" else self.body+"_geom"

    @property
    def joint(self):
        return "target_cube_freejoint" if self.body == "target_cube" else self.body+"_freejoint"

    @property
    def collision_names(self):
        return tuple(self.geom if i==0 else self.geom+f"_{i}" for i in range(len(self.geometry[1])))

    def export_mesh(self,path):
        self.mesh().export(str(path))

    def mask(self,rgb):
        return Part.mask(self,rgb)

    def configure(self,spec):
        box=mujoco.mjtGeom.mjGEOM_MESH
        if self.body == "target_cube":
            body=spec.body(self.body)
        else:
            body=spec.worldbody.add_body(name=self.body)
            body.add_freejoint(name=self.joint)
        visual=self.mesh()
        spec.add_mesh(name=self.key+"_visual_mesh", uservert=visual.vertices.ravel().tolist(),
                      userface=visual.faces.ravel().tolist())
        body.add_geom(name=self.key+"_visual", type=box, meshname=self.key+"_visual_mesh",
                      rgba=self.rgba, contype=0, conaffinity=0, mass=0, group=2)
        for index,piece in enumerate(self.geometry[1]):
            name=self.collision_names[index]
            geom=spec.geom(name) if self.body=="target_cube" and index==0 else body.add_geom(name=name)
            geom.mass=self.mass_kg/len(self.geometry[1])
            geom.friction=[1.2,.01,.001]
            geom.group=3
            geom.rgba=self.rgba
            if self.sphere:
                geom.type=mujoco.mjtGeom.mjGEOM_SPHERE
                geom.size=[.025,0,0]
                geom.condim=6  # Include physical torsional and rolling resistance.
            else:
                meshname=self.key+f"_collision_{index}"
                spec.add_mesh(name=meshname,uservert=piece.vertices.ravel().tolist(),
                              userface=piece.faces.ravel().tolist())
                geom.type=box
                geom.meshname=meshname


DIVERSE_PARTS=(
    LibraryPart("hammer","Google Scanned Objects: Cole Hardware hammer",
                (.62,.12,.76,1.),(125,80,35),(170,255,255),"target_cube",
                (.46,-.24),(.46,.23),grasp_offset=(.055,0.,.007)),
    LibraryPart("sphere","50 mm sphere",(.92,.05,.05,1.),(0,110,40),(10,255,255),
                "target_sphere",(.37,-.10),(.37,.11),sphere=True,yaw_period=0.,grasp_offset_z=.010),
    LibraryPart("hex_nut","Hexagonal nut with circular through-hole",
                (.95,.77,.06,1.),(22,80,45),(39,255,255),"target_hex_nut",
                (.54,-.10),(.54,.11),yaw_period=np.pi/3),
)

# An additional scanned tool is available for inspection and printing. Its
# thin handle needs separate grasp validation; it is not in the auto-pick set.
SCREWDRIVER=LibraryPart("screwdriver","Google Scanned Objects: Craftsman Phillips screwdriver",
                       (.08,.65,.27,1.),(43,75,35),(80,255,255),"target_screwdriver",
                       (.70,-.10),(.70,.18))


def rotation_error(part, estimated, actual):
    """Orientation accuracy modulo physical symmetries, not raw Euler error."""
    if getattr(part,"sphere",False):
        return None
    period=getattr(part,"yaw_period",2*np.pi)
    count=max(1,round(2*np.pi/period)) if part.key=="hex_nut" else 1
    return float(min(np.rad2deg(Rotation.from_matrix(
        estimated @ (actual@Rotation.from_euler("z",i*period).as_matrix()).T).magnitude())
        for i in range(count)))
