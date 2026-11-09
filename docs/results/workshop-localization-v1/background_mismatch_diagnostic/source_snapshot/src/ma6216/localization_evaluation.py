"""Downstream mask metrics: never imported by perception or control."""
import numpy as np


def mask_metrics(prediction, visible_truth):
    p, t = np.asarray(prediction) > 0, np.asarray(visible_truth) > 0
    if p.shape != t.shape:
        raise ValueError("Mask shapes must match")
    tp = int(np.count_nonzero(p & t))
    fp, fn = int(np.count_nonzero(p & ~t)), int(np.count_nonzero(~p & t))
    visible, predicted = int(t.sum()), int(p.sum())
    return {"true_positive_pixels": tp, "false_positive_pixels": fp, "false_negative_pixels": fn,
            "visible_truth_pixels": visible, "predicted_pixels": predicted,
            "iou": tp / (tp + fp + fn) if visible else None,
            "precision": tp / predicted if predicted else (0. if visible else None),
            "recall": tp / visible if visible else None,
            "mask_returned": predicted >= 40,
            "localized_iou50": bool(visible >= 40 and predicted >= 40 and tp / (tp + fp + fn) >= .5),
            "false_positive_on_invisible": bool(visible == 0 and predicted >= 40)}


def evaluate_rendered_mask(renderer, model, body_name, prediction):
    """Call only after a prediction exists; no return value may guide control."""
    from .scene import mujoco
    renderer.enable_segmentation_rendering()
    try:
        segmentation = renderer.render().copy()
    finally:
        renderer.disable_segmentation_rendering()
    gids = np.flatnonzero(model.geom_bodyid == model.body(body_name).id)
    truth = np.isin(segmentation[..., 0], gids) & (segmentation[..., 1] == int(mujoco.mjtObj.mjOBJ_GEOM))
    return mask_metrics(prediction, truth)
