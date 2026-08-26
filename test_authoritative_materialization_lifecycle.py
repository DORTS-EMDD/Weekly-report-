import copy
import datetime
import unittest

import report_workflow_service as workflow_service
from test_report_workflow_service import _candidate


def _config() -> workflow_service.WorkflowConfig:
    return workflow_service.WorkflowConfig(
        today=datetime.date(2026, 8, 11),
        lookback_days=7,
        selected_types=["技術新知", "重大事故", "營運政策", "營運爭議"],
        active_regions=["美國", "印尼"],
        is_global_scope=True,
        standards_enabled=False,
        include_research_supplement=False,
        fast_mode_enabled=False,
        date_range="2026年08月05日 至 2026年08月11日",
        report_title="lifecycle fixture",
        report_scope_label="全球",
        report_period_label="週報",
    )


def _prefetch_stats() -> dict:
    return {
        "limit": 1,
        "forward_enrichment_budget": 0,
        "general_rescue_budget": 1,
        "procurement_rescue_budget": 0,
        "annual_general_rescue_budget": 0,
        "eligible_count": 1,
        "attempted_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "skipped_limit_count": 0,
        "forward_enrichment_candidate_count": 0,
        "forward_enrichment_attempted_count": 0,
        "forward_enrichment_success_count": 0,
        "forward_enrichment_skipped_count": 0,
        "forward_enrichment_failure_reason_counts": {},
        "procurement_rescue_candidate_count": 0,
        "procurement_rescue_attempted_count": 0,
        "procurement_rescue_success_count": 0,
        "elapsed_seconds": 0.0,
    }


class AuthoritativeMaterializationLifecycleTests(unittest.TestCase):
    def _run_fixture(self, mutate=None) -> tuple[dict, list[tuple[bool, str]]]:
        config = _config()
        candidate = _candidate(1)
        candidate["date"] = config.today.isoformat()
        runtime = workflow_service.make_runtime(
            config,
            workflow_service.WorkflowDependencies(prefetch_enabled=mutate is not None),
        )
        runtime.parse_candidates = lambda _raw_rss, _raw_ddg: [copy.deepcopy(candidate)]
        materialization_calls: list[tuple[bool, str]] = []
        original_materialize = runtime._materialize_authoritative_candidate

        def traced_materialize(candidate, *, authoritative=True):
            materialization_calls.append((authoritative, candidate.get("snippet", "")))
            return original_materialize(candidate, authoritative=authoritative)

        runtime._materialize_authoritative_candidate = traced_materialize
        if mutate is not None:
            def fake_prefetch(candidates):
                mutate(candidates[0])
                candidates[0]["prefetch_status"] = "success"
                return _prefetch_stats()

            runtime.selector_api["prefetch_candidates_before_filter"] = fake_prefetch
        return runtime.prepare_candidate_pool("", ""), materialization_calls

    def test_unchanged_candidate_skips_second_materialization(self):
        pool, calls = self._run_fixture()
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            pool["authoritative_materialization_lifecycle"],
            {
                "initial_materialization_count": 1,
                "refresh_count": 0,
                "unchanged_skip_count": 1,
            },
        )

    def test_prefetch_text_change_refreshes_exactly_once(self):
        pool, calls = self._run_fixture(
            lambda candidate: candidate.update({
                "snippet": candidate.get("snippet", "")
                + " The deployment uses CBTC signalling to improve metro capacity."
            })
        )
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0][0] is False)
        self.assertTrue(calls[1][0] is True)
        self.assertEqual(pool["authoritative_materialization_lifecycle"]["refresh_count"], 1)

    def test_geography_evidence_change_refreshes_exactly_once(self):
        pool, calls = self._run_fixture(
            lambda candidate: candidate.update({
                "title": "Jakarta MRT deploys a new metro signalling system",
                "snippet": "Jakarta MRT in Indonesia deploys a new metro signalling system.",
            })
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(pool["authoritative_materialization_lifecycle"]["refresh_count"], 1)
        materialized = pool["model_candidates"] + pool["excluded_candidates"]
        self.assertTrue(any(item.get("resolved_region") in {"印尼", "Indonesia"} for item in materialized))

    def test_em_evidence_change_refreshes_and_updates_systems(self):
        def enrich(candidate):
            candidate.update({
                "title": "Metro deploys a new signalling system",
                "snippet": "The metro deploys a new CBTC signalling system for passenger service.",
            })

        pool, calls = self._run_fixture(enrich)
        self.assertEqual(len(calls), 2)
        self.assertEqual(pool["authoritative_materialization_lifecycle"]["refresh_count"], 1)
        materialized = pool["model_candidates"] + pool["excluded_candidates"]
        self.assertTrue(any("號誌" in (item.get("core_systems") or []) for item in materialized))

    def test_resolved_url_change_refreshes_event_identity_inputs(self):
        pool, calls = self._run_fixture(
            lambda candidate: candidate.update({
                "resolved_article_url": "https://railway-news.com/fixture/1-resolved",
            })
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(pool["authoritative_materialization_lifecycle"]["refresh_count"], 1)


if __name__ == "__main__":
    unittest.main()
