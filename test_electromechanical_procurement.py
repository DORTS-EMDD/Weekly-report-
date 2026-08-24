import datetime
import unittest

import ddgs_search_service
import developer_debug_service
from article_selector import build_selector_api
from config import (
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
)
from search_queries import (
    DOMESTIC_ELECTROMECHANICAL_PROCUREMENT_QUERY_SPECS,
    ELECTROMECHANICAL_PROCUREMENT_QUERY_SPECS,
    GLOBAL_REGIONAL_COVERAGE_QUERY_SPECS,
)


FIXED_DATE = datetime.date(2026, 8, 11)


def _selector(
    news_scope: str = "international",
    selected_types: list[str] | None = None,
) -> dict:
    return build_selector_api(
        selected_types=selected_types
        or ["技術新知", ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL],
        active_regions=[],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=FIXED_DATE,
        news_scope=news_scope,
        _search_family_from_query=lambda _query: ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
        _search_language_from_query=lambda _query: "zh" if news_scope == "domestic" else "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(
    candidate_id: int,
    title: str,
    snippet: str = "",
    *,
    source_domain: str = "example.com",
) -> dict:
    url = f"https://{source_domain}/news/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet or f"{title} The authority published the formal procurement decision.",
        "date": "2026-08-10",
        "region": "未判定",
        "query_region": "global",
        "source": "Fixture Metro News",
        "source_display": "Fixture Metro News",
        "source_domain": source_domain,
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "page_type": "news_article",
        "search_family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
        "search_query": "fixture procurement query",
        "search_language": "en",
    }


def _evaluate(api: dict, candidate: dict) -> dict:
    candidate.update(api["evaluate_category_gates"](candidate))
    return candidate


class ElectromechanicalProcurementPositiveFixtureTests(unittest.TestCase):
    def _assert_procurement_primary(self, candidate: dict, system: str) -> None:
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assertTrue(
            candidate["category_gates"][ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY]
        )
        self.assertEqual(
            candidate["primary_category"],
            ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
        )
        self.assertIn(system, candidate["procurement_systems"])
        self.assertTrue(candidate["procurement_actions"])

    def test_positive_international_signalling(self):
        candidate = _evaluate(
            _selector(),
            _candidate(1, "Metro authority awards CBTC signalling contract to Siemens."),
        )
        self._assert_procurement_primary(candidate, "signalling")
        self.assertFalse(candidate["category_gates"]["technology"])
        self.assertIn("urban_rail", candidate["procurement_signals"])
        self.assertIn("contract_award", candidate["procurement_actions"])

    def test_positive_international_power(self):
        candidate = _evaluate(
            _selector(),
            _candidate(2, "Operator awards traction power and substations contract for metro line."),
        )
        self._assert_procurement_primary(candidate, "traction_power")

    def test_positive_international_afc(self):
        candidate = _evaluate(
            _selector(),
            _candidate(3, "Metro selects supplier for new automatic fare collection system."),
        )
        self._assert_procurement_primary(candidate, "afc")

    def test_positive_rolling_stock(self):
        candidate = _evaluate(
            _selector(),
            _candidate(4, "Metro orders 30 new electric trainsets from manufacturer."),
        )
        self._assert_procurement_primary(candidate, "rolling_stock")
        self.assertFalse(candidate["category_gates"]["technology"])

    def test_positive_domestic_signalling(self):
        candidate = _evaluate(
            _selector("domestic"),
            _candidate(5, "臺北捷運號誌系統更新案完成決標"),
        )
        self._assert_procurement_primary(candidate, "signalling")
        self.assertEqual(candidate["procurement_domestic_system"], "臺北")

    def test_positive_domestic_power(self):
        candidate = _evaluate(
            _selector("domestic"),
            _candidate(6, "高雄捷運牽引供電系統標案完成決標"),
        )
        self._assert_procurement_primary(candidate, "traction_power")
        self.assertEqual(candidate["procurement_domestic_system"], "高雄")

    def test_positive_domestic_afc(self):
        candidate = _evaluate(
            _selector("domestic"),
            _candidate(7, "桃園捷運自動收費系統採購案公告決標"),
        )
        self._assert_procurement_primary(candidate, "afc")
        self.assertEqual(candidate["procurement_domestic_system"], "桃園")


