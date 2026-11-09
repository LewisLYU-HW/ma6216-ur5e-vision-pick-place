"""Add traceable context/detail scientific composites to archived simulation evidence."""
import argparse,hashlib,json,sys,textwrap
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'docs/presentation/plates'; F=ROOT/'docs/presentation/frames'
parser=argparse.ArgumentParser();parser.add_argument('--qa-tools',type=Path,required=True)
sys.path.insert(0,str(parser.parse_args().qa_tools))
from audit_panel_alignment import require_matplotlib_panel_alignment
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'],'font.size':12,'pdf.fonttype':42,'svg.fonttype':'none'})
# Every ROI is a manually selected explanatory pixel region, not a detector output.
S={
'hanging':[
('hang_align_wrist','Align','171.00 s',(350,0,610,250),'Ring / pin interface','Precontact view; the hole and pin are visible.'),
('hang_thread_wrist','Thread','179.00 s',(350,0,610,250),'Pin inside ring','The enlarged view exposes the local relationship.'),
('final_wrist','Release','195.00 s',(350,0,610,250),'Released support','Gripper withdrawn; terminal checks pass in the log.')],
'regrasp':[
('regrasp_place_wrist','Place on support','147.00 s',(325,230,635,530),'Original grasp','Supported tool before opening the fingers.'),
('regrasp_clear_wrist','Clear fingers','150.40 s',(325,230,635,530),'Open clearance','Tool remains on support while the fingers withdraw.'),
('regrasp_lift_wrist','Acquire new grasp','158.20 s',(325,230,635,530),'New grasp region','Reobservation precedes the new grasp and lift.')],
'insertion':[
('driver_orient_wrist','Reorient','50.00 s',(320,170,640,490),'Tool / gripper','Wrist view during orientation change.'),
('driver_insert_wrist','Insert','60.00 s',(320,170,640,490),'Insertion region','Socket contact is partly occluded by the gripper.'),
('driver_done_wrist','Release','70.00 s',(320,170,640,490),'Placed tool','Released placement; acceptance is checked in the log.')],
'correction':[
('pulse_before','Before correction','171.64 s',(350,0,610,250),'Visual residual: 1.60°','Logged pose residual; separate perturbed integration run.'),
('pulse_after','After reobservation','172.76 s',(350,0,610,250),'Visual residual: 0.74°','One logged correction. Images alone do not measure angular error.')],
'paired':[
('open_failure_wrist','Open loop / seed 400','57.96 s',(310,170,650,510),'Insertion guard stop','Endpoint from the failure replay; cause identified from logs.'),
('driver_done_wrist','Iterative / seed 400','70.00 s',(310,170,650,510),'Released placement','Matched seed, no disturbance; different endpoint times.')],
'failure':[
('staged_failure_wrist','Staged / seed 401','40.24 s',(310,170,650,510),'Pickup guard stop','Gripper-closure failure before downstream insertion control.'),
('iter_failure_wrist','Iterative / seed 401','40.24 s',(310,170,650,510),'Same failure stage','Matched seed and stage; retained in whole-task statistics.')],
}
S['pose']=[
('driver_align_wrist','Screwdriver pose','54.40 s',(280,130,700,550),'Estimated object frame',''),
('regrasp_lift_wrist','Spanner pose after regrasp','158.20 s',(280,120,700,540),'Estimated object frame','')]
records=json.loads((OUT/'manifest.json').read_text())
poses=json.loads((ROOT/'docs/presentation/pose_axes.json').read_text())
for name,panels in S.items():
 n=len(panels);fig=plt.figure(figsize=(12,5.3)); records[name]=[]; axes=[]
 for i,(key,title,time,roi,label,explanation) in enumerate(panels):
  left=.025+i*.96/n; width=.90/n
  fig.text(left,.97,chr(97+i)+'  '+title,fontsize=14,weight='bold',color='#243746',va='top')
  fig.text(left,.905,'t = '+time+'  |  wrist RGB',fontsize=12,color='#52616B')
  # Large matched task-region crops replace duplicate context and small detail images.
  crop=[210,0,770,560] if name in ('hanging','correction') else [250,80,750,580]
  if name in ('paired','failure'):crop=[210,70,770,630]
  ax=fig.add_axes([left,.205,width,.66]);axes.append(ax)
  im=Image.open(F/(key+'.jpg'));ax.imshow(im);ax.set_xlim(crop[0],crop[2]);ax.set_ylim(crop[3],crop[1]);ax.set_axis_off()
  overlay=poses.get(key)
  if overlay:
   pts=np.array(overlay['pixels_origin_xyz'])
   assert np.all((pts[:,0]>=crop[0]) & (pts[:,0]<=crop[2]) & (pts[:,1]>=crop[1]) & (pts[:,1]<=crop[3])), (name,key,'axis outside crop')
   for j,(axis,color) in enumerate(zip('XYZ',['#FF5555','#52ED70','#4CA5FF']),1):
    origin,end=pts[0],pts[j]
    ann=ax.annotate('',xy=end,xytext=origin,arrowprops=dict(arrowstyle='->',color=color,lw=2.6,mutation_scale=13),annotation_clip=True)
    ann.arrow_patch.set_path_effects([pe.Stroke(linewidth=4.2,foreground='#17232B'),pe.Normal()])
    delta=end-origin;delta=delta/max(np.linalg.norm(delta),1)
    labelpoint=end+delta*12+np.array([(-18,0),(10,-10),(18,10)][j-1])
    labelpoint=np.clip(labelpoint,[crop[0]+25,crop[1]+25],[crop[2]-25,crop[3]-25])
    ax.text(*labelpoint,axis,fontsize=14,weight='bold',color=color,ha='center',va='center',path_effects=[pe.withStroke(linewidth=2.7,foreground='#17232B')],clip_on=True)
  fig.text(left+width/2,.13,label,fontsize=12,weight='bold',color='#146B8C',ha='center')
  records[name].append({'source':str((F/(key+'.jpg')).relative_to(ROOT)),'source_sha256':hashlib.sha256((F/(key+'.jpg')).read_bytes()).hexdigest(),'context_crop_xyxy':crop,'panel':chr(97+i),'title':title,'caption':explanation,'annotation':'Enlarged task-region crop; XYZ reprojected from archived estimated pose, 60 mm axes','contrast_or_color_change':False,'time':time,'detail_label':label,'pose_overlay':overlay})
 fig.text(.5,.035,'Estimated object frame: X (red), Y (green), Z (blue) | 60 mm display axes | camera perspective retained',ha='center',fontsize=11.5,color='#52616B')
 fig.canvas.draw()
 require_matplotlib_panel_alignment(fig,json_out=OUT/f'{name}.alignment.json',tolerance_pt=1.5,gutter_tolerance_pt=1.5,strict=True,axes=axes,panel_ids=[str(j) for j in range(n)],row_groups=[[str(j) for j in range(n)]])
 fig.savefig(OUT/f'{name}.png',dpi=300);fig.savefig(OUT/f'{name}.pdf');fig.savefig(OUT/f'{name}.svg');plt.close(fig)
(OUT/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
print('Exported seven enlarged evidence figures with measured-pose projections.')
