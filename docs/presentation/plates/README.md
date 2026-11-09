# Scientific image plates

These plates organize actual recorded observations into a research evidence sequence. Every source and crop appears in [manifest.json](manifest.json); the original video-to-frame mapping is in [../frames/manifest.json](../frames/manifest.json).

| Plate | Evidence role | Files |
|---|---|---|
| overview | Initial conditions and released final state | [PNG](overview.png) · [PDF](overview.pdf) · [SVG](overview.svg) |
| calibration | Independent image-based camera estimation | [PNG](calibration.png) · [PDF](calibration.pdf) · [SVG](calibration.svg) |
| localization | Tool-specific predicted/visible mask overlays | [PNG](localization.png) · [PDF](localization.pdf) · [SVG](localization.svg) |
| hammer | Held vs released placement | [PNG](hammer.png) · [PDF](hammer.pdf) · [SVG](hammer.svg) |
| insertion | Reorientation, insertion and released socket support | [PNG](insertion.png) · [PDF](insertion.pdf) · [SVG](insertion.svg) |
| rack | Independent object, seating and released fixture | [PNG](rack.png) · [PDF](rack.pdf) · [SVG](rack.svg) |
| regrasp | Placement, finger clearance and new grasp | [PNG](regrasp.png) · [PDF](regrasp.pdf) · [SVG](regrasp.svg) |
| hanging | Alignment, threading and released hanging | [PNG](hanging.png) · [PDF](hanging.pdf) · [SVG](hanging.svg) |
| correction | Separate integration example with logged visual residuals | [PNG](correction.png) · [PDF](correction.pdf) · [SVG](correction.svg) |
| paired | Same-seed open-loop guard stop and iterative completion | [PNG](paired.png) · [PDF](paired.pdf) · [SVG](paired.svg) |
| failure | Same-seed early failure of both feedback variants | [PNG](failure.png) · [PDF](failure.pdf) · [SVG](failure.svg) |
| background | Context and magnification of a false-positive region | [PNG](background.png) · [PDF](background.pdf) · [SVG](background.svg) |

All runtime times are video playback times, not wall-clock latency. No frame is an independent trial. Positive and negative examples retain the archived selection and outcomes. Quantitative intervals and all attempted trials remain in the linked full report.

Processing is limited to recorded rectangular crops, common image viewports, labels and amber region outlines. No color/contrast/gamma or scene-content edits are applied. No metric scale bar is inferred from perspective views. Original mask overlays encode green overlap, red extra foreground and blue missed visible target; the accompanying text explains this encoding.

The Python source exports 12-inch-wide slide plates at 300 dpi and PDF/SVG with editable text. Native image resolution is finite. The 300 dpi and 12-inch dimensions intentionally target presentation use, not a journal's 89/183 mm production format. The PNG-instead-of-TIFF, DPI and width source-audit warnings are documented in [qa.json](qa.json). Every plate has `.alignment.json`, `.text-audit.json` and `.collision-audit.json`; annotated collision PDFs are diagnostic files, not presentation images.

The insertion, regrasp, hanging, correction, paired and failure plates additionally contain connected context/detail views. Amber leaders map each original-pixel ROI to its enlarged inset; identical pixel windows are used within each comparison. Text distinguishes visible relationships from logged residuals and acceptance checks. See [inspected paper figures and design adaptations](../FIGURE_DESIGN_REFERENCES.md). Regenerate these six plates using `scripts/refine_presentation_evidence.py --qa-tools /path/to/nature-figure/scripts` after generating the base plates.

Latest revision supersedes the six context/detail layouts above: enlarged matched task-region crops now fill the evidence panels, with reprojected 60 mm XYZ axes. A thirteenth plate, [pose](pose.png), shows the object frames for screwdriver alignment and spanner regrasp. See [axis provenance](../pose_axes.json).
