# R21 score-dependence historical and frozen-slate evidence

Research replay only; no model promotion or formal KPI eligibility. R21 preserves the R7 score marginals and fits a bounded dependence term from prior-match npxG concordance and chance volume.

## Historical windows

The evaluation window is the fixed 2025/26 holdout; recent and November-extension windows remain separate. Coverage is by competition and window in [competition-window-coverage.csv](competition-window-coverage.csv). Fit coefficients, validation doses and time bounds are in [fitted-weights-and-doses.csv](fitted-weights-and-doses.csv).

Paired same-fixture gains and losses, net hits/rates and date-clustered 95% intervals are in [paired-gains.csv](paired-gains.csv). `candidate_vs_r7` is the preferred selected R21 recipe against R7; `candidate_vs_market` is the same-game market ablation; `candidate_vs_constant` compares against the intercept-only model at its own selected doses; `candidate_vs_constant_matched` holds the contextual dose while using intercept-only weights. All four outcome definitions are retained, including total settlement eligibility.

## Frozen forward slate

The 45 first issues retain the 2026-11-25 21:17:21.555419 +08 registration; 3 started fixtures are excluded from the original R7 population of 48. The exact registration and ranked-plan SHA values, per-league market/history coverage, and independently reconstructed 15 seats are in [frozen-forward-rank.json](../verification/frozen-forward-rank.json) and [forward-coverage.csv](../verification/forward-coverage.csv). The verifier only reads and hashes the frozen receipts; it does not issue or overwrite records.

## Raw npxG audit

[Understat raw verification](../verification/understat/reports/verification.json) independently recalculates all 11,031 fixed R14 events from 35 original getLeagueData responses. npxG/npxGA live in nested `source_history_sides`, separate from the top-level all-shot xG/xGA columns. Competition sums are reconciled against the global totals.
