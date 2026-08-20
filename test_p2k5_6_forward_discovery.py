import datetime
import unittest
from unittest.mock import patch

import article_selector
import ddgs_search_service
import search_queries


def _context(lookback_days=365):
    return ddgs_search_service.DdgsSearchContext(
        selected_types=["技術新知"],
        active_regions=[],
        lookback_days=lookback_days,
        lookback_int=lookback_days,
        is_global_scope=True,
        today=datetime.date(2026, 8, 19),
        ddgs_client_factory=None,
        news_scope="international",
    )


def _selector(lookback_days=365):
    return article_selector.build_selector_api(
        selected_types=["技術新知"],
        active_regions=[],
        lookback_days=lookback_days,
        lookback_int=lookback_days,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 19),
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: object(),
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(identifier, title, snippet, *, family="forward_technology", date_value="2026-08-10"):
    url = f"https://fixture.example.test/forward/{identifier}"
    return {
        "id": identifier,
        "candidate_id": identifier,
        "title": title,
        "snippet": snippet,
        "date": date_value,
        "region": "英國",
        "query_region": "英國",
        "source": "Railway Gazette",
        "source_display": "Railway Gazette",
        "source_domain": "railwaygazette.com",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "search_family": family,
        "search_query": "metro urban rail forward technology",
        "search_language": "en",
        "python_score": 90,
        "final_selection_score": 90,
    }


