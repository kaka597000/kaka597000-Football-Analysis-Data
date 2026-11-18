"""Replay the two immutable five-league archives, evaluate one later season, and fit the frozen trial."""

import argparse
from collections import Counter
import csv
from datetime import datetime
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import tarfile

import numpy as np
from scipy.stats import poisson

TRAIN_END = "2025-08-01T00:00:00Z"
CURRENT_CHECK = "2026-11-14T00:00:00Z"
TRIAL_CUTOFF = "2026-11-18T00:00:00Z"
LEAGUES = {"E0": "eng.1", "D1": "ger.1", "F1": "fra.1", "I1": "ita.1", "SP1": "esp.1"}
ARMS = ("current", "market", "market_cohort")
COLS = ("B365CH", "B365CD", "B365CA", "B365C>2.5", "B365C<2.5")
APPENDIX = Path("workspace-updates")
ARCHIVES = {
    "quotes": (
        "20261105-remaining-nine-market/parts/research.tar.gz.part000",
        "ebe1acee81f2909b8d0c5f9cf6c535c543ef3c656c502b1aecbc0c194366b655",
    ),
    "2425": (
        "20261112-elo-kelly/diagnostic-results.tar.gz",
        "predictions.json",
        "2125307c034717c8f67c0051140c2c17420df5f57731088e25fa65b727e6f33c",
    ),
    "2526": (
        "20261112-post32/elo-independent-temporal.tar.gz",
        "elo-fixed-temporal-v3/goals-only-predictions.json",
        "3b580e86cfb92595941eb72422f85217f84587fca40b3bfe83f52b10bbc29ebe",
    ),
}


def write(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def dump_rows(path, rows):
    body = "".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
        for row in rows
    )
    path.write_bytes(gzip.compress(body.encode(), mtime=0))


