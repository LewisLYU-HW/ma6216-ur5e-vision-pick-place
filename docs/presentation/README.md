# Final project presentation — English

- [Editable PowerPoint](vision_guided_manipulation.pptx)
- [PDF viewing copy](vision_guided_manipulation.pdf)
- [English speaker notes](speaker_notes.md), also embedded in the PowerPoint notes
- [Slide content](slides.json) and [data/image provenance](provenance.json)
- [Final PDF/PPT and language checks](validation.json)
- [Course requirement and evidence map](../FINAL_PROJECT.md)
- [Technical selection and verified references](../LITERATURE_AND_SELECTION.md)
- [Final estimated-wrist evaluation](../results/visual-feedback-calibrated-v1/README.md)
- [Original complete and failure videos](../videos/visual-feedback-calibrated-v1/README.md)

The 19-slide deck is designed for approximately 12–15 minutes, with a short video excerpt during the talk. Complete recordings remain separate for review; the deck does not embed multiple large videos. The deck's task illustrations explain the workflow and are not independent statistical observations. Quantitative plots come from the final 48-attempt estimated-wrist replication, not the historical ideal-wrist study.

Texts and tables are editable PowerPoint objects. Plots are embedded as high-resolution previews; editable SVG/PDF versions and source-data CSVs are provided in the [figure package](../results/visual-feedback-calibrated-v1/figures/README.md). Image placement preserves aspect ratio without changing visual content.

The notes explain assumptions, experimental units, failed attempts and the limits of the comparison. Do not replace the measured results with a claim of guaranteed architectural superiority. Add the actual group member names and course submission identifiers if required by the class; they are not inferred from repository authorship.

```bash
python3 scripts/build_project_presentation.py \
  --results docs/results/visual-feedback-calibrated-v1 \
  --output artifacts/presentation_rebuilt
```

The builder requires Python with `python-pptx` and Pillow. PDF export uses LibreOffice; the simulation environment does not need these presentation dependencies. The final generated files are already included for viewing without running the builder.
