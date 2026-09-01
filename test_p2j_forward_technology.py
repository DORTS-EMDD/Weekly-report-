import datetime
import unittest

import article_selector
import ddgs_search_service


def _selector_api():
    return article_selector.build_selector_api(
        selected_types=["技術新知"],
        active_regions=["臺灣"],
        lookback_days=30,
        lookback_int=30,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 11),
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(candidate_id: int, title: str, snippet: str) -> dict:
    url = f"https://railwaygazette.com/news/2026/08/10/p2j-{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-10",
        "region": "臺灣",
        "query_region": "臺灣",
        "source": "Railway Gazette Fixture",
        "source_display": "Railway Gazette Fixture",
        "source_domain": "railwaygazette.com",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "search_family": "forward_technology",
        "search_query": "metro forward technology",
        "search_language": "en",
    }


def _evaluated(api: dict, candidate: dict) -> dict:
    candidate.update(api["evaluate_category_gates"](candidate))
    candidate["classification"] = candidate.get("primary_category", "")
    return candidate


class P2JForwardTechnologyTests(unittest.TestCase):
    def test_forward_queries_are_planned_for_all_report_periods(self):
        for lookback in (7, 30, 365):
            context = ddgs_search_service.DdgsSearchContext(
                selected_types=["技術新知", "重大事故", "營運政策", "營運爭議"],
                active_regions=[],
                lookback_days=lookback,
                lookback_int=lookback,
                is_global_scope=True,
                today=datetime.date(2026, 8, 11),
                ddgs_client_factory=None,
            )
            queries, _ = ddgs_search_service.build_search_queries(
                context=context,
                include_forward_technology=True,
            )
            forward_queries = [
                query for query in queries
                if context.query_metadata[query].get("family") == "forward_technology"
            ]
            self.assertGreater(len(forward_queries), 0, msg=f"lookback={lookback}")
            self.assertEqual(context.forward_technology_query_count, len(forward_queries))

    def test_track_b_ai_predictive_maintenance_passes_without_core_system(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                1,
                "Metro deploys machine learning for predictive maintenance",
                "An urban rail operator deploys machine learning predictive maintenance to monitor equipment conditions and reduce failures.",
            ),
        )
        self.assertEqual(api["_core_systems_for_candidate"](candidate), [])
        self.assertTrue(candidate["track_b_gate_pass"])
        self.assertTrue(candidate["cross_system_emerging_technology_gate"])
        self.assertTrue(candidate["passes_forward_technology_gate"])
        self.assertEqual(candidate["primary_category"], "技術新知")

    def test_track_b_digital_twin_subway_maintenance_passes(self):
        candidate = _evaluated(
            _selector_api(),
            _candidate(
                2,
                "Subway uses a digital twin for maintenance",
                "A subway operator uses a digital twin for maintenance planning and condition monitoring in daily operations.",
            ),
        )
        self.assertTrue(candidate["track_b_gate_pass"])
        self.assertTrue(candidate["passes_forward_technology_gate"])

    def test_track_b_thermal_energy_network_study_passes(self):
        candidate = _evaluated(
            _selector_api(),
            _candidate(
                8,
                "New York to Study Thermal Energy Network for Cooler Subway Platforms",
                "The MTA is studying a thermal energy network for subway platforms to transfer excess heat and reduce platform temperature.",
            ),
        )
        self.assertTrue(candidate["track_b_gate_pass"])
        self.assertTrue(candidate["passes_forward_technology_gate"])

    def test_track_b_cybersecurity_anomaly_detection_passes(self):
        candidate = _evaluated(
            _selector_api(),
            _candidate(
                3,
                "Metro tests cybersecurity anomaly detection on control network",
                "A subway operator tests cybersecurity anomaly detection on its metro control network to identify faults.",
            ),
        )
        self.assertTrue(candidate["track_b_gate_pass"])
        self.assertTrue(candidate["passes_forward_technology_gate"])

    def test_track_b_composite_vehicle_material_passes(self):
        candidate = _evaluated(
            _selector_api(),
            _candidate(
                4,
                "Metro tests lightweight composite vehicle body",
                "A metro operator tests a lightweight composite material for a rail vehicle body, reducing vehicle weight by 12%.",
            ),
        )
        self.assertTrue(candidate["track_b_gate_pass"])
        self.assertTrue(candidate["passes_forward_technology_gate"])

    def test_generic_ai_investment_without_rail_application_fails(self):
        candidate = _evaluated(
            _selector_api(),
            _candidate(
                5,
                "Company announces AI investment strategy",
                "A technology company announces an AI investment strategy for smart cities.",
            ),
        )
        self.assertFalse(candidate["track_b_gate_pass"])
        self.assertFalse(candidate["passes_forward_technology_gate"])

    def test_generic_material_research_is_not_track_b(self):
        candidate = _evaluated(
            _selector_api(),
            _candidate(
                6,
                "Researchers develop composite material for building construction",
                "Researchers test a new composite material for building construction and generic infrastructure.",
            ),
        )
        self.assertFalse(candidate["track_b_gate_pass"])
        self.assertFalse(candidate["passes_forward_technology_gate"])

    def test_core_system_whitelist_is_unchanged_and_track_b_debug_is_exposed(self):
        self.assertEqual(
            article_selector.CORE_SYSTEM_LABELS,
            ("電聯車", "號誌", "供電", "通訊", "自動收費", "機廠維修設備", "月臺門", "垂直運輸設備", "通風空調系統"),
        )
        candidate = _evaluated(
            _selector_api(),
            _candidate(
                7,
                "Metro deploys machine learning for predictive maintenance",
                "An urban rail operator deploys machine learning predictive maintenance to monitor equipment conditions and reduce failures.",
            ),
        )
        annotated = _selector_api()["annotate_candidate_for_scheme_d"](candidate)
        for key in (
            "track_a_gate_pass",
            "track_b_gate_pass",
            "cross_system_emerging_technology_gate",
            "track_b_gate_signals",
            "track_b_failure_reasons",
        ):
            self.assertIn(key, annotated)


if __name__ == "__main__":
    unittest.main()
