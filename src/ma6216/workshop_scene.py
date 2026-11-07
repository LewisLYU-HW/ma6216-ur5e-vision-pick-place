"""A compact repair bench built around the group's UR5e and 2F-85.

Only reset assigns object coordinates. Rack geometry is surveyed equipment;
tool shapes supplied to the controller come from reference reconstruction.
"""

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from .advanced_scene import TaskScene, WRIST_CAMERA, add_marker, set_initial_pose
from .config import project_root
from .direct_route import configure_direct_table, set_front_ready
from .pose_insertion import transform
from .scene import build_scene, look_at_quat, matrix_to_quat, mujoco
from .workshop_assets import TOOLS, RACK_TOOLS, RACK_FRAME, FRAME_PROFILE, FRAME_DEPTH, ring_mesh

TABLE_Z = 0.375
BELT_TOP = 0.414
CRADLE = np.array([0.345, 0.015, 0.444])
PARK = np.array([0.600, -0.280, 0.447])
RACK_POSE = transform([0.50, 0.205, 0.391], Rotation.from_euler("z", 20.0, degrees=True).as_matrix())
WORKSHOP_T_MARKER = transform([-0.105, -0.035, 0.0015])
ASSEMBLY_T_MARKER = transform([-0.130, -0.025, 0.0915])
HOOK_CENTRE = np.array([-0.055, -0.012, 0.205])
HOOK_RADIUS = 0.004
HOOK_AXIS = np.array([0.0, -1.0, 0.0])
SOCKET_POSE = transform([0.090, -0.150, 0.072], Rotation.from_euler("y", 8.0, degrees=True).as_matrix())
SOCKET_INNER = 0.0045
SOCKET_DEPTH = 0.036
SPANNER_HANG_ROTATION = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, -1.0], [-1.0, 0.0, 0.0]])
RACK_T_FRAME = transform([-0.055, 0.010, 0.110])
FRAME_CLEARANCE = 0.0015

# Surveyed pickup regions are deliberately broad. They associate a task name
# with a station, not with a simulator segmentation ID or true object pose.
PICK_REGIONS = {
    "rack_spanner": ([0.44, -0.075, TABLE_Z + 0.002], [0.65, 0.05, 0.44]),
    "rack_frame": ([0.33, -0.22, 0.395], [0.59, -0.05, 0.49]),
    "screwdriver": ([0.275, -0.35, BELT_TOP + 0.0015], [0.515, -0.12, 0.48]),
    "hammer": ([0.42, -0.17, TABLE_Z + 0.002], [0.59, -0.055, 0.46]),
    "spanner": ([0.44, -0.01, TABLE_Z + 0.002], [0.65, 0.10, 0.44]),
    "cradle": ([0.25, -0.055, CRADLE[2] + 0.0015], [0.44, 0.085, 0.49]),
}


def box(body, name, pos, size, rgba, *, material=None, contact=True):
    kwargs = dict(
        name=name, type=mujoco.mjtGeom.mjGEOM_BOX, pos=pos, size=size, rgba=rgba, friction=[1.0, 0.01, 0.001]
    )
    if material:
        kwargs["material"] = material
    if not contact:
        kwargs.update(contype=0, conaffinity=0)
    return body.add_geom(**kwargs)


def label_texture(spec, name, title, subtitle, *, colour=(32, 49, 61)):
    """Deterministic typography assets, cached outside tracked source files."""
    directory = project_root() / "artifacts/workshop_texture_cache"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name + ".png")
    rgb = np.full((128, 512, 3), colour, dtype=np.uint8)
    cv2.rectangle(rgb, (0, 0), (10, 127), (52, 173, 234), -1)
    cv2.putText(rgb, title, (27, 56), cv2.FONT_HERSHEY_DUPLEX, 1.05, (236, 239, 241), 2, cv2.LINE_AA)
    cv2.putText(rgb, subtitle, (28, 96), cv2.FONT_HERSHEY_SIMPLEX, 0.57, (172, 191, 202), 1, cv2.LINE_AA)
    cv2.imwrite(str(path), rgb)
    spec.add_texture(name=name + "_texture", type=mujoco.mjtTexture.mjTEXTURE_2D, file=str(path))
    mat = spec.add_material(name=name + "_material", specular=0.1)
    mat.textures[1] = name + "_texture"
    return mat.name


