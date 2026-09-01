import datetime
import unittest

from article_processor import _canonical_candidate_region
from article_selector import build_selector_api
from config import SERVICE_OPENING_CATEGORY_KEY


ALL_TYPES = [
    "技術新知",
    "重大事故",
    "營運政策",
    "營運爭議",
    "機電標案",
    SERVICE_OPENING_CATEGORY_KEY,
]


def _selector(lookback_days: int = 14):
    return build_selector_api(
        selected_types=ALL_TYPES,
        active_regions=[],
        lookback_days=lookback_days,
        lookback_int=lookback_days,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 24),
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(
    candidate_id: str,
    title: str,
    snippet: str,
    *,
    source: str = "International Metro Review",
) -> dict:
    url = f"https://example.com/v56c/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "raw_title": title,
        "snippet": snippet,
        "date": "2026-08-20",
        "published_date": "2026-08-20",
        "region": "未判定",
        "query_region": "global",
        "source": source,
        "source_display": source,
        "source_domain": "example.com",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "page_type": "news_article",
        "search_family": "technology",
        "search_query": "fixture service opening",
        "search_language": "en",
    }


def _evaluate(candidate: dict, *, lookback_days: int = 14) -> dict:
    candidate.update(_selector(lookback_days)["evaluate_category_gates"](candidate))
    return candidate


class V56CServiceOpeningEvidenceTests(unittest.TestCase):
    def test_commenced_passenger_service_passes(self):
        candidate = _evaluate(_candidate(
            "commenced",
            "Thessaloniki Metro line opening",
            "The line officially commenced passenger service on August 20.",
        ))
        self.assertTrue(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assertNotIn("passenger_service_not_confirmed", candidate["service_opening_failure_reasons"])

    def test_passenger_service_began_passes(self):
        candidate = _evaluate(_candidate(
            "began",
            "Metro line passenger service update",
            "Passenger service began after the final safety inspection.",
        ))
        self.assertTrue(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])

    def test_entered_passenger_service_passes(self):
        candidate = _evaluate(_candidate(
            "entered",
            "Metro line enters operation",
            "The new line entered passenger service for the public.",
        ))
        self.assertTrue(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])

    def test_will_commence_passenger_service_is_future_only(self):
        candidate = _evaluate(_candidate(
            "future-commence",
            "Metro line opening date announced",
            "The line will commence passenger service on 13 September.",
        ))
        self.assertFalse(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assertTrue(candidate["future_opening_signal"])

    def test_testing_begins_is_testing_only(self):
        candidate = _evaluate(_candidate(
            "testing",
            "Metro testing begins",
            "Testing begins on the new metro extension before public service.",
        ))
        self.assertFalse(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assertIn("testing_only", candidate["service_opening_failure_reasons"])

    def test_construction_only_extension_is_rejected(self):
        candidate = _evaluate(_candidate(
            "construction",
            "Metro line extension under construction",
            "The extension remains under construction and its opening is planned.",
        ))
        self.assertFalse(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assertIn("planning_or_construction_only", candidate["service_opening_failure_reasons"])

    def test_non_passenger_facility_opening_is_rejected(self):
        candidate = _evaluate(_candidate(
            "facility",
            "Metro maintenance depot opens",
            "The maintenance facility opened for fleet servicing and workshop operations.",
        ))
        self.assertFalse(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])

    def test_madrid_driverless_testing_remains_technology(self):
        candidate = _evaluate(_candidate(
            "madrid-testing",
            "Testing Begins on Driverless Trains for Madrid Metro",
            "Madrid Metro has begun testing new driverless trains.",
        ))
        self.assertFalse(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assertTrue(candidate["category_gates"]["technology"])
        self.assertEqual(candidate["primary_category"], "技術新知")

    def test_auckland_future_opening_remains_future(self):
        candidate = _evaluate(_candidate(
            "auckland-future",
            "Auckland Metro opening date set",
            "Auckland will commence passenger services on 13 September.",
        ))
        self.assertFalse(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assertTrue(candidate["future_opening_signal"])

    def test_existing_genuine_opening_remains_pass(self):
        candidate = _evaluate(_candidate(
            "existing-opening",
            "New metro line officially opens to passengers",
            "The line opened to passengers and entered revenue service on August 20.",
        ))
        self.assertTrue(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assertEqual(candidate["primary_category"], "營運政策")
        self.assertEqual(candidate["operational_subtype"], SERVICE_OPENING_CATEGORY_KEY)

    def test_thessaloniki_geography_remains_canonical(self):
        candidate = _candidate(
            "thess-geography",
            "Greece: Service Begins on Kalamaria Extension of Thessaloniki Metro",
            "The Kalamaria extension of the Thessaloniki metro officially commenced passenger service, expanding Greece's first fully automated driverless metro network.",
        )
        self.assertEqual(_canonical_candidate_region(candidate), "希臘")
        evaluated = _evaluate(candidate)
        self.assertTrue(evaluated["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assertEqual(evaluated["primary_category"], "營運政策")

    def test_generic_semantics_are_not_title_specific(self):
        candidate = _evaluate(_candidate(
            "generic-title",
            "Metro line operational milestone confirmed",
            "The metro line has officially begun passenger service.",
        ))
        self.assertTrue(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])

    def test_service_opening_is_not_source_specific(self):
        for source in ("International Metro Review", "Railway Gazette"):
            with self.subTest(source=source):
                candidate = _evaluate(_candidate(
                    f"source-{source}",
                    "Metro service begins for passengers",
                    "The metro service has officially begun for passengers.",
                    source=source,
                ))
                self.assertTrue(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])

    def test_service_opening_is_not_lookback_specific(self):
        for lookback_days in (7, 30, 365):
            with self.subTest(lookback_days=lookback_days):
                candidate = _evaluate(
                    _candidate(
                        f"lookback-{lookback_days}",
                        "Metro service begins",
                        "Passenger service began on the line.",
                    ),
                    lookback_days=lookback_days,
                )
                self.assertTrue(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])


if __name__ == "__main__":
    unittest.main()
