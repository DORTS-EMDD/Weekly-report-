import datetime
import unittest

import article_selector
import ddgs_search_service
from article_processor import _canonical_candidate_region
from config import ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY


FIXED_DATE = datetime.date(2026, 8, 20)
ALL_REPORT_TYPES = [
    "技術新知",
    "重大事故",
    "營運政策",
    "營運爭議",
    "service_opening",
    "機電標案",
]


def _context(*, is_global_scope, active_regions, lookback_int=365):
    return ddgs_search_service.DdgsSearchContext(
        selected_types=list(ALL_REPORT_TYPES),
        active_regions=list(active_regions),
        lookback_days=lookback_int,
        lookback_int=lookback_int,
        is_global_scope=is_global_scope,
        today=FIXED_DATE,
        ddgs_client_factory=None,
        news_scope="both",
    )


def _selector():
    return article_selector.build_selector_api(
        selected_types=list(ALL_REPORT_TYPES),
        active_regions=[],
        lookback_days=365,
        lookback_int=365,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=FIXED_DATE,
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(title, snippet, *, country="日本"):
    return {
        "id": title,
        "candidate_id": title,
        "title": title,
        "snippet": snippet,
        "source": "Railway Gazette",
        "source_href": "https://example.com/news",
        "url": "https://example.com/news",
        "date": "2026-08-18",
        "region": country,
        "country": country,
        "query_region": "global",
        "source_tier": "B_professional",
        "source_quality": "B",
        "page_type": "news_article",
    }


class P2K5R2GQueryRoutingTests(unittest.TestCase):
    def test_global_365_reserves_major_accident_and_official_investigation(self):
        context = _context(is_global_scope=True, active_regions=[])
        queries, _ = ddgs_search_service.build_search_queries(
            context=context,
            include_forward_technology=True,
        )
        families = [context.query_metadata[query]["family"] for query in queries]
        self.assertIn("major_accident", families)
        self.assertIn("official_investigation", families)
        self.assertLessEqual(len(queries), 40)

    def test_global_flags_remain_broad_without_active_region_filter(self):
        context = _context(is_global_scope=True, active_regions=[])
        ddgs_search_service.build_search_queries(context=context)
        self.assertTrue(context.is_global_scope)
        self.assertEqual(context.active_regions, [])
        self.assertIn("major_accident", context.planned_required_families)

    def test_advanced_country_route_keeps_existing_incident_families(self):
        context = _context(is_global_scope=False, active_regions=["日本"])
        queries, _ = ddgs_search_service.build_search_queries(
            context=context,
            include_forward_technology=True,
        )
        families = [context.query_metadata[query]["family"] for query in queries]
        self.assertIn("major_accident", families)
        self.assertIn("official_investigation", families)
        self.assertTrue(
            any(
                context.query_metadata[query].get("query_region") == "日本"
                and context.query_metadata[query].get("family") == "major_accident"
                for query in queries
            )
        )

    def test_global_does_not_add_benchmark_specific_query_content(self):
        context = _context(is_global_scope=True, active_regions=[])
        queries, _ = ddgs_search_service.build_search_queries(
            context=context,
            include_forward_technology=True,
        )
        query_text = " ".join(queries).casefold()
        for forbidden in ("manhattan", "manchester piccadilly", "wmata", "https://"):
            self.assertNotIn(forbidden, query_text)


class P2K5R2GLockedBehaviorTests(unittest.TestCase):
    def test_tokyo_timetable_adjustment_remains_operational(self):
        candidate = _candidate(
            "Tokyo Metro timetable change increases frequency",
            "Ginza Line trains run every 3 minutes and Marunouchi Line trains every 4 minutes.",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertTrue(gates["category_gates"]["operational_policy"])
        self.assertEqual(gates["operational_subtype"], "major_service_adjustment")

    def test_washington_wmata_region_precedence_remains_usa(self):
        candidate = _candidate(
            "Washington Metro Van Ness station signalling update",
            "WMATA announced a signalling update at Van Ness in Washington, DC.",
            country="英國",
        )
        candidate["query_region"] = "英國"
        self.assertEqual(_canonical_candidate_region(candidate), "美國")
        self.assertTrue(candidate["region_conflict"])

    def test_procurement_gate_behavior_remains_unchanged(self):
        candidate = _candidate(
            "London Underground awards CBTC signalling contract",
            "The metro authority awarded a CBTC signalling contract for the urban rail line.",
            country="英國",
        )
        gates = _selector()["evaluate_category_gates"](candidate)
        self.assertTrue(gates["category_gates"][ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY])

    def test_accident_threshold_remains_strict(self):
        candidate = _candidate(
            "Light rail vehicle has minor road collision with no derailment",
            "A minor road interface collision caused a short delay and no injuries.",
            country="澳洲",
        )
        self.assertFalse(_selector()["_passes_major_accident_gate"](candidate))


if __name__ == "__main__":
    unittest.main()
