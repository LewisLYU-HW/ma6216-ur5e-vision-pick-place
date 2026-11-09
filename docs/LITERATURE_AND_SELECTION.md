# Literature review and technical selection

This review supports the current four-stage workshop application: hammer return, moving-screwdriver pickup and tilted insertion, rack assembly, and spanner release/regrasp followed by hole-over-pin hanging. The engineering requirement is an object-to-fixture transformation with both translation and orientation. A grasp point alone does not specify the insertion axis or hanging-hole alignment.

This is a targeted technical review, not a systematic review or a new algorithm contribution. Primary papers and official documentation were checked on 9 November 2026. Candidate-method comparisons below describe published capabilities and our integration decisions; only methods identified as implemented have project measurements.

## Object localization and pose estimation

| Candidate | Inputs and output | Strength and limitation for this task | Decision |
|---|---|---|---|
| Color segmentation plus RGB-D geometry | Color thresholds and depth; foreground region, centroid and principal axes | Simple for deliberately colored parts; sensitive to appearance, and principal-axis signs or symmetry can leave orientation ambiguous | Retained for historical colored-part tasks; current tools use depth background subtraction |
| Depth foreground segmentation in commissioned pickup regions | Current depth, paired empty-workcell depth and estimated camera calibration; binary target mask | Avoids assigning artificial colors to tools; assumes known stations and a matching background, and does not perform general category recognition | Implemented for current tool localization; separately evaluated for layout variation, occlusion, noise and absent targets |
| FoundationPose model-based / model-free [1] | RGB-D with an object CAD model, or reference images from which an implicit object representation is learned; object pose and tracking | Supports novel objects without retraining the pose network for each object; the model-free setup still requires object-specific references | Selected: 24 calibrated synthetic RGB-D references per tool, official Neural Object Field reconstruction, followed by the official pose estimator |
| MegaPose [2] | Object region and CAD model; coarse pose and render-and-compare refinement | Relevant novel-object pose alternative; still needs an object model at inference | Literature candidate only; not installed or evaluated as a project baseline |
| GraspNet-1Billion approach [3] | RGB-D observations and grasp annotations/evaluation; grasp candidates | Relevant to general grasp acquisition; an executable grasp is a different output from the object-to-fixture pose required for insertion | Literature candidate for improving pickup; not an external experimental comparator |

FoundationPose unifies model-based and model-free estimation/tracking using shared downstream pose modules [1]. Our use of the model-free route means that object CAD is not supplied to the reconstruction/pose pipeline. It does not mean no object-specific data, no pretrained network, or no geometric object representation after reconstruction. Simulator geometry still exists for rendering and physics. These boundaries must remain explicit in the presentation.

The project contributes observation capture, input adaptation, coordinate propagation, task features on reconstructed geometry, grasp/regrasp strategy, control integration and independent evaluation. We do not claim authorship of the pretrained FoundationPose networks. The actual implementation and limitations are documented in [MODEL_FREE_TASKS.md](MODEL_FREE_TASKS.md) and [WORKSHOP.md](WORKSHOP.md).

## Camera calibration and hand-eye calibration

Zhang's planar-pattern calibration estimates camera parameters from images of a plane at different orientations, followed by nonlinear refinement [4]. We use rendered checkerboard images and OpenCV calibration rather than directly substituting simulator intrinsics. The virtual sensor is a known distortion-free pinhole model, so distortion coefficients are fixed to zero. Independent image splits and simulator-reference errors are reported separately.

The fixed camera uses known 3D-to-image correspondences to establish its robot-installation-frame transform. For the wrist camera, OpenCV's documented hand-eye convention provides the camera-to-gripper transformation from gripper-to-base poses and target-to-camera observations [5]. Our solver uses relative motions in AX=XB, rotation-log SVD and linear translation, followed by training-only joint reprojection refinement of the hand-eye transform and stationary-board pose. This is a standard calibration formulation implemented locally, not a novel calibration algorithm.

The engineering decisions are to excite multiple rotation axes, reject visually inconsistent checkerboard detections, and freeze all estimated transforms during hand-eye validation. Simulator camera truth is read only after the estimate has been saved. Runtime propagation uses robot FK and the estimated mounting transform:

```text
Fixed camera: world_T_object = world_T_camera_estimated × camera_T_object
Wrist camera: world_T_object = world_T_gripper_FK × gripper_T_camera_estimated × camera_T_object
```

Robot FK, board dimensions and rigid mounting are ideal simulation assumptions. The reference-image scanning setup retains ideal synthetic calibration; it is separate from the independently calibrated manipulation cameras. See [calibration methods and evidence](CALIBRATION_LOCALIZATION.md).

## Manipulation and visual feedback

The visual-servo literature distinguishes image-based control, which regulates image features, from position-based control, which regulates reconstructed spatial pose [6]. We select pose-based feedback because the same 6D object and fixture representations already define tilted insertion and hanging goals. An IBVS alternative would require designing and maintaining task-specific image features and their interaction model; it was not implemented in this project.

Our controller is bounded, discrete pose-based alignment before contact, rather than a reproduction of the continuous velocity law or stability analysis in [6]. It reobserves the object, estimates the pose error, and proposes limited TCP corrections. The existing IK, collision checks, joint servo and contact guards execute or reject those corrections. Partial occlusion and bad pose updates remain failure risks; an estimated residual below threshold is not proof of a small true alignment error.

The three actual comparison modes share the initial visual acquisition, motion prediction, estimator, joint control and physical acceptance criteria:

| Mode | Execution-period visual feedback |
|---|---|
| Open loop | No post-grasp/post-release visual correction; initial vision and moving-target prediction remain enabled |
| Staged feedback | Reobservation at selected task transitions |
| Iterative feedback | Staged observations plus repeated bounded 6D corrections before contact |

