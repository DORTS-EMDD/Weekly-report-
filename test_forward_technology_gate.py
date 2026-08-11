import datetime
import unittest

from article_selector import build_selector_api
from developer_debug_service import _debug_candidate_rows


def _selector_api():
    return build_selector_api(
        selected_types=["技術新知"],
        active_regions=["美國"],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 11),
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(candidate_id: int, title: str, snippet: str, *, family: str = "forward_technology") -> dict:
    url = f"https://railwaygazette.com/news/2026/08/10/forward-case-{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-10",
        "region": "美國",
        "query_region": "美國",
        "source": "Railway Gazette Fixture",
        "source_display": "Railway Gazette Fixture",
        "source_domain": "railwaygazette.com",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "search_family": family,
        "search_query": "metro forward technology",
        "search_language": "en",
    }


def _evaluated(api: dict, candidate: dict) -> dict:
    candidate.update(api["evaluate_category_gates"](candidate))
    candidate["classification"] = candidate.get("primary_category", "")
    return candidate


class ForwardTechnologyGateTests(unittest.TestCase):
    def test_unknown_lightweight_material_case_passes_forward_gate(self):
        api = _selector_api()
        candidate = _candidate(
            1,
            "Metro operator pilots newly developed lightweight material on rail vehicles",
            "A metro operator pilots a newly developed lightweight material on rail vehicles, reducing vehicle weight and traction energy consumption.",
        )
        kept, reason = api["preliminary_filter_candidate"](candidate)
        self.assertTrue(kept, reason)
        candidate = _evaluated(api, candidate)

        self.assertTrue(candidate["passes_forward_technology_gate"])
        self.assertTrue(candidate["category_gates"]["forward_technology"])
        self.assertTrue(candidate["category_gates"]["technology"])
        self.assertEqual(candidate["primary_category"], "技術新知")
        self.assertTrue(api["_is_technical_news_selection_candidate"](candidate))

    def test_low_friction_coating_case_passes_forward_gate(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                2,
                "Subway operator field-tests new low-friction coating on rail components",
                "A subway operator field-tests a new low-friction coating on rail components, reducing wear and extending service life.",
            ),
        )

        self.assertTrue(candidate["passes_forward_technology_gate"])

    def test_new_sensing_method_case_passes_forward_gate(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                3,
                "Urban metro validates new sensing method for tunnel equipment",
                "An urban metro validates a new sensing method for tunnel equipment, reducing manual inspection time.",
            ),
        )

        self.assertTrue(candidate["passes_forward_technology_gate"])

    def test_marketing_only_case_fails_forward_gate(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                4,
                "Innovative green smart metro technology announced",
                "An operator announced an innovative green smart metro technology.",
            ),
        )

        self.assertFalse(candidate["passes_forward_technology_gate"])
        self.assertEqual(candidate["primary_category"], "excluded")
        self.assertTrue(candidate["forward_gate_failure_reasons"])

    def test_non_urban_material_case_fails_forward_gate(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                5,
                "Aircraft maker pilots newly developed lightweight material",
                "An aircraft maker pilots a newly developed lightweight material, reducing aircraft weight and energy consumption.",
            ),
        )

        self.assertFalse(candidate["passes_forward_technology_gate"])
        self.assertFalse(candidate["category_gates"]["technology"])

    def test_proposal_and_feasibility_cases_fail_forward_gate(self):
        api = _selector_api()
        cases = (
            (
                "Researchers propose new coating to reduce railway wear",
                "Researchers propose a new coating that may reduce railway wear.",
            ),
            (
                "Metro plans to study innovative materials for future trains",
                "A metro operator plans to study innovative materials for future trains.",
            ),
        )

        for index, (title, snippet) in enumerate(cases, 6):
            candidate = _evaluated(api, _candidate(index, title, snippet))
            self.assertFalse(candidate["passes_forward_technology_gate"], msg=title)

    def test_missing_benefit_or_novelty_cases_fail_forward_gate(self):
        api = _selector_api()
        cases = (
            (
                "New material deployed on metro trains",
                "New material deployed on metro trains.",
            ),
            (
                "Metro reduces energy use by 20%",
                "Metro reduces energy use by 20%.",
            ),
        )

        for index, (title, snippet) in enumerate(cases, 8):
            candidate = _evaluated(api, _candidate(index, title, snippet))
            self.assertFalse(candidate["passes_forward_technology_gate"], msg=title)

    def test_technology_family_cannot_use_forward_alternate_gate(self):
        api = _selector_api()
        candidate = _candidate(
            10,
            "Metro operator pilots newly developed material on bogies",
            "A metro operator pilots a newly developed lightweight material on bogies, reducing mass and traction energy consumption.",
            family="technology",
        )
        candidate = _evaluated(api, candidate)

        self.assertFalse(api["_passes_technical_triad"](candidate))
        self.assertFalse(api["_passes_forward_technology_gate"](candidate))
        self.assertFalse(candidate["category_gates"]["technology"])
        self.assertEqual(candidate["primary_category"], "excluded")

    def test_forward_gate_metadata_is_available_in_existing_debug_shapes(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                11,
                "Urban metro validates new sensing method for tunnel equipment",
                "An urban metro validates a new sensing method for tunnel equipment, reducing manual inspection time.",
            ),
        )
        annotated = api["annotate_candidate_for_scheme_d"](candidate)
        card = api["build_candidate_card"](annotated)
        debug_row = _debug_candidate_rows([annotated])[0]

        for row in (annotated, card, debug_row):
            self.assertTrue(row["passes_forward_technology_gate"])
            self.assertTrue(row["forward_gate_signals"]["benefit"])
            self.assertEqual(row["forward_gate_failure_reasons"], [])


if __name__ == "__main__":
    unittest.main()
