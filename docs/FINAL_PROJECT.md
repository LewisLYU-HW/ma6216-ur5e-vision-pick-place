# Final Project 1 — Vision-Guided Robotic Manipulation

The final application is a four-stage simulated maintenance workcell: return a hammer, intercept a moving screwdriver and insert it into a tilted socket, assemble and relocalize an independent rack, then release/regrasp a spanner and hang it through its hole. UR5e and Robotiq 2F-85 execute contact-based manipulation in MuJoCo. RGB-D observations, reconstructed object references and official FoundationPose inference provide the object poses used for control.

## Submission map

| Course requirement | Implementation | Evidence |
|---|---|---|
| Task 1 — Literature and selection | Compare localization, pose-versus-grasp estimation, calibration, visual feedback and simulation choices; distinguish implemented methods from literature candidates | [English technical review](LITERATURE_AND_SELECTION.md), [BibTeX](references.bib) |
| Task 2 — Camera intrinsics | Fixed and wrist camera parameters estimated from rendered checkerboards; simulator K used only as a validation reference | [Fixed-camera results](results/calibration.json), [wrist images, estimates and held-out errors](results/wrist-calibration-v1/README.md) |
| Task 3 — Camera–robot calibration | Fixed 3D–2D correspondences; wrist image/FK AX=XB with training-only refinement; explicit frame transformations | [Coordinate chain and methods](CALIBRATION_LOCALIZATION.md), [independent wrist validation](results/wrist-calibration-v1/evaluation.json) |
| Task 4 — Object localization | Current-tool depth foreground segmentation in known pickup stations; independently score prediction masks after inference | [50 scenes / 200 queries](results/workshop-localization-v1/README.md), including all masks, intervals and separate background-mismatch failure cases |
| Task 5 — 6D pose estimation | Official FoundationPose using RGB-D-reconstructed references; transform camera-frame estimates into robot coordinates | [Model-free integration](MODEL_FREE_TASKS.md), [pose and alignment metrics](results/visual-feedback-calibrated-v1/README.md) |
| Task 6 — Robot manipulation | Grasp/transfer, tilted insertion, rack assembly, physical regrasp and hanging; planning, joint feedback and release/stability acceptance | [48-attempt final-version evaluation](results/visual-feedback-calibrated-v1/README.md), [original trial replays](videos/visual-feedback-calibrated-v1/README.md) |
| Bonus — Closed-loop vision | Staged reobservation and discrete iterative pose-based alignment compared with no execution-period visual correction | [Feedback implementation](VISUAL_FEEDBACK.md), [paired final-version comparisons](results/visual-feedback-calibrated-v1/README.md) |
| Final presentation | English editable slides, English speaker notes and PDF | [Presentation package](presentation/README.md) |

## Independent technical decisions

The original robot and gripper platform are retained. The extension uses reconstructed tool references instead of feeding tool CAD to pose inference, depth foreground segmentation instead of artificial tool colors, and a wrist view to update held-object and fixture relationships. It adds explicit release/regrasp, rack installation, moving-target prediction, and bounded precontact visual alignment. Camera parameters are independently estimated and propagated through FK. Every success claim is checked after physical release.

These decisions are engineering integration work. FoundationPose, its pretrained networks, and the Neural Object Field implementation are third-party methods. No new neural algorithm or training-from-scratch contribution is claimed. Source and dependency attribution remains in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Experimental boundaries

The final manipulation comparison comprises 48 attempts: three feedback modes, two disturbance conditions, and eight seeds per configuration. It uses the image-estimated wrist calibration. Seeds 400–407 have been used previously, including seed400 integration checks; this is a paired replication rather than a new holdout. All task failures remain in the denominator. Phase completion is reported with reachability and does not replace final whole-sequence success.

The historical [ideal-wrist 48-trial study](results/visual-feedback-v1/README.md) retains its original code/version assumptions and results. It must not be pooled with the estimated-wrist replication. Likewise, the 50-scene localization experiment is a perception study, not 50 robot executions. Reusing one camera-calibration solution across many trials is not repeated independent calibration.

An executable visual-feedback loop and a successful demonstration do not establish an overall performance improvement. The report's effect sizes, uncertainty, exact paired comparisons and failures determine the strength of the conclusion. The project has internal module/feedback comparisons; the literature candidates are not external experimental baselines.

## Limitations to retain in the talk

The workcell uses known pickup regions and fixture conventions. Reference scanning, robot FK, rigid mounting and basic depth rendering retain ideal simulation assumptions. The localization audit has a restricted occlusion/noise envelope, and the manipulation study varies a small set of layouts. Pose-based correction is discrete and applied before contact; it is not continuous contact impedance control. Physics step rate, visual updates and wall-clock inference are different quantities. Wall time includes shared-resource waits and downstream evaluation diagnostics. The release/contact model is not evidence of real-robot reliability.

## Reproduction entry points

Environment setup: [SETUP.md](SETUP.md). Current task-camera calibration and localization: [CALIBRATION_LOCALIZATION.md](CALIBRATION_LOCALIZATION.md). Final comparison configuration: [visual_feedback_calibrated_48.json](../configs/visual_feedback_calibrated_48.json). The final result protocol stores source, calibration and weight hashes, execution conditions and seeds.

```bash
# Use the shared GPU service described in EVALUATION.md.
MA6216_POSE_SOCKET=/tmp/ma6216-calibrated48.sock .venv/bin/python scripts/run_benchmark.py \
  --config configs/visual_feedback_calibrated_48.json --jobs 8 --timeout 2400 \
  --foundationpose-python /path/to/foundationpose/python \
  --output artifacts/calibrated_replication_new

# Rebuild the final English deck from the published results.
python3 scripts/build_project_presentation.py \
  --results docs/results/visual-feedback-calibrated-v1 \
  --output artifacts/presentation_rebuilt
```

The complete videos should be available during the presentation; a short excerpt can fit the 12–15 minute talk, with full-length recordings retained for questions and independent review. Actual oral delivery and any course-platform submission remain group activities.
