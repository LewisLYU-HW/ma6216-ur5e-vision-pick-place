# Estimated-calibration feedback evaluation: original videos

These five videos replay four original trials from the final 48-trial paired replication. They preserve the full recorded sequence and original outcomes. No inference or physics is rerun for video export.

| Video | Outcome | Duration |
|---|---|---|
| [complete__iterative__none__400.mp4](complete__iterative__none__400.mp4) | Success | 195.88 s |
| [complete__iterative__none__400__wrist.mp4](complete__iterative__none__400__wrist.mp4) | Success | 195.88 s |
| [complete__iterative__none__401.mp4](complete__iterative__none__401.mp4) | Failure | 40.40 s |
| [complete__open_loop__none__400.mp4](complete__open_loop__none__400.mp4) | Failure | 58.12 s |
| [complete__staged__none__401.mp4](complete__staged__none__401.mp4) | Failure | 40.40 s |

The main demonstration is the lowest successful seed in iterative/no-disturbance mode (400): hammer return, moving screwdriver pickup and tilted insertion, independent rack installation, spanner release/regrasp and through-hole hanging. The separate wrist recording shows the same run.

The open-loop seed 400 failure is paired with iterative seed 400. Staged seed 401 is paired with iterative seed 401, which also fails. Selection follows the frozen protocol; a successful demonstration does not establish a high success rate.

Across eight trials per cell, open-loop succeeds 0/8 without and 0/8 with disturbance; staged feedback 3/8 and 2/8; iterative feedback 3/8 and 3/8. All four Holm-adjusted method-comparison p-values are 1.0. These reused seeds constitute a paired replication, not a fresh holdout.

[Full metrics and confidence intervals](../../results/visual-feedback-calibrated-v1/README.md) · [Video hashes and provenance](manifest.json) · [Independent main-video motion audit](../../results/visual-feedback-calibrated-v1/hero_motion_audit.json)

MP4/H.264/yuv420p, 25 fps. Playback uses simulation time; inference, planning and queue waiting are not represented as real-time delays. Visual residual overlays are estimated residuals, not ground-truth geometric error.
