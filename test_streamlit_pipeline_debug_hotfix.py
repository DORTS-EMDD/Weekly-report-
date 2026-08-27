import datetime
import unittest
from pathlib import Path

import developer_debug_service
from streamlit_report_state import (
    begin_report_run,
    build_maiagent_failure_diagnostics,
    commit_successful_report,
    persist_current_run_debug_checkpoint,
    record_failed_report_attempt,
)


STREAMLIT_SOURCE = Path(__file__).with_name("streamlit_app.py")


class StreamlitPipelineDebugHotfixTests(unittest.TestCase):
    def test_new_run_does_not_expose_previous_debug_before_checkpoint(self):
        state = {
            "latest_debug_info": {"run_config": {"lookback_days": 7}},
            "latest_debug_payload": {"run_info": {"lookback_days": 7}},
            "latest_report_md": "previous report",
            "latest_report_integrity_failure": {"report_validation_passed": False},
        }
        begin_report_run(state)
        self.assertNotIn("latest_debug_info", state)
        self.assertNotIn("latest_debug_payload", state)
        self.assertNotIn("latest_report_integrity_failure", state)
        self.assertEqual(state["latest_report_md"], "previous report")

    def test_checkpoint_is_persisted_before_first_maiagent_call(self):
        source = STREAMLIT_SOURCE.read_text(encoding="utf-8")
        checkpoint_pos = source.index("checkpoint_debug_info, checkpoint_report_stats = _persist_pre_maiagent_debug_checkpoint(")
        first_call_pos = source.index("raw_report = call_maiagent_cloud(report_prompt)")
        self.assertLess(checkpoint_pos, first_call_pos)

        state = {}
        checkpoint = {
            "run_config": {"report_date": "2026-08-26", "lookback_days": 365},
            "selected_ids": [101],
            "pipeline_debug_stats": {"annual_gate_pass_by_bucket": {"2026-Q1": 2}},
            "temporal_retrieval": {"verified": 3},
            "report_generation_stage": "pre_maiagent_checkpoint",
        }
        stats = {
            "raw_count": 3,
            "filtered_count": 2,
            "ai_selected_count": 1,
            "report_validation_passed": None,
        }
        persist_current_run_debug_checkpoint(
            state,
            debug_info=checkpoint,
            debug_payload={"selected_ids": [101]},
            report_stats=stats,
            source_statuses=[{"status": "ok"}],
            run_config=checkpoint["run_config"],
        )
        self.assertEqual(
            state["latest_debug_info"]["report_generation_stage"],
            "pre_maiagent_checkpoint",
        )
        self.assertIsNone(state["latest_report_stats"]["report_validation_passed"])

    def test_maiagent_403_after_checkpoint_keeps_current_run_debug(self):
        state = {"latest_report_md": "old", "latest_pdf": b"old", "report_generated": True}
        checkpoint = {
            "run_config": {"report_date": "2026-08-26", "lookback_days": 365},
            "selected_ids": [202],
            "pipeline_debug_stats": {"annual_selected_by_bucket": {"2026-Q2": 1}},
            "report_generation_stage": "pre_maiagent_checkpoint",
        }
        stats = {"ai_selected_count": 1, "report_validation_passed": None}
        persist_current_run_debug_checkpoint(
            state,
            debug_info=checkpoint,
            debug_payload={"run_info": {"lookback_days": 365}, "selected_ids": [202]},
            report_stats=stats,
            source_statuses=[],
            run_config=checkpoint["run_config"],
        )
        failure_info, failure_stats = build_maiagent_failure_diagnostics(
            checkpoint,
            stats,
            RuntimeError("HTTP 403 permission denied"),
            attempted_call_count=1,
        )
        record_failed_report_attempt(
            state,
            failure_info["failure_diagnostics"],
            debug_info=failure_info,
            debug_payload={"selected_ids": failure_info["selected_ids"]},
            report_stats=failure_stats,
            source_statuses=[],
            run_config=checkpoint["run_config"],
        )
        self.assertEqual(state["latest_debug_info"]["selected_ids"], [202])
        self.assertIn("403", state["latest_debug_info"]["failure_diagnostics"]["error_message"])
        self.assertFalse(state["report_generated"])
        self.assertIsNone(state["latest_pdf"])

    def test_maiagent_timeout_after_checkpoint_has_no_fallback_report(self):
        state = {}
        checkpoint = {
            "run_config": {"report_date": "2026-08-26", "lookback_days": 30},
            "selected_ids": [303],
            "report_generation_stage": "pre_maiagent_checkpoint",
        }
        stats = {"ai_selected_count": 1, "report_validation_passed": None}
        failure_info, failure_stats = build_maiagent_failure_diagnostics(
            checkpoint,
            stats,
            TimeoutError("MaiAgent read timeout"),
            attempted_call_count=1,
        )
        record_failed_report_attempt(
            state,
            failure_info["failure_diagnostics"],
            debug_info=failure_info,
            debug_payload={"selected_ids": [303]},
            report_stats=failure_stats,
            source_statuses=[],
            run_config=checkpoint["run_config"],
        )
        self.assertEqual(state["latest_debug_payload"]["selected_ids"], [303])
        self.assertEqual(state["latest_report_md"], "")
        self.assertIsNone(state["latest_pdf"])
        self.assertFalse(state["report_generated"])

    def test_run_b_checkpoint_replaces_run_a_debug_after_failure(self):
        state = {}
        commit_successful_report(
            state,
            report_md="report A",
            pdf_bytes=b"pdf A",
            report_summary={},
            report_stats={},
            debug_info={"run_config": {"lookback_days": 7}, "selected_ids": [1]},
            debug_payload={"run_info": {"lookback_days": 7}, "selected_ids": [1]},
            source_statuses=[],
            run_config={"lookback_days": 7},
        )
        checkpoint_b = {
            "run_config": {"lookback_days": 365},
            "selected_ids": [999],
            "temporal_retrieval": {"verified": 51},
            "report_generation_stage": "pre_maiagent_checkpoint",
        }
        stats_b = {"ai_selected_count": 1, "report_validation_passed": None}
        persist_current_run_debug_checkpoint(
            state,
            debug_info=checkpoint_b,
            debug_payload={"run_info": {"lookback_days": 365}, "selected_ids": [999]},
            report_stats=stats_b,
            source_statuses=[],
            run_config=checkpoint_b["run_config"],
        )
        failure_info, failure_stats = build_maiagent_failure_diagnostics(
            checkpoint_b,
            stats_b,
            RuntimeError("HTTP 403"),
            attempted_call_count=1,
        )
        record_failed_report_attempt(
            state,
            failure_info["failure_diagnostics"],
            debug_info=failure_info,
            debug_payload={"selected_ids": [999]},
            report_stats=failure_stats,
            source_statuses=[],
            run_config=checkpoint_b["run_config"],
        )
        self.assertEqual(state["latest_debug_payload"]["selected_ids"], [999])
        self.assertEqual(state["latest_run_config"]["lookback_days"], 365)
        self.assertNotEqual(state["latest_debug_payload"]["selected_ids"], [1])

    def test_checkpoint_preserves_temporal_selector_diagnostics_and_success_can_upgrade(self):
        state = {}
        checkpoint = {
            "run_config": {"lookback_days": 365},
            "selected_ids": [401, 402],
            "selection_debug": {"final_selected_count": 2},
            "pipeline_debug_stats": {"annual_gate_pass_by_bucket": {"2025-Q4": 4}},
            "temporal_retrieval": {"verified_bucket": {"2025-Q4": 4}},
            "report_generation_stage": "pre_maiagent_checkpoint",
        }
        stats = {"ai_selected_count": 2, "report_validation_passed": None}
        persist_current_run_debug_checkpoint(
            state,
            debug_info=checkpoint,
            debug_payload={
                "pipeline_debug_stats": checkpoint["pipeline_debug_stats"],
                "temporal_retrieval": checkpoint["temporal_retrieval"],
            },
            report_stats=stats,
            source_statuses=[],
            run_config=checkpoint["run_config"],
        )
        self.assertEqual(
            state["latest_debug_info"]["temporal_retrieval"]["verified_bucket"]["2025-Q4"],
            4,
        )
        commit_successful_report(
            state,
            report_md="final report",
            pdf_bytes=b"final pdf",
            report_summary={},
            report_stats={"report_validation_passed": True},
            debug_info={"run_config": checkpoint["run_config"], "selected_ids": [401, 402]},
            debug_payload={"final_report_md": "final report"},
            source_statuses=[],
            run_config=checkpoint["run_config"],
        )
        self.assertTrue(state["report_generated"])
        self.assertEqual(state["latest_report_md"], "final report")
    def test_pipeline_stats_are_materialized_immediately_after_candidate_pool(self):
        source = STREAMLIT_SOURCE.read_text(encoding="utf-8")
        pool_pos = source.index("candidate_pool = prepare_candidate_pool(")
        stats_assignment = "pipeline_debug_stats = candidate_pool.get(\"pipeline_debug_stats\", {})"
        stats_pos = source.index(stats_assignment, pool_pos)
        failure_branch_pos = source.index("if not report_id_validation_after_retry.get(\"report_validation_passed\"):", stats_pos)
        success_tail_pos = source.index("postprocess_runtime = workflow_service.make_runtime(", stats_pos)
        self.assertLess(pool_pos, stats_pos)
        self.assertLess(stats_pos, failure_branch_pos)
        self.assertLess(stats_pos, success_tail_pos)
        self.assertEqual(source.count(stats_assignment), 1)

    def test_weekly_and_monthly_candidate_pool_stats_keep_one_source_dict(self):
        for report_period in ("weekly", "monthly"):
            stats = {"report_period": report_period, "raw_count": 4}
            candidate_pool = {"pipeline_debug_stats": stats}
            pipeline_debug_stats = candidate_pool.get("pipeline_debug_stats", {})
            self.assertIs(pipeline_debug_stats, stats)
            self.assertEqual(pipeline_debug_stats["report_period"], report_period)

    def test_missing_optional_candidate_pool_stats_use_stable_empty_dict(self):
        candidate_pool = {"raw_candidates": [], "filtered_candidates": []}
        pipeline_debug_stats = candidate_pool.get("pipeline_debug_stats", {})
        self.assertEqual(pipeline_debug_stats, {})

    def test_failure_debug_payload_preserves_candidate_pool_stats(self):
        stats = {
            "raw_count": 4,
            "pipeline_counts": {"filtered": 2},
            "temporal_retrieval": {"verified": 1},
        }
        failure_debug_info = {
            "run_config": {"report_date": datetime.date(2026, 8, 26)},
            "pipeline_debug_stats": stats,
            "report_validation_passed": False,
            "failure_diagnostics": {"missing_candidate_ids": [7]},
        }
        context = developer_debug_service.DeveloperDebugContext(
            current_run_config={"report_date": datetime.date(2026, 8, 26)},
            latest_run_config=None,
            app_source_hash="fixture",
            latest_report_md="",
            source_health_summary_builder=lambda _statuses: {},
            candidate_marker_remover=lambda value: value,
            now_provider=lambda: datetime.datetime(2026, 8, 26, 12, 0, 0),
        )
        payload = developer_debug_service.build_developer_debug_payload(
            failure_debug_info,
            {"report_validation_passed": False},
            [],
            context=context,
        )
        self.assertEqual(payload["pipeline_debug_stats"], stats)
        self.assertEqual(payload["pipeline_debug_stats"]["temporal_retrieval"]["verified"], 1)
        self.assertEqual(payload["failure_diagnostics"]["missing_candidate_ids"], [7])


if __name__ == "__main__":
    unittest.main()
