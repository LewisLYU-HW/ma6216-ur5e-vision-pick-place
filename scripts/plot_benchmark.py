"""Export static figures from measured benchmark summaries (requires matplotlib)."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

LABELS = {
    "assembly": "Assembly\nrecovery",
    "clutter": "Occlusion\n+ regrasp",
    "conveyor": "Moving\npickup",
    "insert": "Driver\ninsertion",
    "hang": "Spanner\nhanging",
    "rack": "Rack\nself-assembly",
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", type=Path, required=True)
    args = p.parse_args()
    result = json.loads((args.results / "summary.json").read_text())
    if not result["complete"]:
        raise RuntimeError("Publication figures require a complete matrix")
    folder = args.results / "figures"
    folder.mkdir(exist_ok=True)
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
            "figure.dpi": 160,
        }
    )
    tasks = list(LABELS)
    colours = ("#157f83", "#d37b42")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
    for ax, disturbed in zip(axes, (False, True)):
        for offset, full, colour in zip((-0.17, 0.17), (True, False), colours):
            groups = [
                next(
                    g
                    for g in result["groups"]
                    if g["task"] == task
                    and (g["method"] == "full") == full
                    and (g["disturbance"] != "none") == disturbed
                )
                for task in tasks
            ]
            y = np.array([g["success_rate"] for g in groups]) * 100
            limits = np.array([g["success_ci95"] for g in groups]) * 100
            x = np.arange(len(tasks)) + offset
            ax.bar(x, y, width=0.30, color=colour, label="Full system" if full else "Task-specific ablation")
            ax.errorbar(
                x,
                y,
                yerr=np.maximum(0.0, np.vstack([y - limits[:, 0], limits[:, 1] - y])),
                fmt="none",
                color="#263442",
                capsize=3,
            )
            for position, value, group in zip(x, y, groups):
                ax.text(
                    position,
                    min(105.0, value + 3.0),
                    f"{group['successes']}/{group['n_trials']}",
                    ha="center",
                    fontsize=8,
                )
        ax.set_xticks(range(len(tasks)), [LABELS[t] for t in tasks])
        ax.set_ylim(0, 112)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_title("Prescribed disturbance" if disturbed else "No added disturbance")
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Physical task success (%)")
    axes[0].legend(loc="lower left", fontsize=8)
    fig.suptitle("10 paired seeds per configuration · 95% Wilson intervals", fontsize=12)
    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(folder / ("success_rates." + suffix), bbox_inches="tight")
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    metrics = [
        ("pose_initial_raw_translation_error_mm", "Initial FoundationPose error (mm)"),
        ("tcp_tracking_translation_mm_rmse", "TCP tracking RMSE (mm)"),
        ("register_latency_seconds", "Registration latency (s)"),
    ]
    for ax, (metric, label) in zip(axes, metrics):
        for offset, disturbed, colour in zip((-0.12, 0.12), (False, True), colours):
            groups = [
                next(
                    g
                    for g in result["groups"]
                    if g["task"] == t and g["method"] == "full" and (g["disturbance"] != "none") == disturbed
                )
                for t in tasks
            ]
            stats = [g["metrics"].get(metric, {"mean": None, "ci95": [None, None]}) for g in groups]
            y = np.array([s["mean"] if s["mean"] is not None else np.nan for s in stats])
            limits = np.array([[np.nan if x is None else x for x in s["ci95"]] for s in stats])
            ax.errorbar(
                np.arange(len(tasks)) + offset,
                y,
                yerr=np.maximum(0.0, np.vstack([y - limits[:, 0], limits[:, 1] - y])),
                fmt="o",
                color=colour,
                capsize=3,
                label="Disturbed" if disturbed else "Nominal",
            )
        ax.set_xticks(range(len(tasks)), [t[:4] for t in tasks], rotation=30)
        ax.set_ylabel(label)
        ax.grid(axis="y", alpha=0.2)
        ax.set_ylim(bottom=0.0)
    axes[0].legend(fontsize=8)
    fig.suptitle("Full system · trial-level means and 95% bootstrap intervals", fontsize=12)
    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(folder / ("measured_metrics." + suffix), bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
