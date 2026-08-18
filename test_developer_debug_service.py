"""Offline regression tests for developer debug JSON payload shaping."""

import ast
import datetime as real_datetime
import hashlib
import json
import logging
import os
import types
import unittest
from pathlib import Path

os.environ.setdefault("MAIAGENT_API_KEY", "debug-test")
os.environ.setdefault("MAIAGENT_CHATBOT_ID", "debug-test")
os.environ.setdefault("MAIAGENT_API_BASE", "https://api.maiagent.ai")
os.environ.setdefault("GMAIL_USER", "debug@example.invalid")
os.environ.setdefault("GMAIL_APP_PASS", "debug-test")
os.environ.setdefault("RECIPIENTS", "debug@example.invalid")
os.environ.setdefault("DEFAULT_RECIPIENTS", "debug@example.invalid")

logging.disable(logging.CRITICAL)

import developer_debug_service
import streamlit_app as app


EXPECTED_SCENARIO_SHA256 = {
    "fast_mode": "c762addd736271a0dafeec4fd3cd6f3e97208163436c176ea08c1279f8f247d7",
    "full_weekly": "a8aa47c7947f8d4b94e087cd34826948662f6b463c802fdf4bf0c7b4273b64fc",
    "no_debug_info": "6592ec44c8199ca6abce10bb59fb04ab686ea158af9e83fa191e0fb43e297a92",
    "missing_report_stats": "c7b23d673c91498f471ab586ba8740190eafa68e2e7d127f2e41bde7536f21b5",
    "current_config_fallback": "236993d9ec9a2d88eb2250bc8285d2625905463eb690f6ddd8f800733a7cd1ce",
    "json_safe_types": "5cf8865f0d742f7a4911fb086b889607650d1e869334fdd7ea7de420b17160f5",
    "internal_fields": "ee4364666c6cd592fb83b8f3eb2daebaa9f72954346eee0521c895c758f1b12f",
    "empty_candidates": "bad340decdc94228874dbfc9cfb18ce75a7078dfb7ba326aff47a789da53cb49",
    "full_candidates": "09f66a96c5820ce2bb6eb1e3fda5e8c6b60af04b4cdd59c0a1e916fd6dda82da",
}
EXPECTED_AGGREGATE_SHA256 = "58ed43c59eead21252fdb03931adcdfc391e3e227ac1efea33e10aeaf070a955"


class FixedDateTime(real_datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 7, 23, 12, 34, 56)
        return value if tz is None else value.replace(tzinfo=tz)


class FixedDatetimeModule:
    datetime = FixedDateTime
    date = real_datetime.date


class StableObject:
    def __str__(self):
        return "stable-custom-object"


def _run_config(*, fast_mode: bool, label: str) -> dict:
    return {
        "report_date": real_datetime.date(2026, 7, 23),
        "start_date": real_datetime.date(2026, 7, 17),
        "end_date": real_datetime.date(2026, 7, 23),
        "lookback_days": 7,
        "date_range": "2026-07-17 ~ 2026-07-23",
        "report_label": label,
        "report_title": f"Fixture {label}",
        "selected_types": ["技術新知", "重大事故", "營運政策", "規範更新"],
        "selected_regions": ["全球", "日本"],
        "scope_mode": "global",
        "include_standards": True,
        "include_research_supplement": True,
        "research_supplement_period": {
            "start_date": real_datetime.date(2026, 1, 1),
            "end_date": real_datetime.date(2026, 7, 23),
            "lookback_days": 204,
        },
        "fast_mode": fast_mode,
        "demo_cache_mode": fast_mode,
    }


def _candidate(candidate_id: int = 7) -> dict:
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "date": real_datetime.date(2026, 7, 20),
        "title": "Metro CBTC fixture",
        "search_family": "technical",
        "search_query": "metro CBTC fixture",
        "search_language": "en",
        "query_region": "Japan",
        "source": "Fixture Rail News",
        "source_display": "Fixture Rail News",
        "source_domain_raw": "www.fixture.example",
        "source_domain_normalized": "fixture.example",
        "source_quality": "A",
        "source_tier": "official",
        "region": "日本",
        "source_type": "技術新知",
        "page_type": "article",
        "page_type_reason": "article fixture",
        "date_validation": "exact",
        "urban_rail_gate": True,
        "canonical_tags": ["CBTC", "號誌"],
        "category_gates": {"技術新知": True, "重大事故": False},
        "category_gate_reasons": {"技術新知": ["technical_triplet"]},
        "primary_category": "技術新知",
        "alternative_category_flags": ["營運政策"],
        "accident_severity_score": 0,
        "technical_triplet_status": "passed",
        "candidate_level": "A",
        "preliminary_type": "技術新知",
        "python_score": 17,
        "score_reason": "fixture score",
        "candidate_flags": ["official", "recent"],
        "exclude_reason": "",
        "final_exclude_reason": "",
        "event_fingerprint": {"operator": "Fixture Metro", "event": "CBTC"},
        "duplicate_of": "",
        "selection_stage": "strict",
        "url": "https://fixture.example/metro-cbtc",
        "classification": "technical",
        "selected_reason": "fixture selected",
        "summary": "Fixture summary",
        "_internal_score": 99,
        "nested": {
            "visible": "kept",
            "_private": "removed",
            "rows": [{"ok": 1, "_drop": 2}],
        },
    }


