# English speaker notes

Image-led revision. Target: 12–15 minutes for slides 1–24; slides 25–26 are backup.

## 1. From visual observations to physical tool handling

This is our simulated maintenance workcell, built on a UR5e and Robotiq gripper in MuJoCo. The images throughout this talk are captured from actual recorded simulation runs. We return a hammer, intercept and insert a screwdriver, install a rack, and regrasp and hang a spanner. The engineering contribution is the complete calibrated vision-to-action chain, with reproducible successes and failures. It is not a newly trained neural algorithm.

Source: Final estimated-calibration evaluation | original trial frames

## 2. One continuous scene: before and after

Both images come from the same successful original trial. The start image shows the tools at their pickup stations. The final image shows the completed workcell after the entire sequence, rather than four successes assembled from separate runs. The main replay lasts 195.88 seconds of simulation playback. That duration excludes wall-clock inference and planning waits and must not be interpreted as real-time robotic throughput.

Source: Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps

## 3. Four operations that depend on orientation

The operations have different geometric constraints. Hammer return requires a supported placement. The moving screwdriver must be caught and its shaft aligned with a tilted socket. The rack must seat on its base and then be localized again. The spanner must change grasp and align its hole with a pin. A position centroid alone does not specify these insertion and hanging relationships.

Source: Final estimated-calibration evaluation | original trial frames

## 4. An image-to-action chain you can inspect

The runtime path begins with RGB-D images and estimated calibration. Depth foreground segmentation supplies the object mask. FoundationPose estimates camera-frame object pose from reconstructed references, and the calibrated transform converts this into robot targets. Motion planning and joint control execute the target; later images permit correction. Simulator object truth is used downstream for scoring, not as the commanded object pose. Robot FK and contact guards have distinct roles.

Source: Final estimated-calibration evaluation | original trial frames

## 5. Technical choices follow the manipulation task

We selected FoundationPose because it supports object pose estimation from few-shot reconstructed references. MegaPose is a relevant model-based alternative; GraspNet predicts grasps rather than the object pose needed for assembly. These alternatives were reviewed, not experimentally ranked. MuJoCo preserves the existing articulated robot and contact model; OpenCV supports calibration and image processing. The model-free route still uses object-specific RGB-D references, a reconstructed representation and pretrained networks.

Source: Wen et al. 2024; Labbé et al. 2022; Fang et al. 2020; Todorov et al. 2012 | literature review in repository

## 6. Calibrate from rendered checkerboard pixels

The manipulation camera intrinsics are estimated from checkerboard detections. For the wrist camera, 24 valid training images estimate K and eight held-out images test reprojection. Simulator intrinsics are used only for validation. Distortion is fixed to zero for the known synthetic pinhole camera. The reported 0.02177-pixel value is the held-out mean RMSE; it is specific to this ideal image-formation model and is not a claim about a real camera.

Source: Actual calibration captures | Zhang 2000 | docs/results/wrist-calibration-v1

## 7. Estimate the camera–gripper transform

The board remains fixed while the robot presents multiple wrist configurations. Image PnP gives camera-to-board pose and robot FK gives gripper motion. We solve AX equals XB and refine only on training images. The validation freezes the intrinsics, hand-eye transform and board pose. Against simulation truth, the estimated wrist transform has 0.852-millimeter translation error and 0.0227-degree rotation error. Runtime multiplies robot FK by the estimated hand-eye transform.

Source: Actual calibration captures | OpenCV AX=XB conventions | 24 training / 10 held-out views

## 8. What the foreground detector actually sees

These are saved prediction-versus-label overlays for all four tools in one nominal scene. Green is correctly predicted foreground, red is extra foreground, and blue is missed visible target. The detector relies on depth background subtraction and known pickup regions, not tool color. The audit uses fifty scenes and two hundred queries. That is a perception experiment, not two hundred independent robot runs. Each tool-condition cell has ten examples.

Source: Localization audit | nominal seed 500 | green: overlap; red: extra; blue: missed | cropped original overlays

