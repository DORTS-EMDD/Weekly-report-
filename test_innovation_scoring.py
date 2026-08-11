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


def _score(api: dict, candidate_id: int, title: str, snippet: str) -> dict:
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


if __name__ == "__main__":
    unittest.main()
