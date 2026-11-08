"""Plot every measured feedback configuration and paired effect, with uncertainty."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


TASKS = {"complete": "Complete\nsequence", "insert": "Driver\ninsertion", "hang": "Spanner\nhanging", "rack": "Rack\nassembly"}
SHORT = {"complete": "Complete", "insert": "Driver", "hang": "Spanner", "rack": "Rack"}
METHODS = {"open_loop": "Open loop", "staged": "Staged feedback", "iterative": "Iterative feedback"}
COLOURS = {"open_loop": "#78818D", "staged": "#C28137", "iterative": "#087F83"}


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--qa-tools", type=Path, required=True, help="Directory containing audit_panel_alignment.py")
    args = parser.parse_args()
    sys.path.insert(0, str(args.qa_tools))
    from audit_panel_alignment import require_matplotlib_panel_alignment
    source = args.results / "summary.json"
    result = json.loads(source.read_text())
    protocol = json.loads((args.results / "protocol.json").read_text())
    if not result["complete"]:
        raise RuntimeError("Only plot the complete, frozen evaluation")
    tasks = list(protocol["config"]["tasks"])
    expected = len(tasks) * len(METHODS) * 2
    if len(result["groups"]) != expected:
        raise RuntimeError("Missing/extra feedback configurations")
    output = args.results / "figures"
    output.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"],
                        "font.size": 8.5, "axes.labelsize": 8.5, "xtick.labelsize": 7.5,
                        "ytick.labelsize": 8, "legend.fontsize": 8.5,
                        "axes.spines.top": False, "axes.spines.right": False,
                        "axes.linewidth": 0.7, "legend.frameon": False,
                        "svg.fonttype": "none", "pdf.fonttype": 42,
                        "savefig.dpi": 600})

    def save(fig, name):
        fig.canvas.draw()
        require_matplotlib_panel_alignment(fig, json_out=output / (name + ".alignment.json"),
                                          overlay_svg=output / (name + ".alignment.svg"),
                                          tolerance_pt=1.5, gutter_tolerance_pt=1.5, strict=True)
        fig.savefig(output / (name + ".pdf"))
        fig.savefig(output / (name + ".svg"))
        fig.savefig(output / (name + ".png"), dpi=600)
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(183/25.4, 86/25.4), sharey=True)
    fig.subplots_adjust(left=0.09, right=0.98, top=0.85, bottom=0.26, wspace=0.15)
    rows = []
    for panel, condition in enumerate(("none", "alignment_impulse")):
        ax = axes[panel]
        for i, (method, title) in enumerate(METHODS.items()):
            groups = [next(g for g in result["groups"] if (g["task"], g["method"], g["disturbance"]) == (task, method, condition)) for task in tasks]
            y = 100 * np.array([g["success_rate"] for g in groups])
            limits = 100 * np.array([g["success_ci95"] for g in groups])
            ax.errorbar(np.arange(len(tasks)) + (i-1)*0.23, y,
                        yerr=np.stack([y-limits[:, 0], limits[:, 1]-y]),
                        fmt=("o", "s", "^")[i], markersize=4.5, capsize=2.2,
                        color=COLOURS[method], elinewidth=1.0, label=title)
            rows.extend({"task": g["task"], "method": method, "condition": condition,
                         "successes": g["successes"], "n_trials": g["n_trials"],
                         "success_rate_percent": 100*g["success_rate"],
                         "wilson_lower_percent": 100*g["success_ci95"][0],
                         "wilson_upper_percent": 100*g["success_ci95"][1]} for g in groups)
        ax.set_xticks(np.arange(len(tasks)), [TASKS[t] for t in tasks])
        ax.set_yticks([0, 20, 40, 60, 80, 100])
        ax.set_ylim(-5, 105)
        ax.set_xlim(-0.55, len(tasks)-0.45)
        ax.grid(axis="y", color="#D8DCE0", linewidth=0.5)
        ax.set_axisbelow(True)
        ax.set_title("No external perturbation" if panel == 0 else "Alignment force/torque pulse", fontsize=9.0, pad=10)
        ax.annotate(chr(97+panel), xy=(0, 1), xycoords="axes fraction", xytext=(-25, 10),
                    textcoords="offset points", fontweight="bold", fontsize=10, va="bottom")
    axes[0].set_ylabel("Task success (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.53, 0.015), ncol=3)
    save(fig, "success_rates")
    write_csv(output / "success_rates.source-data.csv", rows)

    pairs = result["paired_module_comparisons"]
    pair_height_mm = max(65, 26 + 7.1 * len(pairs))
    fig, ax = plt.subplots(figsize=(183/25.4, pair_height_mm/25.4))
    fig.subplots_adjust(left=0.37, right=0.97, top=0.93, bottom=0.23 if len(pairs) <= 4 else 0.12)
    labels, rows = [], []
    for i, item in enumerate(pairs):
        point = 100*item["success_difference"]
        lo, hi = 100*np.asarray(item["conservative_ci95"])
        colour = COLOURS[item["b"]]
        ax.errorbar(point, i, xerr=np.array([[point-lo], [hi-point]]), fmt="o",
                    color=colour, markersize=4.3, elinewidth=1.0, capsize=2.0)
        condition = "None" if item["disturbance"] == "none" else "Pulse"
        baseline = "Open" if item["b"] == "open_loop" else "Staged"
        labels.append(f"{SHORT[item['task']]} / {condition} / vs {baseline}")
        rows.append({"task": item["task"], "condition": item["disturbance"],
                     "method_a": item["a"], "method_b": item["b"], "n_pairs": item["n_pairs"],
                     "difference_percentage_points": point, "lower_percentage_points": lo,
                     "upper_percentage_points": hi, "a_only_success": item["a_only_success"],
                     "b_only_success": item["b_only_success"],
                     "mcnemar_p": item["exact_mcnemar_p_unadjusted"],
                     "holm_p": item["exact_mcnemar_p_holm_within_family"]})
    ax.axvline(0, color="#B6BDC5", linewidth=0.8, linestyle="--", zorder=0)
    ax.set_yticks(np.arange(len(labels)), labels)
    ax.set_ylim(len(labels)-0.4, -0.6)
    ax.set_xlim(-105, 105)
    ax.set_xticks([-100, -50, 0, 50, 100])
    ax.set_xlabel("Iterative minus comparator (percentage points)")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=6)
    save(fig, "paired_differences")
    write_csv(output / "paired_differences.source-data.csv", rows)
    (output / "provenance.json").write_text(json.dumps({
        "summary_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "groups_plotted": expected, "paired_comparisons_plotted": len(pairs),
        "excluded_configurations": [], "backend": "Python/matplotlib",
        "dimensions_mm": {"success_rates": [183, 86], "paired_differences": [183, pair_height_mm]},
        "uncertainty": "Wilson 95% for task rates; conservative exact marginal bounds for paired success differences",
        "unit": "one trial; never one video frame", "image_adjustments": "none; numerical plots only",
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
