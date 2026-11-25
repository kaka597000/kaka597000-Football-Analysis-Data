#!/usr/bin/env python3
"""Rebuild and verify 2026/27 four-league fixture artifacts from captured gzip JSON.
Uses Python standard library only; no network access.
Run: python3 verify_calendars.py
Rewrite generated tables from the raw objects: python3 verify_calendars.py --write
"""

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import html
import json
import pathlib
import re
import sys
import unicodedata
from collections import defaultdict
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent
LEAGUES = {
    "esp.1": ("esp", "Spanish LALIGA"),
    "ger.1": ("ger", "German Bundesliga"),
    "ita.1": ("ita", "Italian Serie A"),
    "fra.1": ("fra", "French Ligue 1"),
}
ESPN_LEAGUE_IDS = {"esp.1": "740", "ger.1": "720", "ita.1": "730", "fra.1": "710"}
FOTMOB_IDS = {"esp.1": "87", "ger.1": "54", "ita.1": "55", "fra.1": "53"}
WINDOWS = [
    ("nov27_dec04", "2026-11-27T00:00:00+08:00", "2026-12-04T00:00:00+08:00"),
    ("dec04_dec11", "2026-12-04T00:00:00+08:00", "2026-12-11T00:00:00+08:00"),
]
TZ = ZoneInfo("Asia/Shanghai")
ALIASES = {
    "esp": {"deportivo alaves": "alaves", "deportivo": "deportivo a coruna"},
    "ger": {
        "1 fc union berlin": "union berlin",
        "fc cologne": "koln",
        "1 fc koln": "koln",
        "fc augsburg": "augsburg",
        "bayern munich": "bayern munchen",
        "hamburg sv": "hamburger sv",
        "mainz": "mainz 05",
        "sc freiburg": "freiburg",
        "sc paderborn 07": "paderborn",
        "sv elversberg": "elversberg",
        "tsg hoffenheim": "hoffenheim",
    },
    "ita": {"internazionale": "inter", "ac milan": "milan", "as roma": "roma"},
    "fra": {
        "aj auxerre": "auxerre",
        "as monaco": "monaco",
        "le havre ac": "le havre",
        "stade rennais": "rennes",
    },
}
FIXTURE_FIELDS = ["match_id", "cohort", "stage", "kickoff_at", "home", "away"]
SUSPENDED_MATCH_ID = "401882849"
ATHLETIC_CAPTURE_START = "2026-11-25T12:00:03.600627Z"
ATHLETIC_CAPTURE_SHA256 = (
    "9d88266e51af690f0dc1012319e43247fbbf8c75bc4cd5183642bc90fb3b1e62"
)
CSV_FIELDS = [
    "window",
    "match_id",
    "competition",
    "season",
    "stage",
    "kickoff_at",
    "kickoff_beijing",
    "home_name",
    "away_name",
    "home_espn_id",
    "away_espn_id",
    "home_fotmob_id",
    "away_fotmob_id",
    "fotmob_match_id",
    "espn_round",
    "fotmob_round",
    "espn_source_sha256",
    "fotmob_source_sha256",
    "espn_url",
    "fotmob_url",
    "espn_observed_request_start_utc",
    "espn_observed_response_end_utc",
    "fotmob_observed_request_start_utc",
    "fotmob_observed_response_end_utc",
    "espn_status",
    "espn_time_valid",
    "fotmob_started",
    "fotmob_finished",
    "fotmob_cancelled",
    "fotmob_time_nonplaceholder",
    "espn_home_score",
    "espn_away_score",
    "espn_status_period",
    "espn_status_clock_seconds",
    "fotmob_status_label",
]
STATUS_FIELDS = [
    "window",
    "competition",
    "match_id",
    "home_name",
    "away_name",
    "kickoff_at",
    "espn_status",
    "espn_time_valid",
    "espn_home_score",
    "espn_away_score",
    "espn_status_period",
    "espn_status_clock_seconds",
    "fotmob_status",
    "fotmob_match_id",
    "espn_source_sha256",
    "fotmob_source_sha256",
    "espn_url",
    "fotmob_url",
    "espn_observed_request_start_utc",
    "espn_observed_response_end_utc",
    "fotmob_observed_request_start_utc",
    "fotmob_observed_response_end_utc",
    "official_source_url",
    "official_capture_start_utc",
    "official_capture_sha256",
    "official_observation",
    "fotmob_started",
    "fotmob_finished",
    "fotmob_cancelled",
    "fotmob_time_nonplaceholder",
    "calendar_denominator_included",
    "prematch_first_issue_eligible_now",
    "hold_reason",
]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def parse_utc(value):
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return dt.datetime.fromisoformat(normalized)


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


