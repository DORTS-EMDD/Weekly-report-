import datetime
import unittest
from collections import Counter

import ddgs_search_service
import search_queries
from article_processor import dedupe_candidates


class P2K510ProductionMultilaneTests(unittest.TestCase):
    def _context(self, days=365):
        return ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=days,
            lookback_int=days,
            is_global_scope=True,
            today=datetime.date(2026, 8, 19),
            ddgs_client_factory=None,
        )

    def test_production_forward_builder_allocates_controlled_lanes(self):
        context = self._context()
        queries, _ = ddgs_search_service.build_search_queries(
            context=context,
            include_forward_technology=True,
        )
        forward_queries = [
            query for query in queries
            if context.query_metadata[query].get("family") == "forward_technology"
            and not context.query_metadata[query].get("fallback_layer")
        ]
        lane_counts = Counter(context.query_metadata[query].get("retrieval_lane") for query in forward_queries)
        self.assertEqual(dict(lane_counts), search_queries.FORWARD_TECHNOLOGY_LANE_BUDGETS)
        self.assertEqual(len(forward_queries), search_queries.FORWARD_TECHNOLOGY_PRIMARY_QUERY_BUDGET)
        self.assertLessEqual(len(queries), 40)

    def test_all_five_generic_families_remain_covered(self):
        topics = {spec["topic"] for spec in search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS}
        self.assertEqual(topics, {"energy", "materials", "ai_maintenance", "digital_twin", "advanced_control"})
        self.assertTrue(all(any(spec["topic"] == topic for spec in search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS) for topic in topics))

    def test_dual_anchor_and_source_aware_semantics_are_generic(self):
        rail_terms = ("metro", "subway", "urban rail", "light rail", "tram")
        system_terms = (
            "rolling stock", "power", "energy", "maintenance", "monitoring", "inspection",
            "machine learning", "digital twin", "infrastructure", "signalling", "control",
        )
        source_terms = ("authority", "publication", "research institute", "manufacturer")
        dual_specs = [spec for spec in search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS if spec["retrieval_lane"] == "DUAL_ANCHOR"]
        source_specs = [spec for spec in search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS if spec["retrieval_lane"] == "SOURCE_AWARE"]
        self.assertTrue(all(any(term in spec["query"] for term in rail_terms) for spec in dual_specs))
        self.assertTrue(all(any(term in spec["query"] for term in system_terms) for spec in dual_specs))
        self.assertTrue(all(any(term in spec["query"] for term in source_terms) for spec in source_specs))

    def test_quoted_assist_is_small_and_not_the_primary_lane(self):
        quoted_count = sum(
            spec["retrieval_lane"] == "QUOTED_ASSIST"
            for spec in search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS
        )
        self.assertEqual(quoted_count, 2)
        self.assertLessEqual(quoted_count / search_queries.FORWARD_TECHNOLOGY_PRIMARY_QUERY_BUDGET, 0.2)
        self.assertTrue(all('"' in spec["query"] for spec in search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS if spec["retrieval_lane"] == "QUOTED_ASSIST"))

    def test_query_specs_have_no_benchmark_specific_combinations(self):
        queries = [
            spec["query"].casefold()
            for spec in search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS + search_queries.FORWARD_TECHNOLOGY_FALLBACK_QUERY_SPECS
        ]
        forbidden_combinations = (
            ("hydrogen", "superconducting", "battery"),
            ("low-floor", "composite"),
            ("webgis", "digital twin"),
            ("generative ai", "digital twin", "emergency maintenance"),
        )
        self.assertFalse(any(all(term in query for term in combination) for query in queries for combination in forbidden_combinations))

    def test_cross_lane_url_dedup_aggregates_provenance(self):
        candidates = [
            {
                "title": "Metro pilots predictive maintenance",
                "date": "2026-08-10",
                "region": "美國",
                "url": "https://example.com/story?utm_source=one",
                "source_type": "ddgs",
                "source_tier": "B_media",
                "source_quality": "B",
                "retrieval_lane": "BROAD_DISCOVERY",
                "retrieval_lanes": ["BROAD_DISCOVERY"],
                "retrieval_provenance": [{"retrieval_lane": "BROAD_DISCOVERY", "query": "metro maintenance", "source_domain": "example.com"}],
            },
            {
                "title": "Metro pilots predictive maintenance",
                "date": "2026-08-10",
                "region": "美國",
                "url": "https://example.com/story?utm_source=two",
                "source_type": "ddgs",
                "source_tier": "B_media",
                "source_quality": "B",
                "retrieval_lane": "DUAL_ANCHOR",
                "retrieval_lanes": ["DUAL_ANCHOR"],
                "retrieval_provenance": [{"retrieval_lane": "DUAL_ANCHOR", "query": "metro maintenance condition monitoring", "source_domain": "example.com"}],
            },
        ]
        deduped, stats = dedupe_candidates(candidates, lookback_days=30)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(set(deduped[0]["retrieval_lanes"]), {"BROAD_DISCOVERY", "DUAL_ANCHOR"})
        self.assertEqual(len(deduped[0]["retrieval_provenance"]), 2)
        self.assertEqual(stats["multi_lane_candidates"], 1)

    def test_summary_reports_forward_lane_calls_raw_empty_and_domains(self):
        statuses = [
            {"search_family": "forward_technology", "retrieval_lane": "BROAD_DISCOVERY", "added_to_raw_count": 3, "result_domains": ["a.example"], "execution_status": "success"},
            {"search_family": "forward_technology", "retrieval_lane": "DUAL_ANCHOR", "added_to_raw_count": 0, "result_domains": [], "execution_status": "zero_results"},
            {"search_family": "forward_technology", "retrieval_lane": "SOURCE_AWARE", "added_to_raw_count": 2, "result_domains": ["b.example"], "execution_status": "success"},
        ]
        summary = ddgs_search_service.build_ddgs_search_summary(statuses)
        self.assertEqual(summary["forward_query_calls_total"], 3)
        self.assertEqual(summary["forward_query_calls_by_lane"]["DUAL_ANCHOR"], 1)
        self.assertEqual(summary["forward_raw_by_lane"]["SOURCE_AWARE"], 2)
        self.assertEqual(summary["forward_empty_queries_by_lane"]["DUAL_ANCHOR"], 1)
        self.assertEqual(summary["forward_domains_by_lane"]["BROAD_DISCOVERY"], ["a.example"])


if __name__ == "__main__":
    unittest.main()