class ElectromechanicalProcurementNegativeFixtureTests(unittest.TestCase):
    def _assert_rejected(self, candidate: dict, expected_reason: str) -> None:
        self.assertFalse(candidate["procurement_gate_pass"])
        self.assertFalse(
            candidate["category_gates"][ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY]
        )
        self.assertNotEqual(
            candidate["primary_category"],
            ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
        )
        self.assertTrue(
            any(
                reason == expected_reason or reason.startswith(expected_reason)
                for reason in candidate["procurement_failure_reasons"]
            ),
            msg=candidate["procurement_failure_reasons"],
        )

    def test_negative_civil_tunnel_contract(self):
        candidate = _evaluate(
            _selector(),
            _candidate(10, "Metro awards tunnel construction contract."),
        )
        self._assert_rejected(candidate, "civil_only")

    def test_negative_station_structural_contract(self):
        candidate = _evaluate(
            _selector(),
            _candidate(11, "Contract awarded for station structural works."),
        )
        self._assert_rejected(candidate, "civil_only")

    def test_negative_feasibility_study(self):
        candidate = _evaluate(
            _selector(),
            _candidate(12, "Feasibility study commissioned for new metro line."),
        )
        self._assert_rejected(candidate, "planning_or_consultancy_only")

    def test_negative_urban_redevelopment(self):
        candidate = _evaluate(
            _selector(),
            _candidate(13, "Urban redevelopment contract near metro station."),
        )
        self._assert_rejected(candidate, "electromechanical_system_missing")

    def test_negative_intercity_railway_signalling(self):
        candidate = _evaluate(
            _selector(),
            _candidate(14, "Railway signalling contract for national intercity railway."),
        )
        self._assert_rejected(candidate, "urban_rail_missing")

    def test_negative_domestic_taiwan_railways(self):
        candidate = _evaluate(
            _selector("domestic"),
            _candidate(15, "台鐵號誌改善標案"),
        )
        self._assert_rejected(candidate, "domestic_scope_excluded")

    def test_negative_domestic_high_speed_rail(self):
        candidate = _evaluate(
            _selector("domestic"),
            _candidate(16, "台灣高鐵供電系統採購"),
        )
        self._assert_rejected(candidate, "domestic_scope_excluded")

    def test_negative_domestic_civil_award(self):
        candidate = _evaluate(
            _selector("domestic"),
            _candidate(17, "臺北捷運新線土建工程決標"),
        )
        self._assert_rejected(candidate, "civil_only")

    def test_negative_domestic_route_feasibility_award(self):
        candidate = _evaluate(
            _selector("domestic"),
            _candidate(18, "臺中捷運路線可行性研究案決標"),
        )
        self._assert_rejected(candidate, "planning_or_consultancy_only")


class ElectromechanicalProcurementMixedPriorityTests(unittest.TestCase):
    def test_mixed_pure_cbtc_contract_is_procurement_only(self):
        candidate = _evaluate(
            _selector(),
            _candidate(20, "Metro awards CBTC contract."),
        )
        self.assertFalse(candidate["category_gates"]["technology"])
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assertEqual(
            candidate["primary_category"],
            ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
        )

    def test_mixed_moving_block_cbtc_contract_keeps_procurement_primary(self):
        candidate = _evaluate(
            _selector(),
            _candidate(
                21,
                "Metro awards moving-block CBTC contract that increases line capacity by 20%.",
            ),
        )
        self.assertTrue(candidate["category_gates"]["technology"])
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assertEqual(
            candidate["primary_category"],
            ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
        )
        self.assertIn("技術新知", candidate["alternative_category_flags"])

    def test_mixed_pure_train_order_is_procurement_only(self):
        candidate = _evaluate(
            _selector(),
            _candidate(22, "Metro orders 20 trains."),
        )
        self.assertFalse(candidate["category_gates"]["technology"])
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assertEqual(
            candidate["primary_category"],
            ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
        )

    def test_mixed_sic_train_order_keeps_procurement_primary(self):
        candidate = _evaluate(
            _selector(),
            _candidate(
                23,
                "Metro orders trains with SiC traction inverters reducing energy consumption by 15%.",
                "The metro rail trains use silicon carbide traction inverters, reducing traction energy consumption by 15%.",
            ),
        )
        self.assertTrue(candidate["category_gates"]["technology"])
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assertEqual(
            candidate["primary_category"],
            ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
        )
        self.assertIn("技術新知", candidate["alternative_category_flags"])

    def test_project_only_regression_stays_excluded_when_category_is_not_selected(self):
        candidate = _evaluate(
            _selector(selected_types=["技術新知"]),
            _candidate(24, "Metro authority awards CBTC signalling contract."),
        )
        self.assertFalse(candidate["category_gates"]["technology"])
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assertFalse(
            candidate["category_gates"][ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY]
        )
        self.assertEqual(candidate["primary_category"], "excluded")


