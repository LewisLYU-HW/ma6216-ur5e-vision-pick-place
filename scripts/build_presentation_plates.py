"""Create annotated image plates from unchanged archived simulation frames."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
F=ROOT/'docs/presentation/frames'
OUT=ROOT/'docs/presentation/plates'
BLUE='#146B8C'; INK='#172E43'; AMBER='#E5A43B'

def main(qa):
    sys.path.insert(0,str(qa))
    from audit_panel_alignment import require_matplotlib_panel_alignment
    OUT.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'],'font.size':14,'pdf.fonttype':42,'svg.fonttype':'none','savefig.dpi':300})
    records={}
    def fr(key):return F/(key+'.jpg')
    def panel(path,title,caption,crop=None,roi=None):
        return dict(path=path,title=title,caption=caption,crop=crop,roi=roi)
    # Rectangular crops are shared within each temporal comparison.
    specs={
      'overview':[
        panel(fr('initial_overview'),'Initial workcell','t = 0.00 s | object pickup stations'),
        panel(fr('final_overview'),'Released final state','t = 195.00 s | four acceptance checks passed')],
      'calibration':[
        panel(ROOT/'docs/results/wrist-calibration-v1/examples/intrinsic_train.jpg','Checkerboard observations','Image-based corner detection',(120,70,1160,850)),
        panel(ROOT/'docs/results/wrist-calibration-v1/examples/hand_eye_validation.jpg','Held-out hand–eye view','PnP + robot FK; frozen validation chain',(120,70,1160,850))],
      'localization':[
        panel(ROOT/f'docs/results/workshop-localization-v1/examples/nominal__{n}__sample__500.jpg',title,'Nominal scene | seed 500',{'hammer':(570,440,820,690),'screwdriver':(360,440,610,690),'rack_frame':(480,390,730,640),'spanner':(530,390,780,640)}[n])
        for n,title in [('hammer','Hammer'),('screwdriver','Screwdriver'),('rack_frame','Rack frame'),('spanner','Spanner')]],
      'hammer':[
        panel(fr('hammer_lift_overview'),'Lift and transport','t = 13.60 s',(190,100,800,560)),
        panel(fr('hammer_released_overview'),'Released tray placement','t = 25.00 s',(190,100,800,560))],
      'insertion':[
        panel(fr(k),t,c,(200,100,800,620)) for k,t,c in [
        ('driver_orient_wrist','Reorientation','t = 50.00 s'),('driver_insert_wrist','Guarded insertion','t = 60.00 s'),('driver_done_wrist','Released placement','t = 70.00 s')]],
      'rack':[
        panel(fr('rack_lift_overview'),'Independent frame pickup','t = 91.00 s',(100,0,850,642)),
        panel(fr('rack_insert_wrist'),'Frame–base seating','t = 112.00 s',(100,0,850,642)),
        panel(fr('rack_done_overview'),'Released fixture','t = 134.40 s',(100,0,850,642))],
      'regrasp':[
        panel(fr(k),t,c,(180,0,820,600)) for k,t,c in [
        ('regrasp_place_wrist','Supported placement','t = 147.00 s'),('regrasp_clear_wrist','Complete finger clearance','t = 150.40 s'),('regrasp_lift_wrist','New grasp after observation','t = 158.20 s')]],
      'hanging':[
        panel(fr(k),t,c,(260,0,730,560), (120,30,230,200)) for k,t,c in [
        ('hang_align_wrist','Precontact alignment','t = 171.00 s'),('hang_thread_wrist','Hole-over-pin threading','t = 179.00 s'),('final_wrist','Released hanging state','t = 195.00 s')]],
      'paired':[
        panel(fr('open_failure_wrist'),'Open loop: guard stop','Seed 400 | t = 57.96 s',(180,90,820,620)),
        panel(fr('driver_done_wrist'),'Iterative: released driver','Seed 400 | t = 70.00 s',(180,90,820,620))],
      'failure':[
        panel(fr('staged_failure_wrist'),'Staged feedback','Seed 401 | contact guard at gripper closure',(120,0,850,620)),
        panel(fr('iter_failure_wrist'),'Iterative feedback','Seed 401 | same early failure stage',(120,0,850,620))],
      'correction':[
        panel(fr('pulse_before'),'Before corrective action','Visual angular residual: 1.60°',(260,0,730,560)),
        panel(fr('pulse_after'),'After correction and reobservation','Visual angular residual: 0.74°',(260,0,730,560))],
      'background':[
        panel(ROOT/'docs/results/workshop-localization-v1/background_mismatch_diagnostic/target_absent__rack_frame__failure__500.jpg','Target-absent scene','Separate background-mismatch diagnosis',(200,100,1100,850),(425,420,90,75)),
        panel(ROOT/'docs/results/workshop-localization-v1/background_mismatch_diagnostic/target_absent__rack_frame__failure__500.jpg','Magnified false-positive region','Red pixels: predicted foreground without target',(580,470,760,620))],
    }
    for name,ps in specs.items():
        n=len(ps); rows=1; cols=n
        height=4.4 if n==4 else (4.7 if n==2 else 4.6)
        fig,axes=plt.subplots(rows,cols,figsize=(12,height),squeeze=False)
        fig.subplots_adjust(left=.035,right=.985,bottom=.14,top=.88,wspace=.10,hspace=.45)
        records[name]=[]
        for i,(ax,p) in enumerate(zip(axes.flat,ps)):
            raw=Image.open(p['path']); im=raw.crop(p['crop']) if p['crop'] else raw
            # Keep the image aspect ratio and choose a common viewport through uniform padding.
            # Equal axes are enforced; no object geometry is stretched.
            ax.imshow(im,aspect='equal');ax.set_axis_off()
            # Explicit shared box ratio avoids geometry drift when source crops differ.
            target_ratio=1.0 if n==4 else (1.35 if n==2 else 0.95)
            w,h=im.size; target_w=max(w,h*target_ratio);target_h=target_w/target_ratio
            ax.set_xlim(-(target_w-w)/2,w+(target_w-w)/2);ax.set_ylim(h+(target_h-h)/2,-(target_h-h)/2)
            ax.text(0,1.08,chr(97+i),transform=ax.transAxes,fontweight='bold',fontsize=16,color=INK,va='bottom')
            ax.text(.09,1.08,p['title'],transform=ax.transAxes,fontsize=13.5,color=INK,va='bottom')
            ax.text(.5,-.075,p['caption'],transform=ax.transAxes,ha='center',va='top',fontsize=12,color='#4A5965')
            if p['roi']:
                x,y,rw,rh=p['roi'];ax.add_patch(Rectangle((x,y),rw,rh,fill=False,edgecolor=AMBER,lw=1.7))
            records[name].append({'source':str(p['path'].relative_to(ROOT)),'source_sha256':hashlib.sha256(p['path'].read_bytes()).hexdigest(),'crop_xyxy':p['crop'],'annotation_roi_xywh_in_crop':p['roi'],'panel':chr(97+i),'title':p['title'],'caption':p['caption'],'contrast_or_color_change':False})
        fig.canvas.draw()
        require_matplotlib_panel_alignment(fig,json_out=OUT/f'{name}.alignment.json',tolerance_pt=1.5,gutter_tolerance_pt=1.5,strict=True)
        fig.savefig(OUT/f'{name}.png',dpi=300)
        fig.savefig(OUT/f'{name}.pdf')
        fig.savefig(OUT/f'{name}.svg')
        plt.close(fig)
    (OUT/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
    print('Exported',len(specs),'image plates')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--qa-tools',type=Path,required=True);main(p.parse_args().qa_tools)
