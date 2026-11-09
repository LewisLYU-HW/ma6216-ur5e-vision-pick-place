# Academic presentation figure contract

Audience: engineering course research presentation, approximately 12–15 minutes. This is not a journal submission. English slides and notes; native PowerPoint text and diagrams; original simulation evidence dominates the slides.

Central question: how does execution-period pose feedback affect complete-sequence manipulation under independently estimated camera calibration? The existing 48-attempt replication provides the quantitative answer; selected frames illustrate mechanisms and failure boundaries, not independent repetitions or evidence of statistical superiority.

Evidence sequence: problem and geometric constraints → calibrated observation/control chain → physical operation evidence → controlled comparison → failure mechanisms → bounded conclusions.

Image plates use the Python/matplotlib backend. White canvas; restrained navy, blue and amber annotations; lowercase panel identifiers; equal image rectangles within each comparison. Final plate width 12 inches for slide use; editable PDF/SVG and 300 dpi PNG. Native image resolution is retained and disclosed; no claim that upsampling creates new image detail. Minimum plate font 12 pt. No journal-specific TIFF requirement.

| Plate | Question and panel roles |
|---|---|
| overview | Initial conditions vs released final state; establishes sequence scope |
| calibration | Image detections vs held-out hand-eye view; establishes independent camera estimation |
| localization | Four tool masks in one nominal scene; shows detector output and missed foreground |
| hammer | Held tool vs released tray placement; demonstrates physical return |
| insertion | Reorientation → insertion → released socket placement; demonstrates shaft constraint |
| rack | Pickup → seating → released rack; establishes the movable-fixture dependency |
| regrasp | Supported placement → cleared fingers → new grasp; distinguishes physical regrasp from attachment changes |
| hanging | Alignment → threading → released hanging; demonstrates hole/pin geometry |
| paired | Open-loop guard stop vs iterative completion in seed 400; illustrative paired comparison |
| failure | Staged vs iterative pickup stop in seed 401; bounds downstream feedback benefit |
| correction | Pre/post logged correction in a separate integration run; illustrates loop action only |
| background | Context image vs magnified false-positive region; exposes background dependency |

Image integrity: raw files remain unchanged. Crop boxes and panel-source SHA-256 are recorded. No brightness, contrast, gamma, pseudo-color or physical scene edits are introduced. Existing mask/pose overlays remain part of the original evidence. New rectangles, leaders and labels are explanatory annotations, not recovered calibration axes or measured contact forces. Insets identify image coordinates only; no invented metric scale bars. The nominal segmentation plates and separate background diagnosis are explicitly distinguished from robot trials.

Validation: run rendered panel-alignment checks at 1.5 pt tolerance, PDF text and collision audits, and inspect every final plate. Document intentional leader/ROI intersections. Inspect rendered slides for clipping and text collisions. Verify presentation and original-image hashes. Reuse existing quantitative figures without recomputing or selecting outcomes; preserve all configurations and uncertainty in the report.

## Context/detail revision

Six figures (insertion, regrasp, hanging, correction, paired, failure) now use two levels of evidence: matched context windows and explicitly connected, enlarged pixel regions. Insets are square-padded, never stretched, and use identical crop coordinates within a comparison. Amber rectangles and leaders identify manually selected explanatory regions, not estimated masks or measured trajectories. Original camera motion is retained; equal pixel windows do not imply a fixed world-coordinate scale. Text adjacent to each detail distinguishes visible geometry from log-derived acceptance or failure attribution. Minimum source font is 11.5 pt; these figures occupy full slide width in the dedicated evidence slides.

The two rows of deliberately different-sized axes are audited independently for equal alignment. Source hashes, context/detail coordinates, time labels and explanatory annotation semantics are stored in `plates/manifest.json`. Run `scripts/refine_presentation_evidence.py` after the base plate builder and before the slide builder.

## Enlarged-image and pose-axis revision (supersedes context/detail layout)

Seven plates now prioritize large matched task-region views, replacing duplicated small context/inset pairs. The pose figure additionally replaces the two raw images on the coordinate-transformation slide. Axes are projected from the archived `estimated_pose` arrays, using the replay camera extrinsics and original 960×720 projection/crop conventions. Axis length is 60 mm (formerly 25 mm in the replay); vector strokes are 2.6 pt with a dark outline and 14 pt XYZ labels. Labels may be offset to remain readable; axis origins, directions and endpoints retain the actual perspective projection. Nearly collinear projected axes are not artificially rotated apart. These are display overlays of the archived estimate, not fresh pose estimates or ground-truth object poses.

`pose_axes.json` records the trajectory hashes, snapshot indices, poses, projected endpoints and camera convention. The frame JPEGs, trial results and camera calibration are unchanged. Camera truth is used only to reproduce the presentation camera projection, not as new controller input. The plate manifest records each cropped view and the associated projection. Full original videos remain the context reference.