class P2K56ForwardDiscoveryTests(unittest.TestCase):
    def test_forward_query_matrix_is_generic_short_and_covers_five_families(self):
        expected_topics = {
            "energy",
            "materials",
            "ai_maintenance",
            "digital_twin",
            "advanced_control",
        }
        topic_terms = {
            "energy": ("energy", "power"),
            "materials": ("material",),
            "ai_maintenance": ("maintenance", "inspection", "diagnosis"),
            "digital_twin": ("digital", "asset", "geospatial"),
            "advanced_control": ("signalling", "control", "automation", "inspection"),
        }
        rail_anchors = ("metro", "urban rail", "light rail", "tram")
        primary = search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS
        fallback = search_queries.FORWARD_TECHNOLOGY_FALLBACK_QUERY_SPECS

        self.assertGreaterEqual(len(primary), 15)
        self.assertLessEqual(len(primary), 30)
        self.assertLessEqual(len(fallback), 5)
        self.assertEqual({spec["topic"] for spec in primary}, expected_topics)
        self.assertEqual({spec["topic"] for spec in fallback}, expected_topics)

        for spec in primary + fallback:
            query = spec["query"].casefold()
            self.assertLessEqual(len(query.split()), 5, query)
            self.assertTrue(any(anchor in query for anchor in rail_anchors), query)
            self.assertTrue(any(term in query for term in topic_terms[spec["topic"]]), query)

    def test_forward_specs_exclude_benchmark_specific_combinations(self):
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

    def test_forward_query_family_is_stable_across_report_periods(self):
        expected_topics = {
            spec["topic"] for spec in search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS
        }
        for lookback_days in (7, 30, 365):
            context = _context(lookback_days)
            ddgs_search_service.build_search_queries(
                context=context,
                include_forward_technology=True,
            )
            forward_topics = {
                query_metadata.get("topic")
                for query_metadata in context.query_metadata.values()
                if query_metadata.get("family") == "forward_technology"
                and not query_metadata.get("fallback_layer")
            }
            self.assertEqual(forward_topics, expected_topics)

    def test_forward_and_general_rescue_budgets_are_separate(self):
        api = _selector(365)
        self.assertEqual(api["_forward_enrichment_budget_for_period"](365), 12)
        self.assertEqual(api["_general_rescue_budget_for_period"](365), 13)

    def test_forward_enrichment_continues_after_http_404(self):
        api = _selector(30)
        forward_candidates = [
            _candidate(
                identifier,
                "Technology: Keeping automated metros healthy",
                "Automated metros.",
            )
            for identifier in (1, 2)
        ]
        attempted_ids = []

        def enrich(candidate, _session):
            attempted_ids.append(candidate["id"])
            if candidate["id"] == 1:
                return {"status": "error", "reason": "source_lookup_http_404"}
            candidate["snippet"] += (
                " The operator deploys predictive maintenance and condition monitoring "
                "for rolling stock to improve reliability."
            )
            return {"status": "success", "chars": 180, "elapsed_seconds": 0.0, "reason": "fixture"}

        with patch.object(article_selector, "_prefetch_candidate_article", side_effect=enrich):
            stats = api["prefetch_candidates_before_filter"](forward_candidates)

        self.assertEqual(set(attempted_ids), {1, 2})
        self.assertEqual(stats["forward_enrichment_candidate_count"], 2)
        self.assertEqual(stats["forward_enrichment_attempted_count"], 2)
        self.assertEqual(stats["forward_enrichment_success_count"], 1)
        self.assertEqual(
            stats["forward_enrichment_failure_reason_counts"],
            {"source_lookup_http_404": 1},
        )

    def test_forward_taxonomy_plans_all_generic_topics(self):
        context = _context(30)
        queries, _ = ddgs_search_service.build_search_queries(
            context=context,
            include_forward_technology=True,
        )
        forward_queries = [
            query for query in queries
            if context.query_metadata[query].get("family") == "forward_technology"
            and not context.query_metadata[query].get("fallback_layer")
        ]
        topics = {
            context.query_metadata[query].get("topic")
            for query in forward_queries
        }
        self.assertEqual(
            topics,
            {"energy", "materials", "ai_maintenance", "digital_twin", "advanced_control"},
        )
        self.assertEqual(len(forward_queries), len(search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS))
        self.assertTrue(
            all(
                any(anchor in query.casefold() for anchor in ("metro", "subway", "urban rail", "light rail", "tram"))
                for query in forward_queries
            )
        )

    def test_forward_taxonomy_is_available_for_seven_day_window(self):
        context = _context(7)
        queries, _ = ddgs_search_service.build_search_queries(
            context=context,
            include_forward_technology=True,
        )
        self.assertEqual(
            sum(
                metadata.get("family") == "forward_technology"
                for metadata in context.query_metadata.values()
            ),
            len(search_queries.FORWARD_TECHNOLOGY_QUERY_SPECS),
        )
        self.assertTrue(queries)

    def test_multi_region_forward_queries_are_not_prefixed_to_first_region(self):
        context = _context(365)
        context.active_regions = ["臺灣", "英國", "美國"]
        context.is_global_scope = False
        queries, _ = ddgs_search_service.build_search_queries(
            context=context,
            include_forward_technology=True,
        )
        forward_queries = [
            query for query in queries
            if context.query_metadata[query].get("family") == "forward_technology"
            and not context.query_metadata[query].get("fallback_layer")
        ]
        self.assertTrue(forward_queries)
        self.assertTrue(all(not query.startswith("臺灣 ") for query in forward_queries))
        self.assertTrue(
            all(context.query_metadata[query].get("query_region") == "selected_regions" for query in forward_queries)
        )

    def test_forward_query_summary_reports_topic_counts(self):
        statuses = [
            {
                "search_family": "forward_technology",
                "forward_topic": "energy",
                "added_to_raw_count": 2,
                "execution_status": "success",
            },
            {
                "search_family": "forward_technology",
                "forward_topic": "materials",
                "added_to_raw_count": 1,
                "execution_status": "success",
            },
        ]
        summary = ddgs_search_service.build_ddgs_search_summary(statuses)
        self.assertEqual(summary["forward_query_count_by_topic"], {"energy": 1, "materials": 1})
        self.assertEqual(summary["forward_raw_count_by_topic"], {"energy": 2, "materials": 1})

    def test_short_forward_title_enters_independent_enrichment_queue(self):
        api = _selector(365)
        forward = _candidate(
            1,
            "Technology: Keeping automated metros healthy",
            "Automated metros.",
        )
        general = [
            _candidate(
                index + 10,
                f"Metro {index} CBTC modernization",
                "Urban rail metro CBTC modernization deploys system integration and improves reliability.",
                family="technology",
                date_value="2025-10-10",
            )
            for index in range(20)
        ]

        def enrich(candidate, _session):
            candidate["snippet"] += " The operator deploys predictive maintenance and condition monitoring for rolling stock."
            return {"status": "success", "chars": 180, "elapsed_seconds": 0.0, "reason": "fixture"}

        with patch.object(article_selector, "_prefetch_candidate_article", side_effect=enrich):
            stats = api["prefetch_candidates_before_filter"](general + [forward])

        self.assertTrue(api["_is_forward_enrichment_candidate"](forward))
        self.assertEqual(stats["forward_enrichment_candidate_count"], 1)
        self.assertEqual(stats["forward_enrichment_attempted_count"], 1)
        self.assertEqual(stats["forward_enrichment_success_count"], 1)
        self.assertEqual(forward["prefetch_status"], "success")
        self.assertTrue(forward["track_b_gate_pass_after_enrichment"])
        self.assertLessEqual(stats["attempted_count"], stats["limit"])

    def test_non_urban_generic_ai_and_material_candidates_fail_forward_gate(self):
        api = _selector(7)
        for identifier, title, snippet in (
            (2, "AI smart city maintenance platform", "An AI smart city platform improves municipal assets."),
            (3, "Advanced composite material research", "Researchers test composite material for building construction."),
        ):
            candidate = _candidate(identifier, title, snippet)
            candidate["search_family"] = "forward_technology"
            evaluated = api["evaluate_category_gates"](candidate)
            self.assertFalse(evaluated["passes_forward_technology_gate"])


if __name__ == "__main__":
    unittest.main()
