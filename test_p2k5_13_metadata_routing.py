"""Offline regression tests for bounded academic metadata routing."""

from __future__ import annotations

import datetime
import json
import unittest
import urllib.parse
from unittest.mock import patch

import journal_service


class FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class CrossrefFixtureSession:
    def get(self, url: str, timeout: int = 8, headers: dict | None = None) -> FakeResponse:
        if url.startswith("https://api.crossref.org/works?"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            title = query.get("query.bibliographic", [""])[0]
            return FakeResponse(200, json.dumps({
                "message": {
                    "items": [{
                        "DOI": "10.5555/metadata-fixture",
                        "title": [title],
                        "publisher": "IEEE",
                        "container-title": ["Urban Rail Research"],
                        "published-online": {"date-parts": [[2026, 8, 10]]},
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
        "ddgs_client_factory": None,
        "http_session_factory": CrossrefFixtureSession,
        "make_news_candidate": lambda **kwargs: dict(kwargs),
        "is_urban_rail_candidate": lambda text: "urban rail" in text.casefold() or "metro" in text.casefold(),
    }
    values.update(overrides)
    return journal_service.JournalServiceContext(**values)


class FakeDDGS:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def text(self, query: str, max_results: int, backend: str) -> list[dict]:
        lowered = query.casefold()
        if lowered.startswith("precision"):
            return [
                {
                    "title": f"Urban rail Springer study {index}",
                    "body": "Urban rail metro signalling technology study",
                    "href": f"https://link.springer.com/article/fixture-{index}",
                }
                for index in range(8)
            ]
        route_urls = {
            "springer": "https://link.springer.com/article/fixture-source-springer",
            "sciencedirect": "https://www.sciencedirect.com/science/article/pii/S1234567890123456",
            "mdpi": "https://www.mdpi.com/article/fixture-mdpi",
            "ieee": "https://ieeexplore.ieee.org/document/fixture-ieee",
            "taylor": "https://www.tandfonline.com/doi/full/10.5555/fixture-taylor",
        }
        for keyword, url in route_urls.items():
            if lowered.startswith(keyword):
                return [{
                    "title": f"Urban rail {keyword} study",
                    "body": "Urban rail metro signalling technology study",
                    "href": url,
                }]
        if lowered.startswith("broad"):
            return [{
                "title": "Urban rail broad academic study",
                "body": "Urban rail metro signalling technology study",
                "href": "https://doi.org/10.5555/fixture-broad",
            }]
        return []


class AcademicMetadataRoutingTests(unittest.TestCase):
    def test_page_type_contract_distinguishes_article_and_landing_pages(self):
        cases = {
            "https://example.org/search?q=metro": "SEARCH_RESULT",
            "https://example.org/journal/urban-rail": "JOURNAL_HOME",
            "https://example.org/issues/2026-08": "ISSUE_PAGE",
            "https://example.org/article/fixture": "ARTICLE_PAGE",
            "https://example.org/home": "GENERIC_LANDING",
            "https://example.org/publisher": "UNKNOWN",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(journal_service.classify_academic_page_type(url, "Urban rail paper"), expected)

    def test_generic_landing_title_is_not_sent_to_crossref(self):
        session_calls = []

        class RecordingSession:
            def get(self, url: str, timeout: int = 8, headers: dict | None = None):
                session_calls.append(url)
                return FakeResponse(500, "")

        metadata = journal_service.fetch_scholarly_title_metadata(
            "IEEE Xplore",
            publisher_domain="ieee.org",
            url="https://ieeexplore.ieee.org/Xplore/home.jsp",
            context=_context(http_session_factory=RecordingSession),
        )
        self.assertEqual(metadata["metadata_fetch_status"], "skipped")
        self.assertEqual(metadata["metadata_lookup_skipped_reason"], "generic_landing_page_title")
        self.assertEqual(session_calls, [])

    def test_sciencedirect_and_springer_landings_are_not_article_titles(self):
        for url, title in (
            ("https://www.sciencedirect.com/journal/urban-rail", "ScienceDirect"),
            ("https://link.springer.com/journal/40864", "SpringerLink"),
        ):
            with self.subTest(url=url):
                self.assertIn(
                    journal_service.classify_academic_page_type(url, title),
                    {"JOURNAL_HOME", "GENERIC_LANDING"},
                )
                metadata = journal_service.fetch_scholarly_title_metadata(
                    title,
                    publisher_domain=journal_service._academic_domain(url),
                    url=url,
                    context=_context(),
                )
                self.assertEqual(metadata["metadata_fetch_status"], "skipped")
                self.assertEqual(metadata["metadata_lookup_skipped_reason"], "generic_landing_page_title")

    def test_article_title_can_use_bounded_crossref_rescue(self):
        metadata = journal_service.fetch_scholarly_title_metadata(
            "Urban rail signalling technology study",
            publisher_domain="ieee.org",
            publisher_name="IEEE",
            url="https://ieeexplore.ieee.org/document/fixture",
            snippet="Urban rail metro signalling technology study",
            context=_context(),
        )
        self.assertEqual(metadata["metadata_fetch_status"], "success")
        self.assertEqual(metadata["metadata_year_match"], True)
        self.assertEqual(metadata["page_type"], "ARTICLE_PAGE")

    def test_truncated_title_requires_more_than_a_short_prefix(self):
        class TruncatedTitleSession:
            def get(self, url: str, timeout: int = 8, headers: dict | None = None):
                return FakeResponse(200, json.dumps({
                    "message": {
                        "items": [{
                            "title": ["Urban rail signalling advanced technology"],
                            "publisher": "IEEE",
                            "published-online": {"date-parts": [[2026, 8, 10]]},
                        }]
                    }
                }))

        metadata = journal_service.fetch_scholarly_title_metadata(
            "Urban rail signalling...",
            publisher_domain="ieee.org",
            publisher_name="IEEE",
            url="https://ieeexplore.ieee.org/document/fixture",
            snippet="Urban",
            context=_context(http_session_factory=TruncatedTitleSession),
        )
        self.assertEqual(metadata["metadata_fetch_status"], "failed")
        self.assertIn("標題", metadata["metadata_reject_reason"])

    def test_broad_queries_have_no_evaluation_fixture_identifiers(self):
        joined = " ".join(journal_service.build_broad_academic_queries()).casefold()
        for forbidden in ("10.5555", "fixture", "s1234567890123456"):
            self.assertNotIn(forbidden, joined)

    def test_search_date_is_not_authoritative(self):
        info = journal_service._research_date_info(
            {"date": "2026-08-01"},
            "Urban rail paper",
            "Metro study",
            context=_context(),
        )
        self.assertFalse(info["date_authoritative"])
        self.assertEqual(info["date_source"], "search_result")
        self.assertEqual(info["date_resolution_method"], "search_result_hint_only")

    def test_publisher_date_is_authoritative(self):
        info = journal_service._research_date_info(
            {"date": "2026-08-01", "journal_metadata": {"published_date": "2026-08-10", "metadata_source": "publisher_page"}},
            "Urban rail paper",
            "Metro study",
            context=_context(),
        )
        self.assertTrue(info["date_authoritative"])
        self.assertEqual(info["date_source"], "publisher_page")
        self.assertEqual(info["date_resolution_method"], "published_date")

    def test_pii_url_is_article_eligible(self):
        self.assertEqual(
            journal_service.classify_academic_page_type(
                "https://www.sciencedirect.com/science/article/pii/S1234567890123456",
                "Urban rail paper",
                pii="S1234567890123456",
            ),
            "ARTICLE_PAGE",
        )

    def test_source_domain_routes_override_query_lane(self):
        self.assertEqual(
            journal_service._metadata_route_for_candidate(
                "precision_queries",
                "https://ieeexplore.ieee.org/document/fixture",
            ),
            "IEEE Xplore",
        )
        self.assertEqual(
            journal_service._metadata_route_for_candidate(
                "broad_academic",
                "https://doi.org/10.5555/fixture",
            ),
            "Broad Academic",
        )

    def test_metadata_budget_is_bounded_per_route_and_broad_lane_is_not_starved(self):
        def resolved_metadata(url: str, **kwargs):
            return {
                "metadata_fetch_status": "success",
                "metadata_attempt_method": "offline_fixture",
                "metadata_source": "publisher_page",
                "metadata_title": kwargs.get("title", ""),
                "metadata_fields_seen": ["published_date"],
                "published_date": "2026-08-10",
                "date_confidence": "high",
                "date_reason": "offline fixture",
                "journal_name": "Urban Rail Research",
                "publisher_domain": journal_service._academic_publisher_domain(url),
            }

        patches = [
            patch.object(journal_service, "JOURNAL_SOURCE_PAGES", []),
            patch.object(journal_service, "JOURNAL_PRECISION_QUERIES", ("precision",)),
            patch.object(journal_service, "JOURNAL_EXPLORATORY_QUERIES", ()),
            patch.object(journal_service, "JOURNAL_SOURCE_QUERY_SPECS", (
                ("Springer", "springer"),
                ("ScienceDirect", "sciencedirect"),
                ("MDPI", "mdpi"),
                ("IEEE Xplore", "ieee"),
                ("Taylor & Francis", "taylor"),
            )),
            patch.object(journal_service, "JOURNAL_SOURCE_QUERY_BUDGET", 1),
            patch.object(journal_service, "JOURNAL_ARTICLE_FETCH_LIMIT", 18),
            patch.object(journal_service, "JOURNAL_MAX_RESULTS_PER_QUERY", 20),
            patch.object(journal_service, "get_journal_target_count", return_value=(1, 8)),
            patch.object(journal_service, "build_broad_academic_queries", return_value=["broad"]),
            patch.object(journal_service, "resolve_journal_metadata", side_effect=resolved_metadata),
            patch.object(journal_service, "score_journal_candidate", return_value={"journal_score": 80, "journal_score_reason": "fixture"}),
        ]
        for active_patch in patches:
            active_patch.start()
        try:
            context = _context(ddgs_client_factory=FakeDDGS)
            selected, statuses, excluded = journal_service.collect_journal_candidates(context=context)
        finally:
            for active_patch in reversed(patches):
                active_patch.stop()

        self.assertEqual(len(selected), 7)
        summary = next(row for row in statuses if row.get("timing_stage") == "summary")
        routes = summary["journal_metadata_route_outcomes"]
        self.assertEqual(routes["Springer"]["metadata_attempted_count"], 2)
        self.assertGreater(routes["Springer"]["metadata_budget_skipped_count"], 0)
        for route in ("Broad Academic", "ScienceDirect", "MDPI", "IEEE Xplore", "Taylor & Francis"):
            with self.subTest(route=route):
                self.assertGreater(routes[route]["metadata_attempted_count"], 0)
        self.assertGreater(routes["Broad Academic"]["accepted_count"], 0)
        self.assertTrue(any(item.get("metadata_route") == "Broad Academic" for item in selected))
        for item in selected:
            self.assertTrue(item["metadata_attempted"])
            self.assertEqual(item["metadata_method"], "offline_fixture")
            self.assertTrue(item["metadata_resolved"])
            self.assertEqual(item["metadata_failure_reason"], "")
        self.assertTrue(any("metadata route budget" in str(item.get("metadata_reject_reason")) for item in excluded))


if __name__ == "__main__":
    unittest.main()
