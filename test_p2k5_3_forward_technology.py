import datetime
import unittest
from unittest.mock import patch

import article_selector
import ddgs_search_service
import streamlit_app


def _selector(lookback=365):
    return article_selector.build_selector_api(
        selected_types=["技術新知"],
        active_regions=[],
        lookback_days=lookback,
        lookback_int=lookback,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 18),
        news_scope="both",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(candidate_id, title, snippet, date_value="2026-08-10"):
    url = f"https://fixture.example.test/forward/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": date_value,
        "region": "英國",
        "query_region": "全球",
        "source": "Fixture Rail Technology",
        "source_display": "Fixture Rail Technology",
        "source_domain": "fixture.example.test",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "search_family": "forward_technology",
        "search_query": "metro forward technology",
        "search_language": "en",
        "python_score": 90,
        "final_selection_score": 90,
        "candidate_flags": ["technical_or_system_detail"],
    }


def _evaluated(api, candidate):
    candidate.update(api["evaluate_category_gates"](candidate))
    candidate["classification"] = candidate.get("primary_category", "")
    return candidate


class P2K53ForwardTechnologyTests(unittest.TestCase):
    def test_high_value_forward_fixtures_pass(self):
        api = _selector()
        fixtures = [
            _candidate(
                1,
                "Metro validates lightweight CFRP composite vehicle body",
                "An urban rail operator validates a lightweight CFRP composite vehicle body prototype, reducing vehicle weight by 12%.",
            ),
            _candidate(
                2,
                "Metro deploys AI predictive maintenance for rolling stock",
                "A subway operator deploys machine learning predictive maintenance to monitor rolling stock condition and reduce failures.",
            ),
            _candidate(
                3,
                "Subway deploys digital twin for maintenance",
                "An urban rail operator deploys a digital twin for maintenance planning and condition monitoring in operations.",
            ),
            _candidate(
                4,
                "Urban rail engineering study evaluates flywheel energy storage",
                "An urban rail system evaluates flywheel energy storage in an engineering study to reduce traction energy consumption.",
            ),
            _candidate(
                5,
                "Metro field validates virtual coupling and advanced train control",
                "A metro operator field validates virtual coupling and advanced train control to increase capacity.",
            ),
        ]
        for candidate in fixtures:
            with self.subTest(candidate=candidate["id"]):
                evaluated = _evaluated(api, candidate)
                self.assertTrue(evaluated["passes_forward_technology_gate"])
                self.assertEqual(evaluated["primary_category"], "技術新知")

    def test_generic_forward_candidates_fail(self):
        api = _selector()
        fixtures = [
            _candidate(
                6,
                "Company announces AI investment strategy",
                "A technology company announces an AI platform investment strategy for smart cities without an urban rail application.",
            ),
            _candidate(
                7,
                "Researchers develop composite material for building construction",
                "Researchers test a composite material for building construction and generic infrastructure.",
            ),
            _candidate(
                8,
                "Metro Line project approved",
                "The metro project was approved and construction planning will proceed.",
            ),
        ]
        for candidate in fixtures:
            with self.subTest(candidate=candidate["id"]):
                evaluated = _evaluated(api, candidate)
                self.assertFalse(evaluated["passes_forward_technology_gate"])

    def test_material_detector_requires_forward_family_and_urban_rail(self):
        api = _selector()
        rail_material = _candidate(
            9,
            "Metro tests advanced composite vehicle body",
            "An urban rail operator tests an advanced composite vehicle body.",
        )
        generic_material = _candidate(
            10,
            "Researchers test advanced composite building material",
            "Researchers test an advanced composite material for building construction.",
        )
        self.assertTrue(api["_is_forward_material_candidate"](rail_material))
        self.assertFalse(api["_is_forward_material_candidate"](generic_material))

    def test_annual_forward_pool_has_gate_pass_and_selection(self):
        api = _selector(365)
        dates = ("2025-09-10", "2025-12-10", "2026-03-10", "2026-06-10", "2026-08-10")
        candidates = []
        for index, date_value in enumerate(dates, 1):
            candidate = _candidate(
                20 + index,
                f"Metro forward technology fixture {index}",
                "An urban rail operator deploys a digital twin for maintenance condition monitoring and improves reliability.",
                date_value,
            )
            candidates.append(_evaluated(api, candidate))
        selected = api["select_candidates_by_python"](candidates)
        self.assertGreater(article_selector.LAST_PYTHON_SELECTION_DEBUG["track_b_gate_pass_count"], 0)
        self.assertGreater(len(selected), 0)
        debug = streamlit_app.build_pipeline_debug_stats(
            candidates,
            candidates,
            candidates,
            [],
            {},
        )
        self.assertGreater(debug["forward_technology_raw_count"], 0)
        self.assertGreater(debug["forward_technology_gate_pass_count"], 0)
        self.assertTrue(debug["forward_gate_pass_ids"])
        self.assertIn("forward_selected_ids", debug)
        self.assertTrue(article_selector.LAST_PYTHON_SELECTION_DEBUG["forward_selected_ids"])

    def test_seven_day_forward_fixture_is_not_excluded(self):
        api = _selector(7)
        candidate = _evaluated(
            api,
            _candidate(
                30,
                "Metro deploys sensor-based automated inspection",
                "A subway operator deploys sensors for automated inspection to reduce inspection time.",
                "2026-08-15",
            ),
        )
        selected = api["select_candidates_by_python"]([candidate])
        self.assertEqual(len(selected), 1)

    def test_nonzero_irrelevant_primary_results_trigger_forward_rescue(self):
        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=7,
            lookback_int=7,
            is_global_scope=True,
            today=datetime.date(2026, 8, 18),
            ddgs_client_factory=object(),
            query_metadata={
                "metro forward": {
                    "family": "forward_technology",
                    "lang": "en",
                    "planned_index": 1,
                }
            },
            sleep=lambda _seconds: None,
            random_uniform=lambda _low, _high: 0,
        )

        def fake_execute(_factory, query, **_kwargs):
            if query == "metro forward":
                return [{
                    "title": "Metro policy announcement",
                    "body": "A city policy announcement concerns fares and service administration.",
                    "href": "https://fixture.example.test/policy",
                    "date": "2026-08-17",
                }]
            return [{
                "title": "Subway deploys predictive maintenance",
                "body": "A subway operator deploys predictive maintenance to monitor equipment and reduce failures.",
                "href": "https://fixture.example.test/forward-rescue",
                "date": "2026-08-17",
            }]

        with patch.object(ddgs_search_service, "service_execute_ddgs_query", side_effect=fake_execute):
            _, statuses, summary = ddgs_search_service.run_duckduckgo_searches(
                context=context,
                search_queries=["metro forward"],
                news_query_indices={1},
            )
        self.assertEqual(summary["forward_technology_primary_raw_count"], 1)
        self.assertEqual(summary["forward_technology_fallback_query_count"], 5)
        self.assertEqual(summary["forward_technology_fallback_raw_count"], 5)
        self.assertTrue(any(row.get("fallback_layer") for row in statuses))


if __name__ == "__main__":
    unittest.main()
