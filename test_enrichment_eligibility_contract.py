import copy
import datetime
import unittest
from unittest.mock import patch

import article_selector
import report_workflow_service as workflow_service


def _selector_api(*, with_formal_checker=True, formal_report_mode=None):
    dependencies = dict(
        selected_types=["技術新知", "重大事故", "營運政策", "營運爭議"],
        active_regions=[],
        lookback_days=7,
        lookback_int=7,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=datetime.date(2026, 9, 17),
        news_scope="both",
        _search_family_from_query=lambda _query: "major_accident",
        _search_language_from_query=lambda _query: "en",
        create_requests_session=lambda: None,
        _profile_timing_add=lambda *_args: None,
    )
    if with_formal_checker:
        dependencies[
            "formal_report_evidence_eligibility"
        ] = workflow_service._formal_report_evidence_eligibility
    if formal_report_mode is not None:
        dependencies["formal_report_mode"] = formal_report_mode
    return article_selector.build_selector_api(**dependencies)


def _candidate(
    *,
    title="Metro train collision injures passengers",
    date="2026-09-17",
    index=1,
):
    source = f"Fixture News {index}"
    url = f"https://fixture.example/article/{index}"
    return {
        "title": title,
        "snippet": f"{title} {source}",
        "date": date,
        "source": source,
        "source_display": source,
        "source_domain": "fixture.example",
        "source_tier": "B_professional",
        "source_quality": "A",
        "source_href": url,
        "url": url,
        "region": "美國",
        "resolved_region": "美國",
        "country": "美國",
        "page_type": "news_article",
        "authoritative_materialization_stage": "provisional",
        "primary_category": "重大事故",
        "classification": "重大事故",
        "preliminary_type": "重大事故",
        "category_gates": {"major_accident": True},
        "evidence": {
            "feed_snippet": f"{title} {source}",
            "article_excerpt": "",
            "provenance": "feed",
            "richness": "feed_snippet",
        },
    }


