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

        self.assertEqual(len(queries), 33)
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

        self.assertGreaterEqual(len(forward_queries), 15)
        self.assertLessEqual(len(forward_queries), 30)
        self.assertEqual(len(forward_queries), len(search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS))
        self.assertEqual(
            {context.query_metadata[query].get("topic") for query in forward_queries},
            {"energy", "materials", "ai_maintenance", "digital_twin", "advanced_control"},
        )

    def test_forward_queries_are_short_generic_and_urban_rail_contextual(self):
        urban_rail_terms = ("metro", "subway", "urban rail", "light rail", "tram")
        topic_terms = {
            "energy": ("energy", "power"),
            "materials": ("material",),
            "ai_maintenance": ("maintenance", "inspection", "diagnosis"),
            "digital_twin": ("digital", "asset", "geospatial"),
            "advanced_control": ("signalling", "control", "automation", "inspection"),
        }

        for spec in search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS:
            query = spec["query"].casefold()
            self.assertLessEqual(len(query.split()), 5, msg=query)
            self.assertTrue(any(term in query for term in urban_rail_terms), msg=query)
            self.assertTrue(any(term in query for term in topic_terms[spec["topic"]]), msg=query)

    def test_forward_queries_do_not_embed_benchmark_combinations(self):
        queries = [
            spec["query"].casefold()
            for spec in (
                search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS
                + search_queries.FORWARD_TECHNOLOGY_FALLBACK_QUERY_SPECS
            )
        ]
        forbidden_combinations = (
            ("hydrogen", "superconducting", "battery"),
            ("low-floor", "composite"),
            ("webgis", "digital twin"),
            ("generative ai", "digital twin", "emergency maintenance"),
        )
        for combination in forbidden_combinations:
            self.assertFalse(
                any(all(term in query for term in combination) for query in queries),
                combination,
            )

    def test_forward_queries_fit_existing_search_budget(self):
        self.assertGreaterEqual(len(search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS), 15)
        self.assertLessEqual(len(search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS), 30)
        self.assertLessEqual(len(search_queries.FORWARD_TECHNOLOGY_FALLBACK_QUERY_SPECS), 5)
        self.assertLessEqual(
            len(search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS),
            config.DDGS_GLOBAL_QUERY_LIMIT,
        )


if __name__ == "__main__":
    unittest.main()
