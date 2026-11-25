#!/usr/bin/env python3
"""Independently verify source calendars, four registered windows and historical first issues."""
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import shutil

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
COMPS = ("uefa.europa", "uefa.europa.conf")
WINDOWS = {
    "window_1": ("2026-11-26T00:00:00+08:00", "2026-12-03T00:00:00+08:00"),
    "window_2": ("2026-12-03T00:00:00+08:00", "2026-12-12T00:00:00+08:00"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_bytes())


def canonical_sha(record):
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode()
    return sha(encoded)


def dt(value):
    value = value.replace("Z", "+00:00")
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("timezone required: " + value)
    return result


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_archive_json(tar, member):
    stream = tar.extractfile(member)
    if stream is None:
        raise ValueError("missing archive member: " + member)
    return json.load(stream)


def verify_manifest():
    manifest = read_json(ROOT / "manifest.json")
    actual = {
        p.relative_to(ROOT).as_posix(): sha(p.read_bytes())
        for p in ROOT.rglob("*")
        if p.is_file() and p.name != "manifest.json"
        and "__pycache__" not in p.relative_to(ROOT).parts
    }
    require(manifest.get("schema") == "UEFA-THURSDAY-TWO-WINDOWS-PACKAGE-1"
            and manifest.get("files") == actual, "package file manifest differs")
    return actual


def verify_source_rebuild():
    """Replay the complete frozen public-source package offline, including odds clocks."""
    archive = ROOT / "archives/uefa-thursday-20261125-5c03f3517796c580.tar.gz"
    with tempfile.TemporaryDirectory(prefix="uefa-thursday-source-") as temporary:
        source = Path(temporary) / "source"
        source.mkdir()
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(source, filter="data")
        source_archive = source / archive.name
        shutil.copyfile(archive, source_archive)
        shutil.copyfile(archive.with_name(archive.name + ".sha256"),
                        source_archive.with_name(source_archive.name + ".sha256"))
        subprocess.run([sys.executable, "-B", "archive.py", "replay", str(source_archive)],
                       cwd=source, check=True, stdout=subprocess.DEVNULL)
        derived = source / "derived"
        manifest = read_json(source / "source-manifest.json")
        captures = {c["path"]: c for c in manifest["sources"]}
        fixtures = list(csv.DictReader((derived / "calendar.csv").open(encoding="utf-8", newline="")))
        quotes = [json.loads(line) for line in (derived / "first-round-draftkings.jsonl").read_text().splitlines()]
        upstream_pairs = list(csv.DictReader((source / "alternatives/infersports-same-book.csv").open(
            encoding="utf-8", newline="")))
        return source, manifest, captures, fixtures, quotes, upstream_pairs


def verify_registration_and_rows(fixtures, captures):
    registration = read_json(ROOT / "evidence/window-registration.json")
    require(registration["schema"] == "UEFA-THURSDAY-TWO-COMPETITIONS-TWO-WINDOWS-REGISTRATION-1"
            and registration["parent_pr"] == 57
            and registration["parent_head"] == "6a014e9f2225a2aaad029e0f8dab17d07148a52d"
            and registration["no_comprehensive_forecast_created"] is True
            and registration["no_three_seats_selected"] is True
            and registration["no_model_promotion"] is True,
            "registration scope or parent pin differs")
    rows = [json.loads(line) for line in (ROOT / "evidence/fixtures.jsonl").read_text().splitlines()]
    require(len(rows) == 72 and len({r["stable_match_id"] for r in rows}) == 72,
            "calendar rows are not 72 unique official fixtures")
    source_rows = {r["stable_match_id"]: r for r in fixtures}
    require(set(source_rows) == {r["stable_match_id"] for r in rows},
            "frozen fixture rows differ from rebuilt calendar")
    for row in rows:
        source = dict(source_rows[row["stable_match_id"]])
        source["window"] = {"first": "window_1", "next": "window_2"}[source["window"]]
        require(row == source, "fixture row differs from original source rebuild: " + row["stable_match_id"])
        comp = row["competition"]
        begin, end = WINDOWS[row["window"]]
        kickoff = dt(row["kickoff_bjt"])
        require(begin <= kickoff.isoformat() < end,
                "kickoff outside registered BJT interval: " + row["stable_match_id"])
        require(row["stage"] == "League Phase" and row["identity_sources_agree"] == "True",
                "stage or three-provider fixture identity differs")
        require(row["stable_match_id"] == "uefa:" + row["uefa_event_id"],
                "stable ID is not the original UEFA event ID")
        for provider in ("uefa", "espn", "fotmob"):
            capture = captures[row[provider + "_path"]]
            require(capture["sha256"] == row[provider + "_sha256"]
                    and capture["response_received_utc"] == row[provider + "_response_received_utc"]
                    and capture["url"] == row[provider + "_url"]
                    and dt(capture["request_started_utc"]) <= dt(capture["response_received_utc"])
                    and dt(capture["response_received_utc"]) < dt(row["kickoff_utc"]),
                    "provider response clock/hash mismatch: " + row["stable_match_id"] + " " + provider)
        stage = registration["stages"][comp + ":" + row["window"]]
        require(row["stable_match_id"] in stage["stable_match_ids"]
                and row["uefa_stage_id"] == stage["uefa_stage_id"]
                and row["fotmob_round"] == stage["fotmob_round"],
                "stage registration ID differs: " + row["stable_match_id"])
    require(set(registration["stages"]) == {
        "uefa.europa:window_1", "uefa.europa:window_2",
        "uefa.europa.conf:window_1", "uefa.europa.conf:window_2"},
        "four competition windows are not registered")
    for key, stage in registration["stages"].items():
        subset = [r for r in rows if r["competition"] == stage["competition"] and r["window"] == stage["window"]]
        require(len(subset) == stage["fixture_count"] == 18
                and set(stage["stable_match_ids"]) == {r["stable_match_id"] for r in subset},
                "window slate incomplete: " + key)
        targets = stage["required_registered_coverage"]
        require(targets == {
            "unique_first_score": 1.0,
            "top3_all_three_scores": 1.0,
            "wdl": 1.0,
            "selected_seat_count": 3,
            "all_three_seat_first_score_sweep": 1.0,
            "genuine_bookmaker_quote_clock_and_total_line": 0.80,
            "nonpush_total_settlement_full_win_rate_minimum": 0.70,
        }, "registered minima differ: " + key)
        require(stage["selected_seats"] == [] and stage["selected_seat_status"] == "not_selected_by_this_registration"
                and stage["phase_status"] == "registered_pending"
                and stage["market_observation"]["threshold_pass"] == "not_evaluated",
                "registration incorrectly grants seats or phase pass: " + key)
    return registration, rows


def verify_research_issues(rows):
    comparison = list(csv.DictReader((ROOT / "evidence/issued-firsts-comparison.csv").open(
        encoding="utf-8", newline="")))
    require(len(comparison) == 72 and {r["stable_match_id"] for r in comparison}
            == {r["stable_match_id"] for r in rows}, "research first-issue comparison population differs")
    row_by_id = {r["stable_match_id"]: r for r in rows}
    with tarfile.open(ROOT / "archives/research-first-issues.tar.gz", "r:gz") as tar:
        names = set(tar.getnames())
        r7_receipts = load_archive_json(tar, "r7/receipts.json")
        r13_receipts = load_archive_json(tar, "r13/receipts.json")
        r7_registration = load_archive_json(tar, "r7/registration.json")
        r13_registration = load_archive_json(tar, "r13/registration.json")
        require(r7_registration["freeze_id"] == r7_receipts["registration"]["id"]
                and r7_registration["record_sha256"] == r7_receipts["registration"]["sha256"]
                and r13_registration["track"] == "research-r13-domestic-form-20261125-registration"
                and r13_registration["record_sha256"] == r13_receipts["registration"]["sha256"],
                "historical research registration receipt differs")
        r7_count = r13_count = 0
        for row in comparison:
            fixture = row_by_id[row["stable_match_id"]]
            mid = "espn:" + fixture["espn_event_id"]
            r7_ref = r7_receipts["matches"].get(mid)
            r7_path = "r7/issues/" + r7_ref["file"] if r7_ref else None
            if r7_ref:
                require(r7_path in names, "missing original R7 issue: " + mid)
                raw = tar.extractfile(r7_path).read()
                rec = json.loads(raw)
                fc = rec["payload"]["forecasts"]["candidate"]
                require(rec["record_sha256"] == r7_ref["sha256"] == canonical_sha(rec)
                        and rec["evaluation_slot"] == "FIRST_PREMATCH"
                        and rec["track"] == "research-prematch-continuation-20261123"
                        and rec["match_id"] == mid
                        and dt(rec["recorded_at"]) < dt(fixture["kickoff_utc"])
                        and row["r7_freeze_id"] == rec["freeze_id"]
                        and row["r7_record_sha256"] == rec["record_sha256"]
                        and row["r7_primary"] == fc["primary"]
                        and row["r7_top3"] == "|".join(fc["top3"])
                        and row["r7_model_sha256"] == rec["payload"]["model_sha256"],
                        "R7 first issue reference or prediction differs: " + mid)
                r7_count += 1
                require(row["r7_status"] == "issued_first", "R7 status label differs: " + mid)
            else:
                require(row["r7_status"] == "no_first_issue_for_fixture" and not row["r7_freeze_id"]
                        and not row["r7_primary"], "missing R7 record was filled: " + mid)
            r13_ref = r13_receipts["matches"].get(mid)
            if r13_ref:
                member = "r13/issues/" + r13_ref["file"]
                require(member in names, "missing original R13 issue: " + mid)
                raw = tar.extractfile(member).read()
                rec = json.loads(raw)
                fc = rec["payload"]["forecasts"]["candidate"]
                require(rec["record_sha256"] == r13_ref["sha256"] == canonical_sha(rec)
                        and rec["evaluation_slot"] == "FIRST_PREMATCH"
                        and rec["track"] == "research-r13-domestic-form-20261125"
                        and rec["match_id"] == mid
                        and dt(rec["recorded_at"]) < dt(fixture["kickoff_utc"])
                        and row["r13_freeze_id"] == rec["freeze_id"]
                        and row["r13_record_sha256"] == rec["record_sha256"]
                        and row["r13_primary"] == fc["primary"]
                        and row["r13_top3"] == "|".join(fc["top3"])
                        and row["r13_recipe_sha256"] == rec["payload"]["recipe_sha256"]
                        and float(row["r13_score_dose"]) == rec["payload"]["doses"]["score"]
                        and float(row["r13_wdl_dose"]) == rec["payload"]["doses"]["wdl"]
                        and float(row["r13_total_dose"]) == rec["payload"]["doses"]["total"],
                        "R13 first issue or actual fitted dose differs: " + mid)
                r13_count += 1
                require(row["r13_status"] == "issued_first", "R13 status label differs: " + mid)
            else:
                require(row["r13_status"] == "no_first_issue_for_fixture" and not row["r13_freeze_id"]
                        and not row["r13_primary"], "missing R13 record was filled: " + mid)
        require(r7_count == r13_count == 36, "actual R7/R13 research first issue count differs")
        # Both existing research tracks cover only the first scheduled round; no round-six issue is implied.
        for comp in COMPS:
            first = [r for r in comparison if r["competition"] == comp and r["window"] == "window_1"]
            second = [r for r in comparison if r["competition"] == comp and r["window"] == "window_2"]
            require(all(r["r7_status"] == r["r13_status"] == "issued_first" for r in first)
                    and all(r["r7_status"] == r["r13_status"] == "no_first_issue_for_fixture" for r in second),
                    "R7/R13 actual coverage must remain separated by window")
    return r7_count, r13_count


def verify_market_coverage(rows, source_quotes, captures, registration):
    compare = {r["stable_match_id"]: r for r in csv.DictReader(
        (ROOT / "evidence/issued-firsts-comparison.csv").open(encoding="utf-8", newline=""))}
    quote_by_id = {r["stable_match_id"]: r for r in source_quotes}
    require(len(source_quotes) == 36 and len(quote_by_id) == 36,
            "the original market snapshot does not cover exactly 36 first-window matches")
    shops = {}
    quote_times = 0
    for row in source_quotes:
        capture = captures[row["source_raw_path"]]
        require(capture["sha256"] == row["source_sha256"]
                and capture["request_started_utc"] == row["source_request_utc"]
                and capture["response_received_utc"] == row["source_response_utc"]
                and capture["http_status"] == 200
                and dt(capture["response_received_utc"]) < dt(row["kickoff_utc"]),
                "market response metadata differs: " + row["espn_event_id"])
        mid = row["stable_match_id"]
        if row["quote_time_utc"]:
            quote_times += 1
        if compare[mid]["r13_recorded_at"]:
            require(dt(capture["request_started_utc"]) > dt(compare[mid]["r13_recorded_at"]),
                    "later market snapshot was captured before the R13 issue unexpectedly")
    # Strict coverage uses a bookmaker row's own explicit clock and a complete same-book line.
    strict = sum(bool(r["quote_time_utc"]) and r["both_totals_and_line"] for r in source_quotes)
    require(quote_times == strict == 0, "an explicit bookmaker quote clock was missed or inferred")
    coverage = read_json(ROOT / "evidence/market-coverage.json")
    require(coverage["strict_bookmaker_quote_time_available"] == 0
            and coverage["window_1"]["complete_same_bookmaker_1x2_ou_line"] == 35
            and coverage["window_1"]["provider_quote_clock"] == 0
            and coverage["window_2"]["complete_same_bookmaker_1x2_ou_line"] == 0
            and coverage["window_2"]["provider_quote_clock"] == 0
            and coverage["ou_nonpush_gate"]["eligible_nonpush_settlements"] == 0
            and coverage["ou_nonpush_gate"]["status"].startswith("not_evaluated"),
            "strict market coverage or unsettled OU status is inaccurate")
    return dict(market_fixture_snapshots=36, complete_same_bookmaker_1x2_ou_line=35,
                explicit_provider_quote_clock=0, strict_clock_line_coverage=0.0,
                nonpush_settlements=0)


def verify_upstream_market_clock_evidence(rows, source_pairs):
    """Verify the separate InferSports upstream odds clocks against captured raw rows."""
    coverage = read_json(ROOT / "evidence/upstream-market-fixture-coverage.json")
    require(coverage["attribution"]["market_data_provider"] == "InferSports"
            and coverage["attribution"]["field"] == "odds[i].as_of"
            and "not a bookmaker-issued timestamp" in coverage["attribution"]["semantics"]
            and "does not contain a separate Euclid execution receipt" in coverage["attribution"]["Euclid_claim"],
            "upstream quote clocks or Euclid execution provenance misattributed")
    raw_archive = ROOT / coverage["raw_archive"]
    with tarfile.open(raw_archive, "r:gz") as tar:
        members = {m.name: m for m in tar.getmembers()}
        odds_paths = sorted(n for n in members if n.startswith("raw/alternative/evt_")
                            and n.endswith("-odds.json"))
        require(len(odds_paths) == 36, "upstream raw response archive is not 36 fixtures")
        fixture_by_id = {r["stable_match_id"]: r for r in rows}
        fixture_by_infer_id = {r["infer_event_id"]: r for r in coverage["fixture_rows"]}
        source_to_fixture = {}
        observed_fixture_ids = set()
        raw_by_path = {}
        meta_by_path = {}
        for path in odds_paths:
            body = tar.extractfile(path).read()
            data = json.loads(body)
            mid = "infer:" + data["event_id"]
            sidecar_path = path.removesuffix(".json") + ".meta.json"
            require(sidecar_path in members, "missing per-response acquisition sidecar: " + path)
            meta = json.loads(tar.extractfile(sidecar_path).read())
            crosswalk = fixture_by_infer_id.get(data["event_id"])
            require(crosswalk is not None, "upstream event ID not mapped to a registered UEFA fixture: " + mid)
            fixture = fixture_by_id.get(crosswalk["stable_match_id"])
            require(fixture is not None and fixture["uefa_event_id"] == crosswalk["uefa_event_id"]
                    and fixture["espn_event_id"] == crosswalk["espn_event_id"]
                    and fixture["fotmob_event_id"] == crosswalk["fotmob_event_id"],
                    "upstream event crosswalk differs from official three-source identity: " + mid)
            require(meta["sha256"] == sha(body) and meta["path"] == path
                    and meta["request_started_utc"] <= meta["response_received_utc"]
                    and dt(meta["response_received_utc"]) < dt(fixture["kickoff_utc"])
                    and data["stale"] is False,
                    "upstream response hash, chronology, or stale marker invalid: " + mid)
            observed_fixture_ids.add(fixture["stable_match_id"])
            source_to_fixture[path] = fixture
            raw_by_path[path] = data
            meta_by_path[path] = meta
            markets = data["odds"]
            pair_rows = [q for q in markets if q.get("status") == "open"
                         and q.get("period") == "full_time" and q.get("format") == "decimal"
                         and q.get("bookmaker") in {"crown", "hkjc", "m8bet", "macau", "nova88", "sbobet"}
                         and q.get("market_type") in {"1x2", "totals"}
                         and isinstance(q.get("prices"), dict)
                         and all(type(q["prices"].get(k)) in (int, float)
                                 and q["prices"][k] > 1 and q["prices"][k] != float("inf")
                                 for k in ({"home", "draw", "away"} if q["market_type"] == "1x2"
                                           else {"over", "under"}))
                         and q.get("as_of") and dt(q["as_of"]) <= dt(meta["response_received_utc"])
                         and (dt(meta["response_received_utc"]) - dt(q["as_of"])).total_seconds() <= 3600]
            pairs = {}
            for q in pair_rows:
                key = (q["bookmaker"], q["market_type"], q.get("line"))
                pairs.setdefault(key, q)
            # Every fixture needs at least one common bookmaker and a valid total line with both clocks fresh.
            money = {book: q for (book, kind, line), q in pairs.items() if kind == "1x2"}
            totals = [(book, q) for (book, kind, line), q in pairs.items()
                      if kind == "totals" and isinstance(line, (int, float)) and line > 0]
            require(any(book in money for book, _ in totals),
                    "fixture lacks same-book full-time 1X2 and total with both upstream clocks within one hour: "
                    + fixture["stable_match_id"])
        first_ids = {r["stable_match_id"] for r in rows if r["window"] == "window_1"}
        require(observed_fixture_ids == first_ids,
                "upstream odds archive does not map 1:1 to first window")

    require(len(source_pairs) == 491, "original all-pair source table has unexpected denominator")
    calculated_pairs = []
    for pair in source_pairs:
        market_path = pair["source_path"]
        raw = raw_by_path.get(market_path)
        meta = meta_by_path.get(market_path)
        require(raw is not None and meta is not None and pair["source_sha256"] == meta["sha256"],
                "source pair references missing raw capture or has a wrong response SHA")
        odds = raw["odds"]
        a, b = int(pair["moneyline_raw_index"]), int(pair["totals_raw_index"])
        require(a < len(odds) and b < len(odds), "source market row index outside raw response")
        money, total = odds[a], odds[b]
        row_sha = lambda obj: sha(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":")).encode())
        received = dt(meta["response_received_utc"])
        money_age = (received - dt(money["as_of"])).total_seconds()
        total_age = (received - dt(total["as_of"])).total_seconds()
        same_clock = dt(money["as_of"]) == dt(total["as_of"])
        both_fresh = max(money_age, total_age) <= 3600
        require(money["market_type"] == "1x2" and total["market_type"] == "totals"
                and money["bookmaker"] == total["bookmaker"] == pair["bookmaker"]
                and money["prices"] == {"home": float(pair["home_decimal"]),
                                         "draw": float(pair["draw_decimal"]),
                                         "away": float(pair["away_decimal"])}
                and total["prices"] == {"over": float(pair["over_decimal"]),
                                         "under": float(pair["under_decimal"])}
                and str(total.get("line")) == pair["total_line"]
                and money["as_of"] == pair["moneyline_quote_time"]
                and total["as_of"] == pair["totals_quote_time"]
                and row_sha(money) == pair["moneyline_raw_row_sha256"]
                and row_sha(total) == pair["totals_raw_row_sha256"]
                and round(money_age, 6) == round(float(pair["moneyline_age_seconds"]), 6)
                and round(total_age, 6) == round(float(pair["totals_age_seconds"]), 6)
                and str(same_clock) == pair["same_quote_time"]
                and str(both_fresh) == pair["both_within_1h_at_receipt"],
                "all-pair row differs from source markets or acquisition clock")
        calculated_pairs.append(pair)

    fixtures_with_pairs = {p["stable_match_id"] for p in calculated_pairs}
    fixtures_fresh = {p["stable_match_id"] for p in calculated_pairs
                      if p["both_within_1h_at_receipt"] == "True"}
    fixtures_equal = {p["stable_match_id"] for p in calculated_pairs
                      if p["same_quote_time"] == "True"}
    selected_source_pairs = [p for p in calculated_pairs
                             if p["same_quote_time"] == "True" and p["both_within_1h_at_receipt"] == "True"]
    require(len(fixtures_with_pairs) == len(fixtures_fresh) == len(fixtures_equal) == 36
            and len(selected_source_pairs) == 35
            and len({p["stable_match_id"] for p in selected_source_pairs}) == 20,
            "independently recalculated complete, fresh and identical-clock market counts differ")

    pairs = list(csv.DictReader((ROOT / "evidence/upstream-market-matched-pairs.csv").open(
        encoding="utf-8", newline="")))
    require(len(pairs) == 35 and len({r["stable_match_id"] for r in pairs}) == 20,
            "equal-clock, within-one-hour pair list differs from claimed count")
    require(pairs == selected_source_pairs,
            "published equal-clock pairs do not match the independently verified all-pair source table")
    for pair in pairs:
        require(pair["same_quote_time"] == "True" and pair["both_within_1h_at_receipt"] == "True"
                and pair["moneyline_quote_time"] == pair["totals_quote_time"]
                and max(float(pair["moneyline_age_seconds"]), float(pair["totals_age_seconds"])) <= 3600,
                "published matched pair does not have identical fresh upstream clocks")
        market_path = pair["source_path"]
        raw = raw_by_path[market_path]
        odds = raw["odds"]
        a, b = int(pair["moneyline_raw_index"]), int(pair["totals_raw_index"])
        require(a < len(odds) and b < len(odds)
                and sha(json.dumps(odds[a], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
                    == pair["moneyline_raw_row_sha256"]
                and sha(json.dumps(odds[b], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
                    == pair["totals_raw_row_sha256"]
                and odds[a]["as_of"] == odds[b]["as_of"] == pair["moneyline_quote_time"]
                and odds[a]["bookmaker"] == odds[b]["bookmaker"] == pair["bookmaker"],
                "matched-pair raw row reference differs")
    expected = {
        "registered_fixtures": 36,
        "fixtures_with_same_book_pair": 36,
        "fixtures_with_both_clocks_within_1h": 36,
        "fixtures_with_equal_clocks_within_1h": 20,
        "equal_clock_pairs_within_1h": 35,
    }
    require(all(coverage[k] == v for k, v in expected.items()), "upstream clock coverage counts differ")
    return {"upstream_odds_clock_fixtures_with_same_book_1x2_total_within_1h": 36,
            "identical_upstream_clock_fixtures_within_1h": 20,
            "identical_upstream_clock_pairs_within_1h": 35,
            "direct_bookmaker_issued_clock_claimed": False,
            "separate_euclid_execution_receipt_archived": False}


def verify_native_routes():
    state = read_json(ROOT / "evidence/native-model-status.json")
    registry_path = REPO / state["parent_registry_path"]
    registry = read_json(registry_path)
    require(sha(registry_path.read_bytes()) == state["parent_registry_sha256"],
            "parent native model registry hash differs")
    require(all(not state["competitions"][c]["registry_key_present"]
                and c not in registry["models"]
                and state["competitions"][c]["current"] == "not_registered"
                and state["competitions"][c]["test"] == "not_registered"
                and state["competitions"][c]["execution"] == "not_run_in_this_package"
                for c in COMPS), "native Current/Test state misreported")
    weights = read_json(ROOT / "evidence/method-weight-references.json")
    table_path = REPO / weights["r13_weight_table_path"]
    require(sha(table_path.read_bytes()) == weights["r13_weight_table_sha256"],
            "R13 forward weight-table hash differs")
    table = {r["competition"]: r for r in csv.DictReader(table_path.open(encoding="utf-8", newline=""))}
    for comp in COMPS:
        item = weights["competitions"][comp]["R13"]["registered_fitted_forward_weights"]
        original = table[comp]
        for key, value in item.items():
            require(str(original[key]) == str(value), "R13 actual forward weight differs: " + comp + " " + key)
    return dict(native_current_routes=0, native_test_routes=0,
                R7_actual_weight_ids={c: weights["competitions"][c]["R7"]["model_sha256_values"] for c in COMPS},
                R13_actual_recipes={c: weights["competitions"][c]["R13"]["recipe_sha256_values"] for c in COMPS})


def verify():
    manifest = verify_manifest()
    source_root, source_manifest, captures, source_fixtures, source_quotes, source_upstream_pairs = verify_source_rebuild()
    registration, rows = verify_registration_and_rows(source_fixtures, captures)
    r7, r13 = verify_research_issues(rows)
    market = verify_market_coverage(rows, source_quotes, captures, registration)
    upstream = verify_upstream_market_clock_evidence(rows, source_upstream_pairs)
    native = verify_native_routes()
    return {
        "status": "PASS",
        "fixture_count": len(rows),
        "registered_windows": len(registration["stages"]),
        "fixtures_per_window": 18,
        "R7_actual_research_first_issues": r7,
        "R13_actual_research_first_issues": r13,
        "window_2_R7_first_issues": 0,
        "window_2_R13_first_issues": 0,
        "native_current_test_execution_receipts": 0,
        "selected_seats_created": 0,
        **market,
        **upstream,
        **native,
        "package_files": len(manifest),
        "source_capture_rows": len(source_manifest["sources"]),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
