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
    "plan_global": "d0076e096c7e51fb869fc8feb8c8cb6d23de697ffd54477c6ceca52d3503a5b4",
    "plan_no_selected": "549d7739bddc7e487b502525c794834298a7916dbb1bdff68612b2162cb457fa",
    "plan_regions": "3588607c7280f86232618fc8affac65accc85e4e006c8a621dc12f86648cac27",
    "plan_standards": "5e641af9c1c12dfdba5377e8de1b120fecc5bfabb7243b7ddee63c47a68d33bf",
    "run_403": "f63c0c481e687af2013903db4da8da5cbd4a9e0055e7872933b0d99a37486c85",
    "run_429": "9798572a537f43165dca1dcf8267e7b066276b46958ff0df0260b9472c7e32e1",
    "run_exception": "da36b8e1a7e4e2dc0346aacfdc99c9558fcc6593bda4bcd5a1756178e4a4ebb4",
    "run_excluded": "5b24e01c6f062e3704e50a982cd20a8cc378d9a5289738538341dfe92aaedf9b",
    "run_missing": "69562d9b31e3727ddb1993e5df312cbdddb266238d05e289512c3761dcfa69a0",
    "run_no_selected": "da227b1f5778723ab6f1011bd568fcd1d6e7eea4181bff3436a09c0bd19abf99",
    "run_success": "049113f28025c74ae28c249e650362e8911f684c1ef4296880285f266a007fb0",
    "run_timeout": "90ace2d79d86601267f8d0c4bd3d44e05eb3cd7fdc4c3103127570eae8265aed",
    "run_zero": "ef6faa67e26fcae8564a054584e3dbb7ae81fb2b4a95ccb9797e11bac865c9d7",
}
EXPECTED_AGGREGATE_SHA256 = "b9ca403abf61da024619ddaec227030e704fd5e663a104c6f1b674436edf676a"


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
