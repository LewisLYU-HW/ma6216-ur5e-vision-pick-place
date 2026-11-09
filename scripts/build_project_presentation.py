"""Build compact academic slides from traceable archived content and image plates."""
import argparse,json,hashlib
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
        text(s,title,.45,.26,11.9,.45,21,True);text(s,section,10.5,.85,2.3,.24,10,False,GREY)
        rect(s,.45,.81,12.4,.012,'BCC9D0');text(s,f'{len(prs.slides):02}',12.35,.32,.45,.25,11,False,GREY)
        note='\n\n'.join(source[i-1]['notes'] for i in ids);refs=' | '.join(dict.fromkeys(source[i-1]['source'] for i in ids))
        notes.append({'slide':len(prs.slides),'title':title,'notes':note,'source':refs,'images':[]});s.notes_slide.notes_text_frame.text=note+'\n\nEvidence: '+refs
        text(s,'MA6216 · Vision-guided robotic manipulation · simulation evidence',.45,7.13,11.8,.22,9,False,GREY)
        return s
    def image(s,p,x,y,w,h):
        p=Path(p);iw,ih=Image.open(p).size;k=min(w/iw,h/ih);dw,dh=iw*k,ih*k
        s.shapes.add_picture(str(p),Inches(x+(w-dw)/2),Inches(y+(h-dh)/2),width=Inches(dw),height=Inches(dh));rel=str(p.relative_to(ROOT));assets[rel]=sha(p);notes[-1]['images'].append(rel)
    def plate(s,n,x,y,w,h):image(s,plates/(n+'.png'),x,y,w,h)
    def sequence(s,keys,labels,y):
        width=12.2/len(keys)
        for i,(key,label) in enumerate(zip(keys,labels)):
            x=.55+i*width
            image(s,frames/(key+'.jpg'),x,y+.30,width-.18,2.00)
            text(s,chr(97+i)+'  '+label,x+.12,y,width-.35,.25,12,False,INK)
    def heading(s,t,x,y,w=5.8):text(s,t,x,y,w,.3,16,True,BLUE)
    def table(s,headers,rows,x,y,w,h,size=14):
        tb=s.shapes.add_table(len(rows)+1,len(headers),Inches(x),Inches(y),Inches(w),Inches(h)).table
        for i,row in enumerate([headers,*rows]):
            for j,v in enumerate(row):
                c=tb.cell(i,j);c.text=str(v);c.margin_left=c.margin_right=Inches(.08);c.margin_top=c.margin_bottom=Inches(.06)
                c.fill.solid();c.fill.fore_color.rgb=RGBColor.from_string('EDF2F5' if i==0 else 'FFFFFF')
                for p in c.text_frame.paragraphs:p.font.name='Aptos';p.font.size=Pt(size);p.font.bold=i==0;p.font.color.rgb=RGBColor.from_string(INK)
    def caption(s,t,y=6.55):text(s,t,.55,y,12.2,.48,12,False,GREY)
    def equation(s,parts,x,y,w):
        z=text(s,'',x,y,w,.5,23);p=z.text_frame.paragraphs[0]
        for value,base in parts:
            r=p.add_run();r.text=value;r.font.name='Cambria Math';r.font.size=Pt(16 if base else 23);r.font.color.rgb=RGBColor.from_string(INK)
            if base:r._r.get_or_add_rPr().set('baseline',str(base))

    s=slide('Calibrated 6D vision for sequential tool manipulation',[1,2],'Problem & scope')
    plate(s,'overview',.4,1.08,8.3,3.6)
    heading(s,'Study objective',9,1.22,3.8)
    text(s,'UR5e + Robotiq 2F-85 in MuJoCo\nRGB-D reconstruction + FoundationPose\n\nDoes execution-period pose feedback improve complete-task reliability?',9,1.68,3.8,2.5,16)
    table(s,['Operation','Required relationship','Acceptance'],[['Hammer return','Tool-to-tray pose','Released support'],['Moving screwdriver','Shaft-to-tilted-socket axis','Insertion + release'],['Independent rack','Frame-to-base seating','Stable fixture'],['Spanner regrasp / hang','New grasp; hole-to-pin alignment','Released hanging']],.55,4.65,12.2,1.95,14)
    caption(s,'Scope: one continuous four-operation scene. Contribution: independent integration and evaluation of existing methods.',6.72)

    s=slide('System architecture and technical selection',[3,4],'Methods')
    steps=[('RGB-D','Estimated K'),('Localization','Depth foreground'),('6D pose','FoundationPose'),('Robot target','Calibrated chain'),('Execution','IK + control')]
    for i,(a,b) in enumerate(steps):
        x=.55+i*2.47;rect(s,x,1.25,2.2,.78,'EDF2F5');text(s,a,x+.1,1.36,2,.26,16,True);text(s,b,x+.1,1.71,2,.24,12,False,GREY)
        if i<4:text(s,'→',x+2.23,1.49,.25,.3,17)
    text(s,'Reobserve → update pose → bounded correction; simulation truth enters downstream scoring only.',.65,2.21,12,.44,15)
    table(s,['Method / component','Output / role','Selection boundary'],[['FoundationPose','Object-frame 6D pose','Selected; reconstructed RGB-D references'],['MegaPose','Model-based 6D pose','Reviewed; no external benchmark'],['GraspNet','Grasp candidates','Does not alone specify assembly pose'],['MuJoCo / OpenCV','Contact simulation / calibration','Reuse platform; inspectable interfaces']],.55,2.9,8.2,2.7,14)
    image(s,frames/'regrasp_lift_wrist.jpg',9.05,2.9,3.75,2.7)
    text(s,'Model-free route: 24 calibrated RGB-D reference views → object-specific reconstruction → registration / tracking.\nReferences and pretrained networks are still required; synthetic reference calibration remains an assumption.',.65,5.94,12,.85,15)

    s=slide('Camera calibration: estimation and independent validation',[5],'Methods')
    plate(s,'calibration',.45,1.1,8.25,3.65)
    table(s,['Procedure','Train / validation','Validation result'],[['Wrist intrinsics','24 / 8 views','0.02177 px RMSE'],['Wrist hand–eye','24 / 10 views','0.852 mm / 0.0227°'],['Frozen chain','K, X and Y fixed','0.05497 px']],8.85,1.4,3.95,2.65,12)
    heading(s,'Estimation protocol',.65,5.05)
    text(s,'Checkerboard pixels → intrinsic calibration → image PnP + robot FK → AX = XB → training-only refinement.',.65,5.48,12,.52,16)
    text(s,'Simulator K and camera pose are validation references only. Rejected images and held-out views are retained.\nThe known distortion-free pinhole model explains the small residuals; these are not real-camera accuracy claims.',.65,6.06,12,.78,14)

    s=slide('Localization: image masks, evaluation unit and assumptions',[7],'Methods & validation')
    plate(s,'localization',.45,1.12,12.4,3.55)
    table(s,['Detector','Independent evaluation','Boundary'],[['Depth foreground subtraction\nKnown pickup regions','50 scenes / 200 queries\n10 scenes per tool–condition cell','Matched empty backgrounds\nRestricted occlusion / noise'],['Predictions saved first','160/160 positive queries: IoU ≥ 0.5\n0/40 absent-target false positives','Wilson and scene-bootstrap intervals\nNot 200 robot executions']],.55,4.93,12.2,1.58,14)
    caption(s,'Nominal seed 500. Green: overlap; blue: missed visible target; red: extra foreground. Crops preserve original overlays.',6.72)

    s=slide('6D pose estimation and coordinate transformation',[6,4],'Methods')
    equation(s,[('T',0),('BO',-25000),(' = T',0),('BG',-25000),(' · T',0),('GC',-25000),(' · T',0),('CO',-25000)],.65,1.25,7)
    text(s,'B: robot base   G: gripper   C: wrist camera   O: object',.65,1.95,8,.35,14)
    text(s,'T_AB maps coordinates from B into A.\nFK supplies T_BG; calibration estimates T_GC.\nFoundationPose supplies T_CO from visual observations.',8.65,1.3,4.1,1.25,14)
    image(s,frames/'driver_align_wrist.jpg',.65,2.65,5.9,3.25);image(s,frames/'regrasp_lift_wrist.jpg',6.85,2.65,5.9,3.25)
    text(s,'Task target: estimated object pose + task-specific geometric offset.\nRegrasp changes the object-to-gripper relationship; observe again before generating the next target.',.65,6.17,12,.7,15)

    s=slide('Visual feedback: modes, residuals and correction policy',[8,15],'Methods')
    table(s,['Mode','Execution-period observation','Common components'],[['Open loop','Initial acquisition / feed prediction only','Same estimator, calibration and guards'],['Staged','Selected task-transition reobservations','Same physical acceptance'],['Iterative','Repeated precontact pose correction','Staged observations retained']],.55,1.2,12.2,1.85,14)
    plate(s,'correction',.4,3.24,7.5,3.0)
    equation(s,[('e',0),('p',-25000),(' = p',0),('des',-25000),(' − p',0),('est',-25000)],8.3,3.5,4.5)
    equation(s,[('ΔR = R',0),('des',-25000),(' R',0),('est',-25000),('T',30000)],8.3,4.16,4.5)
    text(s,'Cap: 4 mm / 2° per step\nConverged: two observations within\n1.5 mm / 1.5°\nDiscrete precontact control; no stability proof.',8.3,4.91,4.45,1.3,14)
    caption(s,'Correction images: separate perturbed integration run, one logged correction; 1.60° → 0.74° are visual residuals, not true geometric errors.',6.63)

    s=slide('Experimental design and metric definitions',[9,18],'Evaluation protocol')
    table(s,['Factor','Levels / unit','Control'],[['Feedback','Open loop / staged / iterative','Same pose estimator and camera calibration'],['Disturbance','None / alignment force–torque pulse','Delivery logged; early failures retained'],['Randomization','8 seeds per cell; 48 attempts','Initial states paired within seed'],['Primary outcome','All four final physical checks','Geometry + support + release + stability']],.55,1.2,12.2,2.5,14)
    image(s,frames/'initial_overview.jpg',.65,4.05,4.1,2.7)
    heading(s,'Statistical reporting',5.15,4.15)
    text(s,'Success: Wilson 95% confidence intervals.\nPaired comparisons: exact tests with Holm adjustment.\nContinuous metrics: trial-level summaries and bootstrap intervals.\nSeeds 400–407 are reused: paired replication, not a new holdout.\nNo task failures are removed or pooled with historical studies.',5.15,4.62,7.5,2.0,15)

    s=slide('Execution evidence I: tool return and tilted insertion',[10,11],'Representative successful run')
    sequence(s,['hammer_lift_overview','hammer_released_overview'],['Lift / 13.60 s','Released placement / 25.00 s'],1.12)
    text(s,'a–b  Hammer: held transport → released tray placement. Support and stability determine acceptance.',.65,3.45,12,.36,13)
    sequence(s,['driver_orient_wrist','driver_insert_wrist','driver_done_wrist'],['Reorientation / 50.00 s','Insertion / 60.00 s','Released / 70.00 s'],3.94)
    caption(s,'a–c  Screwdriver: reorientation → guarded insertion → released placement. Initial moving-target acquisition precedes these frames.',6.57)

    s=slide('Execution evidence II: rack installation and physical regrasp',[12,13],'Representative successful run')
    sequence(s,['rack_lift_overview','rack_insert_wrist','rack_done_overview'],['Frame pickup / 91.00 s','Seating / 112.00 s','Released fixture / 134.40 s'],1.12)
    text(s,'a–c  Rack: independent frame → seating → released fixture; relocalize before the next operation.',.65,3.45,12,.36,13)
    sequence(s,['regrasp_place_wrist','regrasp_clear_wrist','regrasp_lift_wrist'],['Supported / 147.00 s','Finger clearance / 150.40 s','New grasp / 158.20 s'],3.94)
    caption(s,'a–c  Spanner: supported placement → finger clearance → new grasp after observation. One continuous original trajectory.',6.57)

    s=slide('Hole-over-pin placement and terminal acceptance',[14],'Representative successful run')
    plate(s,'hanging',.4,1.08,12.4,4.2)
    table(s,['Visual relationship','Controller / physical evidence','Interpretation'],[['Visual alignment','Thread → seat → release','Explanatory ROI outlines'],['Final support','Four terminal checks passed','Single feasible trajectory'],['Passive stability','30 s stable after release','Separate diagnostic']],.55,5.45,12.2,1.35,13)

    s=slide('Paired qualitative comparison and failure boundary',[16,17],'Controlled examples')
    sequence(s,['open_failure_wrist','driver_done_wrist'],['Open loop / guard stop / 57.96 s','Iterative / released / 70.00 s'],1.12)
    text(s,'Seed 400, no disturbance: open-loop insertion guard stop vs iterative released placement. Different endpoint times.',.65,3.46,12,.38,13)
    sequence(s,['staged_failure_wrist','iter_failure_wrist'],['Staged / pickup stop / 40.24 s','Iterative / pickup stop / 40.24 s'],3.94)
    caption(s,'Seed 401: both staged and iterative modes stop at gripper closure. Contact causes come from logs, not visual inference.',6.57)

    s=slide('Whole-sequence results and statistical uncertainty',[18],'Quantitative results')
    image(s,results/'figures/success_rates.png',.45,1.15,8.0,4.05)
    table(s,['Mode','None','Pulse'],[['Open loop','0/8','0/8'],['Staged','3/8','2/8'],['Iterative','3/8','3/8']],8.65,1.5,4.1,2.2,15)
    text(s,'11/48 complete successes.\nAll four adjusted paired p-values: 1.0.\nNo statistically established superiority\nor equivalence in this sample.',8.65,4.03,4.1,1.38,15)
    heading(s,'Interpretation',.65,5.6)
    text(s,'The selected successful trajectory demonstrates feasibility. Low complete-sequence reliability and wide intervals limit conclusions about feedback benefit. Early failures remain part of the system-level outcome.',.65,6.04,12.0,.78,15)

    s=slide('Diagnostic results: pose accuracy and physical failures',[19],'Error decomposition')
    table(s,['Initial pose metric','Mean'],[['Translation error','2.60 mm'],['Rotation error','1.44°'],['ADD / ADD-S','3.17 / 2.29 mm']],.55,1.3,5.3,2.02,15)
    table(s,['Failure category','Attempts'],[['Moving-pickup contact guard','24'],['Hammer approach planning','6'],['Open-loop insertion guard','6'],['Bilateral spanner grasp loss','1']],6.2,1.3,6.55,2.02,14)
    for i,key in enumerate(['driver_align_wrist','iter_failure_wrist','regrasp_lift_wrist']):image(s,frames/(key+'.jpg'),.65+4.15*i,3.72,3.75,2.65)
    caption(s,'Different endpoints: initial pose error, TCP tracking error, final placement and task success. 500 Hz physics is not visual feedback frequency.',6.67)

    s=slide('Generalization boundary: background-dependent localization',[20,21],'Limitations')
    plate(s,'background',.4,1.1,8.3,3.8)
    heading(s,'Observed limitation',9,1.5,3.8)
    text(s,'Absent rack target, but mismatched background geometry produces a false-positive region.\n\nThe zoom is from the same original image.',9,1.98,3.8,2.4,15)
    table(s,['Assumption','Impact on interpretation'],[['Known pickup stations and paired backgrounds','Does not establish arbitrary-clutter recognition'],['Synthetic scans, ideal FK / depth, rigid mounts','Does not establish real-camera or hardware reliability'],['Small reused-seed sample','Broader unseen-scene trials remain necessary']],.55,5.22,12.2,1.5,14)
    caption(s,'Separate development diagnosis; not pooled into the 50-scene localization audit or the 48 robot attempts.',6.8)

    s=slide('Conclusions and priorities for further experiments',[21,1],'Discussion')
    table(s,['Supported by the evidence','Not established'],[['Independent calibration integrated into visual control','Real-robot accuracy and reliability'],['Physical four-operation sequence with regrasp','High success rate across arbitrary layouts'],['Auditable internal feedback comparison','Statistical superiority or external-algorithm ranking']],.55,1.2,12.2,2.0,15)
    image(s,frames/'final_wrist.jpg',.65,3.7,4.7,2.95)
    heading(s,'Next experiments',5.75,3.8)
    text(s,'1. Improve pickup planning and bilateral-contact reliability.\n2. Test segmentation under changed backgrounds and clutter.\n3. Evaluate pose bias and observation scheduling.\n4. Use unseen seeds and matched external-estimator baselines.\n5. Validate the calibrated pipeline on physical hardware.',5.75,4.3,7,2.0,15)

    s=slide('References and reproducibility',[22],'Appendix')
    text(s,'Selected methods\nWen et al. FoundationPose. CVPR, 2024.\nZhang. A flexible new technique for camera calibration. TPAMI, 2000.\nOpenCV. Camera and hand–eye calibration documentation.\nChaumette & Hutchinson. Visual servo control, Part I. RAM, 2006.\nTodorov et al. MuJoCo. IROS, 2012.\n\nReviewed alternatives\nLabbé et al. MegaPose. arXiv:2212.06870, 2022.\nFang et al. GraspNet-1Billion. CVPR, 2020.',.65,1.4,6.6,4.7,15)
    text(s,'Repository evidence\nCalibration images + robot FK\nPredicted and evaluation masks\n48 complete trial summaries\nOriginal successful and failed replays\n12 annotated image plates (PDF / SVG)\nFrame indices, crop boxes and source hashes\n\nFull references: docs/LITERATURE_AND_SELECTION.md\nExperiment report: visual-feedback-calibrated-v1',7.7,1.4,5.05,4.7,15)
    caption(s,'Simulation images illustrate observed behavior; quantitative conclusions use all predefined attempted trials.',6.63)

    prs.save(out/'vision_guided_manipulation.pptx')
    (out/'slides.json').write_text(json.dumps(notes,indent=2)+'\n')
    (out/'speaker_notes.md').write_text('# English speaker notes — compact academic version\n\n15 main slides + 1 reference appendix. Target: approximately 12–15 minutes.\n\n'+'\n\n'.join(f"## {n['slide']}. {n['title']}\n\n{n['notes']}\n\nSource: {n['source']}" for n in notes)+'\n')
    meta={'revision':'Compact academic layout; no takeaway banners','slides':16,'main_slides':15,'appendix_slides':1,'language':'English','title_font_pt':21,'body_font_pt_range':[12,16],'results':str(results.relative_to(ROOT)),'summary_sha256':sha(results/'summary.json'),'image_assets_sha256':assets,'image_plate_manifest_sha256':sha(plates/'manifest.json'),'content_source':'content.json','content_sha256':sha(ROOT/'docs/presentation/content.json'),'slides_with_runtime_or_calibration_images':sum(any('/figures/' not in p for p in n['images']) for n in notes),'statistical_chart_placements':1,'runtime_image_panel_placements':sum(len(pm[Path(p).stem]) if '/plates/' in p else int('/figures/' not in p) for n in notes for p in n['images'])}
    (out/'provenance.json').write_text(json.dumps(meta,indent=2)+'\n');print({k:meta[k] for k in ['slides','runtime_image_panel_placements','slides_with_runtime_or_calibration_images']})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.results.resolve(),a.output.resolve())
