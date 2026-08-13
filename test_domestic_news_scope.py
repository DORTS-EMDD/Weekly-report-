import datetime
import unittest

import ddgs_search_service
from article_processor import _is_valid_news_url
from article_selector import build_selector_api


FIXED_DATE = datetime.date(2026, 8, 11)


def _selector(news_scope: str):
    return build_selector_api(
        selected_types=["技術新知", "重大事故", "營運政策", "營運爭議"],
        active_regions=[],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=FIXED_DATE,
        news_scope=news_scope,
        _search_family_from_query=lambda _query: "domestic_metro",
        _search_language_from_query=lambda _query: "zh",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )


def _candidate(candidate_id: int, title: str, snippet: str) -> dict:
    url = f"https://metro.gov.tw/news/{candidate_id}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-10",
        "region": "未判定",
        "query_region": "domestic",
        "source": "臺灣捷運官方新聞",
        "source_display": "臺灣捷運官方新聞",
        "source_domain": "metro.gov.tw",
        "source_href": url,
        "url": url,
        "source_tier": "A_official",
        "source_quality": "A",
        "search_family": "domestic_metro",
        "search_query": "臺灣 捷運",
        "search_language": "zh",
    }


class DomesticNewsScopeTests(unittest.TestCase):
    def _run_preliminary(self, candidate: dict, news_scope: str = "domestic"):
        api = _selector(news_scope)
        candidate.update(api["evaluate_category_gates"](candidate))
        return api["preliminary_filter_candidate"](candidate), candidate, api

    def test_domestic_technology_candidate_is_retained_in_both_scope(self):
        candidate = _candidate(
            1,
            "臺北捷運導入列車狀態監測系統",
            "臺北捷運導入列車狀態監測系統，透過即時資料監測車況並支援預測性維護，改善設備維修效率與營運可靠度。",
        )
        (keep, _reason), candidate, _api = self._run_preliminary(candidate, "both")
        self.assertTrue(keep)
        self.assertTrue(candidate["domestic_candidate"])
        self.assertEqual(candidate["domestic_system"], "臺北")
        self.assertEqual(candidate["region"], "臺北")
        self.assertTrue(candidate["category_gates"]["technology"])

    def test_domestic_ai_failure_prediction_is_retained(self):
        candidate = _candidate(
            2,
            "桃園捷運導入 AI 設備故障預測",
            "桃園捷運導入 AI 設備故障預測，使用設備資料提前辨識異常並支援智慧維修，降低故障處理時間。",
        )
        (keep, _reason), candidate, _api = self._run_preliminary(candidate)
        self.assertTrue(keep)
        self.assertEqual(candidate["domestic_system"], "桃園")
        self.assertEqual(candidate["region"], "桃園")
        self.assertTrue(candidate["category_gates"]["technology"])

    def test_domestic_major_accident_uses_existing_gate(self):
        candidate = _candidate(
            3,
            "高雄捷運列車發生碰撞並造成多人受傷",
            "高雄捷運列車發生碰撞，造成多人受傷並啟動安全調查，營運單位發布事故處置資訊。",
        )
        (keep, _reason), candidate, _api = self._run_preliminary(candidate)
        self.assertTrue(keep)
        self.assertEqual(candidate["region"], "高雄")
        self.assertTrue(candidate["category_gates"]["major_accident"])

    def test_domestic_policy_uses_existing_gate(self):
        candidate = _candidate(
            4,
            "臺中捷運發布重大營運制度調整",
            "臺中捷運發布重大營運制度調整，調整票務制度、班距與服務管理，並說明新的營運時間安排。",
        )
        (keep, _reason), candidate, _api = self._run_preliminary(candidate)
        self.assertTrue(keep)
        self.assertEqual(candidate["region"], "臺中")
        self.assertTrue(candidate["category_gates"]["operational_policy"])

    def test_domestic_scope_rejects_non_metro_content(self):
        fixtures = [
            "台鐵新列車投入營運",
            "台灣高鐵新增班次",
            "臺北市公車票價調整",
            "桃園機場旅客捷運提供航空旅遊服務",
            "臺北捷運周邊商場房地產開發",
            "臺北捷運新線可行性研究啟動",
            "桃園捷運工程土建標開標",
        ]
        for index, title in enumerate(fixtures, 10):
            candidate = _candidate(index, title, f"{title} 的相關內容與背景說明。")
            candidate["source"] = "一般交通新聞"
            candidate["source_display"] = "一般交通新聞"
            (keep, reason), _candidate_value, _api = self._run_preliminary(candidate)
            self.assertFalse(keep, msg=title)
            self.assertTrue(reason, msg=title)

    def test_airport_metro_technical_content_is_retained(self):
        candidate = _candidate(
            20,
            "桃園機場捷運列車導入新號誌設備",
            "桃園機場捷運列車導入新號誌設備並完成測試，提升列車控制與營運安全。",
        )
        (keep, _reason), candidate, _api = self._run_preliminary(candidate)
        self.assertTrue(keep)
        self.assertEqual(candidate["domestic_system"], "桃園")

    def test_international_scope_keeps_taiwan_excluded(self):
        candidate = _candidate(
            21,
            "臺北捷運導入列車狀態監測系統",
            "臺北捷運導入列車狀態監測系統，透過即時資料監測車況並支援預測性維護。",
        )
        (keep, reason), _candidate_value, _api = self._run_preliminary(candidate, "international")
        self.assertFalse(keep)
        self.assertIn(reason, {"範圍排除", "國內新聞排除"})

    def test_scope_url_safety_is_explicit(self):
        domestic_result = _is_valid_news_url(
            "https://metro.gov.tw/news/1",
            news_scope="domestic",
        )
        international_result = _is_valid_news_url(
            "https://metro.gov.tw/news/1",
            news_scope="international",
        )
        self.assertTrue(domestic_result[0])
        self.assertFalse(international_result[0])

    def test_domestic_query_family_is_limited_and_scoped(self):
        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知", "重大事故", "營運政策", "營運爭議"],
            active_regions=[],
            lookback_days=7,
            lookback_int=7,
            is_global_scope=True,
            today=FIXED_DATE,
            ddgs_client_factory=None,
            news_scope="domestic",
        )
        queries, _news_indices = ddgs_search_service.build_search_queries(context=context)
        self.assertEqual(len(queries), 6)
        self.assertEqual(
            {context.query_metadata[query]["family"] for query in queries},
            {"domestic_metro", "service_opening"},
        )
        self.assertEqual(
            {context.query_metadata[query]["query_region"] for query in queries},
            {"domestic"},
        )

    def test_domestic_queries_are_recall_friendly(self):
        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知", "重大事故", "營運政策", "營運爭議", "機電標案"],
            active_regions=[],
            lookback_days=30,
            lookback_int=30,
            is_global_scope=True,
            today=FIXED_DATE,
            ddgs_client_factory=None,
            news_scope="domestic",
        )
        queries, _news_indices = ddgs_search_service.build_search_queries(context=context)
        domestic_queries = {
            query
            for query in queries
            if context.query_metadata[query]["query_region"] == "domestic"
        }
        self.assertEqual(
            domestic_queries,
            {
                "臺灣 捷運 號誌",
                "臺灣 捷運 維修",
                "臺灣 捷運 安全",
                "臺灣 捷運 票務",
                "臺灣 捷運 爭議",
                "臺灣 捷運 通車",
                "臺灣 捷運 機電 決標",
                "臺灣 捷運 車輛 採購",
            },
        )
        self.assertTrue(all(len(query.split()) <= 4 for query in domestic_queries))

    def test_both_scope_adds_domestic_queries_without_changing_default(self):
        context = ddgs_search_service.DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=30,
            lookback_int=30,
            is_global_scope=True,
            today=FIXED_DATE,
            ddgs_client_factory=None,
            news_scope="both",
        )
        queries, _news_indices = ddgs_search_service.build_search_queries(context=context)
        families = {context.query_metadata[query]["family"] for query in queries}
        self.assertEqual(len(queries), 23)
        self.assertIn("technology", families)
        self.assertIn("domestic_metro", families)


if __name__ == "__main__":
    unittest.main()
