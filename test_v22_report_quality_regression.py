import datetime
import unittest
from collections import Counter

from article_processor import _canonical_candidate_region, region_matches_selected_regions
from ddgs_search_service import (
    DdgsSearchContext,
    _annual_quarter_windows,
    _query_with_period,
    build_search_queries,
    run_duckduckgo_searches,
)
from report_postprocessor import (
    deduplicate_report_quality_issues,
    deduplicate_formal_report_sections,
    normalize_source_line,
)
from run_config_service import derive_news_scope
import streamlit_app as app


def _candidate(candidate_id: int, title: str, snippet: str, *, category: str = "技術新知") -> dict:
    url = f"https://example.com/v22-quality/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-01",
        "classification": category,
        "preliminary_type": category,
        "region": "日本",
        "query_region": "日本",
        "source": "Fixture Source",
        "source_display": "Fixture Source",
        "source_domain": "example.com",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
    }


class V22ReportQualityRegressionTests(unittest.TestCase):
    def _reconcile(self, report: str, candidates: list[dict], selected_types: list[str]):
        original = (
            app.selected_types,
            app.standards_enabled,
            app.include_research_supplement,
        )
        try:
            app.selected_types = selected_types
            app.standards_enabled = False
            app.include_research_supplement = False
            return app.reconcile_report_candidate_output(report, candidates)
        finally:
            (
                app.selected_types,
                app.standards_enabled,
                app.include_research_supplement,
            ) = original

    def test_fallback_system_uses_supported_system_or_marks_unknown(self):
        candidate = _candidate(
            1,
            "北捷新列車亮相並規劃投入淡水信義線",
            "台北捷運採購的新電聯車將投入淡水信義線營運。",
            category="機電標案",
        )
        candidate["procurement_systems"] = ["rolling_stock"]

        fallback = app._fallback_report_block(candidate)

        self.assertIn("• 相關機電系統：車輛系統", fallback)
        self.assertNotIn("依原始候選資料所示之都市軌道系統", fallback)
        self.assertEqual(app.normalize_electromechanical_system_value("都市軌道系統"), "未明確")

    def test_fallback_summary_does_not_echo_headline(self):
        title = "北捷新列車亮相！增無線充電功能 最快2027年投入淡水信義線"
        candidate = _candidate(2, title, title, category="機電標案")

        fallback = app._fallback_report_block(candidate)

        self.assertEqual(fallback, "")
        self.assertNotIn(f"事件摘要：\n{title}", fallback)

    def test_generic_insight_fallback_is_omitted(self):
        candidate = _candidate(3, "捷運列車系統更新", "捷運列車完成設備更新。")
        fallback = app._fallback_report_block(candidate)
        report = "\n".join([
            "🔹 [技術新知] 捷運列車系統更新",
            "• 事件摘要：捷運列車完成設備更新。",
            "• 臺北捷運局啟示：後續內容仍應以原始來源核實。",
        ])

        self.assertNotIn("後續內容仍應以原始來源核實", fallback)
        self.assertNotIn("可作為相關設備與系統整合案例之參考", fallback)
        self.assertNotIn("後續內容仍應以原始來源核實", app.normalize_final_report_md(report))

    def test_osaka_metro_ev_bus_is_not_an_urban_rail_candidate(self):
        candidate = _candidate(
            4,
            "EVバス「リスク報告が不十分」 大阪メトロ、万博トラブルで",
            "大阪メトロが運行したEVバスの運行トラブルを報告した。",
        )
        candidate["source"] = "大阪メトロ"

        gates = app.evaluate_category_gates(candidate)

        self.assertFalse(app._selector_api["_candidate_urban_rail_gate"](candidate))
        self.assertFalse(gates["category_gates"]["technology"])

    def test_untranslated_japanese_headline_is_replaced_in_formal_report(self):
        title = "筑豊電鉄が新型車両導入へ 消費電力半分の低床車"
        report = "\n".join([
            f"🔹 [技術新知] {title}",
            "• 發布/事件日期：2026-08-01",
            "• 相關機電系統：車輛系統",
            "• 事件摘要：筑豊電鉄が新型車両を導入する。",
            "• 資料來源：Fixture Source，2026-08-01，https://example.com/article",
        ])

        normalized = app.normalize_final_report_md(report)
        heading = next(line for line in normalized.splitlines() if line.startswith("🔹"))

        self.assertNotIn(title, heading)
        self.assertNotRegex(heading, r"[\u3040-\u30ff\uac00-\ud7af]")
        self.assertRegex(heading, r"[\u3400-\u9fff]{6,}")
        self.assertNotIn("筑豊電鉄が新型車両を導入する", normalized)

    def test_untranslated_english_headline_is_replaced_in_formal_report(self):
        title = "Metro orders new trains for capacity upgrade"

        normalized = app.normalize_final_report_md(f"🔹 [技術新知] {title}")

        self.assertNotIn(title, normalized)
        self.assertRegex(normalized, r"[\u3400-\u9fff]{6,}")

    def test_candidate_id_reconciliation_accepts_pipe_style_category_labels(self):
        candidate = _candidate(10, "捷運完成號誌系統更新", "更新後提升列車調度可靠度。", category="營運政策")
        report = "\n".join([
            "<!-- candidate_id: 10 -->",
            "🔹 營運動態－營運政策｜捷運完成號誌系統更新",
            "• 發布/事件日期：2026-08-01",
            "• 國家/地區：日本",
            "• 相關機電系統：號誌系統",
            "• 事件摘要：該捷運完成號誌系統更新作業，提升列車調度可靠度。",
            "• 臺北捷運局啟示：可作為號誌更新驗證與切換作業規劃參考。",
            "• 資料來源：Fixture Source，2026-08-01，https://example.com/v22-quality/10",
        ])

        output, diagnostics = self._reconcile(report, [candidate], ["營運政策"])

        self.assertIn("<!-- candidate_id: 10 -->", output)
        self.assertIn("🔹 [營運政策]", output)
        self.assertEqual(diagnostics["accepted_model_candidate_ids"], [10])
        self.assertEqual(diagnostics["skipped_candidate_ids"], [])
        self.assertEqual(diagnostics["fallback_block_count"], 0)

    def test_unreconciled_candidate_gets_deterministic_fallback(self):
        candidate = _candidate(11, "捷運車站設備更新", "候選資料不足。")

        output, diagnostics = self._reconcile("", [candidate], ["技術新知"])

        self.assertNotIn("捷運車站設備更新", output)
        self.assertNotIn("資料不足，未能形成可核實的事件摘要。", output)
        self.assertNotIn("依原始候選資料所示之都市軌道系統", output)
        self.assertNotIn("後續內容仍應以原始來源核實", output)
        self.assertEqual(diagnostics["skipped_candidate_ids"], [11])
        self.assertEqual(diagnostics["fallback_candidate_ids"], [])
        self.assertEqual(diagnostics["fallback_block_count"], 0)

    def test_title_copy_summary_is_dropped_instead_of_replaced_with_generic_text(self):
        title = "北捷新列車亮相！增無線充電功能 最快2027年投入淡水信義線"
        candidate = _candidate(14, title, title, category="機電標案")
        report = "\n".join([
            "<!-- candidate_id: 14 -->",
            f"🔹 機電標案｜{title}",
            "• 發布/事件日期：2026-08-01",
            "• 相關機電系統：車輛系統",
            f"• 事件摘要：{title}",
            "• 資料來源：Fixture Source，2026-08-01，https://example.com/v22-quality/14",
        ])

        output, diagnostics = self._reconcile(report, [candidate], ["機電標案"])

        self.assertNotIn(title, output)
        self.assertNotIn("資料不足，未能形成可核實的事件摘要。", output)
        self.assertNotRegex(output, rf"事件摘要：\s*{title}")
        self.assertEqual(diagnostics["skipped_candidate_ids"], [14])
        self.assertEqual(diagnostics["fallback_candidate_ids"], [])

    def test_complete_mta_elevator_block_with_source_variants_is_preserved(self):
        candidate = _candidate(
            4,
            "MTA Announces Two Modernized Elevators Open at Crown Hts-Utica Av Subway Station",
            "MTA opened two modernized elevators at the subway station to improve accessibility.",
            category="機電標案",
        )
        report = "\n".join([
            "<!-- candidate_id: 4 -->",
            "🔹 [機電標案] MTA Crown Hts-Utica Av 站電梯現代化啟用",
            "• 發布/事件日期：2026-08-01",
            "• 國家/地區：美國",
            "• 相關機電系統：電梯、電扶梯",
            "• 事件摘要：",
            "MTA 在 Crown Hts-Utica Av 地鐵站啟用兩部現代化電梯，改善車站無障礙通行。",
            "• 臺北捷運局啟示：可參考車站垂直運輸設備更新與驗證。",
            "• 資料來源：來源名稱：https://example.com/v22-quality/4",
        ])

        output, diagnostics = self._reconcile(report, [candidate], ["機電標案"])

        self.assertIn("Crown Hts-Utica Av", output)
        self.assertEqual(diagnostics["accepted_model_candidate_ids"], [4])
        self.assertEqual(diagnostics["skipped_candidate_ids"], [])
        self.assertEqual(diagnostics["fallback_block_count"], 0)

    def test_complete_mexico_metro_block_with_markdown_source_is_preserved(self):
        candidate = _candidate(
            8,
            "Mexico City Metro Line 3 Modernization",
            "Mexico City Metro is modernizing Line 3 systems and stations.",
            category="技術新知",
        )
        report = "\n".join([
            "<!-- candidate_id: 8 -->",
            "🔹 [技術新知] 墨西哥城地鐵第三線現代化",
            "• 發布/事件日期：2026-07-15",
            "• 國家/地區：墨西哥",
            "• 相關機電系統：號誌系統",
            "• 事件摘要：",
            "墨西哥城地鐵第三線推動系統現代化，內容涉及號誌設備與車站改善。",
            "• 臺北捷運局啟示：可參考分階段系統更新的介面整合與驗證安排。",
            "• 資料來源：**來源名稱：** [官方來源](https://example.com/v22-quality/8)",
        ])

        output, diagnostics = self._reconcile(report, [candidate], ["技術新知"])

        self.assertIn("墨西哥城地鐵第三線現代化", output)
        self.assertEqual(diagnostics["accepted_model_candidate_ids"], [8])
        self.assertEqual(diagnostics["parser_failures"], [])

    def test_normal_model_manchester_title_is_not_replaced_by_generic_title(self):
        title = "Manchester Piccadilly 電車出軌調查終止"
        candidate = _candidate(15, title, "Metrolink tram derailment investigation ended.", category="重大事故")
        report = "\n".join([
            "<!-- candidate_id: 15 -->",
            f"🔹 [重大事故] {title}",
            "• 發布/事件日期：2026-08-01",
            "• 國家/地區：英國",
            "• 相關機電系統：車輛系統",
            "• 事件摘要：Manchester Piccadilly 的 Metrolink 電車出軌調查已終止。",
            "• 資料來源：https://example.com/v22-quality/15",
        ])

        normalized = app.normalize_final_report_md(report)
        repaired = app.repair_generic_report_titles(normalized, [candidate])

        self.assertIn(title, repaired)
        self.assertNotIn("捷運列車更新案", repaired)

    def test_finch_west_ramp_title_is_not_rewritten_as_hitachi(self):
        candidate = _candidate(
            11,
            "Finch West LRT station ramp accessibility request",
            "Advocacy groups request an accessible ramp at Finch West station.",
        )
        report = "<!-- candidate_id: 11 -->\n🔹 [技術新知] 捷運列車更新案"
        repaired = app.repair_generic_report_titles(report, [candidate])

        self.assertNotIn("Hitachi", repaired)
        self.assertNotIn("捷運列車更新案", repaired)
        self.assertIn("Finch West LRT station ramp accessibility request", repaired)

    def test_final_reconciliation_rehomes_model_block_by_selected_category(self):
        candidate = _candidate(
            15,
            "Manchester Piccadilly 電車出軌調查終止",
            "Metrolink tram derailment investigation ended.",
            category="重大事故",
        )
        report = "\n".join([
            "<!-- candidate_id: 15 -->",
            "🔹 [營運動態] Manchester Piccadilly 電車出軌調查終止",
            "• 發布/事件日期：2026-08-01",
            "• 國家/地區：英國",
            "• 相關機電系統：車輛系統",
            "• 事件摘要：Manchester Piccadilly 的 Metrolink 電車出軌調查已終止。",
            "• 資料來源：https://example.com/v22-quality/15",
        ])

        output, diagnostics = self._reconcile(
            report,
            [candidate],
            ["技術新知", "重大事故", "營運政策", "營運爭議", "機電標案"],
        )

        self.assertIn("## 二、重大事故", output)
        self.assertNotIn("## 三、營運動態\n\n<!-- candidate_id: 15 -->", output)
        self.assertEqual(diagnostics["final_candidate_ids"], [15])
        self.assertTrue(diagnostics["final_candidate_id_integrity_passed"])
        self.assertEqual(diagnostics["final_count_by_category"]["重大事故"], 1)

    def test_electromechanical_taxonomy_uses_specific_vertical_transport_labels(self):
        self.assertEqual(
            app.normalize_electromechanical_system_value(
                "",
                "MTA opened two elevators at Crown Hts-Utica Av subway station.",
            ),
            "電梯",
        )
        self.assertEqual(
            app.normalize_electromechanical_system_value(
                "",
                "station elevators and escalators were modernized",
            ),
            "電梯、電扶梯",
        )
        self.assertEqual(
            app.normalize_electromechanical_system_value("車站無障礙設施"),
            "未明確",
        )

    def test_accessibility_ramp_without_equipment_does_not_pass_technical_gate(self):
        candidate = _candidate(
            20,
            "Finch West LRT station ramp accessibility upgrade",
            "Finch West station adds a ramp and slope improvements for accessibility.",
        )
        self.assertFalse(app._selector_api["_passes_technical_triad"](candidate))
        self.assertFalse(app.evaluate_category_gates(candidate)["category_gates"]["technology"])

    def test_accessibility_advocacy_request_is_not_promoted_by_elevator_keyword(self):
        candidate = _candidate(
            21,
            "Finch West LRT station ramp accessibility request",
            "Advocacy groups request an accessible ramp and call for better slope design at Finch West station.",
        )
        self.assertFalse(app._selector_api["_passes_technical_triad"](candidate))
        self.assertFalse(app.evaluate_category_gates(candidate)["category_gates"]["technology"])

    def test_missing_model_candidate_fallback_keeps_its_own_evidence(self):
        candidate = _candidate(
            11,
            "Finch West LRT station ramp accessibility request",
            "倡議團體要求改善 Finch West 車站坡道與無障礙通行，並重新檢視斜坡設計。",
        )
        output, diagnostics = self._reconcile("", [candidate], ["技術新知"])

        self.assertIn("Finch West", output)
        self.assertNotIn("Hitachi", output)
        self.assertEqual(diagnostics["fallback_candidate_ids"], [11])
        self.assertEqual(diagnostics["skipped_candidate_ids"], [])
        self.assertEqual(diagnostics["parser_failures"][0]["candidate_id"], 11)

    def test_taiwan_selected_scope_matches_taipei_and_taoyuan(self):
        self.assertTrue(region_matches_selected_regions("臺北", ["臺灣"]))
        self.assertTrue(region_matches_selected_regions("桃園", ["臺灣"]))
        self.assertFalse(region_matches_selected_regions("印度", ["臺灣"]))

    def test_electromechanical_systems_do_not_use_operational_or_incident_text(self):
        self.assertEqual(
            app.normalize_electromechanical_system_value("電車營運、安全調查"),
            "未明確",
        )
        normalized = app.normalize_electromechanical_system_value("捷運營運、列車測試與驗證")
        self.assertNotIn("列車測試與驗證", normalized)
        self.assertIn(normalized, {"車輛系統", "未明確"})
        self.assertEqual(
            app.normalize_electromechanical_system_value(
                "",
                "Manchester Piccadilly Metrolink tram derailment investigation",
            ),
            "未明確",
        )

    def test_electromechanical_mapping_requires_physical_evidence(self):
        self.assertEqual(
            app.normalize_electromechanical_system_value(
                "",
                "voestalpine new urban track: tram and light rail embedded track system",
            ),
            "軌道系統",
        )
        self.assertEqual(
            app.normalize_electromechanical_system_value(
                "",
                "TTC Long Branch Loop tram track renewal",
            ),
            "軌道系統",
        )
        signalling = app.normalize_electromechanical_system_value(
            "",
            "Washington Metro Red Line train control room flooding and signalling problems",
        )
        self.assertEqual(signalling, "號誌系統")
        self.assertEqual(
            app.normalize_electromechanical_system_value("train and tram operations"),
            "未明確",
        )
        self.assertIn(
            "車輛系統",
            app.normalize_electromechanical_system_value("Brno KT8 battery-powered vehicle"),
        )

    def test_electromechanical_procurement_scope_without_detail_stays_explicitly_unknown(self):
        candidate = _candidate(
            24,
            "桃園捷運棕線機電系統統包工程決標",
            "本案公告完成決標，原始資料未列出各分項設備或系統規格。",
            category="機電標案",
        )
        fallback = app._fallback_report_block(candidate)
        self.assertIn("桃園捷運棕線機電系統統包工程決標", fallback)
        self.assertIn("• 相關機電系統：未明確", fallback)
        self.assertNotRegex(fallback, r"號誌系統|供電系統|通訊系統|自動收費系統")

    def test_source_line_uses_canonical_markdown_link(self):
        source = normalize_source_line(
            "• 資料來源：來源名稱：https://example.com/source，2026-08-01"
        )
        self.assertIn("[來源名稱](https://example.com/source)", source)
        self.assertNotIn("來源名稱：https://example.com/source", source)

    def test_internal_editor_note_is_not_kept_in_formal_report(self):
        report = "## 一、技術新知\n編校說明：此行僅供內部使用。\n🔹 [技術新知] CBTC 更新"
        normalized = app.normalize_final_report_md(report)
        self.assertNotIn("編校說明", normalized)

    def test_candidate_id_integrity_ignores_model_block_order(self):
        first = _candidate(22, "CBTC 號誌更新", "CBTC 號誌更新完成並提升列車控制可靠度。")
        second = _candidate(23, "車站通訊設備升級", "車站通訊設備升級完成並改善資料傳輸可靠度。")
        report = "\n\n".join([
            "\n".join([
                "<!-- candidate_id: 23 -->",
                "🔹 [技術新知] 車站通訊設備升級",
                "• 發布/事件日期：2026-08-01",
                "• 國家/地區：日本",
                "• 相關機電系統：通訊系統",
                "• 事件摘要：更新作業完成並改善車站資料傳輸可靠度。",
                "• 資料來源：Fixture Source，2026-08-01，https://example.com/v22-quality/23",
            ]),
            "\n".join([
                "<!-- candidate_id: 22 -->",
                "🔹 [技術新知] CBTC 號誌更新",
                "• 發布/事件日期：2026-08-01",
                "• 國家/地區：日本",
                "• 相關機電系統：號誌系統",
                "• 事件摘要：號誌更新作業完成並提升列車控制可靠度。",
                "• 資料來源：Fixture Source，2026-08-01，https://example.com/v22-quality/22",
            ]),
        ])
        output, diagnostics = self._reconcile(report, [first, second], ["技術新知"])

        self.assertCountEqual(diagnostics["final_candidate_ids"], [23, 22])
        self.assertTrue(diagnostics["final_candidate_id_integrity_passed"])
        self.assertIn("<!-- candidate_id: 22 -->", output)
        self.assertIn("<!-- candidate_id: 23 -->", output)

    def test_region_content_overrides_query_region_and_records_conflict(self):
        chennai = _candidate(16, "Chennai Metro Rail ropes in consultant", "Chennai Metro Rail appointed a consultant for the system.")
        chennai["region"] = "臺灣"
        chennai["query_region"] = "臺灣"
        self.assertEqual(_canonical_candidate_region(chennai), "印度")
        self.assertTrue(chennai["region_conflict"])
        self.assertEqual(chennai["region_resolution_method"], "title_snippet_explicit_event")

        manchester = _candidate(17, "Manchester Piccadilly tram derailment", "Metrolink tram derailment investigation.")
        manchester["region"] = "澳洲"
        manchester["query_region"] = "澳洲"
        self.assertEqual(_canonical_candidate_region(manchester), "英國")
        self.assertTrue(manchester["region_conflict"])

    def test_thermal_energy_network_study_requires_and_satisfies_technical_triad(self):
        candidate = _candidate(
            18,
            "New York to Study Thermal Energy Network for Cooler Subway Platforms",
            "The MTA and NYC will study a thermal energy network for subway platforms to reduce platform temperature by transferring excess heat.",
        )
        gates = app.evaluate_category_gates(candidate)
        self.assertTrue(app._selector_api["_passes_technical_triad"](candidate))
        self.assertTrue(gates["category_gates"]["technology"])

    def test_maintenance_services_for_tram_rolling_stock_is_procurement_action(self):
        candidate = _candidate(
            19,
            "Maintenance services for Euskotren Tram rolling stock, Spain",
            "Euskotren is procuring a contract for maintenance services for its tram rolling stock.",
            category="機電標案",
        )
        original_types = app.selected_types
        try:
            app.selected_types = ["機電標案"]
            payload = app._selector_api["_compute_electromechanical_procurement_gate"](candidate)
        finally:
            app.selected_types = original_types
        self.assertTrue(payload["procurement_gate_pass"])
        self.assertIn("maintenance_services", payload["procurement_actions"])

    def test_annual_query_plan_contains_each_calendar_quarter(self):
        context = DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=365,
            lookback_int=365,
            is_global_scope=True,
            today=datetime.date(2026, 8, 14),
            ddgs_client_factory=None,
            news_scope="international",
        )
        windows = _annual_quarter_windows(context)
        self.assertEqual([bucket for bucket, _, _ in windows], ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"])
        queries, _ = build_search_queries(context=context)
        bucket_queries = [query for query in queries if "after:" in query and "before:" in query]
        self.assertEqual(len(bucket_queries), len(windows))

    def test_duplicate_event_fingerprint_is_kept_once_in_formal_report(self):
        first = _candidate(12, "捷運月台門完成更新", "捷運月台門更新完成並恢復車站安全隔離功能。")
        second = _candidate(13, "捷運月台門更新完成", "同一事件的轉載，內容仍涉及月台門設備更新。")
        fingerprint = {
            "operator_key": "metro-x",
            "geo_key": "taipei",
            "asset_key": "platform-door",
            "action_key": "upgrade",
            "incident_key": "",
            "date_bucket": "2026-08-01",
        }
        first["event_fingerprint"] = fingerprint
        second["event_fingerprint"] = fingerprint
        report = "\n\n".join([
            "\n".join([
                "<!-- candidate_id: 12 -->",
                "🔹 技術新知｜捷運月台門完成更新",
                "• 發布/事件日期：2026-08-01",
                "• 相關機電系統：月台門系統",
                "• 事件摘要：捷運完成月台門更新。",
                "• 資料來源：Fixture Source，2026-08-01，https://example.com/v22-quality/12",
            ]),
            "\n".join([
                "<!-- candidate_id: 13 -->",
                "🔹 技術新知｜捷運月台門更新完成",
                "• 發布/事件日期：2026-08-01",
                "• 相關機電系統：月台門系統",
                "• 事件摘要：同一事件的轉載。",
                "• 資料來源：Fixture Source，2026-08-01，https://example.com/v22-quality/13",
            ]),
        ])

        output, diagnostics = self._reconcile(report, [first, second], ["技術新知"])

        self.assertIn("<!-- candidate_id: 12 -->", output)
        self.assertNotIn("<!-- candidate_id: 13 -->", output)
        self.assertEqual(diagnostics["deduplicated_event_candidate_ids"], [13])
        self.assertEqual(diagnostics["final_unique_article_count"], 1)

    def test_formal_sections_are_deduplicated_without_losing_other_sections(self):
        report = "\n".join([
            "## 一、技術新知",
            "\n🔹 [技術新知] 第一則",
            "\n## 五、規範更新",
            "\n規範內容保留。",
            "\n## 一、技術新知",
            "\n🔹 [技術新知] 第二則",
        ])

        output = deduplicate_formal_report_sections(report)

        self.assertEqual(output.count("## 一、技術新知"), 1)
        self.assertIn("第一則", output)
        self.assertIn("第二則", output)
        self.assertIn("## 五、規範更新", output)
        self.assertIn("規範內容保留。", output)

    def test_empty_and_research_sections_are_deduplicated(self):
        report = "\n".join([
            "## 二、重大事故",
            "本期未發現符合條件之重大事故案例。",
            "本期未發現符合條件之重大事故案例。",
            "## 四、機電標案",
            "本期未發現符合條件之機電標案。",
            "本期未發現符合條件之機電標案。",
            "## 五、規範更新",
            "同一規範更新內容。",
            "## 五、規範更新",
            "同一規範更新內容。",
            "## 六、國際學術期刊",
            "1、同一研究\n• 資料來源：https://doi.org/10.1234/fixture.1",
            "## 六、國際學術期刊",
            "1、同一研究\n• 資料來源：https://doi.org/10.1234/fixture.1",
        ])

        output = deduplicate_report_quality_issues(report)

        self.assertEqual(output.count("## 二、重大事故"), 1)
        self.assertEqual(output.count("本期未發現符合條件之重大事故案例。"), 1)
        self.assertEqual(output.count("本期未發現符合條件之機電標案。"), 1)
        self.assertEqual(output.count("## 五、規範更新"), 1)
        self.assertEqual(output.count("## 六、國際學術期刊"), 1)

    def test_formal_section_headings_are_canonicalized_once(self):
        report = "\n".join([
            "## 技術新知",
            "🔹 [技術新知] Fixture",
            "## 二、重大事故## 二、重大事故",
            "本期未發現符合條件之重大事故案例。",
        ])

        original_types = app.selected_types
        original_standards = app.standards_enabled
        try:
            app.selected_types = ["技術新知", "重大事故"]
            app.standards_enabled = False
            output = app.normalize_report_section_numbering(report)
        finally:
            app.selected_types = original_types
            app.standards_enabled = original_standards

        self.assertEqual(output.count("## 一、技術新知"), 1)
        self.assertEqual(output.count("## 二、重大事故"), 1)
        self.assertNotIn("重大事故##", output)

    def test_canonical_system_mapping_and_source_link_normalization(self):
        self.assertEqual(
            app.normalize_electromechanical_system_value(
                "都市軌道系統",
                "車站增設電梯與電扶梯，改善無障礙動線。",
            ),
            "電梯、電扶梯",
        )
        self.assertEqual(app.normalize_electromechanical_system_value("都市軌道系統"), "未明確")
        source = normalize_source_line(
            "• 資料來源：Fixture Source，原文連結，原文連結，https://example.com/source"
        )
        self.assertNotIn("原文連結，原文連結", source)

    def test_scope_is_derived_from_taiwan_selection_and_365_queries_are_rolling(self):
        self.assertEqual(derive_news_scope("全球（安全白名單來源）", []), "both")
        self.assertEqual(derive_news_scope("指定先進國家", ["臺灣"]), "domestic")
        self.assertEqual(derive_news_scope("指定先進國家", ["臺灣", "日本"]), "both")
        self.assertEqual(derive_news_scope("指定先進國家", ["日本"]), "international")

        context = DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=365,
            lookback_int=365,
            is_global_scope=True,
            today=datetime.date(2026, 8, 14),
            ddgs_client_factory=None,
            news_scope="international",
        )
        queries, _ = build_search_queries(context=context)
        breakthrough_queries = [
            query for query in queries
            if any(term in query.casefold() for term in ("advanced material", "sic semiconductor", "novel sensor"))
        ]
        self.assertEqual(len(breakthrough_queries), 3)
        self.assertTrue(all(any(term in query.casefold() for term in ("metro", "subway", "mrt", "light rail")) for query in breakthrough_queries))
        self.assertEqual(_query_with_period("metro advanced material", context=context), "metro advanced material")

    def test_annual_regional_plan_covers_selected_families_before_breakthrough_supplement(self):
        context = DdgsSearchContext(
            selected_types=["技術新知", "重大事故", "營運政策", "營運爭議", "機電標案"],
            active_regions=["日本", "德國"],
            lookback_days=365,
            lookback_int=365,
            is_global_scope=False,
            today=datetime.date(2026, 8, 14),
            ddgs_client_factory=None,
            news_scope="international",
        )

        queries, _ = build_search_queries(context=context)
        family_counts = Counter(
            metadata.get("family")
            for metadata in context.query_metadata.values()
        )

        for family in context.planned_required_families:
            self.assertGreaterEqual(family_counts[family], 1, family)
        self.assertLessEqual(context.annual_breakthrough_query_count, 3)
        self.assertEqual(len(queries), len(context.query_metadata))

        _, statuses, summary = run_duckduckgo_searches(
            context=context,
            search_queries=queries,
            news_query_indices=set(),
        )
        self.assertEqual(len(statuses), len(queries))
        self.assertFalse(summary["annual_query_plan_family_coverage"]["warning"])


if __name__ == "__main__":
    unittest.main()
