# 2026-11-04 data supplement execution

## Collection

- Six ESPN scoreboards returned 740 candidate event records: Europa League 189, Conference League 153, 2026 World Cup 104, AFC Champions League Elite 119, A-League 175, Finland 0. Each response is retained with query timestamp and SHA-256.
- Completed 725 summary requests, covering 719 unique match IDs: ten initial samples plus the full 175-match A-League season and 540 completed fixtures across Europa League, Conference League, World Cup, and AFC. The sample IDs overlap with the full competition batches. All raw files, HTTP times, identifiers and hashes are retained.
- 708 rows have matching event/team/score, an explicit `neutralSite` boolean (all false), a named phase, a two-period format, and a full-time score status. This is retrospective evidence retrieved on 2026-11-04; `first_known_at` remains null. Four additional AET/PEN sample events and non-FT/cancelled rows are excluded.
- A-League season audit: 175 detail responses all 200, 168 pass the stricter inclusion checks. Seven excluded rows remain in the audit with reasons.

## What entered model research

The A-League 168 rows were normalized with ESPN team IDs and per-row source hashes into `/workspace/WCPP/research/all-scope-20261104/numerical-inputs/aus.1/merged-history.json`. The monthly expanding historical reconstruction uses the explicitly labeled research constant because there is no active AUS Current route. It produced 46 predictions after the fixed 120-match warm-up gate; 122 remain warm-up. Top1 was 4/46 for both the reconstructed reference and dynamic Poisson. This is a small retrospective reconstruction, not deployed Current performance or future validation.

Other four competition groups have evidence-verified rows (UEL 184; UECL 146; World Cup 95; AFC Elite 115), but existing competition-router definitions do not support those phases for training. We did not bypass those guards. Within these rows, the phase-specific sample counts are preserved in `strict-training-candidates.json`; none is claimed as a completed fitted route. Finland's sampled ESPN season returned zero events.

No active Current/Test registry, artifact or historical freeze was altered. No market training was performed.
