import datetime
import json
import unittest
from dataclasses import replace

import config
import ddgs_search_service
import report_prompt_service
import report_workflow_service
import streamlit_sidebar_ui

from test_streamlit_ui_modules import FakeStreamlit, _sidebar_context
from unittest.mock import patch


def _candidate(candidate_id: int, category: str, title: str, *, subtype: str = "") -> dict:
    url = f"https://fixture.example/p4e1/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": f"Urban rail fixture content for {title}.",
        "date": "2026-08-12",
        "source": "Fixture Source",
        "source_display": "Fixture Source",
        "source_domain": "fixture.example",
        "source_tier": "B_professional",
        "source_quality": "A",
        "region": "日本",
        "classification": category,
        "preliminary_type": category,
        "operational_subtype": subtype,
        "url": url,
        "source_href": url,
    }


def _raw_report(candidates: list[dict]) -> str:
    blocks = []
    for heading, group in (
        ("## 一、技術新知", [candidates[0]]),
        ("## 二、重大事故", [candidates[1]]),
        ("## 三、營運動態", [candidates[2], candidates[3], candidates[4]]),
        ("## 四、機電標案", [candidates[5]]),
    ):
        blocks.append(heading)
        for candidate in group:
            report_category = "營運動態" if heading == "## 三、營運動態" else candidate["classification"]
            blocks.extend([
                f"<!-- candidate_id: {candidate['id']} -->",
                f"🔹 [{report_category}] {candidate['title']}",
                "• 發布/事件日期：2026-08-12",
                "• 國家/地區：日本",
                "• 相關機電系統：都市軌道系統",
                "• 事件摘要：Fixture summary with source-backed details.",
                "• 臺北捷運局啟示：Fixture integration reference.",
                f"• 資料來源：Fixture Source，2026-08-12，{candidate['url']}",
                "",
            ])
    return "\n".join(blocks)


class P4E1SidebarTests(unittest.TestCase):
    def test_four_formal_types_and_both_default_are_wired(self):
        context = replace(
            _sidebar_context(),
            default_selected_types=[
                "技術新知",
                "重大事故",
                "營運政策",
                "營運爭議",
                "service_opening",
                "機電標案",
            ],
            advanced_types=config.BACKEND_CATEGORY_TYPES,
            default_news_scope="both",
        )
        recorder = FakeStreamlit()
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(context)

        labels = {
            call["args"][0]
            for call in recorder.calls
            if call["name"] == "checkbox"
            and call["receiver"].startswith("expander")
        }
        self.assertTrue({"技術新知", "重大事故", "營運動態", "機電標案"}.issubset(labels))
        self.assertNotIn("營運議題", labels)
        self.assertEqual(result.news_scope, "both")
        self.assertEqual(
            result.selected_types,
            [
                "技術新知",
                "重大事故",
                "營運政策",
                "營運爭議",
                "service_opening",
                "機電標案",
            ],
        )

    def test_sidebar_derives_both_scope_when_taiwan_is_selected(self):
        context = replace(
            _sidebar_context(),
            default_selected_types=["技術新知"],
        )
        recorder = FakeStreamlit()
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(context)
        self.assertEqual(result.news_scope, "both")
        self.assertIn("臺灣", result.selected_regions)


