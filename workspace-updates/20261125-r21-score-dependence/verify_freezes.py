#!/usr/bin/env python3
"""Verify retained R21 first-issue and ranked-seat bytes without reissuing."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
FORWARD_SHA = "03fbf89faf84312015532a3d935824bfe6e5eb0560c609a2f3654cc873aea33c"
RANKED_SHA = "2b8e50f9248f21685b19f5236c10c6a02fe6926bd52ac3b4da1d4c4b7936cf35"
COMPETITIONS = ("eng.1", "esp.1", "ger.1", "ita.1", "fra.1")
R7_SIZE = 48
STARTED = {"espn:401875009", "espn:401879237", "espn:401882802"}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_record(record: dict) -> str:
    body = {key: value for key, value in record.items() if key != "record_sha256"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha_bytes(encoded)


def instant(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError(f"timestamp lacks UTC offset: {value}")
    return stamp.astimezone(timezone.utc)


def read_verified(folder: Path, ref: dict) -> tuple[dict, str]:
    name = ref["file"]
    if Path(name).name != name:
        raise ValueError(f"nonlocal freeze path: {name}")
    raw = (folder / name).read_bytes()
    record = json.loads(raw)
    digest = sha_record(record)
    if (record.get("record_sha256") != digest or ref.get("sha256") != digest
            or ref.get("id") != record.get("freeze_id") or ref.get("recorded_at") != record.get("recorded_at")):
        raise ValueError(f"freeze checksum/index mismatch: {name}")
    if (record.get("evaluation_slot") != "FIRST_PREMATCH" or record.get("stage") != "prematch"
            or record.get("revision") != 1 or record.get("previous_sha256") is not None):
        raise ValueError(f"not the preserved first prematch issue: {name}")
    return record, sha_bytes(raw)


def verify() -> dict:
    forward_dir = HERE / "forward"
    index_path = forward_dir / "receipts.json"
    index_bytes = index_path.read_bytes()
    if not index_bytes:
        raise ValueError("empty R21 forward index")
    index = json.loads(index_bytes)
    registration, registration_file_sha = read_verified(forward_dir, index["registration"])
    if registration["record_sha256"] != FORWARD_SHA:
        raise ValueError("R21 registration SHA differs from the supplied frozen SHA")
    if registration["recorded_at"] != "2026-11-25T21:17:21.555419+08:00":
        raise ValueError("R21 registration clock differs from the supplied freeze time")
    payload = registration["payload"]
    identity = payload["identity"]
    if payload["track"] != "research-r21-score-dependence-20261125":
        raise ValueError("unexpected R21 registration track")
    if identity["already_started"] != sorted(STARTED) or set(identity["competitions"]) != set(COMPETITIONS):
        raise ValueError("R7 original population exclusions or competition set differ")
    if identity["formal_kpi_eligible"] is not False:
        raise ValueError("R21 research registration must remain nonformal")
    fixtures = payload["fixtures"]
    matches = index["matches"]
    if len(fixtures) != 45 or set(fixtures) != set(matches) or len(set(fixtures)) != len(fixtures):
        raise ValueError("R21 registration is not the 45 unique unstarted R7 targets")
    if len(fixtures) + len(STARTED) != R7_SIZE:
        raise ValueError("R21 population does not reconcile to original R7 48")

    by_comp = {code: {"registered": 0, "market_h2h_total": 0, "both_teams_recent": 0,
                      "candidate_first_changed_vs_r7": 0, "candidate_three_order_changed_vs_r7": 0}
               for code in COMPETITIONS}
    raw_file_hashes = {"forward/receipts.json": sha_bytes(index_bytes)}
    rows = []
    cutoff = instant(registration["recorded_at"])
    for match_id, fixture in fixtures.items():
        ref = matches[match_id]
        record, raw_sha = read_verified(forward_dir, ref)
        raw_file_hashes["forward/" + ref["file"]] = raw_sha
        if record.get("track") != payload["track"] or record.get("match_id") != match_id:
            raise ValueError(f"issue track/match differs: {match_id}")
        if record["payload"].get("registration_sha256") != registration["record_sha256"]:
            raise ValueError(f"issue does not bind to R21 registration: {match_id}")
        actual_fixture = record["fixture"]
        fixture_fields = ("match_id", "cohort", "stage", "kickoff_at", "home", "away")
        if any(actual_fixture.get(k) != fixture.get(k) for k in fixture_fields):
            raise ValueError(f"first issue fixture differs from registered fixture: {match_id}")
        if not (cutoff <= instant(actual_fixture["cutoff_at"]) <= instant(record["recorded_at"])
                < instant(actual_fixture["kickoff_at"])):
            raise ValueError(f"R21 first issue time is outside its prematch window: {match_id}")
        code = fixture["cohort"]
        if code not in by_comp:
            raise ValueError(f"unregistered competition: {code}")
        detail = by_comp[code]
        detail["registered"] += 1
        source = record["payload"]
        evidence = source.get("market_evidence") or {}
        prices = source.get("prices") or {}
        has_market = all(evidence.get(k) and prices.get(k) for k in ("h2h", "total"))
        detail["market_h2h_total"] += int(has_market)
        process = source.get("process") or {}
        bilateral = all((process.get(side) or {}).get("usable", 0) > 0 for side in ("home", "away"))
        detail["both_teams_recent"] += int(bilateral)
        forecasts = source["forecasts"]
        if forecasts["candidate"]["primary"] != forecasts["r7"]["primary"]:
            detail["candidate_first_changed_vs_r7"] += 1
        if forecasts["candidate"]["top3"] != forecasts["r7"]["top3"]:
            detail["candidate_three_order_changed_vs_r7"] += 1
        rows.append({"match_id": match_id, "competition": code, "kickoff_at": fixture["kickoff_at"],
                     "first_issue_sha256": record["record_sha256"], "raw_file_sha256": raw_sha})

    ranked_dir = HERE / "ranked"
    plan_index_bytes = (ranked_dir / "plan.json").read_bytes()
    plan_ref = json.loads(plan_index_bytes)
    ranked_record, ranked_raw_sha = read_verified(ranked_dir, plan_ref)
    raw_file_hashes["ranked/plan.json"] = sha_bytes(plan_index_bytes)
    raw_file_hashes["ranked/" + plan_ref["file"]] = ranked_raw_sha
    if ranked_record["record_sha256"] != RANKED_SHA:
        raise ValueError("R21 ranked-plan SHA differs from the supplied frozen SHA")
    if ranked_record["track"] != "research-ranked-first-scores-r10-registration":
        raise ValueError("unexpected ranked plan track")
    if instant(registration["recorded_at"]) >= instant(ranked_record["recorded_at"]):
        raise ValueError("ranked seat selection predates its source registration")
    ranked_payload = ranked_record["payload"]
    selected = ranked_payload["identity"]["selected"]
    if ranked_payload["identity"]["source_registration"] != registration["record_sha256"]:
        raise ValueError("ranked seats do not bind to the R21 first-issue registration")
    if ranked_payload["fixtures"] != fixtures:
        raise ValueError("ranked plan target fixtures differ from the R21 registration")

    recomputed = {}
    forecast_by_comp = {code: [] for code in COMPETITIONS}
    issue_by_id = {}
    for row in rows:
        issue_by_id[row["match_id"]] = row
    for match_id, ref in matches.items():
        record, _ = read_verified(forward_dir, ref)
        fixture, source = fixtures[match_id], record["payload"]
        forecast_by_comp[fixture["cohort"]].append({
            "match_id": match_id, "kickoff_at": fixture["kickoff_at"],
            "first_probability": source["quality"]["p_first"],
            "primary": source["forecasts"]["candidate"]["primary"],
            "top3": source["forecasts"]["candidate"]["top3"],
            "home": source["home_name"], "away": source["away_name"],
            "first_issue": ref,
        })
    for code in COMPETITIONS:
        ranked_rows = sorted(forecast_by_comp[code],
                             key=lambda r: (-r["first_probability"], instant(r["kickoff_at"]), r["match_id"]))[:3]
        expected = [{k: row[k] for k in ("match_id", "kickoff_at", "first_probability", "primary", "top3", "home", "away", "first_issue")}
                    for row in ranked_rows]
        if selected.get(code) != expected:
            raise ValueError(f"recomputed top-three seats differ: {code}")
        recomputed[code] = len(expected)
    if sum(recomputed.values()) != 15 or any(v != 3 for v in recomputed.values()):
        raise ValueError("expected three independently reproduced seats per competition")

    report = {
        "schema": "r21-frozen-forward-rank-audit-v1",
        "forward_registration_sha256": registration["record_sha256"],
        "forward_registration_recorded_at": registration["recorded_at"],
        "ranked_plan_sha256": ranked_record["record_sha256"],
        "ranked_plan_recorded_at": ranked_record["recorded_at"],
        "original_r7_population": {"registered": R7_SIZE, "already_started": len(STARTED), "issued": len(fixtures)},
        "issued_matches": len(fixtures),
        "seat_count": sum(recomputed.values()),
        "all_seats_recomputed_from_frozen_first_probability": True,
        "formal_kpi_eligible": False,
        "competitions": by_comp,
        "overall": {key: sum(v[key] for v in by_comp.values())
                    for key in next(iter(by_comp.values()))},
        "original_file_sha256": dict(sorted(raw_file_hashes.items())),
        "method": "Read-only checksum, identity and chronology audit; top-three seats sorted from preserved first-issue p_first, kickoff and stable match ID. No receipt was emitted.",
    }
    out_dir = HERE / "verification"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "frozen-forward-rank.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    with (out_dir / "forward-coverage.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["competition", *next(iter(by_comp.values())).keys()],
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows({"competition": code, **values} for code, values in by_comp.items())
    return report


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, ensure_ascii=False))
