import datetime
import unittest

import config
import ddgs_search_service
import search_queries
import streamlit_app
import streamlit_sidebar_ui

from test_streamlit_ui_modules import FakeStreamlit, _sidebar_context
from unittest.mock import patch


def _candidate(candidate_id, title, snippet, *, family="policy", tier="B_professional", score=85):
    url = f"https://railwaygazette.com/fixture/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-01",
        "source": "Railway Gazette Fixture",
        "source_display": "Railway Gazette Fixture",
        "source_domain": "railwaygazette.com",
        "source_tier": tier,
        "source_quality": "A",
        "url": url,
        "source_href": url,
        "search_family": family,
        "search_language": "en",
        "query": "metro subway urban rail",
        "region": "美國",
        "python_score": score,
        "candidate_flags": [],
    }


class V21OperationalTopicTests(unittest.TestCase):
    def test_sidebar_groups_operational_types_and_migrates_legacy_keys(self):
        recorder = FakeStreamlit(
            session_state={
                "selected_types_state": [],
                "type_營運政策": True,
                "type_營運爭議": False,
                "include_research_supplement": False,
            }
        )
        with patch.object(streamlit_sidebar_ui, "st", recorder):
            result = streamlit_sidebar_ui.render_sidebar(_sidebar_context())

        checkbox_keys = {
            call["kwargs"].get("key")
            for call in recorder.calls
            if call["name"] == "checkbox"
            and call["receiver"].startswith("expander")
        }
        self.assertEqual(
            checkbox_keys,
            {
                "type_技術新知",
                "type_重大事故",
                "type_營運動態",
                "type_規範更新",
                "include_research_supplement",
                "demo_cache_mode",
            },
        )
        self.assertEqual(
            {
                call["kwargs"].get("key")
                for call in recorder.calls
                if call["name"] == "checkbox"
                and call["kwargs"].get("key") == "show_developer_info"
                and call["receiver"] == "sidebar"
            },
            set(),
        )
        checkbox_labels = {
            call["args"][0]
            for call in recorder.calls
            if call["name"] == "checkbox"
            and call["receiver"].startswith("expander")
        }
        self.assertIn("營運動態", checkbox_labels)
        self.assertNotIn("營運議題", checkbox_labels)
        self.assertEqual(
            result.selected_types,
            ["營運政策", "營運爭議", "service_opening"],
        )
        self.assertTrue(recorder.session_state["type_營運政策"])
        self.assertTrue(recorder.session_state["type_營運爭議"])

    def test_research_supplement_period_rules(self):
        for days in (7, 14, 30, 90, 180, 365):
            self.assertTrue(config.research_supplement_allowed_for_report(days))
        for days in (0, 1, 31, 89, 91, 179, 181, 364, 366):
            self.assertFalse(config.research_supplement_allowed_for_report(days))
        for days in (7, 14, 30, 90):
            self.assertEqual(config.get_research_supplement_lookback_days(days), 90)
        self.assertEqual(config.get_research_supplement_lookback_days(180), 180)
        self.assertEqual(config.get_research_supplement_lookback_days(365), 365)

    def test_operational_query_families_are_multilingual_and_contextual(self):
        required_languages = {"en", "ja", "ko", "zh", "de", "fr", "es"}
        context_terms = {
            "en": ("metro", "subway", "mrt", "lrt", "tram", "urban rail", "light rail"),
            "de": ("u-bahn", "stadtbahn", "straßenbahn", "schienenverkehr"),
            "fr": ("métro", "tramway", "transport urbain", "rail"),
            "es": ("metro", "tranvía", "ferroviario", "tren urbano"),
            "it": ("metro", "metropolitana", "tram", "ferroviario"),
            "pt": ("metro", "metropolitana", "tram", "ferroviário"),
            "ru": ("метро", "трамвай", "рельсовый транспорт"),
            "ja": ("地下鉄", "メトロ", "路面電車", "都市鉄道"),
            "ko": ("지하철", "도시철도", "경전철", "트램"),
            "zh": ("地鐵", "地铁", "捷運", "mrt", "輕軌", "轻轨", "城市軌道"),
        }
        for family in ("policy", "dispute"):
            specs = [spec for spec in search_queries.SEARCH_QUERY_SPECS if spec["family"] == family]
            self.assertTrue(required_languages.issubset({spec["lang"] for spec in specs}))
            for spec in specs:
                query = spec["query"].casefold()
                self.assertTrue(
                    any(term.casefold() in query for term in context_terms[spec["lang"]]),
                    msg=f"missing urban rail context: {spec}",
                )

    def test_no_operational_selection_means_no_operational_query_family(self):
        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=["美國"],
            lookback_days=7,
            lookback_int=7,
            is_global_scope=True,
            today=datetime.date(2026, 8, 7),
            ddgs_client_factory=None,
        )
        ddgs_search_service.build_search_queries(context=context)
        families = {metadata.get("family") for metadata in context.query_metadata.values()}
        self.assertNotIn("policy", families)
        self.assertNotIn("dispute", families)

    def test_category_fixtures_cover_policy_dispute_and_technology_intent(self):
        policy = _candidate(
            1,
            "Metro fare reform approved after public policy review",
            "Government approved the fare adjustment and operating hours policy for the subway service.",
        )
        primary_dispute = _candidate(
            2,
            "Metro subway union strike disrupts service after contract dispute",
            "The operator and union dispute the contract and service is suspended during industrial action.",
            family="dispute",
        )
        secondary_dispute = _candidate(
            3,
            "Metro contract arbitration delays line construction",
            "Urban rail project schedule and service capacity are affected by the arbitration decision.",
            family="dispute",
        )
        generic_delay = _candidate(
            4,
            "Metro project delay affects construction schedule",
            "The urban rail project has a delay and a revised schedule.",
            family="dispute",
        )
        technology = _candidate(
            5,
            "Metro CBTC signalling upgrade enters service",
            "The subway train control system was commissioned after testing and integration.",
            family="technology",
        )
        weekend_notice = _candidate(
            6,
            "Metro weekend service notice for passengers",
            "A short weekend service advisory explains temporary schedule changes.",
        )

        policy_gate = streamlit_app.evaluate_category_gates(policy)
        primary_dispute_gate = streamlit_app.evaluate_category_gates(primary_dispute)
        secondary_dispute_gate = streamlit_app.evaluate_category_gates(secondary_dispute)
        generic_delay_gate = streamlit_app.evaluate_category_gates(generic_delay)
        technology_gate = streamlit_app.evaluate_category_gates(technology)

        self.assertEqual(policy_gate["primary_category"], "營運政策")
        self.assertEqual(primary_dispute_gate["primary_category"], "營運爭議")
        self.assertEqual(secondary_dispute_gate["primary_category"], "營運爭議")
        self.assertFalse(generic_delay_gate["category_gates"]["operational_dispute"])
        self.assertEqual(technology_gate["primary_category"], "技術新知")
        self.assertTrue(streamlit_app.hard_low_value_candidate_reason(weekend_notice))

    def test_selection_protects_operational_topic_coverage(self):
        candidates = [
            _candidate(
                1,
                "Metro CBTC signalling upgrade enters service",
                "The subway train control system was commissioned after testing and integration.",
                family="technology",
            ),
            _candidate(
                2,
                "Metro fare reform approved after public policy review",
                "Government approved the fare adjustment and operating hours policy for the subway service.",
            ),
        ]
        for candidate in candidates:
            candidate.update(streamlit_app.evaluate_category_gates(candidate))
            candidate.update({
                "resolved_region": candidate["region"],
                "country": candidate["region"],
                "core_systems": [],
                "category_resolution_method": "event_action_object_status",
                "canonical_event_id": f"event:fixture:{candidate['id']}",
                "authoritative_materialization_stage": "post_enrichment",
                "normalized_publication_date": candidate["date"],
                "date_validation": "valid_in_range",
                "recent_window_valid": True,
            })

        selected_types = list(streamlit_app.selected_types)
        streamlit_app.selected_types[:] = ["技術新知", "重大事故", "營運政策", "營運爭議"]
        try:
            selected = streamlit_app.select_candidates_by_python(candidates)
        finally:
            streamlit_app.selected_types[:] = selected_types
        self.assertTrue(
            any(item.get("classification") == "營運政策" for item in selected)
        )

    def test_debug_stats_include_operational_family_and_gate_details(self):
        policy = _candidate(1, "Metro fare reform approved", "Government approved fare adjustment for subway service.")
        dispute = _candidate(
            2,
            "Metro contract arbitration delays construction",
            "Urban rail schedule is affected by arbitration.",
            family="dispute",
        )
        for candidate in (policy, dispute):
            candidate.update(streamlit_app.evaluate_category_gates(candidate))
        original_summary = streamlit_app.LAST_DDGS_SEARCH_SUMMARY
        original_statuses = streamlit_app.LAST_DDGS_QUERY_STATUSES
        streamlit_app.LAST_DDGS_SEARCH_SUMMARY = {
            "query_count_by_family": {"policy": 4, "dispute": 5}
        }
        streamlit_app.LAST_DDGS_QUERY_STATUSES = []
        try:
            stats = streamlit_app.build_pipeline_debug_stats(
                [policy, dispute], [policy, dispute], [policy, dispute], []
            )
        finally:
            streamlit_app.LAST_DDGS_SEARCH_SUMMARY = original_summary
            streamlit_app.LAST_DDGS_QUERY_STATUSES = original_statuses
        self.assertEqual(stats["policy_query_count"], 4)
        self.assertEqual(stats["dispute_query_count"], 5)
        self.assertEqual(stats["policy_raw_candidate_count"], 1)
        self.assertEqual(stats["dispute_raw_candidate_count"], 1)
        self.assertEqual(stats["policy_gate_pass_count"], 1)
        self.assertEqual(stats["dispute_gate_pass_count"], 1)
        self.assertIn("policy_raw_candidates", stats)
        self.assertIn("dispute_raw_candidates", stats)
        self.assertIn("gate_failure_reason_stats", stats)


if __name__ == "__main__":
    unittest.main()
