"""One physical scene containing three free objects, with independent grasps."""
import numpy as np
from scipy.spatial.transform import Rotation

from .scene import build_scene, mujoco
from .direct_route import configure_direct_table, plan_direct, set_front_ready
from .foundationpose import validate_pose
from .motion import Robot
from .parts import PARTS, configure_parts


def build_multi_scene(parts=PARTS):
    def configure(spec):
        configure_direct_table(spec)
        configure_parts(spec, parts)
        # Three ground-level slots leave room for fingers to open before retreat.
        spec.body("target_tray").pos = [.47, .18, .375]
        spec.geom("tray_bottom").size = [.16, .10, .007]
        for name, sign in (("left", -1), ("right", 1)):
            spec.geom("tray_wall_"+name).pos = [sign*.155, 0, .034]
        for name, sign in (("front", -1), ("back", 1)):
            spec.geom("tray_wall_"+name).size = [.16, .005, .02]
        if any(getattr(part,"sphere",False) for part in parts):
            spec.geom("tray_bottom").size = [.16, .14, .007]
            for name in ("left","right"):
                spec.geom("tray_wall_"+name).size = [.005,.14,.02]
            for name,sign in (("front",-1),("back",1)):
                spec.geom("tray_wall_"+name).pos = [0,sign*.135,.034]

    first = parts[0]
    model, data = build_scene(first.xy, calibration_board=False, configure_spec=configure,
                              object_z=.375+first.half_height+.001)
    # Initial conditions only. All subsequent object motion comes from contact.
    for part in parts:
        adr = model.jnt_qposadr[model.joint(part.joint).id]
        data.qpos[adr:adr+3] = [*part.xy, .375+part.half_height+.001]
        data.qpos[adr+3:adr+7] = [1, 0, 0, 0]
    set_front_ready(model, data)
    mujoco.mj_forward(model, data)
    return model, data


class MultiRobot(Robot):
    def __init__(self, model, data, part, known_poses, *, ground_truth=False, parts=PARTS):
        super().__init__(model, data, target_vertices=part.vertices, target_body=part.body,
                         target_geom=part.geom, target_joint=part.joint,
                         target_geoms=getattr(part,"collision_names",None))
        self.part = part
        self.ground_truth = ground_truth
        self.known_poses = known_poses
        # Collision objects are located using the same estimated observation
        # chain as the selected target. No simulator object pose enters control.
        for other in parts:
            pose = validate_pose(known_poses[other.key])
            adr = model.jnt_qposadr[model.joint(other.joint).id]
            self.initial_qpos[adr:adr+3] = pose[:3, 3]
            quat = Rotation.from_matrix(pose[:3, :3]).as_quat()
            self.initial_qpos[adr+3:adr+7] = quat[[3, 0, 1, 2]]

    def plan(self, object_pose=None, yaw=0.):
        pose = validate_pose(self.known_poses[self.part.key] if object_pose is None else object_pose)
        if not getattr(self.part,"sphere",False) and pose[2, 2] < .85:
            raise ValueError(f"{self.part.key} is not upright enough for its configured grasp")
        xyz = pose[:3, 3].copy()
        heading = float(np.arctan2(pose[1, 0], pose[0, 0]))
        period=getattr(self.part,"yaw_period",np.pi)
        grasp_yaw = (heading+period/2) % period - period/2 if period else 0.
        offset=pose[:3,:3]@np.asarray(getattr(self.part,"grasp_offset",(0.,0.,0.)))
        grasp_xyz=xyz+offset
        grasp_z = float(grasp_xyz[2]+self.part.grasp_offset_z)
        centre_z = max(float(xyz[2]), .375+self.part.half_height)
        self.initial_qpos[self.cube_qposadr+2] = centre_z
        source = "ground_truth_control_baseline" if self.ground_truth else "vision_pose_file"
        carry_offset=np.r_[-offset[:2],centre_z-grasp_z]
        plan = plan_direct(self, grasp_xyz, grasp_yaw, grasp_z, .437+offset[2], carry_offset, source,
                           destination_xy=np.asarray(self.part.destination_xy)+offset[:2],
                           payload_destination_xy=self.part.destination_xy)
        plan.update(target_id=self.part.key, destination_xy_m=list(self.part.destination_xy))
        return plan


def physical_outcomes(model, data, parts=PARTS):
    """Outcome evaluation only; this function never supplies control targets."""
    output = []
    for part in parts:
        body = model.body(part.body).id
        jid = model.joint(part.joint).id
        dof = model.jnt_dofadr[jid]
        xyz = data.xpos[body]
        vertices = part.vertices @ data.xmat[body].reshape(3, 3).T + xyz
        normal_force = 0.
        geoms={model.geom(name).id for name in getattr(part,"collision_names",(part.geom,))}
        tray=model.geom("tray_bottom").id
        for i, contact in enumerate(data.contact):
            pair={int(contact.geom1),int(contact.geom2)}
            if tray in pair and geoms.intersection(pair):
                force = np.zeros(6)
                mujoco.mj_contactForce(model, data, i, force)
                normal_force += max(0., float(force[0]))
        speed = float(np.linalg.norm(data.qvel[dof:dof+3]))
        omega = float(np.linalg.norm(data.qvel[dof+3:dof+6]))
        low_x = data.geom_xpos[model.geom("tray_wall_left").id, 0] + .005
        high_x = data.geom_xpos[model.geom("tray_wall_right").id, 0] - .005
        low_y = data.geom_xpos[model.geom("tray_wall_front").id, 1] + .005
        high_y = data.geom_xpos[model.geom("tray_wall_back").id, 1] - .005
        inside = bool(np.all((vertices[:, 0] > low_x) & (vertices[:, 0] < high_x)) and
                      np.all((vertices[:, 1] > low_y) & (vertices[:, 1] < high_y)))
        output.append({"id": part.key, "position_m": xyz.tolist(), "tray_support_force_n": normal_force,
                       "inside_tray": inside, "linear_speed_m_s": speed, "angular_speed_rad_s": omega,
                       "success": inside and normal_force > .1 and speed < .005 and omega < .05,
                       "slot_error_mm": float(1000*np.linalg.norm(xyz[:2]-part.destination_xy))})
    return output