def _source_statuses() -> list[dict]:
    return [
        {
            "source_name": "Fixture RSS",
            "method": "官方 RSS",
            "status": "成功",
            "item_count": 1,
            "error_message": "",
            "fallback_used": False,
        },
        {
            "source_name": "Fallback RSS",
            "method": "Google News fallback",
            "status": "fallback 成功",
            "item_count": 1,
            "error_message": "official failed",
            "fallback_used": True,
        },
    ]


def _full_debug_info() -> dict:
    candidate = _candidate()
    ddgs_summary = {
        "planned_query_count": 4,
        "executed_query_count": 3,
        "query_count_by_region": {"Japan": 2, "Global": 2},
        "query_count_by_family": {"technical": 3, "incident": 1},
        "query_count_by_language": {"en": 3, "ja": 1},
        "no_backend_result_count": 1,
        "all_results_basic_excluded_count": 1,
        "query_error_count": 1,
        "added_zero_count": 1,
        "success_with_raw_count": 2,
        "rate_limited_query_count": 1,
        "DDGS_added_to_raw_count": 5,
    }
    selection_debug = {
        "strict_selected_count": 1,
        "borderline_added_count": 1,
        "B_added_count": 1,
        "B_backfill_triggered": True,
        "B_backfill_cap": 2,
        "B_backfill_considered_count": 3,
        "B_backfill_appended_ids": [7],
        "B_backfill_append_stage": "after_strict",
        "shortfall_before_backfill": 1,
        "shortfall_after_backfill": 0,
        "backfill_reason": "fixture shortfall",
        "incident_search_raw_count": 2,
        "incident_gate_pass_count": 1,
        "incident_selected_count": 1,
        "python_incident_selected_count": 1,
        "maiagent_incident_report_count": 1,
        "final_incident_report_count": 1,
        "incident_dropped_after_maiagent": 0,
        "incident_coverage_warning": False,
        "incident_coverage_reason": "",
    }
    pipeline_debug = {
        "pipeline_counts": {"raw": 5, "filtered": 2},
        "candidate_pool_timings": {"rss": 0.4, "ddgs": 0.8},
        "prefetch_stats": {"attempted": 2, "success": 1},
        "page_type_exclusion_counts": {"homepage": 1},
        "no_category_gate_count": 1,
        "category_gate_pass_counts": {"技術新知": 2},
        "A_candidate_count": 1,
        "B_candidate_count": 1,
        "C_candidate_count": 0,
        "source_tier_counts": {"official": 1},
        "multilingual_candidate_counts": {"en": 1, "ja": 1},
        "normalized_domain_change_count": 1,
        "top_excluded_valuable_candidates": [{"id": 9, "reason": "fixture"}],
    }
    report_stats = {
        "raw_count": 5,
        "deduped_count": 4,
        "filtered_count": 2,
        "ai_selected_count": 1,
        "formal_count": 1,
        "prompt_chars": 1234,
        "raw_chars": 5678,
        "maiagent_call_count": 2,
        "category_counts": {"技術新知": 1},
        "journal_count": 1,
        "source_count": 2,
        "ddgs_query_count": 4,
        "ddgs_general_only_query_count": 1,
        "ddgs_search_summary": ddgs_summary,
        "candidate_card_limit": 30,
        "candidate_card_count": 2,
        "elapsed_seconds_total": 4.5,
        "elapsed_seconds_rss": 0.4,
        "elapsed_seconds_ddgs": 0.8,
        "elapsed_seconds_candidate_pool": 0.6,
        "candidate_pool_timings": {"rss": 0.4, "ddgs": 0.8},
        "elapsed_seconds_journal": 0.5,
        "elapsed_seconds_selection": 0.7,
        "elapsed_seconds_python_selection": 0.3,
        "elapsed_seconds_report": 1.0,
        "elapsed_seconds_pdf": 0.2,
        "pipeline_counts": pipeline_debug["pipeline_counts"],
        "prefetch_stats": pipeline_debug["prefetch_stats"],
        "prefetch_attempted_count": 2,
        "prefetch_success_count": 1,
        "top_excluded_valuable_count": 1,
        "dropped_selected_ids": [11],
        "dropped_selected_titles": ["Dropped fixture"],
        "dropped_selected_reasons": ["not in response"],
        "selection_method": "python_gate_first",
        "demo_cache_mode": False,
        "include_research_supplement": True,
        "research_supplement_period": {"lookback_days": 204},
        "report_retry_attempted": True,
        "report_id_validation_before_retry": {"missing_ids": [7]},
        "report_id_validation_after_retry": {"missing_ids": []},
        "report_id_reconciliation": {"fallback_candidate_ids": []},
    }
    report_stats.update(selection_debug)
    report_stats.update({
        key: value
        for key, value in pipeline_debug.items()
        if key not in {"candidate_pool_timings", "prefetch_stats"}
    })
    report_stats.update({
        "python_evaluated_candidate_count": 2,
        "filtered_candidates_entered_python_selection": True,
        "candidate_card_limit_applied_to_python_selection": False,
        "journal_target_count": 1,
        "journal_selected_count": 1,
        "journal_shortfall_reason": "",
        "journal_summary_conclusion_chars": 88,
        "journal_exclusion_stats": {"outside_period": 1},
    })
    return {
        "run_config": _run_config(fast_mode=False, label="一般週報"),
        "report_stats": report_stats,
        "long_term_coverage": {
            "long_term_coverage_warning": True,
            "reason": "fixture long-term warning",
        },
        "source_statuses": _source_statuses(),
        "source_health_summary": {
            "total": 2,
            "success": 2,
            "fallback_success": 1,
            "fallback_used": 1,
        },
        "raw_candidates": [candidate],
        "deduped_candidates": [candidate],
        "filtered_candidates": [candidate],
        "candidate_cards": [candidate],
        "selected_candidates": [candidate],
        "selected_ids": [7],
        "dropped_selected_ids": [11],
        "dropped_selected_titles": ["Dropped fixture"],
        "dropped_selected_reasons": ["not in response"],
        "selection_debug": selection_debug,
        "pipeline_debug_stats": pipeline_debug,
        "candidate_pool_timings": pipeline_debug["candidate_pool_timings"],
        "ddgs_query_statuses": [{
            "query": "metro CBTC",
            "execution_status": "success_with_raw",
            "backend": "news",
            "planned_index": 1,
        }],
        "ddgs_search_summary": ddgs_summary,
        "ddgs_no_backend_result_queries": ["empty query"],
        "ddgs_all_results_basic_excluded_queries": ["excluded query"],
        "ddgs_query_errors": [{"query": "rate query", "error_message": "429"}],
        "ddgs_added_zero_queries": ["zero query"],
        "ddgs_success_with_raw_queries": ["metro CBTC"],
        "ddgs_general_only_queries": ["general query"],
        "prefetch_stats": pipeline_debug["prefetch_stats"],
        "top_excluded_valuable_candidates": pipeline_debug["top_excluded_valuable_candidates"],
        "borderline_candidates": [{"id": 8, "candidate_level": "B"}],
        "duplicate_event_records": [{"id": 10, "duplicate_of": 7}],
        "report_id_validation_before_retry": {"missing_ids": [7]},
        "report_id_validation_after_retry": {"missing_ids": []},
        "report_id_reconciliation": {"fallback_candidate_ids": []},
        "enriched_selected_candidates": [candidate],
        "excluded_candidates": [{**candidate, "exclude_reason": "fixture excluded"}],
        "exclusion_stats": {"fixture excluded": 1},
        "dedupe_stats": {"duplicate_url": 1},
        "ai_unselected_stats": {"not_selected": 1},
        "python_unselected_stats": {"gate_failed": 1},
        "journal_candidates": [{
            "title": "Urban Rail Transit fixture",
            "journal_score": 12,
            "date_confidence": "exact",
        }],
        "journal_selected_candidates": [{
            "title": "Urban Rail Transit fixture",
            "journal_score": 12,
        }],
        "journal_statuses": [{"source": "Fixture Journal", "status": "success"}],
        "journal_source_statuses": [{"source": "Fixture Journal", "status": "success"}],
        "journal_excluded_candidates": [{"title": "Old paper", "exclude_reason": "outside_period"}],
        "journal_exclusion_stats": {"outside_period": 1},
        "journal_target_count": 1,
        "journal_selected_count": 1,
        "journal_shortfall_reason": "",
        "journal_summary_conclusion_chars": 88,
        "selection_method": "python_gate_first",
        "selection_prompt": "FIXTURE SELECTION PROMPT",
        "selection_response": "FIXTURE SELECTION RESPONSE",
        "ai_selection_response": "FIXTURE AI SELECTION RESPONSE",
        "report_prompt": "FIXTURE REPORT PROMPT",
        "initial_raw_report": "<!-- candidate_id: 7 -->\nInitial report",
        "raw_report": "<!-- candidate_id: 7 -->\nRaw report",
        "raw_report_candidate_ids": [7],
        "initial_report_response": "FIXTURE INITIAL REPORT RESPONSE",
        "report_response": "FIXTURE REPORT RESPONSE",
        "report_id_validation_before_clean": {"missing_ids": [], "duplicate_ids": []},
        "latest_report_md": "<!-- candidate_id: 7 -->\n# Fixture final report",
    }


