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
    url = f"https://railwaygazette.com/news/2026/08/10/watchlist-case-{candidate_id}"
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


class ForwardTechnologyWatchlistTests(unittest.TestCase):
    def test_strict_unknown_technology_is_report_eligible(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                1,
                "Metro pilots newly developed lightweight material on rail vehicles",
                "A metro operator pilots a newly developed lightweight material on rail vehicles, reducing vehicle weight by 12% and traction energy consumption by 8%.",
            ),
        )

        self.assertTrue(candidate["passes_forward_technology_gate"])
        self.assertTrue(candidate["radar_watchlist_pass"])
        self.assertEqual(candidate["forward_status"], "report_eligible")

    def test_delhi_monitoring_is_watchlist_only(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                2,
                "Delhi Metro Rail deploys AI-based infrastructure monitoring",
                "Delhi Metro Rail deploys AI-based infrastructure monitoring to identify equipment conditions during operations.",
            ),
        )

        self.assertFalse(candidate["passes_forward_technology_gate"])
        self.assertTrue(candidate["radar_watchlist_pass"])
        self.assertEqual(candidate["forward_status"], "radar_watchlist")
        self.assertTrue(candidate["radar_watchlist_signals"]["project_only_clear"])

    def test_delhi_fault_detection_is_watchlist_only(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                3,
                "Delhi Metro Rail deploys AI fault detection",
                "Delhi Metro Rail deploys AI fault detection to identify equipment faults earlier.",
            ),
        )

        self.assertFalse(candidate["passes_forward_technology_gate"])
        self.assertTrue(candidate["radar_watchlist_pass"])
        self.assertEqual(candidate["forward_status"], "radar_watchlist")

    def test_negative_cases_are_rejected_by_both_layers(self):
        api = _selector_api()
        cases = (
            ("Innovative green smart metro project announced.", "An innovative green smart metro project was announced."),
            ("Metro orders 20 new trains.", "Metro orders 20 new trains."),
            ("Feasibility study launched for future smart station.", "A feasibility study was launched for a future smart station."),
            ("Metro achieves 99.95% punctuality.", "Metro achieves 99.95% punctuality."),
            ("Company wins signalling contract.", "A company wins a signalling contract for Metro Line X."),
            ("Aviation company tests novel lightweight material.", "An aviation company tests a novel lightweight material."),
        )

        for index, (title, snippet) in enumerate(cases, 10):
            candidate = _evaluated(api, _candidate(index, title, snippet))
            self.assertFalse(candidate["passes_forward_technology_gate"], msg=title)
            self.assertFalse(candidate["radar_watchlist_pass"], msg=title)
            self.assertEqual(candidate["forward_status"], "rejected", msg=title)

    def test_technology_family_cannot_use_watchlist_bypass(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                20,
                "Delhi Metro Rail deploys AI-based infrastructure monitoring",
                "Delhi Metro Rail deploys AI-based infrastructure monitoring to identify equipment conditions during operations.",
                family="technology",
            ),
        )

        self.assertFalse(api["_passes_forward_technology_gate"](candidate))
        self.assertFalse(api["_passes_forward_technology_watchlist"](candidate))
        self.assertEqual(api["_compute_forward_candidate_status"](candidate), {})

    def test_watchlist_candidate_is_not_formally_selected(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                21,
                "Delhi Metro Rail deploys CBTC equipment monitoring",
                "Delhi Metro Rail deploys CBTC equipment monitoring and fault detection during operations.",
            ),
        )
        annotated = api["annotate_candidate_for_scheme_d"](candidate)

        self.assertTrue(annotated["radar_watchlist_pass"])
        self.assertEqual(annotated["forward_status"], "radar_watchlist")
        self.assertFalse(api["_is_technical_news_selection_candidate"](annotated))
        self.assertEqual(api["select_candidates_by_python"]([annotated]), [])

    def test_watchlist_metadata_is_available_in_card_and_debug(self):
        api = _selector_api()
        candidate = _evaluated(
            api,
            _candidate(
                22,
                "Delhi Metro Rail deploys AI fault detection",
                "Delhi Metro Rail deploys AI fault detection to identify equipment faults earlier.",
            ),
        )
        annotated = api["annotate_candidate_for_scheme_d"](candidate)
        card = api["build_candidate_card"](annotated)
        debug_row = _debug_candidate_rows([annotated])[0]

        for row in (annotated, card, debug_row):
            self.assertEqual(row["forward_status"], "radar_watchlist")
            self.assertTrue(row["radar_watchlist_pass"])
            self.assertTrue(row["radar_watchlist_signals"]["technical_method"])
            self.assertEqual(row["radar_watchlist_failure_reasons"], [])


if __name__ == "__main__":
    unittest.main()
