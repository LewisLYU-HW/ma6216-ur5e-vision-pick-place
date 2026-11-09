"""Same-observation visual processing evidence, plus separate prior reconstruction and later outcome."""
import json,hashlib,sys
from pathlib import Path
import numpy as np,trimesh
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
ROOT=Path(__file__).resolve().parents[1];O=ROOT/'docs/presentation/plates';S=ROOT/'docs/presentation/pipeline_source'
sys.path.insert(0,str(Path.home()/'.codex/skills/nature-figure/scripts'))
from audit_panel_alignment import require_matplotlib_panel_alignment
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'],'font.size':12,'pdf.fonttype':42,'svg.fonttype':'none'})
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
capture=json.loads((S/'capture.json').read_text());result=json.loads((S/'pose_result.json').read_text());rgb=np.array(Image.open(S/'rgb.png'));mask=np.array(Image.open(S/'mask.png'))>0;depth=np.load(S/'depth.npy');K=np.array(capture['K']);pose=np.array(result['camera_T_object']);crop=[360,0,920,760]
manifest=json.loads((O/'manifest.json').read_text())
def setup(name,titles):
 fig,axes=plt.subplots(1,3,figsize=(12,5.0));fig.subplots_adjust(left=.025,right=.985,top=.88,bottom=.18,wspace=.08)
 for i,(ax,title) in enumerate(zip(axes,titles)):
  ax.set_axis_off();ax.text(0,1.055,chr(97+i)+'  '+title,transform=ax.transAxes,fontsize=14,weight='bold',color='#243746')
 return fig,axes
fig,axes=setup('observation',['Calibrated RGB','Metric depth','Predicted foreground'])
for ax in axes:ax.set_xlim(crop[0],crop[2]);ax.set_ylim(crop[3],crop[1])
axes[0].imshow(rgb);axes[1].imshow(np.ma.masked_where(depth<=0,depth),cmap='viridis',vmin=.05,vmax=.30);axes[2].imshow(rgb);overlay=np.zeros((*mask.shape,4));overlay[mask]=[.05,.8,.6,.65];axes[2].imshow(overlay)
for ax,t in zip(axes,['Wrist RGB | t = 160.340 s','Metric depth (display range clipped)','Predicted foreground mask']):ax.text(.5,-.065,t,transform=ax.transAxes,ha='center',fontsize=11.5,color='#52616B')
bar=fig.add_axes([.425,.065,.15,.02]);bar.imshow(np.linspace(.05,.30,256)[None,:],cmap='viridis',aspect='auto',extent=[.05,.30,0,1],vmin=.05,vmax=.30);bar.set_yticks([]);bar.set_xticks([.05,.30]);bar.set_xticklabels(['0.05 m','0.30 m'],fontsize=11);bar.tick_params(length=0);bar.spines[:].set_visible(False)
fig.canvas.draw();require_matplotlib_panel_alignment(fig,json_out=O/'processing_observation.alignment.json',strict=True,tolerance_pt=1.5,axes=list(axes))
fig.savefig(O/'processing_observation.png',dpi=300);fig.savefig(O/'processing_observation.pdf');fig.savefig(O/'processing_observation.svg');plt.close(fig)
# Render the actual reconstructed surface into a square image. Geometry is not synthesized.
meshpath=ROOT/'assets/reconstructed/workshop/spanner/model.obj';mesh=trimesh.load(meshpath,force='mesh',process=False);assert sha(meshpath)==result['model_sha256']
fig=plt.figure(figsize=(5,5));ax=fig.add_axes([0,0,1,1],projection='3d');tri=mesh.vertices[mesh.faces];normals=mesh.face_normals;light=np.array([.3,-.5,.8]);shade=.45+.55*np.abs(normals@light/np.linalg.norm(light));colors=np.c_[.22*shade,.65*shade,.78*shade,np.ones(len(shade))];ax.add_collection3d(Poly3DCollection(tri,facecolors=colors,edgecolors='none',rasterized=True));centre=mesh.bounds.mean(axis=0);extent=np.ptp(mesh.bounds,axis=0);ax.set_xlim(centre[0]-.095,centre[0]+.095);ax.set_ylim(centre[1]-.05,centre[1]+.05);ax.set_zlim(centre[2]-.025,centre[2]+.025);ax.set_box_aspect((.19,.10,.05));ax.view_init(elev=67,azim=-90);ax.set_axis_off();fig.savefig(S/'reference_surface.png',dpi=300);plt.close(fig)
fig,axes=setup('pose',['Reference mesh','Estimated pose','Released hanging'])
axes[0].imshow(Image.open(S/'reference_surface.png'));axes[1].imshow(rgb);axes[1].set_xlim(crop[0],crop[2]);axes[1].set_ylim(crop[3],crop[1]);axes[2].imshow(Image.open(ROOT/'docs/presentation/frames/final_wrist.jpg'));axes[2].set_xlim(210,770);axes[2].set_ylim(560,0)
points=np.vstack([np.zeros(3),np.eye(3)*.05]);cp=points@pose[:3,:3].T+pose[:3,3];uv=cp@K.T;uv=uv[:,:2]/uv[:,2,None]
for pt,c,t in zip(uv[1:],['#FF5555','#52ED70','#4CA5FF'],'XYZ'):
 a=axes[1].annotate('',xy=pt,xytext=uv[0],arrowprops=dict(arrowstyle='->',color=c,lw=2.5));a.arrow_patch.set_path_effects([pe.Stroke(linewidth=4,foreground='#243746'),pe.Normal()]);axes[1].text(*(pt+[12,0]),t,fontsize=14,weight='bold',color=c,path_effects=[pe.withStroke(linewidth=2,foreground='#243746')],clip_on=True)
