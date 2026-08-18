import datetime
import unittest
from unittest.mock import patch

import article_processor
import article_selector
import ddgs_search_service
import report_postprocessor


def _selector():
    return article_selector.build_selector_api(
        selected_types=["技術新知", "營運政策"],
        active_regions=["美國", "日本", "澳洲", "英國"],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=False,
        today=datetime.date(2026, 8, 18),
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(title, snippet, *, family="technology", source="Fixture Rail News", tier="B_professional"):
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
        "search_family": family,
        "query": "metro urban rail technology",
        "search_query": "metro urban rail technology",
        "core_systems": [],
    }


class _Response:
    def __init__(self, text, url="", status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.history = []


class _SourceLookupSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **_kwargs):
        self.calls.append(url)
        if "news.google.com" in url:
            raise RuntimeError("Google News redirect unresolved")
        if "/search/" in url:
            return _Response(
                '<html><a href="/news/how-automation-is-reshaping-light-rail">'
                "How Automation Is Reshaping Light Rail</a></html>",
                url=url,
            )
        return _Response(
            "<html><title>How Automation Is Reshaping Light Rail</title>"
            "<p>UITP describes automated train operation and digital twin monitoring "
            "for light rail maintenance, reliability, verification and deployment "
            "in passenger service.</p></html>",
            url=url,
        )


class P2K2RuntimeQualityTests(unittest.TestCase):
    def test_unresolved_google_news_uses_source_domain_followup(self):
        candidate = _candidate(
            "How Automation Is Reshaping Light Rail",
            "How Automation Is Reshaping Light Rail UITP",
            source="UITP",
            tier="A_official",
        )
        candidate["source_domain"] = "uitp.org"
        candidate["source_href"] = "https://www.uitp.org"
        candidate["url"] = "https://news.google.com/rss/articles/fixture"
        session = _SourceLookupSession()

        result = article_processor._prefetch_candidate_article(candidate, session)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["enrichment_method"], "source_domain_followup")
        self.assertEqual(candidate["enrichment_failure_reason"], "")
        self.assertTrue(candidate["resolved_article_url"].endswith("how-automation-is-reshaping-light-rail"))
        self.assertGreater(candidate["enriched_snippet_chars"], 120)
        self.assertEqual(candidate["enriched_content_source"], "source_domain_search")
        self.assertEqual(len(session.calls), 3)

    def test_high_priority_rescue_excludes_low_value_items(self):
        api = _selector()
        cases = [
            ("How Automation Is Reshaping Light Rail", "UITP", True),
            (
                "NY MTA Eyes Plan to Combat Subway Heat, Harness it for Municipal Building Use",
                "Railway Age",
                True,
            ),
            ("MTA Announces Two Modernized Elevators Open", "MTA", False),
            ("MTA Weekender Service", "MTA", False),
            ("Metro Ridership Statistics Released", "MTA", False),
            ("Company Announces AI Investment Strategy", "Technology Wire", False),
        ]
        for title, source, expected in cases:
            with self.subTest(title=title):
                candidate = _candidate(title, title, source=source, tier="A_official")
                self.assertEqual(api["_is_high_priority_rescue_candidate"](candidate), expected)

    def test_heat_recovery_and_digital_twin_track_b_pass(self):
        api = _selector()
        cases = [
            (
                "Metro deploys digital twin for maintenance",
                "A subway operator deploys a digital twin for predictive maintenance and condition monitoring.",
            ),
            (
                "NY subway heat recovery application",
                "The subway captures waste heat through a heat recovery system for municipal building energy reuse.",
            ),
        ]
        for title, snippet in cases:
            with self.subTest(title=title):
                candidate = _candidate(title, snippet, family="forward_technology")
                gates = api["evaluate_category_gates"](candidate)
                self.assertTrue(gates["track_b_gate_pass"])
                self.assertTrue(gates["passes_forward_technology_gate"])

    def test_regional_forward_fallback_keeps_selected_regions_in_metadata(self):
        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=["日本", "韓國", "澳洲", "英國"],
            lookback_days=7,
            lookback_int=7,
            is_global_scope=False,
            today=datetime.date(2026, 8, 18),
            ddgs_client_factory=object(),
            query_metadata={"metro forward": {"family": "forward_technology", "lang": "en", "planned_index": 1}},
            sleep=lambda _seconds: None,
            random_uniform=lambda _low, _high: 0,
        )

        def fake_execute(_factory, query, **_kwargs):
            if query == "metro forward":
                return []
            return []

        with patch.object(ddgs_search_service, "service_execute_ddgs_query", side_effect=fake_execute):
            ddgs_search_service.run_duckduckgo_searches(
                context=context,
                search_queries=["metro forward"],
                news_query_indices={1},
            )

        fallback_metadata = [
            metadata for metadata in context.query_metadata.values()
            if metadata.get("fallback_layer")
        ]
        self.assertEqual(len(fallback_metadata), 8)
        self.assertTrue(all(metadata["selected_regions"] == context.active_regions for metadata in fallback_metadata))
        self.assertTrue(all(metadata.get("region_group") for metadata in fallback_metadata))

    def test_source_renderer_drops_generic_label_but_keeps_real_source(self):
        source_line = report_postprocessor.normalize_source_line(
            "• 資料來源：資料來源未明確辨識。Railway-News：https://railway-news.com/fixture/article"
        )
        self.assertNotIn("資料來源未明確辨識", source_line)
        self.assertIn("Railway-News", source_line)
        self.assertIn("https://railway-news.com/fixture/article", source_line)

        report = report_postprocessor.normalize_final_report_md(
            "• 資料來源：\n資料來源未明確辨識\nRailway-News：https://railway-news.com/fixture/article"
        )
        self.assertNotIn("資料來源未明確辨識", report)
        self.assertIn("Railway-News", report)

    def test_gold_coast_and_sanying_incident_regressions_remain(self):
        api = _selector()
        gold_coast = _candidate(
            "Alstom Celebrates Delivery of Stage 3 of Gold Coast Light Rail Project",
            "Gold Coast Light Rail completed testing and commissioning of telecommunications, signalling and control systems for passenger service.",
            family="technology",
            source="Railway-News",
        )
        self.assertEqual(article_processor._canonical_candidate_region(gold_coast), "澳洲")
        self.assertTrue(api["evaluate_category_gates"](gold_coast)["category_gates"]["technology"])

        sanying = _candidate(
            "Metro signalling failure suspends service",
            "A signalling failure caused service suspension and degraded operation on the metro line.",
            family="policy",
            source="Fixture Rail News",
        )
        gates = api["evaluate_category_gates"](sanying)
        self.assertTrue(gates["technical_operation_incident"])
        self.assertEqual(gates["operational_subtype"], "technical_operation_incident")


if __name__ == "__main__":
    unittest.main()
