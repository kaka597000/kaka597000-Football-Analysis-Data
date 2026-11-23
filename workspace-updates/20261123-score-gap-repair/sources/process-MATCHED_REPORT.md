# Final archived process-stat sidecar

`matched.jsonl` contains one record per R5 or blind-panel fixture ID and uses the requested sidecar fields plus source provenance. Data is from retained local original bytes only; no new data was fetched.

## Counts

| Measure | Count |
|---|---:|
| Unique fixture IDs | 34669 |
| IDs with at least one shots/xG field | 32525 |
| IDs with no process data | 2144 |
| IDs with complete HS/AS/HST/AST | 32524 |
| IDs with both xG sides | 6741 |
| Understat two-sided xG joined and verified | 6299 |
| ESPN verified 90-minute event stats | 2481 |
| R5 mmz source rows with shot fields | 15134 |
| R5 exact panel row pointers verified against raw mmz | 15135 |
| Duplicate IDs in output | 0 |
| IDs appearing in multiple panel files, collapsed to one sidecar row | 15990 |
| Duplicate source candidate groups | 0 |

The 48 mmz CSVs were read from the R5 `source-index.json` URL records, extracted from the specified tar member and gzip layer, and SHA-256 checked against the index hash. Every R5 panel row pointer for the six domestic leagues was checked by row number, date, and home/away team; no pointer disagreements. Where a raw row exists but has no shot fields, values remain null and its source path is retained.

The mmz source inventory is in `mmz-source-manifest.json`; extracted verified CSV bytes are under `raw-mmz/`. The source archive and member for each is included in the manifest. The fixture-level list with no process fields is `missing.jsonl`; missing component values stay null in the main sidecar.

## ESPN period eligibility

ESPN rows were keyed to the R5 `espn:<event_id>` and required exact event date and home/away team identity agreement. They were accepted only if the R5 stage was regular, group, or league phase; ESPN status was completed Full Time; `format.regulation.periods` was 2; both competitors had exactly two linescores; and no overtime format block appeared. This excludes knockout/playoff matches with extra-time risk. The 2,481 eligible rows are from UCL, Europa League, Conference League, and A-League. Raw source hashes, tar members, and exclusion reasons are in `espn-merge-audit.json`.

## Understat xG

Understat home and away xG were matched by exact date and both teams. All 6,299 joined pairs were re-read and verified directionally against their source rows. The independent SHA-256 of each original `rows.jsonl` is in `understat-source-manifest.json` and each sidecar row (`xg_source_sha256`); original Understat payload SHA is retained as `xg_source_payload_sha256`. Exact files are bundled in `understat-source-rows.tar`, whose SHA-256 is in the manifest. When both Understat and CSV xG existed, Understat is primary and CSV xG is retained in `csv_home_xg`/`csv_away_xg` with `csv_xg_source_sha256`.
