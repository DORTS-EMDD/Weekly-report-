import datetime
import json
import unittest
from unittest.mock import patch

import article_selector
import report_postprocessor
import streamlit_sidebar_ui

from test_streamlit_ui_modules import FakeStreamlit, _sidebar_context


def _selector(lookback=365, *, active_regions=None, is_global_scope=True):
    return article_selector.build_selector_api(
        selected_types=["技術新知"],
        active_regions=[] if active_regions is None else active_regions,
        lookback_days=lookback,
        lookback_int=lookback,
        fast_mode_enabled=False,
        is_global_scope=is_global_scope,
        today=datetime.date(2026, 8, 18),
        news_scope="both",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: object(),
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(identifier, title, snippet, date_value):
    url = f"https://fixture.example.test/news/{identifier}"
    return {
        "id": identifier,
        "candidate_id": identifier,
        "title": title,
        "snippet": snippet,
        "date": date_value,
        "region": "英國",
        "query_region": "全球",
        "source": "Fixture Rail News",
        "source_display": "Fixture Rail News",
        "source_domain": "fixture.example.test",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "search_family": "technology",
        "query": "metro urban rail technology",
        "search_query": "metro urban rail technology",
        "classification": "技術新知",
        "primary_category": "技術新知",
        "category_gates": {"technology": True},
        "python_score": 90,
        "final_selection_score": 90,
        "candidate_flags": ["technical_or_system_detail", "core_metro_technical_content"],
    }


class P2K52RuntimeTests(unittest.TestCase):
    def test_thermal_subway_energy_study_passes_narrow_technical_gate(self):
        api = _selector(7)
        candidate = _candidate(
            1,
            "New York to Study Thermal Energy Network for Cooler Subway Platforms",
            "MTA is studying a thermal energy network for subway platforms to reduce platform temperature and transfer excess heat.",
            "2026-08-11",
        )
        self.assertTrue(api["_passes_technical_triad"](candidate))

    def test_annual_rich_pool_keeps_twelve_quality_events(self):
        api = _selector()
        dates = (
            "2025-09-10", "2025-10-10", "2025-12-10", "2026-01-10",
            "2026-02-10", "2026-03-10", "2026-04-10", "2026-05-10",
            "2026-06-10", "2026-07-10", "2026-08-01", "2026-08-10",
        )
        candidates = [
            _candidate(
                index,
                f"Metro {index} CBTC modernization",
                "Urban rail metro CBTC modernization deploys system integration and improves reliability.",
                date_value,
            )
            for index, date_value in enumerate(dates, 1)
        ]
        selected = api["select_candidates_by_python"](candidates)
        self.assertEqual(len(selected), 12)
        self.assertEqual(article_selector.LAST_PYTHON_SELECTION_DEBUG["annual_shortfall"], 0)

    def test_annual_poor_pool_keeps_only_seven_and_reports_shortfall(self):
        api = _selector()
        candidates = [
            _candidate(
                index,
                f"Metro {index} CBTC modernization",
                "Urban rail metro CBTC modernization deploys system integration and improves reliability.",
                f"2026-0{index}-10",
            )
            for index in range(1, 8)
        ]
        selected = api["select_candidates_by_python"](candidates)
        debug = article_selector.LAST_PYTHON_SELECTION_DEBUG
        self.assertEqual(len(selected), 7)
        self.assertEqual(debug["annual_target"], 12)
        self.assertEqual(debug["annual_qualified_count"], 7)
        self.assertEqual(debug["annual_shortfall"], 5)
        self.assertTrue(debug["annual_backfill_triggered"])
        self.assertEqual(debug["annual_backfill_added_count"], 0)

    def test_annual_rescue_budget_reaches_each_quarter(self):
        api = _selector()
        candidates = []
        bucketed_dates = (
            ("2025-09-10", "2025-Q3"),
            ("2025-12-10", "2025-Q4"),
            ("2026-03-10", "2026-Q1"),
            ("2026-06-10", "2026-Q2"),
            ("2026-08-10", "2026-Q3"),
        )
        for index, (date_value, verified_bucket) in enumerate(
            bucketed_dates,
            1,
        ):
            candidate = _candidate(
                index,
                f"Metro {index} CBTC modernization",
                "Urban rail metro CBTC modernization",
                date_value,
            )
            candidate.update({
                "verified_bucket": verified_bucket,
                "date_verification_status": "verified",
                "normalized_publication_date": date_value,
                # The provisional materialization has no supported category;
                # enrichment is responsible for discovering the gate evidence.
                "primary_category": "excluded",
                "classification": "excluded",
                "category_gates": {"technology": False},
            })
            candidates.append(candidate)

        def enrich(candidate, _session):
            candidate["snippet"] += " deploys system integration and improves reliability."
            return {"status": "success", "chars": 120, "elapsed_seconds": 0.0, "reason": "fixture"}

        with patch.object(article_selector, "_prefetch_candidate_article", side_effect=enrich):
            stats = api["prefetch_candidates_before_filter"](candidates)
        self.assertEqual(
            set(stats["annual_rescue_attempted_by_bucket"]),
            {"2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"},
        )
        self.assertEqual(stats["annual_rescue_success_by_bucket"], stats["annual_rescue_attempted_by_bucket"])

    def test_annual_rescue_rechecks_gate_after_enrichment(self):
        api = _selector()
        candidate = _candidate(
            20,
            "Metro CBTC modernization",
            "Urban rail metro CBTC modernization",
            "2025-09-10",
        )
        candidate.update({
            "verified_bucket": "2025-Q3",
            "date_verification_status": "verified",
            "normalized_publication_date": "2025-09-10",
            "primary_category": "excluded",
            "classification": "excluded",
            "category_gates": {"technology": False},
        })

        def enrich(candidate, _session):
            candidate["snippet"] += " deploys system integration and improves reliability."
            return {"status": "success", "chars": 120, "elapsed_seconds": 0.0, "reason": "fixture"}

        with patch.object(article_selector, "_prefetch_candidate_article", side_effect=enrich):
            stats = api["prefetch_candidates_before_filter"]([candidate])
        self.assertEqual(stats["success_count"], 1)
        self.assertTrue(api["_passes_technical_triad"](candidate))

    def test_annual_thin_verified_candidate_enters_without_final_gate_evidence(self):
        api = _selector()
        candidate = _candidate(
            30,
            "Toronto NST system update",
            "Toronto urban rail",
            "2025-12-10",
        )
        candidate.update({
            "verified_bucket": "2025-Q4",
            "date_verification_status": "verified",
            "normalized_publication_date": "2025-12-10",
            "primary_category": "excluded",
            "classification": "excluded",
            "category_gates": {"technology": False},
        })
        self.assertTrue(api["_is_annual_quality_rescue_candidate"](candidate))
        self.assertTrue(api["_candidate_prefetch_signal"](candidate))

    def test_annual_hard_known_pages_do_not_consume_rescue_slots(self):
        api = _selector()
        fixtures = [
            (60, "Metro service status", "Metro service status and alerts", "/status"),
            (61, "Metro search results", "Search results for metro technology", "/search"),
            (62, "Metro route map", "Metro route map and station map", "/map"),
            (63, "Metro market analysis report", "Financial market analysis report", "/reports/market"),
            (64, "Metro open day promotion", "Open day promotion and game day travel information", "/events/open-day"),
        ]
        for identifier, title, snippet, path in fixtures:
            candidate = _candidate(identifier, title, snippet, "2026-04-10")
            candidate.update({
                "url": f"https://fixture.example.test{path}",
                "source_href": f"https://fixture.example.test{path}",
                "verified_bucket": "2026-Q2",
                "date_verification_status": "verified",
                "normalized_publication_date": "2026-04-10",
                "primary_category": "excluded",
                "classification": "excluded",
                "category_gates": {"technology": False},
            })
            with self.subTest(title=title):
                self.assertFalse(api["_is_annual_quality_rescue_candidate"](candidate))

    def test_annual_out_of_scope_resolved_region_does_not_consume_slot(self):
        api = _selector(active_regions=["英國"], is_global_scope=False)
        candidate = _candidate(
            65,
            "New York Metro braking failure during wet weather",
            "A genuine urban rail braking failure was reported during wet weather.",
            "2026-04-10",
        )
        candidate.update({
            "resolved_region": "美國",
            "verified_bucket": "2026-Q2",
            "date_verification_status": "verified",
            "normalized_publication_date": "2026-04-10",
            "primary_category": "excluded",
            "classification": "excluded",
            "category_gates": {"technology": False},
        })
        self.assertFalse(api["_annual_rescue_scope_eligible"](candidate))
        self.assertFalse(api["_is_annual_quality_rescue_candidate"](candidate))

    def test_annual_gate_failure_alone_does_not_disqualify_rescue(self):
        api = _selector()
        candidate = _candidate(
            66,
            "DLR wet-weather braking failure disrupts service",
            "London DLR reported a braking failure during wet weather and emergency checks.",
            "2026-04-10",
        )
        candidate.update({
            "verified_bucket": "2026-Q2",
            "date_verification_status": "verified",
            "normalized_publication_date": "2026-04-10",
            "primary_category": "技術新知",
            "classification": "技術新知",
            "category_gates": {"technology": False},
        })
        self.assertTrue(api["_is_annual_quality_rescue_candidate"](candidate))

    def test_annual_equal_score_prefers_event_evidence_over_retrieval_order(self):
        api = _selector()
        strong = _candidate(
            67,
            "Metro train collision injures passengers",
            "Two urban rail trains collided and passengers were evacuated.",
            "2026-04-10",
        )
        generic = _candidate(
            68,
            "Metro project update",
            "Urban rail metro project update was announced.",
            "2026-04-11",
        )
        for candidate in (strong, generic):
            candidate.update({
                "verified_bucket": "2026-Q2",
                "date_verification_status": "verified",
                "normalized_publication_date": candidate["date"],
                "primary_category": "excluded",
                "classification": "excluded",
                "category_gates": {"technology": False},
                "python_score": 35,
                "final_selection_score": 35,
                "candidate_flags": [],
            })
        attempted_ids = []

        def enrich(candidate, _session):
            attempted_ids.append(candidate["id"])
            return {"status": "success", "chars": 120, "elapsed_seconds": 0.0, "reason": "fixture"}

        with patch.object(article_selector, "_prefetch_candidate_article", side_effect=enrich):
            api["prefetch_candidates_before_filter"]([generic, strong])
        self.assertEqual(attempted_ids[:2], [67, 68])

    def _run_priority_scope_fixture(self, lookback):
        api = _selector(lookback)
        generic = _candidate(
            71,
            "Metro signalling modernization update",
            "Urban rail metro signalling system upgrade was announced.",
            "2026-04-10",
        )
        event = _candidate(
            72,
            "Metro train collision injures passengers",
            "Two urban rail trains collided and passengers were evacuated.",
            "2026-04-11",
        )
        for candidate in (generic, event):
            candidate.update({
                "verified_bucket": "2026-Q2",
                "date_verification_status": "verified",
                "normalized_publication_date": candidate["date"],
                "primary_category": "excluded",
                "classification": "excluded",
                "category_gates": {"technology": False},
                "candidate_flags": [],
            })
        generic.update({"python_score": 90, "final_selection_score": 90})
        event.update({"python_score": 35, "final_selection_score": 35})
        attempted_ids = []

        def enrich(candidate, _session):
            attempted_ids.append(candidate["id"])
            return {"status": "success", "chars": 120, "elapsed_seconds": 0.0, "reason": "fixture"}

        with patch.object(article_selector, "_prefetch_candidate_article", side_effect=enrich):
            stats = api["prefetch_candidates_before_filter"]([generic, event])
        return attempted_ids[:2], stats

    def test_7_day_rescue_priority_preserves_baseline_order(self):
        attempted_ids, _stats = self._run_priority_scope_fixture(7)
        self.assertEqual(attempted_ids, [71, 72])

    def test_30_day_rescue_priority_preserves_baseline_order(self):
        attempted_ids, _stats = self._run_priority_scope_fixture(30)
        self.assertEqual(attempted_ids, [71, 72])

    def test_365_day_rescue_priority_uses_annual_quality_order(self):
        attempted_ids, _stats = self._run_priority_scope_fixture(365)
        self.assertEqual(attempted_ids, [72, 71])

    def test_annual_priority_scope_isolated_from_weekly_monthly_lane(self):
        weekly_ids, _ = self._run_priority_scope_fixture(7)
        monthly_ids, _ = self._run_priority_scope_fixture(30)
        annual_ids, _ = self._run_priority_scope_fixture(365)
        self.assertEqual(weekly_ids, [71, 72])
        self.assertEqual(monthly_ids, [71, 72])
        self.assertEqual(annual_ids, [72, 71])

    def test_annual_bucket_ownership_precedes_score_with_q4_q1_q2_q3(self):
        api = _selector()
        fixtures = [
            (40, "2025-12-10", "2025-Q4"),
            (41, "2026-01-10", "2026-Q1"),
            (42, "2026-04-10", "2026-Q2"),
            (43, "2026-07-10", "2026-Q3"),
            (44, "2026-07-11", "2026-Q3"),
            (45, "2026-07-12", "2026-Q3"),
        ]
        candidates = []
        for identifier, date_value, verified_bucket in fixtures:
            candidate = _candidate(
                identifier,
                f"Metro {identifier} event update",
                "Urban rail metro",
                date_value,
            )
            candidate.update({
                "verified_bucket": verified_bucket,
                "date_verification_status": "verified",
                "normalized_publication_date": date_value,
                "primary_category": "excluded",
                "classification": "excluded",
                "category_gates": {"technology": False},
                # Make the crowded Q3 bucket score higher; score must not
                # erase the first opportunity for older represented buckets.
                "final_selection_score": (
                    101 - (identifier - 43) if verified_bucket == "2026-Q3" else 40
                ),
                "python_score": (
                    101 - (identifier - 43) if verified_bucket == "2026-Q3" else 40
                ),
            })
            candidates.append(candidate)

        attempted_ids = []

        def enrich(candidate, _session):
            attempted_ids.append(candidate["id"])
            return {"status": "success", "chars": 120, "elapsed_seconds": 0.0, "reason": "fixture"}

        with patch.object(article_selector, "_prefetch_candidate_article", side_effect=enrich):
            stats = api["prefetch_candidates_before_filter"](candidates)

        self.assertEqual(
            attempted_ids[:4],
            [40, 41, 42, 43],
        )
        self.assertEqual(
            set(stats["annual_rescue_attempted_by_bucket"]),
            {"2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"},
        )

    def test_annual_verified_low_value_notice_stays_out_of_rescue(self):
        api = _selector()
        candidate = _candidate(
            46,
            "Piccadilly line weekend timetable notice",
            "Piccadilly line weekend timetable",
            "2026-07-10",
        )
        candidate.update({
            "verified_bucket": "2026-Q3",
            "date_verification_status": "verified",
            "normalized_publication_date": "2026-07-10",
            "primary_category": "excluded",
            "classification": "excluded",
            "category_gates": {"technology": False},
        })
        self.assertFalse(api["_is_annual_quality_rescue_candidate"](candidate))

    def test_annual_case_families_can_enter_before_enrichment(self):
        api = _selector()
        cases = [
            (49, "Piccadilly line signalling renewal", "Piccadilly line urban rail"),
            (50, "Madrid Metro Line 6 renewal", "Madrid Metro Line 6 urban rail"),
            (51, "SMRT AI inspection trial", "Singapore MRT urban rail"),
            (52, "DLR regenerative braking study", "London DLR urban rail"),
        ]
        for identifier, title, snippet in cases:
            candidate = _candidate(identifier, title, snippet, "2026-04-10")
            candidate.update({
                "verified_bucket": "2026-Q2",
                "date_verification_status": "verified",
                "normalized_publication_date": "2026-04-10",
                "primary_category": "excluded",
                "classification": "excluded",
                "category_gates": {"technology": False},
            })
            with self.subTest(title=title):
                self.assertTrue(api["_is_annual_quality_rescue_candidate"](candidate))

    def test_annual_candidate_with_existing_category_evidence_skips_rescue(self):
        api = _selector()
        candidate = _candidate(
            53,
            "Metro CBTC modernization deployment",
            "Urban rail metro CBTC modernization deploys system integration and improves reliability.",
            "2026-04-10",
        )
        candidate.update({
            "verified_bucket": "2026-Q2",
            "date_verification_status": "verified",
            "normalized_publication_date": "2026-04-10",
        })
        self.assertFalse(api["_is_annual_quality_rescue_candidate"](candidate))

    def test_weak_annual_candidate_is_not_rescued(self):
        api = _selector()
        candidate = _candidate(
            21,
            "New depot project approved",
            "A project was approved for a new depot.",
            "2025-09-10",
        )
        self.assertFalse(api["_is_annual_quality_rescue_candidate"](candidate))
        self.assertFalse(api["_passes_technical_triad"](candidate))

    def test_generic_em_turnkey_does_not_infer_vehicle_from_project_progress(self):
        api = _selector(30)
        candidate = _candidate(
            1,
            "桃捷棕線機電系統統包工程決標",
            "桃園捷運棕線機電系統統包工程已決標，工程持續穩健推進。",
            "2026-07-29",
        )
        candidate["source_tier"] = "C_media"
        self.assertEqual(api["_core_systems_for_candidate"](candidate), [])

    def test_generic_em_with_signal_and_telecom_keeps_only_explicit_systems(self):
        api = _selector(30)
        candidate = _candidate(
            2,
            "Metro electromechanical turnkey package awarded",
            "The package includes signalling and telecommunications systems for the urban rail line.",
            "2026-07-29",
        )
        self.assertEqual(api["_core_systems_for_candidate"](candidate), ["號誌", "通訊"])

    def test_rolling_stock_procurement_keeps_vehicle_system(self):
        api = _selector(30)
        candidate = _candidate(
            3,
            "Metro rolling stock procurement awarded",
            "The metro procures rolling stock and trainsets for the new fleet.",
            "2026-07-29",
        )
        self.assertEqual(api["_core_systems_for_candidate"](candidate), ["電聯車"])

    def test_generic_em_fallback_is_empty_without_explicit_system(self):
        candidate = {
            "procurement_generic_electromechanical_scope": True,
            "core_systems": [],
            "procurement_systems": ["station_electromechanical"],
            "title": "Metro electromechanical turnkey package",
            "snippet": "The package covers station electromechanical works.",
        }
        self.assertEqual(report_postprocessor._fallback_electromechanical_system(candidate), "")

    def test_missing_authoritative_em_does_not_fallback_from_procurement_systems(self):
        candidate = {
            "procurement_generic_electromechanical_scope": False,
            "core_systems": [],
            "procurement_systems": ["signalling"],
            "title": "Metro signalling renewal",
            "snippet": "The signalling system will be renewed.",
        }
        # A7-T11: an explicit empty authoritative result is valid and must not
        # be replaced by procurement/title inference.
        self.assertEqual(report_postprocessor._fallback_electromechanical_system(candidate), "")

    def test_sidebar_settings_use_fragment_without_requesting_workflow(self):
        recorder = FakeStreamlit()
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(_sidebar_context())
        self.assertFalse(result.generate_requested)
        self.assertEqual([call["name"] for call in recorder.calls].count("button"), 4)
        self.assertFalse(any(call["name"] == "form" for call in recorder.calls))
        self.assertFalse(
            any(
                "🚀 產生捷運 AI" in json.dumps(call, ensure_ascii=False)
                for call in recorder.calls
            )
        )

        recorder = FakeStreamlit(
            responses={"🚀 產生捷運 AI 週報": True},
        )
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(_sidebar_context())
        self.assertFalse(result.generate_requested)


if __name__ == "__main__":
    unittest.main()
