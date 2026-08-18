import datetime
import unittest

import article_processor
from article_selector import build_selector_api
from config import ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY, SERVICE_OPENING_CATEGORY_KEY
from report_workflow_service import (
    WorkflowConfig,
    WorkflowDependencies,
    WorkflowRuntime,
)


FIXED_DATE = datetime.date(2026, 8, 18)
ALL_TYPES = ["技術新知", "重大事故", "營運政策", "營運爭議", "機電標案", SERVICE_OPENING_CATEGORY_KEY]


def _selector(selected_types=None):
    return build_selector_api(
        selected_types=selected_types or ALL_TYPES,
        active_regions=[],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=FIXED_DATE,
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(candidate_id, title, snippet, *, source_tier="B_professional"):
    url = f"https://example.com/news/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-10",
        "region": "未判定",
        "query_region": "global",
        "source": "Fixture Metro News",
        "source_display": "Fixture Metro News",
        "source_domain": "example.com",
        "source_href": url,
        "url": url,
        "source_tier": source_tier,
        "source_quality": "A",
        "page_type": "news_article",
        "search_family": "technology",
        "search_query": "fixture category gate",
        "search_language": "en",
    }


def _evaluate(api, candidate):
    candidate.update(api["evaluate_category_gates"](candidate))
    return candidate


