import unittest

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


if __name__ == "__main__":
    unittest.main()
