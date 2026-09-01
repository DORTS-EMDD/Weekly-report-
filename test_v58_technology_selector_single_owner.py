import datetime
import unittest

from article_selector import build_selector_api


TECHNOLOGY = "技術新知"


def _api():
    return build_selector_api(
        selected_types=[TECHNOLOGY, "營運政策", "機電標案"],
        active_regions=[],
        lookback_days=30,
        lookback_int=30,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 8, 31),
        news_scope="international",
        _search_family_from_query=lambda _query: "technology",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(**overrides):
    url = "https://railway-news.com/news/2026/08/20/v58-fixture"
    candidate = {
        "id": "v58",
        "candidate_id": "v58",
        "title": "Metro signalling technology deployment",
        "snippet": "The metro deployed a signalling system upgrade on the urban rail network.",
        "date": "2026-08-20",
        "region": "國際",
        "resolved_region": "國際",
        "source": "Railway-News",
        "source_display": "Railway-News",
        "source_domain": "railway-news.com",
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "page_type": "news_article",
        "search_family": "technology",
        "search_query": "metro technology",
        "search_language": "en",
        "category_gates": {"technology": True},
        "primary_category": TECHNOLOGY,
        "classification": TECHNOLOGY,
    }
    candidate.update(overrides)
    return candidate


class V58TechnologySelectorSingleOwnerTests(unittest.TestCase):
    def test_selector_technology_is_canonical_mirror_only(self):
        api = _api()
        candidate = _candidate(
            category_gates={"technology": False},
            primary_category="機電標案",
            classification="機電標案",
            selector_strict_technical=True,
            selector_forward_gate_pass=True,
        )

        api["materialize_selector_quality"](candidate)

        self.assertFalse(candidate["selector_technology_gate_pass"])
        self.assertFalse(candidate["selector_forward_gate_pass"])
        self.assertFalse(candidate["selector_strict_technical"])
        self.assertFalse(api["_is_technical_news_selection_candidate"](candidate))

    def test_primary_category_dominance_blocks_technology_admission(self):
        api = _api()
        candidate = _candidate(
            category_gates={"technology": True, "service_opening": True},
            primary_category="營運政策",
            classification="營運政策",
        )

        api["materialize_selector_quality"](candidate)

        self.assertFalse(candidate["selector_technology_gate_pass"])
        self.assertFalse(candidate["selector_strict_technical"])

    def test_canonical_technology_candidate_remains_eligible(self):
        api = _api()
        candidate = _candidate()

        api["materialize_selector_quality"](candidate)

        self.assertTrue(candidate["selector_technology_gate_pass"])
        self.assertFalse(candidate["selector_forward_gate_pass"])
        self.assertTrue(candidate["selector_strict_technical"])
        self.assertTrue(api["_is_technical_news_selection_candidate"](candidate))

    def test_non_forward_candidate_never_gets_forward_selector_credit(self):
        api = _api()
        candidate = _candidate(
            category_gates={"technology": True},
            primary_category=TECHNOLOGY,
            search_family="technology",
        )

        api["materialize_selector_quality"](candidate)

        self.assertFalse(candidate["selector_forward_gate_pass"])


if __name__ == "__main__":
    unittest.main()
