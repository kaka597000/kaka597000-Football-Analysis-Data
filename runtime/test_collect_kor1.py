"""Kor.1 routing tests. No network and no training rows."""
import gzip
import json
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.collect_kor1 import (
    collect, espn_scopes, is_k_league_1, live_fetch, load_config,
)

ROOT = Path(__file__).resolve().parents[1]
SECRET = "test-secret-value"
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def league_body(name="K League 1", country="South Korea"):
    return {"success": 1, "data": {
        "id": 2270596712, "name": name,
        "country": {"code": "KR", "name": country},
        "seasons": [{"season": "2026", "current": True}],
    }}


def fixture(match_id=55, status="finished", code="full", round_name=30, goals=(2, 1)):
    home, away = (goals if goals else (None, None))
    return {
        "id": match_id,
        "league": {"id": 2270596712, "name": "K League 1"},
        "teams": {"home": {"id": 7, "name": "Ulsan"}, "away": {"id": 8, "name": "Pohang"}},
        "kickoff_utc": "2018-03-01T10:00:00+00:00" if match_id == 18 else "2026-10-31T10:00:00+00:00",
        "status": status, "status_code": code, "round": round_name,
        "goals": {"home": home, "away": away},
        "odds": {"1x2": {"opening": {"home": 1.8}}},
        "statistics": {"shots_on_target": {"home": 5, "away": 3}, "note": SECRET},
    }


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def __call__(self, url, headers):
        self.urls.append(url)
        for key in headers.values():
            if key and key in url:
                raise AssertionError("credential in url")
        for prefix, response in self.routes.items():
            if url.startswith(prefix) or prefix in url:
                status, body = response
                raw = json.dumps(body).encode()
                return status, raw
        raise AssertionError("unexpected url " + url)