def add_rack(spec, *, assembly=False):
    rack = spec.body("target_tray")
    rack.mocap = True
    rack.pos = RACK_POSE[:3, 3]
    rack.quat = matrix_to_quat(RACK_POSE[:3, :3])
    for old in ("tray_bottom", *("tray_wall_" + n for n in ("left", "right", "front", "back"))):
        g = spec.geom(old)
        g.contype = g.conaffinity = 0
        g.rgba = [0.0, 0.0, 0.0, 0.0]
    box(rack, "rack_foot", [0.0, 0.005, -0.008], [0.16, 0.09, 0.008], [0.15, 0.20, 0.24, 1.0])
    box(rack, "rack_board", [0.0, 0.060, 0.145], [0.16, 0.006, 0.145], [0.24, 0.31, 0.36, 1.0])
    for x in np.arange(-0.135, 0.14, 0.025):
        for z in np.arange(0.035, 0.27, 0.025):
            rack.add_geom(
                name=f"pegboard_{x:.3f}_{z:.3f}",
                type=mujoco.mjtGeom.mjGEOM_CYLINDER,
                pos=[x, 0.0538, z],
                size=[0.0024, 0.00015, 0.0],
                quat=matrix_to_quat(Rotation.from_euler("x", 90, degrees=True).as_matrix()),
                rgba=[0.07, 0.09, 0.10, 1.0],
                contype=0,
                conaffinity=0,
            )
    # A true horizontal peg: the eye must cross its end and then rest on it.
    rack.add_geom(
        name="rack_hook",
        type=mujoco.mjtGeom.mjGEOM_CAPSULE,
        fromto=[HOOK_CENTRE[0], 0.049, HOOK_CENTRE[2], *HOOK_CENTRE],
        size=[HOOK_RADIUS, 0.0, 0.0],
        rgba=[0.69, 0.72, 0.75, 1.0],
        friction=[0.9, 0.01, 0.001],
    )
    rack.add_geom(
        name="rack_hook_tip",
        type=mujoco.mjtGeom.mjGEOM_SPHERE,
        pos=HOOK_CENTRE,
        size=[0.006, 0.0, 0.0],
        rgba=[0.60, 0.63, 0.66, 1.0],
    )
    socket = rack.add_body(
        name="driver_socket", pos=SOCKET_POSE[:3, 3], quat=matrix_to_quat(SOCKET_POSE[:3, :3])
    )
    # Small tube with a genuine empty bore and a bottom stop.
    _, sectors = ring_mesh([0.0, 0.0], 0.013, SOCKET_INNER, SOCKET_DEPTH, segments=40)
    for i, mesh in enumerate(sectors):
        name = f"driver_socket_wall_{i}"
        spec.add_mesh(
            name=name, uservert=mesh.vertices.ravel().tolist(), userface=mesh.faces.ravel().tolist()
        )
        socket.add_geom(
            name=name,
            type=mujoco.mjtGeom.mjGEOM_MESH,
            meshname=name,
            pos=[0.0, 0.0, -SOCKET_DEPTH / 2],
            rgba=[0.66, 0.69, 0.72, 1.0],
            friction=[0.6, 0.01, 0.001],
        )
    socket.add_geom(
        name="driver_socket_floor",
        type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        pos=[0.0, 0.0, -SOCKET_DEPTH - 0.003],
        size=[0.013, 0.003, 0.0],
        rgba=[0.46, 0.50, 0.54, 1.0],
    )
    box(rack, "socket_bracket", [0.09, -0.05, 0.022], [0.018, 0.106, 0.007], [0.24, 0.31, 0.36, 1.0])
    if assembly:
        box(
            rack,
            "assembly_marker_pedestal",
            [-0.130, -0.025, 0.045],
            [0.040, 0.040, 0.045],
            [0.16, 0.23, 0.28, 1.0],
        )
        for name in ("rack_hook", "rack_hook_tip"):
            geom = spec.geom(name)
            geom.contype = geom.conaffinity = 0
            geom.rgba = [0.0, 0.0, 0.0, 0.0]
        mount = rack.add_body(name="frame_socket", pos=RACK_T_FRAME[:3, 3])
        box(
            rack,
            "frame_pedestal",
            [*RACK_T_FRAME[:2, 3], 0.035],
            [0.035, 0.030, 0.035],
            [0.16, 0.23, 0.28, 1.0],
        )
        box(
            mount,
            "frame_socket_floor",
            [0.0, 0.0, -FRAME_DEPTH - 0.002],
            [0.028, 0.025, 0.002],
            [0.16, 0.23, 0.28, 1.0],
        )
        # Offset polygon edges leave a real asymmetric bore, without a weld.
        for i, a in enumerate(FRAME_PROFILE):
            b = FRAME_PROFILE[(i + 1) % len(FRAME_PROFILE)]
            edge = b - a
            normal = np.array([edge[1], -edge[0]]) / np.linalg.norm(edge)
            xy = (a + b) / 2 + normal * (FRAME_CLEARANCE + 0.004)
            g = box(
                mount,
                f"frame_socket_wall_{i}",
                [*xy, -FRAME_DEPTH / 2],
                [np.linalg.norm(edge) / 2 + 0.004, 0.004, FRAME_DEPTH / 2],
                [0.29, 0.38, 0.44, 1.0],
            )
            g.quat = matrix_to_quat(Rotation.from_euler("z", np.arctan2(edge[1], edge[0])).as_matrix())
    add_marker(rack, ASSEMBLY_T_MARKER if assembly else WORKSHOP_T_MARKER)
    # Marker remains readable next to both tools; it localizes the whole rack.
    mat = label_texture(spec, "rack_label", "TOOL DOCK", "01  HANG     /     02  INSERT")
    box(
        rack,
        "rack_label",
        [0.0, 0.052, 0.268],
        [0.14, 0.0003, 0.019],
        [1.0, 1.0, 1.0, 1.0],
        material=mat,
        contact=False,
    )


