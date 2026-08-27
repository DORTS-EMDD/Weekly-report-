import datetime
import importlib
import unittest
from copy import deepcopy
from unittest import mock

import report_workflow_service as workflow_service
import streamlit_app as app
from temporal_retrieval_service import TemporalRetrievalRequest


def _fixture_config(today: datetime.date | None = None) -> workflow_service.WorkflowConfig:
    today = today or datetime.date(2026, 8, 11)
    return workflow_service.WorkflowConfig(
        today=today,
        lookback_days=7,
        selected_types=["技術新知", "重大事故", "營運政策", "營運爭議"],
        active_regions=["美國"],
        is_global_scope=True,
        standards_enabled=False,
        include_research_supplement=False,
        fast_mode_enabled=False,
        date_range="2026年08月05日 至 2026年08月11日",
        report_title="fixture",
        report_scope_label="全球",
        report_period_label="週報",
    )


def _rss_fixture(today: datetime.date) -> str:
    rows = [
        (
            "Company wins CBTC contract for Metro Line X",
            "The company won the CBTC contract for Metro Line X.",
        ),
        (
            "Metro orders 20 new trains",
            "The metro ordered 20 new trains.",
        ),
        (
            "Feasibility study awarded for new depot",
            "A feasibility study was awarded for a new depot.",
        ),
        (
            "Construction begins on metro signalling upgrade",
            "Construction begins on a metro signalling upgrade.",
        ),
        (
            "Metro deploys CBTC with moving-block operation, increasing capacity by 20%",
            "The metro rail system deployed moving-block CBTC and increased capacity by 20%.",
        ),
        (
            "New metro trains use SiC traction inverters reducing traction energy consumption",
            "The metro rail trains use silicon carbide traction inverters to reduce traction energy consumption.",
        ),
        (
            "Pilot uses onboard sensors for continuous track condition monitoring",
            "A metro rail pilot uses onboard sensors for continuous track condition monitoring.",
        ),
    ]
    lines = ["【RSS來源：Railway-News】"]
    for index, (title, snippet) in enumerate(rows, 1):
        lines.extend([
            f"日期：{(today - datetime.timedelta(days=1)).isoformat()}",
            f"標題：{title}",
            f"摘要：{snippet}",
            f"連結：https://railway-news.com/fixture-{index}",
            "",
        ])
    return "\n".join(lines)


def _candidate(candidate_id: int, category: str = "技術新知") -> dict:
    url = f"https://example.com/fixture/{candidate_id}"
    candidate = {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": "Metro deploys CBTC moving-block control",
        "snippet": "The metro rail system deployed moving-block CBTC after testing.",
        "date": app.today.isoformat(),
        "classification": category,
        "preliminary_type": category,
        "region": "美國",
        "query_region": "美國",
        "source": "Fixture Source",
        "source_display": "Fixture Source",
        "source_domain": "example.com",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
    }
    candidate.update(app.evaluate_category_gates(candidate))
    return candidate


