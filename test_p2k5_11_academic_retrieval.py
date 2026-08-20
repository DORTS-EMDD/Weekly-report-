"""Offline regression tests for P2-K5.11 academic retrieval diagnostics."""

from __future__ import annotations

import datetime
import json
import unittest

import config
import journal_service
from diagnostics.p2_k5_9_retrieval_ab_diagnosis import validate_no_benchmark_leakage
from diagnostics.p2_k5_11_academic_validation import calculate_layered_benchmark_metrics


class FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class MetadataSession:
    def get(self, url: str, timeout: int = 8, headers: dict | None = None) -> FakeResponse:
        if url.endswith("/year-only"):
            return FakeResponse(200, """
                <html><head>
                <meta name="citation_title" content="Urban rail digital twin study">
                <meta name="citation_date" content="2025">
                </head></html>
            """)
        if url.endswith("/priority"):
            return FakeResponse(200, """
                <html><head>
                <meta name="citation_publication_date" content="2026-07-10">
                <meta name="citation_online_date" content="2026-08-01">
                <meta name="og:title" content="Urban rail metadata fixture">
                </head></html>
            """)
        if url.startswith("https://api.crossref.org/works/"):
            return FakeResponse(200, json.dumps({
                "message": {
                    "DOI": "10.1234/fixture.webgis",
                    "title": ["Urban rail digital twin study"],
                    "container-title": ["Transportation Research"],
                    "published-online": {"date-parts": [[2026, 6, 18]]},
                }
            }))
        return FakeResponse(404, "")


def _context(**overrides):
    values = {
        "today": datetime.date(2026, 8, 20),
        "research_supplement_lookback_days": 365,
        "research_supplement_period_label": "近 365 天",
        "include_research_supplement": True,
        "ddgs_client_factory": object,
        "http_session_factory": MetadataSession,
        "make_news_candidate": lambda **kwargs: dict(kwargs),
        "is_urban_rail_candidate": lambda text: "urban rail" in text.casefold() or "metro" in text.casefold(),
    }
    values.update(overrides)
    return journal_service.JournalServiceContext(**values)


class P2K511MetadataTests(unittest.TestCase):
    def test_publication_date_priority_and_provenance(self):
        metadata = journal_service.fetch_journal_page_metadata(
            "https://publisher.example/priority",
            context=_context(),
        )
        self.assertEqual(metadata["published_date"], "2026-07-10")
        self.assertEqual(metadata["date_confidence"], "high")
        self.assertEqual(metadata["metadata_source"], "publisher_citation_meta")
        self.assertIn("citation_publication_date", metadata["metadata_fields_seen"])
        self.assertIn("citation_online_date", metadata["metadata_fields_seen"])

    def test_year_only_does_not_create_a_guessed_date(self):
        metadata = journal_service.fetch_journal_page_metadata(
            "https://publisher.example/year-only",
            context=_context(),
        )
        self.assertEqual(metadata["published_date"], "")
        self.assertEqual(metadata["date_confidence"], "low")
        self.assertEqual(metadata["date_reason"], "原始頁未解析到完整發表日期")

    def test_doi_metadata_rescues_year_only_candidate(self):
        metadata = journal_service.resolve_journal_metadata(
            "https://www.sciencedirect.com/science/article/pii/S1234567890123456",
            doi="10.1234/fixture.webgis",
            context=_context(),
        )
        self.assertEqual(metadata["published_date"], "2026-06-18")
        self.assertEqual(metadata["date_confidence"], "high")
        self.assertEqual(metadata["metadata_source"], "doi_metadata")
        self.assertIn("published-online", metadata["metadata_fields_seen"])

    def test_year_only_remains_excluded_without_authoritative_metadata(self):
        class YearOnlyDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def text(self, query: str, max_results: int, backend: str) -> list[dict]:
                return [{
                    "title": "Urban rail digital twin platform study",
                    "body": "Urban rail transit infrastructure digital twin research study.",
                    "href": "https://www.sciencedirect.com/science/article/pii/S1234567890123456",
                    "date": "2025",
                }]

        selected, statuses, excluded = journal_service.collect_journal_candidates(
            context=_context(ddgs_client_factory=YearOnlyDDGS),
        )
        self.assertEqual(selected, [])
        self.assertTrue(any(
            item.get("metadata_disposition") == "DISCOVERED_BUT_METADATA_REJECTED"
            for item in excluded
        ))

    def test_pii_and_doi_are_extracted_without_benchmark_specific_logic(self):
        self.assertEqual(
            journal_service._extract_pii("https://www.sciencedirect.com/science/article/pii/S0957417425027964"),
            "S0957417425027964",
        )
        self.assertEqual(
            journal_service._extract_doi("https://doi.org/10.1234/example.2026"),
            "10.1234/example.2026",
        )


