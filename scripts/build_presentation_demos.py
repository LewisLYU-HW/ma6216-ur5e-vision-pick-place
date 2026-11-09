"""Traceable edited task reel and log-synchronized feedback video; no new trials."""
import json,hashlib,subprocess,sys
from pathlib import Path
import numpy as np,cv2
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from ma6216.workshop_scene import build_workshop_scene
from ma6216.scene import mujoco
OUT=ROOT/'docs/presentation/media';OUT.mkdir(exist_ok=True)
W,H,FPS=1600,900,25
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
NAVY='#243746';BLUE='#146B8C';GREY='#52616B'
def txt(draw,xy,value,size=24,color=NAVY,bold=False):draw.text(xy,value,font=ImageFont.truetype(BOLD if bold else FONT,size),fill=color)
def writer(name):return subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/name)],stdin=subprocess.PIPE)
FRAME_CACHE={}
def readframe(cap,t):
 target=round(t*25);previous,frame=FRAME_CACHE.get(id(cap),(-100000,None))
 if target==previous:return frame
 if previous < target < previous+200:
  for _ in range(target-previous):assert cap.grab(),t
  ok,fr=cap.retrieve()
 else:
  cap.set(cv2.CAP_PROP_POS_FRAMES,target);ok,fr=cap.read()
 assert ok,t
 frame=cv2.cvtColor(fr,cv2.COLOR_BGR2RGB);FRAME_CACHE[id(cap)]=(target,frame);return frame
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def base(title,subtitle):
 im=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(im);d.rectangle((0,0,W,6),fill=BLUE);txt(d,(40,25),title,32,bold=True);txt(d,(40,75),subtitle,20,GREY);return im,d
hero=ROOT/'docs/videos/visual-feedback-calibrated-v1/complete__iterative__none__400.mp4'
# Chronological excerpts, explicit cuts and per-segment playback speed.
segments=[(0,2,1,0,'Initial calibrated workcell'),(10,15,2,0,'Physical hammer pickup'),(21,26,2,0,'Released hammer return'),(28,32,2,1,'Moving feed acquisition'),(39,44,1,1,'Moving screwdriver pickup'),(49,55,2,1,'Reorientation to the tilted socket'),(59,63,1,1,'Guarded insertion'),(67,70,1.5,1,'Released screwdriver placement'),(88,94,3,2,'Independent rack pickup'),(104,113,3,2,'Frame-to-base seating'),(117,120,1,2,'Rack release'),(146,152,1,3,'Supported placement and finger clearance'),(154,159,1,3,'New grasp after reobservation'),(171,177,3,3,'Hole-to-pin approach'),(177,184,1,3,'Threading and physical release'),(193,195.8,1,3,'Final accepted state')]
if '--feedback-only' not in sys.argv:
 cap=cv2.VideoCapture(str(hero));p=writer('complete_task_highlights.mp4');record=[];frame_count=0
 labels=['01 HAMMER RETURN','02 MOVING DRIVER','03 RACK INSTALLATION','04 REGRASP + HANG']
 for start,end,speed,phase,desc in segments:
  count=round((end-start)/speed*FPS);record.append(dict(source_start_s=start,source_end_s=end,speed=speed,output_start_s=frame_count/FPS,output_frames=count,phase=phase,description=desc))
  for j in range(count):
   t=start+j/FPS*speed;fr=readframe(cap,t);im,d=base('Vision-guided tool-service sequence','EDITED HIGHLIGHTS  |  iterative feedback / no disturbance / seed 400')
   for k,name in enumerate(['WORKCELL VIEW','WRIST VIEW']):
    x=40+k*780;txt(d,(x,118),name,18,BLUE,True);panel=Image.fromarray(fr[56:698,k*960:(k+1)*960]).resize((740,495),Image.Resampling.LANCZOS);im.paste(panel,(x,151))
   txt(d,(40,675),desc,29,bold=True);txt(d,(40,724),f'Source playback {t:06.2f} s   |   {speed:g}x playback   |   Chronological excerpts with cuts',21,GREY)
   for k,label in enumerate(labels):
    x=40+k*390;d.rectangle((x,788,x+370,847),fill=BLUE if k==phase else '#EDF2F5');txt(d,(x+12,806),label,19,'white' if k==phase else GREY,True)
   txt(d,(40,868),'Selected successful run; quantitative results include all 48 attempted trials.',17,GREY)
   p.stdin.write(im.tobytes())
   if frame_count==0:im.save(OUT/'complete_task_poster.jpg',quality=94)
   frame_count+=1
 p.stdin.close();assert p.wait()==0;cap.release();print('Task reel:',frame_count/FPS,'s',flush=True)
else:
 previous=json.loads((OUT/'manifest.json').read_text())['task_reel'];record=previous['segments'];frame_count=round(previous['duration_s']*FPS)
