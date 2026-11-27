"""Rebuild the paired J1 shot history from the retained provider archive."""

import argparse
from contextlib import closing
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tarfile


PANEL_SHA256 = "b9c883ee9055b0e562e8ad5b482a26dab219d1c0d6bd76ae0c16f74a42f23edb"
WINDOWS = (
    ("before_2025", "0000-01-01", "2025-01-01"),
    ("2025_h1", "2025-01-01", "2025-07-01"),
    ("2025_h2", "2025-07-01", "2026-01-01"),
    ("2026_through_nov21", "2026-01-01", "2026-11-22"),
)
RESULTS = """
SELECT m.match_id, m.date, m.kickoff_utc, m.home_id, m.away_id, h.name AS home,
       a.name AS away, m.h90, m.a90, o.source_key, o.score_scope, o.observed_at,
       o.first_known_at, o.raw_json, s.sha256, s.path
FROM matches m JOIN match_evidence e USING (match_id)
JOIN observations o USING (obs_id) JOIN sources s USING (source_id)
JOIN teams h ON h.team_id = m.home_id JOIN teams a ON a.team_id = m.away_id
WHERE m.competition = 'jpn.1' AND m.stage = 'regular' AND m.status = 'completed'
      AND o.provider = '5dollar'
ORDER BY m.date, m.match_id, o.source_key
"""


def archive_rows(panel):
    if sha256(panel.read_bytes()).hexdigest() != PANEL_SHA256:
        raise ValueError("R5 archive hash differs")
    with tarfile.open(panel) as packed:
        rows = map(json.loads, packed.extractfile("panel.jsonl"))
        return {row["id"]: row for row in rows if row["stage"] == "regular"}


def timestamp(value):
    time = datetime.fromisoformat(value)
    if time.utcoffset() is None:
        raise ValueError("missing source timezone")
    return time


@lru_cache
def page(root, name, digest):
    body = (root / name).read_bytes()
    if sha256(body).hexdigest() != digest:
        raise ValueError(f"provider page hash differs for {name}")
    payload = json.loads(body)
    if payload["http_status"] != 200:
        raise ValueError(f"unsuccessful archived response for {name}")
    games = {str(row["id"]): row for row in payload["response"]["data"]}
    return games, payload["query_time"]


def original_teams(db):
    return dict(db.execute("""
        SELECT p.provider_id, COALESCE(r.new_id, p.team_id) FROM provider_team_ids p
        LEFT JOIN team_redirects r ON r.old_id = p.team_id WHERE p.provider = '5dollar'
    """))


def panel_ids(db):
    ids = {}
    for match, source in db.execute("""
        SELECT DISTINCT e.match_id, o.source_key FROM match_evidence e
        JOIN matches m USING (match_id) JOIN observations o USING (obs_id)
        WHERE m.competition = 'jpn.1' AND m.stage = 'regular' AND o.provider = 'espn'
    """):
        ids.setdefault(match, set()).add(source)
    return ids


def shot_pair(stats, field):
    pair = tuple(stats[field][side] for side in ("home", "away"))
    if any(type(value) is not int or value < 0 for value in pair):
        raise ValueError(f"invalid paired {field}")
    return pair


def matched_observation(row, game, teams, root):
    name = Path(row["path"]).name
    games, capture = page(root, name, row["sha256"])
    raw = games[row["source_key"].removeprefix("5dollar:")]
    source_team_ids = [str(raw["teams"][side]["id"]) for side in ("home", "away")]
    score = [raw["goals"][side] for side in ("home", "away")]
    if (raw != json.loads(row["raw_json"]) or raw["status_code"] != "full"
            or row["score_scope"] != "regulation_90" or game["score_basis"] != "regulation_90"
            or [teams[key] for key in source_team_ids] != [row["home_id"], row["away_id"]]
            or timestamp(raw["kickoff_utc"]) != timestamp(row["kickoff_utc"])
            or timestamp(row["observed_at"]) != timestamp(capture)
            or timestamp(capture) <= timestamp(raw["kickoff_utc"])
            or [row[key] for key in ("date", "home", "away")] != [game[key] for key in ("date", "home", "away")]
            or score != [row["h90"], row["a90"]] or score != [game["home_goals"], game["away_goals"]]):
        raise ValueError(f"provider fixture identity or evidence differs for {game['id']}")
    home_sot, away_sot = shot_pair(raw["statistics"], "shots_on_target")
    home_off, away_off = shot_pair(raw["statistics"], "shots_off_target")
    return dict(id=game["id"], competition=game["competition"], date=game["date"],
                home=game["home"], away=game["away"], actual=score, kickoff_utc=raw["kickoff_utc"],
                home_sot=home_sot, away_sot=away_sot, home_shots_off_target=home_off,
                away_shots_off_target=away_off, provider="5dollar", source_id=row["source_key"],
                source_observed_at=capture, source_first_known_at=row["first_known_at"],
                source_page=name, source_sha256=row["sha256"], result_source_sha256=game["source_sha256"])


def extract(panel, database, raw_root):
    population = archive_rows(panel)
    observations = {}
    source_rows = 0
    uri = database.resolve().as_uri() + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        ids, teams = panel_ids(db), original_teams(db)
        for row in db.execute(RESULTS):
            source_rows += 1
            match_ids = ids.get(row["match_id"], set()).intersection(population)
            if len(match_ids) != 1:
                raise ValueError(f"unclear R5 fixture binding for {row['source_key']}")
            key, = match_ids
            shot = matched_observation(row, population[key], teams, raw_root)
            if observations.setdefault(key, shot) != shot:
                raise ValueError(f"conflicting retained provider evidence for {key}")
    unique = sorted(observations.values(), key=lambda row: (row["date"], row["id"]))
    coverage = [dict(window=name, fixtures=sum(start <= row["date"] < end for row in population.values()),
                     paired=sum(start <= row["date"] < end for row in unique))
                for name, start, end in WINDOWS]
    if (len(unique) != sum(row["paired"] for row in coverage)
            or len(population) != sum(row["fixtures"] for row in coverage)):
        raise ValueError("fixture outside the registered archive date segments")
    status = dict(panel_sha256=PANEL_SHA256, source_rows=source_rows, unique_fixtures=len(unique),
                  first_known_at=sum(row["source_first_known_at"] is not None for row in unique), coverage=coverage,
                  source_pages=dict(sorted({row["source_page"]: row["source_sha256"] for row in unique}.items())))
    return unique, status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    records, summary = extract(args.panel, args.db, args.raw)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "paired-sot.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records))
    (args.out / "coverage.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
