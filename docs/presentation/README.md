# Academic research presentation — English

![Selected pages from the academic presentation](preview.jpg)

- [Editable PowerPoint](vision_guided_manipulation.pptx)
- [PDF viewing copy](vision_guided_manipulation.pdf)
- [English speaker notes](speaker_notes.md), also embedded in PowerPoint
- [Slide content](slides.json) · [Provenance](provenance.json) · [Validation](validation.json)
- [Processed scientific image plates](plates/README.md) · [Figure contract](FIGURE_CONTRACT.md)
- [Original frame manifest](frames/manifest.json): video hashes, frame indices, timestamps and camera-panel crops
- [Course evidence map](../FINAL_PROJECT.md) · [Literature review](../LITERATURE_AND_SELECTION.md)
- [Complete quantitative report](../results/visual-feedback-calibrated-v1/README.md) · [Original videos](../videos/visual-feedback-calibrated-v1/README.md)

This academic revision replaces the previous files at the same paths. It contains **22 English slides: 21 main slides and one reference appendix**, designed for approximately 12–15 minutes. All slides retain real simulation or calibration imagery. There are 48 runtime/calibration panel placements and one statistical chart.

The argument follows the research question, technical selection, calibrated observation-to-control method, physical operation evidence, paired experimental design, quantitative results, failure analysis and limitations. Coordinate transforms and pose residuals use editable equation text; the architecture is composed of editable PowerPoint shapes. Detailed interpretation is in the English notes.

Twelve processed image plates use consistent cropping, matched temporal views, lowercase panel identifiers, explanatory region outlines and a magnified false-positive region. Original frames and outcomes are unchanged. Each plate is supplied as PNG plus editable-text PDF/SVG with a crop/source manifest and rendered quality checks. The PNGs are embedded in PowerPoint; text within a plate is edited through its source SVG or plotting script, while slide titles, equations and explanatory text are native PowerPoint objects.

The main manipulation plates follow iterative/no-disturbance seed 400. Qualitative controls show the matched open-loop failure in seed 400 and both staged/iterative pickup failures in seed 401. The correction example is a **separate integration run**; the background diagnosis is a **separate localization experiment**. Neither changes the denominator of the final 48 attempts. The result does not establish architectural superiority, equivalence or real-robot reliability.

No image-generative enhancement, scene retouching, contrast adjustment or invented metric scale is used. Source videos provide finite raster resolution; high-DPI exports improve annotations but do not invent image detail. Rectangles identify visual regions, not measured coordinate axes or contact forces. Full-length movies remain separate from the presentation.

```bash
python3 scripts/extract_presentation_frames.py
python3 scripts/build_presentation_plates.py --qa-tools /path/to/nature-figure/scripts
python3 scripts/build_project_presentation.py \
  --results docs/results/visual-feedback-calibrated-v1 \
  --output artifacts/presentation_rebuilt
```

Rebuilding requires ffmpeg, Pillow, matplotlib and python-pptx; figure alignment uses the supplied skill audit interface. LibreOffice exports the PDF. The final files are included for immediate use without rebuilding. Add actual group names and course identifiers if required by the class.
