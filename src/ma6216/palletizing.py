"""Vision-driven, contact-supported two-column/two-layer palletizing."""
import math

import numpy as np
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation, Slerp

from .scene import mujoco
from .parts import Part
from .multi_object import build_multi_scene
from .motion import Robot, MotionFailure
from .foundationpose import validate_rigid_transform


TABLE_Z=.375
PALLET_Z=.389
HEIGHT=.040
TRANSFER_Z=.56
RELEASE_CLEARANCE=.016
FOOTPRINT=((-40,-25),(32,-25),(40,-17),(40,25),(-40,25))
VERTICES=tuple((x,y,z) for z in (-20,20) for x,y in FOOTPRINT)
PARTS=(
    Part('green','Flat-top pallet block',VERTICES,(.08,.68,.33,1.),(46,75,38),(95,255,255),
         'target_cube',(.38,-.25),(.40,.18)),
    Part('orange','Flat-top pallet block',VERTICES,(.95,.43,.06,1.),(5,100,50),(29,255,255),
         'pallet_orange',(.54,-.25),(.54,.18)),
    Part('purple','Flat-top pallet block',VERTICES,(.58,.16,.76,1.),(125,80,40),(168,255,255),
         'pallet_purple',(.38,-.08),(.40,.18)),
    Part('red','Flat-top pallet block',VERTICES,(.92,.05,.05,1.),(0,110,40),(10,255,255),
         'pallet_red',(.54,-.08),(.54,.18)),
)
BY_KEY={p.key:p for p in PARTS}
LEVELS={'green':0,'orange':0,'purple':1,'red':1}
SUPPORTS={'green':None,'orange':None,'purple':'green','red':'orange'}


def rz(yaw):
    return Rotation.from_euler('z',yaw).as_matrix()


def set_pose(qpos, model, part, pose):
    """For scene initialization or PRIVATE planning data only."""
    adr=model.jnt_qposadr[model.joint(part.joint).id]
    qpos[adr:adr+3]=pose[:3,3]
    quat=Rotation.from_matrix(pose[:3,:3]).as_quat()
    qpos[adr+3:adr+7]=quat[[3,0,1,2]]


def build_pallet_scene(layout=0):
    model,data=build_multi_scene(PARTS)
    yaw_sets=((0.,0.,0.,0.),(12.,-12.,8.,-8.))
    if layout not in range(len(yaw_sets)):
        raise ValueError('Supported layouts: 0 and 1')
    for index,part in enumerate(PARTS):
        pose=np.eye(4);pose[:3,:3]=rz(np.deg2rad(yaw_sets[layout][index]))
        xy=np.asarray(part.xy)+ (np.array([.003*(-1)**index,.004]) if layout else 0.)
        pose[:3,3]=[*xy,TABLE_Z+HEIGHT/2+.001]
        set_pose(data.qpos,model,part,pose)
    mujoco.mj_forward(model,data)
    return model,data


def truth_poses(model,data):
    """Explicit diagnostic baseline or evaluation only."""
    poses={}
    for part in PARTS:
        body=model.body(part.body).id
        pose=np.eye(4);pose[:3,:3]=data.xmat[body].reshape(3,3);pose[:3,3]=data.xpos[body]
        poses[part.key]=pose
    return poses


def footprint_margin(point, vertices):
    hull=ConvexHull(vertices[:,:2])
    distances=-(hull.equations[:,:2]@point+hull.equations[:,2])
    return float(np.min(distances))


