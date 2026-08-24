import datetime
import unittest
from unittest.mock import patch

import article_processor
import ddgs_search_service
import developer_debug_service
import rss_feed_service
from test_electromechanical_procurement import _candidate, _evaluate, _selector


FIXED_FETCHED_AT = datetime.datetime(2026, 8, 24, 4, 30, tzinfo=datetime.timezone.utc)


class _ParsedFeed:
    def __init__(self, entries):
        self.entries = entries


def _candidate_factory(query_metadata=None):
    query_metadata = query_metadata or {}

    def factory(**kwargs):
        query = kwargs.get("query", "")
        return article_processor._make_news_candidate(
            **kwargs,
            query_metadata=query_metadata.get(query, {}),
            search_family_resolver=lambda value: query_metadata.get(value, {}).get("family", "general"),
            search_language_resolver=lambda value: query_metadata.get(value, {}).get("lang", "en"),
        )

    return factory


def _rss_context(entries):
    return rss_feed_service.RssFeedContext(
        lookback_days=7,
        feedparser_module=object(),
        http_session_factory=lambda: object(),
        fetch_feed_callback=lambda _session, _url, _parser: _ParsedFeed(entries),
        fallback_url_builder=lambda _url: None,
        url_safety_check=lambda _url, **_kwargs: (True, ""),
        known_bad_source_checker=lambda _name, _url: False,
        parse_pub_date=article_processor._parse_pub_date,
        is_recent=lambda _value, _cutoff: True,
        entry_pub_str=lambda entry: str(entry.get("published") or entry.get("updated") or "").strip(),
        entry_source_href=lambda entry: str((entry.get("source") or {}).get("href") or ""),
        contains_taiwan_reference=lambda _text: False,
        is_standards_source=lambda _name: False,
        is_standard_update_candidate=lambda _text: False,
        is_urban_rail_candidate=lambda _text, _source="": True,
        is_tech_news_only_mode=lambda: False,
        is_technical_news_candidate=lambda _text, _source="": True,
        normalize_title=article_processor._normalize_title,
        dedupe_url=article_processor._dedupe_url,
        domain_from_url=article_processor._domain_from_url,
        now_provider=lambda: FIXED_FETCHED_AT,
    )


def _run_ddgs(result, query="fixture metro query"):
    metadata = {
        query: {
            "family": "technology",
            "lang": "en",
            "query_region": "德國",
            "use_news": True,
            "timelimit": "w",
            "requested_max_results": 8,
            "planned_index": 1,
        }
    }
    context = ddgs_search_service.DdgsSearchContext(
        selected_types=["技術新知"],
        active_regions=["德國"],
        lookback_days=7,
        lookback_int=7,
        is_global_scope=False,
        today=datetime.date(2026, 8, 24),
        ddgs_client_factory=object(),
        query_metadata=metadata,
        sleep=lambda _seconds: None,
        random_uniform=lambda _start, _end: 0.0,
        now_provider=lambda: FIXED_FETCHED_AT,
    )
    with patch.object(
        ddgs_search_service,
        "service_execute_ddgs_query",
        return_value=[result],
    ):
        raw_text, statuses, summary = ddgs_search_service.run_duckduckgo_searches(
            context=context,
            search_queries=[query],
            news_query_indices={1},
        )
    candidates = article_processor.parse_ddg_candidates(
        raw_text,
        _candidate_factory(metadata),
    )
    return raw_text, candidates, statuses, summary


