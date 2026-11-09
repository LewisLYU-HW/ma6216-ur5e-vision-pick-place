# Grounded processing-chain evidence

RGB, metric depth, predicted mask and calibration come from one archived wrist observation: `complete__iterative__none__400`, `observations/00029_wrist_camera_spanner/`, simulation time 160.340 s. The matching pose result is selected from the trial's perception list using capture time. The reference mesh hash matches the estimator's logged `model_sha256`.

The depth panel uses a disclosed 0.05–0.30 m color range; values outside it are clipped for display. The foreground panel shows the saved prediction, including its imperfections; it is not a simulator segmentation label. The estimated axes are projected using the recorded camera intrinsics and camera-frame object pose.

The reference surface is the actual prior RGB-D reconstruction from 24 views. It was not generated from this single runtime frame. The released hanging image is a later state of the same trial, not a simultaneous observation. Geometry is rendered without changing the stored mesh.

[manifest.json](manifest.json) links the input files, crop, time, pose source and reconstruction hash. Rebuild the two figures using `python3 scripts/build_processing_chain_figure.py`.
