# Validation and preparation notes

The complete notebook was executed from the five supplied raw CSV files in a fresh Python 3.12 process. All 11 code cells completed; the saved notebook retains tables and its figure. The portable runner uses IPython to execute the same cells without requiring a Jupyter server. Interactive Jupyter launching was not tested in this execution environment because local sockets were unavailable.

## Comparison with the original analysis

- Reconstructed order count: 486,928; bundle/quantity comparison: 79,875 orders.
- All 48 regression coefficients across 21 models match the original integrated notebook to numerical precision (maximum absolute difference below 2 × 10⁻¹⁵).
- Model observation counts are unchanged. All 21 fixed-effect procedures converged.
- Standard errors now include the absorbed fixed-effect rank in the CR1 finite-sample adjustment. Confidence intervals and p-values both use a t distribution with clusters minus one degrees of freedom.
- Main remote-fulfillment association: −14.1995 percentage points; revised 95% interval: [−21.4830, −6.9161]. The conclusion is unchanged.

## Checks performed

Three targeted numerical tests pass: absorbed coefficients/standard errors/p-values/intervals agree with explicit dummy-variable OLS; nested effects are not counted twice; failed absorption convergence stops inference. Reference merges enforce cardinality. Input audits and sample-flow tables are exported. The figure was visually reviewed.

## Data issues made explicit

The SKU reference has 31,868 rows but 31,867 distinct keys. One SKU has conflicting `attribute2` values; its disputed attribute is set to missing, and no order line uses it. No numerical order fields are missing after parsing, but 8,537 final-unit-price entries are negative. The original clipping-to-zero convention is retained and documented; the main regression does not use final revenue. Discount accounting discrepancies remain visible in the audit.

## Repository changes

One main notebook replaces the collection of similarly named final/exploratory versions. Reusable functions live in `src/`; paths are relative to the project. Raw data, personal paths, automatic package installation, redundant workbook exports, and original hashed SKU labels are excluded from public outputs. Purpose comments and Markdown explain the operations and assumptions. Input SHA-256 digests and package versions are in `results/`.

The original uploaded notebooks and output archives were not modified. The README and interpretations describe associations rather than causal promotion effects.