def load_proxies(data):
    quote_path, expected = ARCHIVES["quotes"]
    raw = (data / APPENDIX / quote_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("quote archive SHA256 differs")
    prefix = "WCPP/research/remaining-nine-20261105/raw/"
    rows, ledger = [], {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        sources = {
            f.name[len(prefix) :]: archive.extractfile(f).read()
            for f in archive
            if f.isfile() and f.name.startswith(prefix) and f.name.endswith(".csv")
        }
    for season in ("2425", "2526"):
        path, member, expected = ARCHIVES[season]
        with tarfile.open(data / APPENDIX / path) as archive:
            pred = archive.extractfile(member).read()
        if hashlib.sha256(pred).hexdigest() != expected:
            raise ValueError("original predictions SHA256 differs")
        files = {}
        for league in LEAGUES:
            filename = f"{season}_{league}.csv"
            source = sources[filename]
            src_sha = hashlib.sha256(source).hexdigest()
            files[league] = (list(csv.DictReader(source.decode("utf-8-sig").splitlines())), src_sha)
            ledger[filename] = {
                "sha256": src_sha,
                "url": f"https://www.football-data.co.uk/mmz4281/{season}/{league}.csv",
            }
        for prediction in json.loads(pred):
            league = prediction["league"]
            line = prediction["source_line"]
            matches, checksum = files[league]
            match = matches[line - 2]
            day = datetime.strptime(match["Date"], "%d/%m/%Y").date().isoformat()
            if (
                checksum != prediction["source_sha256"]
                or match["Div"] != league
                or day != prediction["date"]
                or [int(match["FTHG"]), int(match["FTAG"])] != [prediction["hg"], prediction["ag"]]
            ):
                raise ValueError("prediction does not match immutable source row")
            h, d, a, o, u = (float(match[k]) for k in COLS)
            if min(h, d, a, o, u) <= 1 or not np.isfinite([h, d, a, o, u]).all():
                raise ValueError("incomplete panel in audited historical population")
            rows.append(
                {
                    "match_id": prediction["id"],
                    "cohort": LEAGUES[league],
                    "game_date": day,
                    "season": season,
                    "historical_proxy": True,
                    "home_goals": prediction["hg"],
                    "away_goals": prediction["ag"],
                    "rates": prediction["models"]["goals"]["lambda"],
                    "home": match["HomeTeam"],
                    "away": match["AwayTeam"],
                    "market": {
                        "h2h": {"home": h, "draw": d, "away": a},
                        "total": {"line": 2.5, "over": o, "under": u},
                    },
                    "source_line": line,
                    "source_file": f"{season}_{league}.csv",
                }
            )
    return rows, ledger


def materialize(row):
    # Preserve the published independent Poisson laws to numerical precision on 0..25.
    rates = np.asarray(row["rates"])
    grid = np.arange(26)
    matrix = poisson.pmf(grid[:, None], rates[None, :])
    joint = np.outer(matrix[:, 0], matrix[:, 1])
    if not np.isclose(joint.sum(), 1.0, rtol=0, atol=1e-10):
        raise ValueError("Poisson matrix support insufficient")
    return dict(row, current_matrix=joint / joint.sum())


def evaluate(model, artifact, rows):
    predictions = []
    for row in rows:
        market = row["market"]
        h, a = row["home_goals"], row["away_goals"]
        if row.get("historical_proxy"):
            matrices = model.apply_historical_proxy(
                artifact, row["current_matrix"], market, cohort=row["cohort"], game_date=row["game_date"]
            )
        else:
            matrices = model.apply(
                artifact, row["current_matrix"], market, cohort=row["cohort"], cutoff_at=row["cutoff_at"]
            )
        day = row["game_date"] if row.get("historical_proxy") else row["kickoff_at"][:10]
        item = {
            "match_id": row["match_id"],
            "cohort": row["cohort"],
            "date": day,
            "actual": [h, a],
            "arms": {},
        }
        for arm, matrix in matrices.items():
            # Direct half-goal line has two possible settlements; live Asian lines use the full settlement routine.
            line = market["total"]["line"] if market else None
            pick = model.score_picks(matrix, line=line)
            actual_side = "home" if h > a else "away" if a > h else "draw"
            direction = pick["total"]["direction"] if pick["total"] else None
            settlement = None
            if line is not None:
                legs = (line,) if float(line * 2).is_integer() else (line - 0.25, line + 0.25)
                net = sum(int(np.sign(h + a - x)) for x in legs) / len(legs)
                settlement = {1: "win", 0.5: "half_win", 0: "push", -0.5: "half_loss", -1: "loss"}[
                    net * (1 if direction == "over" else -1)
                ]
            item["arms"][arm] = {
                "primary": pick["primary"],
                "wdl": pick["wdl"],
                "wdl_probabilities": pick["wdl_probabilities"],
                "total": direction,
                "line": line,
                "primary_hit": int(pick["primary"] == f"{h}-{a}"),
                "wdl_hit": int(pick["wdl"] == actual_side),
                "settlement": settlement,
                "exact_score_probability": float(matrix[h, a]),
                "actual_wdl_probability": pick["wdl_probabilities"][actual_side],
            }
        predictions.append(item)
    return predictions


def summarize(rows):
    if not rows:
        return {"n": 0}
    result = {"n": len(rows), "by_cohort_population": dict(Counter(r["cohort"] for r in rows)), "arms": {}}
    for arm in ARMS:
        obs = [r["arms"][arm] for r in rows]
        counts = Counter(v["settlement"] for v in obs if v["settlement"])
        nonpush = sum(counts.values()) - counts["push"]
        result["arms"][arm] = {
            "primary_hits": sum(v["primary_hit"] for v in obs),
            "wdl_hits": sum(v["wdl_hit"] for v in obs),
            "score_log_loss": sum(-math.log(max(v["exact_score_probability"], 1e-300)) for v in obs)
            / len(obs),
            "wdl_log_loss": sum(-math.log(max(v["actual_wdl_probability"], 1e-300)) for v in obs)
            / len(obs),
            "totals": dict(counts),
            "totals_eligible": sum(counts.values()),
            "totals_non_push": nonpush,
            "strict_full_win_rate": counts["win"] / nonpush if nonpush else None,
        }
    result["paired"] = {}
    for control, arm in (("current", "market"), ("market", "market_cohort"), ("current", "market_cohort")):
        values = {}
        for metric in ("primary_hit", "wdl_hit", "settlement"):
            if metric == "settlement":
                sample = [
                    r
                    for r in rows
                    if all(r["arms"][x][metric] not in (None, "push") for x in (control, arm))
                ]
                diff = [
                    int(r["arms"][arm][metric] == "win") - int(r["arms"][control][metric] == "win")
                    for r in sample
                ]
            else:
                sample = rows
                diff = [r["arms"][arm][metric] - r["arms"][control][metric] for r in sample]
            dates = sorted({r["date"] for r in sample})
            blocks = {d: [0, 0] for d in dates}
            for r, v in zip(sample, diff):
                b = blocks[r["date"]]
                b[0] += v
                b[1] += 1
            interval = None
            if len(dates) >= 2:
                b = np.asarray(list(blocks.values()))
                rng = np.random.default_rng(20261118)
                sums = b[rng.integers(len(b), size=(2000, len(b)))].sum(axis=1)
                interval = np.quantile(sums[:, 0] / sums[:, 1], [0.025, 0.975]).tolist()
            values[metric] = {
                "n": len(diff),
                "gained": diff.count(1),
                "lost": diff.count(-1),
                "net_hits": sum(diff),
                "date_block_95pct_rate_interval": interval,
            }
        result["paired"][control + "_vs_" + arm] = values
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "data", "out"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--historical-only", action="store_true")
    args = parser.parse_args()
    sys.path[:0] = [str(args.source.resolve()), str(args.source.resolve() / "runtime")]
    from runtime.research_program import three_arm_model as model

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    proxies, ledger = load_proxies(args.data.resolve())
    full = [materialize(r) for r in proxies]
    fit_rows = [r for r in full if r["season"] == "2425"]
    test = [r for r in full if r["season"] == "2526"]
    assert len(fit_rows) == 1299 and len(test) == 1737
    first = model.fit(fit_rows, cutoff_at=TRAIN_END, allow_historical_proxy=True)
    pred = evaluate(model, first, test)
    write(out / "season-training-artifact.json", first)
    dump_rows(out / "season-holdout.jsonl.gz", pred)
    write(
        out / "historical-sources.json",
        {
            "archives": ARCHIVES,
            "files": ledger,
            "book": "Bet365",
            "columns": COLS,
            "timestamps": "Closing prices. Source does not give individual quote timestamps or within-book simultaneity.",
            "baseline": "Original date-separated goals-only Poisson rate predictions; not deployed Current.",
            "population": {
                "2425": "1299 eligible archived diagnostics through March 16, 2025, not a full season.",
                "2526": "1737 eligible previously researched goals-only forecasts out of 1752 source fixtures.",
            },
        },
    )
    report = {
        "validation": "Previously researched seasons. One fixed date-separated comparison; quote timing not certified.",
        "train_cutoff": TRAIN_END,
        "evaluation_dates": [min(r["game_date"] for r in test), max(r["game_date"] for r in test)],
        "fit_n": len(fit_rows),
        "market_weight": first["market_weight"],
        "season": summarize(pred),
        "by_league": {
            c: summarize([r for r in pred if r["cohort"] == c]) for c in sorted({r["cohort"] for r in pred})
        },
        "cohort_development_in_european_proxy_holdout": "No genuine as-of frozen Current available before the 2025 training cut. C uses zero correction.",
    }
    write(out / "season-validation.json", report)
    if args.historical_only:
        return
    raw = out / "actual_current.jsonl.gz"
    real = [json.loads(v) for v in gzip.decompress(raw.read_bytes()).splitlines()]
    early = model.fit(full + real, cutoff_at=CURRENT_CHECK, allow_historical_proxy=True)
    clock = datetime.fromisoformat(CURRENT_CHECK.replace("Z", "+00:00"))
    later = [
        r
        for r in real
        if datetime.fromisoformat(r["cutoff_at"].replace("Z", "+00:00")) >= clock
        and datetime.fromisoformat(r["observed_at"].replace("Z", "+00:00"))
        <= datetime.fromisoformat(TRIAL_CUTOFF.replace("Z", "+00:00"))
    ]
    checks = evaluate(model, early, later)
    dump_rows(out / "frozen-current-holdout.jsonl.gz", checks)
    write(out / "early-calibration-artifact.json", early)
    write(
        out / "frozen-current-validation.json",
        {
            "fitted_at_cutoff": CURRENT_CHECK,
            "training_evidence": early["training_by_source"],
            "scope": "Development replay of previous first freezes at their original cutoffs, not new future scores.",
            "results": summarize(checks),
        },
    )
    artifact = model.fit(full + real, cutoff_at=TRIAL_CUTOFF, allow_historical_proxy=True)
    write(out / "artifact.json", artifact)
    print(
        "artifact",
        artifact["n"],
        artifact["market_weight"],
        artifact["cohort_calibration_n"],
        artifact["cohorts"].get("bra.1"),
    )


if __name__ == "__main__":
    main()
