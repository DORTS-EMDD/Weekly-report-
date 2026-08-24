import datetime
import unittest

from article_selector import build_selector_api
from electromechanical_taxonomy import classify_electromechanical_evidence
from report_postprocessor import (
    ReportPostprocessContext,
    _fallback_electromechanical_system,
    _force_candidate_fields_in_block,
    normalize_electromechanical_system_value,
)


def _selector() -> dict:
    return build_selector_api(
        selected_types=["技術新知", "機電標案"],
        active_regions=[],
        lookback_days=30,
        lookback_int=30,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 24),
        news_scope="domestic",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "zh",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(candidate_id: int, title: str, snippet: str) -> dict:
    url = f"https://example.com/a3/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "raw_title": title,
        "title": title,
        "raw_snippet": snippet,
        "snippet": snippet,
        "date": "2026-08-20",
        "region": "桃園",
        "source": "Fixture Metro News",
        "source_domain": "example.com",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "page_type": "news_article",
        "query": "metro technology",
    }


class ElectromechanicalTaxonomyOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = _selector()

    def _systems(self, candidate_id: int, title: str, snippet: str) -> tuple[list[str], dict]:
        candidate = _candidate(candidate_id, title, snippet)
        systems = self.api["_core_systems_for_candidate"](candidate)
        candidate["core_systems"] = list(systems)
        return systems, candidate

    def test_a3_t1_taoyuan_driverless_test_rejects_depot_location(self):
        systems, candidate = self._systems(
            1,
            "桃園捷運綠線全自動無人駕駛測試",
            "列車於G11站至北機廠辦理全自動無人駕駛測試。",
        )
        self.assertEqual(systems, ["號誌"])
        self.assertNotIn("機廠維修設備", systems)
        gate_payload = self.api["evaluate_category_gates"](candidate)
        self.assertTrue(gate_payload["category_gates"]["technology"])
        self.assertEqual(gate_payload["primary_category"], "技術新知")
        self.assertTrue(any(
            item["system"] == "號誌" and "無人駕駛" in item["evidence"]
            for item in candidate["electromechanical_winning_evidence"]
        ))
        self.assertTrue(any(
            item["system"] == "機廠維修設備"
            and item["reason"] == "location_only_evidence"
            for item in candidate["electromechanical_rejected_evidence"]
        ))
        self.assertEqual(
            normalize_electromechanical_system_value("", f"{candidate['title']} {candidate['snippet']}"),
            "號誌系統",
        )

    def test_a3_t2_goa4_at_depot_is_signalling(self):
        systems, _ = self._systems(
            2,
            "GoA4 unattended train operation at depot",
            "The metro tests unattended operation at its maintenance depot.",
        )
        self.assertEqual(systems, ["號誌"])

    def test_a3_t3_underfloor_wheel_lathe_is_depot_equipment(self):
        systems, _ = self._systems(
            3,
            "Underfloor wheel lathe installed at depot",
            "The metro installed an underfloor wheel lathe in its workshop.",
        )
        self.assertEqual(systems, ["機廠維修設備"])

    def test_a3_t4_real_workshop_equipment_is_depot_equipment(self):
        fixtures = (
            "train washing system installed at depot",
            "lifting equipment commissioned in the workshop",
            "workshop maintenance equipment contract",
        )
        for index, text in enumerate(fixtures, 4):
            with self.subTest(text=text):
                systems, _ = self._systems(index, text, f"Metro {text}.")
                self.assertEqual(systems, ["機廠維修設備"])

    def test_a3_t5_thermal_energy_network_is_not_communications(self):
        systems, candidate = self._systems(
            7,
            "MTA thermal energy network study",
            "The subway heat network transfers excess heat from platforms.",
        )
        self.assertNotIn("通訊", systems)
        self.assertTrue(any(
            item["reason"] == "network_without_communications_context"
            for item in candidate["electromechanical_rejected_evidence"]
        ))
        self.assertEqual(
            normalize_electromechanical_system_value("", f"{candidate['title']} {candidate['snippet']}"),
            "未明確",
        )

    def test_a3_t6_explicit_communications_context_is_communications(self):
        for index, text in enumerate((
            "fiber communications network deployment",
            "radio network and TETRA upgrade",
        ), 8):
            with self.subTest(text=text):
                systems, _ = self._systems(index, text, f"Metro deploys {text}.")
                self.assertEqual(systems, ["通訊"])

    def test_a3_t7_jakarta_afc_guard(self):
        systems, candidate = self._systems(
            10,
            "Jakarta MRT AFC modernization contract",
            "The Automatic Fare Collection upgrade includes fare gates, smart cards and contactless payment.",
        )
        self.assertEqual(systems, ["自動收費"])
        self.assertEqual(_fallback_electromechanical_system(candidate), "自動收費系統 AFC")

    def test_a3_t8_generic_automatic_test_at_depot_remains_unknown(self):
        systems, candidate = self._systems(
            11,
            "Automatic test at depot",
            "The metro conducts an automatic test at the depot.",
        )
        self.assertEqual(systems, [])
        self.assertEqual(candidate["electromechanical_classification_reason"], "insufficient_electromechanical_evidence")
        self.assertNotIn("號誌", systems)
        self.assertNotIn("機廠維修設備", systems)

    def test_a3_t9_english_train_control_family_is_signalling(self):
        fixtures = (
            "CBTC and ATO commissioning",
            "Automatic Train Protection and Automatic Train Supervision upgrade",
            "UTO driverless operation trial",
            "autonomous train control deployment",
        )
        for index, text in enumerate(fixtures, 12):
            with self.subTest(text=text):
                systems, _ = self._systems(index, text, f"Metro {text}.")
                self.assertIn("號誌", systems)

    def test_a3_t10_chinese_train_control_family_is_signalling(self):
        fixtures = ("無人駕駛", "無人運轉", "全自動列車運轉", "自動列車運轉", "列車控制")
        for index, term in enumerate(fixtures, 16):
            with self.subTest(term=term):
                systems, _ = self._systems(index, f"捷運{term}測試", f"列車辦理{term}驗證。")
                self.assertEqual(systems, ["號誌"])

    def test_formal_candidate_classification_overrides_model_keyword_drift(self):
        candidate = _candidate(
            22,
            "桃園捷運綠線全自動無人駕駛測試",
            "列車於北機廠辦理測試。",
        )
        candidate["classification"] = "技術新知"
        candidate["core_systems"] = ["號誌"]
        context = ReportPostprocessContext(
            selected_types=["技術新知"],
            standards_enabled=False,
            include_research_supplement=False,
            lookback_int=30,
            today=datetime.date(2026, 8, 24),
            date_range="2026-07-26 至 2026-08-24",
            report_title="Fixture",
            report_scope_label="國內",
            candidate_selection_text=lambda item: f"{item.get('title', '')} {item.get('snippet', '')}",
            infer_preliminary_type=lambda _item: "技術新知",
            is_urban_rail_candidate=lambda _text: True,
            research_section_heading=lambda _enabled: "",
            id_validation_target={},
        )
        block = "\n".join((
            "🔹 [技術新知] 桃園捷運綠線測試",
            "• 發布/事件日期：2026-08-20",
            "• 國家/地區：臺灣",
            "• 相關機電系統：機廠設備",
            "• 事件摘要：桃園捷運綠線辦理無人駕駛測試。",
            "• 資料來源：Fixture Metro News，https://example.com/a3/22",
        ))
        output = _force_candidate_fields_in_block(block, candidate, context=context)
        self.assertIn("• 相關機電系統：號誌系統", output)
        self.assertNotIn("• 相關機電系統：機廠設備", output)

    def test_diagnostics_are_bounded_and_unknown_is_not_forced(self):
        payload = classify_electromechanical_evidence({
            "title": "Automatic test at depot workshop maintenance depot heat network",
            "snippet": "A generic network test at the depot without equipment detail.",
        })
        self.assertEqual(payload["systems"], [])
        self.assertLessEqual(len(payload["winning_evidence"]), 16)
        self.assertLessEqual(len(payload["rejected_evidence"]), 12)


if __name__ == "__main__":
    unittest.main()
