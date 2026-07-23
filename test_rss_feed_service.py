"""Offline regression tests for RSS/Atom collection and source diagnostics."""

import ast
import hashlib
import json
import logging
import os
import unittest
from pathlib import Path

os.environ.setdefault("MAIAGENT_API_KEY", "rss-test")
os.environ.setdefault("MAIAGENT_CHATBOT_ID", "rss-test")
os.environ.setdefault("MAIAGENT_API_BASE", "https://api.maiagent.ai")
os.environ.setdefault("GMAIL_USER", "rss@example.invalid")
os.environ.setdefault("GMAIL_APP_PASS", "rss-test")
os.environ.setdefault("RECIPIENTS", "rss@example.invalid")
os.environ.setdefault("DEFAULT_RECIPIENTS", "rss@example.invalid")

logging.disable(logging.CRITICAL)

import rss_feed_service
import streamlit_app as app


FUTURE_PUB_DATE = "Wed, 20 Jul 2999 00:00:00 GMT"
EXPECTED_SCENARIO_SHA256 = {
    "cross_source_duplicate": "f5f5218bcad9675300d9ed011c0bd8fdb7745a3ad593ddbf216dd07f4d88019b",
    "fallback_both_fail": "f2d3e7adbf0e302c015532e260cae5e8513d4c3f8e3d7ef9db65d561c91bdaea",
    "fallback_no_valid": "cc4f1bee18e94bb9c0402fcb8bb9b0d0ad284b5627a52b73aee51ea8e8c58d4f",
    "fallback_success": "a1850822348a12f3f0a55ce332bcf72fe0e7c904b0339bbf0d29765f11b01903",
    "health_summary": "fe8a764b5d644fb363ac438c839f81e938773e3eeb904c213bcc31f40a50f7e1",
    "known_bad": "b92e66e6d7c1607a40510be9226eee5ea5a8ef677308d8d349975bba1f22f8ae",
    "no_articles": "27c89d7de487b144e43d4db601413be0d87549ea4f74481ef9a10dd9d11f5fd0",
    "non_urban": "49919a336a10e7321ac9e405f22a71705b08ced469612e06c9451935b308751e",
    "official_success": "58d6df7ff67f959c5a6ba15318d7fa1dc6ca618fe2b8d77462396220c48ab339",
    "safety_excluded": "dcb7752e7fa7df76bb548e89c9f6b32e236a33bccaa195cb159b2c98fe0518c4",
    "standards_not_update": "f1f6b7d3eea58ab2d352c502ef5df05bd4818c8d4b606684db69c1f2f63b33af",
    "tech_only_excluded": "c43b78b0a45d6e8759616a256401ecbd1e112a33f8ec4c597dabf2f6792da27a",
}
EXPECTED_AGGREGATE_SHA256 = (
    "87b3a2b1d3145701557aac27d563071b609e8f073edffddad416d92a2297cf8a"
)


class FakeResponse:
    def __init__(self, url: str, status_code: int):
        self.content = url.encode("utf-8")
        self.status_code = status_code


class FakeSession:
    def __init__(self, feeds: dict[str, dict]):
        self.feeds = feeds

    def get(self, url: str, timeout: int = 15) -> FakeResponse:
        fixture = self.feeds.get(url, {"status_code": 404, "entries": []})
        error = fixture.get("error")
        if error:
            raise error
        return FakeResponse(url, fixture.get("status_code", 200))


class FakeParsedFeed:
    def __init__(self, entries: list[dict], *, bozo: bool = False):
        self.entries = entries
        self.bozo = bozo
        self.bozo_exception = "fixture parse error"


class FakeFeedParser:
    def __init__(self, feeds: dict[str, dict]):
        self.feeds = feeds

    def parse(self, content: bytes) -> FakeParsedFeed:
        fixture = self.feeds[content.decode("utf-8")]
        return FakeParsedFeed(
            fixture.get("entries", []),
            bozo=fixture.get("bozo", False),
        )


class StatusRecorder:
    def __init__(self):
        self.messages: list[str] = []

    def text(self, value: str) -> None:
        self.messages.append(value)


def _entry(
    title: str,
    link: str,
    summary: str = "Metro urban rail technical article",
) -> dict:
    return {
        "title": title,
        "link": link,
        "summary": summary,
        "published": FUTURE_PUB_DATE,
        "source": {"href": link},
    }


