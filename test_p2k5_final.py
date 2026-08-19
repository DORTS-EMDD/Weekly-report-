import datetime
import json
import unittest
from pathlib import Path

from article_processor import _make_news_candidate, build_formal_report_source
from article_selector import build_selector_api
from ddgs_search_service import DdgsSearchContext, build_search_queries
from report_postprocessor import (
    ReportPostprocessContext,
    build_final_report_coverage_warning,
    normalize_journal_section_format,
    normalize_source_line,
    validate_authoritative_report,
)
from streamlit_report_state import (
    commit_successful_report,
    record_failed_report_attempt,
)


class P2K5FinalTests(unittest.TestCase):
    def test_formal_source_mapping_and_google_proxy_suppression(self):
        direct = build_formal_report_source(
            {
                "source": "news.ttv.com.tw",
                "source_domain": "news.ttv.com.tw",
                "url": "https://news.ttv.com.tw/news/123",
            }
        )
        self.assertEqual(direct["display_name"], "台視新聞網")
        self.assertEqual(direct["display_url"], "https://news.ttv.com.tw/news/123")

        proxy_url = "https://news.google.com/rss/articles/ABC?q=site%3Anews.yahoo.co.jp"
        proxy_candidate = _make_news_candidate(
            "Yahoo Metro report",
            "2026-08-17",
            "Yahoo! JAPAN",
            proxy_url,
            "Metro report",
            "fixture",
            "全球",
            "Google News 代理",
            query_metadata={"family": "technology", "lang": "en", "query_region": "global"},
        )
        formal = build_formal_report_source(proxy_candidate)
        self.assertEqual(formal["display_name"], "Yahoo! JAPAN")
        self.assertEqual(formal["display_url"], "https://news.yahoo.co.jp/")
        self.assertIn("source_proxy_url", proxy_candidate)
        self.assertNotIn("news.google.com/rss/articles/", json.dumps(formal, ensure_ascii=False))

    def test_source_renderer_keeps_name_and_visible_url(self):
        rendered = normalize_source_line(
            "• 資料來源：自由時報 https://news.ltn.com.tw/news/life/breakingnews/123。"
        )
        self.assertIn("自由時報", rendered)
        self.assertIn("https://news.ltn.com.tw/news/life/breakingnews/123", rendered)
        self.assertNotIn("[自由時報]", rendered)

    def test_journal_source_keeps_visible_article_url(self):
        context = ReportPostprocessContext(
            selected_types=["技術新知"],
            standards_enabled=False,
            include_research_supplement=True,
            lookback_int=30,
            today=datetime.date(2026, 8, 18),
            date_range="2026-07-20 至 2026-08-18",
            report_title="fixture",
            report_scope_label="全球",
            candidate_selection_text=lambda candidate: str(candidate.get("title", "")),
            infer_preliminary_type=lambda _candidate: "技術新知",
            is_urban_rail_candidate=lambda _text: True,
            research_section_heading=lambda _enabled: "國際學術期刊",
            id_validation_target={},
        )
        article_url = "https://link.springer.com/article/10.1007/something"
        report = (
            "## 國際學術期刊\n"
            "1、Urban Rail Transit study\n"
            "發表日期：2026-08-01\n"
            "期刊／來源：Urban Rail Transit\n"
            "研究主題：Metro maintenance\n"
            "研究摘要：A study.\n"
            "臺北捷運局啟示：可供維修規劃參考。\n"
            f"資料來源：Urban Rail Transit {article_url}\n"
            "📊 本期統計"
        )
        normalized = normalize_journal_section_format(
            report,
            [{"title": "Urban Rail Transit study", "journal_name": "Urban Rail Transit", "url": article_url}],
            context=context,
        )
        self.assertIn("Urban Rail Transit", normalized)
        self.assertIn(article_url, normalized)

    def test_generic_electromechanical_package_does_not_become_train(self):
        selector = build_selector_api(
            selected_types=["技術新知", "機電標案"],
            active_regions=[],
            lookback_days=30,
            lookback_int=30,
            fast_mode_enabled=False,
            is_global_scope=True,
            today=datetime.date(2026, 8, 18),
            news_scope="international",
            _search_family_from_query=lambda _query: "electromechanical_procurement",
            _search_language_from_query=lambda _query: "en",
            create_requests_session=lambda: None,
            _profile_timing_add=lambda *_args: None,
        )
        generic = {
            "title": "Taoyuan Brown Line E&M turnkey package for metro trains",
            "snippet": "The electromechanical systems package contract covers the line project.",
        }
        self.assertEqual(selector["_core_systems_for_candidate"](generic), [])
        detailed = {
            "title": "Gold Coast Light Rail signalling and communications package",
            "snippet": "The contract includes signalling and communications systems.",
        }
        self.assertEqual(
            selector["_core_systems_for_candidate"](detailed),
            ["號誌", "通訊"],
        )

    def test_annual_planner_executes_selected_policy_and_dispute_families(self):
        context = DdgsSearchContext(
            selected_types=["技術新知", "重大事故", "營運政策", "營運爭議", "機電標案"],
            active_regions=[],
            lookback_days=365,
            lookback_int=365,
            is_global_scope=True,
            today=datetime.date(2026, 8, 18),
            ddgs_client_factory=None,
            news_scope="international",
        )
        build_search_queries(context=context)
        families = [metadata.get("family") for metadata in context.query_metadata.values()]
        self.assertIn("policy", families)
        self.assertIn("dispute", families)
        self.assertIn("policy", context.planned_required_families)
        self.assertIn("dispute", context.planned_required_families)

    def test_annual_coverage_uses_structured_final_candidate_dates(self):
        report_end = datetime.date(2026, 8, 18)
        candidates = [
            {"date": "2025-10-16"},
            {"date": "2026-02-10"},
            {"date": "2026-05-11"},
            {"date": "2026-08-01"},
        ]
        coverage = build_final_report_coverage_warning(
            "沒有可解析日期的 rendered text",
            365,
            report_end,
            structured_candidates=candidates,
            context=ReportPostprocessContext(
                selected_types=["技術新知"],
                standards_enabled=False,
                include_research_supplement=False,
                lookback_int=365,
                today=report_end,
                date_range="fixture",
                report_title="fixture",
                report_scope_label="全球",
                candidate_selection_text=lambda _candidate: "",
                infer_preliminary_type=lambda _candidate: "技術新知",
                is_urban_rail_candidate=lambda _text: True,
                research_section_heading=lambda _enabled: "",
                id_validation_target={},
            ),
        )
        self.assertEqual(coverage["coverage_date_source"], "structured_final_candidates")
        self.assertEqual(coverage["formal_news_with_valid_date_count"], 4)
        self.assertGreaterEqual(len(coverage["quarterly_coverage_buckets"]), 3)

    def test_annual_rebalance_preserves_quality_across_quarters(self):
        selector = build_selector_api(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=365,
            lookback_int=365,
            fast_mode_enabled=False,
            is_global_scope=True,
            today=datetime.date(2026, 8, 18),
            news_scope="international",
            _search_family_from_query=lambda _query: "technology",
            _search_language_from_query=lambda _query: "en",
            create_requests_session=lambda: None,
            _profile_timing_add=lambda *_args: None,
        )
        def candidate(identifier: int, date_value: str) -> dict:
            return {
                "id": identifier,
                "candidate_id": identifier,
                "date": date_value,
                "title": f"Urban rail technical candidate {identifier}",
                "url": f"https://example.com/{identifier}",
                "source_tier": "B_professional",
                "final_selection_score": 92,
                "python_score": 92,
            }

        selected = [candidate(1, "2026-08-01"), candidate(2, "2026-07-10"), candidate(3, "2026-06-25")]
        pool = selected + [
            candidate(4, "2026-05-10"),
            candidate(5, "2026-02-10"),
            candidate(6, "2025-10-16"),
        ]
        balanced = selector["rebalance_selected_candidates"](selected, pool)
        quarters = {
            f"{datetime.date.fromisoformat(item['date']).year:04d}-Q{((datetime.date.fromisoformat(item['date']).month - 1) // 3) + 1}"
            for item in balanced
        }
        self.assertGreaterEqual(len(quarters), 3)

    def test_annual_common_english_phrase_requires_retry_validation(self):
        selected = [{
            "id": 1,
            "candidate_id": 1,
            "classification": "技術新知",
            "preliminary_type": "技術新知",
            "country": "美國",
            "core_systems": [],
        }]
        report = (
            "一、技術新知\n"
            "<!-- candidate_id: 1 -->\n"
            "🔹 [技術新知] 紐約地鐵環境控制研究\n"
            "• 發布/事件日期：2026-08-01\n"
            "• 國家：美國\n"
            "• 事件摘要：The passenger service study concerns a subway platform.\n"
            "• 臺北捷運局啟示：應評估 railway station junction 的介面管理。\n"
            "• 資料來源：https://example.com/article\n"
        )
        validation = validate_authoritative_report(report, selected, selected_types=["技術新知"])
        self.assertFalse(validation["report_validation_passed"] if "report_validation_passed" in validation else validation["valid"])
        self.assertTrue(any(issue["code"] == "untranslated_common_english_phrase" for issue in validation["content_quality_issues"]))

    def test_failed_attempt_preserves_previous_successful_streamlit_result(self):
        state = {
            "latest_report_md": "old report",
            "latest_pdf": b"old pdf",
            "latest_report_stats": {"generated_at": "2026-08-18T08:00:00"},
            "report_generated": True,
            "email_sent": True,
        }
        previous = record_failed_report_attempt(state, {"reason": "validation_failed"})
        self.assertEqual(state["latest_report_md"], "old report")
        self.assertEqual(state["latest_pdf"], b"old pdf")
        self.assertTrue(state["report_generated"])
        self.assertEqual(previous["latest_report_md"], "old report")

        commit_successful_report(
            state,
            report_md="new report",
            pdf_bytes=b"new pdf",
            report_summary={},
            report_stats={},
            debug_info={},
            debug_payload={},
            source_statuses=[],
            run_config={},
        )
        self.assertEqual(state["latest_report_md"], "new report")
        self.assertEqual(state["latest_pdf"], b"new pdf")
        self.assertTrue(state["report_generated"])
        self.assertFalse(state["email_sent"])
        self.assertNotIn("latest_report_integrity_failure", state)

    def test_scope_caption_removed_from_user_facing_sources(self):
        sidebar = Path("streamlit_sidebar_ui.py").read_text(encoding="utf-8")
        demo = Path("streamlit_app.py").read_text(encoding="utf-8")
        self.assertNotIn("全球模式會自動納入臺灣與國際捷運資料。", sidebar)
        self.assertNotIn('f"> 報導範圍：{report_scope_label}"', demo)


if __name__ == "__main__":
    unittest.main()
