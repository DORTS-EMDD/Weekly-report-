import datetime
import inspect
import unittest

import article_selector
from article_processor import _prefetch_candidate_article


FIXED_DATE = datetime.date(2026, 8, 31)


def _selector():
    return article_selector.build_selector_api(
        selected_types=["重大事故", "技術新知"],
        active_regions=[],
        lookback_days=365,
        lookback_int=365,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=FIXED_DATE,
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(title: str, snippet: str, *, country: str = "德國") -> dict:
    url = "https://example.com/news/v55c"
    return {
        "id": "v55c",
        "candidate_id": "v55c",
        "title": title,
        "snippet": snippet,
        "source": "Rail News",
        "source_display": "Rail News",
        "source_domain": "example.com",
        "source_href": url,
        "url": url,
        "date": "2026-08-28",
        "region": country,
        "country": country,
        "query_region": "global",
        "search_family": "major_accident",
        "source_tier": "B_professional",
        "source_quality": "B",
        "page_type": "news_article",
    }


class _Response:
    status_code = 200
    headers = {"Content-Type": "text/html; charset=utf-8"}

    def __init__(self, text: str, url: str):
        self.text = text
        self.url = url


class _Session:
    def __init__(self, text: str):
        self.text = text

    def get(self, url, **_kwargs):
        return _Response(self.text, url)


def _html(title: str, body: str) -> str:
    return f"<html><head><title>{title}</title></head><body><p>{body}</p></body></html>"


class V55CMajorAccidentTests(unittest.TestCase):
    def test_german_entgleisung_satisfies_severity_evidence(self):
        candidate = _candidate(
            "Tram-Unfall nach Entgleisung",
            "A Schwerer Tram-Unfall occurred after Entgleisung in Berlin.",
        )
        self.assertTrue(_selector()["_passes_major_accident_gate"](candidate))

    def test_german_verletzte_satisfies_injury_severity_evidence(self):
        candidate = _candidate(
            "Tram-Unfall mit 20 Verletzte",
            "A Schwerer Tram-Unfall occurred; 20 Verletzte were reported.",
        )
        self.assertTrue(_selector()["_passes_major_accident_gate"](candidate))

    def test_complete_berlin_tram_case_passes_major_accident_gate(self):
        candidate = _candidate(
            "Schwerer Tram-Unfall in Alt-Hohenschönhausen: 20 Verletzte nach Entgleisung",
            "Schwerer Tram-Unfall in Alt-Hohenschönhausen: 20 Verletzte nach Entgleisung.",
        )
        api = _selector()
        self.assertTrue(api["_passes_major_accident_gate"](candidate))
        self.assertEqual(api["evaluate_category_gates"](candidate)["category_gates"]["major_accident"], True)

    def test_german_accident_requires_urban_rail_context(self):
        candidate = _candidate(
            "Schwerer Unfall: 20 Verletzte nach Entgleisung",
            "Schwerer Unfall with 20 Verletzte nach Entgleisung was reported.",
            country="德國",
        )
        self.assertFalse(_selector()["_passes_major_accident_gate"](candidate))

    def test_german_severity_without_occurred_event_is_rejected(self):
        candidate = _candidate(
            "Tram safety research on Entgleisung und Verletzte",
            "An academic research study discusses hypothetical Entgleisung and Verletzte scenarios for tram evacuation.",
        )
        self.assertFalse(_selector()["_passes_major_accident_gate"](candidate))

    def test_sciencedirect_research_non_event_remains_rejected(self):
        candidate = _candidate(
            "Metro evacuation and fire hazard assessment",
            "A research study evaluates evacuation methodology for hypothetical tram collision scenarios.",
            country="美國",
        )
        candidate["source"] = "ScienceDirect"
        self.assertFalse(_selector()["_passes_major_accident_gate"](candidate))

    def test_missing_tram_collision_metadata_remains_rejected(self):
        candidate = _candidate(
            "Metro evacuation research evidence review",
            "Missing: tram collision. Fire hazards and evacuation assessment are discussed.",
            country="美國",
        )
        self.assertFalse(_selector()["_passes_major_accident_gate"](candidate))

    def test_existing_english_genuine_accidents_remain_valid(self):
        api = _selector()
        cases = (
            (
                "Tram collision injures passengers",
                "Two urban rail trams collided and passengers were injured.",
            ),
            (
                "Metro train fire injures passengers",
                "A train fire broke out and eight passengers were injured during evacuation.",
            ),
            (
                "Metro train derailment evacuates passengers",
                "A metro train derailed in the station and passengers were evacuated.",
            ),
            (
                "Metro incident causes emergency evacuation",
                "A train fire broke out and the station was evacuated after the incident.",
            ),
        )
        for title, snippet in cases:
            with self.subTest(title=title):
                self.assertTrue(api["_passes_major_accident_gate"](_candidate(title, snippet, country="日本")))

    def test_multilingual_severity_uses_canonical_owner(self):
        severity_terms = {term.casefold() for term in article_selector.MAJOR_ACCIDENT_SEVERITY_TERMS}
        self.assertIn("entgleisung", severity_terms)
        self.assertIn("verletzte", severity_terms)
        source = inspect.getsource(article_selector.build_selector_api)
        self.assertIn("MAJOR_ACCIDENT_SEVERITY_TERMS", source)

    def test_v55a_page_type_regression_remains_pass(self):
        api = _selector()
        root_only = _candidate("Google News root", "Metro accident", country="美國")
        root_only["url"] = "https://news.google.com/"
        root_only["source_href"] = "https://news.google.com/"
        article = _candidate("Metro train derailment", "A metro train derailed and passengers evacuated.", country="美國")
        self.assertNotEqual(api["_compute_candidate_page_type"](root_only)[0], "news_article")
        self.assertEqual(api["_compute_candidate_page_type"](article)[0], "news_article")

    def test_v55b_evidence_validity_guard_remains_intact(self):
        candidate = _candidate("Metro signalling contract awarded", "Original feed evidence")
        shell = (
            "Search results for metro. Search 0 results. Home menu navigation latest stories "
            "contact us privacy policy terms of use. "
        ) * 3
        result = _prefetch_candidate_article(candidate, _Session(_html("Generic page", shell)))
        self.assertEqual(result["status"], "failed_enrichment")
        self.assertTrue(result["transport_success"])
        self.assertFalse(result["evidence_valid"])
        self.assertEqual(candidate["snippet"], "Original feed evidence")


if __name__ == "__main__":
    unittest.main()