def add_bench(spec):
    configure_direct_table(spec)
    table = spec.geom("worktable")
    table.rgba = [0.53, 0.43, 0.31, 1.0]
    spec.add_texture(
        name="workshop_mat_texture",
        type=mujoco.mjtTexture.mjTEXTURE_2D,
        builtin=mujoco.mjtBuiltin.mjBUILTIN_CHECKER,
        width=256,
        height=256,
        rgb1=[0.13, 0.18, 0.19],
        rgb2=[0.15, 0.20, 0.21],
    )
    mat = spec.add_material(name="workshop_mat", texrepeat=[18.0, 18.0], specular=0.10, shininess=0.12)
    mat.textures[1] = "workshop_mat_texture"
    box(
        spec.worldbody,
        "bench_mat",
        [0.535, 0.0, 0.37505],
        [0.265, 0.335, 0.00005],
        [1.0, 1.0, 1.0, 1.0],
        material=mat.name,
        contact=False,
    )
    for x in (0.29, 0.81):
        for y in (-0.30, 0.30):
            box(
                spec.worldbody,
                f"bench_leg_{x}_{y}",
                [x, y, 0.17],
                [0.018, 0.018, 0.17],
                [0.12, 0.17, 0.20, 1.0],
            )
    box(spec.worldbody, "cabinet", [0.67, 0.0, 0.20], [0.15, 0.285, 0.13], [0.10, 0.18, 0.24, 1.0])
    for z in (0.125, 0.205, 0.285):
        box(spec.worldbody, f"drawer_{z}", [0.67, -0.288, z], [0.139, 0.003, 0.034], [0.16, 0.25, 0.31, 1.0])
        box(
            spec.worldbody,
            f"drawer_handle_{z}",
            [0.67, -0.297, z + 0.012],
            [0.045, 0.006, 0.004],
            [0.63, 0.66, 0.68, 1.0],
        )
    label = label_texture(spec, "bench_brand", "MA6216 / SERVICE LAB", "VISION-GUIDED TOOL HANDLING")
    box(
        spec.worldbody,
        "bench_brand",
        [0.545, -0.361, 0.343],
        [0.21, 0.001, 0.024],
        [1.0, 1.0, 1.0, 1.0],
        material=label,
        contact=False,
    )
    floor = spec.geom("floor")
    if floor is not None:
        floor.material = ""
        floor.rgba = [0.25, 0.28, 0.30, 1.0]
    for y in (-0.8, 0.8):
        box(
            spec.worldbody,
            f"floor_stripe_{y}",
            [0.50, y, 0.001],
            [0.85, 0.012, 0.001],
            [0.73, 0.55, 0.21, 1.0],
            contact=False,
        )
    spec.visual.headlight.ambient = [0.35, 0.35, 0.35]
    spec.visual.headlight.diffuse = [0.55, 0.55, 0.55]
    spec.visual.headlight.specular = [0.18, 0.18, 0.18]
    spec.visual.quality.shadowsize = 4096
    spec.worldbody.add_light(
        name="workshop_softbox",
        pos=[0.3, -0.5, 1.8],
        dir=[0.1, 0.2, -1.0],
        diffuse=[0.65, 0.61, 0.55],
        specular=[0.25, 0.25, 0.25],
        castshadow=True,
    )


