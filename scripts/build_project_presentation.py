"""Build an academic English presentation from calibrated manipulation evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches,Pt
from pptx.oxml.xmlchemy import OxmlElement

ROOT=Path(__file__).resolve().parents[1]
INK,BLUE,GREY,LIGHT,AMBER='182F43','146B8C','536271','EFF4F7','A96516'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def build(results,output,preview=False):
    if preview:raise ValueError('Use complete published evidence')
    summary=json.loads((results/'summary.json').read_text());assert summary['complete'] and summary['n_trials']==48
    assert summary['calibration']['wrist_hand_eye']['measured_error']
    plates=ROOT/'docs/presentation/plates';frames=ROOT/'docs/presentation/frames'
    pm=json.loads((plates/'manifest.json').read_text());output.mkdir(parents=True,exist_ok=True)
    prs=Presentation();prs.slide_width=Inches(13.333);prs.slide_height=Inches(7.5)
    notes=[];assets={}
    def text(s,v,x,y,w,h,size=22,color=INK,bold=False):
        z=s.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h));tf=z.text_frame;tf.word_wrap=True
        tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
        for i,line in enumerate(v.split('\n')):
            p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=line
            p.font.name='Aptos';p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=RGBColor.from_string(color);p.space_after=Pt(7)
        return z
    def equation(s,parts,x,y,w):
        z=text(s,'',x,y,w,.7,32,BLUE,False);p=z.text_frame.paragraphs[0]
        for value,baseline in parts:
            r=p.add_run();r.text=value;r.font.name='Cambria Math';r.font.size=Pt(22 if baseline else 32);r.font.color.rgb=RGBColor.from_string(BLUE)
            if baseline:r._r.get_or_add_rPr().set('baseline',str(baseline))
        return z
    def rect(s,x,y,w,h,color):
        z=s.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h));z.fill.solid();z.fill.fore_color.rgb=RGBColor.from_string(color);z.line.fill.background();z._element.spPr.append(OxmlElement('a:effectLst'));
        for e in z._element.iter():
            if e.tag.endswith('}effectRef'):e.set('idx','0')
        return z
    def slide(title,section,note,source='Final calibrated evaluation | 48 paired attempts | original simulation evidence'):
        s=prs.slides.add_slide(prs.slide_layouts[6]);s.background.fill.solid();s.background.fill.fore_color.rgb=RGBColor(255,255,255)
        text(s,section.split(' / ',1)[-1].upper(),.55,.30,11.9,.25,11,BLUE,True)
        text(s,title,.55,.73,12.2,.62,28,INK,True);rect(s,.55,1.38,12.2,.018,'CCD6DD')
        text(s,source,.55,7.10,11.8,.24,10,GREY);text(s,f'{len(prs.slides):02}',12.35,7.06,.4,.3,12,BLUE,True)
        notes.append({'slide':len(prs.slides),'title':title,'section':section,'notes':note,'source':source,'images':[]})
        s.notes_slide.notes_text_frame.text=note+'\n\nEvidence: '+source
        return s
    def image(s,path,x,y,w,h):
        path=Path(path);iw,ih=Image.open(path).size;scale=min(w/iw,h/ih);dw,dh=iw*scale,ih*scale
        s.shapes.add_picture(str(path),Inches(x+(w-dw)/2),Inches(y+(h-dh)/2),width=Inches(dw),height=Inches(dh))
        rel=str(path.relative_to(ROOT));assets[rel]=sha(path);notes[-1]['images'].append(rel)
    def finding(s,headline,detail=''):
        rect(s,.55,6.25,12.2,.61,LIGHT);text(s,headline,.72,6.36,11.86,.38,19,INK,True)
        if detail:text(s,detail,.65,5.86,12,.31,13,GREY)
    def plate(title,section,name,claim,note,detail='',source=None):
        s=slide(title,section,note,source or 'Representative original run | iterative / no disturbance / seed 400 | playback time')
        image(s,plates/f'{name}.png',.45,1.58,12.43,4.15)
        finding(s,claim,detail);return s
    def body(s,heading,content,x,y,w=5.7):
        text(s,heading,x,y,w,.4,21,BLUE,True);text(s,content,x,y+.55,w,1.6,20)

    s=slide('Calibrated 6D Vision for Sequential Tool Manipulation','MA6216 / Final Project 1',
        'We study vision-guided manipulation in a simulated maintenance workcell. The system integrates independently estimated camera calibration, image-based localization, reconstructed object references, FoundationPose, and physical robot control. Four dependent operations are executed in one continuous scene. The research question is whether additional execution-period pose feedback improves complete-sequence success, rather than merely improving a local alignment residual. The contribution is independent engineering integration and critical evaluation, not a new neural algorithm.',
        'UR5e + Robotiq 2F-85 | MuJoCo | Model-free reference reconstruction + FoundationPose')
    image(s,plates/'overview.png',.4,1.6,8.5,4.2)
    text(s,'Independent calibration\n6D pose-guided assembly\nControlled feedback comparison',9.1,2.15,3.7,2.7,22,BLUE,True)
    finding(s,'A reproducible study of perception, physical manipulation and feedback.')

    s=slide('Research question and task constraints','01 / Problem formulation',
        'The central question is whether more visual feedback improves a sequential task when calibration, pose estimation and contact all contribute errors. Translation alone is insufficient: shaft-to-socket and hole-to-pin relationships constrain orientation. Rack installation changes the next task fixture, while spanner regrasp changes the object-to-gripper relationship. We therefore distinguish local pose alignment from released whole-sequence success. One successful replay illustrates feasibility; all attempted trials are required for evaluation.')
    image(s,plates/'hanging.png',.4,1.65,8.35,3.9)
    body(s,'Research question','Does execution-period 6D feedback improve complete-task reliability?',9.05,1.8,3.7)
    body(s,'Geometric constraints','Tool-axis alignment\nMovable fixture\nChanged grasp transform',9.05,4.0,3.7)
    finding(s,'Local alignment and complete-sequence success are different endpoints.')

    s=slide('System architecture and information boundaries','02 / Method',
        'The control path starts with RGB-D and estimated calibration. Depth foreground segmentation generates the mask; FoundationPose estimates the object in the camera frame from reconstructed references. Calibrated transforms and robot FK map the pose into a robot target. Checked IK and trajectories, joint control and contact guards execute the operation. Reobservations close a discrete precontact loop. Simulator object truth is downstream evaluation only. Robot FK and contact sensing are legitimate inputs but are not substitutes for visual object localization.')
    steps=[('RGB-D','Estimated K'),('Localization','Foreground mask'),('6D pose','FoundationPose'),('Robot target','Calibrated transforms'),('Execution','IK + joint control')]
    for i,(a,b) in enumerate(steps):
        x=.55+i*2.48;rect(s,x,1.85,2.25,1.03,LIGHT);text(s,a,x+.12,2,2.01,.35,20,BLUE,True);text(s,b,x+.12,2.48,2.01,.27,13,GREY)
        if i<4:text(s,'→',x+2.28,2.17,.22,.4,18,BLUE)
    text(s,'Execution-period images → re-estimate pose → bounded target correction',.7,3.18,12,.5,21,BLUE)
    for i,k in enumerate(['initial_overview','driver_align_wrist','final_wrist']):image(s,frames/(k+'.jpg'),.8+4.1*i,3.87,3.6,1.85)
    finding(s,'Simulation truth is used for scoring, not for commanded object poses.')

    s=slide('Method selection for pose-guided manipulation','02 / Technical rationale',
        'FoundationPose was selected for its few-shot model-free reference route and object-pose output. The tool CAD is not supplied to the pose estimator; calibrated RGB-D scans are reconstructed into an object-specific representation. This still requires references and pretrained networks. MegaPose and GraspNet were reviewed alternatives: the former estimates model-based object pose, while the latter predicts grasp candidates. They were not executed as external experimental baselines. MuJoCo retains the original robot and contact model; OpenCV provides calibration and image operations.',
        'Wen et al., CVPR 2024; Labbé et al., 2022; Fang et al., CVPR 2020; Todorov et al., IROS 2012')
    image(s,frames/'regrasp_lift_wrist.jpg',.6,1.65,5.45,4.32)
    body(s,'Selected: FoundationPose','Object-specific RGB-D reconstruction → camera-frame 6D pose',6.55,1.75)
    body(s,'Reviewed alternatives','MegaPose: model-based 6D pose\nGraspNet: grasp candidates, not assembly pose',6.55,3.75)
    finding(s,'“Model-free” describes the reference route; it does not mean reference-free.')

    plate('Image-based intrinsic and hand–eye calibration','02 / Calibration','calibration',
        'Wrist validation: 0.02177 px RMSE; hand–eye error 0.852 mm / 0.0227°.',
        'Wrist intrinsics use twenty-four accepted training views and eight held-out views. Hand-eye estimation uses image PnP and robot FK, followed by AX equals XB and training-only refinement, with twenty-four training and ten validation views. Validation freezes K, the hand-eye transform and board pose. The simulator provides reference values only after estimation. The very low reprojection residuals reflect synthetic distortion-free images; they are not evidence of equivalent real-camera precision.',
        'Intrinsic validation: 8 views. Hand–eye validation: 10 views. Ideal pinhole image formation.',
        'Actual checkerboard captures | Zhang 2000; OpenCV hand–eye conventions | wrist-calibration-v1')

    s=slide('Coordinate chain and the object-to-gripper transform','02 / Pose-to-action mapping',
        'For the wrist camera, the camera-to-base transform is obtained from robot FK and the independently estimated camera-to-gripper transform. Multiplying by the camera-frame object estimate produces the object pose in the base frame. The notation T sub A B maps coordinates in frame B into frame A. Task-specific geometric offsets then define the desired grasp or insertion target. After a physical regrasp, the object-to-gripper relationship must be observed again; a previous rigid relationship cannot simply be reused.')
    equation(s,[('T',0),('BO',-25000),(' = T',0),('BG',-25000),(' · T',0),('GC',-25000),(' · T',0),('CO',-25000)],.8,1.7,11.8)
    text(s,'B: robot base     G: gripper     C: wrist camera     O: object',.8,2.45,11.8,.4,19,GREY)
    image(s,frames/'regrasp_clear_wrist.jpg',.65,3.15,5.85,2.6)
    image(s,frames/'regrasp_lift_wrist.jpg',6.85,3.15,5.85,2.6)
    finding(s,'Regrasp requires an updated object-to-gripper transform.')

    plate('Localization outputs and the evaluation boundary','02 / Visual localization','localization',
        'Depth foreground masks are evaluated independently of manipulation success.',
        'These are crops of original mask overlays for all four tools in nominal seed five hundred. Green marks overlapping prediction and visible target, blue marks missed target and red extra foreground. Known pickup regions associate masks with tools. The fifty-scene audit contains two hundred queries, including one hundred sixty target-present and forty target-absent queries. Predictions are saved before simulator labels are read. All positive queries pass the predefined IoU threshold in this restricted audit, with no absent-target false positives; each tool-condition cell has only ten examples.',
        'Green: overlap; blue: missed target; red: extra foreground. 50 scenes / 200 queries.',
        'Localization audit | nominal seed 500 | cropped original overlays | separate from the 48 robot attempts')

    plate('Physical tool return: grasp, transport and release','03 / Manipulation evidence','hammer',
        'The acceptance criterion requires released support, not waypoint arrival.',
        'The hammer operation clears tool access before the feed operation. These matched crops show a held tool and the released tray state from the same continuous run. Image-estimated object pose determines the target; checked motion and joint control execute it. Support, geometry and stability determine acceptance. Hammer approach planning failures are retained in the full comparison, rather than treating only reached placements as attempted trials.',
        'Spatially matched overview crops; no scene content or image contrast altered.')

    plate('Moving-target acquisition followed by tilted insertion','03 / Manipulation evidence','insertion',
        'The screwdriver shaft must align with the socket before guarded insertion.',
        'The screwdriver is first localized on a moving feed and intercepted using prediction. The image sequence begins after acquisition, showing reorientation, guarded insertion and the released screwdriver. Every feedback mode includes initial visual acquisition and moving-target prediction. The comparison concerns execution-period corrections, not vision versus no vision. Frames illustrate the mechanism; the physical acceptance logs establish successful support after release.',
        'Wrist crops: reorientation → insertion → released placement. Playback times are not wall times.')

    plate('Rack installation creates a new downstream fixture','03 / Manipulation evidence','rack',
        'The installed rack is released and relocalized before spanner hanging.',
        'The independent frame is picked up and physically seated on its base. Because seating can change the fixture pose, the rack is checked and observed again before the spanner approaches it. The three panels have complementary roles: initial independent object, contact-mediated installation, and released assembled fixture. All prior tools remain in the same scene. The fixture observation is part of the staged and iterative control modes.')

    plate('Physical regrasp: release, observe and reacquire','03 / Manipulation evidence','regrasp',
        'Placement, finger clearance and reacquisition are all visible in the original run.',
        'The sequence documents actual physical regrasp rather than changing a software attachment. The spanner is placed on a support, the fingers open and clear the object, and the robot acquires a new grasp after observation. The common crop makes the change in finger-object relationship visible. The image order and timestamps follow one original trajectory. Contact logs and the recorded regrasp event provide independent evidence for the operation.')

    plate('Hole-over-pin alignment and released support','03 / Manipulation evidence','hanging',
        'Final success requires hanging support after gripper withdrawal.',
        'The highlighted region identifies the hole and pin relationship, not a metric error measurement. The images show precontact alignment, threading, and the released final state. No axis or contact force is inferred from the colored annotation. The original trial passes all four terminal checks. A separate thirty-second passive diagnostic retains these outcomes; it does not replace the original score or inspect every five-hundred-hertz physics step.',
        'Amber rectangles identify the hole–pin region; annotations are explanatory, not measured axes.')

    s=slide('Discrete pose-based visual feedback before contact','02 / Feedback formulation',
        'The implemented controller uses discrete pose-based alignment. Open-loop mode uses initial acquisition and prediction but no execution-period visual correction. Staged mode adds selected reobservations. Iterative mode adds repeated estimates and bounded corrections before contact. Position and orientation residuals are measured from vision, with default correction caps of four millimeters and two degrees. Two consecutive observations within one-point-five millimeters and one-point-five degrees establish convergence. This is not continuous contact impedance control or a claim of formal closed-loop stability.',
        'Chaumette & Hutchinson, IEEE RAM 2006 | project-specific discrete pose alignment | VISUAL_FEEDBACK.md')
    equation(s,[('e',0),('p',-25000),(' = p',0),('des',-25000),(' − p',0),('est',-25000),('      ΔR = R',0),('des',-25000),(' R',0),('est',-25000),('T',30000)],.75,1.7,12)
    body(s,'Open loop','Initial images + feed prediction',.75,2.65,3.8)
    body(s,'Staged','Reobserve at task transitions',4.95,2.65,3.6)
    body(s,'Iterative','Repeated bounded pose correction',9,2.65,3.6)
    image(s,frames/'hang_align_wrist.jpg',.75,4.1,3.6,1.85)
    text(s,'Per-step cap: 4 mm / 2°\nConvergence: two observations within 1.5 mm / 1.5°',4.85,4.5,7.8,1.15,21)
    finding(s,'Visual residual ≠ true geometric error ≠ physical acceptance.')

    plate('A logged correction in a perturbed integration run','03 / Feedback mechanism','correction',
        'One correction reduces the estimated angular residual in this example.',
        'This example is from a separately archived calibration integration run with an alignment impulse. One spanner correction is logged. The estimated angular residual decreases from 1.60 to 0.74 degrees; those numbers come from original visual observations, not measurements drawn on the images. The visual change is small, so the figure should not be used to estimate a geometric displacement. This run is not an additional attempt in the final forty-eight-trial comparison.',
        'Separate integration run, seed 400; visual residuals only. Not added to the final 48 attempts.',
        'Calibrated integration | iterative / alignment impulse / seed 400 | original log + original frames')

    s=slide('Paired experimental design and predefined endpoints','04 / Experimental design',
        'The experiment uses three feedback modes, two disturbance conditions and eight seeds per cell: forty-eight complete attempts. Initial physical states are paired by seed. Estimated wrist calibration, pose estimator, control thresholds and physical acceptance remain fixed. The seeds were used previously, making this a paired replication rather than a fresh holdout. Failures before alignment or disturbance delivery stay in the denominator. We report Wilson success intervals, trial-level bootstrap intervals, paired exact tests and Holm correction.')
    image(s,plates/'overview.png',.5,1.65,7.3,3.5)
    body(s,'3 × 2 × 8 = 48 attempts','Feedback mode × disturbance × seed\nSame initial states within seed',8.2,1.8,4.55)
    body(s,'Primary endpoint','All four objects pass final geometry, support, release and stability checks.',8.2,3.9,4.55)
    text(s,'Fixed: camera estimates, pose model, control thresholds, acceptance rules',.7,5.65,12,.4,18,GREY)
    finding(s,'All task failures are retained; reused seeds are explicitly disclosed.')

    plate('Paired insertion outcomes under the same initial state','05 / Qualitative comparison','paired',
        'This pair illustrates behavior; all attempted trials determine performance.',
        'Both runs share initial seed four hundred without disturbance. The open-loop trial stops at the insertion contact guard, while the iterative trial releases the screwdriver and completes the full sequence. The panels are aligned by task outcome, not by playback time. The failure cause is taken from the recorded guard, since a rendered image alone cannot establish the contact violation. This favorable pair must be interpreted with the full paired statistics.',
        'Same seed and initial state; different termination times. Failure reason taken from the original log.',
        'Final 48 attempts | open_loop vs iterative / no disturbance / seed 400')

    plate('Matched failure: both methods stop before alignment','05 / Failure analysis','failure',
        'Early pickup reliability limits the benefit of downstream visual correction.',
        'Seed four hundred one produces an unexpected robot contact during moving-screwdriver gripper closure in both staged and iterative modes. The iterative failure is shown rather than hidden. The failure occurs before later insertion alignment, so it is a reachability bottleneck for evaluating the feedback loop. The contact violation can be submillimeter and need not look dramatic in a screenshot. Its classification comes from the original controller log.',
        'Both trials stop at CLOSE_GRIPPER. Similar appearance does not imply acceptable contact.',
        'Final 48 attempts | staged vs iterative / no disturbance / seed 401')

    s=slide('Complete-sequence success and uncertainty','05 / Quantitative results',
        'The complete-sequence success rates are low, and uncertainty is wide. Open-loop succeeds zero of eight with and without disturbance. Staged feedback succeeds three of eight without and two of eight with disturbance. Iterative feedback succeeds three of eight in both conditions. All four method comparisons have Holm-adjusted p equal to one. This establishes neither superiority nor equivalence. The images demonstrate feasible behavior but do not override the full attempted-trial results.',
        'n = 8 per mode × condition | Wilson 95% confidence intervals | exact paired tests with Holm correction')
    image(s,results/'figures/success_rates.png',.55,1.65,8.3,4.25)
    image(s,frames/'final_wrist.jpg',9.25,1.85,3.5,2.45)
    text(s,'11 / 48 complete successes\nAll failures retained\nAdjusted p = 1.0',9.25,4.65,3.5,1.25,20,BLUE,True)
    finding(s,'This sample does not establish a statistically significant feedback advantage.')

    s=slide('Pose accuracy and physical failure modes','05 / Diagnostic results',
        'The initial fixed-camera pose errors average 2.60 millimeters and 1.44 degrees; ADD and ADD-S are 3.17 and 2.29 millimeters. Those common initial observations do not directly predict whole-sequence success. Of thirty-seven failures, twenty-four stop at moving-pickup closure, six at hammer approach settling, six during open-loop insertion retraction and one after loss of bilateral spanner grasp. This separates perception accuracy, stage reachability and physical reliability. Execution error and visual timing remain in the full report with sample counts.')
    image(s,frames/'driver_align_wrist.jpg',.6,1.65,5.6,4.15)
    body(s,'Initial pose accuracy','Translation: 2.60 mm\nRotation: 1.44°\nADD / ADD-S: 3.17 / 2.29 mm',6.7,1.75,5.7)
    text(s,'37 failures: 24 pickup · 6 hammer approach\n6 open-loop insertion · 1 grasp loss',6.7,4.55,5.7,1.05,20,AMBER,True)
    finding(s,'Accurate initial pose estimates do not guarantee reliable contact execution.')

    plate('Background dependence bounds visual generalization','06 / Limitations','background',
        'A mismatched background creates a false-positive target region.',
        'This separate development diagnosis uses mismatched background geometry. The rack target is absent, but the overlay contains a false-positive red region. The right panel magnifies the region marked on the context image. It is not pooled into the formal fifty-scene localization audit, which uses matched per-scene empty backgrounds. The example exposes a practical limitation: known pickup stations and consistent background references remain assumptions. No artificial failure or scene retouching was introduced.',
        'Context and magnified ROI from the same original image. Red: false-positive foreground.',
        'Separate localization diagnosis | target absent / rack frame / seed 500 | not a robot-trial outcome')

    s=slide('Conclusions and next experiments','06 / Discussion',
        'The project demonstrates a complete calibrated vision-to-action pipeline and a physically released four-operation sequence. The evidence supports feasibility and inspectability, not superior architecture or real-world reliability. The controlled replication has no statistically established feedback gain. Immediate priorities are pickup/contact reliability, background robustness and then feedback scheduling or pose bias. Future validation requires unseen seeds, broader clutter and occlusion, external pose estimators under matched conditions, and eventually hardware. Reference scanning, rigid mounts, FK and basic depth rendering retain ideal assumptions.')
    image(s,plates/'hanging.png',.45,1.7,8.3,3.75)
    body(s,'Supported','Calibrated perception\nPhysical task integration',9.05,1.85,3.7)
    body(s,'Not established','Architectural superiority\nUnseen-scene generalization\nReal-robot reliability',9.05,3.95,3.7)
    finding(s,'Priority: pickup reliability, then broader controlled evaluation.')

    s=slide('Primary references and reproducible evidence','Appendix / References',
        'These references underpin the implemented methods and reviewed alternatives. FoundationPose is the selected pose estimator. Zhang and OpenCV support calibration, Chaumette and Hutchinson provide visual-servoing concepts, and MuJoCo provides the simulator. MegaPose and GraspNet are literature alternatives rather than executed external baselines. The repository retains source code, calibration images and FK, segmentation masks, complete trial summaries, original replays and all image-plate crop manifests.',
        'Full citations: docs/LITERATURE_AND_SELECTION.md and docs/references.bib | source manifests included')
    image(s,frames/'final_overview.jpg',.6,1.75,4.7,3.6)
    text(s,'Wen et al.  FoundationPose. CVPR, 2024.\nZhang.  A flexible new technique for camera calibration. TPAMI, 2000.\nOpenCV.  Camera and hand–eye calibration documentation.\nChaumette & Hutchinson.  Visual servo control, Part I. RAM, 2006.\nTodorov et al.  MuJoCo. IROS, 2012.\nLabbé et al.  MegaPose. arXiv:2212.06870, 2022.\nFang et al.  GraspNet-1Billion. CVPR, 2020.',5.7,1.8,7.0,4.15,17)
    finding(s,'Code + data + original images + source hashes support independent review.')

    # Scientific argument: methods and experimental design precede execution evidence.
    order=list(range(7))+[12,14]+list(range(7,12))+[13]+list(range(15,22))
    ids=list(prs.slides._sldIdLst)
    for element in ids:prs.slides._sldIdLst.remove(element)
    for i in order:prs.slides._sldIdLst.append(ids[i])
    notes=[notes[i] for i in order]
    for number,(s,n) in enumerate(zip(prs.slides,notes),1):
        n['slide']=number
        for shape in s.shapes:
            if shape.has_text_frame and shape.left>Inches(12) and shape.text.isdigit():shape.text_frame.paragraphs[0].runs[0].text=f'{number:02}'
    prs.save(output/'vision_guided_manipulation.pptx')
    (output/'speaker_notes.md').write_text('# English speaker notes — academic revision\n\nTarget: approximately 12–15 minutes for slides 1–21; slide 22 is a reference appendix.\n\n'+'\n\n'.join(f"## {n['slide']}. {n['title']}\n\n{n['notes']}\n\nSource: {n['source']}" for n in notes)+'\n')
    (output/'slides.json').write_text(json.dumps(notes,indent=2)+'\n')
    runtime_panels=sum(len(pm[Path(p).stem]) if '/plates/' in p else int('/figures/' not in p) for n in notes for p in n['images'])
    meta={'revision':'Academic research presentation with annotated evidence plates','slides':len(notes),'main_slides':len(notes)-1,'appendix_slides':1,'language':'English slides and English notes','layout_preview':False,'results':str(results.relative_to(ROOT)),'summary_sha256':sha(results/'summary.json'),'image_assets_sha256':assets,'image_plate_manifest_sha256':sha(plates/'manifest.json'),'image_plate_manifest':'plates/manifest.json','frame_manifest':'frames/manifest.json','slides_with_runtime_or_calibration_images':sum(any('/figures/' not in p for p in n['images']) for n in notes),'runtime_image_panel_placements':runtime_panels,'statistical_chart_placements':1,'image_transform':'Recorded rectangular crops, common panel viewports, explanatory ROI outlines; no retouching, contrast or outcome edits'}
    (output/'provenance.json').write_text(json.dumps(meta,indent=2)+'\n');print(json.dumps({k:v for k,v in meta.items() if k not in ['image_assets_sha256']}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--layout-preview',action='store_true');a=p.parse_args();build(a.results.resolve(),a.output.resolve(),a.layout_preview)
