# English speaker notes

Target: approximately 12–15 minutes; play only a short video excerpt during the talk.

## 1. Vision-Guided Tool Manipulation

Our application is a simulated maintenance workcell. A UR5e and Robotiq gripper return a hammer, intercept and insert a screwdriver, assemble a rack, and regrasp and hang a spanner. The project integrates the complete chain from image measurements to physical manipulation. We use existing pretrained methods and focus on engineering decisions, reproducibility and critical evaluation. The main question is whether additional execution-period visual feedback improves this complete sequence.

Source: MA6216 Final Project 1 | UR5e + Robotiq 2F-85 | MuJoCo

## 2. The task requires orientation, not only position

Each phase requires a different geometric relationship. The screwdriver must align its shaft with a tilted socket. The rack must seat on its base. After the rack moves, the spanner must be observed again, released and regrasped, then aligned by its hole with the hanging pin. These constraints explain why centroid detection or color sorting alone would not demonstrate the required 6D pose use. Our final success check revisits all objects after the whole sequence finishes.

Source: Project implementation and recorded evidence

## 3. System architecture and evaluation boundary

The forward path starts with RGB-D images and estimated camera calibration. Segmentation supplies the object mask, and FoundationPose estimates the object pose relative to the camera using the reconstructed reference. Camera-to-robot transforms convert that estimate into grasp and insertion goals. IK, trajectory checks and joint control execute the motion. Reobservations close the pose-based loop. Simulator object and camera truth remain in downstream scoring; robot FK, contact guards and physical acceptance have separate roles.

Source: Project implementation and recorded evidence

## 4. Technical selection: match outputs to the task

We reviewed pose estimation and grasp detection as different technical routes. FoundationPose supports a few-shot model-free setup and shares downstream estimation modules with its model-based setup. MegaPose is a relevant render-and-compare alternative requiring an object model at inference. GraspNet addresses general grasp detection, which could improve pickup but does not alone specify our assembly target. Only the selected pipeline and internal variants were executed. We make no empirical ranking against these external methods.

Source: Wen et al., CVPR 2024; Labbé et al., arXiv:2212.06870; Fang et al., CVPR 2020

## 5. Why MuJoCo and a Python integration?

MuJoCo lets us retain the existing articulated robot, gripper and contact model while adding camera observations and reproducible trajectories. PyBullet, Gazebo and Isaac Sim are reasonable alternatives with different integration ecosystems, but changing simulator would require revalidating the same gripper and release behavior. This is an integration decision, not a cross-simulator performance result. OpenCV handles image calibration and segmentation; NumPy and SciPy support coordinate estimation and motion calculations.

Source: Todorov et al., IROS 2012; official MuJoCo, PyBullet, Gazebo and Isaac Sim documentation

## 6. Task 2 / Image-based camera intrinsics

We estimate the manipulation cameras from rendered checkerboard images. Simulator intrinsics are reference values used only after estimation. For the wrist camera, 24 valid training views estimate K and eight independent views validate reprojection. All rejected images are retained. Since this virtual camera is a known distortion-free pinhole sensor, distortion coefficients are fixed to zero. The very small pixel residual is specific to this synthetic setting and is not a claim about real camera calibration.

Source: Zhang, IEEE TPAMI 2000; docs/results/wrist-calibration-v1

## 7. Task 3 / Estimate the wrist-to-gripper transform

The board remains stationary while the robot takes multiple static configurations. Image PnP estimates camera-to-board pose, and FK provides gripper motion. We solve AX equals XB and refine only on training images. Validation freezes K, the hand-eye transform X, and board pose Y. It does not refit the board on each validation image. The translation error is about 0.852 millimeters and rotation error 0.0227 degrees against simulator truth, accessed after estimation.

Source: OpenCV hand-eye conventions; docs/CALIBRATION_LOCALIZATION.md

## 8. Task 4 / Independent localization evaluation

The localization audit has ten paired scene seeds and five conditions, with four object queries in each scene. That is fifty scene observations and two hundred queries, not fifty manipulation trials. Predictions are saved before simulator segmentation is rendered for scoring. Foreground regions are associated with known pickup stations, so this is not general object-class recognition. Every object-condition group has only ten observations; the report includes Wilson and scene-level bootstrap intervals.

Source: docs/results/workshop-localization-v1

## 9. Task 5 / What “model-free” means here

We do not give the object CAD mesh to the pose pipeline. Instead, twenty-four synthetic RGB-D reference views, masks and calibrated scan poses create an object-specific reconstruction with the official Neural Object Field implementation. FoundationPose then registers or tracks the object from task images. The scan calibration remains an ideal synthetic assumption. This route still uses references and pretrained networks, and it creates a geometric representation. It is not reference-free or training-from-scratch.

Source: Wen et al., CVPR 2024; docs/MODEL_FREE_TASKS.md

