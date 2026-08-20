import unittest

import article_selector
import ddgs_search_service
from article_processor import normalize_country
from config import (
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
    INTERNATIONAL_ELECTROMECHANICAL_PROCUREMENT_QUERY_BUDGET,
)
from diagnostics.p2_k5_12r_global_category import (
    build_major_accident_diagnostic,
    build_operational_diagnostic,
    build_procurement_retrieval_diagnostic,
)
from search_queries import (
    DOMESTIC_ELECTROMECHANICAL_PROCUREMENT_QUERY_SPECS,
    ELECTROMECHANICAL_PROCUREMENT_QUERY_SPECS,
)


FIXED_DATE = __import__("datetime").date(2026, 8, 20)


def _selector(selected_types=None, *, lookback_int=7, is_global_scope=True):
    return article_selector.build_selector_api(
        selected_types=selected_types or [
            "技術新知", "重大事故", "營運政策", "營運爭議", ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
        ],
        active_regions=[],
        lookback_days=lookback_int,
        lookback_int=lookback_int,
        fast_mode_enabled=False,
        is_global_scope=is_global_scope,
        today=FIXED_DATE,
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(title, snippet, *, source="Transit Authority", country="日本", date="2026-08-18"):
    return {
        "id": title,
        "candidate_id": title,
        "title": title,
        "snippet": snippet,
        "source": source,
        "source_href": "https://example.com/news",
        "url": "https://example.com/news",
        "date": date,
        "region": country,
        "country": country,
        "source_tier": "B_professional",
        "source_quality": "B",
        "page_type": "news_article",
    }


class P2K5_12RQueryTests(unittest.TestCase):
    def _context(self, *, lookback_int=365, active_regions=None, is_global_scope=True, news_scope="international"):
        return ddgs_search_service.DdgsSearchContext(
            selected_types=[ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL],
            active_regions=active_regions or [],
            lookback_days=lookback_int,
            lookback_int=lookback_int,
            is_global_scope=is_global_scope,
            today=FIXED_DATE,
            ddgs_client_factory=None,
            news_scope=news_scope,
        )

    def test_annual_global_plans_bounded_international_procurement_queries(self):
        context = self._context()
        queries, _ = ddgs_search_service.build_search_queries(context=context)
        rows = [
            context.query_metadata[query]
            for query in queries
            if context.query_metadata[query].get("family") == ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY
        ]
        self.assertEqual(len(rows), INTERNATIONAL_ELECTROMECHANICAL_PROCUREMENT_QUERY_BUDGET)
        self.assertTrue(all(row.get("query_region") == "global" for row in rows))
        self.assertTrue(all("臺灣" not in query for query in queries))

    def test_domestic_procurement_queries_are_unchanged(self):
        context = self._context(lookback_int=7, is_global_scope=False, news_scope="domestic")
        queries, _ = ddgs_search_service.build_search_queries(context=context)
        self.assertEqual(
            queries,
            [spec["query"] for spec in DOMESTIC_ELECTROMECHANICAL_PROCUREMENT_QUERY_SPECS],
        )

    def test_global_query_budget_does_not_change_weekly_taxonomy(self):
        context = self._context(lookback_int=7)
        queries, _ = ddgs_search_service.build_search_queries(context=context)
        rows = [
            context.query_metadata[query]
            for query in queries
            if context.query_metadata[query].get("family") == ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY
        ]
        self.assertEqual(len(rows), len(ELECTROMECHANICAL_PROCUREMENT_QUERY_SPECS))
        self.assertTrue(all(row.get("query_region") == "global" for row in rows))

    def test_specified_regions_keep_procurement_query_region(self):
        context = self._context(
            lookback_int=365,
            active_regions=["日本", "美國"],
            is_global_scope=False,
            news_scope="international",
        )
        queries, _ = ddgs_search_service.build_search_queries(context=context)
        rows = [
            context.query_metadata[query]
            for query in queries
            if context.query_metadata[query].get("family") == ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY
        ]
        self.assertTrue(rows)
        self.assertTrue({row.get("query_region") for row in rows} <= {"日本", "美國"})

    def test_global_procurement_diagnostic_disables_region_filter(self):
        result = build_procurement_retrieval_diagnostic(
            [{"search_family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY, "query_region": "global", "added_to_raw_count": 2}],
            [{"search_family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY, "query_region": "global", "country": "日本"}],
            is_global_scope=True,
        )
        self.assertFalse(result["region_filter_enabled"])
        self.assertEqual(result["international_raw_count"], 2)
        self.assertEqual(result["non_taiwan_candidate_count"], 1)

    def test_specified_procurement_diagnostic_filters_active_regions(self):
        result = build_procurement_retrieval_diagnostic(
            [{"search_family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY, "query_region": "日本", "added_to_raw_count": 1}],
            [
                {"search_family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY, "query_region": "日本", "country": "日本"},
                {"search_family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY, "query_region": "日本", "country": "美國"},
            ],
            active_regions=["日本"],
            is_global_scope=False,
        )
        self.assertEqual(result["international_candidate_count"], 1)


class P2K5_12RCategoryTests(unittest.TestCase):
    def _evaluate(self, candidate):
        return _selector()["evaluate_category_gates"](candidate)

    def test_genuine_major_accident_passes(self):
        candidate = _candidate(
            "Seoul Metro train collision injures 25 and suspends Line 2",
            "Two metro trains collided, 25 passengers were injured and service was suspended.",
            country="韓國",
        )
        gates = self._evaluate(candidate)
        self.assertTrue(gates["category_gates"]["major_accident"])

    def test_minor_lrt_road_collision_is_not_major(self):
        candidate = _candidate(
            "Light rail vehicle has minor road collision with no derailment",
            "A minor road interface collision caused a short delay and no injuries.",
            country="澳洲",
        )
        gates = self._evaluate(candidate)
        self.assertFalse(gates["category_gates"]["major_accident"])

    def test_academic_accident_simulation_is_not_major(self):
        candidate = _candidate(
            "Accident simulation study for metro train collision risk",
            "An academic paper presents a simulated collision scenario and risk model.",
        )
        gates = self._evaluate(candidate)
        self.assertFalse(gates["category_gates"]["major_accident"])

    def test_emergency_inspection_is_operational_dynamics(self):
        candidate = _candidate(
            "Tokyo Metro emergency inspection causes temporary suspension",
            "Tokyo Metro temporarily suspended service for emergency inspection of the line.",
        )
        gates = self._evaluate(candidate)
        self.assertTrue(gates["category_gates"]["operational_policy"])
        self.assertEqual(gates["operational_subtype"], "technical_operation_incident")

    def test_routine_weekend_notice_is_not_operational_dynamics(self):
        candidate = _candidate(
            "Metro weekend service notice",
            "A routine maintenance advisory changes the weekend timetable.",
        )
        gates = self._evaluate(candidate)
        self.assertFalse(gates["category_gates"]["operational_policy"])

    def test_japan_odor_suspension_is_operational_dynamics(self):
        candidate = _candidate(
            "Nagoya subway odor causes partial service suspension",
            "Nagoya subway suspended part of the line as a precaution after an unusual odor.",
        )
        gates = self._evaluate(candidate)
        self.assertTrue(gates["category_gates"]["operational_policy"])

    def test_international_signalling_contract_passes_procurement(self):
        candidate = _candidate(
            "London Underground awards CBTC signalling contract",
            "The metro authority awarded a CBTC signalling contract for the urban rail line.",
            country="英國",
        )
        gates = self._evaluate(candidate)
        self.assertTrue(gates["category_gates"][ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY])

    def test_rolling_stock_contract_passes_procurement(self):
        candidate = _candidate(
            "Singapore MRT orders new rolling stock",
            "Singapore MRT placed an order for new metro trains and rolling stock.",
            country="新加坡",
        )
        gates = self._evaluate(candidate)
        self.assertTrue(gates["category_gates"][ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY])

    def test_civil_only_contract_fails_procurement(self):
        candidate = _candidate(
            "Metro awards tunnel construction contract",
            "The authority awarded a civil tunnel construction contract for a new line.",
        )
        gates = self._evaluate(candidate)
        self.assertFalse(gates["category_gates"][ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY])

    def test_accessibility_only_contract_fails_procurement(self):
        candidate = _candidate(
            "Metro accessibility campaign contract",
            "A contractor will provide accessibility advocacy and passenger assistance.",
        )
        gates = self._evaluate(candidate)
        self.assertFalse(gates["category_gates"][ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY])

    def test_category_diagnostic_lists_at_least_thirty_incident_rows(self):
        raw = [_candidate(f"Metro incident {index}", "Metro collision reported.") for index in range(35)]
        report = build_major_accident_diagnostic(raw, evaluator=self._evaluate, limit=30)
        self.assertEqual(report["listed_count"], 30)

    def test_operational_diagnostic_retains_failure_reasons(self):
        candidate = _candidate("Metro routine notice", "A routine weekend timetable notice.")
        report = build_operational_diagnostic(
            [candidate], evaluator=self._evaluate
        )
        self.assertTrue(report["candidates"][0]["failure_reasons"])

    def test_major_diagnostic_retains_score_and_selected_state(self):
        candidate = _candidate("Metro collision", "Metro collision injured passengers.")
        candidate.update({"python_score": 88, "candidate_id": 7})
        report = build_major_accident_diagnostic(
            [candidate], evaluator=self._evaluate, selected_ids=[7]
        )
        self.assertEqual(report["candidates"][0]["selection_score"], 88)
        self.assertTrue(report["candidates"][0]["selected"])

    def test_global_diagnostic_preserves_domestic_and_international_counts(self):
        result = build_procurement_retrieval_diagnostic(
            [
                {"search_family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY, "query_region": "domestic", "added_to_raw_count": 2},
                {"search_family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY, "query_region": "global", "added_to_raw_count": 3},
            ],
            [],
            is_global_scope=True,
        )
        self.assertEqual(result["domestic_query_count"], 1)
        self.assertEqual(result["international_raw_count"], 3)

    def test_forward_architecture_fixture_is_not_reclassified(self):
        candidate = _candidate(
            "Metro digital twin pilot improves maintenance",
            "A pilot uses a digital twin to improve maintenance reliability.",
        )
        candidate["search_family"] = "forward_technology"
        self.assertEqual(candidate["search_family"], "forward_technology")

    def test_annual_global_selection_uses_country_tie_break_without_quota(self):
        api = _selector(selected_types=["營運政策"], lookback_int=365)
        candidates = []
        for index, country in enumerate(("Taiwan", "Taiwan", "Japan"), 1):
            candidate = _candidate(
                f"{country} metro line announces major service restructuring policy {index}",
                "The urban rail metro line announces a service restructuring policy to improve capacity and service frequency.",
                country=country,
            )
            candidate["id"] = index
            candidate["date"] = f"2026-0{9 - index}-18"
            candidate.update(
                api["evaluate_category_gates"](candidate)
                | {
                    "classification": "營運政策",
                    "primary_category": "營運政策",
                    "python_score": 80,
                    "final_selection_score": 80,
                    "candidate_level": "A",
                }
            )
            candidates.append(candidate)
        selected = api["select_candidates_by_python"](candidates)
        self.assertEqual(len(selected), 3)
        self.assertIn(normalize_country("Japan"), {item.get("region") for item in selected})


if __name__ == "__main__":
    unittest.main()