for ax,t in zip(axes,['Prior reconstruction | 24 views','Same capture | estimated XYZ axes','Later replay frame | t = 195.00 s']):ax.text(.5,-.065,t,transform=ax.transAxes,ha='center',fontsize=11.5,color='#52616B')
# Shared square viewports make the evidence rectangles equal without stretching images.
for ax in axes:
 x0,x1=ax.get_xlim();y1,y0=ax.get_ylim();side=max(abs(x1-x0),abs(y1-y0));cx=(x0+x1)/2;cy=(y0+y1)/2;ax.set_xlim(cx-side/2,cx+side/2);ax.set_ylim(cy+side/2,cy-side/2)
fig.canvas.draw();require_matplotlib_panel_alignment(fig,json_out=O/'processing_pose.alignment.json',strict=True,tolerance_pt=1.5)
fig.savefig(O/'processing_pose.png',dpi=300);fig.savefig(O/'processing_pose.pdf');fig.savefig(O/'processing_pose.svg');plt.close(fig)
provenance={'trial':'complete__iterative__none__400','archive':'artifacts/visual_feedback_calibrated_48/trials/complete__iterative__none__400/observations.tar.gz','archive_member_prefix':'observations/00029_wrist_camera_spanner/','capture_time_s':capture['capture_time_s'],'camera':capture['camera'],'crop_xyxy':crop,'pose_source':'docs/results/visual-feedback-calibrated-v1/trials/complete__iterative__none__400.json / perception matching capture_time_s','reference_mesh':str(meshpath.relative_to(ROOT)),'reference_mesh_sha256':sha(meshpath),'reference_note':'Prior reconstruction from 24 views; not reconstructed from the runtime image','later_outcome_note':'Same trial, later time; not simultaneous with the input observation','files_sha256':{p.name:sha(p) for p in S.iterdir() if p.is_file() and p.name!='manifest.json'}}
(S/'manifest.json').write_text(json.dumps(provenance,indent=2)+'\n')
for name,files in [('processing_observation',['rgb.png','depth.npy','mask.png']),('processing_pose',['reference_surface.png','pose_result.json'])]:
 manifest[name]=[{'source':str((S/f).relative_to(ROOT)),'source_sha256':sha(S/f),'caption':'See pipeline_source/manifest.json for capture and transformation provenance'} for f in files]
manifest['processing_pose'].append({'source':'docs/presentation/frames/final_wrist.jpg','source_sha256':sha(ROOT/'docs/presentation/frames/final_wrist.jpg'),'caption':'Later outcome, same trial'})
(O/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Built two grounded processing-chain figures.')
