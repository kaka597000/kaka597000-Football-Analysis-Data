"""Audit the mirrored Understat quantities used by R23 without match outcomes."""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import math
from pathlib import Path

LEAGUES = ("eng.1", "esp.1", "ger.1", "ita.1", "fra.1")
SOURCE_SHA = "63f853739198298cbbde9dfce2cb02c582cb9dccb4070215c51453325f553bd5"


def exposure(row):
    fields = ("xG", "npxG", "xGA", "npxGA")
    raw = row.get("source_history_sides", {})
    try:
        values = [[raw[s][f] for f in fields] for s in ("home", "away")]
        if any(isinstance(x, bool) for side in values for x in side):
            return "invalid_value", None
        home, away = ([float(x) for x in side] for side in values)
    except (KeyError, TypeError, ValueError):
        return "missing_value", None
    if any(not math.isfinite(x) or x < 0 for x in home + away):
        return "invalid_value", None
    h, a = home[0]-home[1], away[0]-away[1]
    back_h, back_a = away[2]-away[3], home[2]-home[3]
    if min(h, a, back_h, back_a) < -0.002:
        return "negative_difference", None
    if max(abs(h-back_h), abs(a-back_a)) > 0.002:
        return "mirror_mismatch", None
    return "valid", (max(0.0,h), max(0.0,a))


def audit(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError("Understat event bytes differ from the pinned source")
    leagues = {c: Counter() for c in LEAGUES}
    dates = {c: [] for c in LEAGUES}
    seen = set()
    for text in raw.splitlines():
        row = json.loads(text)
        code, key = row["competition"], (row["competition"], str(row["source_match_id"]))
        if code not in leagues or key in seen:
            raise ValueError(f"unexpected or duplicate event: {key}")
        seen.add(key)
        group = leagues[code]
        group["matches"] += 1
        dates[code].append(date.fromisoformat(row["date"][:10]).isoformat())
        reason, sides = exposure(row)
        group[reason] += 1
        if sides is not None:
            group["valid_team_observations"] += 2
            group["positive_team_exposure"] += sum(x > 0.002 for x in sides)
            group["matches_with_positive_exposure"] += any(x > 0.002 for x in sides)
    return {"understat_events_sha256": SOURCE_SHA, "total_fixtures": len(seen),
            "positive_for_audit": "xG - npxG above 0.002; this count does not change the fitted signal",
            "leagues": {code: dict(stats, first_date=min(dates[code]), last_date=max(dates[code]))
                        for code, stats in leagues.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.events), indent=2, sort_keys=True))