class EnrichmentEligibilityContractTests(unittest.TestCase):
    def test_category_pass_title_like_evidence_enters_existing_pool(self):
        api = _selector_api()
        candidate = _candidate()

        self.assertFalse(
            workflow_service._formal_report_evidence_eligibility(candidate)[0]
        )
        with patch.object(
            article_selector,
            "_prefetch_candidate_article",
            return_value={
                "status": "failed_enrichment",
                "reason": "test_no_network",
                "evidence_valid": False,
            },
        ):
            stats = api["prefetch_candidates_before_filter"]([candidate])

        self.assertEqual(stats["eligible_count"], 1)
        self.assertEqual(stats["attempted_count"], 1)
        self.assertTrue(candidate["rescue_candidate"])

    def test_category_pass_low_value_service_notice_is_not_rescued(self):
        api = _selector_api()
        candidate = _candidate(
            title="Subway weekend service notice for passengers",
        )
        candidate["primary_category"] = "營運政策"
        candidate["classification"] = "營運政策"
        candidate["preliminary_type"] = "營運政策"
        candidate["category_gates"] = {"high_value_policy": True}

        self.assertFalse(
            workflow_service._formal_report_evidence_eligibility(candidate)[0]
        )
        self.assertEqual(api["_information_quality_issue"](candidate), "日常服務推播")
        self.assertFalse(api["_candidate_prefetch_signal"](candidate))

    def test_category_fail_existing_pre_gate_rescue_is_preserved(self):
        api = _selector_api()
        candidate = _candidate(
            title="Subway service update procurement award announced",
        )
        candidate["primary_category"] = "excluded"
        candidate["classification"] = "excluded"
        candidate["preliminary_type"] = "excluded"
        candidate["category_gates"] = {}

        self.assertEqual(api["_information_quality_issue"](candidate), "日常服務推播")
        self.assertTrue(api["_is_pre_gate_rescue_candidate"](candidate))
        self.assertTrue(api["_candidate_prefetch_signal"](candidate))

    def test_category_pass_with_sufficient_evidence_does_not_need_rescue(self):
        api = _selector_api()
        candidate = _candidate()
        candidate["evidence"] = {
            "feed_snippet": (
                "The metro train collision injured passengers and suspended service."
            ),
            "article_excerpt": "",
            "provenance": "feed",
            "richness": "feed_snippet",
        }

        self.assertTrue(
            workflow_service._formal_report_evidence_eligibility(candidate)[0]
        )
        self.assertFalse(api["_candidate_prefetch_signal"](candidate))

    def test_category_fail_without_existing_signal_is_unchanged(self):
        api = _selector_api()
        candidate = _candidate(title="Metro station travel notice")
        candidate["primary_category"] = "excluded"
        candidate["classification"] = "excluded"
        candidate["preliminary_type"] = "excluded"
        candidate["category_gates"] = {}

        self.assertFalse(api["_candidate_prefetch_signal"](candidate))

    def test_hard_exclusions_still_win(self):
        api = _selector_api()
        old = _candidate(date="2020-01-01")
        nonurban = _candidate(title="National intercity freight railway collision")

        self.assertFalse(api["_candidate_prefetch_signal"](old))
        self.assertFalse(api["_candidate_prefetch_signal"](nonurban))

    def test_formal_gate_and_budget_contract_are_unchanged(self):
        api = _selector_api()
        candidate = _candidate()
        self.assertFalse(
            workflow_service._formal_report_evidence_eligibility(candidate)[0]
        )
        self.assertEqual(api["_prefetch_limit_for_period"](7), 8)

    def test_prefetch_respects_existing_weekly_budget_cap(self):
        api = _selector_api()
        candidates = [_candidate(index=index) for index in range(1, 11)]

        with patch.object(
            article_selector,
            "_prefetch_candidate_article",
            return_value={
                "status": "failed_enrichment",
                "reason": "test_no_network",
                "evidence_valid": False,
            },
        ):
            stats = api["prefetch_candidates_before_filter"](candidates)

        self.assertGreater(stats["eligible_count"], 8)
        self.assertLessEqual(stats["attempted_count"], 8)
        self.assertEqual(stats["attempted_count"], stats["general_rescue_budget"])

    def test_formal_report_mode_requires_evidence_dependency(self):
        with self.assertRaises(ValueError):
            _selector_api(with_formal_checker=False, formal_report_mode=True)

    def test_category_pass_candidate_is_reenriched_and_revalidated(self):
        config = workflow_service.WorkflowConfig(
            today=datetime.date(2026, 9, 17),
            lookback_days=7,
            selected_types=["技術新知", "重大事故", "營運政策", "營運爭議"],
            active_regions=[],
            is_global_scope=True,
            standards_enabled=False,
            include_research_supplement=False,
            fast_mode_enabled=False,
            date_range="2026年09月11日 至 2026年09月17日",
            report_title="enrichment fixture",
            report_scope_label="全球",
            report_period_label="週報",
        )
        candidate = _candidate()
        runtime = workflow_service.make_runtime(
            config,
            workflow_service.WorkflowDependencies(
                prefetch_enabled=True,
                http_session_factory=lambda: None,
            ),
        )
        runtime.parse_candidates = lambda _rss, _ddg: [copy.deepcopy(candidate)]

        def fake_prefetch(item, _session):
            excerpt = "The metro collision injured passengers and suspended service."
            item["evidence"] = {
                "feed_snippet": item["evidence"]["feed_snippet"],
                "article_excerpt": excerpt,
                "provenance": "feed+prefetch",
                "richness": "feed+article",
            }
            item["prefetched_text_snippet"] = excerpt
            return {
                "status": "success",
                "reason": "test_article",
                "chars": len(excerpt),
                "evidence_valid": True,
                "transport_success": True,
                "enrichment_method": "direct_article_url",
                "enriched_content_source": "article_html",
            }

        with patch.object(article_selector, "_prefetch_candidate_article", fake_prefetch):
            pool = runtime.prepare_candidate_pool("", "")

        self.assertEqual(pool["prefetch_stats"]["eligible_count"], 1)
        self.assertEqual(pool["prefetch_stats"]["success_count"], 1)
        self.assertEqual(len(pool["model_candidates"]), 1)
        self.assertTrue(
            workflow_service._formal_report_evidence_eligibility(
                pool["model_candidates"][0]
            )[0]
        )


if __name__ == "__main__":
    unittest.main()
