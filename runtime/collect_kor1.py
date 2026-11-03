"""Bounded K League 1 collection: 5Dollar primary, API-Football fallback.

The pinned Football-Analysis collector maps every scopes.json competition code
onto an ESPN path. kor.1 stays in that file and is omitted only for that call.
This script never requests ESPN and never appends training rows.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ALLOWED_HOSTS = {"api.5dollarfootballapi.com", "v3.football.api-sports.io"}
CONFIG_NAME = "kor1-sources.json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_config(state_dir):
    path = Path(state_dir) / "config" / CONFIG_NAME
    config = json.loads(path.read_text())
    if config.get("cohort") != "kor.1" or config.get("competition") != "kor.1":
        raise ValueError("kor.1 identity required")
    if config.get("espn") is not False:
        raise ValueError("kor.1 ESPN collection is not allowed")
    primary = config["primary"]
    fallback = config["fallback"]
    if primary.get("provider") != "5dollar" or int(primary["competition_id"]) != 2270596712:
        raise ValueError("primary provider must be 5Dollar competition 2270596712")
    if (fallback.get("provider") != "api-football" or fallback.get("competition_id") is not None
            or fallback.get("league_name") != "K League 1" or fallback.get("country") != "South-Korea"):
        raise ValueError("fallback must resolve the unique South-Korea K League 1 identity")
    for item in (primary, fallback):
        host = urlsplit(item["base_url"]).hostname
        if host not in ALLOWED_HOSTS or urlsplit(item["base_url"]).scheme != "https":
            raise ValueError("unsupported provider host")
    return config


def is_k_league_1(name, country=""):
    """True for the men's first division label, false for cups and K League 2."""
    text = " ".join(str(part or "") for part in (name, country)).lower()
    compact = text.replace(" ", "").replace("-", "").replace("_", "")
    if any(token in compact for token in ("kleague2", "k리그2", "kleaguechallenge", "k2league")):
        return False
    if any(token in text for token in ("k league 2", "k-league 2", "challenge", " cup", "fa cup")):
        return False
    korea = "korea" in text or "한국" in text or "kr" == text.strip()
    first = any(token in compact for token in ("kleague1", "k리그1", "k리그원")) or "k league 1" in text
    bare = compact in {"kleague", "k리그"} or text.strip() in {"k league", "k-league"}
    if first:
        return True
    return bare and (korea or "league" in text or "리그" in text)


def espn_scopes(scopes):
    """Drop kor.1 from the list the ESPN collector will read. Do not invent a slug."""
    if not isinstance(scopes, list):
        raise ValueError("scope list required")
    found = [row for row in scopes if row.get("competition") == "kor.1" or row.get("cohort") == "kor.1"]
    if len(found) != 1 or found[0].get("competition") != "kor.1":
        raise ValueError("kor.1 must remain in scopes.json exactly once")
    kept = [row for row in scopes if row is not found[0]]
    if len(kept) != len(scopes) - 1:
        raise ValueError("espn scope filter changed more than kor.1")
    if any(row.get("competition") == "kor.1" or row.get("cohort") == "kor.1" for row in kept):
        raise ValueError("kor.1 still visible to the espn collector")
    return kept


def omit_espn(state_dir):
    path = Path(state_dir) / "config" / "scopes.json"
    scopes = json.loads(path.read_text())
    path.write_text(json.dumps(espn_scopes(scopes), ensure_ascii=False, indent=2) + "\n")


