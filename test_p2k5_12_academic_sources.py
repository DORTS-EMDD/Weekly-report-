"""Offline regression tests for P2-K5.12 academic discovery and metadata rescue."""

from __future__ import annotations

import datetime
import json
import unittest
import urllib.parse

import config
import journal_service


class FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class AcademicFixtureSession:
    def get(self, url: str, timeout: int = 8, headers: dict | None = None) -> FakeResponse:
        if url.endswith("/priority"):
            return FakeResponse(200, """
                <html><head>
                <meta name="citation_publication_date" content="2026-07-10">
                <meta name="citation_online_date" content="2026-08-01">
                </head></html>
            """)
        if url.endswith("/pii/S1234567890123456"):
            return FakeResponse(200, """
                <html><head>
                <meta name="citation_title" content="Urban rail digital twin metadata rescue">
                <meta name="citation_pii" content="S1234567890123456">
                </head></html>
            """)
        if url.startswith("https://api.crossref.org/works/10.1234/fixture"):
            return FakeResponse(200, json.dumps({
                "message": {
                    "DOI": "10.1234/fixture.rescue",
                    "title": ["Urban rail digital twin metadata rescue"],
                    "container-title": ["Transportation Research"],
                    "published-online": {"date-parts": [[2026, 6, 18]]},
                }
            }))
        if url.startswith("https://api.crossref.org/works?"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            title = query.get("query.bibliographic", [""])[0]
            if title == "Urban rail digital twin metadata rescue":
                return FakeResponse(200, json.dumps({
                    "message": {
                        "items": [{
                            "DOI": "10.1234/fixture.rescue",
                            "title": [title],
                            "publisher": "Elsevier",
                            "container-title": ["Transportation Research"],
                            "published-online": {"date-parts": [[2026, 6, 18]]},
                        }]
                    }
                }))
            return FakeResponse(200, json.dumps({
                "message": {
                    "items": [{
                        "DOI": "10.9999/unrelated",
                        "title": ["Unrelated paper title"],
                        "publisher": "Elsevier",
                        "published-online": {"date-parts": [[2026, 6, 18]]},
                    }]
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
        "http_session_factory": AcademicFixtureSession,
        "make_news_candidate": lambda **kwargs: dict(kwargs),
        "is_urban_rail_candidate": lambda text: "urban rail" in text.casefold() or "metro" in text.casefold(),
    }
    values.update(overrides)
    return journal_service.JournalServiceContext(**values)


class P2K512SourceNormalizationTests(unittest.TestCase):
    def test_sciencedirect_aliases_are_canonicalized(self):
        self.assertEqual(journal_service._academic_domain("https://www.sciencedirect.com/article"), "sciencedirect.com")
        self.assertTrue(journal_service._journal_source_domain_matches("https://www.sciencedirect.com/article", "ScienceDirect"))

    def test_ieee_aliases_are_canonicalized(self):
        self.assertEqual(journal_service._academic_domain("https://ieeexplore.ieee.org/document/123"), "ieee.org")
        self.assertTrue(journal_service._journal_source_domain_matches("https://ieeexplore.ieee.org/document/123", "IEEE Xplore"))

    def test_taylor_francis_aliases_are_canonicalized(self):
        self.assertEqual(journal_service._academic_domain("https://www.tandfonline.com/doi/full/10.1/example"), "tandfonline.com")
        self.assertTrue(journal_service._journal_source_domain_matches("https://www.tandfonline.com/doi/full/10.1/example", "Taylor & Francis"))

    def test_springer_link_domain_is_not_lost(self):
        self.assertEqual(journal_service._academic_domain("https://link.springer.com/article/10.1/example"), "springer.com")
        self.assertTrue(journal_service._journal_source_domain_matches("https://link.springer.com/article/10.1/example", "Springer Urban Rail Transit articles"))

    def test_redirect_prefers_publisher_target(self):
        result = {
            "href": "https://www.google.com/url?q=https%3A%2F%2Fieeexplore.ieee.org%2Fdocument%2F123",
            "title": "Urban rail signalling study",
        }
        self.assertEqual(
            journal_service._journal_result_url(result),
            "https://ieeexplore.ieee.org/document/123",
        )

    def test_publisher_source_family_is_generic(self):
        self.assertEqual(journal_service._journal_source_family_for_url("https://elsevier.com/article"), "ScienceDirect")
        self.assertEqual(journal_service._journal_source_family_for_url("https://ieeexplore.ieee.org/document/1"), "IEEE Xplore")

    def test_doi_redirect_can_use_authoritative_publisher_name(self):
        self.assertEqual(
            journal_service._academic_publisher_domain(
                "https://doi.org/10.1234/example",
                {"publisher": "IEEE"},
            ),
            "ieee.org",
        )


class P2K512BroadDiscoveryTests(unittest.TestCase):
    def test_broad_lane_is_bounded(self):
        queries = journal_service.build_broad_academic_queries()
        self.assertEqual(len(queries), config.JOURNAL_BROAD_DISCOVERY_QUERY_BUDGET)
        self.assertLessEqual(len(queries), 10)

    def test_broad_lane_covers_generic_taxonomy_families(self):
        queries = journal_service.build_broad_academic_queries()
        self.assertTrue(any("materials" in query for query in queries))
        self.assertTrue(any("energy" in query for query in queries))
        self.assertTrue(any("digital twin" in query for query in queries))
        self.assertTrue(any("signalling" in query for query in queries))
        self.assertTrue(any("inspection" in query for query in queries))
        self.assertTrue(any("RAMS" in query for query in queries))

    def test_broad_lane_has_no_benchmark_terms(self):
        joined = " ".join(journal_service.build_broad_academic_queries()).casefold()
        for forbidden in ("flywheel", "webgis", "0957417425027964", "10.1234", "fixture"):
            self.assertNotIn(forbidden, joined)

    def test_broad_query_specs_are_three_part_taxonomy(self):
        self.assertEqual(len(config.ACADEMIC_BROAD_DISCOVERY_TAXONOMY), 10)
        for object_term, technical_family, signal in config.ACADEMIC_BROAD_DISCOVERY_TAXONOMY:
            self.assertTrue(object_term and technical_family and signal)


class P2K512MetadataTests(unittest.TestCase):
    def test_search_result_date_is_only_a_discovery_hint(self):
        info = journal_service._research_date_info(
            {"date": "2026-08-01"},
            "Urban rail paper",
            "Metro study",
            context=_context(),
        )
        self.assertEqual(info["published_date"], "")
        self.assertEqual(info["date_confidence"], "low")
        self.assertEqual(info["discovery_date_hint"], "2026-08-01")

    def test_authoritative_publisher_date_wins(self):
        info = journal_service._research_date_info(
            {"date": "2026-08-01", "journal_metadata": {"published_date": "2026-07-10", "metadata_source": "publisher_citation_meta"}},
            "Urban rail paper",
            "Metro study",
            context=_context(),
        )
        self.assertEqual(info["published_date"], "2026-07-10")
        self.assertEqual(info["date_confidence"], "high")
        self.assertEqual(info["metadata_source"], "publisher_citation_meta")

    def test_year_only_without_authoritative_evidence_stays_low(self):
        info = journal_service._research_date_info(
            {"date": "2026"},
            "Urban rail paper 2026",
            "Metro study",
            context=_context(),
        )
        self.assertEqual(info["published_date"], "")
        self.assertEqual(info["date_confidence"], "low")

    def test_title_lookup_requires_high_confidence_publisher_match(self):
        metadata = journal_service.fetch_scholarly_title_metadata(
            "Urban rail digital twin metadata rescue",
            publisher_domain="sciencedirect.com",
            discovery_date_hint="2026-01-05",
            context=_context(),
        )
        self.assertEqual(metadata["metadata_fetch_status"], "success")
        self.assertEqual(metadata["metadata_source"], "scholarly_title_lookup")
        self.assertEqual(metadata["published_date"], "2026-06-18")

    def test_low_confidence_title_lookup_is_rejected(self):
        metadata = journal_service.fetch_scholarly_title_metadata(
            "Urban rail paper with no exact match",
            publisher_domain="sciencedirect.com",
            discovery_date_hint="2026-01-05",
            context=_context(),
        )
        self.assertEqual(metadata["metadata_fetch_status"], "failed")
        self.assertEqual(metadata["metadata_match_status"], "low_confidence")

    def test_pii_title_lookup_rescues_candidate(self):
        metadata = journal_service.resolve_journal_metadata(
            "https://www.sciencedirect.com/science/article/pii/S1234567890123456",
            title="Urban rail digital twin metadata rescue",
            discovery_date_hint="2026-01-05",
            context=_context(),
        )
        self.assertEqual(metadata["metadata_fetch_status"], "success")
        self.assertEqual(metadata["metadata_source"], "scholarly_title_lookup")
        self.assertEqual(metadata["published_date"], "2026-06-18")

    def test_pii_candidate_becomes_eligible_after_rescue(self):
        class FixtureDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def text(self, query: str, max_results: int, backend: str) -> list[dict]:
                return [{
                    "title": "Urban rail digital twin metadata rescue",
                    "body": "Urban rail transit metro infrastructure digital twin maintenance validation.",
                    "href": "https://www.sciencedirect.com/science/article/pii/S1234567890123456",
                    "date": "2026-01-05",
                }]

        selected, _, excluded = journal_service.collect_journal_candidates(
            context=_context(ddgs_client_factory=FixtureDDGS),
        )
        self.assertTrue(selected)
        self.assertEqual(selected[0]["date_confidence"], "high")
        self.assertEqual(selected[0]["metadata_source"], "scholarly_title_lookup")
        self.assertTrue(any(item.get("exclude_reason") == "重複研究候選" for item in excluded))


class P2K512DiagnosticsTests(unittest.TestCase):
    def test_required_pipeline_counters_are_present(self):
        counters = journal_service._journal_pipeline_counts()
        for key in (
            "backend_raw_count", "result_url_count", "domain_match_count",
            "metadata_attempted_count", "metadata_resolved_count",
            "urban_rail_pass_count", "journal_score_pass_count", "accepted_count",
        ):
            self.assertIn(key, counters)

    def test_source_diagnostics_preserve_rescue_and_selection_layers(self):
        statuses = [{
            "source_family": "IEEE Xplore",
            "backend_raw_count": 2,
            "result_url_count": 2,
            "domain_match_count": 2,
            "metadata_attempted_count": 2,
            "metadata_resolved_count": 1,
            "urban_rail_pass_count": 1,
            "journal_score_pass_count": 1,
            "accepted_count": 1,
            "status": "成功",
        }]
        candidates = [{"url": "https://ieeexplore.ieee.org/document/1", "publisher_domain": "ieee.org"}]
        diagnostics = journal_service.academic_source_diagnostics(statuses, candidates, candidates)
        self.assertEqual(diagnostics["academic_discovery_by_source"]["IEEE Xplore"]["metadata_resolved_count"], 1)
        self.assertEqual(diagnostics["academic_selected_by_source"]["IEEE Xplore"], 1)
        self.assertEqual(diagnostics["academic_source_diversity_count"], 1)

    def test_springer_source_page_remains_discoverable(self):
        self.assertTrue(journal_service._journal_source_domain_matches(
            "https://link.springer.com/article/10.1007/example",
            "Springer Urban Rail Transit articles",
        ))


if __name__ == "__main__":
    unittest.main()
