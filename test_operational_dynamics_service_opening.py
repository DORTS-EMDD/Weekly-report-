import datetime
import unittest

import ddgs_search_service
import developer_debug_service
import search_queries
import article_selector
from article_selector import build_selector_api
from config import SERVICE_OPENING_CATEGORY_KEY


FIXED_DATE = datetime.date(2026, 8, 11)


def _selector(news_scope="international", selected_types=None):
    return build_selector_api(
        selected_types=selected_types or ["技術新知", "重大事故", "營運政策", "營運爭議"],
        active_regions=[],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=FIXED_DATE,
        news_scope=news_scope,
        _search_family_from_query=lambda _query: SERVICE_OPENING_CATEGORY_KEY,
        _search_language_from_query=lambda _query: "zh" if news_scope == "domestic" else "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(candidate_id, title, snippet, *, domain="railwaygazette.com", region="美國", family=SERVICE_OPENING_CATEGORY_KEY):
    url = f"https://{domain}/news/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-10",
        "region": region,
        "query_region": region,
        "source": "Railway Gazette Fixture",
        "source_display": "Railway Gazette Fixture",
        "source_domain": domain,
        "source_href": url,
        "url": url,
        "source_tier": "B_professional",
        "source_quality": "A",
        "page_type": "news_article",
        "search_family": family,
        "search_query": "metro urban rail passenger service",
        "search_language": "en",
    }


def _evaluated(api, candidate):
    candidate.update(api["evaluate_category_gates"](candidate))
    candidate.update(api["score_news_candidate"](candidate))
    candidate["classification"] = candidate.get("primary_category", "")
    return candidate


class ServiceOpeningGateTests(unittest.TestCase):
    def test_actual_international_opening_passes_and_exposes_subtype(self):
        api = _selector()
        candidate = _evaluated(
            api,
            _candidate(
                1,
                "Metro Line 5 opens to passengers",
                "The urban rail extension opened to passengers and entered revenue service.",
            ),
        )
        self.assertTrue(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assertEqual(candidate["primary_category"], "營運政策")
        self.assertEqual(candidate["operational_subtype"], SERVICE_OPENING_CATEGORY_KEY)
        self.assertTrue(candidate["service_opening_gate_pass"])
        self.assertIn("passenger_service_started", candidate["service_opening_signals"])

    def test_actual_domestic_opening_passes(self):
        api = _selector("domestic")
        candidate = _evaluated(
            api,
            _candidate(
                2,
                "臺北捷運延伸段正式通車並開始載客",
                "臺北捷運新路段正式啟用，正式營運並開始載客服務。",
                domain="metro.gov.tw",
                region="臺北",
            ),
        )
        self.assertTrue(candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assertEqual(candidate["operational_subtype"], SERVICE_OPENING_CATEGORY_KEY)

    def test_future_planning_testing_and_non_urban_cases_fail(self):
        api = _selector()
        fixtures = [
            ("Metro extension will open to passengers next year", "The urban rail extension is scheduled to open in 2027."),
            ("Metro extension construction begins", "Groundbreaking and construction begin for the future urban rail line."),
            ("Feasibility study awarded for metro extension", "The feasibility study will assess a proposed urban rail route."),
            ("Metro line begins testing", "The urban rail line starts trial operation and train testing."),
            ("TRA railway line enters passenger service", "The conventional railway route entered revenue service."),
        ]
        for index, (title, snippet) in enumerate(fixtures, 10):
            candidate = _evaluated(api, _candidate(index, title, snippet))
            self.assertFalse(
                candidate["category_gates"][SERVICE_OPENING_CATEGORY_KEY],
                title,
            )

    def test_technology_priority_and_procurement_separation(self):
        api = _selector(selected_types=["技術新知", "營運政策"])
        technical = _evaluated(
            api,
            _candidate(
                20,
                "Metro line opens with moving-block CBTC",
                "The urban rail line opened to passengers with moving-block CBTC, increasing capacity by 20%.",
            ),
        )
        procurement = _evaluated(
            api,
            _candidate(
                21,
                "Metro awards signalling contract for future Line 5",
                "The urban rail authority awarded a contract for the planned signalling upgrade.",
            ),
        )
        self.assertTrue(technical["category_gates"][SERVICE_OPENING_CATEGORY_KEY])
        self.assertEqual(technical["primary_category"], "技術新知")
        self.assertFalse(procurement["category_gates"][SERVICE_OPENING_CATEGORY_KEY])

    def test_service_opening_query_family_is_small_and_contextual(self):
        international = ddgs_search_service.DdgsSearchContext(
            selected_types=["營運政策"], active_regions=[], lookback_days=7,
            lookback_int=7, is_global_scope=True, today=FIXED_DATE,
            ddgs_client_factory=None,
        )
        queries, _news_indices = ddgs_search_service.build_search_queries(context=international)
        service_queries = [
            query for query in queries
            if international.query_metadata[query].get("family") == SERVICE_OPENING_CATEGORY_KEY
        ]
        self.assertEqual(len(service_queries), 2)
        self.assertTrue(all("planning" not in query.casefold() for query in service_queries))

        domestic = ddgs_search_service.DdgsSearchContext(
            selected_types=["營運政策"], active_regions=[], lookback_days=7,
            lookback_int=7, is_global_scope=False, news_scope="domestic",
            today=FIXED_DATE, ddgs_client_factory=None,
        )
        domestic_queries, _news_indices = ddgs_search_service.build_search_queries(context=domestic)
        self.assertEqual(
            sum(
                domestic.query_metadata[query].get("family") == SERVICE_OPENING_CATEGORY_KEY
                for query in domestic_queries
            ),
            1,
        )

    def test_operational_dynamics_selection_and_debug_fields(self):
        api = _selector(selected_types=["營運政策", "營運爭議"])
        candidates = [
            _evaluated(
                api,
                _candidate(
                    index,
                    f"Metro Line {index} opens to passengers",
                    "The urban rail extension opened to passengers and entered revenue service.",
                ),
            )
            for index in range(30, 38)
        ]
        selected = api["select_candidates_by_python"](candidates)
        self.assertEqual(len(selected), len(candidates))
        self.assertTrue(all(item.get("operational_subtype") == SERVICE_OPENING_CATEGORY_KEY for item in selected))
        self.assertEqual(article_selector.LAST_PYTHON_SELECTION_DEBUG["service_opening_selected_count"], len(selected))
        rows = developer_debug_service._debug_candidate_rows(candidates[:1])
        for key in (
            "operational_subtype",
            "service_opening_gate_pass",
            "service_opening_signals",
            "service_opening_failure_reasons",
            "future_opening_signal",
        ):
            self.assertIn(key, rows[0])


if __name__ == "__main__":
    unittest.main()