class P2K3CategoryGoldenTests(unittest.TestCase):
    def test_a_gold_coast_signalling_is_technology(self):
        candidate = _evaluate(
            _selector(),
            _candidate(
                "A",
                "Gold Coast Light Rail deploys signalling and communications upgrade",
                "The light rail operator deploys a signalling and communications system upgrade.",
            ),
        )
        self.assertTrue(candidate["category_gates"]["technology"])
        self.assertEqual(candidate["primary_category"], "技術新知")

    def test_b_sanying_signal_fault_is_operational_dynamics(self):
        candidate = _evaluate(
            _selector(),
            _candidate(
                "B",
                "Sanying light rail signal fault forces manual operation",
                "A signalling fault forced manual operation and stopped service for about 20 minutes.",
            ),
        )
        self.assertTrue(candidate["technical_operation_incident"])
        self.assertTrue(candidate["category_gates"]["operational_policy"])
        self.assertEqual(candidate["operational_subtype"], "technical_operation_incident")

    def test_c_five_minute_minor_delay_is_not_incident(self):
        candidate = _evaluate(
            _selector(),
            _candidate("C", "Metro service delayed five minutes", "A minor delay lasted five minutes with normal service continuing."),
        )
        self.assertFalse(candidate["technical_operation_incident"])

    def test_d_major_collision_is_accident(self):
        candidate = _evaluate(
            _selector(),
            _candidate(
                "D",
                "Metro collision causes major disruption and service suspension",
                "Two metro trains collided, 25 people were injured, passengers were evacuated and service was suspended system-wide.",
            ),
        )
        self.assertTrue(candidate["category_gates"]["major_accident"])
        self.assertEqual(candidate["primary_category"], "重大事故")

    def test_e_small_passenger_incident_is_not_major(self):
        candidate = _evaluate(
            _selector(),
            _candidate("E", "Passenger incident at metro station", "One passenger had a minor medical incident and service continued normally."),
        )
        self.assertFalse(candidate["category_gates"]["major_accident"])

    def test_f_electricity_tariff_reform_is_policy(self):
        candidate = _evaluate(
            _selector(),
            _candidate(
                "F",
                "Seoul Metro electricity tariff reform affects railway operation",
                "The electricity tariff reform raises metro operating costs and includes a public service subsidy policy.",
            ),
        )
        self.assertTrue(candidate["category_gates"]["operational_policy"])

    def test_g_generic_national_electricity_policy_is_not_metro_policy(self):
        candidate = _evaluate(
            _selector(),
            _candidate("G", "National electricity tariff reform announced", "The national electricity tariff reform applies across the energy sector."),
        )
        self.assertFalse(candidate["category_gates"]["operational_policy"])

    def test_h_metro_protest_with_service_impact_is_dispute(self):
        candidate = _evaluate(
            _selector(),
            _candidate(
                "H",
                "Seoul Metro Line 4 protest disrupts morning commute",
                "Protesters demonstrated and caused commuter congestion and service disruption.",
            ),
        )
        self.assertTrue(candidate["category_gates"]["operational_dispute"])

    def test_i_political_protest_near_station_without_impact_is_not_dispute(self):
        candidate = _evaluate(
            _selector(),
            _candidate("I", "Political protest near metro station", "Demonstrators gathered near the station; transit operations were unaffected."),
        )
        self.assertFalse(candidate["category_gates"]["operational_dispute"])

    def test_j_tokyo_signalling_contract_is_procurement(self):
        candidate = _evaluate(
            _selector(),
            _candidate("J", "Tokyo Metro signalling contract", "Tokyo Metro signed a signalling contract for a new CBTC system."),
        )
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assertIn("signalling", candidate["procurement_systems"])

    def test_k_civil_tender_is_not_procurement(self):
        candidate = _evaluate(
            _selector(),
            _candidate("K", "Metro awards tunnel construction contract", "The civil construction tender covers tunnel works only."),
        )
        self.assertFalse(candidate["procurement_gate_pass"])

    def test_l_generic_electromechanical_turnkey_is_procurement_without_core_inference(self):
        candidate = _evaluate(
            _selector(),
            _candidate("L", "Metro awards integrated E&M package", "The urban rail authority awards an integrated E&M package for station systems."),
        )
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assertEqual(_selector()["_core_systems_for_candidate"](candidate), [])

    def test_m_cbtc_award_is_procurement_and_signalling(self):
        candidate = _evaluate(
            _selector(),
            _candidate("M", "Metro awards CBTC signalling contract", "The metro authority awarded a CBTC signalling contract."),
        )
        self.assertTrue(candidate["procurement_gate_pass"])
        self.assertIn("signalling", candidate["procurement_systems"])

    def test_n_commercial_opening_is_service_opening(self):
        candidate = _evaluate(
            _selector(),
            _candidate("N", "Metro Line 5 opens to passengers", "The urban rail extension opened to passengers and entered revenue service."),
        )
        self.assertTrue(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])

    def test_o_future_opening_is_not_formal_opening(self):
        candidate = _evaluate(
            _selector(),
            _candidate("O", "Metro Line 6 will open to passengers", "The planned line is scheduled to open next year."),
        )
        self.assertFalse(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])

    def test_p_enrichment_recomputes_procurement_gate(self):
        api = _selector()
        candidate = _candidate("P", "Metro project update", "An urban rail project update was announced.")
        _evaluate(api, candidate)
        before_failure_reasons = list(candidate["procurement_failure_reasons"])
        self.assertFalse(candidate["procurement_gate_pass"])
        candidate["snippet"] += " The metro authority awarded a CBTC signalling contract."
        article_processor._invalidate_candidate_selection_caches(candidate)
        after = _evaluate(api, candidate)
        self.assertTrue(after["procurement_gate_pass"])
        self.assertNotEqual(before_failure_reasons, after["procurement_failure_reasons"])

    def test_multilingual_signals_reach_non_technology_gates(self):
        api = _selector()
        cases = [
            ("韓文事故", "서울 지하철 신호 장애로 운행중단", "신호 장애로 지하철 운행이 중단되고 대피가 진행되었다.", "major_accident"),
            ("日文標案", "東京メトロ 信号 契約", "東京メトロが信号システムの契約を締結した。", ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY),
            ("韓文爭議", "서울 지하철 시위로 운행 영향", "시위대 시위로 승객 혼잡과 운행 영향이 발생했다.", "operational_dispute"),
        ]
        for candidate_id, title, snippet, gate_name in cases:
            candidate = _evaluate(api, _candidate(candidate_id, title, snippet))
            self.assertTrue(candidate["category_gates"].get(gate_name) or candidate.get("procurement_gate_pass"), candidate)


