import datetime
import inspect
import unittest
from unittest.mock import patch

import article_processor
import article_selector


ARTICLE_TITLE = "Metro signalling contract awarded"
ARTICLE_BODY = (
    "The metro signalling contract was awarded after a competitive procurement process. "
    "The rail authority confirmed implementation and delivery milestones for the urban "
    "rail network, including commissioning, safety verification and passenger service."
)
ANNUAL_TITLE = "Metro digital twin deployment uses CBTC system integration"
ANNUAL_BODY = (
    "The metro digital twin deployment uses CBTC system integration and improves reliability. "
    "The rail authority confirmed commissioning, safety verification and passenger service "
    "milestones for the urban rail network."
)


def _html(title: str, body: str) -> str:
    return f"<html><head><title>{title}</title></head><body><p>{body}</p></body></html>"


def _candidate(
    *,
    title: str = ARTICLE_TITLE,
    snippet: str = "Original feed evidence",
    url: str = "https://rail.example/news/metro-signalling-contract",
    source_href: str = "https://rail.example/news/metro-signalling-contract",
) -> dict:
    return {
        "id": "v55b-1",
        "candidate_id": "v55b-1",
        "title": title,
        "snippet": snippet,
        "date": "2026-08-30",
        "region": "英國",
        "query_region": "全球",
        "source": "Rail News",
        "source_display": "Rail News",
        "source_domain": "rail.example",
        "source_href": source_href,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "search_family": "technology",
        "query": "metro urban rail technology",
        "search_query": "metro urban rail technology",
        "primary_category": "excluded",
        "classification": "excluded",
        "category_gates": {"technology": False},
        "verified_bucket": "2026-Q3",
        "date_verification_status": "verified",
    }


class _Response:
    def __init__(self, text: str, url: str):
        self.text = text
        self.url = url
        self.status_code = 200
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.history = []


class _Session:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def get(self, url, **_kwargs):
        self.calls.append(url)
        return _Response(self.text, url)


def _annual_selector(days: int, session_factory=None):
    return article_selector.build_selector_api(
        selected_types=["技術新知", "機電標案"],
        active_regions=[],
        lookback_days=days,
        lookback_int=days,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 31),
        news_scope="both",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=session_factory or (lambda: object()),
        _profile_timing_add=lambda *_args: None,
    )


