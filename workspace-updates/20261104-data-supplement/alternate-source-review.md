# Alternate source review for scope18 gaps

Review time: 2026-11-04 UTC. Scope: whether freely available evidence can certify both (a) a match's neutral-site status and (b) its regulation-90 score for the ESPN scoreboard candidates in this directory.

## Evidence reviewed

The ESPN public scoreboard responses in `*.json` and the original scope18 response files under `../network-probes/` provide event IDs, dates, teams, competition phase, venue labels, home/away labels, score strings, and status. The event-level audit in `audit.json` found no explicit `neutralSite` boolean in any of the candidate collections. The 2024 Europa League and Conference League responses in the parent scope folder have the same relevant limitation.

`STATUS_FINAL_AET` and `STATUS_FINAL_PEN` identify events whose returned score must not be treated as a 90-minute score without a separate match record. `STATUS_FULL_TIME` is a useful candidate filter, but the scoreboard alone does not certify the score basis or phase for this dataset. A venue name, local city, or the apparent nationality of either club cannot establish a neutral boolean. Tournament rules do not establish that an individual fixture is neutral, and knockout tie stages cannot be merged with league phases.

## Summary endpoint cross-check

On explicit direction, ten match-specific ESPN public summary requests were made for two samples per competition with returned events: AFC Champions League Elite, A-League Men, FIFA World Cup, Europa League, and Conference League. Each returned summary contains an explicit boolean `neutralSite`; all ten samples have `false`. For all ten, event ID, team identities, and scores reconcile with the sampled scoreboard event. The six records with `STATUS_FULL_TIME` also expose a two-period regulation format and stage. Four AET/penalty records are excluded as final-score labels. The manifest preserves request timestamps, URLs, response hashes, and raw response paths; `summary-event-audit.json` gives the row-level comparisons.

This proves that the summary endpoint can fill the neutral boolean for queried events, and it yields six exact, usable sampled event records. It does **not** establish neutral-site coverage for unqueried events: the scoreboard corpus still has zero explicit neutral booleans, and a sample result cannot be imputed to other matches. No alternate public provider was queried after the representative summaries; official UEFA/FIFA, federation, and league match records remain the next candidate if full-corpus completion is needed. No venue or team-geography inference was used.

## Row decision

Strictly usable sampled event records: **6** (one AFC Champions League Elite, two A-League Men, one FIFA World Cup, one Europa League, one Conference League). Keep all other downloaded events as source candidates only. These six are evidence-complete records, not model runs or proof that the broader competition histories are ready. Exclude abandoned/canceled events and separate AET/PEN outcomes unless a reliable source independently supplies the 90-minute score.

The raw response count is a collection count, not a verified training count. Existing history with missing `first_known_at` remains retrospective research material and does not become as-of certified by this supplement.