class P2K3MixedPoolTests(unittest.TestCase):
    def test_mixed_pool_is_not_all_technology_and_exposes_gate_debug(self):
        api = _selector()
        candidates = [
            _candidate("technology", "Metro deploys CBTC moving-block operation", "The metro deploys moving-block CBTC to increase capacity by 20%."),
            _candidate("accident", "Metro collision causes evacuation", "Two metro trains collided and passengers were evacuated after a major disruption."),
            _candidate("incident", "Metro signalling fault stops service", "A signalling fault forced manual operation and service suspension."),
            _candidate("policy", "Seoul Metro electricity tariff reform", "The electricity tariff reform changes metro operating cost policy."),
            _candidate("dispute", "Metro protest causes commuter congestion", "Protesters caused commuter congestion and service disruption."),
            _candidate("procurement", "Metro awards CBTC signalling contract", "The authority awarded a CBTC signalling contract."),
            _candidate("opening", "Metro line opens to passengers", "The line opened to passengers and entered revenue service."),
            _candidate("noise", "Metro weekend timetable reminder", "A routine weekend service advisory was published."),
            _candidate("bus", "EV bus service update", "The event concerns electric buses, not subway equipment."),
            _candidate("hsr", "High-speed rail fleet order", "The intercity high-speed train order is not urban rail."),
            _candidate("elevator", "Elevator near metro station", "An elevator service notice was issued."),
            _candidate("civil", "Metro tunnel construction tender", "The tender covers civil tunnel construction only."),
        ]
        evaluated = [_evaluate(api, candidate) for candidate in candidates]
        primary_categories = {candidate["primary_category"] for candidate in evaluated}
        self.assertIn("技術新知", primary_categories)
        self.assertIn("重大事故", primary_categories)
        self.assertIn("機電標案", primary_categories)
        self.assertGreater(len(primary_categories - {"技術新知", "excluded"}), 1)
        for candidate in evaluated:
            self.assertIn("major_accident_failure_reasons", candidate)
            self.assertIn("policy_gate_failure_reasons", candidate)
            self.assertIn("dispute_gate_failure_reasons", candidate)


class P2K3WorkflowEnrichmentDebugTests(unittest.TestCase):
    def test_prepare_candidate_pool_records_before_and_after_gate_snapshots(self):
        candidate = _candidate("workflow", "Metro project update", "An urban rail project update was announced.")
        candidate["date"] = "2026-08-11"
        config = WorkflowConfig(
            today=FIXED_DATE,
            lookback_days=7,
            selected_types=ALL_TYPES,
            active_regions=[],
            is_global_scope=True,
            standards_enabled=False,
            include_research_supplement=False,
            fast_mode_enabled=False,
            date_range="2026-08-11 to 2026-08-18",
            report_title="Fixture",
            report_scope_label="國際捷運",
            report_period_label="7 天",
        )
        runtime = WorkflowRuntime(
            config,
            WorkflowDependencies(
                prefetch_enabled=True,
                debug_stats_builder=lambda *args: {},
                http_session_factory=lambda: None,
            ),
        )
        runtime.parse_candidates = lambda _raw_rss, _raw_ddg: [dict(candidate)]

        def fake_prefetch(items):
            items[0]["prefetch_status"] = "success"
            items[0]["snippet"] += " The metro authority awarded a CBTC signalling contract."
            article_processor._invalidate_candidate_selection_caches(items[0])
            return {"limit": 1, "eligible_count": 1, "attempted_count": 1, "success_count": 1, "failed_count": 0}

        runtime.selector_api["prefetch_candidates_before_filter"] = fake_prefetch
        result = runtime.prepare_candidate_pool("", "")
        self.assertEqual(len(result["filtered_candidates"]), 1)
        enriched = result["filtered_candidates"][0]
        self.assertFalse(enriched["category_gate_before_enrichment"]["category_gates"][ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY])
        self.assertTrue(enriched["category_gate_after_enrichment"]["category_gates"][ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY])
        self.assertTrue(enriched["category_changed_after_enrichment"])
        self.assertIn("electromechanical_procurement", enriched["category_change_reason"])


if __name__ == "__main__":
    unittest.main()
