# R16 first-score seat ranking

This package reproduces the retrospective comparison of raw R7 first-score
probability ranking against the fixed competition-specific calibration, then
verifies the separately frozen R16 prospective seat order against the signed
original R7 first issues.

## Inputs and source

- Original R7 package: `../20261123-prematch-literature/`. Its full manifest
  SHA-256 is recorded in `r7-manifest.sha256`; the verifier checks every file
  named by that manifest.
- Numerical source commit: `source-commit.txt`. The verifier requires an
  explicit `--source` checkout and confirms its Git HEAD and source files.
- Protocol: `protocol.json`, byte-identical to the pinned source protocol.
- The prospective lock is the retained first signed R16 freeze in `forward/`.
  Its `plan.json` points to the original freeze ID and record SHA-256.

## Reproduce the historical package

From the data repository root, with Python 3.12 and `source/requirements.txt`
installed (plus `lightgbm==4.6.0` for the source package import):

```sh
python workspace-updates/20261125-r16-selection/build.py \
  --source /path/to/Football-Analysis \
  --r7 workspace-updates/20261123-prematch-literature \
  --final-verified /path/to/r16-final-verified \
  --final-repeat /path/to/r16-final-repeat \
  --forward /path/to/r16-forward
```

The builder confirms the two retained historic output directories are byte for
byte identical, then performs two independent refits. It requires all discrete
fields, ranks and selected seats to match exactly; floating-point values must
match within `atol=1e-9, rtol=1e-7`. It then rebuilds the descriptive CSV/JSON
tables, verifies the signed forward lock against the original R7 issue records,
and writes the package manifest.

## Verify

```sh
python workspace-updates/20261125-r16-selection/verify.py \
  --source /path/to/Football-Analysis \
  --r7 workspace-updates/20261123-prematch-literature \
  --forward /path/to/r16-forward
```

The historic panel reports 2,686 fixtures over 750 competition/date batches,
416 complete three-seat batches and 334 short batches. The raw and calibrated
rules have 201 and 215 first-score hits respectively; both have zero complete
sweeps (0/416). Individual primary and ordered-trio seat counts, same-fixture
market coverage, and per-competition cold-start/fallback status are in
`replay/`.

The paired complete-batch comparison has zero discordant outcomes, so its
date-cluster bootstrap interval is necessarily `[0, 0]`; that degenerate
interval does not establish equivalence. `replay/uncertainty.json` gives an
exact binomial upper bound for the discordance rate and a separately labelled
descriptive filled-seat primary-hit interval.

The forward lock was recorded at 2026-11-25 18:05:59 Beijing time. It covers
39 whole eligible competition/Beijing-date slates and 150 matches from the
192-fixture signed R7 registration. Its earliest eligible kickoff is
2026-11-26 01:45 Beijing time. The verifier recomputes both selected-seat
orders and checks every cited R7 issue hash and timestamp. This research lock
does not replace any user-facing R7 selections.
