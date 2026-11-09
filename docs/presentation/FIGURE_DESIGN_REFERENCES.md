# Figure design references and adaptation

These papers inform visual communication only. Their images are not reproduced in the slides; no external method is claimed as implemented through this design revision.

1. Wen et al., FoundationPose, CVPR 2024, Figure 5 (PDF page 7). Its qualitative comparison uses consistent object crops across methods and retains pose-result overlays. Adaptation: matched pixel windows for paired controller outcomes, retain original pose overlays, explicitly distinguish different endpoint times. [Primary paper](https://jankautz.com/publications/FoundationPose_CVPR24.pdf).
2. Haugaard, Buch and Iversen, Self-supervised deep visual servoing for high precision peg-in-hole insertion, 2022, Figure 1 (PDF page 1). Rows distinguish components; columns show before servoing and successive iterations. Adaptation: chronological columns with timestamps, local interface detail, and logged pre/post visual residuals. [Primary paper](https://arxiv.org/pdf/2206.08800).

Both figures were inspected as rendered PDF pages. Our additional connected context/detail insets make the small ring/pin and gripper interfaces readable while preserving their original scene context. Thin amber leaders encode image-region correspondence; they are not motion paths. No generative image editing, invented pose axes, retouched contacts, artificial scale bars or altered trial outcomes are used.

The 19-slide English deck retains quantitative uncertainty and failed trials. Six redesigned evidence figures are exported as PNG/PDF/SVG, with source-frame hashes and manually selected ROI coordinates. These are re-presentations of existing evidence, not additional experiments.
