import datetime
import unittest

from ddgs_search_service import DdgsSearchContext, _query_with_period, build_search_queries
from report_postprocessor import (
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

        self.assertIn("資料不足，未能形成可核實的事件摘要。", fallback)
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

    def test_unreconciled_candidate_is_dropped_without_generic_formal_fallback(self):
        candidate = _candidate(11, "捷運車站設備更新", "候選資料不足。")

        output, diagnostics = self._reconcile("", [candidate], ["技術新知"])

        self.assertNotIn("捷運車站設備更新", output)
        self.assertNotIn("依原始候選資料所示之都市軌道系統", output)
        self.assertNotIn("後續內容仍應以原始來源核實", output)
        self.assertEqual(diagnostics["skipped_candidate_ids"], [11])
        self.assertEqual(diagnostics["fallback_candidate_ids"], [])

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
        self.assertEqual(diagnostics["skipped_candidate_ids"], [14])

    def test_duplicate_event_fingerprint_is_kept_once_in_formal_report(self):
        first = _candidate(12, "捷運月台門完成更新", "月台門更新完成。")
        second = _candidate(13, "捷運月台門更新完成", "同一事件的轉載。")
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


if __name__ == "__main__":
    unittest.main()