def teamkey(code, name):
    n = norm(name)
    return ALIASES.get(code, {}).get(n, n)


def read_manifest():
    return json.loads((ROOT / "source-manifest.json").read_text())


def source_record(manifest, comp, provider, year=None):
    for record in manifest["captures"]:
        if record["competition"] != comp or record["source_provider"] != provider:
            continue
        if year is not None and record.get("query_year") != year:
            continue
        if year is None and record.get("query_year") is not None:
            continue
        return record
    raise ValueError(f"missing source record: {comp} {provider} {year}")


def validate_capture_sequence(manifest):
    captures = manifest["captures"]
    if len(captures) != 12:
        raise ValueError(
            f"expected 12 independent calendar captures, found {len(captures)}"
        )
    previous_end = None
    for record in sorted(captures, key=lambda x: x["observed_request_start_utc"]):
        start = parse_utc(record["observed_request_start_utc"])
        end = parse_utc(record["observed_response_end_utc"])
        if record["http_status"] != 200 or not record.get("readback_verified"):
            raise ValueError(
                f"capture not successful/readback-verified: {record['compressed_path']}"
            )
        if record["readback_sha256"] != record["body_sha256"]:
            raise ValueError(
                f"readback SHA mismatch in manifest: {record['compressed_path']}"
            )
        if end < start:
            raise ValueError(
                f"invalid source clock interval: {record['compressed_path']}"
            )
        if previous_end is not None and start < previous_end:
            raise ValueError(
                "source requests overlap; sequential public access is not verified"
            )
        previous_end = end
        if record["source_provider"] == "ESPN" and not record["url"].startswith(
            f"https://site.api.espn.com/apis/site/v2/sports/soccer/{record['competition']}/scoreboard?"
        ):
            raise ValueError("unexpected ESPN source URL")
        if record["source_provider"] == "FotMob" and not record["url"].startswith(
            "https://www.fotmob.com/api/data/leagues?"
        ):
            raise ValueError("unexpected FotMob source URL")


def validate_athletic_official_capture():
    evidence_dir = ROOT / "supplemental-status-evidence"
    captures = [
        json.loads(line)
        for line in (evidence_dir / "captures.jsonl").read_text().splitlines()
    ]
    matches = [
        item for item in captures if item.get("name") == "athletic-official-home"
    ]
    if len(matches) != 1:
        raise ValueError("Athletic Club official capture entry missing or duplicated")
    item = matches[0]
    if (
        item.get("http_status") != 200
        or item.get("url") != "https://www.athletic-club.eus/en/"
        or item.get("request_start_utc") != ATHLETIC_CAPTURE_START
        or item.get("body_sha256") != ATHLETIC_CAPTURE_SHA256
        or not item.get("readback_verified")
    ):
        raise ValueError("Athletic Club official capture metadata mismatch")
    compressed = (evidence_dir / item["gzip_path"]).read_bytes()
    if sha(compressed) != item["gzip_sha256"]:
        raise ValueError("Athletic Club official gzip SHA mismatch")
    body = gzip.decompress(compressed)
    if sha(body) != ATHLETIC_CAPTURE_SHA256:
        raise ValueError("Athletic Club official response SHA mismatch")
    page = html.unescape(body.decode("utf-8", "replace"))
    entry_start = page.find('"id":[0,"1_8579"]')
    entry = page[entry_start : entry_start + 5000] if entry_start >= 0 else ""
    expected_facts = [
        '"id":[0,"1_8579"]',
        '"date":[0,"2026-12-09"]',
        '"time":[0,"20:00"]',
        '"season":[0,"2026-27"]',
        '"matchDay":[0,"8"]',
        '"isMatchPlayed":[0,false]',
        '"hasResult":[0,false]',
        '"isCancelled":[0]',
        '"isPostponed":[0,false]',
        '"name":[0,"Athletic Club"]',
        '"name":[0,"Rayo Vallecano"]',
    ]
    absent = [fact for fact in expected_facts if fact not in entry]
    if absent:
        raise ValueError(
            f"official match entry facts absent from raw capture: {absent}"
        )
    claim = json.loads((evidence_dir / "status-claim.json").read_text())
    official = claim["source_states"]["Athletic_Club_official_site"]
    if (
        claim["fixture"]["match_id"] != "espn:" + SUSPENDED_MATCH_ID
        or not claim["fixture"]["included_in_second_window_denominator"]
        or official["match_id"] != "1_8579"
        or official["body_sha256"] != ATHLETIC_CAPTURE_SHA256
        or official["observed_request_start_utc"] != ATHLETIC_CAPTURE_START
        or official["isPostponed"] is not False
        or claim["assessment"]["first_prematch_issue_allowed_now"] is not False
    ):
        raise ValueError(
            "suspended-fixture evidence summary does not match its capture"
        )


