import datetime
import unittest

from article_processor import _candidate_date_obj, _canonical_candidate_region
from article_selector import build_selector_api
import pdf_exporter
import streamlit_app as app


def _candidate(candidate_id, title, snippet, *, category="技術新知", date="2026-08-01", region="西班牙", query_region="西班牙", url_host="example.com"):
    url = f"https://{url_host}/fixture/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": date,
        "classification": category,
        "preliminary_type": category,
        "region": region,
        "query_region": query_region,
        "source": "Fixture Source",
        "source_display": "Fixture Source",
        "source_domain": url_host,
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
    }


class V21QualityGateTests(unittest.TestCase):
    def test_region_resolution_prefers_article_entities_over_query_region(self):
        fixtures = [
            ("Seattle light rail power outage", "美國"),
            ("Washington Metro Red Line service update", "美國"),
            ("LTA Singapore LRT station safety", "新加坡"),
            ("Seoul Metro station upgrade", "韓國"),
            ("Tokyo Metro signalling upgrade", "日本"),
            ("MTR Hong Kong station works", "香港"),
        ]
        for title, expected in fixtures:
            candidate = _candidate(1, title, title, url_host="example.com")
            self.assertEqual(_canonical_candidate_region(candidate), expected)
            self.assertNotEqual(candidate["region_resolution_method"], "query_region_fallback")

    def test_official_domain_resolves_region_when_title_is_generic(self):
        candidate = _candidate(1, "LRT station safety improvement", "Operator announces measures", url_host="lta.gov.sg")
        candidate["source"] = "LTA"
        self.assertEqual(_canonical_candidate_region(candidate), "新加坡")
        self.assertIn(candidate["region_resolution_method"], {"official_operator_or_source", "official_source_domain"})

    def test_date_normalization_is_date_only(self):
        self.assertEqual(_candidate_date_obj("2026-07-23T00:00:00+00:00"), datetime.date(2026, 7, 23))
        self.assertEqual(app._normalize_report_date_text("2026-07-23T00:00:00+00:00"), "2026-07-23")

    def test_monthly_period_excludes_previous_day(self):
        selector = build_selector_api(
            selected_types=["技術新知"],
            active_regions=["美國"],
            lookback_days=30,
            lookback_int=30,
            fast_mode_enabled=False,
            is_global_scope=True,
            today=datetime.date(2026, 8, 7),
            _search_family_from_query=lambda _query: "technical",
            _search_language_from_query=lambda _query: "en",
            create_requests_session=lambda: None,
            _profile_timing_add=lambda *_args: None,
        )
        candidate = _candidate(
            1,
            "Seattle light rail signalling upgrade",
            "Seattle light rail signalling upgrade improves train control.",
            date="2026-07-07",
            region="美國",
            query_region="美國",
        )
        kept, _reason = selector["preliminary_filter_candidate"](candidate)
        self.assertFalse(kept)
        self.assertEqual(candidate["date_validation"], "out_of_range_old")

    def test_major_accident_gate_requires_major_evidence(self):
        outage = _candidate(1, "Seattle light rail power outage suspends service", "Power outage causes service suspension.", category="重大事故")
        collision = _candidate(2, "Gelsenkirchen tram collision leaves 25 people injured", "Two trams collided and 25 people were injured.", category="重大事故", region="德國", query_region="德國")
        self.assertFalse(app.evaluate_category_gates(outage)["category_gates"]["major_accident"])
        self.assertTrue(app.evaluate_category_gates(collision)["category_gates"]["major_accident"])

    def test_post_incident_lta_policy_is_not_major_accident(self):
        candidate = _candidate(
            1,
            "LTA and operators discuss measures to improve LRT station safety following incidents",
            "Singapore LRT station safety improvement plan and governance measures.",
            category="重大事故",
            region="新加坡",
            query_region="新加坡",
        )
        gates = app.evaluate_category_gates(candidate)
        self.assertFalse(gates["category_gates"]["major_accident"])
        self.assertEqual(gates["primary_category"], "營運政策")
        self.assertEqual(gates["category_reclassification"]["new_category"], "營運政策")

    def test_project_only_technical_candidates_are_excluded(self):
        fixtures = [
            ("Company wins CBTC contract for Metro Line X", "The company won the CBTC contract for Metro Line X."),
            ("Metro orders 20 new trains", "The metro ordered 20 new trains."),
            ("Feasibility study awarded for new depot", "A feasibility study was awarded for a new depot."),
            ("Construction begins on metro signalling upgrade", "Construction begins on a metro signalling upgrade."),
        ]
        for index, (title, snippet) in enumerate(fixtures, 1):
            candidate = _candidate(index, title, snippet)
            gates = app.evaluate_category_gates(candidate)
            self.assertFalse(gates["category_gates"]["technology"], title)
            self.assertNotEqual(gates["primary_category"], "技術新知")

    def test_project_candidates_with_technical_detail_are_retained(self):
        fixtures = [
            ("Metro deploys CBTC with moving-block operation, increasing capacity by 20%", "The metro rail system deployed moving-block CBTC and increased capacity by 20%."),
            ("New metro trains use SiC traction inverters reducing traction energy consumption", "The metro rail trains use silicon carbide traction inverters to reduce traction energy consumption."),
            ("Pilot uses onboard sensors for continuous track condition monitoring", "A metro rail pilot uses onboard sensors for continuous track condition monitoring."),
        ]
        for index, (title, snippet) in enumerate(fixtures, 1):
            candidate = _candidate(index, title, snippet)
            gates = app.evaluate_category_gates(candidate)
            self.assertTrue(gates["category_gates"]["technology"], title)
            self.assertEqual(gates["primary_category"], "技術新知")

    def test_multi_candidate_model_block_is_preserved_and_sources_are_merged(self):
        candidates = [
            _candidate(2, "Bakerloo Line depot feasibility study", "研究摘要", url_host="railway-news.com"),
            _candidate(3, "Bakerloo Line depot and sidings feasibility", "研究摘要", url_host="railuk.com"),
        ]
        report = "\n".join([
            "<!-- candidate_id: 2 -->",
            "<!-- candidate_id: 3 -->",
            "🔹 [技術新知] Bakerloo Line 機廠及側線可行性研究",
            "• 發布/事件日期：2026-08-01",
            "• 國家/地區：英國",
            "• 相關機電系統：機廠與側線",
            "• 事件摘要：",
            "研究摘要",
            "• 臺北捷運局啟示：可供專案研析參考。",
            "• 資料來源：原始來源",
        ])
        original = (app.selected_types, app.standards_enabled, app.include_research_supplement)
        try:
            app.selected_types = ["技術新知"]
            app.standards_enabled = False
            app.include_research_supplement = False
            output, dropped = app.restore_missing_selected_report_items(report, candidates)
        finally:
            app.selected_types, app.standards_enabled, app.include_research_supplement = original
        self.assertEqual(dropped, [])
        self.assertEqual(app.count_report_items(output), 1)
        self.assertIn("railway-news.com", output)
        self.assertNotIn("railuk.com", output)
        self.assertEqual(app.LAST_REPORT_ID_VALIDATION["preserved_model_block_count"], 1)
        self.assertEqual(app.LAST_REPORT_ID_VALIDATION["merged_event_groups"], [[2, 3]])
        self.assertEqual(app.LAST_REPORT_ID_VALIDATION["fallback_block_count"], 0)

    def test_fallback_unescapes_and_does_not_emit_english_snippet_or_iso_date(self):
        candidate = _candidate(
            1,
            "Buangkok MRT station&#8217;s safety upgrade",
            "The English snippet must not be copied into the fallback.",
            date="2026-07-23T00:00:00+00:00",
            region="新加坡",
            query_region="新加坡",
        )
        fallback = app._fallback_report_block(candidate)
        self.assertNotIn("&#8217", fallback)
        self.assertNotIn("The English snippet", fallback)
        self.assertEqual(fallback, "")

    def test_fallback_with_insufficient_source_is_skipped(self):
        candidate = _candidate(1, "CBTC upgrade", "", url_host="")
        candidate["url"] = ""
        candidate["source_href"] = ""
        self.assertEqual(app._fallback_report_block(candidate), "")

    def test_buangkok_title_conflict_is_not_replaced_by_bukit_panjang(self):
        candidate = _candidate(
            1,
            "Buangkok MRT station safety upgrade",
            "Buangkok MRT station safety upgrade improves station access.",
            region="新加坡",
            query_region="新加坡",
        )
        report = "\n".join([
            "<!-- candidate_id: 1 -->",
            "🔹 [技術新知] 武吉班讓站改善工程",
            "• 發布/事件日期：2026-08-01",
            "• 國家/地區：新加坡",
            "• 事件摘要：",
            "Buangkok MRT station safety upgrade improves station access.",
            "• 臺北捷運局啟示：可供車站設備改善參考。",
            "• 資料來源：https://example.com/buangkok",
        ])
        output = app.repair_generic_report_titles(report, [candidate])
        self.assertIn("Buangkok MRT 站", output)
        self.assertNotIn("武吉班讓", output)

    def test_system_normalization_preserves_specific_multi_system_evidence(self):
        text = "機電系統之介面整合與測試驗證，確保控制中心與列車通訊正常。"
        normalized = app.normalize_electromechanical_system_value(text)
        self.assertIn("通訊系統", normalized)
        self.assertNotIn("介面整合與測試驗證", normalized)

    def test_gelsenkirchen_event_fingerprint_keeps_city_boundary(self):
        first = _candidate(1, "Gelsenkirchen tram collision leaves dozens injured", "Gelsenkirchen tram collision", category="重大事故", region="德國", query_region="德國")
        second = _candidate(2, "Tram collision injures 25 people", "Gelsenkirchen tram collision", category="重大事故", region="德國", query_region="德國")
        other_city = _candidate(3, "Berlin tram collision injures 25 people", "Berlin tram collision", category="重大事故", region="德國", query_region="德國")
        self.assertTrue(app._is_same_report_event(first, second))
        self.assertFalse(app._is_same_report_event(first, other_city))

    def test_short_report_pdf_has_footer_without_forced_grouping(self):
        report = "\n".join([
            "# 國際捷運技術週報",
            "",
            "## 一、技術新知",
            "",
            "🔹 [技術新知] CBTC 系統升級",
            "• 發布/事件日期：2026-08-01",
            "• 事件摘要：系統完成測試驗證。",
            "",
            "## 二、重大事故",
            "",
            "本期未發現符合條件資料。",
            "",
            "📊 本期統計：正式新聞共 1 則。",
            "⏰ 報告產出時間：2026年08月07日 週五",
        ])
        pdf_bytes = pdf_exporter.streamlit_markdown_to_pdf_bytes(
            report,
            marker_cleaner=lambda value: value,
            font_registrar=lambda: ("Helvetica", "Helvetica"),
            line_compactor=lambda value: value,
            rich_text_renderer=lambda value, *_fonts: value,
            token_wrapper=lambda value, _limit: value,
            candidate_id_pattern=app.REPORT_CANDIDATE_ID_PATTERN,
        )
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 500)


if __name__ == "__main__":
    unittest.main()
