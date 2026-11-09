"""One continuous electronics-assembly application demo, not a vision benchmark.

Joint actuators and physical pad contact perform every pickup. Surveyed fixture
coordinates supply scripted targets. Seated parts are joined by explicit weld
constraints (simplified fastening), never teleported or attached to the gripper.
"""

from pathlib import Path
import argparse, json, sys, math, subprocess
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ma6216.workcell import build_workcell_spec
from ma6216.scene import mujoco, look_at_quat
from ma6216.motion import Robot, MotionFailure

TABLE = 0.375
SOURCES = {
    "case": (0.35, -0.23, 0.381),
    "battery": (0.50, -0.23, 0.392),
    "pcb": (0.61, -0.23, 0.391),
    "lid": (0.35, -0.04, 0.389),
}
ASSEMBLY = np.array([0.50, 0.115, 0.389])
OFFSETS = {"case": 0.0, "battery": 0.015, "pcb": 0.034, "lid": 0.057}
GRIP = {"case": 0.008, "battery": 0.004, "pcb": 0.009, "lid": 0.006}
PHASES = [
    "Enclosure loading",
    "Battery installation",
    "PCB placement",
    "Cover assembly",
    "Finished unit transfer",
]


def scene():
    s = build_workcell_spec()
    s.delete(s.body("target_cube"))
    s.delete(s.body("target_tray"))
    s.modelname = "Electronics assembly | application demonstration"
    s.geom("floor").material = ""
    s.geom("floor").rgba = [0.17, 0.21, 0.25, 1]
    s.geom("worktable").size = [0.30, 0.40, 0.025]
    s.geom("worktable").pos = [0.55, 0, 0.35]
    s.geom("worktable").rgba = [0.22, 0.29, 0.32, 1]
    box = mujoco.mjtGeom.mjGEOM_BOX

    def geom(body, name, pos, size, color, mass=0.005, physical=True, kind=box):
        return body.add_geom(
            name=name,
            type=kind,
            pos=pos,
            size=size,
            rgba=color,
            mass=mass,
            contype=1 if physical else 0,
            conaffinity=1 if physical else 0,
            friction=[1.3, 0.008, 0.0001],
            solref=[0.006, 1],
        )

    def decor(name, pos, size, color):
        return geom(s.worldbody, name, pos, size, color, physical=False)

    # ESD bench, aluminium edging and precision nests.
    for y in [-0.399, 0.399]:
        decor(
            "bench_rail_" + str(y),
            [0.55, y, 0.355],
            [0.30, 0.004, 0.025],
            [0.64, 0.69, 0.73, 1],
        )
    for x in [0.27, 0.83]:
        for y in [-0.37, 0.37]:
            decor(
                f"leg_{x}_{y}",
                [x, y, 0.175],
                [0.018, 0.018, 0.175],
                [0.17, 0.21, 0.24, 1],
            )
    for name, (x, y, z) in SOURCES.items():
        geom(
            s.worldbody,
            "nest_" + name,
            [x, y, 0.378],
            [0.066, 0.051, 0.003],
            [0.12, 0.17, 0.20, 1],
            mass=0.1,
        )
        for dx in [-0.064, 0.064]:
            decor(
                f"nest_edge_{name}_{dx}",
                [x + dx, y, 0.382],
                [0.001, 0.049, 0.001],
                [0.14, 0.70, 0.76, 1],
            )
    geom(
        s.worldbody,
        "assembly_pedestal",
        [0.50, 0.115, 0.380],
        [0.080, 0.065, 0.005],
        [0.62, 0.66, 0.70, 1],
        mass=1,
    )
    geom(
        s.worldbody,
        "assembly_pad",
        [0.50, 0.115, 0.386],
        [0.060, 0.038, 0.001],
        [0.12, 0.16, 0.19, 1],
        mass=0.1,
    )
    geom(
        s.worldbody,
        "output_pad",
        [0.64, 0.16, 0.381],
        [0.075, 0.065, 0.006],
        [0.13, 0.21, 0.25, 1],
        mass=0.1,
    )
    for y in [0.10, 0.22]:
        decor(
            "output_line_" + str(y),
            [0.64, y, 0.388],
            [0.073, 0.002, 0.001],
            [0.10, 0.76, 0.65, 1],
        )
    # Rear electronics inspection console and lighting.
    decor(
        "console_base", [0.73, 0.32, 0.43], [0.07, 0.035, 0.055], [0.16, 0.20, 0.23, 1]
    )
    decor("screen", [0.73, 0.282, 0.45], [0.060, 0.002, 0.032], [0.035, 0.10, 0.15, 1])
    for i in range(5):
        decor(
            "screen_row_" + str(i),
            [0.72, 0.279, 0.47 - i * 0.009],
            [0.040 - i * 0.004, 0.001, 0.001],
            [0.10, 0.75, 0.76, 1],
        )
    for i, col in enumerate([[0.95, 0.55, 0.08, 1], [0.15, 0.80, 0.45, 1]]):
        decor(
            "indicator_" + str(i),
            [0.82, 0.31, 0.465 + i * 0.018],
            [0.008, 0.008, 0.007],
            col,
        )
    bodies = {}
    for name, xyz in SOURCES.items():
        b = s.worldbody.add_body(name=name, pos=xyz)
        b.add_freejoint(name=name + "_joint")
        bodies[name] = b
    b = bodies["case"]
    silver = [0.77, 0.80, 0.83, 1]
    geom(b, "case_base", [0, 0, 0], [0.056, 0.034, 0.003], silver, mass=0.07)
    for sign in [-1, 1]:
        geom(
            b,
            f"case_wall_y{sign}",
            [0, sign * 0.032, 0.006],
            [0.056, 0.002, 0.006],
            silver,
        )
        geom(
            b,
            f"case_wall_x{sign}",
            [sign * 0.054, 0, 0.006],
            [0.002, 0.030, 0.006],
            silver,
        )
    for x in [-0.047, 0.047]:
        for y in [-0.026, 0.026]:
            geom(
                b,
                f"case_post{x}_{y}",
                [x, y, 0.029],
                [0.003, 0.003, 0.026],
                [0.55, 0.60, 0.66, 1],
            )
    for x in [-0.037, 0.037]:
        for y in [-0.020, 0.020]:
            geom(
                b,
                f"pcb_standoff{x}_{y}",
                [x, y, 0.0195],
                [0.0028, 0.0125, 0],
                [0.85, 0.65, 0.20, 1],
                kind=mujoco.mjtGeom.mjGEOM_CYLINDER,
            )
    # Front ventilation slots (visual markings on solid wall).
    for i in range(7):
        geom(
            b,
            "vent_" + str(i),
            [-0.035 + i * 0.011, -0.0341, 0.006],
            [0.003, 0.0002, 0.003],
            [0.10, 0.14, 0.18, 1],
            physical=False,
        )
    b = bodies["battery"]
    geom(
        b,
        "battery_main",
        [0, 0, 0],
        [0.036, 0.017, 0.012],
        [0.035, 0.28, 0.65, 1],
        mass=0.06,
    )
    for x in [-0.036, 0.036]:
        geom(
            b,
            "battery_cap" + str(x),
            [x, 0, 0],
            [0.002, 0.017, 0.012],
            [0.14, 0.18, 0.22, 1],
        )
    geom(
        b,
        "battery_label",
        [0, 0, 0.0122],
        [0.021, 0.010, 0.0002],
        [0.87, 0.91, 0.94, 1],
        physical=False,
    )
    for x in [-0.025, 0.025]:
        geom(
            b,
            "battery_terminal" + str(x),
            [x, 0.014, 0.0125],
            [0.003, 0.002, 0.001],
            [0.90, 0.72, 0.30, 1],
            physical=False,
        )
    b = bodies["pcb"]
    geom(
        b,
        "pcb_board",
        [0, 0, 0],
        [0.043, 0.024, 0.002],
        [0.035, 0.40, 0.22, 1],
        mass=0.025,
    )
    # Gripping edge rails leave clearance for the fingertip at insertion.
    for y in [-0.023, 0.023]:
        geom(
            b,
            "pcb_grip" + str(y),
            [0, y, 0.006],
            [0.016, 0.002, 0.006],
            [0.08, 0.26, 0.18, 1],
        )
    for x, y, sx, sy in [
        (-0.015, 0, 0.009, 0.008),
        (0.013, 0.004, 0.007, 0.006),
        (0.028, -0.011, 0.004, 0.005),
    ]:
        geom(
            b,
            f"chip{x}",
            [x, y, 0.005],
            [sx, sy, 0.003],
            [0.045, 0.052, 0.062, 1],
            physical=False,
        )
        for k in range(4):
            geom(
                b,
                f"pin{x}_{k}",
                [x - sx + k * 2 * sx / 3, y - sy - 0.001, 0.003],
                [0.0008, 0.002, 0.0005],
                [0.80, 0.82, 0.84, 1],
                physical=False,
            )
    for i in range(6):
        geom(
            b,
            "trace" + str(i),
            [-0.03 + i * 0.010, 0.015, 0.0022],
            [0.003, 0.0005, 0.0002],
            [0.74, 0.64, 0.25, 1],
            physical=False,
        )
    geom(
        b,
        "usb",
        [0.039, 0.005, 0.005],
        [0.006, 0.007, 0.004],
        [0.70, 0.73, 0.76, 1],
        physical=False,
    )
    b = bodies["lid"]
    # Clear centre window and opaque side rails; all are rigid geometry.
    geom(
        b,
        "lid_window",
        [0, 0, 0],
        [0.052, 0.029, 0.002],
        [0.48, 0.76, 0.85, 0.32],
        mass=0.025,
    )
    for y in [-0.032, 0.032]:
        geom(
            b,
            "lid_grip" + str(y),
            [0, y, 0.003],
            [0.056, 0.003, 0.005],
            [0.67, 0.73, 0.78, 1],
            mass=0.012,
        )
    for y in [-0.032, 0.032]:
        geom(
            b,
            "lid_grip_tab" + str(y),
            [0, y, 0.010],
            [0.016, 0.003, 0.010],
            [0.67, 0.73, 0.78, 1],
            mass=0.008,
        )
    for x in [-0.054, 0.054]:
        geom(
            b,
            "lid_edge" + str(x),
            [x, 0, 0],
            [0.002, 0.029, 0.002],
            [0.67, 0.73, 0.78, 1],
        )
    for x in [-0.047, 0.047]:
        for y in [-0.026, 0.026]:
            geom(
                b,
                f"lid_screw{x}_{y}",
                [x, y, 0.0025],
                [0.002, 0.002, 0.001],
                [0.23, 0.29, 0.33, 1],
                physical=False,
                kind=mujoco.mjtGeom.mjGEOM_CYLINDER,
            )
    for name in ["battery", "pcb", "lid"]:
        e = s.add_equality(
            name="fasten_" + name,
            type=mujoco.mjtEq.mjEQ_WELD,
            name1="case",
            name2=name,
            objtype=mujoco.mjtObj.mjOBJ_BODY,
            active=False,
        )
        e.solref = [0.008, 1]
        e.data[:] = 0
        e.data[6] = 1
        e.data[10] = 1
    s.worldbody.add_camera(
        name="overview",
        pos=[1.15, -1.15, 1.06],
        quat=look_at_quat([1.15, -1.15, 1.06], [0.47, 0.015, 0.40]),
        fovy=42,
    )
    s.worldbody.add_camera(
        name="detail",
        pos=[0.88, -0.36, 0.80],
        quat=look_at_quat([0.88, -0.36, 0.80], [0.51, 0.04, 0.405]),
        fovy=39,
    )
    # Rigidly mounted eye-in-hand camera, matching the workshop camera mount.
    wrist_eye = [0.075, 0.0, 0.035]
    s.body("gripper_base").add_camera(
        name="wrist_camera",
        pos=wrist_eye,
        quat=look_at_quat(wrist_eye, [0.0, 0.0, 0.145]),
        fovy=80.0,
    )
    s.visual.global_.offwidth = 1600
    s.visual.global_.offheight = 1000
    s.visual.headlight.ambient = [0.4, 0.4, 0.4]
    s.visual.headlight.diffuse = [0.7, 0.7, 0.7]
    m = s.compile()
    d = mujoco.MjData(m)
    mujoco.mj_resetDataKeyframe(m, d, m.key("home").id)
    d.ctrl[:6] = [-1.5708, -1.5708, 1.5708, -1.5708, -1.5708, 0]
    for name, xyz in SOURCES.items():
        a = m.jnt_qposadr[m.joint(name + "_joint").id]
        d.qpos[a : a + 3] = xyz
        d.qpos[a + 3 : a + 7] = [1, 0, 0, 0]
    mujoco.mj_forward(m, d)
    return m, d