## 9. Failure: background geometry becomes foreground

This image is from the separate background-mismatch diagnosis. The target rack is absent, but the mismatched background geometry produces a false foreground region. The right panel enlarges the same original image; it does not add a synthetic failure. This development diagnosis is kept separate from the formal fifty-scene audit, which uses per-scene matched empty backgrounds. It illustrates a deployment limitation of background subtraction.

Source: Separate development diagnosis | target absent / rack frame / seed 500 | not part of final 48 manipulation trials

## 10. 6D pose must preserve the shaft and the hole axes

These original wrist views show the screwdriver and spanner near alignment. The archived pose overlays belong to the recorded estimate, not a new drawing of simulator truth. The object references are reconstructed from calibrated RGB-D scans rather than supplying tool CAD to the estimator. Translation, rotation, ADD and ADD-S are evaluated separately against simulation truth. Reference-scan calibration remains an ideal synthetic assumption.

Source: Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps

## 11. Return the hammer before the next tool arrives

The first operation clears the workbench and returns the hammer. Compare the lifted tool on the left with the released placement on the right. The controller uses an image-estimated target, checked motion and joint control. The final acceptance requires released support, not simply reaching a Cartesian waypoint. Hammer approach planning is also one of the failure categories in the complete evaluation.

Source: Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps

## 12. Intercept a tool that is already moving

The screwdriver moves through the feed stage before the robot approaches it. Initial observation and moving-target prediction are present in every feedback mode, including the open-loop comparison. The wrist image on the right is captured after pickup. Many complete-task failures occur at this earlier contact stage, before the later insertion feedback can be exercised. Therefore we retain early failures in the final denominator.

Source: Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps

## 13. Rotate the shaft, then insert into a tilted socket

The wrist sequence makes the orientation requirement visible. The robot first reorients the held screwdriver, aligns it with the socket, and inserts in guarded increments. It then opens the fingers and withdraws. The two snapshots are selected from the same successful continuous run. They are illustrative states; the archived motion and acceptance logs provide the evidence that the operation passed.

Source: Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps

## 14. Install the rack as a separate physical object

The rack starts as an independent object in the workcell. The robot lifts it, rotates and aligns it, then inserts it into the base. This adds a dependency to the final spanner task: the hanging fixture may not remain exactly where an earlier observation predicted. The rack is released and its seating is checked before the controller proceeds.

Source: Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps

## 15. Release the rack, then observe the assembled scene

The left image shows withdrawal after rack release; the right is the assembled workcell just before transition to the spanner. In staged and iterative feedback modes, a new observation updates the fixture relationship for the next operation. This step addresses changes caused by contact and seating. The final workcell still contains the previously returned hammer and inserted screwdriver.

Source: Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps

## 16. Put the spanner down and actually open the fingers

This pair shows the first half of the regrasp. The spanner is placed on its support and the gripper releases and retreats. The next grasp is based on a new observation rather than assuming the tool stayed exactly at its commanded pose. The images show the mechanism; the original trial also records the physical regrasp flag and contact-based acceptance. This is not a teleportation or a hidden attachment change.

Source: Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps

## 17. Regrasp so the hole can reach the hanging pin

After the released spanner is observed again, the fingers approach and close at the new grasp. The robot lifts and inspects the tool before turning toward the rack. The hole must remain accessible while the gripper maintains bilateral contact. One separate evaluated failure loses bilateral grasp during the later approach; extra visual measurements do not automatically repair a physically unstable hold.

Source: Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps

## 18. Thread the hole, release, and leave the tool hanging

The large wrist views show the eye passing over the pin and the final released state. The controller seats the eye, opens the fingers, withdraws, and waits for stability. The selected trial passes the final checks for all four objects. A separate diagnostic audits saved motion states and adds thirty seconds of passive simulation; that diagnostic does not replace or improve the original trial score.

Source: Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps

## 19. Visual feedback can trigger a real corrective motion