def _payload_sha256(payload) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _configure_target(target, feeds: dict[str, dict], *, tech_only: bool = False) -> None:
    target.lookback_days = 30
    target.feedparser = FakeFeedParser(feeds)
    target.create_requests_session = lambda: FakeSession(feeds)
    target.google_news_site_proxy_url = (
        lambda domain, days: f"https://news.google.com/fallback/{domain}/{days}"
    )
    target._is_valid_news_url = (
        lambda url, source_href="": (
            (False, "被安全規則排除")
            if "unsafe" in url
            else (True, "")
        )
    )
    target._is_known_bad_official_rss = (
        lambda source_name, url: "known bad" in source_name.lower()
    )
    target._contains_taiwan_reference = lambda text: "taiwan" in text.lower()
    target._is_standards_source = (
        lambda source_name: "standards" in source_name.lower()
    )
    target._is_standard_update_candidate = lambda text: "update" in text.lower()
    target._is_urban_rail_candidate = (
        lambda text, source_name="": "metro" in text.lower()
    )
    target._is_tech_news_only_mode = lambda: tech_only
    target._is_technical_news_candidate = (
        lambda text, source_name="": "cbtc" in text.lower()
    )


def _run_case(
    target,
    sources: list[tuple[str, str]],
    feeds: dict[str, dict],
    *,
    tech_only: bool = False,
    record_status: bool = False,
) -> dict:
    _configure_target(target, feeds, tech_only=tech_only)
    recorder = StatusRecorder() if record_status else None
    raw_text, source_statuses = target.fetch_rss_feeds(
        sources,
        status_text=recorder,
        return_status=True,
    )
    payload = {
        "raw_text": raw_text,
        "source_statuses": source_statuses,
        "source_health_summary": target.build_source_health_summary(source_statuses),
        "candidate_count": raw_text.count("\n  標題："),
    }
    if recorder is not None:
        payload["status_messages"] = recorder.messages
        payload["return_status_false"] = target.fetch_rss_feeds(
            sources,
            return_status=False,
        )
    return payload


def collect_scenarios(target=app) -> dict[str, dict]:
    official_url = "https://official.example/rss"
    fallback_url = "https://news.google.com/fallback/official.example/30"
    duplicate_entry = _entry(
        "Metro CBTC duplicate",
        "https://official.example/metro-duplicate",
    )
    duplicate_title_entry = _entry(
        "Metro CBTC duplicate",
        "https://official.example/metro-duplicate-title",
    )
    duplicate_url_entry = _entry(
        "Metro CBTC duplicate URL",
        "https://official.example/metro-duplicate",
    )

    scenarios = {
        "official_success": _run_case(
            target,
            [("Official RSS", official_url)],
            {
                official_url: {
                    "entries": [
                        _entry(
                            "Metro CBTC upgrade",
                            "https://official.example/metro-cbtc",
                            "<b>Metro CBTC signalling upgrade</b>",
                        )
                    ]
                }
            },
            record_status=True,
        ),
        "no_articles": _run_case(
            target,
            [("Empty RSS", official_url)],
            {official_url: {"entries": []}},
        ),
        "non_urban": _run_case(
            target,
            [("General RSS", official_url)],
            {
                official_url: {
                    "entries": [
                        _entry(
                            "Highway bus timetable",
                            "https://official.example/highway-bus",
                            "Intercity bus operations",
                        )
                    ]
                }
            },
        ),
        "safety_excluded": _run_case(
            target,
            [("Safety RSS", official_url)],
            {
                official_url: {
                    "entries": [
                        _entry(
                            "Metro CBTC safety item",
                            "https://unsafe.example/metro-cbtc",
                        )
                    ]
                }
            },
        ),
        "known_bad": _run_case(
            target,
            [("Known Bad RSS", official_url)],
            {official_url: {"entries": []}},
        ),
        "standards_not_update": _run_case(
            target,
            [("Standards RSS", official_url)],
            {
                official_url: {
                    "entries": [
                        _entry(
                            "Metro standard catalogue",
                            "https://official.example/metro-standard",
                            "Metro standard reference catalogue",
                        )
                    ]
                }
            },
        ),
        "tech_only_excluded": _run_case(
            target,
            [("Technical RSS", official_url)],
            {
                official_url: {
                    "entries": [
                        _entry(
                            "Metro ridership service change",
                            "https://official.example/metro-service",
                            "Metro passenger service operations",
                        )
                    ]
                }
            },
            tech_only=True,
        ),
        "cross_source_duplicate": _run_case(
            target,
            [
                ("First RSS", "https://first.example/rss"),
                ("Second RSS", "https://second.example/rss"),
                ("Third RSS", "https://third.example/rss"),
            ],
            {
                "https://first.example/rss": {"entries": [duplicate_entry]},
                "https://second.example/rss": {"entries": [duplicate_title_entry]},
                "https://third.example/rss": {"entries": [duplicate_url_entry]},
            },
        ),
        "fallback_success": _run_case(
            target,
            [("Fallback RSS", official_url)],
            {
                official_url: {"status_code": 404},
                fallback_url: {
                    "entries": [
                        _entry(
                            "Metro CBTC fallback",
                            "https://fallback.example/metro-cbtc",
                        )
                    ]
                },
            },
        ),
        "fallback_no_valid": _run_case(
            target,
            [("Fallback Empty RSS", official_url)],
            {
                official_url: {"status_code": 404},
                fallback_url: {
                    "entries": [
                        _entry(
                            "Highway fallback article",
                            "https://fallback.example/highway",
                            "Road transport article",
                        )
                    ]
                },
            },
        ),
        "fallback_both_fail": _run_case(
            target,
            [("Fallback Failed RSS", official_url)],
            {
                official_url: {"status_code": 404},
                fallback_url: {"status_code": 405},
            },
        ),
    }

    health_statuses = [
        target._status_record("a", "official", "成功", 1),
        target._status_record("b", "official", "fallback 成功", 1, fallback_used=True),
        target._status_record("c", "official", "無文章", 0),
        target._status_record("d", "official", "非都市軌道", 0),
        target._status_record("e", "official", "skipped_known_bad", 0),
        target._status_record("f", "official", "被安全規則排除", 0),
        target._status_record("g", "official", "parse error", 0, "安全排除 fixture"),
        target._status_record("h", "official", "timeout", 0),
    ]
    scenarios["health_summary"] = {
        "source_statuses": health_statuses,
        "source_health_summary": target.build_source_health_summary(health_statuses),
    }
    return scenarios


