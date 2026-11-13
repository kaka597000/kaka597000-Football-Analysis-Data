# Live rollout receipt — run 43389637073

The authorized `collect` workflow completed successfully. The data repository wrote back state in commit `5294fd7c4799a264b9232e1d52518916834c0313`, parented by the requested deployment commit `0f82cbabb52455a7686ab8e8c6a8bbc846f98821`.

The workflow used collector revision `1257fdde7b6746b7ba6d2aa919382214a2cfb589`, with base/training revision `6639867d502a2dfe53a9a235c8761f8ee6b91533`. Its persisted `future/runtime-revisions/43389637073-1.json` records the six overlay file hashes and confirms locked protocol sources verified, inference source unchanged, and active model unchanged. Manifest hashes and locked-file digests are in `receipt.json`.

Collection executed 49 requests, 48 successful. It recorded 48 successful scoreboard attempts across 16 competitions, three scoreboards per competition. It saw zero events and zero new result observations; collection coverage is incomplete. `scoreboard-attempts.json` is present in the writeback commit with 48 entries and sequence 48.

The KOR1 candidate fallback made four requests and added six candidate rows, but coverage remains `CANDIDATE_ONLY_UNVERIFIED_PHASE_VENUE` and the rows are not training-eligible. The market channel had no credential, made zero requests, verified zero quotes, and saved no market snapshot. The run is operationally successful but source coverage is partial; it does not establish model readiness or model improvement.

The workflow also updated existing forward-review populations. This run created zero new captures; the update is not a new prediction or model-performance result. No credentials or raw error payloads are included.

KOR1 source detail: 5dollar returned HTTP 403. API-Football returned HTTP 200 but zero results and an empty response, so authentication was not verified. FotMob fallback supplied six candidate rows; those remain unverified and ineligible for training. Raw source error text is omitted.