This example comes from the separately archived estimated-calibration integration run with an alignment impulse. The spanner loop records one correction. The measured angular residual falls from 1.60 to 0.74 degrees over the observations. The visual change is small at this scale, so the residual values are taken from the original log, not inferred from pixels. These are estimated residuals, not true geometric errors. This integration example is not counted as an additional trial in the final forty-eight.

Source: Separate calibration integration / iterative / alignment impulse / seed 400 | original log residuals

## 20. Same initial seed, different insertion outcomes

These trials share seed four hundred and the same initial physical scene. The open-loop run stops under the screwdriver insertion contact guard. The iterative run reaches a released screwdriver and eventually completes the whole task. The pictures are aligned by task outcome rather than identical playback time. The failure reason is taken from the recorded guard, not guessed from a rendered contact. A single favorable pair is not a statistical comparison.

Source: Final 48 trials | open_loop vs iterative / no disturbance / seed 400 | different playback times

## 21. Early pickup failure defeats both feedback modes

This matched pair deliberately retains a failure of the iterative method itself. Both runs stop during moving-screwdriver pickup when an unexpected robot contact is detected at gripper closure. This is a safety-guard failure, not necessarily a visually dramatic dropped object. The same visible pose can hide a contact violation; the cause therefore comes from the log. Early reachability limits the whole-sequence benefit of downstream feedback.

Source: Final 48 trials | staged vs iterative / no disturbance / seed 401 | original contact-guard failures

## 22. All attempts count, including the failed pickups

We retain forty-eight attempts: three feedback modes, two disturbance conditions and eight reused seeds in each cell. Open loop succeeds zero of eight in both conditions; staged feedback three of eight without and two of eight with disturbance; iterative feedback three of eight in both. All four Holm-adjusted method comparisons have p equal to one. This does not establish superiority or equivalence. The seeds are reused, so this is a paired replication, not a fresh holdout.

Source: Final estimated-calibration evaluation | original trial frames

## 23. What the failures tell us to improve next

The complete calibrated chain is implemented and inspectable, but overall success remains limited. Twenty-four failures stop at moving-pickup gripper closure, six at hammer approach settling, six during open-loop driver retraction, and one after loss of bilateral spanner grasp. Priorities are pickup planning and contact reliability, then pose bias, visibility and feedback scheduling. Known pickup regions, ideal reference scanning and FK, and a small reused-seed sample limit generalization.

Source: Final failure summaries + separate localization diagnosis | no external estimator performance ranking

## 24. A complete, auditable vision-guided workcell

The project integrates all six course tasks and the visual-feedback extension. The evidence package links independent camera estimates, localization masks, object pose estimates, motion execution and physical acceptance. Our main lesson is that a successful visual alignment module is only one part of a reliable manipulation system. We present the full sequence and its failures, with realistic boundaries on what these simulation experiments demonstrate. The remaining slides are backup material for questions.

Source: Final 48 trials | iterative / no disturbance / seed 400 | playback timestamps

## 25. Accuracy, timing and experimental units

These values separate camera, pose, execution and timing measurements. The initial fixed-camera observations are shared across modes: mean pose translation and rotation errors are 2.60 millimeters and 1.44 degrees, with ADD 3.17 millimeters and ADD-S 2.29 millimeters. Execution and frequency metrics are reported with sample counts in the full report. Physics step rate is not visual inference frequency, and wall time includes shared-resource waits. Calibration images, perception queries and robot attempts are different experimental units.

Source: Full uncertainty and sample counts: docs/results/visual-feedback-calibrated-v1/README.md

## 26. Methods and primary references

FoundationPose provides the selected object-pose method; Zhang and OpenCV support calibration; Chaumette and Hutchinson provide the visual-servoing framework. MuJoCo supplies the simulation platform. MegaPose and GraspNet are reviewed alternatives, not executed external baselines. Full citations and verified primary links are in the literature review and bibliography. Every screenshot also has a source-video hash, timestamp and crop record in the presentation image manifest.

Source: docs/LITERATURE_AND_SELECTION.md | docs/references.bib | docs/presentation/frames/manifest.json
