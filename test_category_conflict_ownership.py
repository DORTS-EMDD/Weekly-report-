import datetime
import unittest

from article_selector import build_selector_api
from config import (
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
    SERVICE_OPENING_CATEGORY_KEY,
)
from report_postprocessor import _formal_category_for_candidate


FIXED_DATE = datetime.date(2026, 8, 24)
ALL_TYPES = [
    "技術新知",
    "重大事故",
    "營運政策",
    "營運爭議",
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
    SERVICE_OPENING_CATEGORY_KEY,
]


def _selector():
    return build_selector_api(
        selected_types=ALL_TYPES,
        active_regions=[],
        lookback_days=14,
        lookback_int=14,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=FIXED_DATE,
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(candidate_id: str, title: str, snippet: str) -> dict:
    url = f"https://example.com/a4/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-20",
        "region": "未判定",
        "query_region": "global",
        "source": "International Metro Review",
        "source_display": "International Metro Review",
        "source_domain": "example.com",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "page_type": "news_article",
        "search_family": "technology",
        "search_query": "fixture category conflict",
        "search_language": "en",
    }


def _evaluate(candidate_id: str, title: str, snippet: str) -> dict:
    api = _selector()
    candidate = _candidate(candidate_id, title, snippet)
    candidate.update(api["evaluate_category_gates"](candidate))
    return candidate


class CategoryConflictOwnershipTests(unittest.TestCase):
    def assert_primary(self, candidate: dict, expected: str) -> None:
        self.assertEqual(candidate["primary_category"], expected, candidate)
        self.assertEqual(candidate["category_resolution_method"], "event_action_object_status")
        self.assertTrue(candidate["category_winning_evidence"])

    def test_a4_t1_jakarta_afc_modernization_contract_is_procurement(self):
        candidate = _evaluate(
            "T1",
            "Jakarta MRT awards AFC modernization contract",
            "Jakarta MRT awarded a contract to modernize its automatic fare collection system, contactless gates and payment equipment.",
        )
        self.assertTrue(candidate["category_gates"][ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY])
        self.assert_primary(candidate, ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL)
        self.assertIn("afc", candidate["procurement_systems"])
        self.assertIn("自動收費", candidate["electromechanical_classification"])
        self.assertIn("afc", candidate["category_winning_evidence"]["event_object"])

    def test_a4_t2_cbtc_system_supply_contract_is_procurement(self):
        candidate = _evaluate(
            "T2",
            "Metro awards CBTC system supply contract",
            "The authority awarded the moving-block CBTC signalling supply and deployment contract to increase line capacity by 20 percent.",
        )
        self.assertTrue(candidate["category_gates"]["technology"])
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assert_primary(candidate, ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL)

    def test_a4_t3_rolling_stock_contract_award_is_procurement(self):
        candidate = _evaluate(
            "T3",
            "Metro awards rolling stock contract",
            "The metro operator awarded a contract for 30 new electric trainsets and onboard control equipment.",
        )
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assert_primary(candidate, ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL)

    def test_a4_t4_new_cbtc_research_pilot_is_technology(self):
        candidate = _evaluate(
            "T4",
            "University and metro launch new CBTC research pilot",
            "Researchers began a pilot demonstration of a new moving-block algorithm on a metro test track, validating a 20 percent capacity improvement.",
        )
        self.assertFalse(candidate["procurement_gate_pass"])
        self.assert_primary(candidate, "技術新知")

    def test_a4_t5_new_material_breakthrough_is_technology(self):
        candidate = _evaluate(
            "T5",
            "New rail material breakthrough demonstrated for metro tracks",
            "Researchers validated a new composite rail material in a metro test environment, reducing wear by 30 percent in trial results.",
        )
        self.assertFalse(candidate["procurement_gate_pass"])
        self.assert_primary(candidate, "技術新知")

    def test_a4_t6_official_opening_is_service_opening(self):
        candidate = _evaluate(
            "T6",
            "New metro line officially opens to passengers",
            "The line opened to passengers and entered revenue service on August 20.",
        )
        self.assertTrue(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assert_primary(candidate, "營運政策")
        self.assertEqual(candidate["operational_subtype"], SERVICE_OPENING_CATEGORY_KEY)

    def test_a4_t7_equipment_contract_for_future_line_is_procurement(self):
        candidate = _evaluate(
            "T7",
            "Metro awards AFC equipment contract for future new line",
            "The authority awarded the automatic fare collection system supply contract for a line scheduled to open next year.",
        )
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assertFalse(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assert_primary(candidate, ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL)

    def test_a4_t8_major_accident_overrides_new_signalling_context(self):
        candidate = _evaluate(
            "T8",
            "Metro collision involving newly installed signalling system",
            "Two trains collided after the newly deployed signalling system failed; 25 passengers were injured, evacuation followed and service was suspended system-wide.",
        )
        self.assertTrue(candidate["category_gates"]["major_accident"])
        self.assert_primary(candidate, "重大事故")

    def test_a4_t9_policy_decision_without_procurement_is_operations(self):
        candidate = _evaluate(
            "T9",
            "Metro board approves fare policy decision",
            "The board approved a fare integration policy that changes ticket prices and system operation from September; no tender or contract was announced.",
        )
        self.assertFalse(candidate["procurement_gate_pass"])
        self.assert_primary(candidate, "營運政策")

    def test_a4_t10_generic_modernization_does_not_force_procurement(self):
        candidate = _evaluate(
            "T10",
            "Metro modernization update announced",
            "The operator discussed modernization of its network and future digital improvements, but announced no tender, award, order or equipment contract.",
        )
        self.assertFalse(candidate["procurement_gate_pass"])
        self.assertNotEqual(candidate["primary_category"], ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL)

    def test_formal_mapper_consumes_primary_owner_before_stale_classification(self):
        candidate = {
            "primary_category": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
            "classification": "技術新知",
            "preliminary_type": "營運政策",
        }
        self.assertEqual(
            _formal_category_for_candidate(candidate),
            ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
        )

    def test_major_accident_overrides_incidental_procurement_history(self):
        candidate = _evaluate(
            "accident-contract",
            "Metro collision involves signalling supplied under modernization contract",
            "Two trains collided after signalling equipment supplied under the awarded modernization contract failed; 25 passengers were injured and the line was evacuated.",
        )
        self.assertTrue(candidate["category_gates"]["major_accident"])
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assert_primary(candidate, "重大事故")
        self.assertIn(
            ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
            candidate["alternative_category_flags"],
        )


if __name__ == "__main__":
    unittest.main()