class V55BEnrichmentEvidenceValidityTests(unittest.TestCase):
    def _assert_rejected(self, candidate, body, *, expected_reason=None):
        original = dict(candidate)
        result = article_processor._prefetch_candidate_article(
            candidate,
            _Session(_html("Generic page", body)),
        )
        self.assertEqual(result["status"], "failed_enrichment")
        self.assertTrue(result["transport_success"])
        self.assertFalse(result["evidence_valid"])
        self.assertTrue(result["reason"].startswith("evidence_rejected:"))
        self.assertEqual(candidate["snippet"], original["snippet"])
        self.assertEqual(candidate["category_gates"], original["category_gates"])
        self.assertEqual(candidate["primary_category"], original["primary_category"])
        if expected_reason:
            self.assertIn(expected_reason, result["reason"])
        return result

    def test_search_results_page_is_rejected_as_evidence(self):
        body = (
            "Search results for metro. Search 0 results. "
            "Home menu navigation latest stories contact us privacy policy terms of use. "
        ) * 3
        self._assert_rejected(
            _candidate(url="https://rail.example/search/?q=metro"),
            body,
            expected_reason="search_results_shell",
        )

    def test_zero_results_shell_is_rejected(self):
        body = (
            "Search 0 RESULTS. No results found for the requested metro story. "
            "Home menu navigation latest stories contact us privacy policy terms of use. "
        ) * 3
        self._assert_rejected(_candidate(), body, expected_reason="search_results_shell")

    def test_a_z_topic_index_is_rejected(self):
        body = (
            "Alle Themen von A bis Z. Themen A-Z. Return to Homepage. "
            "All topics and all categories are listed here for browsing. "
        ) * 3
        self._assert_rejected(
            _candidate(url="https://rail.example/topics/a-z"),
            body,
            expected_reason="index_or_navigation_shell",
        )

    def test_research_index_listing_is_rejected(self):
        body = (
            "Page 1 for research. Return to Homepage. Browse all research categories. "
            "All stories and navigation links are shown in this listing. "
        ) * 3
        self._assert_rejected(
            _candidate(url="https://rail.example/research"),
            body,
            expected_reason="index_or_navigation_shell",
        )

    def test_generic_navigation_boilerplate_is_rejected(self):
        body = (
            "Home menu navigation latest popular search sign in log in subscribe newsletter "
            "contact us about us privacy policy terms of use cookie read more next previous. "
        ) * 3
        self._assert_rejected(_candidate(), body, expected_reason="generic_navigation_boilerplate")

    def test_genuine_article_body_is_accepted(self):
        candidate = _candidate()
        result = article_processor._prefetch_candidate_article(
            candidate,
            _Session(_html(ARTICLE_TITLE, ARTICLE_BODY)),
        )
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["transport_success"])
        self.assertTrue(result["evidence_valid"])
        self.assertIn(ARTICLE_TITLE, candidate["snippet"])
        self.assertEqual(candidate["enrichment_evidence_failure_reason"], "")

    def test_rejected_evidence_does_not_mutate_authoritative_candidate_evidence(self):
        candidate = _candidate(snippet="Original title and source evidence")
        original = {
            key: candidate[key]
            for key in ("title", "snippet", "source_href", "url", "primary_category", "category_gates")
        }
        self._assert_rejected(
            candidate,
            ("Search 0 results. Home menu navigation latest stories contact us privacy policy. " * 4),
        )
        self.assertEqual(
            {key: candidate[key] for key in original},
            original,
        )

    def test_transport_success_is_not_evidence_valid_success(self):
        candidate = _candidate()
        result = self._assert_rejected(
            candidate,
            ("The requested page returned a generic shell with no matching article title. " * 5),
            expected_reason="target_title_mismatch",
        )
        self.assertNotEqual(result["status"], "success")
        self.assertFalse(candidate.get("enrichment_evidence_valid"))

    def test_annual_counter_requires_verified_bucket_and_valid_evidence(self):
        api = _annual_selector(365)
        candidate = _candidate(
            title=ANNUAL_TITLE,
            snippet="Urban rail metro digital twin deployment uses CBTC system integration",
        )

        def rejected(_candidate, _session):
            return {
                "status": "failed_enrichment",
                "chars": 0,
                "elapsed_seconds": 0.0,
                "reason": "evidence_rejected:search_results_shell",
                "transport_success": True,
                "evidence_valid": False,
                "evidence_failure_reason": "search_results_shell",
            }

        with patch.object(article_selector, "_prefetch_candidate_article", side_effect=rejected):
            stats = api["prefetch_candidates_before_filter"]([candidate])
        self.assertEqual(stats["annual_rescue_attempted_by_bucket"], {"2026-Q3": 1})
        self.assertEqual(stats["annual_rescue_success_by_bucket"], {})
        self.assertFalse(candidate["rescue_enrichment_success"])

    def test_annual_counter_does_not_depend_on_post_fetch_readmission(self):
        api = _annual_selector(365)
        candidate = _candidate(
            title=ANNUAL_TITLE,
            snippet="Urban rail metro digital twin deployment uses CBTC system integration",
        )

        def enriched_then_rejected(candidate, _session):
            candidate["date_verification_status"] = "missing"
            candidate["primary_category"] = "技術新知"
            candidate["category_gates"] = {"technology": True}
            return {
                "status": "success",
                "chars": 180,
                "elapsed_seconds": 0.0,
                "reason": "fixture_article",
                "transport_success": True,
                "evidence_valid": True,
            }

        with patch.object(article_selector, "_prefetch_candidate_article", side_effect=enriched_then_rejected):
            stats = api["prefetch_candidates_before_filter"]([candidate])
        self.assertEqual(stats["annual_rescue_attempted_by_bucket"], {"2026-Q3": 1})
        self.assertEqual(stats["annual_rescue_success_by_bucket"], {"2026-Q3": 1})

    def test_shared_enrichment_contract_is_preserved_for_7_30_and_365(self):
        for days in (7, 30, 365):
            with self.subTest(lookback_days=days):
                candidate = _candidate()
                result = article_processor._prefetch_candidate_article(
                    candidate,
                    _Session(_html(ARTICLE_TITLE, ARTICLE_BODY)),
                )
                self.assertEqual(result["status"], "success")
                self.assertTrue(result["evidence_valid"])

    def test_annual_rescue_uses_shared_enrichment_contract(self):
        candidate = _candidate(
            title=ANNUAL_TITLE,
            snippet="Urban rail metro digital twin deployment uses CBTC system integration",
        )
        session = _Session(_html(ANNUAL_TITLE, ANNUAL_BODY))
        api = _annual_selector(365, session_factory=lambda: session)
        stats = api["prefetch_candidates_before_filter"]([candidate])
        self.assertEqual(stats["annual_rescue_attempted_by_bucket"], {"2026-Q3": 1})
        self.assertEqual(stats["annual_rescue_success_by_bucket"], {"2026-Q3": 1})
        self.assertTrue(candidate["enrichment_evidence_valid"])

    def test_v55a_page_type_regressions_remain_intact(self):
        api = _annual_selector(365)
        root_only = _candidate(
            url="https://news.google.com/",
            source_href="https://rail.example/",
        )
        article = _candidate()
        self.assertNotEqual(api["_compute_candidate_page_type"](root_only)[0], "news_article")
        self.assertEqual(api["_compute_candidate_page_type"](article)[0], "news_article")

    def test_evidence_validator_is_shared_and_not_lookback_specific(self):
        source = inspect.getsource(article_processor._prefetch_evidence_validity)
        self.assertNotIn("lookback", source.casefold())
        self.assertNotIn("daily hive", source.casefold())
        self.assertNotIn("alstom", source.casefold())
        self.assertNotIn("berliner kurier", source.casefold())
        self.assertNotIn("nub news", source.casefold())


if __name__ == "__main__":
    unittest.main()
