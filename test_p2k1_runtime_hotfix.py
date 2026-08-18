import datetime
import unittest
from unittest.mock import patch

import article_processor
import article_selector
import ddgs_search_service
from report_workflow_service import (
    WorkflowConfig,
    WorkflowDependencies,
    WorkflowRuntime,
)


def _selector(*, active_regions=None, is_global_scope=True):
    return article_selector.build_selector_api(
        selected_types=["技術新知"],
        active_regions=active_regions or [],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=is_global_scope,
        today=datetime.date(2026, 8, 18),
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(title, snippet, *, source="Fixture Rail News", tier="A_official"):
    return {
        "id": 1,
        "candidate_id": 1,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-17",
        "region": "未判定",
        "query_region": "",
        "source": source,
        "source_display": source,
        "source_domain": "fixture.example.test",
        "source_href": "https://fixture.example.test/source",
        "url": "https://fixture.example.test/article/1",
        "source_tier": tier,
        "source_quality": "A",
        "source_type": "ddgs",
        "search_family": "technology",
        "query": "metro technology",
        "search_query": "metro technology",
        "core_systems": [],
    }


class P2K1RuntimeHotfixTests(unittest.TestCase):
    def test_gold_coast_uses_content_region_when_query_region_is_blank(self):
        candidate = _candidate(
            "Alstom Celebrates Delivery of Stage 3 of Gold Coast Light Rail Project",
            "Alstom delivered testing and commissioning of telecommunications, signalling and control systems for Gold Coast Light Rail passenger service.",
            source="Railway-News",
            tier="B_professional",
        )
        region = article_processor._canonical_candidate_region(candidate)
        self.assertEqual(region, "澳洲")
        self.assertEqual(candidate["country"], "澳洲")
        self.assertEqual(candidate["query_region"], "")

        api = _selector(active_regions=["澳洲"], is_global_scope=False)
        keep, reason = api["preliminary_filter_candidate"](candidate)
        self.assertTrue(keep, reason)

    def test_city_system_and_operator_mappings_cover_common_markets(self):
        cases = [
            ("Sydney Metro announces signalling upgrade", "Sydney Metro Australia", "澳洲"),
            ("Melbourne tram fleet modernization", "Melbourne tram operator", "澳洲"),
            ("London Underground tests new signalling", "Transport for London", "英國"),
            ("New York Subway deploys sensors", "MTA", "美國"),
            ("Tokyo Metro upgrades train control", "Tokyo Metro", "日本"),
            ("Seoul Metro pilots condition monitoring", "Seoul Metro", "韓國"),
        ]
        for title, snippet, expected in cases:
            with self.subTest(title=title):
                candidate = _candidate(title, snippet)
                self.assertEqual(article_processor._canonical_candidate_region(candidate), expected)

    def test_unresolved_location_stays_unresolved(self):
        candidate = _candidate(
            "Urban rail equipment demonstration",
            "A demonstration was reported without a city, country, operator or system location.",
        )
        self.assertEqual(article_processor._canonical_candidate_region(candidate), "未判定")

    def test_short_rescue_fixtures_are_precise(self):
        api = _selector()
        cases = [
            ("How Automation Reshapes Light Rail", "UITP", True),
            ("MTA Weekender Service", "MTA", False),
            ("Status Transport for London", "Transport for London", False),
            ("Metro Rail Digital Twin", "Rail technology source", True),
            ("Light Rail Tourism Activity", "Tourism source", False),
        ]
        for title, source, expected in cases:
            with self.subTest(title=title):
                candidate = _candidate(title, title, source=source)
                self.assertEqual(api["_is_short_snippet_rescue_candidate"](candidate), expected)

    def test_rescue_runs_before_final_category_rejection_and_records_runtime_counts(self):
        candidate = _candidate(
            "How Automation Reshapes Light Rail",
            "How Automation Reshapes Light Rail",
            source="UITP",
        )
        config = WorkflowConfig(
            today=datetime.date(2026, 8, 18),
            lookback_days=7,
            selected_types=["技術新知"],
            active_regions=[],
            is_global_scope=True,
            standards_enabled=False,
            include_research_supplement=False,
            fast_mode_enabled=False,
            date_range="2026年08月11日 至 2026年08月18日",
            report_title="fixture",
            report_scope_label="國際",
            report_period_label="週報",
            news_scope="international",
        )
        runtime = WorkflowRuntime(
            config,
            WorkflowDependencies(
                http_session_factory=lambda: None,
                prefetch_enabled=True,
            ),
        )
        runtime.parse_candidates = lambda _raw_rss, _raw_ddg: [candidate]

        def enrich(item, _session):
            item["snippet"] = (
                "UITP describes deployed automated train operation and digital twin "
                "monitoring for light rail maintenance reliability."
            )
            return {"status": "success", "chars": 120, "elapsed_seconds": 0.0, "reason": "fixture"}

        with patch.object(article_selector, "_prefetch_candidate_article", side_effect=enrich):
            pool = runtime.prepare_candidate_pool("", "")

        stats = pool["prefetch_stats"]
        self.assertEqual(stats["rescue_candidate_count"], 1)
        self.assertEqual(stats["rescue_enrichment_attempted_count"], 1)
        self.assertEqual(stats["rescue_enrichment_success_count"], 1)
        self.assertEqual(pool["pipeline_debug_stats"]["pipeline_stages"]["rescue_candidate"], 1)
        self.assertEqual(pool["pipeline_debug_stats"]["pipeline_stages"]["rescue_enriched"], 1)

    def test_forward_primary_raw_zero_triggers_fallback_without_manual_counter(self):
        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=7,
            lookback_int=7,
            is_global_scope=True,
            today=datetime.date(2026, 8, 18),
            ddgs_client_factory=object(),
            query_metadata={"metro forward": {"family": "forward_technology", "lang": "en", "planned_index": 1}},
            sleep=lambda _seconds: None,
            random_uniform=lambda _low, _high: 0,
        )

        def fake_execute(_factory, query, **_kwargs):
            if query == "metro forward":
                return []
            return [{
                "title": "Subway deploys predictive maintenance",
                "body": "A subway operator deploys predictive maintenance to monitor equipment and reduce failures.",
                "href": "https://railwaygazette.com/fixture/p2k1-forward",
                "date": "2026-08-17",
            }]

        with patch.object(ddgs_search_service, "service_execute_ddgs_query", side_effect=fake_execute):
            raw_text, statuses, summary = ddgs_search_service.run_duckduckgo_searches(
                context=context,
                search_queries=["metro forward"],
                news_query_indices={1},
            )

        self.assertIn("Subway deploys predictive maintenance", raw_text)
        self.assertEqual(summary["forward_technology_primary_raw_count"], 0)
        self.assertEqual(summary["forward_technology_fallback_raw_count"], 8)
        self.assertEqual(summary["forward_technology_raw_count"], 8)
        self.assertEqual(summary["forward_technology_fallback_query_count"], 8)
        self.assertTrue(all(row.get("search_family") == "forward_technology" for row in statuses if row.get("fallback_layer")))

        def candidate_factory(**kwargs):
            metadata = context.query_metadata.get(kwargs.get("query", ""), {})
            return article_processor._make_news_candidate(
                **kwargs,
                query_metadata=metadata,
                search_family_resolver=lambda query: context.query_metadata.get(query, {}).get("family", "general"),
                search_language_resolver=lambda query: context.query_metadata.get(query, {}).get("lang", "en"),
            )

        fallback_candidates = article_processor.parse_ddg_candidates(raw_text, candidate_factory)
        self.assertTrue(fallback_candidates)
        self.assertTrue(all(item["search_family"] == "forward_technology" for item in fallback_candidates))
        forward_gate = _selector()["evaluate_category_gates"](fallback_candidates[0])
        self.assertTrue(forward_gate["track_b_gate_pass"])

    def test_forward_primary_raw_nonzero_does_not_run_fallback(self):
        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=7,
            lookback_int=7,
            is_global_scope=True,
            today=datetime.date(2026, 8, 18),
            ddgs_client_factory=object(),
            query_metadata={"metro forward": {"family": "forward_technology", "lang": "en", "planned_index": 1}},
            sleep=lambda _seconds: None,
            random_uniform=lambda _low, _high: 0,
        )

        def fake_execute(_factory, query, **_kwargs):
            self.assertEqual(query, "metro forward")
            return [{
                "title": "Subway deploys predictive maintenance",
                "body": "A subway operator deploys predictive maintenance to monitor equipment and reduce failures.",
                "href": "https://railwaygazette.com/fixture/p2k1-forward-primary",
                "date": "2026-08-17",
            }]

        with patch.object(ddgs_search_service, "service_execute_ddgs_query", side_effect=fake_execute):
            _raw_text, statuses, summary = ddgs_search_service.run_duckduckgo_searches(
                context=context,
                search_queries=["metro forward"],
                news_query_indices={1},
            )

        self.assertEqual(summary["forward_technology_primary_raw_count"], 1)
        self.assertEqual(summary["forward_technology_fallback_raw_count"], 0)
        self.assertEqual(summary["forward_technology_fallback_query_count"], 0)
        self.assertFalse(any(row.get("fallback_layer") for row in statuses))


if __name__ == "__main__":
    unittest.main()