def build_workshop_scene(seed=0, *, planning_parts=None, empty=False, belt_speed=0.003, rack_assembly=False):
    physical_tools = RACK_TOOLS if rack_assembly else TOOLS
    parts = tuple(physical_tools.values()) if planning_parts is None else tuple(planning_parts)
    rng = np.random.default_rng(seed)
    poses = {
        "hammer": transform([0.50, -0.10, 0.401], Rotation.from_euler("z", -18.0, degrees=True).as_matrix()),
        "screwdriver": transform(
            [0.390, -0.245, BELT_TOP + 0.015], Rotation.from_euler("z", 12.0, degrees=True).as_matrix()
        ),
        "spanner": transform(
            [0.545, 0.045, 0.414], Rotation.from_euler("z", -12.0, degrees=True).as_matrix()
        ),
    }
    if seed:
        for pose in poses.values():
            pose[:2, 3] += rng.uniform(-0.004, 0.004, 2)
    if rack_assembly:
        poses["spanner"][1, 3] -= 0.065
        # Hook points upward on the source rails. This also exposes the front
        # side for the final horizontal-hand approach, clear of the backboard.
        poses = {
            "rack_frame": transform(
                [0.385, -0.120, 0.433], np.column_stack(([0.0, -1.0, 0.0], [0.0, 0.0, -1.0], [1.0, 0.0, 0.0]))
            ),
            "spanner": poses["spanner"],
        }
        if seed:
            poses["rack_frame"][:2, 3] += rng.uniform(-0.004, 0.004, 2)

    def configure(spec):
        add_bench(spec)
        for part in parts:
            part.configure(spec)
        for body in spec.bodies:
            if body.name not in ("world", *[p.body for p in parts], "target_tray"):
                body.gravcomp = 1.0
        spec.option.impratio = 10.0
        spec.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
        # Silicone pads have finite contact patches. Include torsional and
        # rolling friction so thin tools cannot freely pivot at point contacts.
        # This is a declared contact-model assumption, not an attachment weld.
        for side in ("left", "right"):
            for index in (1, 2):
                pad = spec.geom(f"gripper_{side}_pad{index}")
                pad.condim = 6
                pad.friction = [0.9, 0.005, 0.001]
        gripper = spec.body("gripper_base")
        eye = [0.075, 0.0, 0.035]
        gripper.add_camera(name=WRIST_CAMERA, pos=eye, quat=look_at_quat(eye, [0.0, 0.0, 0.145]), fovy=80.0)
        gripper.add_site(name="wrist_ft_site", size=[0.001, 0.0, 0.0])
        for name, kind in (
            ("wrist_force", mujoco.mjtSensor.mjSENS_FORCE),
            ("wrist_torque", mujoco.mjtSensor.mjSENS_TORQUE),
        ):
            spec.add_sensor(name=name, type=kind, objtype=mujoco.mjtObj.mjOBJ_SITE, objname="wrist_ft_site")
        add_rack(spec, assembly=rack_assembly)
        if rack_assembly:
            for i, x in enumerate((0.030, 0.145)):
                p = poses["rack_frame"][:3, 3] + np.array([x, 0.0, 0.0])
                p[2] = 0.3985
                box(
                    spec.worldbody,
                    f"frame_source_rail_{i}",
                    p,
                    [0.008, 0.024, 0.0235],
                    [0.28, 0.34, 0.38, 1.0],
                )
        # A short, finite translating feed tray, driven by a velocity actuator.
        belt = spec.worldbody.add_body(name="conveyor", pos=[0.390, -0.245, BELT_TOP - 0.009], gravcomp=1.0)
        belt.add_joint(name="belt_slide", type=mujoco.mjtJoint.mjJNT_SLIDE, axis=[0.0, 1.0, 0.0], damping=5.0)
        g = box(belt, "belt_surface", [0.0, 0.0, 0.0], [0.112, 0.095, 0.009], [0.075, 0.085, 0.09, 1.0])
        g.mass = 20.0
        for x in (-0.12, 0.12):
            box(
                spec.worldbody,
                f"feed_frame_{x}",
                [0.390 + x, -0.245, 0.399],
                [0.006, 0.105, 0.018],
                [0.50, 0.54, 0.57, 1.0],
            )
        for y in np.arange(-0.08, 0.09, 0.02):
            box(
                belt,
                f"belt_rib_{y}",
                [0.0, y, 0.0091],
                [0.108, 0.0005, 0.0001],
                [0.19, 0.21, 0.22, 1.0],
                contact=False,
            )
        spec.add_actuator(
            name="belt_drive",
            target="belt_slide",
            trntype=mujoco.mjtTrn.mjTRN_JOINT,
            dyntype=mujoco.mjtDyn.mjDYN_NONE,
            gaintype=mujoco.mjtGain.mjGAIN_FIXED,
            gainprm=[1000.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            biastype=mujoco.mjtBias.mjBIAS_AFFINE,
            biasprm=[0.0, 0.0, -1000.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        )
        for sign in (-1, 1):
            support = poses["spanner"][:3, 3] + poses["spanner"][:3, :3] @ np.array([sign * 0.058, 0.0, 0.0])
            support[2] = 0.3915
            box(
                spec.worldbody,
                f"spanner_source_support_{sign}",
                support,
                [0.009, 0.027, 0.0155],
                [0.20, 0.26, 0.28, 1.0],
            )
            box(
                spec.worldbody,
                f"workshop_cradle_rail_{sign}",
                CRADLE + [sign * 0.058, 0.0, -0.004],
                [0.009, 0.035, 0.004],
                [0.31, 0.37, 0.40, 1.0],
            )
            box(
                spec.worldbody,
                f"workshop_cradle_leg_{sign}",
                CRADLE + [sign * 0.058, 0.0, -0.034],
                [0.006, 0.023, 0.030],
                [0.14, 0.20, 0.24, 1.0],
            )
        box(
            spec.worldbody,
            "tool_park",
            PARK - [0.0, 0.0, 0.005],
            [0.087, 0.048, 0.005],
            [0.16, 0.20, 0.22, 1.0],
        )
        for sign in (-1, 1):
            box(
                spec.worldbody,
                f"tool_park_leg_{sign}",
                [PARK[0] + sign * 0.070, PARK[1], (TABLE_Z + PARK[2] - 0.010) / 2],
                [0.007, 0.035, (PARK[2] - 0.010 - TABLE_Z) / 2],
                [0.20, 0.26, 0.29, 1.0],
            )

    m, d = build_scene((0.635, -0.205), calibration_board=False, configure_spec=configure, object_z=0.401)
    for name, tool in physical_tools.items():
        pose = poses[name].copy()
        if empty:
            pose[2, 3] = -5.0
        set_initial_pose(m, d, tool, pose)
    set_front_ready(m, d)
    # Presentation camera changes do not alter the calibrated RGB-D sensor.
    cid = m.camera("overview").id
    eye, target = [0.99, -1.15, 0.99], [0.42, 0.015, 0.425]
    m.cam_pos[cid], m.cam_quat[cid], m.cam_fovy[cid] = eye, look_at_quat(eye, target), 45.0
    mujoco.mj_forward(m, d)
    return TaskScene(m, d, "workshop", seed, RACK_POSE.copy(), parts, belt_speed)


def workshop_supports(stage):
    if stage in ("LIFT", "LIFT_SETTLE"):
        return {
            "worktable",
            "belt_surface",
            "workshop_cradle_rail_-1",
            "workshop_cradle_rail_1",
            "spanner_source_support_-1",
            "spanner_source_support_1",
            "frame_source_rail_0",
            "frame_source_rail_1",
        }
    if stage.startswith("PARK_HAMMER"):
        return {"tool_park"}
    if stage.startswith("PLACE_REGRASP"):
        return {"workshop_cradle_rail_-1", "workshop_cradle_rail_1"}
    if stage.startswith(("INSERT_DRIVER", "RETRACT_DRIVER")):
        return {"driver_socket_floor", *(f"driver_socket_wall_{i}" for i in range(40))}
    if stage.startswith(("THREAD_EYE", "SEAT_EYE", "RETRACT_EYE")):
        return {"rack_hook", "rack_hook_tip"}
    return set()


def rack_assembly_supports(stage, planning_frame_geoms=()):
    if stage.startswith(("INSERT_FRAME", "RETRACT_FRAME")):
        return {"frame_socket_floor", *(f"frame_socket_wall_{i}" for i in range(5))}
    if stage.startswith(("THREAD_EYE", "SEAT_EYE", "RETRACT_EYE")):
        return set(RACK_FRAME.collision_names) | set(planning_frame_geoms)
    return workshop_supports(stage)
