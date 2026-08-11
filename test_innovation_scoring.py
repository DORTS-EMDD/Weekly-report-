import datetime
import unittest

from article_selector import build_selector_api


def _selector_api():
    return build_selector_api(
        selected_types=["技術新知"],
        active_regions=["美國"],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 11),
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _score(api: dict, candidate_id: int, title: str, snippet: str, *, family: str = "") -> dict:
    candidate = {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-10",
        "region": "美國",
        "query_region": "美國",
        "source": "Fixture Source",
        "source_domain": "example.com",
        "source_href": f"https://example.com/{candidate_id}",
        "url": f"https://example.com/{candidate_id}",
        "source_tier": "B_professional",
        "source_quality": "A",
    }
    if family:
        candidate["search_family"] = family
    candidate.update(api["evaluate_category_gates"](candidate))
    return api["annotate_candidate_for_scheme_d"](candidate)


class InnovationScoringTests(unittest.TestCase):
    def test_innovation_score_is_separate_from_quality_score(self):
        api = _selector_api()
        ordinary = _score(
            api,
            1,
            "Metro upgrades Line X to CBTC",
            "The metro rail system upgrades Line X to CBTC signalling.",
        )
        capacity = _score(
            api,
            2,
            "Metro deploys CBTC moving-block operation, increasing line capacity by 20%",
            "The metro rail system deployed moving-block CBTC and increased line capacity by 20%.",
        )
        sic = _score(
            api,
            3,
            "New metro trains use SiC traction inverters reducing traction energy consumption by 15%",
            "The metro rail trains use silicon carbide traction inverters to reduce traction energy consumption by 15%.",
        )
        sensors = _score(
            api,
            4,
            "Pilot uses onboard sensors for continuous track condition monitoring, reducing manual inspection time by 40%",
            "A metro rail pilot uses onboard sensors for continuous track condition monitoring, reducing manual inspection time by 40%.",
        )

        self.assertEqual(ordinary["innovation_score"], 0)
        self.assertEqual(ordinary["innovation_level"], "B")
        self.assertEqual(ordinary["quality_score"], ordinary["python_score"])
        self.assertGreater(capacity["innovation_score"], ordinary["innovation_score"])
        self.assertGreater(sic["innovation_score"], ordinary["innovation_score"])
        self.assertGreater(sensors["innovation_score"], ordinary["innovation_score"])
        self.assertEqual(capacity["innovation_level"], "A")
        self.assertEqual(sic["innovation_level"], "A")
        self.assertEqual(sensors["innovation_level"], "A")
        self.assertIn("quantified_effect", capacity["innovation_signals"])
        self.assertIn("quantified_effect", sic["innovation_signals"])
        self.assertIn("quantified_effect", sensors["innovation_signals"])
        card = api["build_candidate_card"](sensors)
        for key in (
            "innovation_score",
            "innovation_signals",
            "innovation_level",
            "quality_score",
            "final_selection_score",
        ):
            self.assertIn(key, card)

    def test_generic_ai_and_marketing_words_do_not_score_as_innovation(self):
        api = _selector_api()
        ai_only = _score(
            api,
            1,
            "Metro introduces AI system",
            "The metro introduces an AI system.",
        )
        marketing = _score(
            api,
            2,
            "Innovative green smart metro project announced",
            "An innovative green smart metro project was announced.",
        )
        self.assertEqual(ai_only["innovation_score"], 0)
        self.assertEqual(marketing["innovation_score"], 0)
        self.assertEqual(ai_only["innovation_level"], "C")
        self.assertEqual(marketing["innovation_level"], "C")

    def test_project_only_gate_remains_before_innovation_scoring(self):
        api = _selector_api()
        candidate = _score(
            api,
            1,
            "Company wins CBTC contract for Metro Line X",
            "The company won the CBTC contract for Metro Line X.",
        )
        self.assertFalse(candidate["category_gates"]["technology"])
        self.assertEqual(candidate["primary_category"], "excluded")
        self.assertEqual(candidate["innovation_score"], 0)
        self.assertEqual(candidate["final_selection_score"], candidate["python_score"])

    def test_technical_innovation_moves_ahead_of_mature_update(self):
        api = _selector_api()
        candidates = [
            _score(api, 1, "Metro upgrades Line X to CBTC", "The metro rail system upgrades Line X to CBTC signalling."),
            _score(api, 2, "New metro trains use SiC traction inverters reducing traction energy consumption by 15%", "The metro rail trains use silicon carbide traction inverters to reduce traction energy consumption by 15%."),
            _score(api, 3, "Pilot uses onboard sensors for continuous track condition monitoring, reducing manual inspection time by 40%", "A metro rail pilot uses onboard sensors for continuous track condition monitoring, reducing manual inspection time by 40%."),
            _score(api, 4, "Metro introduces AI system", "The metro introduces an AI system."),
        ]
        ordered = sorted(candidates, key=api["_python_selection_sort_key"])
        positions = {item["title"]: index for index, item in enumerate(ordered)}
        self.assertLess(positions[candidates[1]["title"]], positions[candidates[0]["title"]])
        self.assertLess(positions[candidates[2]["title"]], positions[candidates[0]["title"]])
        self.assertGreater(positions[candidates[3]["title"]], positions[candidates[0]["title"]])

    def test_unknown_forward_technology_uses_evidence_based_innovation_score(self):
        api = _selector_api()
        cases = (
            (
                "Metro pilots newly developed lightweight material",
                "A metro operator pilots a newly developed lightweight material on rail vehicles, reducing vehicle weight by 12% and traction energy consumption by 8%.",
            ),
            (
                "Metro field-tests new low-friction coating",
                "A subway operator field-tests a new low-friction coating on rail components, reducing wear by 30%.",
            ),
            (
                "Metro validates new sensing method",
                "An urban metro validates a new sensing method for tunnel equipment, reducing manual inspection time by 40%.",
            ),
        )

        for index, (title, snippet) in enumerate(cases, 1):
            candidate = _score(api, index, title, snippet, family="forward_technology")
            self.assertTrue(candidate["passes_forward_technology_gate"], msg=title)
            self.assertGreaterEqual(candidate["innovation_score"], 15, msg=title)
            self.assertEqual(candidate["innovation_level"], "A", msg=title)
            self.assertTrue(candidate["novelty_evidence"], msg=title)
            self.assertTrue(candidate["validation_evidence"], msg=title)
            self.assertTrue(candidate["benefit_evidence"], msg=title)
            self.assertTrue(candidate["quantified_benefit"], msg=title)
            self.assertGreater(candidate["forward_evidence_bonus"], 0, msg=title)

    def test_forward_family_alone_does_not_create_innovation_score(self):
        api = _selector_api()
        cases = (
            ("Metro introduces AI system", "The metro introduces an AI system."),
            ("Innovative green smart metro project announced", "An operator announced an innovative green smart metro technology."),
        )

        for index, (title, snippet) in enumerate(cases, 20):
            candidate = _score(api, index, title, snippet, family="forward_technology")
            self.assertEqual(candidate["innovation_score"], 0, msg=title)
            self.assertEqual(candidate["forward_evidence_bonus"], 0, msg=title)

    def test_quantified_benefit_requires_associated_benefit_language(self):
        api = _selector_api()
        self.assertTrue(
            api["_has_quantified_benefit_evidence"](
                "The pilot reduces traction energy consumption by 15%.",
                ["reduces traction energy consumption"],
            )
        )
        self.assertFalse(
            api["_has_quantified_benefit_evidence"](
                "The pilot reduces traction energy consumption. It covers 20 trains, 5 stations and a 2026 delivery.",
                ["reduces traction energy consumption"],
            )
        )

    def test_forward_evidence_keeps_valuable_candidates_ahead_of_generic_items(self):
        api = _selector_api()
        candidates = [
            _score(api, 30, "A generic AI project", "The metro introduces an AI system.", family="forward_technology"),
            _score(api, 31, "B new lightweight material", "A metro operator pilots a newly developed lightweight material on rail vehicles, reducing vehicle weight by 12%.", family="forward_technology"),
            _score(api, 32, "C new low-friction coating", "A subway operator field-tests a new low-friction coating on rail components, reducing wear by 30%.", family="forward_technology"),
            _score(api, 33, "D new sensing method", "An urban metro validates a new sensing method for tunnel equipment, reducing manual inspection time by 40%.", family="forward_technology"),
            _score(api, 34, "E moving block capacity", "A metro deploys moving-block operation, increasing line capacity by 20%.", family="forward_technology"),
            _score(api, 35, "F marketing announcement", "An innovative green smart metro technology was announced.", family="forward_technology"),
        ]
        ordered = sorted(candidates, key=api["_python_selection_sort_key"])
        positions = {item["title"][0]: index for index, item in enumerate(ordered)}
        for valuable in "BCDE":
            for generic in "AF":
                self.assertLess(positions[valuable], positions[generic])


if __name__ == "__main__":
    unittest.main()
