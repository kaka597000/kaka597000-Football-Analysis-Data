# kor.1 source routing

K League 1 stays registered as `kor.1` in `config/scopes.json`. This route does not use ESPN, and this repo does not add a Korea ESPN slug.

`config/kor1-sources.json` is the collection map:

- Primary: 5DollarFootballAPI competition `2270596712` (fixtures, results, Bet365 odds, standings, stats; history window starts at 2018).
- Fallback: API-Football unique `K League 1` + `South-Korea` lookup (runtime-verified returned ID; old `219` was Austria 2. Liga), used only when the primary request fails or the returned competition is not K League 1.
- Credential environment variables: `WCPP_5DOLLAR_API_KEY`, `WCPP_API_FOOTBALL_KEY`. Values stay in GitHub Actions secrets.

The unattended collect cron `17 */6 * * *` is unchanged (four runs a day, same job as the other leagues). That job still calls the pinned Football-Analysis collector for every other scope. The collector uses the competition code as an ESPN path, so the workflow removes `kor.1` from the file for that call only and restores `config/scopes.json` before the commit. `runtime/collect_kor1.py` then collects `kor.1`.

Each kor.1 run is capped at 6 requests: current fixtures (with inline odds and stats when 5Dollar returns them), standings, and one history page walking back toward 2018. The API-Football fallback reads the current season (fixtures, standings, and one Bet365 odds page) and does not page the 2018 history. Odds from API-Football are kept only when the bookmaker name is Bet365.

Observations are appended under `kor1/`. They are not written to `normalized-results.jsonl`, so the scheduled trainer does not refit `kor.1` from this feed. `scopes.json` is left byte-for-byte unchanged aside from that temporary in-job omission, because the trainer fingerprints each cohort with its scope object.

A-League (`aus.1`) and J1 (`jpn.1`) stay on the existing ESPN collector.

No replacement numeric ID is guessed or pinned. Resolve name/country uniquely, then validate fixture identity using the returned ID. A valid league lookup does not prove the configured plan permits the current season; such denial remains a failed audited collection, not empty success. Existing cron, credentials and Current remain unchanged.
