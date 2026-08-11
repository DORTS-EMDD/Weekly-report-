import unittest

import config
import search_queries


class SearchQueryCoverageTests(unittest.TestCase):
    def setUp(self):
        self.technology_specs = [
            spec
            for spec in search_queries.SEARCH_QUERY_SPECS
            if spec.get("family") == "technology"
        ]
        self.english_queries = [
            spec["query"].casefold()
            for spec in self.technology_specs
            if spec.get("lang") == "en"
        ]

    def test_technology_query_count_preserves_existing_coverage(self):
        original_queries = {
            "metro subway MRT LRT tram CBTC signalling upgrade commissioning",
            "metro subway LRT tram rolling stock new trains ordered delivered",
            "metro subway tram contactless payment AFC fare gates rollout",
        }
        current_queries = {spec["query"] for spec in self.technology_specs}

        self.assertEqual(len(self.technology_specs), 21)
        self.assertTrue(original_queries.issubset(current_queries))
        self.assertLessEqual(len(self.technology_specs), 24)
        self.assertLessEqual(len(self.technology_specs), config.DDGS_GLOBAL_QUERY_LIMIT)

    def test_known_metro_technical_domains_are_covered(self):
        required_groups = (
            ("traction power", "substation", "upgrade"),
            ("railway 5g", "private lte", "communications"),
            ("platform screen doors", "hvac", "ventilation"),
            ("condition monitoring", "predictive maintenance"),
            ("computer vision", "video analytics", "testing"),
            ("digital twin", "bim", "iot monitoring"),
            ("automated inspection", "robotic inspection"),
            ("traction energy", "regenerative braking", "energy storage"),
            ("signalling cybersecurity", "rail ot", "security"),
        )

        for group in required_groups:
            self.assertTrue(
                any(all(term in query for term in group) for query in self.english_queries),
                msg=f"missing technology query group: {group}",
            )

    def test_english_technology_queries_are_contextual_and_action_oriented(self):
        urban_rail_terms = ("metro", "subway", "mrt", "lrt", "tram", "railway")
        technical_action_terms = (
            "upgrade",
            "commissioning",
            "ordered",
            "delivered",
            "rollout",
            "deployment",
            "testing",
            "assessment",
        )

        for query in self.english_queries:
            self.assertTrue(any(term in query for term in urban_rail_terms), msg=query)
            self.assertTrue(any(term in query for term in technical_action_terms), msg=query)
            self.assertNotIn(query.strip(), {"ai", "energy", "cybersecurity"})

    def test_no_forward_technology_terms_were_added(self):
        forbidden_terms = (
            "novel material",
            "composite material",
            "advanced alloy",
            "low-friction coating",
            "additive manufacturing",
            "aerospace",
            "semiconductor",
            "medical imaging",
        )
        all_queries = " ".join(spec["query"].casefold() for spec in self.technology_specs)

        for term in forbidden_terms:
            self.assertNotIn(term, all_queries)

    def test_technology_language_fallbacks_remain_available(self):
        expected_languages = {"en", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "zh"}
        actual_languages = {spec.get("lang") for spec in self.technology_specs}

        self.assertEqual(actual_languages, expected_languages)


if __name__ == "__main__":
    unittest.main()
