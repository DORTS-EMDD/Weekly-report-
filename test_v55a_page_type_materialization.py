import datetime
import unittest

import article_selector


def _selector(lookback=365):
    return article_selector.build_selector_api(
        selected_types=["技術新知", "重大事故", "機電標案"],
        active_regions=[],
        lookback_days=lookback,
        lookback_int=lookback,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 31),
        news_scope="both",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: object(),
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(*, url="https://news.google.com/", source_href="https://operator.example.com/", title="Metro update", snippet="Urban rail metro update"):
    return {
        "title": title,
        "snippet": snippet,
        "date": "2026-08-01",
        "url": url,
        "source_href": source_href,
        "source": "Operator News",
        "source_domain": "operator.example.com",
        "source_tier": "A_official",
        "source_quality": "A",
        "region": "英國",
        "query": "metro update",
        "query_region": "全球",
        "search_family": "technology",
        "verified_bucket": "2026-Q3",
        "date_verification_status": "verified",
        "primary_category": "excluded",
        "classification": "excluded",
        "category_gates": {"technology": False},
    }


class V55APageTypeMaterializationTests(unittest.TestCase):
    def test_publisher_root_alone_does_not_prove_news_article(self):
        api = _selector()
        page_type, reason = api["_compute_candidate_page_type"](_candidate())
        self.assertNotEqual(page_type, "news_article")
        self.assertEqual(page_type, "publisher_root_only")
        self.assertIn("文章級 URL", reason)

    def test_root_metadata_does_not_bypass_annual_page_type_quality(self):
        api = _selector()
        candidate = _candidate(
            title="Land Transport Authority (LTA)",
            snippet="Land Transport Authority (LTA)",
        )
        candidate["page_type"], candidate["page_type_reason"] = api[
            "_compute_candidate_page_type"
        ](candidate)
        self.assertFalse(api["_is_annual_quality_rescue_candidate"](candidate))
        self.assertTrue(
            api["_annual_rescue_hard_exclusion_reason"](candidate).startswith(
                "page_type:"
            )
        )

    def test_article_level_candidate_url_remains_news_article(self):
        api = _selector()
        candidate = _candidate(url="https://operator.example.com/news/metro-update")
        self.assertEqual(
            api["_compute_candidate_page_type"](candidate)[0], "news_article"
        )

    def test_google_news_article_proxy_remains_news_article(self):
        api = _selector()
        candidate = _candidate(
            url="https://news.google.com/rss/articles/CBMiQ2h0dHBzOi8vZXhhbXBsZS5jb20vbmV3cy9tZXRyby11cGRhdGXSAQA"
        )
        self.assertEqual(
            api["_compute_candidate_page_type"](candidate)[0], "news_article"
        )

    def test_railway_news_style_article_remains_news_article(self):
        api = _selector()
        candidate = _candidate(
            url="https://railway-news.com/testing-begins-on-driverless-trains/",
            source_href="https://railway-news.com/testing-begins-on-driverless-trains/",
            title="Testing begins on driverless trains for Madrid Metro",
            snippet="Urban rail metro driverless trains begin testing on Line 6.",
        )
        self.assertEqual(
            api["_compute_candidate_page_type"](candidate)[0], "news_article"
        )

    def test_page_type_has_no_lookback_specific_behavior(self):
        candidate = _candidate()
        self.assertEqual(
            _selector(7)["_compute_candidate_page_type"](candidate),
            _selector(30)["_compute_candidate_page_type"](candidate),
        )
        self.assertEqual(
            _selector(30)["_compute_candidate_page_type"](candidate),
            _selector(365)["_compute_candidate_page_type"](candidate),
        )

    def test_annual_rescue_consumes_materialized_page_type(self):
        api = _selector()
        candidate = _candidate()
        candidate["page_type"], candidate["page_type_reason"] = api[
            "_compute_candidate_page_type"
        ](candidate)
        self.assertEqual(candidate["page_type"], "publisher_root_only")
        self.assertFalse(api["_candidate_prefetch_signal"](candidate))
        self.assertFalse(api["_is_annual_quality_rescue_candidate"](candidate))


if __name__ == "__main__":
    unittest.main()
