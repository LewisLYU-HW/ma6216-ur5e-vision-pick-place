# Recorded presentation demonstrations

Open [the offline player](../demo_player.html) for the complete continuous 195.88-second original replay at 1× speed. Its task timeline follows the phase and stage logs; selecting a timestamp seeks only on explicit user input. Normal playback never cuts or jumps at task boundaries. The slowed feedback diagnostic is an optional collapsed section. See [full-replay timeline provenance](full_task_timeline.json).

PowerPoint now embeds the full original replay and the separate feedback diagnostic. The short highlights below are retained only as an optional archive; use slideshow mode and click the video. If the presentation application does not support embedded H.264 playback, use the standalone files. PDF contains poster images and links, not playable video.

| Video | Duration | Evidence |
|---|---:|---|
| [Full task replay](../../videos/visual-feedback-calibrated-v1/complete__iterative__none__400.mp4) | 195.88 s | Embedded in PPT; continuous original replay with task timeline |
| [Archived highlights](complete_task_highlights.mp4) | 53.76 s | Optional standalone archive; not embedded in the current PPT |
| [Synchronized visual feedback](visual_feedback_synchronized.mp4) | 20.00 s | Separate perturbed integration run; three observations and one correction |

The highlights retain chronological order with explicit cuts, timestamps and playback-speed labels. Contact-critical excerpts are retained at 1×; the initial moving-feed preview and transport segments may be accelerated. The full original [195.88-second replay](../../videos/visual-feedback-calibrated-v1/complete__iterative__none__400.mp4) remains available.

The feedback video uses 0.125× playback (8× slower). Its source time maps to simulation time by adding the recorded trajectory start, 2.002 s. Metrics become visible only at each observation's `decision_time_s`, and remain held until the next observation is available. There is no interpolation of measurements. Three observed angular residuals are 1.595°, 0.967° and 0.739°. One logged correction commands 0.758 mm / 1.037°. Convergence requires two successive observations within 1.5 mm / 1.5°. The residuals compare estimated and desired object poses; they are not geometric ground-truth errors.

The feedback demo does not change the 48-attempt experiment denominator. Its XYZ overlays reproduce the recorded estimated pose, using the replay camera projection for presentation only. [manifest.json](manifest.json) records sources, hashes, edit points, timing rules, observations and output hashes.

Rebuild from the repository root:

```bash
MUJOCO_GL=egl .venv/bin/python scripts/build_presentation_demos.py
# Re-export only the feedback demonstration:
MUJOCO_GL=egl .venv/bin/python scripts/build_presentation_demos.py --feedback-only
```