def block_outcome(model,data,part):
    """Independent physical acceptance. Never supplies motion targets."""
    body=model.body(part.body).id
    xyz=data.xpos[body].copy();rotation=data.xmat[body].reshape(3,3)
    vertices=part.vertices@rotation.T+xyz
    support_key=SUPPORTS[part.key]
    support_geom=model.geom(BY_KEY[support_key].geom).id if support_key else model.geom('tray_bottom').id
    target_geom=model.geom(part.geom).id
    force=0.;max_penetration=0.
    for i,c in enumerate(data.contact):
        if {int(c.geom1),int(c.geom2)}=={target_geom,support_geom}:
            f=np.zeros(6);mujoco.mj_contactForce(model,data,i,f)
            force+=max(0.,float(f[0]));max_penetration=max(max_penetration,float(-c.dist))
    if support_key:
        support=BY_KEY[support_key];sid=model.body(support.body).id
        sv=support.vertices@data.xmat[sid].reshape(3,3).T+data.xpos[sid]
        actual_surface=float(sv[:,2].max())
        margin=footprint_margin(data.xipos[body,:2],sv)
        support_xy_error=float(np.linalg.norm(xyz[:2]-data.xpos[sid,:2]))
    else:
        actual_surface=PALLET_Z
        margin=min(xyz[0]-.32,.62-xyz[0],xyz[1]-.09,.27-xyz[1])
        support_xy_error=0.
    jid=model.joint(part.joint).id;dof=model.jnt_dofadr[jid]
    speed=float(np.linalg.norm(data.qvel[dof:dof+3]));omega=float(np.linalg.norm(data.qvel[dof+3:dof+6]))
    xy_error=float(np.linalg.norm(xyz[:2]-part.destination_xy))
    plane_gap=float(vertices[:,2].min()-actual_surface)
    tilt=float(np.rad2deg(np.arccos(np.clip(rotation[2,2],-1.,1.))))
    heading=float(np.arctan2(rotation[1,0],rotation[0,0]))
    yaw_error=abs(float(np.rad2deg(np.arctan2(np.sin(heading),np.cos(heading)))))
    nominal_z=PALLET_Z+LEVELS[part.key]*HEIGHT+HEIGHT/2
    inside=bool(np.all((vertices[:,0]>.32)&(vertices[:,0]<.62)) and
                np.all((vertices[:,1]>.09)&(vertices[:,1]<.27)))
    success=(inside and force>.2 and abs(plane_gap)<.003 and margin>.008 and
             xy_error<.010 and abs(xyz[2]-nominal_z)<.004 and tilt<3. and yaw_error<5. and
             speed<.005 and omega<.05)
    return {'id':part.key,'level':LEVELS[part.key],'support':support_key or 'pallet',
            'success':bool(success),'position_m':xyz.tolist(),'nominal_layer_centre_z_m':nominal_z,
            'slot_xy_error_mm':1000*xy_error,'relative_support_xy_error_mm':1000*support_xy_error,
            'support_normal_force_n':force,'support_surface_gap_mm':1000*plane_gap,
            'max_support_contact_penetration_mm':1000*max_penetration,
            'support_polygon_margin_mm':1000*margin,'inside_pallet':inside,
            'tilt_deg':tilt,'yaw_error_deg':yaw_error,'linear_speed_m_s':speed,'angular_speed_rad_s':omega}