class P4E1ScopeAndReportTests(unittest.TestCase):
    def test_run_settings_and_query_scope_mapping(self):
        settings = report_workflow_service.build_run_settings(
            report_workflow_service.RunSettingsContext(
                today=datetime.date(2026, 8, 13),
                lookback_days=7,
                selected_types=["技術新知", "重大事故", "營運政策", "營運爭議", "service_opening", "機電標案"],
                scope_mode="指定先進國家",
                selected_regions=["臺灣", "日本"],
                standards_enabled=False,
                include_research_supplement=False,
                demo_cache_mode_enabled=False,
                current_app_hash="fixture",
                report_period_labels={7: "週報"},
                long_term_target_labels={},
                report_target_by_days={7: 3},
                research_supplement_allowed_for_report=lambda days: False,
                get_research_supplement_lookback_days=lambda days: 90,
                news_scope="both",
            )
        )
        self.assertFalse(settings.is_global_scope)
        self.assertEqual(settings.active_regions, ["臺灣", "日本"])
        self.assertEqual(settings.report_scope_label, "國內＋國際")
        self.assertIn("捷運", settings.report_title)
        self.assertNotIn("國際捷運", settings.report_title)

        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知", "重大事故", "營運政策", "營運爭議", "service_opening", "機電標案"],
            active_regions=["日本"],
            lookback_days=7,
            lookback_int=7,
            is_global_scope=False,
            today=datetime.date(2026, 8, 13),
            news_scope="both",
            ddgs_client_factory=None,
        )
        queries, _ = ddgs_search_service.build_search_queries(context=context)
        metadata = context.query_metadata
        self.assertTrue(any(item.get("query_region") == "domestic" for item in metadata.values()))
        self.assertTrue(any(item.get("query_region") == "日本" for item in metadata.values()))
        self.assertTrue(any("electromechanical_procurement" == item.get("family") for item in metadata.values()))

    def test_prompt_maps_operational_subtypes_and_procurement(self):
        selected_types = ["技術新知", "重大事故", "營運政策", "營運爭議", "service_opening", "機電標案"]
        workflow_config = report_workflow_service.WorkflowConfig(
            today=datetime.date(2026, 8, 13),
            lookback_days=7,
            selected_types=selected_types,
            active_regions=["日本"],
            is_global_scope=False,
            standards_enabled=False,
            include_research_supplement=False,
            fast_mode_enabled=False,
            date_range="2026年08月06日 至 2026年08月13日",
            report_title="【2026/08/13】捷運技術週報",
            report_scope_label="國內＋國際",
            report_period_label="週報",
            news_scope="both",
        )
        runtime = report_workflow_service.make_runtime(
            workflow_config,
            report_workflow_service.WorkflowDependencies(prefetch_enabled=False),
        )
        candidates = [
            _candidate(3, "營運政策", "Metro fare policy"),
            _candidate(6, "機電標案", "Metro signalling procurement"),
        ]
        prompt = runtime.build_report_prompt(candidates, [], 2)
        self.assertIn("三、營運動態", prompt)
        self.assertIn("四、機電標案", prompt)
        self.assertNotIn("營運議題", prompt)
        selected = report_prompt_service.parse_selection_response(
            json.dumps({
                "selected_ids": [
                    {"id": 3, "category": "營運動態", "include_in_report": True},
                    {"id": 6, "category": "機電標案", "include_in_report": True},
                ]
            }, ensure_ascii=False),
            candidates,
            context=runtime._prompt_context(),
        )
        self.assertEqual([item["classification"] for item in selected], ["營運政策", "機電標案"])

    def test_final_report_has_four_formal_sections_and_keeps_sources(self):
        selected_types = ["技術新知", "重大事故", "營運政策", "營運爭議", "service_opening", "機電標案"]
        workflow_config = report_workflow_service.WorkflowConfig(
            today=datetime.date(2026, 8, 13),
            lookback_days=7,
            selected_types=selected_types,
            active_regions=["日本"],
            is_global_scope=False,
            standards_enabled=False,
            include_research_supplement=False,
            fast_mode_enabled=False,
            date_range="2026年08月06日 至 2026年08月13日",
            report_title="【2026/08/13】捷運技術週報",
            report_scope_label="國內＋國際",
            report_period_label="週報",
            news_scope="both",
        )
        candidates = [
            _candidate(1, "技術新知", "CBTC upgrade"),
            _candidate(2, "重大事故", "Metro incident"),
            _candidate(3, "營運政策", "Metro fare policy"),
            _candidate(4, "營運爭議", "Metro labour dispute"),
            _candidate(5, "營運政策", "Metro opens passenger service", subtype="service_opening"),
            _candidate(6, "機電標案", "Metro signalling procurement"),
        ]
        report = report_workflow_service.make_runtime(
            workflow_config,
            report_workflow_service.WorkflowDependencies(prefetch_enabled=False),
        ).postprocess_report(_raw_report(candidates), candidates)[0]

        self.assertEqual(report.count("## 三、營運動態"), 1)
        self.assertEqual(report.count("## 四、機電標案"), 1)
        self.assertIn("機電標案", report)
        for candidate in candidates:
            self.assertIn(candidate["url"], report)


if __name__ == "__main__":
    unittest.main()