class Demo:
    def __init__(self, out):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.m, self.d = scene()
        self.robot = Robot(
            self.m,
            self.d,
            target_body="case",
            target_geom="case_base",
            target_joint="case_joint",
        )
        self.m.body_gravcomp[list(self.robot.robot_bodies)] = 1.0
        self.rot = np.diag([1.0, -1.0, -1.0])
        q, _ = self.robot.solve(
            [0.40, -0.10, 0.56],
            self.rot,
            np.array([0, -1.5, -1.4, -1.7, 1.57, 0]),
            multistart=True,
        )
        self.d.qpos[self.robot.qids] = q
        self.d.ctrl[self.robot.aids] = q
        mujoco.mj_forward(self.m, self.d)
        self.phase = 0
        self.stage = "Ready"
        self.next_frame = 0
        self.frames = []
        self.events = []
        self.holding = None
        self.max_penetration = 0

    def event(self, what, **kw):
        record = {"time": float(self.d.time), "phase": self.phase, "event": what, **kw}
        self.events.append(record)
        print(json.dumps(record), flush=True)

    def tick(self, duration):
        for _ in range(round(duration / self.m.opt.timestep)):
            mujoco.mj_step(self.m, self.d)
            if not np.isfinite(self.d.qpos).all():
                raise RuntimeError("Nonfinite physics")
            bad = self.robot.collision_contacts(
                self.d, allow_cube=True, penetration=0.0015
            )
            if bad:
                raise MotionFailure(
                    f"Physical robot collision during {self.stage}: {bad}"
                )
            if self.d.time >= self.next_frame:
                self.frames.append(
                    (
                        float(self.d.time),
                        self.phase,
                        self.stage,
                        self.d.qpos.copy(),
                        self.d.qvel.copy(),
                        self.d.eq_active.copy(),
                    )
                )
                self.next_frame += 0.04

    def move(self, p, stage, duration=1.6):
        self.stage = stage
        robot = self.robot
        robot.initial_qpos = self.d.qpos.copy()
        robot.scratch.qpos[:] = self.d.qpos
        q0 = self.d.qpos[robot.qids].copy()
        p0 = self.d.site_xpos[robot.sid].copy()
        r0 = self.d.site_xmat[robot.sid].reshape(3, 3).copy()
        p = np.asarray(p)
        n = max(2, int(np.linalg.norm(p - p0) / 0.015) + 1)
        rots = Slerp([0, 1], Rotation.from_matrix([r0, self.rot]))
        qs = [q0]
        seed = q0
        ids = list(robot.cgids) if self.holding else []
        if self.holding and self.phase == 4:
            ids = [
                g
                for g in range(self.m.ngeom)
                if self.m.body(self.m.geom_bodyid[g]).name in SOURCES
            ]
        old_type = self.m.geom_contype[ids].copy()
        old_aff = self.m.geom_conaffinity[ids].copy()
        try:
            self.m.geom_contype[ids] = 0
            self.m.geom_conaffinity[ids] = 0
            for u in np.linspace(0, 1, n + 1)[1:]:
                seed, _ = robot.solve(
                    p0 + (p - p0) * u, rots(u).as_matrix(), seed, multistart=False
                )
                qs.append(seed)
        finally:
            self.m.geom_contype[ids] = old_type
            self.m.geom_conaffinity[ids] = old_aff
        qs = np.array(qs)
        duration = max(
            duration, np.max(np.sum(np.abs(np.diff(qs, axis=0)), axis=0)) * 1.8
        )
        steps = math.ceil(duration / self.m.opt.timestep)
        for k in range(steps):
            t = (k + 1) / steps
            u = 10 * t**3 - 15 * t**4 + 6 * t**5
            v = u * (len(qs) - 1)
            i = min(int(v), len(qs) - 2)
            self.d.ctrl[robot.aids] = qs[i] * (1 - (v - i)) + qs[i + 1] * (v - i)
            self.tick(self.m.opt.timestep)
        self.d.ctrl[robot.aids] = qs[-1]
        self.tick(0.3)

    def target(self, name):
        r = self.robot
        r.cbid = self.m.body(name).id
        r.cgids = {i for i in range(self.m.ngeom) if self.m.geom_bodyid[i] == r.cbid}
        r.cgid = min(r.cgids)
        r.target_joint = self.m.joint(name + "_joint").id
        r.cube_qposadr = int(self.m.jnt_qposadr[r.target_joint])

    def pick(self, name):
        self.target(name)
        p = self.d.xpos[self.m.body(name).id].copy()
        p[2] += GRIP[name]
        self.move(
            [p[0], p[1], 0.50 if np.linalg.norm(p[:2]) > 0.58 else 0.53],
            "Approach " + name,
        )
        self.move(p, "Grasp " + name, 2)
        self.stage = "Close fingers"
        self.d.ctrl[self.robot.gid] = 200
        self.tick(1.2)
        f, dot = self.robot.finger_contacts()
        self.event("physical_grasp", object=name, forces=f, normal_dot=dot)
        if min(f.values()) < 0.1 or dot is None or dot > -0.8:
            raise MotionFailure("Bilateral grasp missing")
        self.holding = name
        self.move(
            [p[0], p[1], 0.50 if np.linalg.norm(p[:2]) > 0.58 else 0.53], "Lift " + name
        )
        if self.d.xpos[self.m.body(name).id, 2] < 0.45:
            raise MotionFailure("Object not lifted")
        # Measured held transform for this scripted demo; not a pose-estimator evaluation.
        self.offset = (
            self.d.site_xpos[self.robot.sid] - self.d.xpos[self.m.body(name).id]
        )

    def place(self, name, xyz, fasten=False):
        goal = np.asarray(xyz) + self.offset
        self.move(
            [goal[0], goal[1], 0.50 if np.linalg.norm(goal[:2]) > 0.58 else 0.53],
            "Transfer " + name,
        )
        self.move(goal + [0, 0, 0.045], "Align " + name)
        self.move(goal + [0, 0, 0.001], "Seat " + name, 2.0)
        self.stage = "Release " + name
        self.d.ctrl[self.robot.gid] = 130 if name == "battery" else 0
        self.tick(1.0)
        self.holding = None
        released_forces, _ = self.robot.finger_contacts()
        self.event("finger_release", object=name, forces=released_forces)
        if max(released_forces.values()) > 0.1:
            raise MotionFailure("Fingers still loaded after release")
        error = float(np.linalg.norm(self.d.xpos[self.m.body(name).id] - xyz))
        self.event("released", object=name, position_error_mm=error * 1000)
        if error > 0.006:
            raise MotionFailure("Placement not seated")
        if fasten:
            a = self.m.body("case").id
            b = self.m.body(name).id
            ra = self.d.xmat[a].reshape(3, 3)
            rb = self.d.xmat[b].reshape(3, 3)
            rel = ra.T @ (self.d.xpos[b] - self.d.xpos[a])
            quat = np.empty(4)
            mujoco.mju_mat2Quat(quat, (ra.T @ rb).ravel())
            eid = self.m.equality("fasten_" + name).id
            self.m.eq_data[eid, :3] = 0
            self.m.eq_data[eid, 3:6] = rel
            self.m.eq_data[eid, 6:10] = quat
            self.d.eq_active[eid] = True
            self.event(
                "simplified_fastening", object=name, relative_position=rel.tolist()
            )
        self.move(
            [goal[0], goal[1], 0.50 if np.linalg.norm(goal[:2]) > 0.58 else 0.53],
            "Clear " + name,
        )
        self.d.ctrl[self.robot.gid] = 0
        self.tick(0.4)

    def run(self):
        self.tick(1.5)
        # First raise away from the robot base before the tabletop approach.

        self.pick("case")
        self.place("case", ASSEMBLY)
        for phase, name in enumerate(["battery", "pcb", "lid"], 1):
            self.phase = phase
            self.event("task_start", name=PHASES[phase])
            self.pick(name)
            base = self.d.xpos[self.m.body("case").id].copy()
            self.place(name, base + [0, 0, OFFSETS[name]], fasten=True)
        self.phase = 4
        self.event("task_start", name=PHASES[4])
        self.pick("lid")
        case = self.d.xpos[self.m.body("case").id].copy()
        lid = self.d.xpos[self.m.body("lid").id].copy()
        self.place("lid", np.array([0.64, 0.16, 0.390]) + (lid - case))
        self.move([0.26, -0.05, 0.68], "Retract")
        self.stage = "Assembly complete"
        self.tick(8)
        positions = {
            name: self.d.xpos[self.m.body(name).id].tolist() for name in SOURCES
        }
        self.event("complete", positions=positions)

    def save(self, success, error=None):
        np.savez_compressed(
            self.out / "trajectory.npz",
            time=[f[0] for f in self.frames],
            phase=[f[1] for f in self.frames],
            stage=[f[2] for f in self.frames],
            qpos=[f[3] for f in self.frames],
            qvel=[f[4] for f in self.frames],
            eq_active=[f[5] for f in self.frames],
            eq_data=self.m.eq_data,
        )
        (self.out / "summary.json").write_text(
            json.dumps(
                {
                    "success": success,
                    "error": error,
                    "scope": "scripted application demo, not a visual-method benchmark",
                    "control": "gravity-compensated joint actuators; physical two-sided fingertip grasp; surveyed targets and simulated held offset",
                    "fastening": "seated assembly welds, no gripper welds, no live qpos teleportation",
                    "events": self.events,
                    "simulation_seconds": float(self.d.time),
                },
                indent=2,
            )
            + "\n"
        )