# Separate integration run; display observed residuals only after decision availability.
trial=ROOT/'docs/results/calibrated-workshop-v1/trials/complete__iterative__alignment_impulse__400';summary=json.loads((trial/'summary.json').read_text());loop=next(x for x in summary['visual_servo'] if x['object_id']=='spanner');obs=loop['observations'];trace=np.load(trial/'motion/trajectory_evaluation_only.npz',allow_pickle=False);origin=float(trace['time'][0]);source=ROOT/'docs/videos/calibrated-workshop-v1/overview-wrist.mp4'
scene=build_workshop_scene(400,rack_assembly=True,complete_task=True);m,data=scene.model,scene.data;cid=m.camera('wrist_camera').id
start,end,speed=171.0,173.5,.125;cap=cv2.VideoCapture(str(source));p=writer('visual_feedback_synchronized.mp4');count=round((end-start)/speed*FPS)
for j in range(count):
 t=start+j/FPS*speed;simulation_time=origin+t;fr=readframe(cap,t);rgb=fr[56:698,960:1920].copy();ix=min(len(trace['time'])-1,max(0,int(np.searchsorted(trace['time'],simulation_time,side='right')-1)))
 for k in ['qpos','qvel','ctrl','mocap_pos','mocap_quat']:getattr(data,k)[:]=trace[k][ix]
 mujoco.mj_forward(m,data);pose=trace['estimated_pose'][ix];pts=np.vstack([np.zeros(3),np.eye(3)*.06]);world=pts@pose[:3,:3].T+pose[:3,3];cp=(world-data.cam_xpos[cid])@data.cam_xmat[cid].reshape(3,3);cp*=np.array([1,-1,-1]);focal=360/np.tan(np.deg2rad(m.cam_fovy[cid])/2);uv=np.rint(cp[:,:2]/cp[:,2,None]*focal+[479.5,303.5]).astype(int)
 for a,col,letter in zip(uv[1:],[(245,75,75),(70,230,100),(65,155,255)],'XYZ'):
  cv2.arrowedLine(rgb,tuple(uv[0]),tuple(a),(25,35,45),7,cv2.LINE_AA,tipLength=.12);cv2.arrowedLine(rgb,tuple(uv[0]),tuple(a),col,4,cv2.LINE_AA,tipLength=.12)
  shift={'X':(-23,12),'Y':(12,-8),'Z':(12,20)}[letter];at=tuple(a+shift);cv2.putText(rgb,letter,at,cv2.FONT_HERSHEY_SIMPLEX,.8,(25,35,45),5,cv2.LINE_AA);cv2.putText(rgb,letter,at,cv2.FONT_HERSHEY_SIMPLEX,.8,col,2,cv2.LINE_AA)
 im,d=base('Visual feedback: observe, correct, observe again','SEPARATE PERTURBED INTEGRATION RUN  |  0.125x playback (8x slower)  |  recorded estimated pose')
 im.paste(Image.fromarray(rgb).resize((1000,669),Image.Resampling.LANCZOS),(40,135));available=[o for o in obs if o['decision_time_s']<=simulation_time];current=available[-1] if available else None
 txt(d,(1090,141),'OBSERVATION LOG',23,BLUE,True)
 if current:
  k=current['iteration'];state=['CORRECTING','REOBSERVING','TOLERANCE CONFIRMED'][k];txt(d,(1090,194),state,23,bold=True)
  txt(d,(1090,247),f'Observation {k+1} / 3',24)
  txt(d,(1090,305),f"Position residual   {current['translation_error_mm']:.2f} mm",21)
  txt(d,(1090,347),f"Angular residual   {current['rotation_error_deg']:.2f}°",21)
  txt(d,(1090,402),f"Captured: {current['capture_time_s']:.3f} s",19,GREY)
  txt(d,(1090,434),f"Available: {current['decision_time_s']:.3f} s",19,GREY)
  if k==0:
   txt(d,(1090,503),'One corrective move commanded',20,BLUE,True);txt(d,(1090,540),f"{obs[0]['command_translation_mm']:.3f} mm / {obs[0]['command_rotation_deg']:.3f}°",23)
  else:txt(d,(1090,503),'Confirm with another observation' if k==1 else 'Two observations confirmed',20,BLUE,True)
 else:txt(d,(1090,205),'Waiting for visual observation',21)
 txt(d,(1090,619),'Convergence rule',21,BLUE,True);txt(d,(1090,660),'Two consecutive observations',19);txt(d,(1090,692),'within 1.5 mm and 1.5°',19)
 txt(d,(40,831),f'Source playback {t:.3f} s  |  Simulation time {simulation_time:.3f} s  |  Latest available measurement held between updates',19,GREY)
 txt(d,(40,868),'Residuals compare estimated pose with the desired pose; not ground-truth error. This run is not pooled into the 48 trials.',17,GREY)
 p.stdin.write(im.tobytes())
 if j==int(count*.45):im.save(OUT/'visual_feedback_poster.jpg',quality=94)
p.stdin.close();assert p.wait()==0;cap.release();print('Feedback video:',count/FPS,'s',flush=True)
manifest={'task_reel':{'source':str(hero.relative_to(ROOT)),'sha256':sha(hero),'segments':record,'duration_s':frame_count/FPS,'fps':FPS,'outcome':'Selected complete success; final 48-trial result unchanged'},'feedback':{'source':str(source.relative_to(ROOT)),'sha256':sha(source),'summary':str((trial/'summary.json').relative_to(ROOT)),'summary_sha256':sha(trial/'summary.json'),'trajectory_sha256':sha(trial/'motion/trajectory_evaluation_only.npz'),'playback_start_s':start,'playback_end_s':end,'speed':speed,'simulation_time_offset_s':origin,'observations':obs,'corrections':loop['corrections'],'metric_update_rule':'Update only at decision_time_s, hold until next available observation; no interpolation','axis_length_m':.06,'duration_s':count/FPS},'files_sha256':{p.name:sha(p) for p in OUT.glob('*.mp4')}}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