def _serialized(value) -> str:
    def without_runtime_fingerprint(item):
        if isinstance(item, dict):
            return {
                key: without_runtime_fingerprint(value)
                for key, value in item.items()
                if key != "runtime_version"
            }
        if isinstance(item, list):
            return [without_runtime_fingerprint(value) for value in item]
        return item

    return json.dumps(
        without_runtime_fingerprint(value),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _sha256(value) -> str:
    return hashlib.sha256(_serialized(value).encode("utf-8")).hexdigest()


def _configure_target(target) -> None:
    target.datetime = FixedDatetimeModule
    target.current_run_config = _run_config(fast_mode=False, label="current fallback")
    target.st = types.SimpleNamespace(session_state={
        "latest_run_config": _run_config(fast_mode=False, label="latest fallback"),
        "_app_source_hash": "fixture-app-source-hash",
        "latest_report_md": "<!-- candidate_id: 99 -->\n# Session fallback report",
    })


def collect_scenarios(target=app) -> dict[str, object]:
    _configure_target(target)
    source_statuses = _source_statuses()
    complete_debug = _full_debug_info()
    full_candidate = _candidate()

    fast_debug = {
        "run_config": _run_config(fast_mode=True, label="展覽快速版"),
        "report_stats": {
            "raw_count": 0,
            "formal_count": 1,
            "demo_cache_mode": True,
            "selection_method": "demo_cache",
        },
        "selection_method": "demo_cache",
        "latest_report_md": "# 展覽快速版 fixture",
    }
    missing_stats_debug = {
        "run_config": _run_config(fast_mode=False, label="missing report_stats"),
        "selection_method": "external_stats",
        "ddgs_search_summary": {"planned_query_count": 2},
    }
    internal_value = {
        "visible": 1,
        "_drop": 2,
        "nested": {"kept": 3, "_nested_drop": 4},
        "rows": [{"ok": 5, "_row_drop": 6}],
        "tuple_rows": ({"kept_in_tuple": 7, "_also_kept_in_tuple": 8},),
    }
    latest_run_config = target.st.session_state["latest_run_config"]
    target.st.session_state["latest_run_config"] = None
    current_config_fallback = target.build_developer_debug_payload(
        {},
        {},
        source_statuses,
    )
    target.st.session_state["latest_run_config"] = latest_run_config

    return {
        "fast_mode": target.build_developer_debug_payload(
            fast_debug,
            fast_debug["report_stats"],
            source_statuses,
        ),
        "full_weekly": target.build_developer_debug_payload(
            complete_debug,
            complete_debug["report_stats"],
            source_statuses,
        ),
        "no_debug_info": target.build_developer_debug_payload(
            {},
            {"raw_count": 2, "selection_method": "fallback_stats"},
            source_statuses,
        ),
        "missing_report_stats": target.build_developer_debug_payload(
            missing_stats_debug,
            {"raw_count": 3, "formal_count": 1, "selection_method": "external_stats"},
            source_statuses,
        ),
        "current_config_fallback": current_config_fallback,
        "json_safe_types": target._json_safe({
            "datetime": FixedDateTime(2026, 7, 23, 1, 2, 3),
            "date": real_datetime.date(2026, 7, 22),
            "set": {1, 2, 3},
            "tuple": ("a", "b"),
            "custom": StableObject(),
        }),
        "internal_fields": {
            "stripped": target._debug_strip_internal_fields(internal_value),
            "payload": target.build_developer_debug_payload(
                {
                    "run_config": _run_config(fast_mode=False, label="internal fields"),
                    "raw_candidates": [internal_value],
                },
                {},
                source_statuses,
            ),
        },
        "empty_candidates": target.build_developer_debug_payload(
            {
                "run_config": _run_config(fast_mode=False, label="empty candidates"),
                "raw_candidates": [],
                "deduped_candidates": [],
                "filtered_candidates": [],
                "candidate_cards": [],
                "selected_candidates": [],
            },
            {},
            source_statuses,
        ),
        "full_candidates": {
            "candidate_rows": target._json_safe(
                target._debug_candidate_rows([full_candidate])
            ),
            "payload": target.build_developer_debug_payload(
                {
                    "run_config": _run_config(fast_mode=False, label="full candidates"),
                    "raw_candidates": [full_candidate],
                    "deduped_candidates": [full_candidate],
                    "filtered_candidates": [full_candidate],
                    "candidate_cards": [full_candidate],
                    "selected_candidates": [full_candidate],
                    "enriched_selected_candidates": [full_candidate],
                    "excluded_candidates": [{**full_candidate, "exclude_reason": "fixture"}],
                },
                {},
                source_statuses,
            ),
        },
    }


class DeveloperDebugServiceRegressionTests(unittest.TestCase):
    def setUp(self):
        self.originals = {
            "datetime": app.datetime,
            "current_run_config": app.current_run_config,
            "st": app.st,
        }

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(app, name, value)

    def test_all_pre_split_debug_payloads_match(self):
        scenarios = collect_scenarios()
        scenario_hashes = {
            name: _sha256(value)
            for name, value in scenarios.items()
        }
        self.assertEqual(scenario_hashes, EXPECTED_SCENARIO_SHA256)
        self.assertEqual(_sha256(scenarios), EXPECTED_AGGREGATE_SHA256)

        full_payload = scenarios["full_weekly"]
        self.assertEqual(full_payload["maiagent"]["report_prompt"], "FIXTURE REPORT PROMPT")
        self.assertEqual(full_payload["raw_candidates"][0].get("_internal_score"), None)
        self.assertEqual(
            full_payload["raw_candidates"][0]["nested"],
            {"visible": "kept", "rows": [{"ok": 1}]},
        )
        self.assertEqual(
            scenarios["json_safe_types"],
            {
                "datetime": "2026-07-23T01:02:03",
                "date": "2026-07-22",
                "set": [1, 2, 3],
                "tuple": ["a", "b"],
                "custom": "stable-custom-object",
            },
        )
        self.assertIn(
            "_also_kept_in_tuple",
            scenarios["internal_fields"]["stripped"]["tuple_rows"][0],
        )
        self.assertEqual(
            scenarios["current_config_fallback"]["run_info"]["report_label"],
            "current fallback",
        )

    def test_service_is_streamlit_free_and_uses_no_star_import(self):
        source = Path(developer_debug_service.__file__).read_text(encoding="utf-8")
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
        self.assertNotIn("session_state", source)


    def test_runtime_version_contains_git_and_module_fingerprints(self):
        runtime_version = developer_debug_service.build_runtime_version()
        self.assertIn("git_commit_sha", runtime_version)
        self.assertIn("branch", runtime_version)
        module_hashes = runtime_version["module_sha1"]
        self.assertEqual(
            set(module_hashes),
            set(developer_debug_service.RUNTIME_FINGERPRINT_MODULES),
        )
        self.assertTrue(all(len(value) == 40 for value in module_hashes.values()))
        for module_name, module_hash in module_hashes.items():
            self.assertEqual(runtime_version[f"{module_name}_hash"], module_hash)

    def test_runtime_module_fingerprint_detects_core_module_changes(self):
        original = {"module_sha1": {"streamlit_app": "a", "article_processor": "b"}}
        changed_core = {"module_sha1": {"streamlit_app": "a", "article_processor": "c"}}
        self.assertEqual(
            developer_debug_service.build_runtime_module_fingerprint(original),
            developer_debug_service.build_runtime_module_fingerprint(original),
        )
        self.assertNotEqual(
            developer_debug_service.build_runtime_module_fingerprint(original),
            developer_debug_service.build_runtime_module_fingerprint(changed_core),
        )


if __name__ == "__main__":
    unittest.main()
