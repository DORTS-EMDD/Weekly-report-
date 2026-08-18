"""Offline regression tests for DDGS planning, execution, and diagnostics."""

import copy
import datetime
import hashlib
import json
import logging
import os
import unittest

os.environ.setdefault("MAIAGENT_API_KEY", "ddgs-test")
os.environ.setdefault("MAIAGENT_CHATBOT_ID", "ddgs-test")
os.environ.setdefault("MAIAGENT_API_BASE", "https://api.maiagent.ai")
os.environ.setdefault("GMAIL_USER", "ddgs@example.invalid")
os.environ.setdefault("GMAIL_APP_PASS", "ddgs-test")
os.environ.setdefault("RECIPIENTS", "ddgs@example.invalid")
os.environ.setdefault("DEFAULT_RECIPIENTS", "ddgs@example.invalid")

logging.disable(logging.CRITICAL)

import streamlit_app as app


TECH = "技術新知"
ACCIDENT = "重大事故"
POLICY = "營運政策"
STANDARDS = "規範更新"
FIXTURE_QUERY = "fixture metro query"
FIXED_TODAY = datetime.date(2026, 7, 23)

EXPECTED_SCENARIO_SHA256 = {
    "plan_global": "2974c4ac2f204de7d06fd95c0a5ecf0adb0c62809156a06c9ccc0eb5febb30b7",
    "plan_no_selected": "c0eec20ff3111558b6152298874210963286a06cdd4884f5b9ec3438e4e0e0cf",
    "plan_regions": "69fccda206f49775ec021b2b72e50f1c9b28c5c35efb6ae200aa2bee5ce43b22",
    "plan_standards": "cb6b2fe9685384b703768601bfe0794a0c86d0fa32841de68de5cf000991b1cb",
    "run_403": "513b0f56f7a88def63f2f6dabbeec62b16418cecd2f21a72aef13c4174c33451",
    "run_429": "00c8dab870772dbee01298882bb984bb248da05872eba5f6c6b1e3a9eae22398",
    "run_exception": "f6713d96bc038f97e191d44184a2238f71ce6c77dc94d8a66f46f229fd888575",
    "run_excluded": "c6a46ad6df46d651aae5d51b5bbef6236c6fc319341340b7b2566bccc4f8cfd9",
    "run_missing": "2262c22aa817a96727439cc09151d5798904a1008225e06e4ac934971eab5870",
    "run_no_selected": "d49f78e6557a9a26d3c64db95f0b5e0296ff3c53f391b85cfea1ed55ee803d57",
    "run_success": "b2cc66ca4f12f55a016badfcf5aea6ade3277c84e3eeb8c74f1b40357de887fd",
    "run_timeout": "5701cb817abc5aa2cf7b13558b553935cfca97a83267121027afe33aeab06f22",
    "run_zero": "ab65b46cb223220c88dc8864f0c8071ce491e644f0d4ccad3b68800e51b3f853",
}
EXPECTED_AGGREGATE_SHA256 = "e567a18a138b228fbc0e522e89463d3c50bc3d36593859310db88d4a546e2472"


class ProgressRecorder:
    def __init__(self):
        self.values: list[float] = []

    def progress(self, value: float) -> None:
        self.values.append(value)


class StatusRecorder:
    def __init__(self):
        self.messages: list[str] = []

    def text(self, value: str) -> None:
        self.messages.append(value)


class FakeDDGS:
    mode = "success"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def _respond(self):
        if self.mode == "success":
            return [{
                "title": "Metro CBTC upgrade",
                "body": "Urban rail signalling deployment",
                "href": "https://example.com/metro-cbtc",
                "date": "2026-07-20",
            }]
        if self.mode == "zero":
            return []
        if self.mode == "excluded":
            return [{
                "title": "Invalid metro result",
                "body": "Urban rail item",
                "href": "not-a-url",
                "date": "2026-07-20",
            }]
        if self.mode == "403":
            raise Exception("403 Forbidden")
        if self.mode == "429":
            raise Exception("429 rate limit")
        if self.mode == "timeout":
            raise TimeoutError("fixture timed out")
        raise RuntimeError("fixture general failure")

    def news(self, query: str, max_results: int, timelimit: str, backend: str):
        return self._respond()

    def text(self, query: str, max_results: int, timelimit: str, backend: str):
        return self._respond()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


class DdgsSearchServiceCompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.original_state = {
            "selected_types": app.selected_types,
            "active_regions": app.active_regions,
            "is_global_scope": app.is_global_scope,
            "lookback_days": app.lookback_days,
            "lookback_int": app.lookback_int,
            "today": app.today,
            "DDGS": app.DDGS,
            "build_search_queries": app.build_search_queries,
            "LAST_DDGS_QUERY_METADATA": app.LAST_DDGS_QUERY_METADATA,
            "LAST_DDGS_QUERY_STATUSES": app.LAST_DDGS_QUERY_STATUSES,
            "LAST_DDGS_SEARCH_SUMMARY": app.LAST_DDGS_SEARCH_SUMMARY,
            "perf_counter": app.time.perf_counter,
            "sleep": app.time.sleep,
            "random_uniform": app.random.uniform,
        }
        app.time.perf_counter = lambda: 100.0
        app.time.sleep = lambda seconds: None
        app.random.uniform = lambda start, end: 0.0

    def tearDown(self):
        app.selected_types = self.original_state["selected_types"]
        app.active_regions = self.original_state["active_regions"]
        app.is_global_scope = self.original_state["is_global_scope"]
        app.lookback_days = self.original_state["lookback_days"]
        app.lookback_int = self.original_state["lookback_int"]
        app.today = self.original_state["today"]
        app.DDGS = self.original_state["DDGS"]
        app.build_search_queries = self.original_state["build_search_queries"]
        app.LAST_DDGS_QUERY_METADATA = self.original_state["LAST_DDGS_QUERY_METADATA"]
        app.LAST_DDGS_QUERY_STATUSES = self.original_state["LAST_DDGS_QUERY_STATUSES"]
        app.LAST_DDGS_SEARCH_SUMMARY = self.original_state["LAST_DDGS_SEARCH_SUMMARY"]
        app.time.perf_counter = self.original_state["perf_counter"]
        app.time.sleep = self.original_state["sleep"]
        app.random.uniform = self.original_state["random_uniform"]

    def _planning_scenario(
        self,
        label: str,
        selected_types: list[str],
        regions: list[str],
        global_scope: bool,
        days: int,
    ) -> dict:
        app.selected_types = list(selected_types)
        app.active_regions = list(regions)
        app.is_global_scope = global_scope
        app.lookback_days = days
        app.lookback_int = int(days)
        app.today = FIXED_TODAY
        queries, news_indices = app.build_search_queries()
        return {
            "label": label,
            "selected_families": app._selected_query_families(),
            "queries": queries,
            "news_query_indices": sorted(news_indices),
            "query_metadata": copy.deepcopy(app.LAST_DDGS_QUERY_METADATA),
        }

    def _fixed_metadata(self) -> dict:
        return {
            FIXTURE_QUERY: {
                "family": "technology",
                "lang": "en",
                "query_region": "global",
                "use_news": True,
                "timelimit": app._ddgs_timelimit_for_lookback(7),
                "requested_max_results": app.DDGS_RESULTS_PER_QUERY,
                "planned_index": 1,
            }
        }

    def _run_scenario(self, label: str, mode: str) -> dict:
        app.selected_types = [] if mode == "no_selected" else [TECH]
        app.active_regions = []
        app.is_global_scope = True
        app.lookback_days = 7
        app.lookback_int = 7
        app.today = FIXED_TODAY
        app.LAST_DDGS_QUERY_METADATA = self._fixed_metadata()
        app.LAST_DDGS_QUERY_STATUSES = []
        app.LAST_DDGS_SEARCH_SUMMARY = {}

        original_build_search_queries = app.build_search_queries
        app.build_search_queries = lambda: ([FIXTURE_QUERY], {1})
        if mode == "missing":
            app.DDGS = None
        else:
            FakeDDGS.mode = mode
            app.DDGS = FakeDDGS

        progress = ProgressRecorder()
        status = StatusRecorder()
        try:
            return_text = app.run_duckduckgo_searches(progress, status)
        finally:
            app.build_search_queries = original_build_search_queries

        return {
            "label": label,
            "return_text": return_text,
            "query_metadata": copy.deepcopy(app.LAST_DDGS_QUERY_METADATA),
            "query_statuses": copy.deepcopy(app.LAST_DDGS_QUERY_STATUSES),
            "search_summary": copy.deepcopy(app.LAST_DDGS_SEARCH_SUMMARY),
            "progress_values": progress.values,
            "status_messages": status.messages,
        }

    def test_all_pre_split_scenario_payloads_match(self):
        scenarios = {
            "plan_no_selected": self._planning_scenario("plan_no_selected", [], [], True, 7),
            "plan_global": self._planning_scenario("plan_global", [TECH, ACCIDENT], [], True, 90),
            "plan_regions": self._planning_scenario(
                "plan_regions",
                [TECH, POLICY],
                ["日本", "德國"],
                False,
                30,
            ),
            "plan_standards": self._planning_scenario("plan_standards", [STANDARDS], [], True, 14),
            "run_no_selected": self._run_scenario("run_no_selected", "no_selected"),
            "run_missing": self._run_scenario("run_missing", "missing"),
            "run_success": self._run_scenario("run_success", "success"),
            "run_zero": self._run_scenario("run_zero", "zero"),
            "run_excluded": self._run_scenario("run_excluded", "excluded"),
            "run_403": self._run_scenario("run_403", "403"),
            "run_429": self._run_scenario("run_429", "429"),
            "run_timeout": self._run_scenario("run_timeout", "timeout"),
            "run_exception": self._run_scenario("run_exception", "exception"),
        }

        actual_hashes = {
            name: payload_digest(payload)
            for name, payload in scenarios.items()
        }
        self.assertEqual(actual_hashes, EXPECTED_SCENARIO_SHA256)
        self.assertEqual(payload_digest(scenarios), EXPECTED_AGGREGATE_SHA256)

        expected_statuses = {
            "run_success": "success",
            "run_zero": "zero_results",
            "run_excluded": "all_results_basic_excluded",
            "run_403": "http_403",
            "run_429": "rate_limited_429",
            "run_timeout": "timeout",
            "run_exception": "other_exception",
            "run_missing": "not_executed_dependency_missing",
        }
        for scenario_name, execution_status in expected_statuses.items():
            self.assertEqual(
                scenarios[scenario_name]["query_statuses"][0]["execution_status"],
                execution_status,
            )


if __name__ == "__main__":
    unittest.main()