## 10. Task 6 / Physical release and regrasp matter

The controller converts observed object geometry into task-specific grasp and placement targets. It checks planned motion, maintains joint control and monitors contact. For the spanner, we require actual finger opening and a changed grasp before hanging. Acceptance is based on released support and stable geometry, not merely the tool appearing close to its destination. The full video includes all four phases and the final wait. A successful demonstration is illustrative; the next slides evaluate all attempted trials.

Source: Project implementation and recorded evidence

## 11. Bonus / Three levels of visual feedback

Open loop here means no execution-period visual correction. It still uses initial images, moving-target prediction, joint feedback and safety guards. Staged mode adds selected reobservations. Iterative mode adds repeated pose measurements and bounded TCP corrections before contact. This is discrete pose-based alignment, inspired by the PBVS formulation, not continuous contact control or a stability-guaranteed reproduction of the classical velocity law. All modes share the same pose estimator and acceptance criteria.

Source: Chaumette & Hutchinson, IEEE RAM 2006; docs/VISUAL_FEEDBACK.md

## 12. Experimental design: 48 paired attempts

We compare three feedback modes under two conditions, with eight seeds per configuration. Every run uses the same estimated wrist calibration, control thresholds and physical acceptance. The initial-state hashes verify pairing. These seeds were used in previous development and evaluation; this is explicitly a replication rather than a fresh holdout. Failures before feedback or before perturbation remain in the denominator. We use Wilson intervals, trial-level bootstrap intervals, and paired exact tests with Holm correction.

Source: Project implementation and recorded evidence

## 13. Whole-sequence success with uncertainty

This is the main result: success means all four objects meet the final physical checks. Read both the counts and the wide confidence intervals. We include every valid attempt, including early pickup failures. The comparison does not simply measure whether the visual alignment routine can converge after it is reached; it measures the complete system. The paired differences on the next slide are more appropriate than inferring significance from overlapping marginal intervals.

Source: docs/results/visual-feedback-calibrated-v1/summary.json; Wilson 95% intervals; n = 8 per configuration

## 14. Paired differences bound the conclusion

No feedback-method comparison passes the Holm-adjusted significance threshold in this experiment. This does not establish equivalence, and it does not prove that the additional loop is useless. It means the complete-sequence evidence is limited by the observed outcomes and small sample. We must report those results instead of choosing a favorable subset or treating one success video as a performance statistic.

Source: docs/results/visual-feedback-calibrated-v1/summary.json; paired comparisons; all configurations retained

## 15. Accuracy and cost are separate measurements

Pose error is evaluated at the first fixed-camera observation, providing a common comparison point. Execution error measures actual TCP tracking against the planned reference. We report inference and wall time separately, since shared resources and pauses influence throughput. This table is an overview of no-disturbance groups; the complete report contains both conditions, uncertainty and available sample counts. A shorter early-failure run is not a faster successful system.

Source: Full conditions, confidence intervals and sample counts are in the accompanying report

## 16. Failure analysis: where the complete system stops

The table includes every failed attempt, grouped by its last recorded controller stage. A stage name is a diagnostic location rather than a complete causal explanation; individual summaries preserve the actual contact or planning reason. Early pickup failures can prevent the later feedback loop from being tested. Additional reobservation cannot repair an approach that already failed. This motivates separating reachability, local alignment, and final task acceptance rather than reporting only reached-stage successes.

Source: Project implementation and recorded evidence

## 17. Limits and the next engineering priorities

Our strongest conclusion is that the complete calibrated vision-to-action chain is implemented and auditable, with quantitatively documented limits. Known pickup regions, synthetic reference calibration, ideal FK and depth, and small reused-seed samples restrict generalization. The immediate engineering priorities are pickup planning and contact reliability, segmentation under changing backgrounds, and then observation scheduling and pose bias. Broader external-estimator comparisons and real hardware would be new experiments, not conclusions from this dataset.

Source: Project implementation and recorded evidence

## 18. Deliverables and course coverage

The repository contains the current technical-selection review, both camera-calibration procedures and their raw evidence, localization masks and statistics, pose and manipulation metrics, complete trial summaries, and original replay videos. The deck and speaker notes are generated from the published result files. This organization makes the six required tasks and the visual-feedback extension traceable without claiming a new algorithm. During the talk, use a short excerpt of the full video and leave the complete recording available for review.

Source: Project implementation and recorded evidence

## 19. References and reproducibility

These references underpin the selected techniques rather than serving as external experimental baselines. Full titles and verified primary links are in the literature review. The result protocol records source and calibration hashes, software versions, seeds and commands. Each replay links to its original trajectory. This final slide can remain visible during questions; the detailed metric definitions and all failure summaries are in the repository.

Source: Full bibliographic details and primary links: docs/LITERATURE_AND_SELECTION.md
