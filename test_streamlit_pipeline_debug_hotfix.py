import datetime
import unittest
from pathlib import Path

import developer_debug_service


STREAMLIT_SOURCE = Path(__file__).with_name("streamlit_app.py")


class StreamlitPipelineDebugHotfixTests(unittest.TestCase):
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