class ReportWorkflowServiceTests(unittest.TestCase):
    def test_annual_mixed_candidate_is_verified_before_materialization(self):
        config = workflow_service.WorkflowConfig(
            today=datetime.date(2026, 8, 24),
            lookback_days=365,
            selected_types=["技術新知"],
            active_regions=[],
            is_global_scope=True,
            standards_enabled=False,
            include_research_supplement=False,
            fast_mode_enabled=False,
            date_range="2025年08月24日 至 2026年08月24日",
            report_title="annual fixture",
            report_scope_label="全球",
            report_period_label="年報",
        )
        runtime = workflow_service.make_runtime(
            config,
            workflow_service.WorkflowDependencies(prefetch_enabled=False),
        )
        candidate = runtime._make_candidate(
            title="Metro deploys CBTC moving-block control increasing capacity",
            date="2026-08-21",
            source="Railway News",
            url="https://railway-news.com/annual-fixture",
            snippet="The metro rail system deployed moving-block CBTC after testing, improving capacity and reliability.",
            query="metro signalling",
            region="未判定",
            source_type="官方 RSS",
            raw_provenance={
                "raw_title": "Metro deploys CBTC moving-block control increasing capacity",
                "raw_url": "https://railway-news.com/annual-fixture",
                "raw_publication_value": "2026-08-21",
                "search_provider": "RSS",
                "original_provider_metadata": {"published": "2026-08-21"},
            },
        )
        runtime.parse_candidates = lambda _raw_rss, _raw_ddg: [candidate]
        runtime.temporal_plan = runtime.temporal_router.build_plan(
            TemporalRetrievalRequest(
                report_date=config.today,
                lookback_days=config.lookback_days,
                selected_types=tuple(config.selected_types),
            )
        )

        pool = runtime.prepare_candidate_pool("", "")

        all_candidates = pool["model_candidates"] + pool["excluded_candidates"]
        verified = next(item for item in all_candidates if item["title"] == candidate["title"])
        self.assertEqual(verified["date_verification_status"], "verified")
        self.assertEqual(verified["verified_bucket"], "2026-Q3")
        self.assertEqual(
            pool["candidate_pool_timings"]["temporal_candidate_verification_calls"],
            1,
        )
        self.assertNotIn("verified_bucket_missing", verified.get("selector_contract_failures", []))

    def test_automation_project_only_gate_and_technical_retention(self):
        config = _fixture_config()
        runtime = workflow_service.make_runtime(
            config,
            workflow_service.WorkflowDependencies(prefetch_enabled=False),
        )
        pool = runtime.prepare_candidate_pool(_rss_fixture(config.today), "")
        model_titles = {item["title"] for item in pool["model_candidates"]}
        excluded_by_title = {
            item["title"]: item for item in pool["excluded_candidates"]
        }
        project_only_titles = {
            "Company wins CBTC contract for Metro Line X",
            "Metro orders 20 new trains",
            "Feasibility study awarded for new depot",
            "Construction begins on metro signalling upgrade",
        }
        technical_titles = {
            "Metro deploys CBTC with moving-block operation, increasing capacity by 20%",
            "New metro trains use SiC traction inverters reducing traction energy consumption",
            "Pilot uses onboard sensors for continuous track condition monitoring",
        }
        self.assertTrue(project_only_titles.isdisjoint(model_titles))
        self.assertTrue(technical_titles.issubset(model_titles))
        for title in project_only_titles:
            self.assertFalse(excluded_by_title[title]["category_gates"]["technology"])

    def test_streamlit_and_automation_candidate_pool_match_offline(self):
        raw_rss = _rss_fixture(app.today)
        config = app._workflow_config()
        shared_pool = workflow_service.make_runtime(
            config,
            workflow_service.WorkflowDependencies(prefetch_enabled=False),
        ).prepare_candidate_pool(raw_rss, "")
        original_dependencies = app._workflow_dependencies
        try:
            app._workflow_dependencies = lambda **_kwargs: workflow_service.WorkflowDependencies(
                prefetch_enabled=False,
            )
            streamlit_pool = app.prepare_candidate_pool(raw_rss, "")
        finally:
            app._workflow_dependencies = original_dependencies

        def summarize(pool):
            return [
                (
                    item["title"],
                    item.get("category_gates", {}).get("technology", False),
                    item.get("exclude_reason", ""),
                )
                for item in pool["model_candidates"] + pool["excluded_candidates"]
            ]

        self.assertEqual(summarize(streamlit_pool), summarize(shared_pool))

    def test_streamlit_and_automation_selection_match(self):
        original_types = app.selected_types
        try:
            app.selected_types = ["技術新知", "重大事故", "營運政策", "營運爭議"]
            candidates = [_candidate(1), _candidate(2, "營運政策")]
            config = app._workflow_config()
            expected = workflow_service.select_candidates_by_python(
                deepcopy(candidates),
                config=config,
            )
            actual = app.select_candidates_by_python(deepcopy(candidates))
        finally:
            app.selected_types = original_types
        self.assertEqual(
            [item.get("id") for item in actual],
            [item.get("id") for item in expected],
        )

    def test_streamlit_and_automation_postprocess_match(self):
        original_validation = dict(app.LAST_REPORT_ID_VALIDATION)
        candidate = _candidate(1)
        raw_report = "\n".join([
            "<!-- candidate_id: 1 -->",
            "🔹 [技術新知] 都市軌道 CBTC 移動閉塞控制部署",
            "• 發布/事件日期：2026-08-10",
            "• 國家/地區：美國",
            "• 相關機電系統：CBTC",
            "• 事件摘要：",
            "都市軌道系統導入移動閉塞控制並完成測試。",
            "• 臺北捷運局啟示：可供系統整合研析參考。",
            "• 資料來源：Fixture Source",
        ])
        try:
            config = app._workflow_config()
            shared = workflow_service.make_runtime(
                config,
                workflow_service.WorkflowDependencies(prefetch_enabled=False),
            ).postprocess_report(raw_report, [candidate])[0]
            streamlit = app.remove_authoritative_candidate_markers(raw_report)
        finally:
            app.LAST_REPORT_ID_VALIDATION.clear()
            app.LAST_REPORT_ID_VALIDATION.update(original_validation)
        self.assertEqual(streamlit, shared)

    def test_final_counts_use_canonical_blocks_and_exclude_skipped_candidates(self):
        config = _fixture_config()
        runtime = workflow_service.make_runtime(
            config,
            workflow_service.WorkflowDependencies(prefetch_enabled=False),
        )
        accepted = _candidate(15)
        skipped = _candidate(16)
        skipped["title"] = "美國 Blue Line 輕軌延伸計畫"
        skipped["snippet"] = "Blue Line extension project information."
        raw_report = "\n".join([
            "<!-- candidate_id: 15 -->",
            "🔹 [技術新知] 都市軌道 CBTC 移動閉塞控制部署",
            "• 發布/事件日期：2026-08-10",
            "• 國家/地區：美國",
            "• 相關機電系統：號誌系統",
            "• 事件摘要：都市軌道系統導入移動閉塞控制並完成測試。",
            "• 臺北捷運局啟示：可作為列車控制驗證與系統介面管理參考。",
            "• 資料來源：[Fixture Source](https://example.com/fixture/15)",
            "",
            "<!-- candidate_id: 16 -->",
            "🔹 [技術新知] 美國 Blue Line 輕軌延伸計畫",
        ])

        result = runtime.postprocess_report_with_diagnostics(
            raw_report,
            [accepted, skipped],
        )
        diagnostics = result["id_validation"]
        rendered = result["clean_report"]

        self.assertEqual(diagnostics["skipped_candidate_ids"], [])
        self.assertIn("Blue Line", rendered)
        self.assertEqual(result["reconciled_accepted_count"], 2)
        self.assertEqual(result["final_rendered_report_count"], app.count_report_items(rendered))
        self.assertEqual(result["final_rendered_report_count"], 2)
        self.assertEqual(diagnostics["final_candidate_ids"], [15, 16])
        self.assertTrue(diagnostics["final_candidate_id_integrity_passed"])
        self.assertEqual(diagnostics["fallback_block_count"], 0)
        self.assertFalse(diagnostics["report_validation_passed"])

    def test_main_import_is_safe_and_does_not_run_workflow(self):
        with mock.patch("report_workflow_service.run_report_workflow") as run_workflow:
            import main

            importlib.reload(main)
        run_workflow.assert_not_called()
        self.assertFalse(hasattr(main, "RSS_SOURCES"))
        self.assertFalse(hasattr(main, "DDGS"))


if __name__ == "__main__":
    unittest.main()
