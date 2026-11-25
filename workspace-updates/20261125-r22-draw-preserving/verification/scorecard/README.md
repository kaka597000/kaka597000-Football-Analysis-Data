# R22 compact scorecard

Research-only readable tables built by `build_scorecard.py` from the original R22 historical and repeat output directories and immutable R22 forward/ranked first records. No model training, tuning, or issue writing occurs in this builder.

## Files

- `scorecard.csv`: exactly 72 rows: five competitions plus overall × evaluation, recent, extension × four metrics.
- `forward-picks.csv`: all 45 preserved R22 first issues, sorted by competition, original kickoff timestamp, then match ID. Each row keeps ordered top-three scores for R7, R21, R22 and market, original offset-qualified registration/issue/cutoff/kickoff clocks, total line and source market quote provenance when available.
- `source-hashes.json`: per-file SHA-256 inventories for both historical trees and the frozen forward/ranked roots.
- `manifest.json`: input tree digests, protocol and freeze hashes, output hashes, coverage, doses and row counts.
- `SHA256SUMS`: hashes for the scorecard, forward picks, source inventory, manifest, builder and this README.

## Reading the scorecard

Each row reports R7, R21, R22 candidate and market hits/eligible for one metric. Pairwise `gained_*`, `lost_*`, `net_hits_*`, `net_rate_*`, and `date_cluster_95_*` columns treat R22 as the candidate against that baseline. The confidence intervals are the original date-clustered 95% intervals from R22 metrics. `actual_ou` is retained under the source metric name; its hit and eligible counts are copied from the R22 report without reinterpretation.

`r22_validation_dose` is the fixed score dose selected on the 2024/25 validation sample for that league. `three_first_sweeps` counts complete three-seat batches whose three first choices all hit. Full/short batches, planned/available/empty seat positions, and availability by seat are included on each row. Short-batch size counts are retained as JSON in the CSV cell.

Historical window populations: {"evaluation": 1752, "extension": 48, "recent": 500}. R22 validation doses: {"eng.1": 1.0, "esp.1": 1.0, "fra.1": 0.0, "ger.1": 1.0, "ita.1": 1.0}. The forward registration was recorded at 2026-11-25T22:10:19.032503+08:00; the ranked plan at 2026-11-25T22:10:19.252448+08:00. These forecasts are research-only and are not formally KPI-eligible.

## Rebuild

```bash
python3 build_scorecard.py \
  --historical /path/to/r22-historical \
  --repeat /path/to/r22-historical-repeat \
  --forward /path/to/r22-forward \
  --ranked /path/to/r22-ranked \
  --out-dir /path/to/r22-compact-tables
```

Only Python's standard library is required. The builder verifies both history directories file-by-file, reconciles league totals to overall totals, validates frozen record SHAs/identity/chronology, and checks the ranked plan's fixture population and 15 seat bindings before writing outputs.