class RawCandidateProvenanceTests(unittest.TestCase):
    def test_a1_t1_rss_provenance_preserves_provider_values(self):
        raw_title = "  Metro   CBTC Upgrade  "
        raw_url = " https://official.example/news/cbtc "
        raw_publication = "Sun, 23 Aug 2026 06:00:00 GMT"
        entries = [{
            "id": "rss-entry-17",
            "title": raw_title,
            "link": raw_url,
            "summary": "Metro signalling system entered testing.",
            "published": raw_publication,
            "source": {
                "title": "Official Metro Authority",
                "href": "https://official.example/",
            },
        }]
        raw_text = rss_feed_service.fetch_rss_feeds(
            [("Fixture Official RSS", "https://official.example/feed")],
            context=_rss_context(entries),
        )
        candidate = article_processor.parse_rss_candidates(
            raw_text,
            _candidate_factory(),
        )[0]

        self.assertIsInstance(raw_text, article_processor.RawSearchText)
        self.assertEqual(candidate["raw_title"], raw_title)
        self.assertEqual(candidate["normalized_title"], "Metro CBTC Upgrade")
        self.assertNotEqual(candidate["raw_title"], candidate["normalized_title"])
        self.assertEqual(candidate["raw_url"], raw_url)
        self.assertEqual(candidate["raw_publication_value"], raw_publication)
        self.assertEqual(candidate["published_date"], "2026-08-23")
        self.assertEqual(candidate["fetched_at"], FIXED_FETCHED_AT.isoformat())
        self.assertEqual(candidate["search_provider"], "RSS")
        self.assertEqual(candidate["publisher"], "Official Metro Authority")
        self.assertTrue(candidate["raw_ingest_id"].startswith("raw_"))
        self.assertEqual(
            candidate["original_provider_metadata"]["feed_url"],
            "https://official.example/feed",
        )
        self.assertIsNone(
            getattr(raw_text, "provenance_records")[0]["query"]
        )

    def test_a1_t2_ddgs_provenance_preserves_query_region_and_publisher(self):
        raw_title = "  München Metro Contract  "
        raw_url = " https://rail.example/items/42 "
        raw_date = "2026-08-23T08:15:00+00:00"
        raw_text, candidates, statuses, summary = _run_ddgs({
            "title": raw_title,
            "body": "Metro authority awarded a signalling contract.",
            "href": raw_url,
            "date": raw_date,
            "source": "Rail Example",
            "provider": "fixture-news",
        })
        candidate = candidates[0]

        self.assertIsInstance(raw_text, article_processor.RawSearchText)
        self.assertEqual(candidate["raw_title"], raw_title)
        self.assertEqual(candidate["normalized_title"], "München Metro Contract")
        self.assertEqual(candidate["raw_url"], raw_url)
        self.assertEqual(candidate["raw_publication_value"], raw_date)
        self.assertEqual(candidate["published_date"], raw_date)
        self.assertEqual(candidate["fetched_at"], FIXED_FETCHED_AT.isoformat())
        self.assertEqual(candidate["search_provider"], "DDGS")
        self.assertEqual(candidate["publisher"], "Rail Example")
        self.assertEqual(candidate["query"], "fixture metro query")
        self.assertEqual(candidate["query_region"], "德國")
        self.assertEqual(candidate["search_family"], "technology")
        self.assertEqual(candidate["original_provider_metadata"]["provider"], "fixture-news")
        self.assertEqual(statuses[0]["added_to_raw_count"], 1)
        self.assertEqual(summary["DDGS_added_to_raw_count"], 1)

    def test_a1_t3_t4_raw_and_normalized_date_values_coexist(self):
        raw_publication = "Sun, 23 Aug 2026 06:00:00 GMT"
        raw_text = rss_feed_service.fetch_rss_feeds(
            [("Fixture RSS", "https://official.example/feed")],
            context=_rss_context([{
                "title": "  Metro   Upgrade  ",
                "link": "https://official.example/news/upgrade",
                "summary": "Metro system upgrade.",
                "published": raw_publication,
            }]),
        )
        candidate = article_processor.parse_rss_candidates(raw_text, _candidate_factory())[0]

        self.assertEqual(candidate["raw_publication_value"], raw_publication)
        self.assertEqual(candidate["published_date"], "2026-08-23")
        self.assertEqual(candidate["date"], candidate["published_date"])
        self.assertEqual(candidate["raw_title"], "  Metro   Upgrade  ")
        self.assertEqual(candidate["title"], "Metro Upgrade")

    def test_a1_t5_missing_provider_values_remain_null(self):
        raw_text, candidates, _statuses, _summary = _run_ddgs({
            "title": "Metro technical update",
            "body": "Urban rail system technical update.",
            "href": "https://rail.example/items/missing",
        })
        candidate = candidates[0]

        self.assertIsNone(candidate["raw_publication_value"])
        self.assertIsNone(candidate["publisher"])
        self.assertEqual(candidate["published_date"], "日期未知")
        self.assertIsNone(candidate["original_provider_metadata"]["date"])
        self.assertIsNone(candidate["original_provider_metadata"]["source"])
        self.assertIsNone(getattr(raw_text, "provenance_records")[0]["publisher"])

    def test_raw_ingest_id_is_deterministic_and_separate_from_candidate_id(self):
        result = {
            "title": "Metro CBTC deployment",
            "body": "Metro train control deployment.",
            "href": "https://rail.example/items/stable",
            "date": "2026-08-23",
            "source": "Rail Example",
        }
        first = _run_ddgs(result)[1][0]
        second = _run_ddgs(result)[1][0]

        self.assertEqual(first["raw_ingest_id"], second["raw_ingest_id"])
        self.assertNotIn("candidate_id", first)
        self.assertNotEqual(first["raw_ingest_id"], first.get("candidate_id"))

    def test_a1_t6_classification_region_dedupe_and_selection_are_unchanged(self):
        api = _selector(
            "international",
            ["技術新知", "機電標案", "營運政策", "重大事故"],
        )
        legacy = _candidate(
            501,
            "Metro selects supplier for new automatic fare collection system.",
        )
        traced = dict(legacy)
        traced.update({
            "raw_title": f" {legacy['title']} ",
            "normalized_title": legacy["title"],
            "raw_url": legacy["url"],
            "raw_publication_value": legacy["date"],
            "published_date": legacy["date"],
            "fetched_at": FIXED_FETCHED_AT.isoformat(),
            "search_provider": "DDGS",
            "publisher": None,
            "original_provider_metadata": {},
            "raw_ingest_id": "raw_fixture_501",
        })

        legacy = api["annotate_candidate_for_scheme_d"](_evaluate(api, legacy))
        traced = api["annotate_candidate_for_scheme_d"](_evaluate(api, traced))
        self.assertEqual(legacy["primary_category"], traced["primary_category"])
        self.assertEqual(legacy["category_gates"], traced["category_gates"])
        self.assertEqual(
            article_processor._canonical_candidate_region(legacy),
            article_processor._canonical_candidate_region(traced),
        )

        legacy_deduped, legacy_stats = article_processor.dedupe_candidates([legacy], 7)
        traced_deduped, traced_stats = article_processor.dedupe_candidates([traced], 7)
        self.assertEqual(legacy_stats, traced_stats)
        self.assertEqual(len(legacy_deduped), len(traced_deduped))

        legacy_selected = api["select_candidates_by_python"](legacy_deduped)
        traced_selected = api["select_candidates_by_python"](traced_deduped)
        self.assertEqual(len(legacy_selected), 1)
        self.assertEqual(len(legacy_selected), len(traced_selected))
        self.assertEqual(
            [item.get("classification") for item in legacy_selected],
            [item.get("classification") for item in traced_selected],
        )
        self.assertEqual(
            [item.get("primary_category") for item in legacy_selected],
            [item.get("primary_category") for item in traced_selected],
        )

    def test_developer_diagnostics_include_bounded_provenance(self):
        candidate = _run_ddgs({
            "title": "Metro signalling update",
            "body": "Metro signalling deployment.",
            "href": "https://rail.example/items/debug",
            "date": "2026-08-23",
            "source": "Rail Example",
        })[1][0]
        row = developer_debug_service._debug_candidate_rows([candidate])[0]

        for key in (
            "candidate_id",
            "raw_ingest_id",
            "provider",
            "search_provider",
            "publisher",
            "raw_title",
            "normalized_title",
            "raw_publication_value",
            "published_date",
            "fetched_at",
            "raw_url",
            "effective_url",
            "original_provider_metadata",
            "search_query",
            "query_region",
        ):
            self.assertIn(key, row)
        self.assertLessEqual(len(candidate["original_provider_metadata"]), 20)


if __name__ == "__main__":
    unittest.main()
