import datetime
import unittest
from unittest.mock import patch

import article_selector
from article_processor import _canonical_candidate_region
from config import ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL
from diagnostics.p2_k5_12r_global_category import (
    build_major_accident_diagnostic,
    build_operational_diagnostic,
    build_procurement_retrieval_diagnostic,
)


FIXED_DATE = datetime.date(2026, 8, 20)


def _selector(*, lookback_days=7):
    return article_selector.build_selector_api(
        selected_types=[
            "技術新知",
            "重大事故",
            "營運政策",
            "營運爭議",
            ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
        ],
        active_regions=[],
        lookback_days=lookback_days,
        lookback_int=lookback_days,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=FIXED_DATE,
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(
    candidate_id,
    title,
    snippet,
    *,
    source="Railway Gazette",
    country="日本",
    query_region="global",
    search_family="technology",
    source_tier="B_professional",
):
    url = f"https://example.com/news/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "source": source,
        "source_display": source,
        "source_domain": "example.com",
        "source_href": url,
        "url": url,
        "date": "2026-08-18",
        "region": country,
        "country": country,
        "query_region": query_region,
        "search_family": search_family,
        "source_tier": source_tier,
        "source_quality": "B",
        "page_type": "news_article",
    }


class P2K5R2OperationalTests(unittest.TestCase):
    def test_quantified_timetable_change_passes_major_service_adjustment(self):
        candidate = _candidate(
            1,
            "Tokyo Metro timetable change increases frequency",
            "Ginza Line trains run every 3 minutes and Marunouchi Line trains every 4 minutes.",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertTrue(gates["category_gates"]["operational_policy"])
        self.assertEqual(gates["operational_subtype"], "major_service_adjustment")

    def test_japanese_daiya_revision_and_frequency_increase_pass(self):
        candidate = _candidate(
            2,
            "東京メトロ ダイヤ改正 増発",
            "銀座線と丸ノ内線を増発し、運転間隔を短縮する。",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertTrue(gates["major_service_adjustment"])

    def test_routine_weekend_notice_fails(self):
        candidate = _candidate(
            3,
            "Tokyo Metro routine weekend service notice",
            "A routine weekend timetable notice covers scheduled maintenance.",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertFalse(gates["category_gates"]["operational_policy"])

    def test_planned_minor_closure_fails_without_substantial_impact(self):
        candidate = _candidate(
            4,
            "Metro planned minor temporary closure",
            "A planned weekend closure will affect one station for routine maintenance.",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertFalse(gates["category_gates"]["operational_policy"])

    def test_flooded_control_room_with_signalling_impact_passes(self):
        candidate = _candidate(
            5,
            "Metro Red Line returns to normal after water floods control room",
            "Significant delays followed a pipe break that flooded the train control room and impacted signals.",
            country="美國",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertTrue(gates["technical_operation_incident"])
        self.assertTrue(gates["category_gates"]["operational_policy"])

    def test_flooding_without_rail_impact_fails(self):
        candidate = _candidate(
            6,
            "City flooding disrupts roads",
            "Flooding affected roads and buildings; no rail service, signalling or station operations were affected.",
            country="美國",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertFalse(gates["technical_operation_incident"])


class P2K5R2RegionAndProcurementTests(unittest.TestCase):
    def test_event_location_overrides_conflicting_query_region(self):
        candidate = _candidate(
            7,
            "Washington Metro Van Ness station signalling update",
            "WMATA announced a signalling update at Van Ness in Washington, DC.",
            country="英國",
            query_region="英國",
        )
        resolved = _canonical_candidate_region(candidate)
        self.assertEqual(resolved, "美國")
        self.assertTrue(candidate["region_conflict"])

    def test_query_region_is_last_resolution_fallback(self):
        candidate = _candidate(
            8,
            "System maintenance announcement",
            "The operator published a maintenance announcement.",
            country="未判定",
            query_region="日本",
        )
        candidate["region"] = "未判定"
        self.assertEqual(_canonical_candidate_region(candidate), "日本")
        self.assertEqual(candidate["region_resolution_method"], "query_region_fallback")

    def test_civic_metro_ambiguity_is_excluded_from_procurement(self):
        candidate = _candidate(
            9,
            "Metro government awards software contract",
            "The metropolitan government awarded a general civic software contract.",
            country="美國",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertFalse(gates["category_gates"]["electromechanical_procurement"])

    def test_genuine_international_signalling_contract_passes(self):
        candidate = _candidate(
            10,
            "London Underground awards signalling contract",
            "London Underground awarded a CBTC signalling contract for an urban rail line.",
            country="英國",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertTrue(gates["category_gates"]["electromechanical_procurement"])

    def test_military_software_contract_fails(self):
        candidate = _candidate(
            11,
            "Defence ministry awards military software contract",
            "The defence ministry awarded a battlefield software contract.",
            country="美國",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertFalse(gates["category_gates"]["electromechanical_procurement"])

    def test_professional_system_missing_candidate_enters_targeted_rescue(self):
        candidate = _candidate(
            12,
            "Sydney Metro project electrical contract awarded",
            "A professional rail source reports a contract for electrical scope during construction and commissioning.",
            source="Railway Gazette",
            country="澳洲",
        )
        api = _selector()
        self.assertTrue(api["_is_procurement_rescue_candidate"](candidate))

        def fake_prefetch(item, _session):
            item["snippet"] += " The package includes traction power and a substation."
            for key in (
                "_selection_text_cache", "_selection_text_fingerprint",
                "_analysis_cache", "_analysis_cache_fingerprint",
            ):
                item.pop(key, None)
            return {"status": "success", "chars": 180, "reason": "fixture"}

        with patch.object(article_selector, "_prefetch_candidate_article", fake_prefetch):
            stats = api["prefetch_candidates_before_filter"]([candidate])
        self.assertEqual(stats["procurement_rescue_attempted_count"], 1)
        self.assertEqual(stats["procurement_rescue_success_count"], 1)
        gates = api["evaluate_category_gates"](candidate)
        self.assertTrue(gates["category_gates"]["electromechanical_procurement"])
        self.assertIn("traction_power", gates["procurement_systems"])

    def test_vague_electrical_scope_stays_excluded(self):
        candidate = _candidate(
            13,
            "Sydney Metro project electrical contract awarded",
            "The contract covers vague electrical works with no identified rail system.",
            source="Railway Gazette",
            country="澳洲",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertFalse(gates["category_gates"]["electromechanical_procurement"])

    def test_procurement_diagnostic_exposes_global_lane_and_rescue_counts(self):
        candidate = _candidate(
            18,
            "Sydney Metro electrical contract",
            "The professional rail source reports a contract for an urban rail project.",
            country="澳洲",
            search_family="electromechanical_procurement",
        )
        candidate["procurement_urban_rail_context"] = True
        candidate["rescue_type"] = "procurement_rescue_candidate"
        result = build_procurement_retrieval_diagnostic(
            [
                {
                    "search_family": "electromechanical_procurement",
                    "query_region": "global",
                    "added_to_raw_count": 4,
                }
            ],
            [candidate],
            is_global_scope=True,
            prefetch_stats={
                "procurement_rescue_attempted_count": 1,
                "procurement_rescue_success_count": 1,
            },
        )
        self.assertEqual(result["international_procurement_raw_count"], 4)
        self.assertEqual(result["international_procurement_urban_rail_count"], 1)
        self.assertEqual(result["international_procurement_near_miss_count"], 1)
        self.assertEqual(result["international_procurement_enrichment_attempted"], 1)
        self.assertEqual(result["international_procurement_enrichment_success"], 1)


class P2K5R2DiagnosticTests(unittest.TestCase):
    def test_major_accident_diagnostic_uses_accident_provenance_not_only_family(self):
        api = _selector()
        candidate = _candidate(
            14,
            "Seoul Metro collision injures 25 and suspends Line 2",
            "Two metro trains collided, 25 passengers were injured and service was suspended.",
            country="韓國",
            search_family="technology",
        )
        candidate["annual_bucket_families"] = ["technology", "major_accident"]
        candidate.update(api["evaluate_category_gates"](candidate))
        report = build_major_accident_diagnostic([candidate])
        self.assertEqual(report["raw_count"], 1)
        self.assertEqual(report["major_accident_gate_pass_count"], 1)
        self.assertEqual(report["true_major_candidate_count"], 1)

    def test_major_accident_threshold_remains_strict(self):
        candidate = _candidate(
            15,
            "Light rail vehicle has minor road collision with no derailment",
            "A minor road interface collision caused a short delay and no injuries.",
            country="澳洲",
        )
        self.assertFalse(_selector()["_passes_major_accident_gate"](candidate))

    def test_operational_diagnostic_counts_major_adjustment(self):
        api = _selector()
        candidate = _candidate(
            16,
            "Tokyo Metro timetable change increases frequency",
            "Ginza Line trains run every 3 minutes and Marunouchi Line trains every 4 minutes.",
        )
        candidate["annual_bucket_families"] = ["technology", "policy"]
        candidate.update(api["evaluate_category_gates"](candidate))
        report = build_operational_diagnostic([candidate])
        self.assertEqual(report["raw_count"], 1)
        self.assertEqual(report["major_service_adjustment_gate_pass_count"], 1)
        self.assertEqual(report["japan_operational_gate_pass_count"], 1)

    def test_academic_simulation_remains_excluded(self):
        candidate = _candidate(
            17,
            "Accident simulation study for metro train collision risk",
            "An academic paper presents a simulated collision scenario and risk model.",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertFalse(gates["category_gates"]["major_accident"])

    def test_missing_accident_metadata_is_not_affirmative_event_evidence(self):
        candidate = _candidate(
            19,
            "Metro evacuation research evidence review",
            "Missing: tram collision. Fire hazards and evacuation assessment are discussed.",
        )
        self.assertFalse(_selector()["_passes_major_accident_gate"](candidate))

    def test_evacuation_fire_hazard_research_is_not_major_accident(self):
        candidate = _candidate(
            20,
            "Metro evacuation and fire hazard assessment",
            "A research study evaluates evacuation methodology for hypothetical tram collision scenarios.",
        )
        self.assertFalse(_selector()["_passes_major_accident_gate"](candidate))

    def test_genuine_tram_collision_still_passes(self):
        candidate = _candidate(
            21,
            "Tram collision injures passengers",
            "Two urban rail trams collided and passengers were injured.",
        )
        self.assertTrue(_selector()["_passes_major_accident_gate"](candidate))

    def test_genuine_metro_fire_with_injuries_still_passes(self):
        candidate = _candidate(
            22,
            "Metro train fire injures passengers",
            "A train fire broke out and eight passengers were injured during evacuation.",
        )
        self.assertTrue(_selector()["_passes_major_accident_gate"](candidate))

    def test_genuine_derailment_still_passes(self):
        candidate = _candidate(
            23,
            "Metro train derailment evacuates passengers",
            "A metro train derailed in the station and passengers were evacuated.",
        )
        self.assertTrue(_selector()["_passes_major_accident_gate"](candidate))

    def test_genuine_incident_evacuation_still_passes(self):
        candidate = _candidate(
            24,
            "Metro incident causes emergency evacuation",
            "A train fire broke out and the station was evacuated after the incident.",
        )
        self.assertTrue(_selector()["_passes_major_accident_gate"](candidate))


if __name__ == "__main__":
    unittest.main()