class P2K511DiagnosticsTests(unittest.TestCase):
    def test_source_pipeline_counts_are_layered(self):
        class FixtureDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def text(self, query: str, max_results: int, backend: str) -> list[dict]:
                return [{
                    "title": "Urban rail digital twin validation study",
                    "body": "Urban rail transit metro infrastructure digital twin validation improves maintenance.",
                    "href": "https://sciencedirect.com/science/article/pii/S1234567890123456",
                    "published_date": "2026-07-12",
                }]

        _, statuses, _ = journal_service.collect_journal_candidates(
            context=_context(ddgs_client_factory=FixtureDDGS),
        )
        diagnostics = next(row for row in statuses if row.get("query") == "journal_diagnostics")
        outcomes = diagnostics["journal_source_pipeline_counts"]
        self.assertIn("ScienceDirect", outcomes)
        for key in (
            "backend_raw_count", "domain_match_count", "metadata_resolved_count",
            "urban_rail_pass_count", "journal_score_pass_count", "accepted_count",
        ):
            self.assertIn(key, outcomes["ScienceDirect"])
        self.assertGreater(outcomes["ScienceDirect"]["backend_raw_count"], 0)

    def test_academic_query_budget_and_benchmark_leakage_guard(self):
        source_queries = [query for _, query in config.JOURNAL_SOURCE_QUERY_SPECS]
        all_queries = list(config.JOURNAL_PRECISION_QUERIES) + list(config.JOURNAL_EXPLORATORY_QUERIES) + source_queries
        self.assertLessEqual(len(source_queries) * config.JOURNAL_SOURCE_QUERY_BUDGET, 5)
        self.assertTrue(validate_no_benchmark_leakage([{"query": query} for query in all_queries])["passed"])

    def test_layered_benchmark_metrics_do_not_change_retrieval(self):
        matcher = lambda candidate, label: candidate.get("benchmark_key") == label
        metrics = calculate_layered_benchmark_metrics(
            ["fixture-a", "fixture-b"],
            forward_raw=[{"benchmark_key": "fixture-a"}],
            academic_raw=[{"benchmark_key": "fixture-b"}],
            metadata_rescued=[{"benchmark_key": "fixture-b"}],
            academic_selected=[{"benchmark_key": "fixture-a"}],
            matcher=matcher,
        )
        self.assertEqual(metrics["benchmark_forward_raw_hits"], 1)
        self.assertEqual(metrics["benchmark_academic_raw_hits"], 1)
        self.assertEqual(metrics["benchmark_academic_metadata_rescued_hits"], 1)
        self.assertEqual(metrics["benchmark_academic_selected_hits"], 1)
        self.assertEqual(metrics["benchmark_any_discovery_hits"], 2)

    def test_forward_gate_module_remains_available_unchanged(self):
        from article_selector import build_selector_api

        api = build_selector_api(
            selected_types=["技術新知"],
            active_regions=["美國"],
            lookback_days=7,
            lookback_int=7,
            fast_mode_enabled=False,
            is_global_scope=True,
            today=datetime.date(2026, 8, 20),
            _search_family_from_query=lambda _query: "technology",
            _search_language_from_query=lambda _query: "en",
            create_requests_session=lambda: None,
            _profile_timing_add=lambda *_args: None,
        )
        candidate = {
            "search_family": "forward_technology",
            "title": "Metro operator pilots newly developed lightweight material on rail vehicles",
            "snippet": "A metro operator pilots a newly developed lightweight material on rail vehicles, reducing vehicle weight and traction energy consumption.",
            "date": "2026-08-10",
            "source": "Railway Gazette Fixture",
            "source_quality": "A",
            "source_tier": "B_professional",
            "url": "https://railwaygazette.com/news/2026/08/10/forward-case",
        }
        self.assertIn("_passes_forward_technology_gate", api)
        self.assertTrue(api["_passes_forward_technology_gate"](candidate))


if __name__ == "__main__":
    unittest.main()
