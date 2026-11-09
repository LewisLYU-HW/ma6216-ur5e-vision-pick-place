# Final evaluation figure contract

Question: under the same estimated task-camera calibration, how does the amount of execution-period visual feedback affect complete-sequence success, and does the comparison change under the specified alignment disturbance?

The figure conclusion is determined by the complete 48-trial result. No superiority claim is prescribed in advance. The experimental unit is one full attempt, with eight paired seeds per mode/condition. All failures and all six configurations are included. Previously used seeds are identified as a replication, not a holdout.

## Figure 1: success and robustness

The quantitative grid has two panels. Panel a shows the no-disturbance comparison; panel b tests the same methods under the prescribed force/torque pulse. Both use identical axes, method mappings and Wilson 95% intervals. The important distinction is between complete-sequence success and local alignment after a stage has been reached.

## Figure 2: paired differences

A separate paired-effect plot shows iterative-minus-comparator success differences for every planned method comparison. Conservative exact marginal bounds are shown; paired exact tests and Holm-adjusted p values remain in the report and source data. Marginal confidence-interval overlap is not a substitute for a paired test. Broad intervals and negative/zero effects remain visible.

## Reuse and data mapping

The existing Python/matplotlib `plot_feedback_benchmark.py` workflow is reused exactly with a new results directory. Its input shape and statistics are unchanged:

| Input | Plot role | Units / guard |
|---|---|---|
| `groups[].method` | Stable color and marker mapping | open_loop, staged, iterative |
| `groups[].disturbance` | Figure 1 panel | none or alignment_impulse |
| `success_rate`, `success_ci95` | Point and error bar | Multiply fractions by 100; retain [0,1] probability bounds |
| `paired_module_comparisons[].success_difference` | Figure 2 point | Percentage points, A−B |
| `conservative_ci95` | Figure 2 interval | Percentage points; retain all comparisons |
| `n_trials`, `n_pairs` | Sample-size labels | Eight per configuration / pair set |

No sampling, imputation, interpolation, logarithm or cross-version pooling is introduced. Source-data CSVs and summary SHA-256 are exported with the plots.

## Export and validation

This is a course presentation/report, not a journal submission. Figures retain the existing 183 mm width, at least 7.5 pt plot text, editable SVG/PDF and 600 dpi PNG. TIFF is not required for this delivery; the source validator's missing-TIFF warning is therefore accepted. No quantitative image edits are used.

The existing script runs the rendered panel-alignment gate with a 1.5 pt tolerance. Each final PDF must pass text-size and collision audits; any ambiguous warnings require visual inspection and a recorded reason. Final QA includes both individual panels and the whole figure. Presentation placement preserves aspect ratio; numerical source plots remain available separately from the raster images embedded in the editable slide deck.