def validate_trace(out):
    """Development acceptance of this one scripted run, never a benchmark."""
    report = json.loads((out / "summary.json").read_text())
    trace = np.load(out / "trajectory.npz")
    grasps = [e for e in report["events"] if e["event"] == "physical_grasp"]
    releases = [e for e in report["events"] if e["event"] == "finger_release"]
    fastenings = [e for e in report["events"] if e["event"] == "simplified_fastening"]
    assert (
        report["success"]
        and len(grasps) == 5
        and len(releases) == 5
        and len(fastenings) == 3
    )
    assert all(
        min(e["forces"].values()) > 0.1 and e["normal_dot"] < -0.8 for e in grasps
    )
    assert all(max(e["forces"].values()) < 0.1 for e in releases)
    assert list(np.unique(trace["phase"])) == [0, 1, 2, 3, 4]
    assert np.all(np.diff(trace["time"]) > 0) and np.isfinite(trace["qpos"]).all()
    model, data = scene()
    model.eq_data[:] = trace["eq_data"]
    data.qpos[:] = trace["qpos"][-1]
    data.qvel[:] = trace["qvel"][-1]
    data.eq_active[:] = trace["eq_active"][-1]
    mujoco.mj_forward(model, data)
    case_id = model.body("case").id
    xy_error = float(np.linalg.norm(data.xpos[case_id, :2] - [0.64, 0.16]))
    assert xy_error < 0.006
    speeds, steps = {}, {}
    for name in SOURCES:
        joint = model.joint(name + "_joint").id
        dof, qpos = model.jnt_dofadr[joint], model.jnt_qposadr[joint]
        speeds[name] = float(np.linalg.norm(data.qvel[dof : dof + 3]))
        steps[name] = float(
            np.max(
                np.linalg.norm(
                    np.diff(trace["qpos"][:, qpos : qpos + 3], axis=0), axis=1
                )
            )
        )
        assert speeds[name] < 0.005 and steps[name] < 0.020
    contacts = [
        float(c.dist)
        for c in data.contact
        if {model.geom(int(c.geom1)).name, model.geom(int(c.geom2)).name}
        == {"case_base", "output_pad"}
    ]
    assert contacts and min(contacts) > -0.001
    result = dict(
        purpose="single-demo development acceptance, not benchmark metrics",
        passed=True,
        physical_pickups=5,
        unloaded_releases=5,
        seated_component_connections=3,
        all_five_phases_recorded=True,
        continuous_trace_frames=len(trace["time"]),
        simulation_duration_s=report["simulation_seconds"],
        final_case_output_xy_error_mm=xy_error * 1000,
        final_case_output_contact_distances_m=contacts,
        final_component_speeds_m_s=speeds,
        maximum_translation_step_at_25hz_m=steps,
    )
    (out / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def render(out, target_seconds=35):
    from PIL import Image, ImageDraw, ImageFont

    report = json.loads((out / "summary.json").read_text())
    if not report["success"]:
        raise RuntimeError("Only a completed run may be rendered as the demo")
    m, d = scene()
    trace = np.load(out / "trajectory.npz")
    m.eq_data[:] = trace["eq_data"]
    duration = float(trace["time"][-1])
    fps = 25
    renderer = mujoco.Renderer(m, width=1280, height=720)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    bold = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20
    )
    target = out / "electronics_assembly_demo.mp4"
    pipe = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "1600x1000",
            "-r",
            str(fps),
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(target),
        ],
        stdin=subprocess.PIPE,
    )
    try:
        for j, t in enumerate(
            np.linspace(trace["time"][0], duration, round(target_seconds * fps))
        ):
            i = min(int(np.searchsorted(trace["time"], t)), len(trace["time"]) - 1)
            d.qpos[:] = trace["qpos"][i]
            d.qvel[:] = trace["qvel"][i]
            d.eq_active[:] = trace["eq_active"][i]
            d.time = t
            mujoco.mj_forward(m, d)
            phase = int(trace["phase"][i])
            name = ["case", "battery", "pcb", "lid", "case"][phase]
            focus_now = d.xpos[m.body(name).id].copy() + [0, 0, 0.018]
            focus = focus_now if j == 0 else 0.80 * focus + 0.20 * focus_now
            cid = m.camera("detail").id
            eye = focus + [0.23, -0.30, 0.27]
            m.cam_pos[cid] = eye
            m.cam_quat[cid] = look_at_quat(eye, focus)
            m.cam_fovy[cid] = 30
            mujoco.mj_forward(m, d)
            renderer.update_scene(d, camera="overview")
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
            wide = renderer.render().copy()
            renderer.update_scene(d, camera="detail")
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
            detail = renderer.render().copy()
            renderer.update_scene(d, camera="wrist_camera")
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
            wrist = renderer.render().copy()
            canvas = Image.new("RGB", (1600, 1000), "#182a37")
            canvas.paste(Image.fromarray(wide).resize((1600, 900)), (0, 75))
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((0, 0, 1600, 74), fill="#182a37")
            draw.text(
                (24, 12),
                "SENSOR MODULE | ELECTRONICS ASSEMBLY",
                font=bold,
                fill="white",
            )
            draw.text(
                (24, 43),
                f"One continuous application demo  /  {duration/target_seconds:.1f}x playback  /  MuJoCo + UR5e",
                font=font,
                fill="#acccd4",
            )
            draw.rectangle((1092, 94, 1580, 404), fill="#182a37")
            canvas.paste(Image.fromarray(detail).resize((480, 270)), (1096, 98))
            draw.text(
                (1110, 376), "DETAIL  /  " + PHASES[phase], font=font, fill="white"
            )
            draw.rectangle((1092, 420, 1580, 730), fill="#182a37")
            canvas.paste(Image.fromarray(wrist).resize((480, 270)), (1096, 424))
            draw.text(
                (1110, 702), "WRIST CAMERA  /  synchronized", font=font, fill="white"
            )
            draw.rectangle((20, 800, 850, 842), fill="#182a37")
            draw.text(
                (34, 809), str(trace["stage"][i]).upper(), font=bold, fill="white"
            )
            for k, label in enumerate(
                [
                    "01  ENCLOSURE",
                    "02  BATTERY",
                    "03  CIRCUIT BOARD",
                    "04  COVER",
                    "05  OUTPUT",
                ]
            ):
                x = 24 + k * 315
                active = k == phase
                draw.rounded_rectangle(
                    (x, 864, x + 299, 949),
                    radius=8,
                    fill="#156b80" if active else "#dce5e9",
                )
                draw.text(
                    (x + 14, 898),
                    label,
                    font=bold,
                    fill="white" if active else "#4f6470",
                )
                if active:
                    draw.rectangle((x + 10, 874, x + 289, 879), fill="#f0b84d")
            draw.rectangle((0, 963, 1600, 1000), fill="#182a37")
            draw.text(
                (24, 972),
                "Application demo only | scripted fixture coordinates | physical grasping | simplified seated fastening",
                font=font,
                fill="#b6cbd4",
            )
            if j in [0, round(target_seconds * fps) - 1]:
                canvas.save(out / ("initial.png" if j == 0 else "final.png"))
            pipe.stdin.write(np.asarray(canvas).tobytes())
            if j % 125 == 0:
                print("render", j, flush=True)
    finally:
        renderer.close()
        pipe.stdin.close()
        code = pipe.wait()
    if code:
        raise RuntimeError("Video encode failed")
    (out / "render_manifest.json").write_text(
        json.dumps(
            {
                "video": target.name,
                "duration_s": target_seconds,
                "fps": fps,
                "simulation_duration_s": duration,
                "playback_speed": duration / target_seconds,
                "views": [
                    "overview",
                    "detail (cinematic following camera)",
                    "wrist_camera (rigid gripper mount)",
                ],
                "wrist_camera_parent": "gripper_base",
                "wrist_camera_local_position_m": [0.075, 0, 0.035],
                "all_views_share_same_state": True,
                "cuts": 0,
                "source_frame_indices": [
                    min(int(np.searchsorted(trace["time"], t)), len(trace["time"]) - 1)
                    for t in np.linspace(
                        trace["time"][0], duration, round(target_seconds * fps)
                    )
                ],
            },
            indent=2,
        )
        + "\n"
    )
    print(target, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--render-only", action="store_true")
    p.add_argument("--render", action="store_true")
    p.add_argument("--seconds", type=float, default=35)
    args = p.parse_args()
    if not args.render_only:
        demo = Demo(args.output)
        try:
            demo.run()
            demo.save(True)
            validate_trace(args.output)
        except Exception as e:
            demo.save(False, str(e))
            raise
    if args.render_only:
        validate_trace(args.output)
    if args.render or args.render_only:
        render(args.output, args.seconds)