class Kor1Tests(unittest.TestCase):
    def setUp(self):
        self.directory = ROOT / "runtime" / ".tmp-kor1-test"
        if self.directory.exists():
            shutil.rmtree(self.directory)
        config = self.directory / "config"
        config.mkdir(parents=True)
        shutil.copy(ROOT / "config" / "kor1-sources.json", config / "kor1-sources.json")
        scopes = json.loads((ROOT / "config" / "scopes.json").read_text())
        (config / "scopes.json").write_text(json.dumps(scopes, indent=2) + "\n")
        (self.directory / "normalized-results.jsonl").write_text('{"cohort":"aus.1"}\n')

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_names(self):
        self.assertTrue(is_k_league_1("K League 1", "South Korea"))
        self.assertTrue(is_k_league_1("K-League 1"))
        self.assertTrue(is_k_league_1("K리그1", "한국"))
        self.assertFalse(is_k_league_1("K League 2", "South Korea"))
        self.assertFalse(is_k_league_1("K League Challenge"))
        self.assertFalse(is_k_league_1("Korean FA Cup"))

    def test_committed_scope_is_unchanged_shape(self):
        scopes = json.loads((ROOT / "config" / "scopes.json").read_text())
        kor = [row for row in scopes if row.get("competition") == "kor.1"]
        self.assertEqual(len(kor), 1)
        self.assertEqual(set(kor[0]), {"cohort", "competition", "stages", "gender", "age"})
        self.assertEqual(kor[0]["stages"], ["regular"])
        config = load_config(ROOT)
        self.assertFalse(config["espn"])
        self.assertEqual(config["primary"]["competition_id"], 2270596712)
        self.assertIsNone(config["fallback"]["competition_id"])
        self.assertEqual(config["fallback"]["league_name"],"K League 1")
        source = (ROOT / "runtime" / "collect_kor1.py").read_text()
        self.assertNotIn("site.api.espn.com", source)
        workflow = (ROOT / ".github" / "workflows" / "unattended.yml").read_text()
        self.assertIn("cron: '17 */6 * * *'", workflow)
        self.assertIn("omit-espn", workflow)
        self.assertIn("WCPP_5DOLLAR_API_KEY", workflow)
        self.assertIn("WCPP_API_FOOTBALL_KEY", workflow)
        self.assertNotIn("site.api.espn.com/apis/site/v2/sports/soccer/kor", workflow)

    def test_espn_filter_drops_only_kor1(self):
        scopes = json.loads((ROOT / "config" / "scopes.json").read_text())
        kept = espn_scopes(scopes)
        self.assertEqual([row["competition"] for row in kept],
                         [row["competition"] for row in scopes if row["competition"] != "kor.1"])
        self.assertNotIn("kor.1", json.dumps(kept))

    def test_primary_collects_without_fallback_or_training_rows(self):
        http = FakeHttp({
            "/status": (200, {"success": 1, "data": {"plan": "community"}}),
            "/leagues/2270596712/fixtures": (200, {"success": 1, "data": [fixture(), fixture(18)],
                                                    "pagination": {"has_more": False}}),
            "/leagues/2270596712": (200, league_body()),
            "/standings": (200, {"success": 1, "data": {"league_id": 2270596712, "table": [{"position": 1}]}}),
        })
        # History and current fixtures share a prefix. Serve the current include call
        # and the history call from the same payload; the cursor must still advance.
        summary = collect(self.directory, {"WCPP_5DOLLAR_API_KEY": SECRET, "WCPP_API_FOOTBALL_KEY": "other"},
                          http, NOW)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["provider"], "5dollar")
        self.assertFalse(summary["used_fallback"])
        self.assertFalse(summary["espn"])
        self.assertTrue(all("api-sports.io" not in url and "espn" not in url for url in http.urls))
        self.assertLessEqual(summary["requests"], 6)
        rows = [json.loads(line) for line in (self.directory / "kor1" / "fixtures.jsonl").read_text().splitlines()]
        self.assertTrue(any(row["match_id"] == "5dollar:55" and row["goals"] == {"home": 2, "away": 1} for row in rows))
        self.assertTrue(all(row["training_eligible"] is False and row["bookmaker"] == "bet365" for row in rows if row["odds"]))
        self.assertNotIn(SECRET, (self.directory / "kor1" / "fixtures.jsonl").read_text())
        cursor = json.loads((self.directory / "kor1" / "history-cursor.json").read_text())
        self.assertEqual(cursor["next_year"], 2019)
        self.assertEqual((self.directory / "normalized-results.jsonl").read_text(), '{"cohort":"aus.1"}\n')
        again = collect(self.directory, {"WCPP_5DOLLAR_API_KEY": SECRET}, http, NOW)
        self.assertEqual(again["fixtures_added"], 0)

    def test_primary_failure_uses_api_football_bet365_only(self):
        http = FakeHttp({
            "/status": (401, {"success": 0, "error": {"code": "unauthorized"}}),
            "/leagues?name=K+League+1&country=South-Korea": (200, {"errors": [], "response": [{
                "league": {"id": 777, "name": "K League 1"},
                "country": {"name": "South-Korea"},
            }]}),
            "/fixtures?": (200, {"errors": [], "response": [{
                "fixture": {"id": 10, "date": "2026-10-31T10:00:00+00:00", "status": {"short": "FT"}},
                "league": {"id": 777, "name": "K League 1", "round": "Regular Season - 30"},
                "teams": {"home": {"id": 1, "name": "Ulsan"}, "away": {"id": 2, "name": "Pohang"}},
                "score": {"fulltime": {"home": 1, "away": 0}},
            }, {
                "fixture": {"id": 11, "date": "2026-11-20T10:00:00+00:00", "status": {"short": "NS"}},
                "league": {"id": 777, "name": "K League 1", "round": "Relegation Round"},
                "teams": {"home": {"id": 3, "name": "A"}, "away": {"id": 4, "name": "B"}},
                "score": {"fulltime": {"home": None, "away": None}},
            }]}),
            "/standings?": (200, {"errors": [], "response": [{"league": {"id": 777}}]}),
            "/odds?": (200, {"errors": [], "response": [{
                "fixture": {"id": 10},
                "bookmakers": [
                    {"id": 8, "name": "Bet365", "bets": [{"name": "Match Winner"}]},
                    {"id": 4, "name": "Pinnacle", "bets": [{"name": "ignored"}]},
                ],
            }]}),
        })
        summary = collect(self.directory, {"WCPP_5DOLLAR_API_KEY": SECRET, "WCPP_API_FOOTBALL_KEY": "fallback-secret"},
                          http, NOW)
        self.assertTrue(summary["ok"])
        self.assertTrue(summary["used_fallback"])
        self.assertEqual(summary["provider"], "api-football")
        rows = [json.loads(line) for line in (self.directory / "kor1" / "fixtures.jsonl").read_text().splitlines()]
        self.assertEqual([row["match_id"] for row in rows], ["api-football:10"])
        self.assertEqual(rows[0]["goals"], {"home": 1, "away": 0})
        self.assertEqual(rows[0]["bookmaker"], "bet365")
        self.assertEqual([book["name"] for book in rows[0]["odds"]], ["Bet365"])
        self.assertTrue(any("/leagues?name=K+League+1&country=South-Korea" in url for url in http.urls))
        self.assertFalse(any("espn" in url for url in http.urls))

    def test_wrong_primary_identity_does_not_save_those_rows(self):
        http = FakeHttp({
            "/status": (200, {"success": 1}),
            "/leagues/2270596712": (200, league_body("K League 2")),
            "/leagues?name=K+League+1&country=South-Korea": (200, {"errors": [], "response": [{
                "league": {"id": 777, "name": "K League 1"}, "country": {"name": "South-Korea"}}]}),
            "/fixtures?": (200, {"errors": [], "response": []}),
            "/standings?": (200, {"errors": [], "response": []}),
            "/odds?": (200, {"errors": [], "response": []}),
        })
        summary = collect(self.directory, {"WCPP_5DOLLAR_API_KEY": SECRET, "WCPP_API_FOOTBALL_KEY": "fallback-secret"},
                          http, NOW)
        self.assertTrue(summary["used_fallback"])
        self.assertFalse(any("/leagues/2270596712/fixtures" in url for url in http.urls))

    def test_named_lookup_rejects_foreign_or_ambiguous_leagues(self):
        for response in ([{'league':{'id':219,'name':'2. Liga'},'country':{'name':'Austria'}}],
                         [{'league':{'id':777,'name':'K League 1'},'country':{'name':'South-Korea'}},
                          {'league':{'id':778,'name':'K League 1'},'country':{'name':'South-Korea'}}]):
            http=FakeHttp({'/status':(403,{}),'/leagues?name=K+League+1&country=South-Korea':(200,{'errors':[],'response':response})})
            summary=collect(self.directory,{'WCPP_5DOLLAR_API_KEY':SECRET,'WCPP_API_FOOTBALL_KEY':'fallback-secret'},http,NOW)
            self.assertFalse(summary['ok'])
            self.assertFalse(any('/fixtures?' in url for url in http.urls))

    def test_missing_credentials_make_no_requests(self):
        http = FakeHttp({})
        summary = collect(self.directory, {}, http, NOW)
        self.assertFalse(summary["ok"])
        self.assertEqual(http.urls, [])
        self.assertIn("credential missing", summary["reason"])

    def test_live_fetch_rejects_other_hosts(self):
        with self.assertRaises(ValueError):
            live_fetch("https://site.api.espn.com/apis/site/v2/sports/soccer/kor.1/scoreboard", {})


if __name__ == "__main__":
    unittest.main()
