import datetime
import unittest

import article_processor
from article_selector import build_selector_api
from config import SERVICE_OPENING_CATEGORY_KEY


TITLE = "First Siemens Metro Train Arrives for Sydney Metro – Western Sydney Airport"
URL = "https://railway-news.com/first-siemens-metro-train-arrives-for-sydney-metro-western-sydney-airport/"
SNIPPET = (
    "Siemens Mobility has delivered the first of 12 three-car metro trains for the "
    "Sydney Metro – Western Sydney Airport project, marking the start of the next "
    "phase of testing and commissioning for the new line. The train arrived in "
    "Australia following testing in Vienna and at Siemens Mobility’s Test and "
    "Validation Center in Wildenrath, Germany."
)


def _candidate(title: str, snippet: str, **overrides) -> dict:
    candidate = {
        "title": title,
        "raw_title": title,
        "normalized_title": title,
        "snippet": snippet,
        "date": "2026-08-19",
        "region": "未判定",
        "query_region": "",
        "query": "Railway-News",
        "search_query": "Railway-News",
        "search_language": "en",
        "search_family": "general",
        "source": "Railway-News",
        "source_display": "Railway-News",
        "publisher": None,
        "source_domain": "railway-news.com",
        "source_href": "",
        "url": URL,
        "raw_url": URL,
        "source_type": "官方 RSS",
        "source_quality": "A",
        "source_tier": "B_professional",
        "search_provider": "RSS",
        "raw_ingest_id": "raw_a2_1_sydney_fixture",
        "original_provider_metadata": {"entry_id": "https://railway-news.com/?p=28745980"},
    }
    candidate.update(overrides)
    return candidate


def _selector():
    return build_selector_api(
        selected_types=[
            "技術新知", "重大事故", "營運政策", "營運爭議", "機電標案",
            SERVICE_OPENING_CATEGORY_KEY,
        ],
        active_regions=[],
        lookback_days=365,
        lookback_int=365,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 24),
        news_scope="international",
        _search_family_from_query=lambda _query: "general",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


class SydneyGeographyRegressionTests(unittest.TestCase):
    def test_a2_1_t1_production_rss_candidate_resolves_to_australia(self):
        raw_rss = article_processor.RawSearchText(
            "\n".join((
                "【RSS來源：Railway-News】",
                "日期：2026-08-19",
                f"標題：{TITLE}",
                f"摘要：{SNIPPET}",
                f"連結：{URL}",
            )),
            provenance_records=[{
                "raw_title": TITLE,
                "raw_url": URL,
                "raw_publication_value": "Wed, 19 Aug 2026 12:42:25 +0000",
                "fetched_at": "2026-08-24T08:03:01.802595+00:00",
                "search_provider": "RSS",
                "publisher": None,
                "query": None,
                "source": "Railway-News",
                "original_provider_metadata": {
                    "entry_id": "https://railway-news.com/?p=28745980",
                },
                "raw_ingest_id": "raw_a2_1_sydney_rss",
            }],
        )
        parsed = article_processor.parse_rss_candidates(
            raw_rss,
            candidate_factory=lambda **kwargs: article_processor._make_news_candidate(
                **kwargs,
                search_family_resolver=lambda _value: "general",
                search_language_resolver=lambda _value: "en",
            ),
        )
        self.assertEqual(len(parsed), 1)
        candidate = parsed[0]

        self.assertEqual(candidate["raw_title"], TITLE)
        self.assertEqual(candidate["raw_url"], URL)
        self.assertEqual(candidate["search_provider"], "RSS")
        self.assertEqual(candidate["raw_ingest_id"], "raw_a2_1_sydney_rss")
        self.assertEqual(candidate["normalized_title"], TITLE)
        self.assertEqual(candidate["region"], "澳洲")

        api = _selector()
        kept, reason = api["preliminary_filter_candidate"](candidate)
        self.assertTrue(kept, reason)
        self.assertEqual(candidate["region_resolution_method"], "metro_system_ownership")
        self.assertEqual(candidate["region_resolution_winning_evidence"]["region"], "澳洲")
        self.assertNotEqual(candidate["primary_category"], "excluded")

    def test_a2_1_t2_sydney_metro_beats_testing_in_vienna(self):
        candidate = _candidate(
            "Sydney Metro train begins commissioning",
            "The train for Sydney Metro completed testing in Vienna before shipment to Australia.",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "澳洲")
        self.assertTrue(any(
            row["type"] == "manufacturer_location" and row["region"] == "奧地利"
            for row in candidate["region_resolution_conflicting_evidence"]
        ))

    def test_a2_1_t3_western_sydney_airport_project_beats_austrian_manufacturer(self):
        candidate = _candidate(
            "Western Sydney Airport metro project receives its first train",
            "The Austrian manufacturer assembled the rolling stock at its Vienna factory.",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "澳洲")

    def test_a2_1_t4_true_vienna_event_beats_sydney_vendor_reference(self):
        candidate = _candidate(
            "Vienna U-Bahn begins passenger testing of new trains",
            "Wiener Linien started the metro trial; a Sydney-based vendor supplied monitoring equipment.",
            region="澳洲",
            query_region="澳洲",
            query="Australia Sydney vendor metro",
            search_query="Australia Sydney vendor metro",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "奧地利")
        self.assertEqual(candidate["region_resolution_evidence_type"], "metro_system_location")

    def test_a2_1_t5_austria_publisher_and_query_cannot_override_sydney_event(self):
        candidate = _candidate(
            "Sydney Metro opens train testing for Western Sydney Airport",
            "Sydney Metro began commissioning the train in Australia.",
            region="奧地利",
            query_region="奧地利",
            query="Austria metro train",
            search_query="Austria metro train",
            source="Austria Rail Journal",
            source_display="Austria Rail Journal",
            publisher="Austria Rail Journal",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "澳洲")
        self.assertTrue(candidate["region_conflict"])

    def test_a2_1_t6_vienna_factory_only_does_not_invent_sydney_ownership(self):
        candidate = _candidate(
            "Siemens completes factory testing in Vienna",
            "The Austrian plant validated a train before delivery; no transit system or event location was identified.",
            region="奧地利",
            source_domain="example.com",
            url="https://example.com/geography/vienna-factory-only",
            raw_url="https://example.com/geography/vienna-factory-only",
        )
        article_processor._canonical_candidate_region(candidate)
        self.assertNotEqual(candidate["resolved_region"], "澳洲")
        self.assertNotEqual(candidate["region_resolution_evidence_type"], "metro_system_location")


if __name__ == "__main__":
    unittest.main()