def _score(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 30:
        return None
    return value


def _stage(value):
    if isinstance(value, int):
        return "regular"
    text = str(value or "").lower()
    if any(token in text for token in ("playoff", "play-off", "final", "relegation", "promotion", "cup")):
        return None
    return "regular"


def _row(provider, competition_id, match_id, kickoff, status, goals, home_id, away_id,
         home_name, away_name, odds, statistics, bookmaker, captured_at, source_url):
    date = kickoff[:10] if isinstance(kickoff, str) and len(kickoff) >= 10 else None
    return {
        "cohort": "kor.1",
        "competition": "kor.1",
        "stage": "regular",
        "provider": provider,
        "provider_competition_id": competition_id,
        "match_id": match_id,
        "kickoff_at": kickoff,
        "date": date,
        "home_id": home_id,
        "away_id": away_id,
        "home_name": home_name,
        "away_name": away_name,
        "status": status,
        "goals": goals,
        "odds": odds,
        "statistics": statistics,
        "bookmaker": bookmaker,
        "training_eligible": False,
        "score_basis": "NOT_ADMITTED_TO_TRAINING",
        "espn": False,
        "known_at": captured_at,
        "source_url": source_url,
    }


def five_dollar_rows(payload, competition_id, captured_at, source_url):
    rows = []
    for item in payload if isinstance(payload, list) else []:
        league = item.get("league") or {}
        if int(league.get("id") or competition_id) != int(competition_id):
            continue
        if not is_k_league_1(league.get("name"), (league.get("country") or {}).get("name", "")):
            # List rows repeat the league name. A missing name still belongs to the checked id.
            if league.get("name"):
                continue
        if _stage(item.get("round")) is None:
            continue
        teams = item.get("teams") or {}
        home, away = teams.get("home") or {}, teams.get("away") or {}
        status = str(item.get("status") or "")
        code = str(item.get("status_code") or "")
        goals = None
        if status == "finished" and code in {"", "full"}:
            pair = item.get("goals") or {}
            home_goals, away_goals = _score(pair.get("home")), _score(pair.get("away"))
            if home_goals is not None and away_goals is not None:
                goals = {"home": home_goals, "away": away_goals}
        odds = item.get("odds") if isinstance(item.get("odds"), dict) else None
        statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else item.get("stats")
        if not isinstance(statistics, dict):
            statistics = None
        match_id = item.get("id")
        if isinstance(match_id, bool) or not isinstance(match_id, int):
            continue
        rows.append(_row(
            "5dollar", int(competition_id), f"5dollar:{match_id}", item.get("kickoff_utc"), status,
            goals, f"5dollar:{home.get('id')}", f"5dollar:{away.get('id')}", home.get("name"),
            away.get("name"), odds, statistics, "bet365" if odds else None, captured_at, source_url))
    return rows


def api_football_rows(payload, competition_id, captured_at, source_url):
    rows = []
    for item in payload if isinstance(payload, list) else []:
        league = item.get("league") or {}
        if int(league.get("id") or 0) != int(competition_id):
            continue
        if league.get("name") and not is_k_league_1(league.get("name")):
            continue
        if _stage(league.get("round")) is None:
            continue
        fixture = item.get("fixture") or {}
        teams = item.get("teams") or {}
        home, away = teams.get("home") or {}, teams.get("away") or {}
        status = str((fixture.get("status") or {}).get("short") or "")
        goals = None
        if status == "FT":
            full = (item.get("score") or {}).get("fulltime") or {}
            home_goals, away_goals = _score(full.get("home")), _score(full.get("away"))
            if home_goals is not None and away_goals is not None:
                goals = {"home": home_goals, "away": away_goals}
        match_id = fixture.get("id")
        if isinstance(match_id, bool) or not isinstance(match_id, int):
            continue
        rows.append(_row(
            "api-football", int(competition_id), f"api-football:{match_id}", fixture.get("date"), status,
            goals, f"api-football:{home.get('id')}", f"api-football:{away.get('id')}", home.get("name"),
            away.get("name"), None, None, None, captured_at, source_url))
    return rows


def _signature(row):
    payload = {key: row.get(key) for key in ("provider", "match_id", "status", "goals", "odds", "statistics")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _append_new(path, rows, signature=_signature):
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                seen.add(signature(json.loads(line)))
    added = []
    with path.open("a") as handle:
        for row in rows:
            digest = signature(row)
            if digest in seen:
                continue
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            seen.add(digest)
            added.append(row)
    return added


def _full_signature(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _scrub_value(value, secrets):
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [_scrub_value(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: _scrub_value(item, secrets) for key, item in value.items()}
    return value


def _scrub(raw, secrets):
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text.encode()


def _store_raw(root, raw, secrets):
    body = _scrub(raw, secrets)
    digest = hashlib.sha256(body).hexdigest()
    folder = root / "kor1" / "raw"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{digest}.json.gz"
    if not path.exists():
        path.write_bytes(gzip.compress(body, mtime=0))
    return f"kor1/raw/{path.name}"


def live_fetch(url, headers, timeout=15):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise ValueError("unsupported provider url")
    if any(value and value in url for value in headers.values()):
        raise ValueError("credential in url")
    request = Request(url, headers={"User-Agent": "WCPP-research", "Accept-Encoding": "identity", **headers})
    opener = build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(8_000_001)
            status = response.status
    except HTTPError as exc:
        raw = exc.read(8_000_001)
        status = exc.code
    if len(raw) > 8_000_000:
        raise ValueError("response too large")
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return status, raw


class Budget:
    def __init__(self, limit):
        self.limit = limit
        self.used = 0

    def allow(self):
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


def _decode(raw):
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return body if isinstance(body, dict) else None


def _get(fetcher, budget, url, headers, sink, secrets):
    if not budget.allow():
        return None, "request budget exhausted"
    try:
        status, raw = fetcher(url, headers)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return None, "network error"
    stored = _store_raw(sink, raw if isinstance(raw, bytes) else json.dumps(raw).encode(), secrets)
    body = _decode(raw if isinstance(raw, bytes) else json.dumps(raw).encode())
    ok = status == 200 and isinstance(body, dict)
    return {"status": status, "body": body, "raw": stored, "url": url, "ok": ok}, None if ok else f"http {status}"


def _five_dollar_headers(key):
    return {"Authorization": "Bearer " + key}


def _api_football_headers(key):
    return {"x-apisports-key": key}


def _identity_ok(name, country):
    if not is_k_league_1(name, country):
        return False
    label = f"{country or ''}".lower()
    if label and "korea" not in label and "한국" not in label:
        return False
    return True


def _history_url(base, competition_id, cursor, now):
    year = int(cursor.get("next_year") or 2018)
    page = int(cursor.get("page") or 1)
    if cursor.get("completed") or year > now.year:
        return None, cursor
    start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp())
    query = urlencode({
        "start_time": start, "end_time": end, "page": page, "per_page": 100, "order": "asc"})
    return f"{base}/leagues/{competition_id}/fixtures?{query}", {"next_year": year, "page": page, "completed": False}


def _advance_history(cursor, pagination, now, history_from):
    if not isinstance(pagination, dict) or "has_more" not in pagination:
        return {"next_year": int(cursor["next_year"]), "page": int(cursor["page"]), "completed": False}
    has_more = bool(pagination.get("has_more"))
    year = int(cursor["next_year"])
    page = int(cursor["page"])
    if has_more:
        page += 1
    else:
        year += 1
        page = 1
    completed = year > now.year
    if year < history_from:
        year = history_from
    return {"next_year": year, "page": page, "completed": completed}


def collect_primary(config, fetcher, budget, sink, secrets, now, captured_at):
    primary = config["primary"]
    base = primary["base_url"].rstrip("/")
    competition_id = int(primary["competition_id"])
    headers = _five_dollar_headers(secrets["primary"])
    calls = []
    status, error = _get(fetcher, budget, base + "/status", headers, sink, list(secrets.values()))
    calls.append(status or {"url": base + "/status", "ok": False, "error": error})
    if not status or not status["ok"] or status["body"].get("success") != 1:
        return _failed("5dollar", "status rejected", calls)
    league_url = f"{base}/leagues/{competition_id}"
    league, error = _get(fetcher, budget, league_url, headers, sink, list(secrets.values()))
    calls.append(league or {"url": league_url, "ok": False, "error": error})
    if not league or not league["ok"] or league["body"].get("success") != 1:
        return _failed("5dollar", "league lookup failed", calls)
    data = league["body"].get("data") or {}
    country = (data.get("country") or {}).get("name", "")
    if not _identity_ok(data.get("name"), country):
        return _failed("5dollar", "competition is not K League 1", calls)
    fresh_query = urlencode({"include": "odds,stats", "per_page": 50, "page": 1})
    fresh_url = f"{base}/leagues/{competition_id}/fixtures?{fresh_query}"
    fresh, error = _get(fetcher, budget, fresh_url, headers, sink, list(secrets.values()))
    calls.append(fresh or {"url": fresh_url, "ok": False, "error": error})
    if not fresh or not fresh["ok"] or fresh["body"].get("success") != 1:
        return _failed("5dollar", "fixture lookup failed", calls)
    rows = five_dollar_rows(fresh["body"].get("data"), competition_id, captured_at, fresh_url.split("?")[0])
    standings_url = f"{base}/standings?{urlencode({'league': competition_id})}"
    standings, error = _get(fetcher, budget, standings_url, headers, sink, list(secrets.values()))
    calls.append(standings or {"url": standings_url, "ok": False, "error": error})
    table = None
    if standings and standings["ok"] and standings["body"].get("success") == 1:
        table = standings["body"].get("data")
    cursor_path = sink / "kor1" / "history-cursor.json"
    cursor = {"next_year": int(config.get("history_from_year") or 2018), "page": 1, "completed": False}
    if cursor_path.exists():
        cursor = json.loads(cursor_path.read_text())
    history_url, cursor = _history_url(base, competition_id, cursor, now)
    history_rows = []
    if history_url and budget.used < budget.limit:
        history, error = _get(fetcher, budget, history_url, headers, sink, list(secrets.values()))
        calls.append(history or {"url": history_url, "ok": False, "error": error})
        if history and history["ok"] and history["body"].get("success") == 1:
            history_rows = five_dollar_rows(
                history["body"].get("data"), competition_id, captured_at, history_url.split("?")[0])
            cursor = _advance_history(
                cursor, history["body"].get("pagination"), now, int(config.get("history_from_year") or 2018))
    return {
        "ok": True, "provider": "5dollar", "competition_id": competition_id, "rows": rows + history_rows,
        "standings": table, "cursor": cursor, "calls": calls, "reason": None,
    }


def _bet365_by_fixture(payload, bookmaker_id):
    found = {}
    for item in payload if isinstance(payload, list) else []:
        fixture_id = (item.get("fixture") or {}).get("id")
        kept = []
        for book in item.get("bookmakers") or []:
            name = str(book.get("name") or "")
            if bookmaker_id is not None and book.get("id") not in (bookmaker_id, str(bookmaker_id)):
                if "bet365" not in name.lower() and "bet 365" not in name.lower():
                    continue
            if "bet365" not in name.lower() and "bet 365" not in name.lower():
                continue
            kept.append(book)
        if isinstance(fixture_id, int) and kept:
            found[fixture_id] = kept
    return found


def collect_fallback(config, fetcher, budget, sink, secrets, now, captured_at):
    fallback = config["fallback"]
    base = fallback["base_url"].rstrip("/")
    headers = _api_football_headers(secrets["fallback"])
    season = now.year
    calls = []
    league_url = f"{base}/leagues?{urlencode({'name': fallback['league_name'], 'country': fallback['country']})}"
    league, error = _get(fetcher, budget, league_url, headers, sink, list(secrets.values()))
    calls.append(league or {"url": league_url, "ok": False, "error": error})
    if not league or not league["ok"]:
        return _failed("api-football", "league lookup failed", calls)
    body = league["body"]
    if body.get("errors"):
        return _failed("api-football", "provider error", calls)
    response = body.get("response") or []
    if not response:
        return _failed("api-football", "league missing", calls)
    matching=[]
    for item in response:
        info=item.get('league') or {};country=(item.get('country') or {}).get('name','')
        normalized_country=str(country).lower().replace('-','').replace(' ','')
        normalized_name=str(info.get('name') or '').lower().replace(' ','').replace('-','').replace('_','')
        if (normalized_name in {'kleague1','k리그1','k리그원'} and info.get('type')=='League'
                and _identity_ok(info.get('name'),country) and normalized_country in
                {'southkorea','republicofkorea','korearepublic'} and type(info.get('id')) is int and info['id']>0):
            matching.append(item)
    if len(matching)!=1:
        return _failed('api-football','league lookup did not return one verified South-Korea K League 1 identity',calls)
    entry=matching[0];competition_id=entry['league']['id']
    fixture_url = f"{base}/fixtures?{urlencode({'league': competition_id, 'season': season})}"
    fixtures, error = _get(fetcher, budget, fixture_url, headers, sink, list(secrets.values()))
    calls.append(fixtures or {"url": fixture_url, "ok": False, "error": error})
    if not fixtures or not fixtures["ok"] or fixtures["body"].get("errors"):
        failed=_failed('api-football','current-season fixture lookup unavailable',calls)
        failed['competition_id']=competition_id
        if fixtures and isinstance(fixtures.get('body',{}).get('errors'),dict) and 'plan' in fixtures['body']['errors']:
            failed['reason']='current season blocked by provider plan'
        return failed
    rows = api_football_rows(
        fixtures["body"].get("response"), competition_id, captured_at, fixture_url.split("?")[0])
    standings_url = f"{base}/standings?{urlencode({'league': competition_id, 'season': season})}"
    standings, error = _get(fetcher, budget, standings_url, headers, sink, list(secrets.values()))
    calls.append(standings or {"url": standings_url, "ok": False, "error": error})
    table = None
    if standings and standings["ok"] and not standings["body"].get("errors"):
        table = standings["body"].get("response")
    odds_url = f"{base}/odds?{urlencode({'league': competition_id, 'season': season, 'bookmaker': fallback['bet365_bookmaker_id']})}"
    odds, error = _get(fetcher, budget, odds_url, headers, sink, list(secrets.values()))
    calls.append(odds or {"url": odds_url, "ok": False, "error": error})
    if odds and odds["ok"] and not odds["body"].get("errors"):
        books = _bet365_by_fixture(odds["body"].get("response"), int(fallback["bet365_bookmaker_id"]))
        for row in rows:
            match_key = int(row["match_id"].split(":", 1)[1])
            if match_key in books:
                row["odds"] = books[match_key]
                row["bookmaker"] = "bet365"
    return {
        "ok": True, "provider": "api-football", "competition_id": competition_id, "rows": rows,
        "standings": table, "cursor": None, "calls": calls, "reason": None,
    }


def _failed(provider, reason, calls):
    return {"ok": False, "provider": provider, "rows": [], "standings": None, "cursor": None,
            "calls": calls, "reason": reason, "competition_id": None}


def _public_call(call):
    if not call:
        return None
    return {"url": call.get("url"), "ok": bool(call.get("ok")), "status": call.get("status"),
            "raw": call.get("raw"), "error": call.get("error")}


def collect(state_dir, env, fetcher, now=None):
    root = Path(state_dir)
    config = load_config(root)
    scopes = json.loads((root / "config" / "scopes.json").read_text())
    if len([row for row in scopes if row.get("competition") == "kor.1"]) != 1:
        raise ValueError("kor.1 missing from scopes.json; refusing to invent an ESPN slug")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    captured_at = now.isoformat()
    secrets = {
        "primary": env.get(config["primary"]["credential_env"]) or "",
        "fallback": env.get(config["fallback"]["credential_env"]) or "",
    }
    budget = Budget(int(config.get("max_requests_per_run") or 6))
    training = root / "normalized-results.jsonl"
    before = training.read_bytes() if training.exists() else None
    result = None
    used_fallback = False
    if secrets["primary"]:
        result = collect_primary(config, fetcher, budget, root, secrets, now, captured_at)
    else:
        result = _failed("5dollar", "credential missing", [])
    if not result["ok"]:
        primary_reason = result["reason"]
        primary_calls = list(result["calls"])
        if secrets["fallback"]:
            used_fallback = True
            result = collect_fallback(config, fetcher, budget, root, secrets, now, captured_at)
            result["calls"] = primary_calls + result["calls"]
            if not result["ok"]:
                result["reason"] = f"{primary_reason}; {result['reason']}"
        elif not secrets["primary"]:
            result = _failed("api-football", "credential missing", result["calls"])
    secret_values = [value for value in secrets.values() if value]
    result["rows"] = [_scrub_value(row, secret_values) for row in result["rows"]]
    if result["standings"] is not None:
        result["standings"] = _scrub_value(result["standings"], secret_values)
    added = []
    if result["ok"]:
        added = _append_new(root / "kor1" / "fixtures.jsonl", result["rows"])
        if result["standings"] is not None:
            _append_new(root / "kor1" / "standings.jsonl", [{
                "cohort": "kor.1", "provider": result["provider"],
                "provider_competition_id": result["competition_id"], "known_at": captured_at,
                "standings": result["standings"], "training_eligible": False, "espn": False,
            }], signature=_full_signature)
        if result.get("cursor"):
            cursor_path = root / "kor1" / "history-cursor.json"
            cursor_path.parent.mkdir(parents=True, exist_ok=True)
            cursor_path.write_text(json.dumps(result["cursor"], sort_keys=True) + "\n")
    summary = {
        "cohort": "kor.1", "espn": False, "ok": bool(result["ok"]), "provider": result["provider"],
        "used_fallback": used_fallback, "reason": result["reason"], "requests": budget.used,
        "provider_competition_id":result.get("competition_id"),
        "fixtures_seen": len(result["rows"]), "fixtures_added": len(added),
        "standings_saved": result["standings"] is not None, "known_at": captured_at,
        "training_eligible": False, "calls": [_public_call(call) for call in result["calls"]],
    }
    summary = _scrub_value(summary, secret_values)
    summary_path = root / "kor1" / "runs.jsonl"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("a") as handle:
        handle.write(json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n")
    after = training.read_bytes() if training.exists() else None
    if after != before:
        raise RuntimeError("kor.1 collection changed normalized-results.jsonl")
    for path in (root / "kor1").rglob("*"):
        if not path.is_file() or path.suffix == ".gz":
            if path.suffix == ".gz":
                text = gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
            else:
                continue
        else:
            text = path.read_text()
        for secret in secret_values:
            if secret in text:
                raise RuntimeError("credential written to kor.1 output")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("collect", "omit-espn"))
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args(argv)
    if args.command == "omit-espn":
        omit_espn(args.state_dir)
        return 0
    summary = collect(args.state_dir, os.environ, live_fetch)
    print(json.dumps({key: summary[key] for key in (
        "cohort", "espn", "ok", "provider", "used_fallback", "reason", "requests",
        "fixtures_seen", "fixtures_added", "standings_saved")}, sort_keys=True))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
