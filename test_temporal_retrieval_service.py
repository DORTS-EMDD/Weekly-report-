import datetime as dt
from types import SimpleNamespace
import unittest

from rss_feed_service import RssFeedContext, _items_from_parsed_feed, fetch_rss_feeds
from search_service import FeedFetchError
from temporal_retrieval_service import (
    MODE_BUCKETED_ABSOLUTE,
    MODE_CONTINUOUS_RECENT,
    PROVIDER_DDGS,
    PROVIDER_GOOGLE_NEWS_RSS,
    TemporalRetrievalRouter,
    TemporalRetrievalRequest,
    build_calendar_quarter_buckets,
    verify_candidate_publication,
    verify_route_metadata,
)


class TemporalRetrievalServiceTests(unittest.TestCase):
    REPORT_DATE = dt.date(2026, 8, 24)

    def make_plan(self):
        request = TemporalRetrievalRequest(
            report_date=self.REPORT_DATE,
            lookback_days=365,
            selected_types=("技術新知", "重大事故", "營運政策", "營運爭議"),
        )
        return TemporalRetrievalRouter().build_plan(request)

    def test_a6_i1_dynamic_quarter_intersections(self):
        buckets = build_calendar_quarter_buckets(
            dt.date(2025, 8, 24), dt.date(2026, 8, 25)
        )
        self.assertEqual(
            [(row.label, row.start, row.end_exclusive) for row in buckets],
            [
                ("2025-Q3", dt.date(2025, 8, 24), dt.date(2025, 10, 1)),
                ("2025-Q4", dt.date(2025, 10, 1), dt.date(2026, 1, 1)),
                ("2026-Q1", dt.date(2026, 1, 1), dt.date(2026, 4, 1)),
                ("2026-Q2", dt.date(2026, 4, 1), dt.date(2026, 7, 1)),
                ("2026-Q3", dt.date(2026, 7, 1), dt.date(2026, 8, 25)),
            ],
        )

    def test_a6_i2_buckets_are_contiguous_and_non_overlapping(self):
        plan = self.make_plan()
        self.assertEqual(plan.buckets[0].start, dt.date(2025, 8, 24))
        self.assertEqual(plan.buckets[-1].end_exclusive, dt.date(2026, 8, 25))
        for left, right in zip(plan.buckets, plan.buckets[1:]):
            self.assertEqual(left.end_exclusive, right.start)
            self.assertLess(left.start, left.end_exclusive)

    def test_a6_i3_out_of_window_result_does_not_verify_old_quarter(self):
        bucket = self.make_plan().buckets[0]
        result = verify_route_metadata(
            {
                "requested_bucket": bucket.label,
                "requested_start": bucket.start.isoformat(),
                "requested_end_exclusive": bucket.end_exclusive.isoformat(),
            },
            "2026-08-21",
            date_source="rss_published",
        )
        self.assertEqual(result.status, "out_of_window")
        self.assertEqual(result.verified_bucket, "")

    def test_a6_i4_in_window_result_verifies_matching_quarter(self):
        bucket = next(row for row in self.make_plan().buckets if row.label == "2026-Q3")
        result = verify_route_metadata(
            {
                "requested_bucket": bucket.label,
                "requested_start": bucket.start.isoformat(),
                "requested_end_exclusive": bucket.end_exclusive.isoformat(),
            },
            "2026-08-21",
            date_source="rss_published",
        )
        self.assertEqual(result.status, "verified")
        self.assertEqual(result.verified_bucket, "2026-Q3")

    def test_a6_i5_missing_publication_date_has_no_credit(self):
        route = self.make_plan().routes[0]
        result = TemporalRetrievalRouter.verify_route_result(route, None)
        self.assertEqual(result.status, "missing_date")
        self.assertIsNone(result.normalized_publication_date)

    def test_a6_i6_out_of_window_is_rejected(self):
        route = self.make_plan().routes[0]
        result = TemporalRetrievalRouter.verify_route_result(route, "2026-01-01")
        self.assertEqual(result.status, "out_of_window")

    def test_a6_i7_ddgs_has_no_annual_coverage_capability(self):
        from temporal_retrieval_service import PROVIDER_CAPABILITIES

        self.assertFalse(PROVIDER_CAPABILITIES[PROVIDER_DDGS]["annual_bucket_coverage_credit"])

        from ddgs_search_service import DdgsSearchContext, build_search_queries, _ddgs_query_status_template

        context = DdgsSearchContext(
            selected_types=["技術新知"],
            active_regions=[],
            lookback_days=365,
            lookback_int=365,
            is_global_scope=True,
            today=self.REPORT_DATE,
            ddgs_client_factory=None,
        )
        queries, _ = build_search_queries(context=context)
        annual_rows = [
            metadata
            for metadata in context.query_metadata.values()
            if metadata.get("retrieval_lane") == "ddgs_annual_discovery"
        ]
        self.assertTrue(annual_rows)
        self.assertTrue(all(row.get("verified_bucket", "") == "" for row in annual_rows))
        self.assertTrue(all(row.get("annual_bucket_coverage_credit") is False for row in annual_rows))
        annual_query = next(
            query
            for query, metadata in context.query_metadata.items()
            if metadata.get("retrieval_lane") == "ddgs_annual_discovery"
        )
        status = _ddgs_query_status_template(annual_query, "m", context=context)
        self.assertEqual(status.get("date_bucket", ""), "")
        self.assertEqual(status.get("annual_bucket_families", []), [])

    def test_a6_i8_google_news_rss_in_window_verifies(self):
        self.assertEqual(
            self.make_plan().routes[0].provider,
            PROVIDER_GOOGLE_NEWS_RSS,
        )
        route = next(row for row in self.make_plan().routes if row.bucket.label == "2025-Q3")
        self.assertEqual(
            TemporalRetrievalRouter.verify_route_result(route, "2025-09-12").status,
            "verified",
        )

    def test_a6_i9_google_news_rss_out_of_window_fails_closed(self):
        route = next(row for row in self.make_plan().routes if row.bucket.label == "2025-Q3")
        self.assertEqual(
            TemporalRetrievalRouter.verify_route_result(route, "2026-08-21").status,
            "out_of_window",
        )

    def test_a6_i10_provider_failure_does_not_fallback(self):
        plan = self.make_plan()
        route = plan.routes[0]
        events = []
        context = self.make_context(
            route,
            fetch_callback=lambda *_args: (_ for _ in ()).throw(
                FeedFetchError("timeout", "provider timeout")
            ),
            event_callback=lambda metadata, status: events.append((metadata["route_id"], status)),
        )
        _raw, statuses = fetch_rss_feeds(
            [(route.source_name, route.url)], context=context, return_status=True
        )
        self.assertEqual(statuses[0]["status"], "timeout")
        self.assertIn((route.route_id, "provider_error"), events)
        self.assertFalse(any(status == "fallback" for _route, status in events))

    def test_a6_i11_duplicate_routes_retain_bounded_provenance(self):
        plan = self.make_plan()
        first, second = plan.routes[:2]
        context = self.make_context(first)
        first_feed = SimpleNamespace(entries=[self.entry("same article", "https://example.test/a", "2025-09-01")])
        second_feed = SimpleNamespace(entries=[self.entry("same article", "https://example.test/a", "2025-09-02")])
        _items_from_parsed_feed(
            first_feed, dt.datetime(2026, 8, 24, tzinfo=dt.timezone.utc), set(), set(),
            source_name=first.source_name, context=context, feed_url=first.url,
        )
        context.temporal_route_metadata_by_url = {second.url: second.metadata}
        _items_from_parsed_feed(
            second_feed, dt.datetime(2026, 8, 24, tzinfo=dt.timezone.utc),
            {"same article"}, {"https://example.test/a"},
            source_name=second.source_name, context=context, feed_url=second.url,
        )
        provenance = next(iter(context.raw_provenance_by_key.values()))["retrieval_provenance"]
        self.assertEqual({row["route_id"] for row in provenance}, {first.route_id, second.route_id})

    def test_a6_i12_weekly_mode_unchanged(self):
        request = TemporalRetrievalRequest(self.REPORT_DATE, 7)
        self.assertEqual(request.mode, MODE_CONTINUOUS_RECENT)
        self.assertFalse(TemporalRetrievalRouter().build_plan(request).routes)

    def test_a6_i13_monthly_mode_unchanged(self):
        request = TemporalRetrievalRequest(self.REPORT_DATE, 30)
        self.assertEqual(request.mode, MODE_CONTINUOUS_RECENT)
        self.assertFalse(TemporalRetrievalRouter().build_plan(request).buckets)

    def test_a6_i14_requested_bucket_cannot_promote_without_verification(self):
        route = self.make_plan().routes[0]
        result = verify_route_metadata(route.metadata, "2026-08-21", date_source="rss_published")
        self.assertNotEqual(result.status, "verified")
        self.assertEqual(result.verified_bucket, "")

    def test_a6_i15_event_date_cannot_create_publication_credit(self):
        route = next(row for row in self.make_plan().routes if row.bucket.label == "2025-Q3")
        # Event date is deliberately not passed to the publication verifier.
        event_date = "2025-09-15"
        publication_date = "2026-08-21"
        self.assertEqual(event_date, "2025-09-15")
        self.assertEqual(
            TemporalRetrievalRouter.verify_route_result(route, publication_date).status,
            "out_of_window",
        )

    def test_candidate_verification_general_rss_assigns_matching_bucket(self):
        result = verify_candidate_publication(
            self.make_plan(),
            {
                "search_provider": "RSS",
                "raw_publication_value": "2026-08-21",
                "original_provider_metadata": {"published": "2026-08-21"},
            },
        )
        self.assertEqual(result.status, "verified")
        self.assertEqual(result.date_source, "rss_published")
        self.assertEqual(result.verified_bucket, "2026-Q3")

    def test_candidate_verification_missing_future_and_outside_fail_closed(self):
        plan = self.make_plan()
        missing = verify_candidate_publication(plan, {"search_provider": "RSS"})
        future = verify_candidate_publication(
            plan,
            {
                "search_provider": "RSS",
                "raw_publication_value": "2026-08-27",
                "original_provider_metadata": {"published": "2026-08-27"},
            },
        )
        outside = verify_candidate_publication(
            plan,
            {
                "search_provider": "RSS",
                "raw_publication_value": "2025-08-01",
                "original_provider_metadata": {"published": "2025-08-01"},
            },
        )
        self.assertEqual(missing.status, "missing_date")
        self.assertNotEqual(future.status, "verified")
        self.assertNotEqual(outside.status, "verified")

    def test_candidate_verification_conflicting_publication_evidence_fails(self):
        result = verify_candidate_publication(
            self.make_plan(),
            {
                "search_provider": "RSS",
                "raw_publication_value": "2026-08-21",
                "original_provider_metadata": {
                    "published": "2026-08-21",
                },
                "page_parsed_publication_date": "2026-08-20",
            },
        )
        self.assertEqual(result.status, "conflicting_date_evidence")
        self.assertEqual(result.verified_bucket, "")

    def test_candidate_verification_route_origin_requires_matching_window(self):
        plan = self.make_plan()
        route = next(row for row in plan.routes if row.bucket.label == "2026-Q3")
        matching = verify_candidate_publication(
            plan,
            {
                **route.metadata,
                "search_provider": "RSS",
                "raw_publication_value": "2026-08-21",
                "original_provider_metadata": {"published": "2026-08-21"},
            },
        )
        conflicting = verify_candidate_publication(
            plan,
            {
                **route.metadata,
                "search_provider": "RSS",
                "raw_publication_value": "2025-09-12",
                "original_provider_metadata": {"published": "2025-09-12"},
            },
        )
        self.assertEqual(matching.status, "verified")
        self.assertNotEqual(conflicting.status, "verified")

    def test_candidate_verification_ddgs_query_date_is_not_evidence(self):
        query_only = verify_candidate_publication(
            self.make_plan(),
            {
                "search_provider": "DDGS",
                "raw_publication_value": "2026-08-21",
                "original_provider_metadata": {"date": "2026-08-21"},
            },
        )
        published = verify_candidate_publication(
            self.make_plan(),
            {
                "search_provider": "DDGS",
                "raw_publication_value": "2026-08-21",
                "original_provider_metadata": {"published": "2026-08-21"},
            },
        )
        self.assertNotEqual(query_only.status, "verified")
        self.assertEqual(published.status, "verified")

    @staticmethod
    def entry(title, link, published):
        return {
            "title": title,
            "link": link,
            "published": published,
            "summary": "metro rail technical report",
            "source": {"title": "Example"},
        }

    def make_context(self, route, *, fetch_callback=None, event_callback=None):
        from article_processor import _dedupe_url, _normalize_title, _parse_pub_date

        return RssFeedContext(
            lookback_days=365,
            feedparser_module=object(),
            http_session_factory=lambda: object(),
            fetch_feed_callback=fetch_callback or (lambda *_args: SimpleNamespace(entries=[])),
            fallback_url_builder=lambda _url: "https://fallback.invalid",
            url_safety_check=lambda *_args, **_kwargs: (True, ""),
            known_bad_source_checker=lambda *_args: False,
            parse_pub_date=_parse_pub_date,
            is_recent=lambda *_args: True,
            entry_pub_str=lambda entry: str(entry.get("published") or entry.get("updated") or ""),
            entry_source_href=lambda _entry: "",
            contains_taiwan_reference=lambda _text: False,
            is_standards_source=lambda _source: False,
            is_standard_update_candidate=lambda _text: True,
            is_urban_rail_candidate=lambda *_args: True,
            is_tech_news_only_mode=lambda: False,
            is_technical_news_candidate=lambda *_args: True,
            normalize_title=_normalize_title,
            dedupe_url=_dedupe_url,
            domain_from_url=lambda _url: "example.test",
            temporal_route_metadata_by_url={route.url: route.metadata},
            temporal_result_verifier=lambda metadata, raw, date_source: self.verification_dict(
                verify_route_metadata(metadata, raw, date_source=date_source)
            ),
            temporal_event_callback=event_callback,
        )

    @staticmethod
    def verification_dict(result):
        return {
            "status": result.status,
            "normalized_publication_date": result.normalized_publication_date,
            "date_source": result.date_source,
            "verified_bucket": result.verified_bucket,
        }


if __name__ == "__main__":
    unittest.main()
