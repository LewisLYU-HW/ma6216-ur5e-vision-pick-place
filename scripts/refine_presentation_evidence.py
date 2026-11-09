"""Add traceable context/detail scientific composites to archived simulation evidence."""
import argparse,hashlib,json,sys,textwrap
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,ConnectionPatch
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
records=json.loads((OUT/'manifest.json').read_text())
for name,panels in S.items():
 n=len(panels);fig=plt.figure(figsize=(12,5.3)); records[name]=[]; contexts=[];details=[]
 for i,(key,title,time,roi,label,explanation) in enumerate(panels):
  left=.025+i*.96/n; width=.90/n
  fig.text(left,.96,chr(97+i)+'  '+title,fontsize=14,weight='bold',color='#243746',va='top')
  fig.text(left,.895,'t = '+time+'  |  wrist RGB',fontsize=12,color='#52616B')
  ax=fig.add_axes([left,.405,width,.45]);contexts.append(ax)
  im=Image.open(F/(key+'.jpg'));ax.imshow(im);ax.set_xlim(150,810);ax.set_ylim(600,0);ax.set_axis_off()
  x0,y0,x1,y1=roi;ax.add_patch(Rectangle((x0,y0),x1-x0,y1-y0,fill=False,edgecolor='#E5A43B',lw=1.5))
  z=fig.add_axes([left,.065,width*.48,.29]);details.append(z)
  z.imshow(im.crop(roi));z.set_xticks([]);z.set_yticks([])
  # Identical square display extent preserves geometry and common pixel scale.
  side=max(x1-x0,y1-y0);z.set_xlim(-(side-(x1-x0))/2,(x1-x0)+(side-(x1-x0))/2);z.set_ylim((y1-y0)+(side-(y1-y0))/2,-(side-(y1-y0))/2)
  for spine in z.spines.values():spine.set_edgecolor('#E5A43B');spine.set_linewidth(1.2)
  fig.add_artist(ConnectionPatch(xyA=(x0,y1),coordsA=ax.transData,xyB=(.5,1),coordsB=z.transAxes,color='#E5A43B',lw=.85))
  tx=left+width*.53
  fig.text(tx,.32,'\n'.join(textwrap.wrap(label,19 if n==3 else 28)),fontsize=12,weight='bold',color='#146B8C',va='top')
  fig.text(tx,.205,'\n'.join(textwrap.wrap(explanation,22 if n==3 else 32)),fontsize=11.5,color='#243746',va='top',linespacing=1.35)
  records[name].append({'source':str((F/(key+'.jpg')).relative_to(ROOT)),'source_sha256':hashlib.sha256((F/(key+'.jpg')).read_bytes()).hexdigest(),'context_crop_xyxy':[150,0,810,600],'detail_crop_xyxy':roi,'panel':chr(97+i),'title':title,'caption':explanation,'annotation':'Manual explanatory ROI with connected detail inset; not an estimated detection','contrast_or_color_change':False,'time':time,'detail_label':label})
 fig.canvas.draw()
 # Audit equal context rectangles separately from deliberately smaller detail insets.
 for a in details:a.set_in_layout(False)
 require_matplotlib_panel_alignment(fig,json_out=OUT/f'{name}.alignment.json',tolerance_pt=1.5,gutter_tolerance_pt=1.5,strict=True,axes=contexts+details,panel_ids=[f'context{j}' for j in range(n)]+[f'detail{j}' for j in range(n)],row_groups=[[f'context{j}' for j in range(n)],[f'detail{j}' for j in range(n)]])
 fig.savefig(OUT/f'{name}.png',dpi=300);fig.savefig(OUT/f'{name}.pdf');fig.savefig(OUT/f'{name}.svg');plt.close(fig)
(OUT/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
print('Refined six evidence figures with linked context/detail views.')
