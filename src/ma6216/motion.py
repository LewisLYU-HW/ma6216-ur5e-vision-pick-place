"""Offline UR5e pose solving, collision screening and physical joint execution.

The planner writes qpos only in its private kinematic scratch MjData. The live
simulation is driven exclusively through actuators after reset/initialization.
"""
from __future__ import annotations
import json
import math
import time
from pathlib import Path
import numpy as np
import mujoco
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

JOINT_NAMES = ['shoulder_pan_joint','shoulder_lift_joint','elbow_joint','wrist_1_joint','wrist_2_joint','wrist_3_joint']
ACTUATOR_NAMES = ['shoulder_pan','shoulder_lift','elbow','wrist_1','wrist_2','wrist_3']


class MotionFailure(RuntimeError):
    pass


class Robot:
    def __init__(self, model, data, *, target_vertices=None, target_body="target_cube",
                 target_geom="target_cube_geom", target_joint="target_cube_freejoint", target_geoms=None):
        self.model, self.data = model, data
        self.target_vertices = None if target_vertices is None else np.asarray(target_vertices, dtype=float)
        self.joints=np.array([model.joint(n).id for n in JOINT_NAMES])
        self.qids=model.jnt_qposadr[self.joints]
        self.dids=model.jnt_dofadr[self.joints]
        self.aids=np.array([model.actuator(n).id for n in ACTUATOR_NAMES])
        self.gid=model.actuator('gripper_fingers_actuator').id
        self.sid=model.site('gripper_pinch').id
        self.cbid=model.body(target_body).id
        self.cgid=model.geom(target_geom).id
        self.cgids = {model.geom(name).id for name in target_geoms} if target_geoms else {self.cgid}
        self.target_joint = model.joint(target_joint).id
        self.cube_qposadr=int(model.jnt_qposadr[self.target_joint])
        self.low=np.maximum(model.jnt_range[self.joints,0],model.actuator_ctrlrange[self.aids,0])+.001
        self.high=np.minimum(model.jnt_range[self.joints,1],model.actuator_ctrlrange[self.aids,1])-.001
        self.scratch=mujoco.MjData(model)
        self.scratch.qpos[:]=data.qpos
        self.initial_qpos=data.qpos.copy()
        self.scratch.qvel[:]=0
        self.home=data.qpos[self.qids].copy()
        self.pad_sides={model.geom('gripper_'+side+'_pad'+str(i)).id:side for side in ('left','right') for i in (1,2)}
        self.robot_bodies = {model.body('base').id}
        for body in range(1, model.nbody):
            if int(model.body_parentid[body]) in self.robot_bodies:
                self.robot_bodies.add(body)
        self.max_tracking_error=0.
        self.min_transport_height=math.inf
        self.min_transfer_height=math.inf
        self.holding_steps=0
        self.loaded_bilateral_steps=0
        self.minimum_holding_normal_force=math.inf
        self.maximum_holding_normal_dot=-1.
        self.max_robot_penetration=0.
        self.max_cube_support_penetration=0.
        self.samples=[]
        self.stage_metrics=[]
        self.sim_tick=0

    def collision_contacts(self, data=None, allow_cube=False, penetration=.0005):
        d=data or self.scratch
        bad=[]
        for c in d.contact:
            g1,g2=int(c.geom1),int(c.geom2)
            b1,b2=int(self.model.geom_bodyid[g1]),int(self.model.geom_bodyid[g2])
            clearance = max(getattr(self, "obstacle_clearances", {}).get(g1, -penetration),
                            getattr(self, "obstacle_clearances", {}).get(g2, -penetration))
            if c.dist>=clearance:continue
            if b1 not in self.robot_bodies and b2 not in self.robot_bodies:continue
            if allow_cube and self.cgids.intersection((g1,g2)) and any(g in self.pad_sides for g in (g1,g2)):continue
            bad.append({'geom1':self.model.geom(g1).name or f'geom_{g1}', 'geom2':self.model.geom(g2).name or f'geom_{g2}', 'body1':self.model.body(b1).name,'body2':self.model.body(b2).name,'penetration_m':float(-c.dist)})
        return bad

    def fk(self, q):
        self.scratch.qpos[self.qids]=q
        mujoco.mj_forward(self.model,self.scratch)
        return self.scratch.site_xpos[self.sid].copy(),self.scratch.site_xmat[self.sid].reshape(3,3).copy()

    def solve(self, pos, rot, seed, multistart=False):
        pos,rot=np.asarray(pos),np.asarray(rot)
        self.scratch.qpos[:]=self.initial_qpos
        def fun(q):
            p,r=self.fk(q)
            return np.r_[p-pos,.25*Rotation.from_matrix(rot@r.T).as_rotvec()]
        seeds=[seed]
        if multistart:
            for pan in [-3.,-1.5,0.,1.5,3.]:
                for elbow in [1.6,-1.6]:
                    seeds.append(np.array([pan,-1.5,elbow,-1.6,-1.57,0.]))
        candidates=[]; diagnostics=[]
        for s in seeds:
            sol=least_squares(fun,np.clip(s,self.low,self.high),bounds=(self.low,self.high),max_nfev=160,xtol=1e-10,ftol=1e-10,gtol=1e-10)
            p,r=self.fk(sol.x)
            pe=np.linalg.norm(p-pos);re=Rotation.from_matrix(rot@r.T).magnitude()
            bad=self.collision_contacts(allow_cube=True)
            diagnostics.append({'p_error':float(pe),'r_error':float(re),'contacts':bad,'q':sol.x.tolist()})
            if pe>.001 or re>.005:continue
            if bad:continue
            # Equivalent revolutions are chosen close to the previous waypoint.
            q=sol.x.copy()
            for i in range(6):
                choices=[q[i]+k*2*np.pi for k in range(-2,3) if self.low[i]<=q[i]+k*2*np.pi<=self.high[i]]
                q[i]=min(choices,key=lambda a:abs(a-seed[i]))
            candidates.append((np.linalg.norm(q-seed),q,pe,re))
        if not candidates:
            raise MotionFailure(f'No collision-free offline IK at {pos.tolist()}; best={min(diagnostics,key=lambda d:d["p_error"])}')
        _,q,pe,re=min(candidates,key=lambda a:a[0])
        return q,{'position_error_m':float(pe),'rotation_error_rad':float(re)}

    def check_path(self,q0,q1,allow_cube=False,carry_offset_z=None):
        n=max(2,int(np.ceil(np.max(np.abs(q1-q0))/.025))+1)
        for u in np.linspace(0.,1.,n):
            self.fk(q0+(q1-q0)*u)
            if carry_offset_z is not None:
                adr=self.cube_qposadr
                offset=np.asarray(carry_offset_z,dtype=float)
                if offset.ndim==0:offset=np.array([0.,0.,float(offset)])
                self.scratch.qpos[adr:adr+3]=self.scratch.site_xpos[self.sid]+offset
                # Top-down yaw grasp preserves the object's initial orientation.
                mujoco.mj_forward(self.model,self.scratch)
            bad=self.collision_contacts(allow_cube=allow_cube)
            if bad:return False,{'fraction':float(u),'contacts':bad}
            if carry_offset_z is not None:
                for c in self.scratch.contact:
                    if not self.cgids.intersection((int(c.geom1),int(c.geom2))) or c.dist>=-.0005:continue
                    other=int(c.geom2) if int(c.geom1) in self.cgids else int(c.geom1)
                    if other in self.cgids:continue
                    if other in self.pad_sides:continue
                    return False,{'fraction':float(u),'carried_object_collision':self.model.geom(other).name,'penetration_m':float(-c.dist)}
        return True,{'samples':n}

    def plan(self, object_pose=None, xy=None, yaw=0.):
        if object_pose is not None:
            object_pose=np.asarray(object_pose,float)
            if object_pose.shape!=(4,4) or not np.isfinite(object_pose).all() or not np.allclose(object_pose[3],[0,0,0,1],atol=1e-6):
                raise ValueError('world_T_object must be a finite 4x4 rigid transform')
            R=object_pose[:3,:3]
            if not np.allclose(R.T@R,np.eye(3),atol=1e-4) or not np.isclose(np.linalg.det(R),1.,atol=1e-4):
                raise ValueError('world_T_object must have a proper orthonormal rotation')
            xyz=object_pose[:3,3].copy()
            if not (.25<xyz[0]<.65 and -.30<xyz[1]<.0 and .36<xyz[2]<.46):
                raise ValueError(f'Estimated cube pose is outside the validated acquisition workspace: {xyz}')
            # Uniform 50 mm cube: 24 rotational symmetries are physically equal.
            # Choose a horizontal face axis even when its model X axis is vertical.
            axis=int(np.argmax(np.linalg.norm(R[:2,:],axis=0)))
            yaw=math.atan2(R[1,axis],R[0,axis])
            yaw=(yaw+math.pi/4)%(math.pi/2)-math.pi/4
            # Give the collision planner its own estimate of the obstacle.
            # A known tabletop support plane provides a lower bound on Z.
            # This is private MjData, never the live object's qpos.
            adr=self.cube_qposadr
            self.initial_qpos[adr:adr+3]=[xyz[0],xyz[1],max(xyz[2],.400)]
            self.initial_qpos[adr+3:adr+7]=[math.cos(yaw/2),0.,0.,math.sin(yaw/2)]
            source='vision_pose_file'
        else:
            xyz=self.data.xpos[self.cbid].copy()
            if xy is not None:xyz[:2]=xy
            source='ground_truth_control_baseline'
        # Local pinch Z is distal, local Y is the opposing-finger axis.
        # The open distal pad edge extends ~4.5 mm past pinch. Placing pinch
        # 3 mm above the cube centre leaves ~26.5 mm of vertical overlap,
        # with more clearance from the spring links during closure.
        rz=Rotation.from_euler('z',yaw).as_matrix()
        rot=rz@np.diag([1.,-1.,-1.])
        grasp_z=float(xyz[2]+.003)
        carry_offset_z=float(self.initial_qpos[self.cube_qposadr+2]-grasp_z)
        positions=[('CLEAR_HOME',[-.13,.40,.60]),('HOVER_CUBE',[xyz[0],xyz[1],.56]),('PREGRASP',[xyz[0],xyz[1],grasp_z+.10]),('GRASP',[xyz[0],xyz[1],grasp_z]),('LIFT',[xyz[0],xyz[1],.56]),('HOVER_TRAY',[.50,.18,.56]),('PLACE',[.50,.18,.44]),('RETREAT',[.50,.18,.56])]
        plan=[];q0=self.home.copy()
        for i,(name,p) in enumerate(positions):
            q,err=self.solve(p,rot,q0,multistart=True)
            ok,check=self.check_path(q0,q,allow_cube=name in ('GRASP','LIFT','HOVER_TRAY','PLACE'),carry_offset_z=carry_offset_z if name in ('LIFT','HOVER_TRAY','PLACE') else None)
            if not ok:raise MotionFailure(f'Offline path rejected {name}: {check}')
            plan.append({'name':name,'q':q.tolist(),'tcp_position':p,'ik':err,'collision_check':check})
            q0=q
        return {'source':source,'object_position':xyz.tolist(),'object_yaw_rad':yaw,'planning_cube_qpos':self.initial_qpos[self.cube_qposadr:self.cube_qposadr+7].tolist(),'pinch_rotation':rot.tolist(),'waypoints':plan}

    def finger_contacts(self):
        sides={'left':0.,'right':0.};normals={}
        for i,c in enumerate(self.data.contact):
            g1,g2=int(c.geom1),int(c.geom2)
            if not self.cgids.intersection((g1,g2)):continue
            pad=g2 if g1 in self.cgids else g1
            if pad not in self.pad_sides:continue
            f=np.zeros(6);mujoco.mj_contactForce(self.model,self.data,i,f)
            side=self.pad_sides[pad];sides[side]+=max(0.,float(f[0]))
            n=np.array(c.frame[:3]);n=n if g1 in self.cgids else -n
            normals[side]=normals.get(side,np.zeros(3))+max(0.,float(f[0]))*n
        unit={side:n/np.linalg.norm(n) for side,n in normals.items() if np.linalg.norm(n)>1e-10}
        opposition=float(np.dot(unit['left'],unit['right'])) if len(unit)==2 else None
        return sides,opposition

    def execute(self,plan,frame_callback=None,realtime=False):
        dt=float(self.model.opt.timestep)
        self.data.ctrl[self.gid]=0.
        self.start_cube=self.data.xpos[self.cbid].copy()
        transport=False
        def tick(stage,target,allow_cube=False):
            nonlocal transport
            started=time.monotonic()
            self.data.ctrl[self.aids]=target
            mujoco.mj_step(self.model,self.data)
            self.sim_tick+=1
            observed=self.collision_contacts(self.data,allow_cube=allow_cube,penetration=0.)
            self.max_robot_penetration=max([self.max_robot_penetration]+[c['penetration_m'] for c in observed])
            bad=[c for c in observed if c['penetration_m']>.0005]
            if bad:raise MotionFailure(f'Unexpected physical contact {stage}: {bad}')
            for c in self.data.contact:
                if not self.cgids.intersection((int(c.geom1),int(c.geom2))):continue
                other=int(c.geom2) if int(c.geom1) in self.cgids else int(c.geom1)
                if self.model.geom(other).name in ('worktable','tray_bottom'):
                    self.max_cube_support_penetration=max(self.max_cube_support_penetration,float(-c.dist))
            if not np.isfinite(self.data.qpos).all():raise MotionFailure('Nonfinite simulation state')
            err=float(np.max(np.abs(self.data.qpos[self.qids]-target)))
            self.max_tracking_error=max(self.max_tracking_error,err)
            if err>.30:raise MotionFailure(f'Joint tracking error {err:.3f} rad at {stage}')
            if transport:self.min_transport_height=min(self.min_transport_height,float(self.data.xpos[self.cbid,2]))
            if transport:
                force,opposition=self.finger_contacts()
                self.holding_steps+=1
                self.minimum_holding_normal_force=min(self.minimum_holding_normal_force,*force.values())
                if opposition is not None:self.maximum_holding_normal_dot=max(self.maximum_holding_normal_dot,opposition)
                loaded=min(force.values())>.1 and opposition is not None and opposition<-.8
                self.loaded_bilateral_steps+=int(loaded)
                if not loaded:raise MotionFailure(f'Lost bilateral loaded contact at {stage}: {force}, normal dot {opposition}')
                if stage.startswith('HOVER_TRAY'):
                    self.min_transfer_height=min(self.min_transfer_height,float(self.data.xpos[self.cbid,2]))
                    if self.data.xpos[self.cbid,2]<.50:raise MotionFailure('Cube lost transport clearance')
            if self.sim_tick%10==0:
                force,opposition=self.finger_contacts()
                self.samples.append({'time_s':float(self.data.time),'stage':stage,'cube_position_m':self.data.xpos[self.cbid].tolist(),'left_normal_force_n':force['left'],'right_normal_force_n':force['right'],'normal_dot':opposition,'joint_error_rad':err,
                                     'tcp_position_m': self.data.site_xpos[self.sid].tolist(),
                                     'joint_position_rad': self.data.qpos[self.qids].tolist()})
            if frame_callback and self.sim_tick%10==0:frame_callback(self.model,self.data,stage)
            if realtime:time.sleep(max(0,dt-(time.monotonic()-started)))
        def hold(name,seconds,allow_cube=False):
            q=self.data.ctrl[self.aids].copy()
            for _ in range(round(seconds/dt)):tick(name,q,allow_cube)
        hold('SETTLE_HOME',.75)
        for wp in plan['waypoints']:
            name=wp['name'];q1=np.array(wp['q']);q0=self.data.ctrl[self.aids].copy()
            path = np.asarray(wp.get('path_q', [q0, q1]), dtype=float)
            if len(path) < 2 or not np.allclose(path[-1], q1):
                raise MotionFailure(f'Invalid checked joint path for {name}')
            if 'path_q' in wp and not np.allclose(path[0], q0, atol=.001):
                raise MotionFailure(f'Checked path for {name} does not start at the previous command')
            segments = len(path) - 1
            duration = max(1.5, float(np.max(np.abs(np.diff(path, axis=0)))) * segments / .35)
            if name in ('GRASP','PLACE'):duration=max(duration,2.0)
            steps = max(1, round(duration / dt))
            for step in range(steps + 1):
                u = step / steps if 'path_q' in wp else min(1., step * dt / duration)
                progress = (10*u**3 - 15*u**4 + 6*u**5) * segments
                index = min(int(progress), segments - 1)
                q = path[index] + (progress - index) * (path[index + 1] - path[index])
                tick(name,q,allow_cube=name in ('GRASP','LIFT','HOVER_TRAY','PLACE'))
            hold(name+'_SETTLE',.5,allow_cube=name in ('GRASP','LIFT','HOVER_TRAY','PLACE'))
            tcp_error=float(np.linalg.norm(self.data.site_xpos[self.sid]-np.array(wp['tcp_position'])))
            metric={'stage':name,'time_s':float(self.data.time),'tcp_error_m':tcp_error,'cube_position_m':self.data.xpos[self.cbid].tolist()}
            if tcp_error>.025:raise MotionFailure(f'TCP failed to settle at {name}: {tcp_error:.4f}m')
            if name=='GRASP':
                self.data.ctrl[self.gid]=255
                hold('CLOSE_GRIPPER',1.5,allow_cube=True)
                force,opp=self.finger_contacts()
                metric.update(normal_forces_n=force,opposing_normals_dot=opp)
                if min(force.values())<.1 or opp is None or opp>-.8:raise MotionFailure(f'No opposing loaded two-finger contact: {metric}')
                transport=True
            if name=='LIFT':
                height=float(self.data.xpos[self.cbid,2]-self.start_cube[2]);metric['lift_height_m']=height
                if height<.12:raise MotionFailure(f'Cube did not lift: {height}')
            if name=='PLACE':
                transport=False
                self.data.ctrl[self.gid]=0
                hold('RELEASE',1.2,allow_cube=True)
            self.stage_metrics.append(metric)
            print(json.dumps(metric),flush=True)
        hold('FINAL_SETTLE',2.)
        return self.evaluate_placement(plan)

    def evaluate_placement(self, plan):
        """Default tray placement acceptance; stacking supplies its own support graph."""
        p=self.data.xpos[self.cbid].copy()
        cube_jid=self.target_joint
        dq=int(self.model.jnt_dofadr[cube_jid]);speed=float(np.linalg.norm(self.data.qvel[dq:dq+3]));omega=float(np.linalg.norm(self.data.qvel[dq+3:dq+6]))
        corners = self.target_vertices
        if corners is None:
            corners=np.array([[x,y,z] for x in (-.025,.025) for y in (-.025,.025) for z in (-.025,.025)])
        corners=corners@self.data.xmat[self.cbid].reshape(3,3).T+p
        left = self.model.geom('tray_wall_left').id
        right = self.model.geom('tray_wall_right').id
        front = self.model.geom('tray_wall_front').id
        back = self.model.geom('tray_wall_back').id
        xmin = self.data.geom_xpos[left, 0] + self.model.geom_size[left, 0]
        xmax = self.data.geom_xpos[right, 0] - self.model.geom_size[right, 0]
        ymin = self.data.geom_xpos[front, 1] + self.model.geom_size[front, 1]
        ymax = self.data.geom_xpos[back, 1] - self.model.geom_size[back, 1]
        inside = bool(np.all((corners[:, 0] > xmin) & (corners[:, 0] < xmax)) and
                      np.all((corners[:, 1] > ymin) & (corners[:, 1] < ymax)))
        tray_bottom=self.model.geom('tray_bottom').id
        support_force=0.
        for i,contact in enumerate(self.data.contact):
            pair={int(contact.geom1),int(contact.geom2)}
            if tray_bottom in pair and self.cgids.intersection(pair):
                contact_force=np.zeros(6)
                mujoco.mj_contactForce(self.model,self.data,i,contact_force)
                support_force+=max(0.,float(contact_force[0]))
        supported=bool(.410<p[2]<.43 and support_force>.1)
        if self.target_vertices is not None:
            tray_floor = self.data.geom_xpos[tray_bottom, 2] + self.model.geom_size[tray_bottom, 2]
            supported = bool(abs(corners[:, 2].min() - tray_floor) < .004 and support_force > .1)
        force,_=self.finger_contacts()
        result={'success':bool(inside and supported and speed<.005 and omega<.05 and max(force.values())<.05),'control_source':plan['source'],'final_cube_position_m':p.tolist(),'final_linear_speed_m_s':speed,'final_angular_speed_rad_s':omega,'all_cube_corners_inside_tray':inside,'supported_at_tray_bottom':supported,'final_finger_normal_forces_n':force,'max_joint_tracking_error_rad':self.max_tracking_error,'max_unexpected_robot_penetration_m':self.max_robot_penetration,'robot_penetration_abort_tolerance_m':.0005,'max_cube_support_contact_penetration_m':self.max_cube_support_penetration,'min_lift_and_transport_cube_z_m':self.min_transport_height,'min_transfer_cube_z_m':self.min_transfer_height,'min_holding_finger_normal_force_n':self.minimum_holding_normal_force,'max_holding_opposing_normals_dot':self.maximum_holding_normal_dot,'bilateral_loaded_contact_fraction':self.loaded_bilateral_steps/max(1,self.holding_steps),'holding_physics_steps':self.holding_steps,'stages':self.stage_metrics,'simulation_time_s':float(self.data.time)}
        result['tray_bottom_normal_force_n']=support_force
        if self.target_vertices is not None:
            result['all_target_vertices_inside_tray'] = result.pop('all_cube_corners_inside_tray')
        if not result['success']:raise MotionFailure(f'Placement acceptance failed: {result}')
        return result
