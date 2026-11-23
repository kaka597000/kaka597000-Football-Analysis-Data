# Historical FIFA World Cup score inputs

`fifa.world.jsonl` contains 372 regulation-time match rows from six complete men's senior FIFA World Cup editions. The registered partitions are 2014 blind test (64), 2010 development (64), and 1994/1998/2002/2006 training (52/64/64/64). Stage counts cover each edition's full tournament schedule, including group stage, round of 16, quarterfinals, semifinals, third-place match and final as applicable.

## Sources and score rules

The collector uses the OpenFootball `worldcup.json` GitHub repository's `worldcup-full.json` for each edition, retrieved through the GitHub API, plus the ESPN yearly scoreboard for the same edition. Raw API blobs, decoded OpenFootball JSON, ESPN responses, per-request HTTP metadata and SHA-256 hashes are retained under `raw/`; `raw-manifest.json` hashes all retained bytes. The panel includes both source references on each row.

OpenFootball's ordinary score list is used only when the match has no extra-time marker and is reconciled to ESPN's final scoreboard. For matches that reached extra time or penalties, the 90-minute result is reconstructed from goal times through minute 90, including stoppage time, while excluding extra-time goals and shootout kicks. Where OpenFootball lacked goal-time details, ESPN scoring-event minutes were used; an ET/PEN match with no goal events and a 0-0 post-ET result is labeled 0-0. All 341 ordinary full-time scores reconciled to ESPN. All 31 extra-time/penalty outcomes reconciled to ESPN's post-extra-time final score, and 21 rows with goal-minute events available in both sources independently match at 90 minutes. The per-row `score_method` records which path was used.

Home and away teams follow the ESPN event's explicit `homeAway` designation, matched to the OpenFootball fixture by the unordered team pair. The historical ESPN records do not provide a `neutralSite` value; `neutral` is therefore null for these rows rather than inferred from the host country. Market fields are null; no odds or totals were collected.

Run `python collect.py` to repeat public requests and retain fresh snapshots, then `python build_panel.py` to rebuild the panel and indexes from the captured bytes. No model training or forecast analysis is included.
