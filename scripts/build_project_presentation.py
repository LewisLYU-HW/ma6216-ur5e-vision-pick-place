"""Build an editable English project deck and notes from published evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
NAVY, TEAL, INK, GREY = '142D42', '087F8C', '243746', '576B7C'
METHOD_LABELS = {'open_loop':'Open loop','staged':'Staged','iterative':'Iterative'}


def build(results, output, preview=False):
    summary = json.loads((results / 'summary.json').read_text())
    if not summary['complete'] or summary['n_trials'] != 48:
        raise ValueError('Complete results required')
    if not preview and not summary['calibration']['wrist_hand_eye'].get('measured_error'):
        raise ValueError('Final deck requires estimated-wrist results')
    if preview and 'artifacts' not in output.resolve().parts:
        raise ValueError('Layout previews must stay in artifacts')
    output.mkdir(parents=True, exist_ok=True)
    prs = Presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    notes, assets = [], {}

    def text(slide, value, x, y, w, h, size=24, color=INK, bold=False):
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = shape.text_frame; tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(.025)
        for i, line in enumerate(str(value).split('\n')):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line; p.font.name = 'Aptos'; p.font.size = Pt(size)
            p.font.bold = bold; p.font.color.rgb = RGBColor.from_string(color)
            p.space_after = Pt(12)
        return shape

    def slide(title, note, source='Project implementation and recorded evidence'):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.background.fill.solid(); s.background.fill.fore_color.rgb = RGBColor(248,250,252)
        band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(.14))
        band.fill.solid(); band.fill.fore_color.rgb = RGBColor.from_string(TEAL); band.line.fill.background()
        text(s, title, .55, .35, 12.2, .8, 30, NAVY, True)
        text(s, source, .6, 7.03, 11.5, .3, 10, GREY)
        text(s, str(len(prs.slides)), 12.3, 7.03, .4, .3, 10, GREY)
        if preview:
            text(s, 'LAYOUT PREVIEW — HISTORICAL INPUT, NOT FINAL RESULTS', .6, 6.68, 12, .32, 12, 'A33B20', True)
        s.notes_slide.notes_text_frame.text = note + '\n\nEvidence: ' + source
        notes.append({'slide':len(prs.slides),'title':title,'notes':note,'source':source})
        return s

    def bullets(s, lines, x=.65, y=1.55, w=12, size=25):
        text(s, '\n'.join('• ' + x for x in lines), x, y, w, 4.9, size)

    def picture(s, path, x, y, w, h):
        path = Path(path); iw, ih = Image.open(path).size
        scale = min(w/iw, h/ih); dw, dh = iw*scale, ih*scale
        s.shapes.add_picture(str(path), Inches(x+(w-dw)/2), Inches(y+(h-dh)/2), width=Inches(dw), height=Inches(dh))
        assets[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()

    def table(s, headers, rows, y=1.55, height=3.7, size=19):
        tb = s.shapes.add_table(len(rows)+1,len(headers),Inches(.65),Inches(y),Inches(12),Inches(height)).table
        for i,row in enumerate([headers,*rows]):
            for j,value in enumerate(row):
                cell=tb.cell(i,j);cell.text=str(value)
                cell.fill.solid();cell.fill.fore_color.rgb=RGBColor.from_string(NAVY if i==0 else ('EAF0F5' if i%2 else 'FFFFFF'))
                for p in cell.text_frame.paragraphs:
                    p.font.name='Aptos';p.font.size=Pt(size);p.font.bold=i==0
                    p.font.color.rgb=RGBColor.from_string('FFFFFF' if i==0 else INK)

    s=slide('Vision-Guided Tool Manipulation',
        'Our application is a simulated maintenance workcell. A UR5e and Robotiq gripper return a hammer, intercept and insert a screwdriver, assemble a rack, and regrasp and hang a spanner. The project integrates the complete chain from image measurements to physical manipulation. We use existing pretrained methods and focus on engineering decisions, reproducibility and critical evaluation. The main question is whether additional execution-period visual feedback improves this complete sequence.',
        'MA6216 Final Project 1 | UR5e + Robotiq 2F-85 | MuJoCo')
    picture(s,ROOT/'docs/media/complete-workshop-overview.png',.6,1.4,8.2,5.1)
    text(s,'Calibrate\nLocalize\nEstimate 6D pose\nManipulate\nEvaluate',9.15,1.85,3.5,4.3,27,TEAL,True)

    s=slide('The task requires orientation, not only position',
        'Each phase requires a different geometric relationship. The screwdriver must align its shaft with a tilted socket. The rack must seat on its base. After the rack moves, the spanner must be observed again, released and regrasped, then aligned by its hole with the hanging pin. These constraints explain why centroid detection or color sorting alone would not demonstrate the required 6D pose use. Our final success check revisits all objects after the whole sequence finishes.')
    table(s,['1 / Return','2 / Insert','3 / Assemble','4 / Regrasp + hang'],[['Hammer tray pose','Moving screwdriver\nTilted socket','Independent rack\nRelocalize after seating','Actual finger release\nHole-over-pin placement']],height=2.15,size=23)
    text(s,'Final acceptance: geometry + support contact + release + stability',.75,4.45,11.8,1.1,27,TEAL,True)

    s=slide('System architecture and evaluation boundary',
        'The forward path starts with RGB-D images and estimated camera calibration. Segmentation supplies the object mask, and FoundationPose estimates the object pose relative to the camera using the reconstructed reference. Camera-to-robot transforms convert that estimate into grasp and insertion goals. IK, trajectory checks and joint control execute the motion. Reobservations close the pose-based loop. Simulator object and camera truth remain in downstream scoring; robot FK, contact guards and physical acceptance have separate roles.')
    bullets(s,['RGB-D + estimated calibration → foreground mask','Reference reconstruction + FoundationPose → camera-frame 6D pose','Camera-to-robot transform → grasp / insertion target','IK + collision checks + joint control → physical manipulation','Reobserve → bounded pose correction; score with independent truth'],size=25)

    s=slide('Technical selection: match outputs to the task',
        'We reviewed pose estimation and grasp detection as different technical routes. FoundationPose supports a few-shot model-free setup and shares downstream estimation modules with its model-based setup. MegaPose is a relevant render-and-compare alternative requiring an object model at inference. GraspNet addresses general grasp detection, which could improve pickup but does not alone specify our assembly target. Only the selected pipeline and internal variants were executed. We make no empirical ranking against these external methods.',
        'Wen et al., CVPR 2024; Labbé et al., arXiv:2212.06870; Fang et al., CVPR 2020')
    table(s,['Candidate','Task fit','Project decision'],[['FoundationPose','Novel-object 6D pose + tracking','Selected; RGB-D reference route'],['MegaPose','CAD + object region → 6D pose','Reviewed; not experimentally compared'],['GraspNet','General grasp candidates','Reviewed; future pickup alternative'],['Depth / color geometry','Foreground and coarse geometry','Depth mask selected; not full pose']],height=4.25,size=20)

    s=slide('Why MuJoCo and a Python integration?',
        'MuJoCo lets us retain the existing articulated robot, gripper and contact model while adding camera observations and reproducible trajectories. PyBullet, Gazebo and Isaac Sim are reasonable alternatives with different integration ecosystems, but changing simulator would require revalidating the same gripper and release behavior. This is an integration decision, not a cross-simulator performance result. OpenCV handles image calibration and segmentation; NumPy and SciPy support coordinate estimation and motion calculations.',
        'Todorov et al., IROS 2012; official MuJoCo, PyBullet, Gazebo and Isaac Sim documentation')
    bullets(s,['Reuse the validated UR5e / Robotiq workcell and contact acceptance','Render RGB-D and replay saved physical states','Keep camera, vision and controller interfaces inspectable','Alternatives reviewed; no simulator accuracy or speed ranking','Limit: trajectory templates and checked IK, not global planning'])

    s=slide('Task 2 / Image-based camera intrinsics',
        'We estimate the manipulation cameras from rendered checkerboard images. Simulator intrinsics are reference values used only after estimation. For the wrist camera, 24 valid training views estimate K and eight independent views validate reprojection. All rejected images are retained. Since this virtual camera is a known distortion-free pinhole sensor, distortion coefficients are fixed to zero. The very small pixel residual is specific to this synthetic setting and is not a claim about real camera calibration.',
        'Zhang, IEEE TPAMI 2000; docs/results/wrist-calibration-v1')
    picture(s,ROOT/'docs/results/wrist-calibration-v1/examples/intrinsic_train.jpg',.65,1.4,7.2,4.9)
    text(s,'Wrist: 24 train / 8 validation\n0.02177 px validation RMSE\n113 acquired images retained\n66 accepted across all splits',8.15,1.8,4.45,4.3,23)

    s=slide('Task 3 / Estimate the wrist-to-gripper transform',
        'The board remains stationary while the robot takes multiple static configurations. Image PnP estimates camera-to-board pose, and FK provides gripper motion. We solve AX equals XB and refine only on training images. Validation freezes K, the hand-eye transform X, and board pose Y. It does not refit the board on each validation image. The translation error is about 0.852 millimeters and rotation error 0.0227 degrees against simulator truth, accessed after estimation.',
        'OpenCV hand-eye conventions; docs/CALIBRATION_LOCALIZATION.md')
    text(s,'Gᵢ X Cᵢ = Y    →    AX = XB',.85,1.5,11.6,.8,32,TEAL,True)
    bullets(s,['24 valid training views; 10 independent hand-eye validation views','Estimated hand-eye error: 0.852 mm / 0.0227°','Frozen-chain validation: 0.05497 px','Runtime: world_T_gripper(FK) × gripper_T_camera(estimated)'],y=2.65,size=25)

    s=slide('Task 4 / Independent localization evaluation',
        'The localization audit has ten paired scene seeds and five conditions, with four object queries in each scene. That is fifty scene observations and two hundred queries, not fifty manipulation trials. Predictions are saved before simulator segmentation is rendered for scoring. Foreground regions are associated with known pickup stations, so this is not general object-class recognition. Every object-condition group has only ten observations; the report includes Wilson and scene-level bootstrap intervals.',
        'docs/results/workshop-localization-v1')
    loc=json.loads((ROOT/'docs/results/workshop-localization-v1/summary.json').read_text())
    names={'nominal':'Nominal','position_orientation':'Position + orientation','partial_occlusion':'Partial occlusion','depth_noise':'Depth noise'}
    table(s,['Condition','Mean visible-mask IoU','Scene-bootstrap 95% CI'],[[names[r['condition']],f"{r['mean_iou']:.3f}",f"{r['bootstrap95'][0]:.3f}–{r['bootstrap95'][1]:.3f}"] for r in loc['scene_level_aggregates']],height=3.4)
    text(s,'160/160 positive queries passed IoU ≥ 0.5; 0/40 absent-target false positives.\nEach object / condition: n = 10. Background-mismatch failures archived separately.',.75,5.4,11.8,1,19)

    s=slide('Task 5 / What “model-free” means here',
        'We do not give the object CAD mesh to the pose pipeline. Instead, twenty-four synthetic RGB-D reference views, masks and calibrated scan poses create an object-specific reconstruction with the official Neural Object Field implementation. FoundationPose then registers or tracks the object from task images. The scan calibration remains an ideal synthetic assumption. This route still uses references and pretrained networks, and it creates a geometric representation. It is not reference-free or training-from-scratch.',
        'Wen et al., CVPR 2024; docs/MODEL_FREE_TASKS.md')
    bullets(s,['24 reference RGB-D views + masks + scan calibration','Official Neural Object Field → reconstructed object surface','Official FoundationPose register / track → camera_T_object','Estimated task-camera transforms → robot-frame target','Ground-truth translation / rotation / ADD / ADD-S for evaluation'])

    s=slide('Task 6 / Physical release and regrasp matter',
        'The controller converts observed object geometry into task-specific grasp and placement targets. It checks planned motion, maintains joint control and monitors contact. For the spanner, we require actual finger opening and a changed grasp before hanging. Acceptance is based on released support and stable geometry, not merely the tool appearing close to its destination. The full video includes all four phases and the final wait. A successful demonstration is illustrative; the next slides evaluate all attempted trials.')
    picture(s,ROOT/'docs/media/complete-workshop-regrasp.png',.65,1.4,8.1,4.9)
    text(s,'Plan → grip → transfer\nObserve → release → regrasp\nAlign → insert / hang\nRelease → verify support',9.0,1.9,3.6,4.3,24)

    s=slide('Bonus / Three levels of visual feedback',
        'Open loop here means no execution-period visual correction. It still uses initial images, moving-target prediction, joint feedback and safety guards. Staged mode adds selected reobservations. Iterative mode adds repeated pose measurements and bounded TCP corrections before contact. This is discrete pose-based alignment, inspired by the PBVS formulation, not continuous contact control or a stability-guaranteed reproduction of the classical velocity law. All modes share the same pose estimator and acceptance criteria.',
        'Chaumette & Hutchinson, IEEE RAM 2006; docs/VISUAL_FEEDBACK.md')
    table(s,['Mode','Visual correction during manipulation'],[['Open loop','Initial acquisition / feed prediction only'],['Staged','Reobserve at selected task transitions'],['Iterative','Staged + repeated bounded 6D alignment']],height=3.3,size=22)
    text(s,'Default correction cap: 4 mm / 2° per step\nConvergence: two observations within 1.5 mm / 1.5°',.85,5.2,11.6,1.2,23,TEAL,True)

    s=slide('Experimental design: 48 paired attempts',
        'We compare three feedback modes under two conditions, with eight seeds per configuration. Every run uses the same estimated wrist calibration, control thresholds and physical acceptance. The initial-state hashes verify pairing. These seeds were used in previous development and evaluation; this is explicitly a replication rather than a fresh holdout. Failures before feedback or before perturbation remain in the denominator. We use Wilson intervals, trial-level bootstrap intervals, and paired exact tests with Holm correction.')
    bullets(s,['3 modes × 2 conditions × 8 seeds = 48 attempts','Estimated wrist calibration; fixed control and acceptance thresholds','Same initial states paired by seed; disturbance delivery logged','Wilson 95% CI; bootstrap trial means; paired exact tests + Holm','Seeds 400–407 reused; separate from historical ideal-wrist results'])

    s=slide('Whole-sequence success with uncertainty',
        'This is the main result: success means all four objects meet the final physical checks. Read both the counts and the wide confidence intervals. We include every valid attempt, including early pickup failures. The comparison does not simply measure whether the visual alignment routine can converge after it is reached; it measures the complete system. The paired differences on the next slide are more appropriate than inferring significance from overlapping marginal intervals.',
        str(results.relative_to(ROOT))+'/summary.json; Wilson 95% intervals; n = 8 per configuration')
    picture(s,results/'figures/success_rates.png',.65,1.35,12,5.1)

    no_significance=all(r['exact_mcnemar_p_holm_within_family']>=.05 for r in summary['paired_module_comparisons'])
    s=slide('Paired differences bound the conclusion',
        ('No feedback-method comparison passes the Holm-adjusted significance threshold in this experiment. This does not establish equivalence, and it does not prove that the additional loop is useless. It means the complete-sequence evidence is limited by the observed outcomes and small sample. We must report those results instead of choosing a favorable subset or treating one success video as a performance statistic.' if no_significance else 'The paired analysis compares success within the same seed. Interpret the exact adjusted tests together with the conservative confidence intervals and the narrow simulation setting. A statistically detectable comparison does not imply arbitrary-scene or real-robot generalization.'),
        str(results.relative_to(ROOT))+'/summary.json; paired comparisons; all configurations retained')
    picture(s,results/'figures/paired_differences.png',.65,1.35,12,5.1)

    s=slide('Accuracy and cost are separate measurements',
        'Pose error is evaluated at the first fixed-camera observation, providing a common comparison point. Execution error measures actual TCP tracking against the planned reference. We report inference and wall time separately, since shared resources and pauses influence throughput. This table is an overview of no-disturbance groups; the complete report contains both conditions, uncertainty and available sample counts. A shorter early-failure run is not a faster successful system.',
        'Full conditions, confidence intervals and sample counts are in the accompanying report')
    keys=['pose_initial_raw_translation_error_mm','pose_initial_raw_rotation_error_deg','tcp_tracking_translation_mm_rmse','pose_calls_per_wall_second_including_waits']
    def mean(g,key):
        v=g['metrics'].get(key);return 'N/A' if not v or v.get('mean') is None else f"{v['mean']:.2f} (n={v['n_trials']})"
    table(s,['Mode (no pulse)','Pose / mm','Pose / deg','TCP RMSE / mm','Pose calls / wall s'],[[METHOD_LABELS[g['method']]]+[mean(g,k) for k in keys] for g in summary['groups'] if g['disturbance']=='none'],height=3.1,size=19)
    text(s,'Physics: 500 Hz ≠ visual feedback frequency\nTrue alignment errors and visual residuals are recorded separately.',.85,5.15,11.7,1.15,24,TEAL,True)

    reports=[json.loads(f.read_text()) for f in sorted((results/'trials').glob('*.json'))]
    failure_counts=Counter(r.get('last_stage','Unknown') for r in reports if not r['success'])
    s=slide('Failure analysis: where the complete system stops',
        'The table includes every failed attempt, grouped by its last recorded controller stage. A stage name is a diagnostic location rather than a complete causal explanation; individual summaries preserve the actual contact or planning reason. Early pickup failures can prevent the later feedback loop from being tested. Additional reobservation cannot repair an approach that already failed. This motivates separating reachability, local alignment, and final task acceptance rather than reporting only reached-stage successes.')
    table(s,['Last recorded stage','Failed attempts'],failure_counts.most_common(),height=min(4.6,.65*(len(failure_counts)+1)),size=20)

    s=slide('Limits and the next engineering priorities',
        'Our strongest conclusion is that the complete calibrated vision-to-action chain is implemented and auditable, with quantitatively documented limits. Known pickup regions, synthetic reference calibration, ideal FK and depth, and small reused-seed samples restrict generalization. The immediate engineering priorities are pickup planning and contact reliability, segmentation under changing backgrounds, and then observation scheduling and pose bias. Broader external-estimator comparisons and real hardware would be new experiments, not conclusions from this dataset.')
    bullets(s,['Known stations and paired empty backgrounds; no arbitrary clutter claim','Ideal reference scans, FK and rigid mounts; simulation only','Small reused-seed sample; no architectural superiority assumption','Priority: pickup reliability → pose bias / occlusion → feedback timing','External pose baselines and real hardware remain future work'])

    s=slide('Deliverables and course coverage',
        'The repository contains the current technical-selection review, both camera-calibration procedures and their raw evidence, localization masks and statistics, pose and manipulation metrics, complete trial summaries, and original replay videos. The deck and speaker notes are generated from the published result files. This organization makes the six required tasks and the visual-feedback extension traceable without claiming a new algorithm. During the talk, use a short excerpt of the full video and leave the complete recording available for review.')
    bullets(s,['Task 1: literature, alternatives and selection rationale','Tasks 2–3: image-estimated intrinsics and hand-eye calibration','Tasks 4–5: localization audit and 6D pose accuracy','Task 6 + Bonus: complete manipulation and paired feedback evaluation','Editable slides, English notes, data, code, videos and limitations'])

    s=slide('References and reproducibility',
        'These references underpin the selected techniques rather than serving as external experimental baselines. Full titles and verified primary links are in the literature review. The result protocol records source and calibration hashes, software versions, seeds and commands. Each replay links to its original trajectory. This final slide can remain visible during questions; the detailed metric definitions and all failure summaries are in the repository.',
        'Full bibliographic details and primary links: docs/LITERATURE_AND_SELECTION.md')
    bullets(s,['Wen et al. — FoundationPose, CVPR 2024','Labbé et al. — MegaPose, arXiv:2212.06870, 2022','Fang et al. — GraspNet-1Billion, CVPR 2020','Zhang — Camera calibration, IEEE TPAMI, 2000','Chaumette & Hutchinson — Visual servo control I, IEEE RAM, 2006','Todorov et al. — MuJoCo, IROS 2012'],size=23)

    prs.save(output/'vision_guided_manipulation.pptx')
    (output/'speaker_notes.md').write_text('# English speaker notes\n\nTarget: approximately 12–15 minutes; play only a short video excerpt during the talk.\n\n'+'\n\n'.join(f"## {n['slide']}. {n['title']}\n\n{n['notes']}\n\nSource: {n['source']}" for n in notes)+'\n')
    (output/'slides.json').write_text(json.dumps(notes,indent=2)+'\n')
    (output/'provenance.json').write_text(json.dumps({'layout_preview':preview,'results':str(results.relative_to(ROOT)),
        'summary_sha256':hashlib.sha256((results/'summary.json').read_bytes()).hexdigest(),'image_assets_sha256':assets,
        'slides':len(prs.slides),'language':'English slides and English speaker notes','image_transform':'Aspect-preserving placement only; no recoloring or content editing'},indent=2)+'\n')
    print(json.dumps({'output':str(output),'slides':len(prs.slides),'preview':preview}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--layout-preview',action='store_true')
    a=p.parse_args();build(a.results.resolve(),a.output.resolve(),a.layout_preview)