These are internal feedback-module comparisons. Historical module ablations also remove or simplify parts of our own pipeline; they are not a comparison against MegaPose, GraspNet or a different external pose estimator. The experiment must report whichever method performs better, including unchanged or worse performance. See [feedback implementation](VISUAL_FEEDBACK.md).

## Simulation and software selection

| Environment / library | Relevant published capability | Project decision |
|---|---|---|
| MuJoCo [7,8] | Articulated dynamics, contacts, rendering and programmatic simulation | Selected: existing UR5e/Robotiq integration and contact-based release acceptance could be retained; repeatable state traces support independent replay |
| PyBullet [9] | Python robotics simulation interface, rendering and dynamics | Viable candidate, but would require rebuilding and revalidating the existing gripper/contact workcell; no cross-simulator benchmark was run |
| Gazebo [10] | Sensor libraries integrated with rendering and physics | Relevant for a sensor/robot software stack; this assignment does not require a ROS integration, so migration adds interfaces without testing our main question |
| Isaac Sim [11] | Robot simulation and synthetic-data workflows | Relevant for richer sensor/rendering workflows; not used, and no claim is made that MuJoCo is more accurate or faster |
| OpenCV / NumPy / SciPy | Calibration, image processing and numerical estimation/optimization | Selected for transparent camera/coordinate processing and compatibility with the existing Python pipeline |

These choices prioritize an auditable complete system on the available workstation. Offline IK and checked trajectory templates are not a general global motion planner. Contact parameters and ideal depth limit transfer to physical hardware. Wall-clock inference throughput and the 500 Hz physics step rate must not be conflated with real-time visual-control frequency.

## What the experiments can establish

Calibration experiments evaluate estimated parameters and held-out reprojection consistency. Localization experiments evaluate visible-mask quality and missed/false detections. Pose estimation is evaluated against simulation ground truth, and manipulation is judged after release using support, geometry and stability checks. These measurements answer different questions; good segmentation or pose accuracy does not guarantee a successful manipulation sequence.

The estimated-wrist 48-trial replication uses the previously exercised seeds 400–407 and is not a new unseen test set. The historical ideal-wrist evaluation and new estimated-wrist evaluation must remain separate. No success-rate conclusion should be drawn from the two seed400 integration demonstrations alone. Fixed seeds and confidence intervals improve auditability but do not establish real-world generalization.

## Verified references

The six research-paper entries are also available as [BibTeX](references.bib); official software documentation is linked below.

1. Wen, B., Yang, W., Kautz, J., and Birchfield, S. **FoundationPose: Unified 6D Pose Estimation and Tracking of Novel Objects.** CVPR, 2024, pp. 17868–17879. [Primary publication](https://openaccess.thecvf.com/content/CVPR2024/html/Wen_FoundationPose_Unified_6D_Pose_Estimation_and_Tracking_of_Novel_Objects_CVPR_2024_paper.html).
2. Labbé, Y., et al. **MegaPose: 6D Pose Estimation of Novel Objects via Render & Compare.** arXiv:2212.06870, 2022. [Primary manuscript](https://arxiv.org/abs/2212.06870).
3. Fang, H.-S., Wang, C., Gou, M., and Lu, C. **GraspNet-1Billion: A Large-Scale Benchmark for General Object Grasping.** CVPR, 2020. [Primary publication](https://openaccess.thecvf.com/content_CVPR_2020/html/Fang_GraspNet-1Billion_A_Large-Scale_Benchmark_for_General_Object_Grasping_CVPR_2020_paper.html).
4. Zhang, Z. **A Flexible New Technique for Camera Calibration.** IEEE TPAMI, 22, pp. 1330–1334, 2000. [Author's institutional publication record](https://www.microsoft.com/en-us/research/publication/a-flexible-new-technique-for-camera-calibration/). The linked MSR technical report has its own earlier publication/revision dates.
5. OpenCV. **Camera Calibration: calibrateHandEye.** [Official documentation](https://docs.opencv.org/5.0/main_modules/calib.html). Documents transform conventions and separable/simultaneous AX=XB approaches; our local implementation is identified above.
6. Chaumette, F., and Hutchinson, S. **Visual Servo Control, Part I: Basic Approaches.** IEEE Robotics & Automation Magazine, 13(4), pp. 82–90, 2006. [Author's publication discussion](https://faculty.cc.gatech.edu/~seth/res.php?u=vs), [paper](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf).
7. Todorov, E., Erez, T., and Tassa, Y. **MuJoCo: A Physics Engine for Model-Based Control.** IROS, 2012, pp. 5026–5033. DOI: 10.1109/IROS.2012.6386109. [Author-hosted paper](https://homes.cs.washington.edu/~todorov/papers/TodorovIROS12.pdf).
8. MuJoCo. **Overview.** [Official documentation](https://mujoco.readthedocs.io/en/stable/overview.html).
9. Bullet Physics. **PyBullet Quickstart Guide.** [Official repository](https://github.com/bulletphysics/bullet3/blob/master/docs/pybullet_quickstart_guide/PyBulletQuickstartGuide.md.html).
10. Gazebo. **Gazebo Sensors.** [Official documentation](https://gazebosim.org/libs/sensors/).
11. NVIDIA. **Isaac Sim.** [Official overview](https://developer.nvidia.com/isaac/sim/).

Search scope: novel-object RGB-D pose estimation, grasp-versus-pose outputs, planar camera calibration, hand-eye transform conventions, position/image-based visual servoing, and simulator capabilities. The dedicated academic-search MCP was unavailable in this session; primary CVF/arXiv, author/institutional pages and official documentation were retrieved with web search. No citation-count ranking or exhaustive-search claim is made.