def read_raw(record):
    p = ROOT / record["compressed_path"]
    compressed = p.read_bytes()
    if sha(compressed) != record["compressed_sha256"]:
        raise ValueError(f"compressed SHA mismatch: {p}")
    body = gzip.decompress(compressed)
    if sha(body) != record["body_sha256"]:
        raise ValueError(f"decompressed source SHA mismatch: {p}")
    if len(body) != record["body_bytes"]:
        raise ValueError(f"source byte length mismatch: {p}")
    return json.loads(body)


def load_sources(manifest):
    out = {}
    for comp in LEAGUES:
        esp = []
        for year in (2026, 2027):
            rec = source_record(manifest, comp, "ESPN", year)
            board = read_raw(rec)
            if str(board["leagues"][0]["id"]) != ESPN_LEAGUE_IDS[comp]:
                raise ValueError("ESPN league ID mismatch")
            for ev in board.get("events", []):
                season = ev.get("season") or {}
                if season.get("year") != 2026:
                    continue
                competition = (ev.get("competitions") or [{}])[0]
                sides = {
                    x.get("homeAway"): x for x in competition.get("competitors", [])
                }
                if "home" not in sides or "away" not in sides:
                    raise ValueError(f"incomplete ESPN sides for {ev.get('id')}")
                home, away = sides["home"]["team"], sides["away"]["team"]
                esp.append(
                    {
                        "id": str(ev["id"]),
                        "home_id": str(home["id"]),
                        "away_id": str(away["id"]),
                        "home": home["displayName"],
                        "away": away["displayName"],
                        "kickoff": parse_utc(ev["date"]),
                        "season_slug": season.get("slug"),
                        "status": competition.get("status", {})
                        .get("type", {})
                        .get("name"),
                        "status_completed": competition.get("status", {})
                        .get("type", {})
                        .get("completed"),
                        "status_period": competition.get("status", {}).get("period"),
                        "status_clock_seconds": competition.get("status", {}).get(
                            "clock"
                        ),
                        "time_valid": competition.get("timeValid"),
                        "scores": {
                            "home": str(sides["home"].get("score", "")),
                            "away": str(sides["away"].get("score", "")),
                        },
                        "round": (ev.get("week") or {}).get("number"),
                        "record": rec,
                    }
                )
        # ESPN year boards intentionally overlap only at the requested calendar year; event id remains canonical.
        byid = {}
        for ev in esp:
            if ev["id"] in byid and byid[ev["id"]]["kickoff"] != ev["kickoff"]:
                raise ValueError("duplicate ESPN event ID with conflicting data")
            byid[ev["id"]] = ev
        esp = list(byid.values())
        fr = source_record(manifest, comp, "FotMob")
        fd = read_raw(fr)
        if str(fd["details"]["id"]) != FOTMOB_IDS[comp]:
            raise ValueError("FotMob league ID mismatch")
        fot = []
        fot_ids = set()
        for ev in fd["fixtures"]["allMatches"]:
            if str(ev["id"]) in fot_ids:
                raise ValueError(f"duplicate FotMob match ID {ev['id']}")
            fot_ids.add(str(ev["id"]))
            st = ev["status"]
            home, away = ev["home"], ev["away"]
            fot.append(
                {
                    "id": str(ev["id"]),
                    "home_id": str(home["id"]),
                    "away_id": str(away["id"]),
                    "home": home["name"],
                    "away": away["name"],
                    "kickoff": parse_utc(st["utcTime"]),
                    "round": ev.get("roundName", ev.get("round")),
                    "status": st,
                    "record": fr,
                }
            )
        out[comp] = (esp, fot)
    return out


