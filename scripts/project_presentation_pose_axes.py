"""Project archived estimated poses into presentation frames; no inference or physics steps."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from ma6216.workshop_scene import build_workshop_scene
from ma6216.scene import mujoco
F=ROOT/'docs/presentation/frames';manifest=json.loads((F/'manifest.json').read_text());out={};cache={}
for key,item in manifest.items():
 source=Path(item['source']).stem
 if key.startswith('pulse_'):trial=ROOT/'docs/results/calibrated-workshop-v1/trials/complete__iterative__alignment_impulse__400'
 else:trial=ROOT/'docs/results/visual-feedback-calibrated-v1/replay_inputs'/source
 path=trial/'motion/trajectory_evaluation_only.npz'
 if not path.exists():continue
 if str(path) not in cache:
  t=np.load(path,allow_pickle=False);scene=build_workshop_scene(int(source.split('__')[-1]) if not key.startswith('pulse_') else 400,rack_assembly=True,complete_task=True);cache[str(path)]=(t,scene,hashlib.sha256(path.read_bytes()).hexdigest())
 t,scene,h=cache[str(path)];m,d=scene.model,scene.data
 timestamp=float(t['time'][0])+item['frame_index_zero_based']/25
 i=min(len(t['time'])-1,max(0,int(np.searchsorted(t['time'],timestamp,side='right')-1)))
 for k in ['qpos','qvel','ctrl','mocap_pos','mocap_quat']:getattr(d,k)[:]=t[k][i]
 d.time=timestamp;mujoco.mj_forward(m,d);pose=t['estimated_pose'][i]
 if not np.isfinite(pose).all():continue
 camera='wrist_camera' if item['view']=='wrist' or key.startswith('pulse_') else 'overview';cid=m.camera(camera).id
 points=np.vstack([np.zeros(3),np.eye(3)*.060]);world=points@pose[:3,:3].T+pose[:3,3]
 camera_points=(world-d.cam_xpos[cid])@d.cam_xmat[cid].reshape(3,3);camera_points*=np.array([1,-1,-1])
 if np.any(camera_points[:,2]<=.02):continue
 focal=360/np.tan(np.deg2rad(m.cam_fovy[cid])/2);pixels=camera_points[:,:2]/camera_points[:,2,None]*focal+[479.5,359.5];pixels[:,1]-=56
 out[key]={'pixels_origin_xyz':pixels.tolist(),'axis_length_m':.060,'estimated_pose':pose.tolist(),'object_id':str(t['object_id'][i]),'snapshot_index':i,'trajectory':str(path.relative_to(ROOT)),'trajectory_sha256':h,'projection':'Recorded estimated world pose; replay camera transform for visualization only; original crop y-offset 56 px','camera':camera}
(ROOT/'docs/presentation/pose_axes.json').write_text(json.dumps(out,indent=2)+'\n');print('Projected',len(out),'archived estimated poses.')
