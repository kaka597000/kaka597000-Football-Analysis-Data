#!/usr/bin/env python3
"""Match the R22 replay to independent ordered ranks and summarize score coverage."""

import argparse
import csv
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPLAY = Path("replay/reference")
ORDERED_RANKS = Path("verification/independent/ordered-ranks.csv")
LEAGUES = ("eng.1", "esp.1", "ger.1", "ita.1", "fra.1")
WINDOW_COUNTS = {"evaluation": 1752, "recent": 500, "november_extension": 48}
ARMS = {"r7": "r7", "market": "market", "r21": "r21", "r22": "candidate"}


def read_ordered_ranks(path):
    required = {"competition", "match_id", "date", "window", "actual", *ARMS}
    index = {}
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        if not required.issubset(fields) or len(fields) != len(set(fields)):
            raise ValueError("ordered-ranks CSV has missing or duplicate columns")
        for row in reader:
            if None in row or any(not row[field] for field in required):
                raise ValueError(f"incomplete ordered-ranks CSV row at line {reader.line_num}")
            key = row["competition"], row["match_id"]
            if key in index:
                raise ValueError(f"duplicate fixture in ordered-ranks CSV: {key}")
            if key[0] not in LEAGUES or row["window"] not in WINDOW_COUNTS:
                raise ValueError(f"unexpected competition or window in ordered-ranks CSV: {key}")
            index[key] = row
    return index


def hit_summary(games, size):
    # Include zero-hit arms in every group. All hit rates share the group's n.
    counts = Counter(dict.fromkeys((*ARMS, "r7_or_market", "union"), 0))
    misses = Counter()
    for actual, picks in games:
        hits = {arm for arm, scores in picks.items() if actual in scores[:size]}
        counts.update(hits)
        counts["r7_or_market"] += bool(hits & {"r7", "market"})
        counts["union"] += bool(hits)
        if not hits:
            misses[actual] += 1
    return {
        "hits": dict(counts),
        "rates": {arm: count / len(games) for arm, count in counts.items()},
        "uncovered": sum(misses.values()),
        "miss_scores": dict(sorted(misses.items(), key=lambda item: (-item[1], item[0]))),
    }


def summarize(replay, ordered_ranks):
    unmatched = read_ordered_ranks(ordered_ranks)
    archives = {path.parent.name: path for path in replay.glob("main/*/forecasts.jsonl.gz")}
    if set(archives) != set(LEAGUES):
        raise ValueError(f"expected five competition forecast archives, found {sorted(archives)}")

    seen = set()
    groups = defaultdict(list)
    for league in LEAGUES:
        with gzip.open(archives[league], "rt", encoding="utf-8") as stream:
            for game in map(json.loads, stream):
                key = game["cohort"], game["id"]
                if key[0] != league:
                    raise ValueError(f"fixture in the wrong replay competition archive: {key}")
                if key in seen:
                    raise ValueError(f"duplicate fixture in replay: {key}")
                seen.add(key)
                row = unmatched.pop(key, None)
                if row is None:
                    raise ValueError(f"replay fixture missing from ordered-ranks CSV: {key}")

                actual = "-".join(map(str, game["actual"]))
                window = game["window"]
                if (game["date"], window, actual) != (row["date"], row["window"], row["actual"]):
                    raise ValueError(f"fixture date, window or actual score differs: {key}")
                picks = {}
                for arm, field in ARMS.items():
                    forecast = game["forecast"][field]
                    scores = forecast["top3"]
                    if len(scores) != 3 or len(set(scores)) != 3 or forecast["primary"] != scores[0]:
                        raise ValueError(f"invalid replay primary or top three for {arm}: {key}")
                    if scores != row[arm].split("|"):
                        raise ValueError(f"ordered scores differ for {arm}: {key}")
                    picks[arm] = scores
                groups[window, league].append((actual, picks))
                groups[window, "total"].append((actual, picks))

    if unmatched:
        raise ValueError(f"{len(unmatched)} CSV fixtures missing from replay, first: {min(unmatched)}")
    window_counts = {window: len(groups[window, "total"]) for window in WINDOW_COUNTS}
    if window_counts != WINDOW_COUNTS:
        raise ValueError(f"unexpected historical window populations: {window_counts}")

    windows = {}
    for window in WINDOW_COUNTS:
        windows[window] = {}
        for league in (*LEAGUES, "total"):
            games = groups[window, league]
            if not games:
                raise ValueError(f"no matched fixtures for {window}, {league}")
            windows[window][league] = {
                "n": len(games),
                "first": hit_summary(games, 1),
                "three": hit_summary(games, 3),
            }
    return {
        "package_inputs": {"replay": REPLAY.as_posix(), "ordered_ranks": ORDERED_RANKS.as_posix()},
        "matched": len(seen),
        "windows": windows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replay",
        type=Path,
        default=PACKAGE / REPLAY,
        help="historical replay directory, such as the output of an R22 retraining",
    )
    parser.add_argument("--ordered-ranks", type=Path, default=PACKAGE / ORDERED_RANKS)
    parser.add_argument("--output", type=Path, help="JSON report destination (defaults to stdout)")
    args = parser.parse_args()

    result = summarize(args.replay, args.ordered_ranks)
    payload = (json.dumps(result, indent=2) + "\n").encode("utf-8")
    if args.output is None:
        sys.stdout.buffer.write(payload)
    else:
        args.output.write_bytes(payload)


if __name__ == "__main__":
    main()
