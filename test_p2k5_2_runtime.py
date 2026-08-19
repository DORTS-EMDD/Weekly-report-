import datetime
import unittest
from unittest.mock import patch

import article_selector
import report_postprocessor
import streamlit_sidebar_ui

from test_streamlit_ui_modules import FakeStreamlit, _sidebar_context


def _selector(lookback=365):
    return article_selector.build_selector_api(
        selected_types=["技術新知"],
        active_regions=[],
        lookback_days=lookback,
        lookback_int=lookback,
        fast_mode_enabled=False,
        is_global_scope=True,
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
        for index, date_value in enumerate(
            ("2025-09-10", "2025-12-10", "2026-03-10", "2026-06-10", "2026-08-10"),
            1,
        ):
            candidates.append(
                _candidate(
                    index,
                    f"Metro {index} CBTC modernization",
                    "Urban rail metro CBTC modernization",
                    date_value,
                )
            )

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

        def enrich(candidate, _session):
            candidate["snippet"] += " deploys system integration and improves reliability."
            return {"status": "success", "chars": 120, "elapsed_seconds": 0.0, "reason": "fixture"}

        with patch.object(article_selector, "_prefetch_candidate_article", side_effect=enrich):
            stats = api["prefetch_candidates_before_filter"]([candidate])
        self.assertEqual(stats["success_count"], 1)
        self.assertTrue(api["_passes_technical_triad"](candidate))

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

    def test_explicit_em_fallback_keeps_supported_system_label(self):
        candidate = {
            "procurement_generic_electromechanical_scope": False,
            "core_systems": [],
            "procurement_systems": ["signalling"],
            "title": "Metro signalling renewal",
            "snippet": "The signalling system will be renewed.",
        }
        self.assertEqual(report_postprocessor._fallback_electromechanical_system(candidate), "號誌系統")

    def test_sidebar_settings_use_form_and_only_form_submit_requests_workflow(self):
        recorder = FakeStreamlit()
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(_sidebar_context())
        self.assertFalse(result.generate_requested)
        self.assertEqual([call["name"] for call in recorder.calls].count("button"), 0)
        self.assertEqual([call["name"] for call in recorder.calls].count("form_submit_button"), 5)
        self.assertTrue(any(call["name"] == "form" for call in recorder.calls))

        recorder = FakeStreamlit(
            responses={"🚀 產生捷運 AI 週報": True},
        )
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(_sidebar_context())
        self.assertTrue(result.generate_requested)


if __name__ == "__main__":
    unittest.main()