class RssFeedServiceRegressionTests(unittest.TestCase):
    TARGET_GLOBALS = (
        "lookback_days",
        "feedparser",
        "create_requests_session",
        "google_news_site_proxy_url",
        "_is_valid_news_url",
        "_is_known_bad_official_rss",
        "_contains_taiwan_reference",
        "_is_standards_source",
        "_is_standard_update_candidate",
        "_is_urban_rail_candidate",
        "_is_tech_news_only_mode",
        "_is_technical_news_candidate",
    )

    def setUp(self):
        self.originals = {
            name: getattr(app, name)
            for name in self.TARGET_GLOBALS
        }

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(app, name, value)

    def test_offline_rss_scenarios_match_pre_split_payloads(self):
        scenarios = collect_scenarios()
        scenario_hashes = {
            name: _payload_sha256(payload)
            for name, payload in sorted(scenarios.items())
        }
        self.assertEqual(scenario_hashes, EXPECTED_SCENARIO_SHA256)
        self.assertEqual(_payload_sha256(scenarios), EXPECTED_AGGREGATE_SHA256)

        official = scenarios["official_success"]
        self.assertEqual(official["raw_text"], official["return_status_false"])
        self.assertEqual(official["candidate_count"], 1)
        self.assertEqual(
            official["status_messages"],
            ["正在蒐集國際捷運新聞"],
        )
        self.assertEqual(
            scenarios["health_summary"]["source_health_summary"],
            {
                "total": 8,
                "success": 2,
                "no_articles": 1,
                "non_urban_rail": 1,
                "skipped_known_bad": 1,
                "safety_excluded": 2,
                "fallback_success": 1,
                "fallback_used": 1,
                "other": 1,
            },
        )
        duplicate_statuses = scenarios["cross_source_duplicate"]["source_statuses"]
        self.assertEqual(
            [item["status"] for item in duplicate_statuses],
            ["成功", "無文章", "無文章"],
        )
        self.assertTrue(
            all(
                "重複 1" in item["error_message"]
                for item in duplicate_statuses[1:]
            )
        )
        self.assertEqual(
            scenarios["fallback_success"]["source_statuses"][0]["status"],
            "fallback 成功",
        )
        self.assertTrue(
            scenarios["fallback_success"]["source_statuses"][0]["fallback_used"]
        )

    def test_service_has_no_streamlit_dependency(self):
        source = Path(rss_feed_service.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_modules.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        star_imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and any(alias.name == "*" for alias in node.names)
        ]
        self.assertNotIn("streamlit", imported_modules)
        self.assertEqual(star_imports, [])


if __name__ == "__main__":
    unittest.main()
