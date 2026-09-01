import datetime
import unittest

import article_selector
from article_selector import build_selector_api
from electromechanical_taxonomy import CORE_SYSTEM_LABELS, CORE_TO_PROCUREMENT_GROUP


TECHNICAL = "技術新知"
PROCUREMENT = "機電標案"


def _selector() -> dict:
    return build_selector_api(
        selected_types=[TECHNICAL, PROCUREMENT],
        active_regions=[],
        lookback_days=30,
        lookback_int=30,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 31),
        news_scope="international",
        _search_family_from_query=lambda _query: "procurement",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(title: str, snippet: str = "", *, source_domain: str = "railway-news.com") -> dict:
    url = f"https://{source_domain}/news/fixture"
    return {
        "id": 1,
        "candidate_id": 1,
        "title": title,
        "snippet": snippet or title,
        "date": "2026-08-20",
        "region": "未判定",
        "query_region": "global",
        "source": "Railway-News",
        "source_display": "Railway-News",
        "source_domain": source_domain,
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "page_type": "news_article",
        "search_family": "procurement",
        "news_scope": "international",
    }


def _evaluate(api: dict, candidate: dict) -> dict:
    candidate.update(api["evaluate_category_gates"](candidate))
    return candidate


class V57EMProcurementSingleOwnerTests(unittest.TestCase):
    def test_core_systems_are_authoritative_mirror_and_projection(self):
        api = _selector()
        candidate = _candidate(
            "CAF to Supply 15 Tram-Trains for Paris Region's T13 Line",
            "Ile-de-France Mobilites awarded CAF a contract for 15 tram-trains for the T13 line in the Paris region.",
        )
        core = api["_core_systems_for_candidate"](candidate)
        self.assertEqual(core, ["電聯車"])
        self.assertEqual(candidate["electromechanical_classification"], core)
        candidate["authoritative_materialization_stage"] = "category"
        candidate["core_systems"] = core
        gate = api["_compute_electromechanical_procurement_gate"](candidate)
        self.assertIn("rolling_stock", gate["procurement_systems"])
        self.assertIn("contract_award", gate["procurement_actions"])
        self.assertIn("procurement", gate["procurement_actions"])
        self.assertTrue(gate["procurement_gate_pass"])
        self.assertNotIn("non_core_equipment_only", gate["procurement_failure_reasons"])
        evaluated = _evaluate(api, candidate)
        self.assertEqual(evaluated["primary_category"], PROCUREMENT)

    def test_generic_urban_vehicle_concepts_require_vehicle_event_context(self):
        api = _selector()
        positive = [
            "New rolling stock supplied for metro line",
            "Metro orders 20 new trainsets",
            "Light rail vehicles awarded to the operator",
            "The authority replaces its tram-train fleet",
        ]
        for title in positive:
            with self.subTest(title=title):
                self.assertEqual(api["_core_systems_for_candidate"](_candidate(title)), ["電聯車"])
        for title in ("Metro train service update", "Tram service notice", "Generic vehicle fleet strategy"):
            with self.subTest(title=title):
                self.assertNotIn("電聯車", api["_core_systems_for_candidate"](_candidate(title)))

    def test_contextual_vertical_transport_and_hvac_are_canonical(self):
        api = _selector()
        cases = [
            ("MTA modernizes elevators at Crown Hts-Utica Av subway station", "垂直運輸設備"),
            ("Metro station escalator replacement contract", "垂直運輸設備"),
            ("Metro station HVAC upgrade", "通風空調系統"),
            ("Tunnel ventilation system modernization", "通風空調系統"),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                candidate = _candidate(title)
                core = api["_core_systems_for_candidate"](candidate)
                self.assertEqual(core, [expected])
                candidate["authoritative_materialization_stage"] = "category"
                candidate["core_systems"] = core
                gate = api["_compute_electromechanical_procurement_gate"](candidate)
                expected_group = "vertical_transport" if expected == "垂直運輸設備" else "ventilation_hvac"
                self.assertIn(expected_group, gate["procurement_systems"])
        for title in ("Office building elevator modernization", "Property HVAC upgrade"):
            with self.subTest(title=title):
                candidate = _candidate(title)
                self.assertEqual(api["_core_systems_for_candidate"](candidate), [])
                self.assertFalse(api["_compute_electromechanical_procurement_gate"](candidate)["procurement_gate_pass"])

    def test_routine_elevator_notice_is_not_procurement(self):
        api = _selector()
        candidate = _candidate(
            "Metro station elevator service notice",
            "Routine elevator outage information is published for passengers.",
        )
        self.assertEqual(api["_core_systems_for_candidate"](candidate), [])
        gate = api["_compute_electromechanical_procurement_gate"](candidate)
        self.assertFalse(gate["procurement_gate_pass"])

    def test_depot_location_is_not_depot_equipment(self):
        api = _selector()
        location = _candidate("New metro depot opens", "The depot opens near the metro line.")
        equipment = _candidate("Depot purchases wheel lathe", "The maintenance depot purchased a wheel lathe.")
        self.assertNotIn("機廠維修設備", api["_core_systems_for_candidate"](location))
        self.assertEqual(api["_core_systems_for_candidate"](equipment), ["機廠維修設備"])

    def test_generic_package_does_not_guess_specific_system(self):
        api = _selector()
        candidate = _candidate(
            "Metro electromechanical systems turnkey package awarded",
            "The package contains no vehicle, signalling, power, communications, AFC, vertical transport or HVAC specification.",
        )
        candidate["authoritative_materialization_stage"] = "category"
        candidate["core_systems"] = []
        gate = api["_compute_electromechanical_procurement_gate"](candidate)
        self.assertTrue(gate["procurement_generic_electromechanical_scope"])
        self.assertTrue(gate["procurement_gate_pass"])
        self.assertEqual(gate["procurement_systems"], [])

    def test_required_positive_procurement_matrix(self):
        api = _selector()
        cases = [
            ("CAF supplies tram-trains for Paris T13 line", "The authority awards a contract for 15 tram-trains.", "電聯車"),
            ("Metro tram train procurement", "The operator orders new tram train vehicles.", "電聯車"),
            ("Metro light rail vehicle award", "The authority awarded light rail vehicles.", "電聯車"),
            ("Metro LRV replacement", "The operator placed a replacement order for its LRV fleet.", "電聯車"),
            ("Metro train supply contract", "The operator receives new metro trains under a supply contract.", "電聯車"),
            ("Subway train order", "The authority orders subway trains.", "電聯車"),
            ("Metro rolling stock delivery", "Rolling stock was delivered to the metro operator under contract.", "電聯車"),
            ("Metro awards CBTC signalling contract", "The authority awarded a signalling contract.", "號誌"),
            ("Metro awards traction power contract", "The authority awarded traction power supply.", "供電"),
            ("Metro awards communications contract", "The authority awarded a communications system contract.", "通訊"),
            ("Metro awards AFC contract", "The authority awarded an automatic fare collection contract.", "自動收費"),
            ("Metro awards PSD contract", "The authority awarded platform screen doors.", "月臺門"),
            ("Metro depot wheel lathe purchase", "The metro depot purchased a wheel lathe.", "機廠維修設備"),
            ("Metro station elevator modernization contract", "The authority awarded a contract to modernize elevators at the subway station.", "垂直運輸設備"),
            ("Metro escalator replacement contract", "Escalators were replaced at the metro station under contract.", "垂直運輸設備"),
            ("Metro station ventilation contract", "The authority awarded a station ventilation contract.", "通風空調系統"),
            ("Tunnel ventilation contract", "The authority awarded a tunnel ventilation contract.", "通風空調系統"),
            ("Metro station smoke extraction contract", "The authority awarded a smoke extraction system contract.", "通風空調系統"),
        ]
        for title, snippet, expected_core in cases:
            with self.subTest(title=title):
                candidate = _candidate(title, snippet)
                self.assertEqual(api["_core_systems_for_candidate"](candidate), [expected_core])
                gate = api["_compute_electromechanical_procurement_gate"](candidate)
                self.assertTrue(gate["procurement_gate_pass"], gate)
                self.assertEqual(gate["procurement_systems"], [CORE_TO_PROCUREMENT_GROUP[expected_core]])

    def test_authoritative_empty_core_cannot_be_backfilled_from_projection(self):
        api = _selector()
        candidate = _candidate("Metro electromechanical package", "The package is a formal metro systems contract.")
        candidate.update({
            "authoritative_materialization_stage": "category",
            "core_systems": [],
            "electromechanical_classification": [],
            "procurement_systems": ["rolling_stock"],
        })
        self.assertEqual(api["_core_systems_for_candidate"](candidate), [])
        self.assertEqual(api["_compute_electromechanical_procurement_gate"](candidate)["procurement_systems"], [])

    def test_required_negative_scope_matrix(self):
        api = _selector()
        cases = [
            ("Tram service notice", "Routine tram service information."),
            ("Metro train service update", "The metro train service was delayed."),
            ("Generic fleet strategy", "A generic fleet strategy was announced."),
            ("Metro tunnel construction tender", "The tender covers civil tunnel construction only."),
            ("Metro station civil works tender", "The tender covers station structural works."),
            ("Property development contract", "The property development contract was awarded."),
            ("Office equipment procurement", "Office IT equipment was procured."),
            ("Station furniture procurement", "The station furniture contract was awarded."),
            ("Office building elevator modernization", "The office building elevator contract was awarded."),
            ("Property HVAC upgrade", "The property HVAC contract was awarded."),
            ("Metro station elevator service notice", "Routine elevator outage information was published."),
            ("Metro general engineering consultancy", "The general engineering consultant was appointed."),
            ("Metro route planning procurement", "The route planning study contract was awarded."),
            ("Metro operations contract", "The operating contract was awarded."),
            ("High-speed rail rolling stock order", "The intercity train fleet order was awarded."),
            ("New metro depot opens", "The depot opens near the metro line."),
        ]
        for title, snippet in cases:
            with self.subTest(title=title):
                candidate = _candidate(title, snippet)
                self.assertEqual(api["_core_systems_for_candidate"](candidate), [])
                self.assertFalse(api["_compute_electromechanical_procurement_gate"](candidate)["procurement_gate_pass"])

    def test_projection_map_covers_every_canonical_core(self):
        self.assertEqual(set(CORE_SYSTEM_LABELS), set(CORE_TO_PROCUREMENT_GROUP))
        self.assertEqual(len(CORE_TO_PROCUREMENT_GROUP), len(CORE_SYSTEM_LABELS))

    def test_selector_has_no_independent_formal_system_dictionary(self):
        self.assertFalse(hasattr(article_selector, "ELECTROMECHANICAL_PROCUREMENT_SYSTEM_TERMS"))


if __name__ == "__main__":
    unittest.main()
