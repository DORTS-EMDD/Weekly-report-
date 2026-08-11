import datetime
import unittest

from article_processor import _canonical_candidate_region
from article_selector import build_selector_api


FIXED_DATE = datetime.date(2026, 8, 11)


def _selector_api():
    return build_selector_api(
        selected_types=["營運政策", "重大事故"],
        active_regions=["新加坡", "美國"],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=FIXED_DATE,
        _search_family_from_query=lambda _query: "policy",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(candidate_id: int, title: str, snippet: str) -> dict:
    url = f"https://railwaygazette.com/fixture/historical-{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-10",
        "region": "未判定",
        "query_region": "",
        "source": "Railway Gazette Fixture",
        "source_display": "Railway Gazette Fixture",
        "source_domain": "railwaygazette.com",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "search_family": "policy",
        "search_query": "metro safety policy",
        "search_language": "en",
    }


def _evaluated(candidate: dict) -> dict:
    api = _selector_api()
    candidate.update(api["evaluate_category_gates"](candidate))
    return candidate


class HistoricalReportRegressionTests(unittest.TestCase):
    def test_singapore_lta_safety_policy_is_not_major_accident(self):
        candidate = _evaluated(_candidate(
            1,
            "Singapore LTA announces LRT safety measures",
            "LTA implements safety measures and a service restructuring policy for Singapore LRT after prior incidents.",
        ))
        self.assertFalse(candidate["category_gates"]["major_accident"])
        self.assertTrue(candidate["category_gates"]["operational_policy"])
        self.assertEqual(candidate["primary_category"], "營運政策")
        self.assertEqual(_canonical_candidate_region(candidate), "新加坡")

    def test_power_outage_with_delays_is_not_major_accident(self):
        candidate = _evaluated(_candidate(
            2,
            "Metro service suspended after a power outage",
            "Passengers experienced delays after the power outage and service suspension.",
        ))
        self.assertFalse(candidate["category_gates"]["major_accident"])

    def test_power_failure_with_evacuation_and_investigation_is_major_accident(self):
        candidate = _evaluated(_candidate(
            3,
            "Metro service suspended after a power failure",
            "Passengers were evacuated from a train after the power failure and an official safety investigation was opened.",
        ))
        self.assertTrue(candidate["category_gates"]["major_accident"])

    def test_seattle_and_sound_transit_resolve_to_united_states(self):
        for candidate_id, title, snippet in (
            (4, "Seattle light rail safety update", "Seattle light rail service and stations are operated in the city."),
            (5, "Sound Transit Link light rail update", "Sound Transit operates the Link light rail system."),
        ):
            with self.subTest(title=title):
                self.assertEqual(_canonical_candidate_region(_candidate(candidate_id, title, snippet)), "美國")

    def test_washington_metro_and_wmata_red_line_resolve_to_united_states(self):
        for candidate_id, title, snippet in (
            (6, "Washington Metro Red Line service update", "Washington Metro operates the Red Line in the United States."),
            (7, "WMATA Red Line service update", "WMATA operates the Red Line metro service."),
        ):
            with self.subTest(title=title):
                self.assertEqual(_canonical_candidate_region(_candidate(candidate_id, title, snippet)), "美國")

    def test_generic_red_line_metro_does_not_guess_a_country(self):
        candidate = _candidate(
            8,
            "Red Line metro service update",
            "The Red Line metro introduced a service update without a city, operator, or country reference.",
        )
        self.assertEqual(_canonical_candidate_region(candidate), "未判定")


if __name__ == "__main__":
    unittest.main()
