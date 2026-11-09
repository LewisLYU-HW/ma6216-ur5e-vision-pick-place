"""Build compact academic slides from traceable archived content and image plates."""
import argparse,json,hashlib,os
from pathlib import Path
from PIL import Image
from pptx import Presentation
from pptx.util import Inches,Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.xmlchemy import OxmlElement
ROOT=Path(__file__).resolve().parents[1]
INK,BLUE,GREY='243746','146B8C','52616B'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def build(results,out):
    source=json.loads((ROOT/'docs/presentation/content.json').read_text());summary=json.loads((results/'summary.json').read_text());assert summary['complete'] and summary['n_trials']==48
    plates=ROOT/'docs/presentation/plates';frames=ROOT/'docs/presentation/frames';pm=json.loads((plates/'manifest.json').read_text())
    prs=Presentation();prs.slide_width=Inches(13.333);prs.slide_height=Inches(7.5);notes=[];assets={}
    def text(s,v,x,y,w,h,size=15,bold=False,color=INK):
        z=s.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h));tf=z.text_frame;tf.word_wrap=True
        tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
        for i,line in enumerate(v.split('\n')):
            p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=line;p.font.name='Aptos';p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=RGBColor.from_string(color);p.space_after=Pt(5)
        return z
    def rect(s,x,y,w,h,color):
        z=s.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h));z.fill.solid();z.fill.fore_color.rgb=RGBColor.from_string(color);z.line.fill.background();z._element.spPr.append(OxmlElement('a:effectLst'))
        for e in z._element.iter():
            if e.tag.endswith('}effectRef'):e.set('idx','0')
    def slide(title,ids,section):
        s=prs.slides.add_slide(prs.slide_layouts[6]);s.background.fill.solid();s.background.fill.fore_color.rgb=RGBColor(255,255,255)
        rect(s,.0,.0,13.333,.055,BLUE);text(s,title,.45,.28,11.9,.45,20,True);text(s,section,10.5,.85,2.3,.24,10,False,GREY)
        rect(s,.45,.81,12.4,.008,'DBE3E7');text(s,f'{len(prs.slides):02}',12.35,.32,.45,.25,11,False,GREY)
        note='\n\n'.join(source[i-1]['notes'] for i in ids);refs=' | '.join(dict.fromkeys(source[i-1]['source'] for i in ids))
        notes.append({'slide':len(prs.slides),'title':title,'notes':note,'source':refs,'images':[]});s.notes_slide.notes_text_frame.text=note+'\n\nEvidence: '+refs
        text(s,'MA6216 · Vision-guided robotic manipulation · simulation evidence',.45,7.13,11.8,.22,9,False,GREY)
        return s
    def image(s,p,x,y,w,h):
        p=Path(p);iw,ih=Image.open(p).size;k=min(w/iw,h/ih);dw,dh=iw*k,ih*k
        s.shapes.add_picture(str(p),Inches(x+(w-dw)/2),Inches(y+(h-dh)/2),width=Inches(dw),height=Inches(dh));rel=str(p.relative_to(ROOT));assets[rel]=sha(p);notes[-1]['images'].append(rel)
    def plate(s,n,x,y,w,h):image(s,plates/(n+'.png'),x,y,w,h)
    def movie(s,name,poster,full_task=False):
        video=out/'media'/name;still=out/'media'/poster
        x,y,w,h=(.45,1.03,12.4,12.4*860/1920) if full_task else (1.7065,1.03,9.92,5.58)
        s.shapes.add_movie(str(video),Inches(x),Inches(y),Inches(w),Inches(h),poster_frame_image=str(still),mime_type='video/mp4')
        for path in [video,still]:assets[str(path.relative_to(ROOT))]=sha(path)
        notes[-1]['images'].append(str(still.relative_to(ROOT)))
        notes[-1]['video']=str(video.relative_to(ROOT))
        notes[-1]['video_poster']=str(still.relative_to(ROOT))
        cue=('Play the full 195.88-second continuous original replay at normal speed. The timeline below identifies hammer return, moving screwdriver insertion, rack installation, spanner regrasp and hanging. The timeline is rendered into every video frame and automatically highlights the current task during playback, pause and seeking. Interactive chapter selection remains available in the offline player. This is a selected successful trajectory, not a success-rate estimate.' if full_task else 'Play the 20-second slowed feedback replay. Explain the three observations and single corrective move. Measurements update only at logged decision time. This separate integration diagnostic is not pooled into the final 48 attempts.')
        notes[-1]['notes']+='\n\nDemonstration cue: '+cue
        s.notes_slide.notes_text_frame.text=notes[-1]['notes']+'\n\nEvidence: '+notes[-1]['source']

        button=text(s,'Play standalone MP4 ↗',.55,6.76,3.3,.25,11,True,BLUE)
        button.text_frame.paragraphs[0].runs[0].hyperlink.address=os.path.relpath(video,out)

    def sequence(s,keys,labels,y):
        width=12.2/len(keys)
        for i,(key,label) in enumerate(zip(keys,labels)):
            x=.55+i*width
            image(s,frames/(key+'.jpg'),x,y+.30,width-.18,2.00)
            text(s,chr(97+i)+'  '+label,x+.12,y,width-.35,.25,12,False,INK)
    def heading(s,t,x,y,w=5.8):text(s,t,x,y,w,.3,14,True,BLUE)
    def table(s,headers,rows,x,y,w,h,size=14):
        tb=s.shapes.add_table(len(rows)+1,len(headers),Inches(x),Inches(y),Inches(w),Inches(h)).table
        for i,row in enumerate([headers,*rows]):
            for j,v in enumerate(row):
                c=tb.cell(i,j);c.text=str(v);c.margin_left=c.margin_right=Inches(.08);c.margin_top=c.margin_bottom=Inches(.06)
                c.fill.solid();c.fill.fore_color.rgb=RGBColor.from_string('EDF2F5' if i==0 else 'FFFFFF')
                for p in c.text_frame.paragraphs:p.font.name='Aptos';p.font.size=Pt(size);p.font.bold=i==0;p.font.color.rgb=RGBColor.from_string(INK)
    def caption(s,t,y=6.55):text(s,t,.55,y,12.2,.48,12,False,GREY)
    def equation(s,parts,x,y,w):
        z=text(s,'',x,y,w,.32,14);p=z.text_frame.paragraphs[0]
        for value,base in parts:
            r=p.add_run();r.text=value;r.font.name='Cambria Math';r.font.size=Pt(10 if base else 14);r.font.color.rgb=RGBColor.from_string(INK)
            if base:r._r.get_or_add_rPr().set('baseline',str(base))

    s=slide('Calibrated 6D vision for sequential tool manipulation',[1,2],'Task demonstration')
    movie(s,'complete_task_with_timeline.mp4','full_task_timeline_poster.jpg',full_task=True)
    text(s,'Active task highlighted automatically · continuous 1× replay',4.1,6.76,8.4,.25,11,False,GREY)

    s=slide('From visual observation to physical manipulation',[3,4],'Methods')
    steps=[('RGB-D','Estimated intrinsics'),('Localization','Depth foreground'),('6D pose','FoundationPose'),('Robot target','Calibrated chain'),('Execution','IK + control')]
    for i,(a,b) in enumerate(steps):
        x=.55+i*2.47;rect(s,x,1.22,2.2,.68,'F0F5F6');text(s,a,x+.1,1.3,2,.25,14,True);text(s,b,x+.1,1.64,2,.23,11,False,GREY)
        if i<4:text(s,'→',x+2.23,1.42,.25,.3,14)
    image(s,frames/'initial_overview.jpg',.55,2.18,6.05,4.05)
    image(s,frames/'regrasp_lift_wrist.jpg',6.8,2.18,6.0,4.05)
    text(s,'Workcell observation',.65,6.3,5.9,.28,12,True,BLUE)
    text(s,'Pose-guided grasp and reobservation',6.9,6.3,5.8,.28,12,True,BLUE)
    caption(s,'24 RGB-D reference views → reconstruction → registration / tracking. MegaPose and GraspNet were reviewed, not benchmarked.',6.72)

    s=slide('Runtime observation: RGB, metric depth and predicted foreground',[4,7],'Traceable processing chain')
    plate(s,'processing_observation',.4,1.08,12.4,5.35)
    caption(s,'One wrist capture after regrasp: simulation t = 160.340 s, seed 400. Same crop across RGB, depth and predicted mask; no simulator IDs.',6.65)

    s=slide('From reconstructed reference to estimated pose and execution',[4,6,14],'Traceable processing chain')
    plate(s,'processing_pose',.4,1.08,12.4,5.35)
    caption(s,'The reference is reconstructed beforehand from 24 views. Pose uses the preceding runtime observation; hanging is a later state of the same trial.',6.65)

    s=slide('Image-based calibration and held-out validation',[5],'Methods')
    plate(s,'calibration',.4,1.1,12.4,4.75)
    table(s,['Wrist intrinsics','Hand–eye transform','Frozen-chain reprojection'],[['24 / 8 train–validation views','24 / 10 train–validation views','K and transformations fixed'],['0.02177 px RMSE','0.852 mm / 0.0227°','0.05497 px']],.55,5.7,12.2,.91,12)
    caption(s,'Checkerboard detection + image PnP + robot FK. Simulator parameters are validation references; ideal pinhole images limit transfer.',6.72)

    s=slide('Localization: image masks, evaluation unit and assumptions',[7],'Methods & validation')
    plate(s,'localization',.45,1.12,12.4,3.55)
    table(s,['Detector','Independent evaluation','Boundary'],[['Depth foreground subtraction\nKnown pickup regions','50 scenes / 200 queries\n10 scenes per tool–condition cell','Matched empty backgrounds\nRestricted occlusion / noise'],['Predictions saved first','160/160 positive queries: IoU ≥ 0.5\n0/40 absent-target false positives','Wilson and scene-bootstrap intervals\nNot 200 robot executions']],.55,4.93,12.2,1.58,14)
    caption(s,'Nominal seed 500. Green: overlap; blue: missed visible target; red: extra foreground. Crops preserve original overlays.',6.72)

    s=slide('Estimated object frames guide task-specific targets',[6,4],'Methods')
    plate(s,'pose',.4,1.08,12.4,5.3)
    equation(s,[('T',0),('BO',-25000),(' = T',0),('BG',-25000),(' · T',0),('GC',-25000),(' · T',0),('CO',-25000)],.65,6.49,3.45)
    text(s,'FK × hand–eye calibration × visual object pose',4.15,6.49,4.9,.32,12,False,GREY)
    text(s,'Reobserve after regrasp.',9.43,6.49,3.2,.32,12,False,GREY)

    s=slide('Visual feedback modes and bounded correction',[8,15],'Methods')
    plate(s,'correction',.35,1.3,9.0,4.9)
    rect(s,9.5,1.3,.025,5.2,'D9E5EA')
    heading(s,'Observation schedule',9.72,1.42,3.0)
    text(s,'Open loop\nInitial acquisition only\n\nStaged\nTask-transition observations\n\nIterative\nRepeated precontact correction',9.72,1.88,3.0,2.65,13)
    heading(s,'Common control limits',9.72,4.88,3.0)
    text(s,'Step cap: 4 mm / 2°\nConverged: two observations\nwithin 1.5 mm / 1.5°',9.72,5.31,3.0,.94,12)
    caption(s,'Estimated pose residual → bounded correction → reobserve. Same calibration, estimator and guards; discrete precontact control.',6.69)

    s=slide('Logged visual feedback: one correction, three observations',[15],'Separate integration diagnosis')
    movie(s,'visual_feedback_synchronized.mp4','visual_feedback_poster.jpg')
    text(s,'8× slower playback · logged values held between available observations',4.1,6.76,8.4,.25,11,False,GREY)

    s=slide('Paired evaluation in the complete workcell',[9,18],'Evaluation protocol')
    image(s,frames/'initial_overview.jpg',.45,1.15,8.6,5.65)
    heading(s,'48 complete-task attempts',9.45,1.35,3.35)
    text(s,'3 feedback modes\n× 2 disturbance conditions\n× 8 paired seeds',9.45,1.83,3.35,1.12,14)
    heading(s,'Outcome and uncertainty',9.45,3.23,3.35)
    text(s,'All four physical checks must pass.\n\nWilson 95% intervals\nExact paired tests + Holm\nTrial-level continuous summaries',9.45,3.7,3.35,1.7,13)
    text(s,'Seeds 400–407 reused.\nPaired replication, not a new holdout.\nEarly failures remain included.',9.45,5.82,3.35,.9,11,False,GREY)

    s=slide('Physical return and independent rack installation',[10,12],'Representative successful run')
    image(s,frames/'hammer_released_overview.jpg',.45,1.42,6.1,4.8)
    image(s,frames/'rack_done_overview.jpg',6.78,1.42,6.1,4.8)
    text(s,'a  Released hammer placement · 25.00 s',.6,1.12,5.9,.3,13,True,BLUE)
    text(s,'b  Released rack fixture · 134.40 s',6.93,1.12,5.9,.3,13,True,BLUE)
    caption(s,'One continuous replay. The rack is installed as an independent object; released support and stability determine acceptance.',6.65)

    s=slide('Tilted insertion: orientation, contact and released placement',[11],'Representative successful run')
    plate(s,'insertion',.4,1.08,12.4,5.3)
    caption(s,'Enlarged panels use matched pixel windows. Contact is partly occluded; physical acceptance comes from the recorded checks.',6.65)

    s=slide('Physical regrasp: support, clearance and grasp reacquisition',[13],'Representative successful run')
    plate(s,'regrasp',.4,1.08,12.4,5.3)
    caption(s,'One continuous trajectory. Enlarged views expose the grasp interface; new pose observation precedes reacquisition.',6.65)

    s=slide('Hole-over-pin placement: local geometry and final support',[14],'Representative successful run')
    plate(s,'hanging',.4,1.08,12.4,5.3)
    caption(s,'Four terminal checks passed. Separate passive-stability audit: 30 s. Pose axes are visualization overlays, not measured contact forces.',6.65)

    s=slide('Matched-seed comparison: insertion stop versus released placement',[16],'Controlled examples')
    plate(s,'paired',.4,1.08,12.4,5.3)
    caption(s,'Seed 400, no disturbance; endpoint times differ. A selected paired example does not establish statistical superiority.',6.65)

    s=slide('Shared failure boundary: gripper closure before insertion',[17],'Controlled examples')
    plate(s,'failure',.4,1.08,12.4,5.3)
    caption(s,'Seed 401: both modes stop at gripper closure. Stage and guard attribution are from logs; all failed attempts remain in the analysis.',6.65)

    s=slide('Whole-sequence results and statistical uncertainty',[18],'Quantitative results')
    image(s,results/'figures/success_rates.png',.45,1.15,8.0,4.05)
    table(s,['Mode','None','Pulse'],[['Open loop','0/8','0/8'],['Staged','3/8','2/8'],['Iterative','3/8','3/8']],8.65,1.5,4.1,2.2,15)
    text(s,'11/48 complete successes.\nAll four adjusted paired p-values: 1.0.\nNo statistically established superiority\nor equivalence in this sample.',8.65,4.03,4.1,1.38,15)
    heading(s,'Interpretation',.65,5.6)
    text(s,'The selected successful trajectory demonstrates feasibility. Low complete-sequence reliability and wide intervals limit conclusions about feedback benefit. Early failures remain part of the system-level outcome.',.65,6.04,12.0,.78,15)

    s=slide('Pose accuracy and the physical failure boundary',[19],'Error decomposition')
    for i,(key,label) in enumerate([('driver_align_wrist','Visual pose / initial acquisition'),('iter_failure_wrist','Pickup contact guard'),('regrasp_lift_wrist','Grasp reliability after reobservation')]):
        image(s,frames/(key+'.jpg'),.48+4.17*i,1.45,4.03,3.6)
        text(s,label,.6+4.17*i,1.12,3.85,.32,12,True,BLUE)
    table(s,['Initial pose metric','Mean'],[['Translation / rotation','2.60 mm / 1.44°'],['ADD / ADD-S','3.17 / 2.29 mm']],.55,5.16,5.3,1.04,12)
    table(s,['Failure category','Attempts'],[['Pickup contact / hammer planning','24 / 6'],['Insertion guard / spanner grasp loss','6 / 1']],6.2,5.16,6.55,1.04,12)
    caption(s,'Initial pose error, TCP tracking and final placement are different endpoints. 500 Hz physics is not visual feedback frequency.',6.67)

    s=slide('Generalization boundary: background-dependent localization',[20,21],'Limitations')
    plate(s,'background',.4,1.1,8.3,3.8)
    heading(s,'Observed limitation',9,1.5,3.8)
    text(s,'Absent rack target, but mismatched background geometry produces a false-positive region.\n\nThe zoom is from the same original image.',9,1.98,3.8,2.4,15)
    table(s,['Assumption','Impact on interpretation'],[['Known pickup stations and paired backgrounds','Does not establish arbitrary-clutter recognition'],['Synthetic scans, ideal FK / depth, rigid mounts','Does not establish real-camera or hardware reliability'],['Small reused-seed sample','Broader unseen-scene trials remain necessary']],.55,5.22,12.2,1.5,14)
    caption(s,'Separate development diagnosis; not pooled into the 50-scene localization audit or the 48 robot attempts.',6.8)

    s=slide('What the integrated system demonstrates',[21,1],'Discussion')
    image(s,frames/'final_overview.jpg',.45,1.12,8.55,5.65)
    heading(s,'Demonstrated',9.38,1.4,3.4)
    text(s,'Independent calibration\nVisual 6D pose integration\nPhysical regrasp and assembly\nAuditable feedback comparison',9.38,1.85,3.4,1.55,14)
    heading(s,'Next priorities',9.38,3.81,3.4)
    text(s,'Improve pickup contacts.\nTest changed backgrounds.\nUse unseen seeds and external baselines.\nValidate on hardware.',9.38,4.25,3.4,1.7,13)
    text(s,'High reliability and statistical superiority are not established.',9.38,6.25,3.4,.6,11,False,GREY)

    s=slide('References and reproducibility',[22],'Appendix')
    text(s,'Selected methods\nWen et al. FoundationPose. CVPR, 2024.\nZhang. A flexible new technique for camera calibration. TPAMI, 2000.\nOpenCV. Camera and hand–eye calibration documentation.\nChaumette & Hutchinson. Visual servo control, Part I. RAM, 2006.\nTodorov et al. MuJoCo. IROS, 2012.\n\nReviewed alternatives\nLabbé et al. MegaPose. arXiv:2212.06870, 2022.\nFang et al. GraspNet-1Billion. CVPR, 2020.',.65,1.4,6.6,4.7,15)
    text(s,'Repository evidence\nCalibration images + robot FK\nPredicted and evaluation masks\n48 complete trial summaries\nOriginal successful and failed replays\n15 annotated image plates (PDF / SVG)\nFrame indices, crop boxes and source hashes\n\nFull references: docs/LITERATURE_AND_SELECTION.md\nExperiment report: visual-feedback-calibrated-v1',7.7,1.4,5.05,4.7,15)
    caption(s,'Simulation images illustrate observed behavior; quantitative conclusions use all predefined attempted trials.',6.63)

    prs.save(out/'vision_guided_manipulation.pptx')
    (out/'slides.json').write_text(json.dumps(notes,indent=2)+'\n')
    (out/'speaker_notes.md').write_text('# English speaker notes — compact academic version\n\n20 main slides + 1 reference appendix. Target: approximately 18–20 minutes, including demonstrations.\n\n'+'\n\n'.join(f"## {n['slide']}. {n['title']}\n\n{n['notes']}\n\nSource: {n['source']}" for n in notes)+'\n')
    meta={'revision':'Image-led academic deck with embedded task/feedback videos and traceable processing chain','slides':len(prs.slides),'main_slides':len(prs.slides)-1,'appendix_slides':1,'language':'English','title_font_pt':20,'body_font_pt_range':[11,14],'equation_font_pt':14,'results':str(results.relative_to(ROOT)),'summary_sha256':sha(results/'summary.json'),'image_assets_sha256':assets,'image_plate_manifest_sha256':sha(plates/'manifest.json'),'content_source':'content.json','content_sha256':sha(ROOT/'docs/presentation/content.json'),'slides_with_runtime_or_calibration_images':sum(any('/figures/' not in p for p in n['images']) for n in notes),'embedded_videos':2,'main_video_duration_s':195.88,'main_video_editing':'Full continuous replay with frame-synchronized task strip; no cuts or speed changes','statistical_chart_placements':1,'runtime_image_panel_placements':sum(len(pm[Path(p).stem]) if '/plates/' in p else int('/figures/' not in p) for n in notes for p in n['images'])}
    (out/'provenance.json').write_text(json.dumps(meta,indent=2)+'\n');print({k:meta[k] for k in ['slides','runtime_image_panel_placements','slides_with_runtime_or_calibration_images']})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.results.resolve(),a.output.resolve())
