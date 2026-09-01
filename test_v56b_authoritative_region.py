import unittest

import article_processor


def _candidate(
    title: str,
    snippet: str,
    *,
    region: str = "未判定",
    query_region: str = "",
    query: str = "",
    source: str = "Railway-News",
) -> dict:
    url = "https://railway-news.com/v56b-fixture"
    return {
        "id": 1,
        "candidate_id": 1,
        "title": title,
        "raw_title": title,
        "normalized_title": title,
        "snippet": snippet,
        "region": region,
        "query_region": query_region,
        "query": query,
        "search_query": query,
        "source": source,
        "publisher": None,
        "source_domain": "railway-news.com",
        "source_href": url,
        "url": url,
        "raw_url": url,
        "search_language": "en",
    }


class V56BAuthoritativeRegionTests(unittest.TestCase):
    def test_explicit_greece_title_resolves_greece(self):
        candidate = _candidate(
            "Greece: Service Begins on Kalamaria Extension of Thessaloniki Metro",
            "Passenger service commenced on the Thessaloniki metro extension.",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "希臘")
        self.assertEqual(candidate["country"], "希臘")

    def test_thessaloniki_and_kalamaria_use_canonical_mapping(self):
        candidate = _candidate(
            "Kalamaria Extension of Thessaloniki Metro",
            "The Thessaloniki metro extension entered service in Greece.",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "希臘")
        self.assertEqual(candidate["region_resolution_method"], "metro_system_ownership")
        self.assertEqual(candidate["region_resolution_evidence_type"], "metro_system_location")

    def test_underground_context_does_not_map_greece_to_uk(self):
        candidate = _candidate(
            "Greece: Thessaloniki Metro extension",
            "The Kalamaria underground extension is part of Greece's metro network.",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "希臘")
        self.assertNotEqual(candidate["resolved_region"], "英國")

    def test_article_subject_overrides_conflicting_query_and_source_region(self):
        candidate = _candidate(
            "Greece: Thessaloniki Metro passenger service begins",
            "The Kalamaria extension commenced passenger service in Greece.",
            region="英國",
            query_region="英國",
            query="UK metro service",
            source="UK Rail Journal",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "希臘")
        self.assertTrue(candidate["region_conflict"])
        self.assertEqual(candidate["region_resolution_winning_evidence"]["region"], "希臘")

    def test_existing_uk_article_remains_uk(self):
        candidate = _candidate(
            "London Underground signalling upgrade",
            "Transport for London is upgrading signalling on the London Underground.",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "英國")

    def test_existing_madrid_article_remains_spain(self):
        candidate = _candidate(
            "Testing Begins on Driverless Trains for Madrid Metro",
            "Madrid Metro has begun testing new driverless trains.",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "西班牙")

    def test_existing_paris_article_remains_france(self):
        candidate = _candidate(
            "CAF to Supply Tram-Trains for Paris Region's T13 Line",
            "Paris Region awarded CAF a contract for tram-trains.",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "法國")

    def test_untrustworthy_geography_stays_unresolved(self):
        candidate = _candidate(
            "System modernization update",
            "The operator announced a technical review without naming a city or country.",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "未判定")
        self.assertEqual(candidate["region_resolution_method"], "unresolved")

    def test_thessaloniki_mapping_is_not_title_specific(self):
        title_candidate = _candidate(
            "Greece: Thessaloniki Metro extension",
            "Kalamaria extension context.",
        )
        snippet_candidate = _candidate(
            "Metro service extension",
            "The Thessaloniki metro in Greece serves Kalamaria.",
        )
        self.assertEqual(article_processor._canonical_candidate_region(title_candidate), "希臘")
        self.assertEqual(article_processor._canonical_candidate_region(snippet_candidate), "希臘")
        self.assertEqual(title_candidate["region_resolution_method"], "metro_system_ownership")
        self.assertEqual(snippet_candidate["region_resolution_method"], "metro_system_ownership")

    def test_geography_is_not_lookback_specific(self):
        for lookback_days in (7, 30, 365):
            with self.subTest(lookback_days=lookback_days):
                candidate = _candidate(
                    "Greece: Thessaloniki Metro extension",
                    "Kalamaria extension in Greece.",
                )
                candidate["lookback_days"] = lookback_days
                self.assertEqual(article_processor._canonical_candidate_region(candidate), "希臘")


if __name__ == "__main__":
    unittest.main()
