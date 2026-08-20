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
    "plan_global": "ffce6caa36da496f4f3f8b28752d480b6ff039b738fad1fd479c643600d40297",
    "plan_no_selected": "c0eec20ff3111558b6152298874210963286a06cdd4884f5b9ec3438e4e0e0cf",
    "plan_regions": "95f8143ea6c94c6db8bcb59eff0e3db295d9f2105009653f545e0b03a9ec56ca",
    "plan_standards": "cb6b2fe9685384b703768601bfe0794a0c86d0fa32841de68de5cf000991b1cb",
    "run_no_selected": "c0154e3c47b4ab31ed2c0c0da83d0cabda70656ef238bd0425e4274faf6fae5e",
    "run_success": "cfc546fee77a6349e07065680177b0340ba60cda820565d326de4ed7e500f115",
    "run_timeout": "960479b32fc46fd1939d320d5b58e55067817370ea21b26baa062d0576f76e66",
    "run_zero": "64717e6565a3ab40d765bec6df60f907562eec4f1838c343360e0545825a3d77",
    "run_excluded": "d5b6ecd8819a89b0bbebd88ce69d1379148913711cb55615234b1b813aa8f8d6",
    "run_403": "638dce41f37b36df8dc309ea9b92403dea8d932295a79842d1edc588baca609e",
    "run_429": "4023ede256cba4c4a4df1d918e25e7e823d2cb027157b6ef86f8f2d9265287e4",
    "run_exception": "7ddd514f722e53d0c53dbf0b9623545f6d127879071ece6a03e571a09f815e91",
    "run_missing": "7af4f7c33915f1cc56a9a479014e56cfdaf880a57c12e451b85d9b589cf25aa9",
}
EXPECTED_AGGREGATE_SHA256 = "120dece2777ff4258bc972daaafdd7c0fe32a8ab689d4a8839c7917ac6c2825d"


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
