import datetime
import unittest

import config
import ddgs_search_service
import search_queries


class ForwardTechnologyQueryTests(unittest.TestCase):
    def _context(self):
        return ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=30,
            lookback_int=30,
            is_global_scope=True,
            today=datetime.date(2026, 8, 11),
            ddgs_client_factory=None,
        )

    def test_forward_family_is_separate_from_known_technology(self):
        forward_specs = search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS
        known_specs = search_queries.SEARCH_QUERY_SPECS

        self.assertTrue(forward_specs)
        self.assertTrue(all(spec["family"] == "forward_technology" for spec in forward_specs))
        self.assertNotIn("forward_technology", {spec["family"] for spec in known_specs})

    def test_forward_family_is_disabled_by_default(self):
        context = self._context()

        queries, _ = ddgs_search_service.build_search_queries(context=context)

        self.assertEqual(len(queries), 21)
        self.assertNotIn(
            "forward_technology",
            {metadata.get("family") for metadata in context.query_metadata.values()},
        )

    def test_forward_family_is_added_only_when_explicitly_enabled(self):
        context = self._context()

        queries, _ = ddgs_search_service.build_search_queries(
            context=context,
            include_forward_technology=True,
        )
        forward_queries = [
            query
            for query in queries
            if context.query_metadata[query].get("family") == "forward_technology"
        ]

        self.assertGreaterEqual(len(forward_queries), 5)
        self.assertLessEqual(len(forward_queries), 10)
        self.assertEqual(len(forward_queries), len(search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS))
        self.assertEqual(len(queries), 21 + len(forward_queries))

    def test_forward_queries_are_effect_oriented_and_urban_rail_contextual(self):
        forward_queries = [
            spec["query"].casefold()
            for spec in search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS
        ]
        urban_rail_terms = ("metro", "subway", "urban rail", "light rail", "tram")
        novelty_terms = ("novel", "new method", "newly developed", "prototype", "emerging technology")
        application_terms = ("tested", "trial", "pilot", "demonstration", "deployed", "field test")
        effect_terms = (
            "reduce",
            "improve",
            "extend service life",
            "energy saving",
            "energy consumption",
        )

        for query in forward_queries:
            self.assertTrue(any(term in query for term in urban_rail_terms), msg=query)
            self.assertTrue(
                any(term in query for term in novelty_terms)
                or any(term in query for term in application_terms)
                or any(term in query for term in effect_terms),
                msg=query,
            )
            self.assertNotIn(query.strip(), {"ai", "energy", "material", "innovation"})

    def test_forward_family_covers_requested_effects_without_named_materials(self):
        all_queries = " ".join(
            spec["query"].casefold()
            for spec in search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS
        )
        required_effects = (
            ("energy",),
            ("weight",),
            ("friction", "wear"),
            ("maintenance", "service life"),
            ("reliability",),
            ("safety",),
            ("inspection", "sensor"),
        )

        for effect_group in required_effects:
            self.assertTrue(any(term in all_queries for term in effect_group), msg=effect_group)
        self.assertIn("novel material", all_queries)
        self.assertIn("reduce vehicle weight", all_queries)
        self.assertIn("energy consumption", all_queries)
        self.assertNotIn("carbon fiber", all_queries)
        self.assertNotIn("specific alloy", all_queries)
        self.assertNotIn("specific coating product", all_queries)

    def test_forward_queries_fit_existing_search_budget(self):
        self.assertLessEqual(len(search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS), 10)
        self.assertLessEqual(
            len(search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS),
            config.DDGS_GLOBAL_QUERY_LIMIT,
        )


if __name__ == "__main__":
    unittest.main()