def in_window(t, lo, hi):
    local = t.astimezone(TZ)
    return (
        dt.datetime.fromisoformat(lo).astimezone(TZ)
        <= local
        < dt.datetime.fromisoformat(hi).astimezone(TZ)
    )


def canonical_events(sources):
    details = []
    status_rows = []
    fixtures = {c: [] for c in LEAGUES}
    daily = []
    season_audit = {
        "schema": "four-league-window-source-audit-v1",
        "windows": [
            {"name": n, "from_inclusive": a, "until_exclusive": b}
            for n, a, b in WINDOWS
        ],
        "competitions": {},
    }
    for comp, (esp, fot) in sources.items():
        code = LEAGUES[comp][0]
        eb = defaultdict(list)
        fb = defaultdict(list)
        for x in esp:
            eb[(teamkey(code, x["home"]), teamkey(code, x["away"]))].append(x)
        for x in fot:
            fb[(teamkey(code, x["home"]), teamkey(code, x["away"]))].append(x)
        if any(len(v) > 1 for v in eb.values()) or any(len(v) > 1 for v in fb.values()):
            raise ValueError(f"duplicate home-away source rows: {comp}")
        keys = set(eb) | set(fb)
        pairs = []
        missing = []
        diffs = []
        unverified = []
        for key in sorted(keys):
            e = eb[key][0] if eb.get(key) else None
            f = fb[key][0] if fb.get(key) else None
            if not e or not f:
                missing.append(
                    {
                        "home_key": key[0],
                        "away_key": key[1],
                        "missing_from": "ESPN" if not e else "FotMob",
                    }
                )
                continue
            if e["kickoff"] != f["kickoff"]:
                pair = {
                    "espn_id": e["id"],
                    "fotmob_id": f["id"],
                    "home": e["home"],
                    "away": e["away"],
                    "espn_kickoff_utc": e["kickoff"].isoformat(),
                    "fotmob_kickoff_utc": f["kickoff"].isoformat(),
                    "espn_time_valid": e["time_valid"],
                    "espn_status": e["status"],
                    "fotmob_status": "finished"
                    if f["status"].get("finished")
                    else ("cancelled" if f["status"].get("cancelled") else "scheduled"),
                    "outside_windows": not any(
                        in_window(e["kickoff"], lo, hi)
                        or in_window(f["kickoff"], lo, hi)
                        for _, lo, hi in WINDOWS
                    ),
                }
                if pair["outside_windows"]:
                    diffs.append(pair)
                if not e["time_valid"] or (
                    f["kickoff"].strftime("%H:%M") == "00:00"
                    and not f["status"].get("finished")
                ):
                    unverified.append(pair)
            pairs.append((e, f))
        # Any one-sided item in windows is an unresolved calendar discrepancy and cannot silently enter fixtures.
        if missing:
            raise ValueError(
                f"full-season cross-source missing rows in {comp}: {len(missing)}"
            )
        window_counts = {}
        for wname, lo, hi in WINDOWS:
            selected = []
            for e, f in pairs:
                ein = in_window(e["kickoff"], lo, hi)
                fin = in_window(f["kickoff"], lo, hi)
                if ein != fin:
                    raise ValueError(
                        f"window boundary disagreement {comp} ESPN {e['id']} FotMob {f['id']}"
                    )
                if not ein:
                    continue
                if e["kickoff"] != f["kickoff"]:
                    raise ValueError(
                        f"window kickoff disagreement {comp} {e['id']} {f['id']}"
                    )
                fs = f["status"]
                suspended_exception = comp == "esp.1" and e["id"] == SUSPENDED_MATCH_ID
                if suspended_exception:
                    if not (
                        e["home"] == "Rayo Vallecano"
                        and e["away"] == "Athletic Club"
                        and e["status"] == "STATUS_SUSPENDED"
                        and e["time_valid"] is True
                        and e["status_period"] == 1
                        and e["status_clock_seconds"] == 1980.0
                        and e["status_completed"] is False
                        and e["scores"] == {"home": "0", "away": "0"}
                        and fs.get("started") is False
                        and fs.get("finished") is False
                        and fs.get("cancelled") is False
                    ):
                        raise ValueError(
                            "documented Rayo-Athletic suspended-match exception no longer matches the raw sources"
                        )
                    hold_reason = "ESPN reports suspended at 33 minutes, 0-0; hold first prematch issue until an official restart time/status is confirmed"
                else:
                    if e["status"] != "STATUS_SCHEDULED" or e["time_valid"] is not True:
                        raise ValueError(
                            f"ESPN event is not a valid scheduled kickoff: {comp} {e['id']}"
                        )
                    if (
                        fs.get("finished") is not False
                        or fs.get("cancelled") is not False
                        or fs.get("started") is not False
                        or f["kickoff"].strftime("%H:%M") == "00:00"
                    ):
                        raise ValueError(
                            f"FotMob event is finished/cancelled/started or placeholder: {comp} {f['id']}"
                        )
                    hold_reason = ""
                if (
                    fs.get("finished") is not False
                    or fs.get("cancelled") is not False
                    or fs.get("started") is not False
                    or f["kickoff"].strftime("%H:%M") == "00:00"
                ):
                    raise ValueError(
                        f"FotMob event is finished/cancelled/started or placeholder: {comp} {f['id']}"
                    )
                status_rows.append(
                    {
                        "window": wname,
                        "competition": comp,
                        "match_id": "espn:" + e["id"],
                        "home_name": e["home"],
                        "away_name": e["away"],
                        "kickoff_at": e["kickoff"].isoformat(),
                        "espn_status": e["status"],
                        "espn_time_valid": e["time_valid"],
                        "espn_home_score": e["scores"]["home"],
                        "espn_away_score": e["scores"]["away"],
                        "espn_status_period": e["status_period"],
                        "espn_status_clock_seconds": e["status_clock_seconds"],
                        "fotmob_status": "finished"
                        if fs.get("finished")
                        else "cancelled"
                        if fs.get("cancelled")
                        else "started"
                        if fs.get("started")
                        else "not_started",
                        "fotmob_started": fs.get("started", False),
                        "fotmob_finished": fs.get("finished", False),
                        "fotmob_cancelled": fs.get("cancelled", False),
                        "fotmob_time_nonplaceholder": f["kickoff"].strftime("%H:%M")
                        != "00:00",
                        "calendar_denominator_included": True,
                        "prematch_first_issue_eligible_now": not suspended_exception,
                        "hold_reason": hold_reason,
                        "fotmob_match_id": "fotmob:" + f["id"],
                        "espn_source_sha256": e["record"]["body_sha256"],
                        "fotmob_source_sha256": f["record"]["body_sha256"],
                        "espn_url": e["record"]["url"],
                        "fotmob_url": f["record"]["url"],
                        "espn_observed_request_start_utc": e["record"][
                            "observed_request_start_utc"
                        ],
                        "espn_observed_response_end_utc": e["record"][
                            "observed_response_end_utc"
                        ],
                        "fotmob_observed_request_start_utc": f["record"][
                            "observed_request_start_utc"
                        ],
                        "fotmob_observed_response_end_utc": f["record"][
                            "observed_response_end_utc"
                        ],
                        "official_source_url": (
                            "https://www.athletic-club.eus/en/"
                            if suspended_exception
                            else ""
                        ),
                        "official_capture_start_utc": ATHLETIC_CAPTURE_START
                        if suspended_exception
                        else "",
                        "official_capture_sha256": (
                            ATHLETIC_CAPTURE_SHA256 if suspended_exception else ""
                        ),
                        "official_observation": (
                            "Athletic Club official homepage lists match 1_8579, Athletic Club vs Rayo Vallecano, 2026-12-09 20:00 local, matchday 8, isMatchPlayed=false, isPostponed=false; it does not document the prior 33-minute suspension or a restart announcement."
                            if suspended_exception
                            else ""
                        ),
                    }
                )
                item = {
                    "match_id": "espn:" + e["id"],
                    "cohort": comp,
                    "stage": "regular",
                    "kickoff_at": e["kickoff"].isoformat(),
                    "home": "espn:" + e["home_id"],
                    "away": "espn:" + e["away_id"],
                }
                fixtures[comp].append(item)
                selected.append((e, f, item, wname))
            window_counts[wname] = len(selected)
        season_audit["competitions"][comp] = {
            "espn_season_rows": len(esp),
            "fotmob_season_rows": len(fot),
            "matched_home_away_rows": len(pairs),
            "missing_rows": missing,
            "duplicate_home_away_keys": 0,
            "raw_timestamp_differences": len(
                [1 for e, f in pairs if e["kickoff"] != f["kickoff"]]
            ),
            "out_of_window_timestamp_differences": len(diffs),
            "out_of_window_time_unverified_rows": len(unverified),
            "confirmed_explicit_scheduled_time_conflicts": sum(
                1
                for e, f in pairs
                if e["kickoff"] != f["kickoff"]
                and e["status"] in ("STATUS_SCHEDULED", "STATUS_POSTPONED")
                and not f["status"].get("finished")
                and e["time_valid"]
                and (f["kickoff"].strftime("%H:%M") != "00:00")
            ),
            "finished_match_timestamp_differences": sum(
                1
                for e, f in pairs
                if e["kickoff"] != f["kickoff"] and e["status"] == "STATUS_FULL_TIME"
            ),
            "out_of_window_differences": diffs,
            "windows": window_counts,
        }
        for e, f, item, wname in [
            z
            for z in [
                (
                    e,
                    f,
                    {
                        "match_id": "espn:" + e["id"],
                        "cohort": comp,
                        "stage": "regular",
                        "kickoff_at": e["kickoff"].isoformat(),
                        "home": "espn:" + e["home_id"],
                        "away": "espn:" + e["away_id"],
                    },
                    w,
                )
                for e, f in pairs
                for w, lo, hi in WINDOWS
                if in_window(e["kickoff"], lo, hi)
            ]
        ]:
            er = e["record"]
            fr = f["record"]
            local = e["kickoff"].astimezone(TZ).isoformat()
            details.append(
                {
                    "window": wname,
                    "match_id": item["match_id"],
                    "competition": comp,
                    "season": "2026/27",
                    "stage": "regular",
                    "kickoff_at": item["kickoff_at"],
                    "kickoff_beijing": local,
                    "home_name": e["home"],
                    "away_name": e["away"],
                    "home_espn_id": item["home"],
                    "away_espn_id": item["away"],
                    "home_fotmob_id": "fotmob:" + f["home_id"],
                    "away_fotmob_id": "fotmob:" + f["away_id"],
                    "fotmob_match_id": "fotmob:" + f["id"],
                    "espn_round": e["round"],
                    "fotmob_round": f["round"],
                    "espn_source_sha256": er["body_sha256"],
                    "fotmob_source_sha256": fr["body_sha256"],
                    "espn_url": er["url"],
                    "fotmob_url": fr["url"],
                    "espn_observed_request_start_utc": er["observed_request_start_utc"],
                    "espn_observed_response_end_utc": er["observed_response_end_utc"],
                    "fotmob_observed_request_start_utc": fr[
                        "observed_request_start_utc"
                    ],
                    "fotmob_observed_response_end_utc": fr["observed_response_end_utc"],
                    "espn_status": e["status"],
                    "espn_time_valid": e["time_valid"],
                    "fotmob_started": f["status"].get("started", False),
                    "fotmob_finished": f["status"].get("finished", False),
                    "fotmob_cancelled": f["status"].get("cancelled", False),
                    "fotmob_time_nonplaceholder": f["kickoff"].strftime("%H:%M")
                    != "00:00",
                    "espn_home_score": e["scores"]["home"],
                    "espn_away_score": e["scores"]["away"],
                    "espn_status_period": e["status_period"],
                    "espn_status_clock_seconds": e["status_clock_seconds"],
                    "fotmob_status_label": "finished"
                    if f["status"].get("finished")
                    else "cancelled"
                    if f["status"].get("cancelled")
                    else "started"
                    if f["status"].get("started")
                    else "not_started",
                }
            )
    for items in fixtures.values():
        items.sort(key=lambda x: (x["kickoff_at"], x["match_id"]))
    details.sort(key=lambda x: (x["competition"], x["kickoff_at"], x["match_id"]))
    # Complete 14-day Beijing calendar per competition and window, including zero-match dates.
    for comp in LEAGUES:
        es, fs = sources[comp]
        for wname, lo, hi in WINDOWS:
            day = dt.date.fromisoformat(lo[:10])
            end = dt.date.fromisoformat(hi[:10])
            while day < end:
                esd = [e for e in es if e["kickoff"].astimezone(TZ).date() == day]
                fsd = [f for f in fs if f["kickoff"].astimezone(TZ).date() == day]
                daily.append(
                    {
                        "competition": comp,
                        "window": wname,
                        "date_beijing": day.isoformat(),
                        "espn_match_count": len(esd),
                        "fotmob_match_count": len(fsd),
                        "espn_match_ids": ";".join(
                            "espn:" + e["id"]
                            for e in sorted(esd, key=lambda x: x["kickoff"])
                        ),
                        "fotmob_match_ids": ";".join(
                            "fotmob:" + f["id"]
                            for f in sorted(fsd, key=lambda x: x["kickoff"])
                        ),
                    }
                )
                day += dt.timedelta(days=1)
    status_rows.sort(key=lambda x: (x["competition"], x["kickoff_at"], x["match_id"]))
    suspended_rows = [
        row for row in status_rows if row["espn_status"] == "STATUS_SUSPENDED"
    ]
    if (
        len(suspended_rows) != 1
        or suspended_rows[0]["match_id"] != "espn:" + SUSPENDED_MATCH_ID
    ):
        raise ValueError("expected exactly the documented suspended Rayo-Athletic row")
    if sum(row["prematch_first_issue_eligible_now"] for row in status_rows) != 78:
        raise ValueError(
            "expected 78 not-started prematch rows and one held suspended row"
        )
    season_audit["window_status_summary"] = {
        "fixture_rows_in_denominator": len(status_rows),
        "not_started_and_currently_prematch_eligible_rows": 78,
        "suspended_held_rows": [
            {
                "match_id": row["match_id"],
                "competition": row["competition"],
                "espn_status": row["espn_status"],
                "score": f"{row['espn_home_score']}-{row['espn_away_score']}",
                "period": row["espn_status_period"],
                "clock_seconds": row["espn_status_clock_seconds"],
                "fotmob_status": row["fotmob_status"],
                "first_issue_eligible_now": False,
                "reason": row["hold_reason"],
            }
            for row in suspended_rows
        ],
    }
    return fixtures, details, daily, season_audit, status_rows