class ElectromechanicalProcurementScopeQueryAndSelectionTests(unittest.TestCase):
    def _query_context(self, news_scope: str) -> ddgs_search_service.DdgsSearchContext:
        return ddgs_search_service.DdgsSearchContext(
            selected_types=[ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL],
            active_regions=[],
            lookback_days=7,
            lookback_int=7,
            is_global_scope=True,
            today=FIXED_DATE,
            ddgs_client_factory=None,
            news_scope=news_scope,
        )

    def test_international_query_family_has_five_grouped_queries(self):
        context = self._query_context("international")
        queries, _news_indices = ddgs_search_service.build_search_queries(context=context)
        self.assertEqual(len(ELECTROMECHANICAL_PROCUREMENT_QUERY_SPECS), 5)
        self.assertEqual(len(queries), 17)
        self.assertNotIn("臺灣", " ".join(queries))
        self.assertEqual(
            {context.query_metadata[query]["family"] for query in queries},
            {ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY, "technology"},
        )
        self.assertEqual(
            {context.query_metadata[query]["query_region"] for query in queries},
            {"global"} | {spec["region"] for spec in GLOBAL_REGIONAL_COVERAGE_QUERY_SPECS},
        )

    def test_domestic_query_family_has_two_grouped_queries(self):
        context = self._query_context("domestic")
        queries, _news_indices = ddgs_search_service.build_search_queries(context=context)
        self.assertEqual(len(DOMESTIC_ELECTROMECHANICAL_PROCUREMENT_QUERY_SPECS), 2)
        self.assertEqual(len(queries), 2)
        self.assertTrue(all("臺灣" in query for query in queries))
        self.assertEqual(
            {context.query_metadata[query]["family"] for query in queries},
            {ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY},
        )
        self.assertEqual(
            {context.query_metadata[query]["query_region"] for query in queries},
            {"domestic"},
        )

    def test_both_scope_combines_five_international_and_two_domestic_queries(self):
        context = self._query_context("both")
        queries, _news_indices = ddgs_search_service.build_search_queries(context=context)
        self.assertEqual(len(queries), 19)
        self.assertEqual(
            {context.query_metadata[query]["query_region"] for query in queries},
            {"global", "domestic"} | {spec["region"] for spec in GLOBAL_REGIONAL_COVERAGE_QUERY_SPECS},
        )

    def test_procurement_dispute_query_keeps_dispute_family(self):
        family = ddgs_search_service._search_family_from_query(
            "metro signalling contract dispute arbitration"
        )
        self.assertEqual(family, "dispute")

    def test_basic_metadata_failures_are_diagnostic(self):
        candidate = _candidate(30, "Metro awards CBTC contract.")
        candidate.update(
            {
                "date": "",
                "source_domain": "",
                "source_href": "",
                "url": "",
                "source_tier": "D_proxy_low_value",
                "source_quality": "D",
                "page_type": "index_or_search_page",
            }
        )
        candidate = _evaluate(_selector(), candidate)
        for expected in (
            "date_invalid_or_missing",
            "source_reference_missing",
            "source_quality_insufficient",
            "page_type_not_news_article",
        ):
            self.assertIn(expected, candidate["procurement_failure_reasons"])

    def test_selection_keeps_all_qualifying_procurement_items_without_cap(self):
        api = _selector(
            selected_types=[ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL]
        )
        fixtures = [
            "London Underground awards CBTC signalling contract.",
            "Paris Metro awards traction power substation contract.",
            "Madrid Metro selects supplier for automatic fare collection system.",
            "Singapore MRT orders 30 new metro trains.",
            "New York Subway awards platform screen doors contract.",
        ]
        candidates = []
        for index, title in enumerate(fixtures, 40):
            candidate = _evaluate(api, _candidate(index, title, source_domain=f"source{index}.com"))
            candidates.append(api["annotate_candidate_for_scheme_d"](candidate))
        selected = api["select_candidates_by_python"](candidates)
        self.assertEqual(len(selected), len(fixtures))
        self.assertTrue(
            all(
                item["classification"]
                == ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL
                for item in selected
            )
        )

    def test_developer_debug_exposes_procurement_reasons_and_signals(self):
        candidate = _evaluate(
            _selector(),
            _candidate(50, "Metro awards tunnel construction contract."),
        )
        rows = developer_debug_service._debug_candidate_rows([candidate])
        row = rows[0]
        for key in (
            "procurement_gate_pass",
            "procurement_signals",
            "procurement_failure_reasons",
            "procurement_systems",
            "procurement_actions",
            "search_family",
            "primary_category",
            "alternative_category_flags",
        ):
            self.assertIn(key, row)
        self.assertIn("civil_only", row["procurement_failure_reasons"])


if __name__ == "__main__":
    unittest.main()
