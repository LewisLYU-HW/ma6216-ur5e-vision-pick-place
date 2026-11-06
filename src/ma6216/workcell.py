"""Owned workcell geometry composed with external Menagerie robot assets.

The dimensions and physical parameters match the audited MA6216 scene. Robot
and gripper meshes remain in the separately installed Menagerie repository.
"""
from __future__ import annotations

from .config import ensure_mujoco_available, menagerie_dir

ensure_mujoco_available()
import mujoco


def build_workcell_spec():
    assets = menagerie_dir()
    spec = mujoco.MjSpec.from_file(str(assets / "universal_robots_ur5e/scene.xml"))
    gripper = mujoco.MjSpec.from_file(str(assets / "robotiq_2f85/2f85.xml"))
    mount = spec.site("attachment_site")
    if mount is None:
        raise RuntimeError("The UR5e model has no attachment_site")
    spec.attach(gripper, site=mount, prefix="gripper_")
    spec.modelname = "MA6216 Pick and Place Scene"
    box = mujoco.mjtGeom.mjGEOM_BOX

    spec.worldbody.add_geom(
        name="worktable", type=box, pos=[.50, 0., .35], size=[.36, .36, .025],
        rgba=[.62, .62, .65, 1.], friction=[1., .005, .0001],
    )
    cube = spec.worldbody.add_body(name="target_cube", pos=[.46, -.18, .401])
    cube.add_freejoint(name="target_cube_freejoint")
    cube.add_geom(
        name="target_cube_geom", type=box, size=[.025, .025, .025], mass=.10,
        rgba=[.95, .08, .08, 1.], friction=[1.2, .01, .001],
    )
    tray = spec.worldbody.add_body(name="target_tray", pos=[.50, .18, .375])
    tray.add_geom(
        name="tray_bottom", type=box, pos=[0., 0., .007], size=[.10, .10, .007],
        rgba=[.10, .35, .90, 1.],
    )
    walls = (
        ("left", [-.095, 0., .034], [.005, .10, .02]),
        ("right", [.095, 0., .034], [.005, .10, .02]),
        ("front", [0., -.095, .034], [.09, .005, .02]),
        ("back", [0., .095, .034], [.09, .005, .02]),
    )
    for name, position, half_size in walls:
        tray.add_geom(name=f"tray_wall_{name}", type=box, pos=position,
                      size=half_size, rgba=[.10, .35, .90, 1.])
    return spec
