import unittest

import article_processor
import developer_debug_service


def _candidate(
    title: str,
    snippet: str,
    *,
    region: str = "未判定",
    query_region: str = "",
    source: str = "Fixture Rail News",
    publisher: str | None = None,
    query: str = "",
) -> dict:
    url = "https://example.com/geography/fixture"
    return {
        "id": 201,
        "candidate_id": 201,
        "title": title,
        "raw_title": f" {title} ",
        "normalized_title": title,
        "snippet": snippet,
        "region": region,
        "query_region": query_region,
        "query": query,
        "search_query": query,
        "search_language": "en",
        "source": source,
        "publisher": publisher,
        "source_domain": "example.com",
        "source_href": url,
        "url": url,
        "raw_url": url,
        "search_provider": "DDGS",
        "raw_ingest_id": "raw_a2_fixture_201",
        "original_provider_metadata": {"source": publisher},
        "classification": "技術新知",
    }


class GeographyOwnershipHardeningTests(unittest.TestCase):
    def test_a2_t1_munchen_system_beats_wien_factory(self):
        title = "München C2 metro trains manufactured at Siemens factory in Wien"
        snippet = "The C2 fleet for the München U-Bahn was produced at the Siemens factory in Wien, Austria."
        url = "https://example.at/munchen-c2"
        candidate = article_processor._make_news_candidate(
            title=title,
            date="2026-08-23",
            source="Austrian Rail Publisher",
            url=url,
            snippet=snippet,
            query="Austria metro rolling stock",
            region="奧地利",
            source_type="ddgs",
            query_metadata={"family": "technology", "lang": "en", "query_region": "奧地利"},
            search_family_resolver=lambda _value: "technology",
            search_language_resolver=lambda _value: "en",
            raw_provenance={
                "raw_title": f" {title} ",
                "raw_url": url,
                "raw_publication_value": "2026-08-23",
                "fetched_at": "2026-08-24T04:30:00+00:00",
                "search_provider": "DDGS",
                "publisher": "Austrian Rail Publisher",
                "original_provider_metadata": {"source": "Austrian Rail Publisher"},
                "raw_ingest_id": "raw_a2_fixture_201",
            },
        )

        self.assertEqual(candidate["region"], "德國")
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "德國")
        self.assertEqual(candidate["region_resolution_method"], "metro_system_ownership")
        self.assertEqual(candidate["region_resolution_evidence_type"], "metro_system_location")
        self.assertEqual(candidate["region_resolution_winning_evidence"]["region"], "德國")
        self.assertTrue(any(
            row["type"] == "manufacturer_location" and row["region"] == "奧地利"
            for row in candidate["region_resolution_conflicting_evidence"]
        ))
        self.assertEqual(candidate["raw_title"], f" {title} ")
        self.assertEqual(candidate["raw_ingest_id"], "raw_a2_fixture_201")

    def test_a2_t2_muenchen_system_beats_vienna_manufacturing(self):
        candidate = _candidate(
            "New Muenchen C2 metro fleet leaves the Siemens factory in Vienna",
            "The trains will enter service on the Muenchen U-Bahn after assembly in Austria.",
            region="奧地利",
        )

        self.assertEqual(article_processor._canonical_candidate_region(candidate), "德國")
        self.assertEqual(candidate["region_resolution_evidence_type"], "metro_system_location")

    def test_a2_t3_munich_system_beats_austria_publisher(self):
        candidate = _candidate(
            "Munich U-Bahn deploys the new C2 metro fleet",
            "The Munich metro operator introduced the trains this week.",
            region="奧地利",
            source="Austria Transport Journal",
            publisher="Austria Transport Journal",
        )

        self.assertEqual(article_processor._canonical_candidate_region(candidate), "德國")
        self.assertTrue(any(
            row["type"] == "publisher_location" and row["region"] == "奧地利"
            for row in candidate["region_resolution_conflicting_evidence"]
        ))

    def test_a2_t4_mvg_and_swm_operator_ownership(self):
        fixtures = (
            (
                "MVG receives the C2 train fleet from a Siemens factory in Wien",
                "MVG will operate the metro trains on its urban rail network.",
            ),
            (
                "SWM orders new metro trains assembled in Vienna",
                "SWM and the local operator will introduce the rolling stock next year.",
            ),
        )
        for title, snippet in fixtures:
            with self.subTest(title=title):
                candidate = _candidate(title, snippet, region="奧地利")
                self.assertEqual(article_processor._canonical_candidate_region(candidate), "德國")
                self.assertIn(
                    candidate["region_resolution_evidence_type"],
                    {"metro_system_location", "operator_location"},
                )

    def test_a2_t5_true_vienna_metro_event_beats_munich_vendor(self):
        candidate = _candidate(
            "Vienna U-Bahn receives new trains from a Munich-based supplier",
            "Wiener Linien introduced the fleet in Wien; Siemens maintains a factory near Munich.",
            region="德國",
            query_region="德國",
            source="Munich Vendor Bulletin",
        )

        self.assertEqual(article_processor._canonical_candidate_region(candidate), "奧地利")
        self.assertEqual(candidate["region_resolution_evidence_type"], "metro_system_location")
        self.assertTrue(any(
            row["type"] == "manufacturer_location" and row["region"] == "德國"
            for row in candidate["region_resolution_conflicting_evidence"]
        ))

    def test_a2_t6_query_region_cannot_override_system_ownership(self):
        candidate = _candidate(
            "München U-Bahn begins C2 train testing",
            "MVG began testing the metro fleet in passenger service.",
            region="奧地利",
            query_region="奧地利",
            query="Austria metro technology",
        )
        original_classification = candidate["classification"]

        self.assertEqual(article_processor._canonical_candidate_region(candidate), "德國")
        self.assertTrue(candidate["region_conflict"])
        self.assertEqual(candidate["classification"], original_classification)

    def test_a2_t7_unknown_and_vendor_only_geography_remain_unresolved(self):
        unknown = _candidate(
            "System modernization update",
            "The operator announced a technical review without naming a city or country.",
        )
        vendor_only = _candidate(
            "Munich-based vendor opens a new headquarters",
            "The supplier announced a corporate office expansion without identifying a transit project.",
            region="德國",
        )

        for candidate in (unknown, vendor_only):
            with self.subTest(title=candidate["title"]):
                self.assertEqual(article_processor._canonical_candidate_region(candidate), "未判定")
                self.assertEqual(candidate["region_resolution_method"], "unresolved")
        self.assertTrue(any(
            row["type"] == "vendor_location" and row["region"] == "德國"
            for row in vendor_only["region_resolution_conflicting_evidence"]
        ))

    def test_a2_t8_existing_chennai_manchester_and_generic_regions(self):
        fixtures = (
            ("Chennai Metro Rail appoints a signalling consultant", "CMRL confirmed the metro project.", "印度"),
            ("Manchester Piccadilly tram derailment", "Metrolink opened an investigation.", "英國"),
            ("Seattle light rail power outage", "The light rail operator restored service.", "美國"),
        )
        for title, snippet, expected in fixtures:
            with self.subTest(title=title):
                candidate = _candidate(title, snippet, region="未判定")
                self.assertEqual(article_processor._canonical_candidate_region(candidate), expected)

    def test_geography_diagnostics_are_bounded_and_exposed(self):
        candidate = _candidate(
            "München C2 metro trains leave a Siemens factory in Wien",
            "MVG will introduce the fleet; the Austrian publisher covered production in Vienna.",
            region="奧地利",
            query_region="奧地利",
            publisher="Austria Transport Journal",
        )
        article_processor._canonical_candidate_region(candidate)
        row = developer_debug_service._debug_candidate_rows([candidate])[0]

        for key in (
            "resolved_region",
            "region_resolution_method",
            "region_resolution_evidence_type",
            "region_resolution_evidence",
            "region_resolution_winning_evidence",
            "region_resolution_conflicting_evidence",
        ):
            self.assertIn(key, row)
        self.assertLessEqual(len(row["region_resolution_conflicting_evidence"]), 12)


if __name__ == "__main__":
    unittest.main()