class PalletRobot(Robot):
    def __init__(self,model,data,part,known,*,ground_truth=False):
        super().__init__(model,data,target_vertices=part.vertices,target_body=part.body,
                         target_geom=part.geom,target_joint=part.joint)
        self.part=part;self.known=known;self.ground_truth=ground_truth
        # All collision obstacles use visual estimates or commanded placements.
        # Actual robot joint/finger states are proprioception, not object truth.
        for other in PARTS:
            pose=validate_rigid_transform(known[other.key]).copy()
            heading=np.arctan2(pose[1,0],pose[0,0]);pose[:3,:3]=rz(heading)
            floor=PALLET_Z+LEVELS[other.key]*HEIGHT if pose[1,3]>0 else TABLE_Z
            pose[2,3]=max(pose[2,3],floor+HEIGHT/2)
            set_pose(self.initial_qpos,model,other,pose)

    def collision_contacts(self,data=None,allow_cube=False,penetration=.0005):
        bad=super().collision_contacts(data,allow_cube,penetration)
        if data is self.data:
            support=SUPPORTS[self.part.key]
            allowed={self.model.geom('worktable').id,
                     self.model.geom(BY_KEY[support].geom).id if support else self.model.geom('tray_bottom').id}
            for c in data.contact:
                g1,g2=int(c.geom1),int(c.geom2)
                if self.cgid not in (g1,g2) or c.dist>=-penetration:continue
                other=g2 if g1==self.cgid else g1
                if other in allowed or int(self.model.geom_bodyid[other]) in self.robot_bodies:continue
                bad.append({'geom1':self.model.geom(g1).name,'geom2':self.model.geom(g2).name,
                            'penetration_m':float(-c.dist),'reason':'unexpected payload contact'})
        return bad

    def plan(self,object_pose=None,yaw=0.):
        pose=validate_rigid_transform(self.known[self.part.key] if object_pose is None else object_pose)
        xyz=pose[:3,3].copy()
        if not (.30<xyz[0]<.63 and -.33<xyz[1]<-.02 and .36<xyz[2]<.45 and pose[2,2]>.9):
            raise MotionFailure(f'Visual source pose outside palletizing workspace: {xyz}')
        heading=float(np.arctan2(pose[1,0],pose[0,0]))
        grasp_yaw=(heading+np.pi/2)%np.pi-np.pi/2
        source_rotation=rz(grasp_yaw)@np.diag([1.,-1.,-1.])
        object_rotation=rz(heading)
        grasp=np.r_[xyz[:2],xyz[2]+self.part.grasp_offset_z]
        centre_z=max(float(xyz[2]),TABLE_Z+HEIGHT/2)
        tool_R_object=source_rotation.T@object_rotation
        tool_t_object=source_rotation.T@(np.r_[xyz[:2],centre_z]-grasp)
        support=SUPPORTS[self.part.key]
        destination_xy=np.asarray(self.part.destination_xy,dtype=float)
        if support:
            # Reobserved lower block aligns the next layer in XY. Known CAD and
            # surveyed pallet plane supply nominal Z, never a simulator pose.
            destination_xy=validate_rigid_transform(self.known[support])[:2,3].copy()
        plane=PALLET_Z+LEVELS[self.part.key]*HEIGHT
        placed=np.eye(4);placed[:3,3]=[*destination_xy,plane+HEIGHT/2]
        place_rotation=placed[:3,:3]@tool_R_object.T
        release_centre=placed[:3,3]+[0,0,RELEASE_CLEARANCE]
        release_tcp=release_centre-place_rotation@tool_t_object
        targets=[('APPROACH',np.r_[xyz[:2],TRANSFER_Z],source_rotation),
                 ('GRASP',grasp,source_rotation),('LIFT',np.r_[xyz[:2],TRANSFER_Z],source_rotation),
                 ('HOVER_TRAY',np.r_[release_tcp[:2],TRANSFER_Z],place_rotation),
                 ('PLACE',release_tcp,place_rotation),
                 ('RETREAT',np.r_[release_tcp[:2],TRANSFER_Z],place_rotation)]
        original=self.initial_qpos.copy()
        q=self.data.ctrl[self.aids].copy();self.scratch.qpos[:]=original
        start,start_rotation=self.fk(q);waypoints=[]
        def payload(position,rotation):
            result=np.eye(4);result[:3,:3]=rotation@tool_R_object
            result[:3,3]=position+rotation@tool_t_object
            return result
        try:
            for stage,destination,rotation in targets:
                carrying=stage in ('LIFT','HOVER_TRAY','PLACE')
                if stage=='RETREAT':set_pose(self.initial_qpos,self.model,self.part,placed)
                distance=np.linalg.norm(destination-start)
                turn=Rotation.from_matrix(rotation@start_rotation.T).magnitude()
                segments=max(16 if stage=='HOVER_TRAY' else 1,math.ceil(distance/.015),math.ceil(turn/.08))
                slerp=Slerp([0.,1.],Rotation.from_matrix([start_rotation,rotation]))
                path=[q.tolist()];samples=0
                for index in range(1,segments+1):
                    fraction=index/segments
                    position=(1-fraction)*start+fraction*destination;attitude=slerp(fraction).as_matrix()
                    if carrying:set_pose(self.initial_qpos,self.model,self.part,payload(position,attitude))
                    next_q,error=self.solve(position,attitude,q)
                    if np.max(np.abs(next_q-q))>.30:raise MotionFailure(f'IK branch change in {stage}')
                    count=max(2,math.ceil(float(np.max(np.abs(next_q-q)))/.025)+1)
                    for u in np.linspace(0,1,count):
                        self.scratch.qpos[:]=self.initial_qpos
                        p,r=self.fk((1-u)*q+u*next_q)
                        if carrying:
                            set_pose(self.scratch.qpos,self.model,self.part,payload(p,r))
                            mujoco.mj_forward(self.model,self.scratch)
                        bad=self.collision_contacts(allow_cube=carrying or stage=='GRASP')
                        if bad:raise MotionFailure(f'{stage} robot collision: {bad}')
                        if carrying:
                            for c in self.scratch.contact:
                                if self.cgid not in (int(c.geom1),int(c.geom2)) or c.dist>=-.0005:continue
                                other=int(c.geom2) if c.geom1==self.cgid else int(c.geom1)
                                if other not in self.pad_sides:
                                    raise MotionFailure(f'{stage} payload collision with {self.model.geom(other).name}')
                        samples+=1
                    q=next_q;path.append(q.tolist())
                waypoints.append({'name':stage,'q':q.tolist(),'tcp_position':destination.tolist(),
                                  'path_q':path,'ik':error,'collision_check':{'samples':samples,'cartesian_segments':segments}})
                start,start_rotation=destination,rotation
        finally:
            self.initial_qpos[:]=original
        return {'source':'ground_truth_control_baseline' if self.ground_truth else 'vision_pose_file',
                'route':'palletizing','target_id':self.part.key,'level':LEVELS[self.part.key],
                'support':support or 'pallet','support_plane_z_prior_m':plane,
                'release_clearance_m':RELEASE_CLEARANCE,'placed_pose_command':placed.tolist(),
                'object_position':xyz.tolist(),'waypoints':waypoints}

    def evaluate_placement(self,plan):
        outcome=block_outcome(self.model,self.data,self.part)
        forces,_=self.finger_contacts()
        result={'success':outcome['success'] and max(forces.values())<.05,
                'control_source':plan['source'],'placement_evaluation_only':outcome,
                'final_finger_normal_forces_n':forces,
                'max_joint_tracking_error_rad':self.max_tracking_error,
                'max_unexpected_robot_penetration_m':self.max_robot_penetration,
                'max_target_support_penetration_m':self.max_cube_support_penetration,
                'bilateral_loaded_contact_fraction':self.loaded_bilateral_steps/max(1,self.holding_steps),
                'holding_physics_steps':self.holding_steps,'min_holding_finger_normal_force_n':self.minimum_holding_normal_force,
                'stages':self.stage_metrics,'simulation_time_s':float(self.data.time)}
        if not result['success']:raise MotionFailure(f'Stack placement acceptance failed: {result}')
        return result
