# Early blind-test match panels

This is an isolated, pre-R5 historical panel supplement. It adds six code-specific JSONL files with the standard R5 panel fields and a combined `panel.jsonl`. It contains no forecasts or model calculations. Markets are null where no same-match archive was supplied. Time phase is stored in the parallel `phase-index.jsonl` to keep the match rows on the R5 common schema. Every event points to retained raw bytes and a source SHA; see the provider manifests, `availability-report.json`, and `hashes.sha256`.

## Time splits

- Calendar competitions (A-League, K League 1, J.League Cup and AFC Champions League): 2011–2015 train/development, 2016 validation, 2017 test.
- UEFA Champions League and Europa League: 2011-07-01–2015-06-30 train/development, 2015-07-01–2016-06-30 validation, 2016-07-01–2017-06-30 test.
- These intervals are event-date windows. Do not shift European dates by season label.

## Acquisition and score rules

- `aus.1`, `afc.champions`, `uefa.champions`, `uefa.europa`: ESPN public scoreboard files, captured in `raw/` and indexed in `source_manifest.json`. UEFA has main-draw rounds only; qualifications/playoffs were excluded. Round fields use the public round slug and leg prefix only, with all aggregate winner text removed. AFC records are tagged `legacy:` because the 2011–2017 ACL format differs from post-2024 ACL Elite.
- `kor.1`: official K League public schedule/result API, 84 monthly result JSON responses queried for 2011–2017; the official endpoint produced no completed league rows before 2013, so retained panel coverage is 2013–2017 (three pre-test seasons, 2016 validation, 2017 test). Completed league results only; explicitly separate playoff fixtures are excluded. All 1,188 retained scores have the official completed result.
- `jpn.league_cup`: official J.League Data Site season search pages and official match cards. Each retained 90-minute score is first-half plus second-half goals. The separate `jleague_score_scope_audit.jsonl` compares this to the match search's final score. Seven rows have evidence of extra time; their 90-minute halves remain the label, while the full-time search score is not copied into the modeling panel. All 361 rows have both half scores.
- ESPN returned HTTP 400 for historical K League and J.League Cup requests. Those error bodies are retained; the official archives above supply the delivered rows.
- AET/PEN ESPN fixtures are scored only when non-shootout event detail is internally complete and reconciles to the scoreboard full-time score after applying own-goal attribution. Otherwise the row remains with null regulation goals and is excluded from any score-based sample. Missing counts are in `availability-report.json`.

## Scope and gaps

The UEFA Champions League and Europa League are filtered to main-draw group stage through final (including Europa's round of 32); UEFA qualifying/play-off ties are out of scope, matching R5 cup scope. AFC 2017 is an old-format main draw, not a current-format ACL Elite sample. The 2017 test window has no FIFA World Cup finals, no UEFA Nations League (started 2018), and no UEFA Conference League (started 2021); see availability report.

## Reproduction

Run the collectors in this order:

1. `python collect_early_panels.py` (ESPN panels and retained failed-response evidence)
2. `python collect_kleague_official.py`
3. `python collect_jleague_cup_official.py`
4. Run `python normalize_panels.py` to normalize provider rows to the R5 common fields, write `phase-index.jsonl`, audit date splits, and rebuild the combined `panel.jsonl`.

The files here are the frozen acquisition outputs. The R5 extraction references are `/workspace/WCPP/reports/kpi-optimization-20261123-r5/euro-cups/scripts/collect_espn_scoreboards.py` for UEFA scope/scoreboard capture, `/workspace/WCPP/reports/kpi-optimization-20261123-r5/special-cups/rebuild.py` for tournament regulation score reconstruction, and `/workspace/WCPP/reports/kpi-optimization-20261123-r5/nordic-brazil/collect_panels.py` for ESPN panel field conventions. The `availability-report.json` also records that each R5 panel starts after its chosen early test window (first R5 dates range from 2018-01-01 to 2024-09-16), so these test dates were not already in the corresponding R5 panels. No training or performance evaluation was run.
