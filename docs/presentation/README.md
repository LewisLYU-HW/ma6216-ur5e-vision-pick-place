# Image-led academic presentation

- [PowerPoint with embedded videos](vision_guided_manipulation.pptx)
- [PDF with static video posters](vision_guided_manipulation.pdf)
- [Preview](preview.jpg) · [English speaker notes](speaker_notes.md)
- [Offline demonstration player](demo_player.html)
- [Figure sources](plates/README.md) · [Validation](validation.json)

The deck contains **21 English slides: 20 main slides and one reference appendix**, for approximately 15–17 minutes including demonstrations. Nineteen slides contain real simulation or calibration imagery, with 42 image-panel placements, two embedded videos and one statistical chart. Titles use 20 pt; supporting text is mostly 11–14 pt. The sole coordinate-chain equation is a 14 pt annotation below the pose figures.

## Demonstrations and processing evidence

Slide 1 embeds [53.76-second task highlights](media/complete_task_highlights.mp4), with synchronized workcell/wrist views, chronological cuts, source timestamps and explicit speed labels. Key grasp, regrasp and release excerpts are retained at normal speed.

Slides 3–4 show a [traceable processing chain](pipeline_source/README.md): one wrist capture's RGB, metric depth, predicted mask and matching estimated pose. The actual reference reconstruction comes from 24 prior views; the displayed hanging result is a later state of the same trial. The distinction is explicit.

Slide 9 embeds a [20-second synchronized feedback diagnostic](media/visual_feedback_synchronized.mp4), slowed to 0.125×. Three observations and one corrective move are shown. Residuals update only when each logged observation becomes available. This is a separate perturbed integration run, not part of the 48-attempt denominator. See [media provenance and playback guidance](media/README.md).

In PowerPoint slideshow mode, click the video. The MP4 files and offline HTML player are alternatives if the presentation application does not support embedded playback. PDF contains static posters and links.

## Scientific boundaries

The final quantitative analysis remains the 48-attempt calibrated replication: three feedback modes, two disturbance conditions, eight reused paired seeds per cell. Selected successes illustrate feasibility; they do not establish statistical superiority or real-robot reliability. Early failures remain included.

Fifteen figure plates are supplied as PNG/PDF/SVG. Enlarged XYZ overlays use the recorded estimated poses, with 60 mm display axes; [pose provenance](pose_axes.json) records the projection inputs. Original videos, raw frames, measurements and outcomes remain unchanged. [Figure contract](FIGURE_CONTRACT.md) and [inspected paper-figure references](FIGURE_DESIGN_REFERENCES.md) document the design decisions.

## Rebuild

Run from the repository root. Existing source observations and reconstruction assets are retained; rebuilding presentation media does not rerun manipulation trials.

```bash
python3 scripts/build_presentation_plates.py --qa-tools /path/to/nature-figure/scripts
MUJOCO_GL=egl .venv/bin/python scripts/project_presentation_pose_axes.py
python3 scripts/refine_presentation_evidence.py --qa-tools /path/to/nature-figure/scripts
python3 scripts/build_processing_chain_figure.py
MUJOCO_GL=egl .venv/bin/python scripts/build_presentation_demos.py
python3 scripts/build_project_presentation.py \
  --results docs/results/visual-feedback-calibrated-v1 \
  --output docs/presentation
python3 scripts/export_presentation_pdf.py
```

The PDF exporter creates a temporary static-poster copy for conversion; it preserves the videos in the original PPTX. Verification covers PDF text bounds/collisions, figure alignment, source hashes, full MP4 decoding and embedded-video package hashes. Interactive playback in a native PowerPoint application has not been tested.