def csv_bytes(rows, fields):
    import io

    s = io.StringIO(newline="")
    w = csv.DictWriter(s, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return s.getvalue().encode()


def generated(manifest, sources):
    fixtures, details, daily, audit, status_rows = canonical_events(sources)
    files = {}
    files["fixtures.json"] = (
        json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n"
    ).encode()
    for comp in LEAGUES:
        files[f"leagues/{comp}.csv"] = csv_bytes(
            [x for x in details if x["competition"] == comp], CSV_FIELDS
        )
    daily_fields = [
        "competition",
        "window",
        "date_beijing",
        "espn_match_count",
        "fotmob_match_count",
        "espn_match_ids",
        "fotmob_match_ids",
    ]
    files["daily-coverage.csv"] = csv_bytes(daily, daily_fields)
    files["window-status.csv"] = csv_bytes(status_rows, STATUS_FIELDS)
    files["full-season-audit.json"] = (
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    ).encode()
    return files, fixtures, audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    manifest = read_manifest()
    validate_capture_sequence(manifest)
    validate_athletic_official_capture()
    sources = load_sources(manifest)
    files, fixtures, audit = generated(manifest, sources)
    errors = []
    expected = sum(
        audit["competitions"][c]["windows"][w] for c in LEAGUES for w, _, _ in WINDOWS
    )
    if expected != 79:
        errors.append(f"window fixture count is {expected}, expected 79")
    for c in LEAGUES:
        actual = sum(1 for x in fixtures[c])
        want = sum(audit["competitions"][c]["windows"][w] for w, _, _ in WINDOWS)
        if actual != want:
            errors.append(f"{c}: fixture list count mismatch")
    for rel, data in files.items():
        target = ROOT / rel
        if args.write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        elif not target.exists() or target.read_bytes() != data:
            errors.append(
                f"generated output differs: {rel} (run with --write to rebuild)"
            )
    if errors:
        print("\n".join("FAIL: " + e for e in errors))
        return 1
    print(
        f"OK: {expected} fixtures; 8 league-window counts; {len(files)} generated table/audit files; all 56 daily rows include empty dates; source gzip hashes and window identities verified."
    )
    for c in LEAGUES:
        print(
            c,
            ", ".join(
                f"{w}={audit['competitions'][c]['windows'][w]}" for w, _, _ in WINDOWS
            ),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
