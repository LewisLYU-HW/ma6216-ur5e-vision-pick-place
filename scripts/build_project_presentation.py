"""Build the English, runtime-image-led project presentation from archived evidence."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
BG, WHITE, MUTED, TEAL, AMBER, RED = '101C29', 'F4F7FA', 'B4C5D4', '52DBC3', 'FFD17C', 'FF9F91'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(results, output, preview=False):
    if preview:
        raise ValueError('This evidence deck uses final published results only')
    summary = json.loads((results / 'summary.json').read_text())
    assert summary['complete'] and summary['n_trials'] == 48
    assert summary['calibration']['wrist_hand_eye']['measured_error']
    output.mkdir(parents=True, exist_ok=True)
    frames = ROOT / 'docs/presentation/frames'
    manifest = json.loads((frames / 'manifest.json').read_text())
    prs = Presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    notes, assets = [], {}

    def text(s, value, x, y, w, h, size=22, color=WHITE, bold=False):
        z = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = z.text_frame; tf.word_wrap = True
        tf.margin_left = tf.margin_right = 0
        tf.margin_top = tf.margin_bottom = 0
        for i, line in enumerate(value.split('\n')):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line; p.font.name = 'Aptos'; p.font.size = Pt(size)
            p.font.bold = bold; p.font.color.rgb = RGBColor.from_string(color)
            p.space_after = Pt(8)
        return z

    def box(s, x, y, w, h, fill):
        z = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        z.fill.solid(); z.fill.fore_color.rgb = RGBColor.from_string(fill); z.line.fill.background()
        return z

    def slide(title, section, note, source='Final estimated-calibration evaluation | original trial frames'):
        s = prs.slides.add_slide(prs.slide_layouts[6]); s.background.fill.solid()
        s.background.fill.fore_color.rgb = RGBColor.from_string(BG)
        box(s, .45, .38, .07, .68, TEAL)
        text(s, section.upper(), .68, .32, 11.8, .25, 11, TEAL, True)
        text(s, title, .68, .68, 12.05, .6, 29, WHITE, True)
        text(s, source, .5, 7.08, 11.9, .25, 10, MUTED)
        text(s, f'{len(prs.slides):02}', 12.4, 7.05, .5, .28, 12, TEAL, True)
        s.notes_slide.notes_text_frame.text = note + '\n\nEvidence: ' + source
        notes.append({'slide': len(prs.slides), 'title': title, 'section': section,
                      'notes': note, 'source': source, 'images': []})
        return s

    def picture(s, path, x, y, w, h, crop=None):
        path = Path(path); im = Image.open(path); iw, ih = im.size
        # Crops use PowerPoint source-image crop properties; originals remain embedded.
        if crop:
            l,t,r,b = crop; ratio = (r-l)/(b-t)
        else:
            ratio = iw/ih
        dw, dh = min(w, h*ratio), min(h, w/ratio)
        z=s.shapes.add_picture(str(path), Inches(x+(w-dw)/2), Inches(y+(h-dh)/2),
                              width=Inches(dw), height=Inches(dh))
        if crop:
            z.crop_left=l/iw; z.crop_top=t/ih; z.crop_right=1-r/iw; z.crop_bottom=1-b/ih
        rel=str(path.relative_to(ROOT)); assets[rel]=sha(path)
        notes[-1]['images'].append({'path':rel,'crop_xyxy':crop})
        return z

    def frame(s, key, x, y, w, h, label=None):
        picture(s, frames/(key+'.jpg'), x,y,w,h)
        m=manifest[key]
        if label:
            text(s, label, x, y-.34,w,.28,15,TEAL,True)
        text(s, f"{m['view'].upper()}  /  VIDEO {m['playback_seconds']:.2f} s",x,y+h+.07,w,.25,11,MUTED)

    def takeaway(s, value, detail=None):
        box(s,.5,6.28,12.33,.045,TEAL)
        text(s,value,.65,6.42,12.05,.42,21,WHITE,True)
        if detail:
            text(s,detail,.65,5.88,12.05,.32,14,MUTED)

    def pair(title, section, keys, labels, claim, note, source=None):
        s=slide(title,section,note,source or 'Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps')
        for i,(key,label) in enumerate(zip(keys,labels)):
            frame(s,key,.5+6.26*i,1.8,6.07,4.13,label)
        takeaway(s,claim)
        return s

    def gallery(s, items):
        for i,(p,label,crop) in enumerate(items):
            x=.5+(i%2)*6.26; y=1.52+(i//2)*2.34
            picture(s,p,x,y,6.07,2.02,crop)
            text(s,label,x,y+2.03,6.07,.26,13,TEAL,True)

    s=slide('From visual observations to physical tool handling','MA6216 / Final Project 1',
        'This is our simulated maintenance workcell, built on a UR5e and Robotiq gripper in MuJoCo. The images throughout this talk are captured from actual recorded simulation runs. We return a hammer, intercept and insert a screwdriver, install a rack, and regrasp and hang a spanner. The engineering contribution is the complete calibrated vision-to-action chain, with reproducible successes and failures. It is not a newly trained neural algorithm.')
    frame(s,'final_overview',.5,1.55,8.15,4.25)
    frame(s,'final_wrist',8.85,1.55,3.98,2.75)
    text(s,'4 tools\n6D object poses\nPhysical release + support',8.9,4.65,3.8,1.35,20,TEAL,True)
    takeaway(s,'Vision-Guided Robotic Manipulation')

    pair('One continuous scene: before and after','Application',
         ['initial_overview','final_overview'],['START / tools at their pickup stations','FINISH / all four final checks pass'],
         'The task ends after release and stability checks.',
         'Both images come from the same successful original trial. The start image shows the tools at their pickup stations. The final image shows the completed workcell after the entire sequence, rather than four successes assembled from separate runs. The main replay lasts 195.88 seconds of simulation playback. That duration excludes wall-clock inference and planning waits and must not be interpreted as real-time robotic throughput.')

    s=slide('Four operations that depend on orientation','Task geometry',
        'The operations have different geometric constraints. Hammer return requires a supported placement. The moving screwdriver must be caught and its shaft aligned with a tilted socket. The rack must seat on its base and then be localized again. The spanner must change grasp and align its hole with a pin. A position centroid alone does not specify these insertion and hanging relationships.')
    gallery(s,[(frames/'hammer_park_wrist.jpg','01  Return the hammer',None),
               (frames/'driver_insert_wrist.jpg','02  Insert the tilted screwdriver',None),
               (frames/'rack_insert_wrist.jpg','03  Install the independent rack',None),
               (frames/'hang_thread_wrist.jpg','04  Regrasp and thread the spanner',None)])
    takeaway(s,'Position locates the tool. Orientation makes the operation possible.')

    s=slide('An image-to-action chain you can inspect','System architecture',
        'The runtime path begins with RGB-D images and estimated calibration. Depth foreground segmentation supplies the object mask. FoundationPose estimates camera-frame object pose from reconstructed references, and the calibrated transform converts this into robot targets. Motion planning and joint control execute the target; later images permit correction. Simulator object truth is used downstream for scoring, not as the commanded object pose. Robot FK and contact guards have distinct roles.')
    for i,(key,label) in enumerate([('initial_overview','RGB-D observation'),('driver_align_wrist','6D pose in the wrist view'),('final_wrist','Released physical outcome')]):
        frame(s,key,.5+i*4.18,1.85,3.97,2.71,label)
    text(s,'RGB-D  →  mask  →  camera_T_object  →  robot target  →  control',.65,5.02,12,.5,24,TEAL,True)
    text(s,'Reobserve → bounded correction     |     Simulation truth → evaluation only',.65,5.63,12,.4,19,MUTED)
    takeaway(s,'Image estimates guide the robot; independent checks score the result.')

    s=slide('Technical choices follow the manipulation task','Task 1 / Selection',
        'We selected FoundationPose because it supports object pose estimation from few-shot reconstructed references. MegaPose is a relevant model-based alternative; GraspNet predicts grasps rather than the object pose needed for assembly. These alternatives were reviewed, not experimentally ranked. MuJoCo preserves the existing articulated robot and contact model; OpenCV supports calibration and image processing. The model-free route still uses object-specific RGB-D references, a reconstructed representation and pretrained networks.',
        'Wen et al. 2024; Labbé et al. 2022; Fang et al. 2020; Todorov et al. 2012 | literature review in repository')
    frame(s,'regrasp_lift_wrist',.5,1.6,6.07,4.35)
    text(s,'FoundationPose\n6D pose from reconstructed RGB-D references',7,1.65,5.7,1.1,23,TEAL,True)
    text(s,'MegaPose / GraspNet\nReviewed pose and grasp alternatives; not external experimental baselines',7,3.05,5.7,1.55,21)
    text(s,'MuJoCo + OpenCV\nReuse contact dynamics; estimate cameras from images',7,4.85,5.7,1.1,21)
    takeaway(s,'Model-free here does not mean reference-free.')

    s=slide('Calibrate from rendered checkerboard pixels','Task 2 / Camera intrinsics',
        'The manipulation camera intrinsics are estimated from checkerboard detections. For the wrist camera, 24 valid training images estimate K and eight held-out images test reprojection. Simulator intrinsics are used only for validation. Distortion is fixed to zero for the known synthetic pinhole camera. The reported 0.02177-pixel value is the held-out mean RMSE; it is specific to this ideal image-formation model and is not a claim about a real camera.',
        'Actual calibration captures | Zhang 2000 | docs/results/wrist-calibration-v1')
    picture(s,ROOT/'docs/results/wrist-calibration-v1/examples/intrinsic_train.jpg',.5,1.5,6.07,4.58)
    picture(s,ROOT/'docs/results/wrist-calibration-v1/data/images/0014.png',6.76,1.5,6.07,4.58)
    takeaway(s,'24 training views + 8 held-out views  |  0.02177 px validation RMSE')

    s=slide('Estimate the camera–gripper transform','Task 3 / Hand–eye calibration',
        'The board remains fixed while the robot presents multiple wrist configurations. Image PnP gives camera-to-board pose and robot FK gives gripper motion. We solve AX equals XB and refine only on training images. The validation freezes the intrinsics, hand-eye transform and board pose. Against simulation truth, the estimated wrist transform has 0.852-millimeter translation error and 0.0227-degree rotation error. Runtime multiplies robot FK by the estimated hand-eye transform.',
        'Actual calibration captures | OpenCV AX=XB conventions | 24 training / 10 held-out views')
    picture(s,ROOT/'docs/results/wrist-calibration-v1/data/images/0079.png',.5,1.5,6.07,4.58)
    picture(s,ROOT/'docs/results/wrist-calibration-v1/examples/hand_eye_validation.jpg',6.76,1.5,6.07,4.58)
    takeaway(s,'AX = XB  |  Estimated hand–eye error: 0.852 mm / 0.0227°')

    s=slide('What the foreground detector actually sees','Task 4 / Localization',
        'These are saved prediction-versus-label overlays for all four tools in one nominal scene. Green is correctly predicted foreground, red is extra foreground, and blue is missed visible target. The detector relies on depth background subtraction and known pickup regions, not tool color. The audit uses fifty scenes and two hundred queries. That is a perception experiment, not two hundred independent robot runs. Each tool-condition cell has ten examples.',
        'Localization audit | nominal seed 500 | green: overlap; red: extra; blue: missed | cropped original overlays')
    names=['hammer','screwdriver','rack_frame','spanner']
    gallery(s,[(ROOT/f'docs/results/workshop-localization-v1/examples/nominal__{n}__sample__500.jpg',n.replace('_',' ').title(),(390,320,940,680)) for n in names])
    takeaway(s,'50 scenes / 200 queries; predictions saved before ground-truth scoring.')

    s=slide('Failure: background geometry becomes foreground','Localization failure diagnosis',
        'This image is from the separate background-mismatch diagnosis. The target rack is absent, but the mismatched background geometry produces a false foreground region. The right panel enlarges the same original image; it does not add a synthetic failure. This development diagnosis is kept separate from the formal fifty-scene audit, which uses per-scene matched empty backgrounds. It illustrates a deployment limitation of background subtraction.',
        'Separate development diagnosis | target absent / rack frame / seed 500 | not part of final 48 manipulation trials')
    p=ROOT/'docs/results/workshop-localization-v1/background_mismatch_diagnostic/target_absent__rack_frame__failure__500.jpg'
    picture(s,p,.5,1.55,6.07,4.5)
    picture(s,p,6.76,1.55,6.07,4.5,(470,350,900,680))
    takeaway(s,'The red region is a false positive, even though no rack target is present.')

    pair('6D pose must preserve the shaft and the hole axes','Task 5 / Pose estimation',
         ['driver_align_wrist','hang_align_wrist'],['SHAFT → tilted socket','HOLE AXIS → hanging pin'],
         'The wrist estimates connect tool geometry to the required final pose.',
         'These original wrist views show the screwdriver and spanner near alignment. The archived pose overlays belong to the recorded estimate, not a new drawing of simulator truth. The object references are reconstructed from calibrated RGB-D scans rather than supplying tool CAD to the estimator. Translation, rotation, ADD and ADD-S are evaluated separately against simulation truth. Reference-scan calibration remains an ideal synthetic assumption.')

    pair('Return the hammer before the next tool arrives','Operation 01 / Hammer',
         ['hammer_lift_overview','hammer_released_overview'],['13.60 s / lift from the workbench','25.00 s / release into the tray'],
         'Grasp → transfer → release → check stable support.',
         'The first operation clears the workbench and returns the hammer. Compare the lifted tool on the left with the released placement on the right. The controller uses an image-estimated target, checked motion and joint control. The final acceptance requires released support, not simply reaching a Cartesian waypoint. Hammer approach planning is also one of the failure categories in the complete evaluation.')

    pair('Intercept a tool that is already moving','Operation 02 / Moving screwdriver',
         ['feed_overview','driver_lift_wrist'],['29.00 s / observe the moving feed','43.40 s / tool lifted in the gripper'],
         'Prediction and pickup contact both matter before alignment begins.',
         'The screwdriver moves through the feed stage before the robot approaches it. Initial observation and moving-target prediction are present in every feedback mode, including the open-loop comparison. The wrist image on the right is captured after pickup. Many complete-task failures occur at this earlier contact stage, before the later insertion feedback can be exercised. Therefore we retain early failures in the final denominator.')

    pair('Rotate the shaft, then insert into a tilted socket','Operation 02 / Insertion',
         ['driver_orient_wrist','driver_release_wrist'],['50.00 s / reorient the held screwdriver','67.00 s / release after insertion'],
         'Align the tool axis before insertion.',
         'The wrist sequence makes the orientation requirement visible. The robot first reorients the held screwdriver, aligns it with the socket, and inserts in guarded increments. It then opens the fingers and withdraws. The two snapshots are selected from the same successful continuous run. They are illustrative states; the archived motion and acceptance logs provide the evidence that the operation passed.')

    pair('Install the rack as a separate physical object','Operation 03 / Rack assembly',
         ['rack_lift_overview','rack_insert_wrist'],['91.00 s / lift the independent frame','112.00 s / seat the frame on its base'],
         'Install and release the rack before using it as a fixture.',
         'The rack starts as an independent object in the workcell. The robot lifts it, rotates and aligns it, then inserts it into the base. This adds a dependency to the final spanner task: the hanging fixture may not remain exactly where an earlier observation predicted. The rack is released and its seating is checked before the controller proceeds.')

    pair('Release the rack, then observe the assembled scene','Operation 03 / Relocalization',
         ['rack_release_wrist','rack_done_overview'],['118.00 s / gripper withdrawal','134.40 s / assembled-rack check'],
         'Reobserve the rack after physical seating.',
         'The left image shows withdrawal after rack release; the right is the assembled workcell just before transition to the spanner. In staged and iterative feedback modes, a new observation updates the fixture relationship for the next operation. This step addresses changes caused by contact and seating. The final workcell still contains the previously returned hammer and inserted screwdriver.')

    pair('Put the spanner down and actually open the fingers','Operation 04 / Physical regrasp',
         ['regrasp_place_wrist','regrasp_clear_wrist'],['147.00 s / supported placement','150.40 s / gripper clear of the tool'],
         'The change of grasp includes an explicit release and a new observation.',
         'This pair shows the first half of the regrasp. The spanner is placed on its support and the gripper releases and retreats. The next grasp is based on a new observation rather than assuming the tool stayed exactly at its commanded pose. The images show the mechanism; the original trial also records the physical regrasp flag and contact-based acceptance. This is not a teleportation or a hidden attachment change.')

    pair('Regrasp so the hole can reach the hanging pin','Operation 04 / New grasp',
         ['regrasp_close_wrist','regrasp_lift_wrist'],['155.60 s / close at the new grasp','158.20 s / lift and inspect'],
         'The second grasp makes the hole accessible for the final approach.',
         'After the released spanner is observed again, the fingers approach and close at the new grasp. The robot lifts and inspects the tool before turning toward the rack. The hole must remain accessible while the gripper maintains bilateral contact. One separate evaluated failure loses bilateral grasp during the later approach; extra visual measurements do not automatically repair a physically unstable hold.')

    pair('Thread the hole, release, and leave the tool hanging','Operation 04 / Final placement',
         ['hang_thread_wrist','final_wrist'],['179.00 s / thread the eye onto the pin','195.00 s / released final state'],
         'Success requires support by the rack after the gripper withdraws.',
         'The large wrist views show the eye passing over the pin and the final released state. The controller seats the eye, opens the fingers, withdraws, and waits for stability. The selected trial passes the final checks for all four objects. A separate diagnostic audits saved motion states and adds thirty seconds of passive simulation; that diagnostic does not replace or improve the original trial score.')

    pair('Visual feedback can trigger a real corrective motion','Bonus / Correction example',
         ['pulse_before','pulse_after'],['BEFORE / visual angular residual 1.60°','AFTER / visual angular residual 0.74°'],
         'One logged correction; a separate integration example.',
         'This example comes from the separately archived estimated-calibration integration run with an alignment impulse. The spanner loop records one correction. The measured angular residual falls from 1.60 to 0.74 degrees over the observations. The visual change is small at this scale, so the residual values are taken from the original log, not inferred from pixels. These are estimated residuals, not true geometric errors. This integration example is not counted as an additional trial in the final forty-eight.',
         'Separate calibration integration / iterative / alignment impulse / seed 400 | original log residuals')

    pair('Same initial seed, different insertion outcomes','Paired evidence / Seed 400',
         ['open_failure_wrist','driver_done_wrist'],['OPEN LOOP / insertion guard stops the run','ITERATIVE / driver released and stable'],
         'A matched example, not a claim of overall superiority.',
         'These trials share seed four hundred and the same initial physical scene. The open-loop run stops under the screwdriver insertion contact guard. The iterative run reaches a released screwdriver and eventually completes the whole task. The pictures are aligned by task outcome rather than identical playback time. The failure reason is taken from the recorded guard, not guessed from a rendered contact. A single favorable pair is not a statistical comparison.',
         'Final 48 trials | open_loop vs iterative / no disturbance / seed 400 | different playback times')

    pair('Early pickup failure defeats both feedback modes','Failure evidence / Seed 401',
         ['staged_failure_wrist','iter_failure_wrist'],['STAGED / stops at gripper closure','ITERATIVE / also stops at gripper closure'],
         'Both stop before the later visual alignment loop can help.',
         'This matched pair deliberately retains a failure of the iterative method itself. Both runs stop during moving-screwdriver pickup when an unexpected robot contact is detected at gripper closure. This is a safety-guard failure, not necessarily a visually dramatic dropped object. The same visible pose can hide a contact violation; the cause therefore comes from the log. Early reachability limits the whole-sequence benefit of downstream feedback.',
         'Final 48 trials | staged vs iterative / no disturbance / seed 401 | original contact-guard failures')

    s=slide('All attempts count, including the failed pickups','Quantitative context / 48 attempts',
        'We retain forty-eight attempts: three feedback modes, two disturbance conditions and eight reused seeds in each cell. Open loop succeeds zero of eight in both conditions; staged feedback three of eight without and two of eight with disturbance; iterative feedback three of eight in both. All four Holm-adjusted method comparisons have p equal to one. This does not establish superiority or equivalence. The seeds are reused, so this is a paired replication, not a fresh holdout.')
    picture(s,results/'figures/success_rates.png',.5,1.55,7.2,4.55)
    frame(s,'final_wrist',8,1.7,4.8,3.27)
    text(s,'One success image cannot\nreplace all 48 outcomes.',8,5.25,4.8,.75,22,TEAL,True)
    takeaway(s,'Wide uncertainty; no statistically established advantage in this sample.')

    s=slide('What the failures tell us to improve next','Engineering conclusions',
        'The complete calibrated chain is implemented and inspectable, but overall success remains limited. Twenty-four failures stop at moving-pickup gripper closure, six at hammer approach settling, six during open-loop driver retraction, and one after loss of bilateral spanner grasp. Priorities are pickup planning and contact reliability, then pose bias, visibility and feedback scheduling. Known pickup regions, ideal reference scanning and FK, and a small reused-seed sample limit generalization.',
        'Final failure summaries + separate localization diagnosis | no external estimator performance ranking')
    frame(s,'iter_failure_wrist',.5,1.7,6.07,4.13,'PICKUP / the dominant bottleneck')
    text(s,'24 / pickup-contact stops\n6 / hammer approach stops\n6 / open-loop insertion stops\n1 / bilateral-grasp loss',7,1.9,5.6,2.5,24,AMBER,True)
    text(s,'Next: reliable contact → robust visibility\n→ broader unseen-scene evaluation',7,4.85,5.6,1,21)
    takeaway(s,'Reliable pickup is required before downstream feedback can help.')

    pair('A complete, auditable vision-guided workcell','Conclusion / Discussion',
         ['initial_overview','final_wrist'],['From calibrated observations','To released physical manipulation'],
         'Repository evidence: code, calibration, masks, trials and original videos.',
         'The project integrates all six course tasks and the visual-feedback extension. The evidence package links independent camera estimates, localization masks, object pose estimates, motion execution and physical acceptance. Our main lesson is that a successful visual alignment module is only one part of a reliable manipulation system. We present the full sequence and its failures, with realistic boundaries on what these simulation experiments demonstrate. The remaining slides are backup material for questions.')

    s=slide('Accuracy, timing and experimental units','Appendix / Metrics',
        'These values separate camera, pose, execution and timing measurements. The initial fixed-camera observations are shared across modes: mean pose translation and rotation errors are 2.60 millimeters and 1.44 degrees, with ADD 3.17 millimeters and ADD-S 2.29 millimeters. Execution and frequency metrics are reported with sample counts in the full report. Physics step rate is not visual inference frequency, and wall time includes shared-resource waits. Calibration images, perception queries and robot attempts are different experimental units.',
        'Full uncertainty and sample counts: docs/results/visual-feedback-calibrated-v1/README.md')
    frame(s,'driver_align_wrist',.5,1.65,6.07,4.13)
    text(s,'Initial pose: 2.60 mm / 1.44°\nADD / ADD-S: 3.17 / 2.29 mm\nHand–eye: 0.852 mm / 0.0227°',7,1.7,5.65,2.1,23,TEAL,True)
    text(s,'48 robot attempts ≠ 200 mask queries\n500 Hz physics ≠ visual update rate\nTracking error ≠ final placement error',7,4.15,5.65,1.6,21)
    takeaway(s,'Do not mix measurement units, denominators or timing definitions.')

    s=slide('Methods and primary references','Appendix / Reading',
        'FoundationPose provides the selected object-pose method; Zhang and OpenCV support calibration; Chaumette and Hutchinson provide the visual-servoing framework. MuJoCo supplies the simulation platform. MegaPose and GraspNet are reviewed alternatives, not executed external baselines. Full citations and verified primary links are in the literature review and bibliography. Every screenshot also has a source-video hash, timestamp and crop record in the presentation image manifest.',
        'docs/LITERATURE_AND_SELECTION.md | docs/references.bib | docs/presentation/frames/manifest.json')
    frame(s,'final_overview',.5,1.65,5.65,3.85)
    text(s,'Wen et al. — FoundationPose, CVPR 2024\nZhang — Camera calibration, TPAMI 2000\nOpenCV — Hand–eye calibration conventions\nChaumette & Hutchinson — Visual servoing, 2006\nTodorov et al. — MuJoCo, IROS 2012\nLabbé et al. — MegaPose, 2022\nFang et al. — GraspNet-1Billion, CVPR 2020',6.6,1.65,6.2,4.45,19)
    takeaway(s,'Published methods + independent integration + traceable evidence.')

    prs.save(output/'vision_guided_manipulation.pptx')
    (output/'speaker_notes.md').write_text('# English speaker notes\n\nImage-led revision. Target: 12–15 minutes for slides 1–24; slides 25–26 are backup.\n\n'+'\n\n'.join(f"## {n['slide']}. {n['title']}\n\n{n['notes']}\n\nSource: {n['source']}" for n in notes)+'\n')
    (output/'slides.json').write_text(json.dumps(notes,indent=2)+'\n')
    counts={'slides':len(prs.slides),'slides_with_runtime_or_calibration_images':sum(any('/figures/' not in im['path'] for im in n['images']) for n in notes),
            'image_placements':sum(len(n['images']) for n in notes),'unique_image_assets':len(assets),
            'data_chart_placements':sum('/figures/' in im['path'] for n in notes for im in n['images'])}
    (output/'provenance.json').write_text(json.dumps({'layout_preview':False,'revision':'Runtime-image-led replacement',
        'results':str(results.relative_to(ROOT)),'summary_sha256':sha(results/'summary.json'),'image_assets_sha256':assets,
        **counts,'language':'English slides and English speaker notes','image_transform':'Video camera-panel crops and explicitly recorded detail crops; no generated imagery, recoloring or altered physical outcomes',
        'frame_manifest':'frames/manifest.json','frame_manifest_sha256':sha(frames/'manifest.json')},indent=2)+'\n')
    print(json.dumps(counts))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--layout-preview',action='store_true')
    a=p.parse_args();build(a.results.resolve(),a.output.resolve(),a.layout_preview)
