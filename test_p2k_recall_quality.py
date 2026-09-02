import datetime
import unittest
from unittest.mock import patch

import article_selector
import ddgs_search_service
import report_postprocessor
import streamlit_app as app


def _selector(lookback=30):
    return article_selector.build_selector_api(
        selected_types=["技術新知", "營運政策", "機電標案"],
        active_regions=[],
        lookback_days=lookback,
        lookback_int=lookback,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 18),
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(candidate_id, title, snippet, *, family="technology", tier="B_professional", quality="A", core_systems=None):
    url = f"https://fixture.example.test/news/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-10",
        "region": "英國",
        "query_region": "全球",
        "source": "Fixture Rail News",
        "source_display": "Fixture Rail News",
        "source_domain": "fixture.example.test",
        "source_href": url,
        "url": url,
        "source_tier": tier,
        "source_quality": quality,
        "search_family": family,
        "query": "metro urban rail technology",
        "search_query": "metro urban rail technology",
        "core_systems": core_systems if core_systems is not None else [],
    }


class P2KRecallQualityTests(unittest.TestCase):
    def test_formal_core_system_whitelist_contains_canonical_labels(self):
        self.assertEqual(
            article_selector.CORE_SYSTEM_LABELS,
            ("電聯車", "號誌", "供電", "通訊", "自動收費", "機廠維修設備", "月臺門", "垂直運輸設備", "通風空調系統"),
        )

    def test_generic_electromechanical_package_does_not_infer_rolling_stock(self):
        api = _selector()
        candidate = _candidate(
            1,
            "Metro electromechanical systems turnkey package awarded",
            "The project award lists no vehicle, signalling, power, communications or AFC specification.",
        )
        self.assertEqual(api["_core_systems_for_candidate"](candidate), [])

    def test_generic_metro_train_service_does_not_infer_rolling_stock(self):
        api = _selector()
        candidate = _candidate(2, "Metro train service update", "The metro train service was delayed.")
        self.assertEqual(api["_core_systems_for_candidate"](candidate), [])

    def test_train_order_with_explicit_action_keeps_vehicle_system(self):
        api = _selector()
        candidate = _candidate(3, "Metro orders 20 new trains", "The metro ordered 20 new trains.")
        self.assertEqual(api["_core_systems_for_candidate"](candidate), ["電聯車"])

    def test_bus_event_is_not_rescued_by_metro_operator_name(self):
        api = _selector()
        candidate = _candidate(
            4,
            "EVバス Osaka Metro announces electric bus service",
            "Osaka Metro reports an EV bus operating incident; the event concerns buses, not subway equipment.",
        )
        self.assertFalse(api["_candidate_urban_rail_gate"](candidate))

    def test_technical_operation_incident_requires_major_impact(self):
        api = _selector()
        candidate = _candidate(
            5,
            "Metro signalling failure suspends service",
            "A signalling failure caused service suspension and degraded operation on the metro line.",
        )
        gates = api["evaluate_category_gates"](candidate)
        self.assertTrue(gates["technical_operation_incident"])
        self.assertEqual(gates["operational_subtype"], "technical_operation_incident")
        self.assertEqual(gates["primary_category"], "營運政策")

    def test_minor_equipment_delay_is_not_technical_operation_incident(self):
        api = _selector()
        candidate = _candidate(
            6,
            "Metro equipment fault causes minor delay",
            "A minor equipment fault caused a brief delay with normal service continuing.",
        )
        self.assertFalse(api["_passes_technical_operation_incident"](candidate))

    def test_short_high_value_candidate_enters_rescue(self):
        api = _selector()
        candidate = _candidate(
            7,
            "Metro tests new platform cooling system",
            "MTA subway platforms.",
            tier="C_media",
            quality="C",
        )
        self.assertTrue(api["_is_short_snippet_rescue_candidate"](candidate))
        self.assertTrue(api["_is_pre_gate_rescue_candidate"](candidate))

    def test_short_nonrail_candidate_does_not_enter_rescue(self):
        api = _selector()
        candidate = _candidate(
            8,
            "Airport tests new platform cooling system",
            "Airport terminal platform cooling pilot.",
            tier="C_media",
            quality="C",
        )
        self.assertFalse(api["_is_short_snippet_rescue_candidate"](candidate))

    def test_official_procurement_candidate_enters_rescue(self):
        api = _selector()
        candidate = _candidate(
            9,
            "Metro signalling contract awarded by transport authority",
            "The authority awarded a CBTC signalling contract.",
            tier="A_official",
        )
        candidate["source_domain"] = "transport.gov"
        self.assertTrue(api["_is_procurement_rescue_candidate"](candidate))

    def test_civil_procurement_candidate_does_not_enter_rescue(self):
        api = _selector()
        candidate = _candidate(
            10,
            "Metro depot construction contract awarded",
            "The civil construction contract covers a building and road works only.",
            tier="A_official",
        )
        candidate["source_domain"] = "transport.gov"
        self.assertFalse(api["_is_procurement_rescue_candidate"](candidate))

    def test_track_b_accepts_clear_media_evidence_after_quality_relaxation(self):
        api = _selector()
        candidate = _candidate(
            11,
            "Metro deploys predictive maintenance sensors",
            "An urban rail operator deploys predictive maintenance sensors to monitor equipment conditions and reduce failures.",
            family="forward_technology",
            tier="C_media",
            quality="C",
        )
        payload = api["evaluate_category_gates"](candidate)
        self.assertTrue(payload["track_b_gate_pass"])
        self.assertTrue(payload["passes_forward_technology_gate"])

    def test_track_b_rejects_generic_ai_investment(self):
        api = _selector()
        candidate = _candidate(
            12,
            "Company announces AI investment strategy",
            "The company will invest in an AI platform for smart cities without a metro deployment.",
            family="forward_technology",
        )
        payload = api["evaluate_category_gates"](candidate)
        self.assertFalse(payload["track_b_gate_pass"])

    def test_forward_fallback_specs_are_bounded_to_eight_queries(self):
        self.assertEqual(len(ddgs_search_service.FORWARD_TECHNOLOGY_FALLBACK_QUERY_SPECS), 8)

    def test_forward_zero_raw_triggers_constrained_second_layer(self):
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
                "href": "https://railwaygazette.com/fixture/p2k-forward",
                "date": "2026-08-17",
            }]

        context.forward_technology_query_count = 1
        with patch.object(ddgs_search_service, "service_execute_ddgs_query", side_effect=fake_execute):
            _, statuses, summary = ddgs_search_service.run_duckduckgo_searches(
                context=context,
                search_queries=["metro forward"],
                news_query_indices={1},
            )
        self.assertEqual(summary["forward_technology_query_count"], 1)
        self.assertEqual(summary["forward_technology_fallback_query_count"], 8)
        self.assertEqual(summary["forward_technology_primary_raw_count"], 0)
        self.assertEqual(summary["forward_technology_fallback_raw_count"], 8)
        self.assertEqual(summary["forward_technology_raw_count"], 8)
        self.assertTrue(any(row.get("fallback_layer") for row in statuses))

    def test_annual_bucket_metadata_covers_forward_and_selected_families(self):
        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知", "重大事故", "機電標案"],
            active_regions=[],
            lookback_days=365,
            lookback_int=365,
            is_global_scope=True,
            today=datetime.date(2026, 8, 18),
            ddgs_client_factory=None,
        )
        queries, _ = ddgs_search_service.build_search_queries(context=context, include_forward_technology=True)
        bucket_rows = [
            metadata for metadata in context.query_metadata.values()
            if metadata.get("date_bucket")
        ]
        self.assertGreater(len(bucket_rows), 0)
        for metadata in bucket_rows:
            self.assertIn("technology", metadata.get("annual_bucket_families", []))
            self.assertIn("forward_technology", metadata.get("annual_bucket_families", []))
        self.assertEqual(len(queries), len(context.query_metadata))

    def test_global_coverage_queries_include_core_markets(self):
        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=30,
            lookback_int=30,
            is_global_scope=True,
            today=datetime.date(2026, 8, 18),
            ddgs_client_factory=None,
        )
        ddgs_search_service.build_search_queries(context=context, include_forward_technology=True)
        regions = {
            metadata.get("query_region")
            for metadata in context.query_metadata.values()
            if metadata.get("query_region")
        }
        self.assertTrue({"日本", "韓國", "英國", "美國", "加拿大"}.issubset(regions))

    def test_authoritative_parser_accepts_blank_lines_for_all_fields(self):
        candidate = _candidate(14, "Metro CBTC upgrade", "CBTC upgrade improves train control.", core_systems=["號誌"])
        report = "\n".join([
            "## 一、技術新知",
            "<!-- candidate_id: 14 -->",
            "🔹 [技術新知] Metro CBTC upgrade",
            "• 發布/事件日期：2026-08-10",
            "",
            "• 國家：英國",
            "",
            "• 相關機電系統：號誌",
            "",
            "• 事件摘要:",
            "",
            "CBTC upgrade improves train control and service reliability.",
            "",
            "• 臺北捷運局啟示:",
            "",
            "可參考號誌切換與驗證安排。",
            "",
            "• 資料來源：Railway-News：https://railway-news.com/fixture/14",
        ])
        report = report_postprocessor.canonicalize_authoritative_source_fields(report, [candidate])
        validation = report_postprocessor.validate_authoritative_report(report, [candidate], selected_types=["技術新知"])
        self.assertTrue(validation["report_validation_passed"])
        self.assertEqual(validation["missing_model_fields"], {})

    def test_empty_core_systems_allows_omitted_formal_system_field(self):
        candidate = _candidate(15, "Metro cross-system analysis", "AI supports operational analysis for metro maintenance.", core_systems=[])
        report = "\n".join([
            "## 一、技術新知",
            "<!-- candidate_id: 15 -->",
            "🔹 [技術新知] Metro cross-system analysis",
            "• 發布/事件日期：2026-08-10",
            "• 國家：英國",
            "• 事件摘要：AI supports operational analysis for metro maintenance.",
            "• 臺北捷運局啟示：可參考跨系統資料應用。",
            "• 資料來源：https://fixture.example.test/news/15",
        ])
        report = report_postprocessor.canonicalize_authoritative_source_fields(report, [candidate])
        validation = report_postprocessor.validate_authoritative_report(report, [candidate], selected_types=["技術新知"])
        self.assertTrue(validation["report_validation_passed"])

    def test_existing_model_source_is_normalized_to_primary_candidate_source(self):
        candidate = _candidate(16, "Metro signalling upgrade", "CBTC upgrade improves reliability.", core_systems=["號誌"])
        candidate.update({
            "primary_category": "技術新知",
            "classification": "技術新知",
            "preliminary_type": "技術新知",
            "category_gates": {"technology": True},
            "category_resolution_method": "event_action_object_status",
            "resolved_region": "英國",
            "country": "英國",
            "canonical_event_id": "event:fixture:16",
            "authoritative_materialization_stage": "post_enrichment",
        })
        report = "\n".join([
            "<!-- candidate_id: 16 -->",
            "🔹 [技術新知] Metro signalling upgrade",
            "• 發布/事件日期：2026-08-10",
            "• 國家：英國",
            "• 相關機電系統：號誌",
            "• 事件摘要：CBTC upgrade improves reliability.",
            "• 臺北捷運局啟示：可參考號誌驗證作業。",
            "• 資料來源：[Railway-News](https://railway-news.com/fixture/16)",
        ])
        output, _ = app.reconcile_report_candidate_output(report, [candidate])
        self.assertIn("Fixture Rail News", output)
        self.assertNotIn("Railway-News", output)

    def test_core_system_empty_fallback_omits_formal_system_field(self):
        candidate = _candidate(17, "Metro cross-system maintenance", "Metro maintenance evidence supports cross-system analysis.", core_systems=[])
        candidate["summary_zh"] = "都市軌道維修資料支持跨系統分析。"
        candidate["taipei_insight"] = "可參考跨系統維修資料整合。"
        fallback = app._fallback_report_block(candidate)
        self.assertNotIn("相關機電系統", fallback)

    def test_quality_kpis_are_debug_only_candidate_fields(self):
        api = _selector()
        candidate = _candidate(
            18,
            "Metro pilots predictive maintenance sensors",
            "A metro operator pilots sensors for condition monitoring and reduces inspection time.",
            family="forward_technology",
        )
        annotated = api["annotate_candidate_for_scheme_d"](candidate)
        for key in ("technology_maturity", "event_importance", "evidence_strength", "innovation_type"):
            self.assertIn(key, annotated)

    def test_cross_period_debug_reports_monthly_coverage(self):
        api = _selector()
        monthly = [_candidate(19, "Monthly event", "Metro system update.")]
        annual_raw = [_candidate(19, "Monthly event", "Metro system update.")]
        debug = api["build_cross_period_coverage_debug"](monthly, annual_raw, annual_raw, [])
        self.assertEqual(debug["cross_period_coverage_ratio"], 1.0)
        self.assertEqual(debug["monthly_selected_missing_from_annual_raw"], [])

    def test_pipeline_debug_exposes_all_recall_stages(self):
        debug = app.build_pipeline_debug_stats([], [], [], [], {})
        self.assertEqual(
            set(("raw", "dedup", "filtered", "gate_pass", "rescue_candidate", "rescue_enriched", "selected", "model", "final")),
            set(debug["pipeline_stages"]),
        )
        self.assertIn("quality_acceptance", debug)

    def test_annual_selection_rebalances_when_multiple_quarters_exist(self):
        api = _selector(365)
        selected = []
        annual_pool = []
        for index, date_value in enumerate((
            "2026-08-10", "2026-08-01", "2026-07-15", "2026-04-10", "2026-03-10",
            "2026-02-10", "2025-12-10", "2025-10-10", "2025-08-20", "2025-08-01",
        ), 20):
            item = _candidate(index, f"Metro technical event {index}", "Metro system deployment improves reliability.")
            item["date"] = date_value
            item["classification"] = "技術新知"
            item["primary_category"] = "技術新知"
            item["final_selection_score"] = 75 - index % 4
            selected.append(item)
            annual_pool.append(item)
        result = api["rebalance_selected_candidates"](selected, annual_pool)
        quarters = {item["date"][:7][:4] + "-Q" + str((int(item["date"][5:7]) - 1) // 3 + 1) for item in result}
        self.assertGreaterEqual(len(quarters), 3)


if __name__ == "__main__":
    unittest.main()
