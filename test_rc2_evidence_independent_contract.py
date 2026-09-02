import datetime
import json
import unittest

from article_processor import _apply_prefetch_evidence, _make_news_candidate
from report_postprocessor import validate_authoritative_report
from report_prompt_service import ReportPromptContext, format_report_candidate


TITLE = "Metro deploys CBTC signalling"
FEED = "The operator announced a CBTC signalling deployment for the urban rail system."
ARTICLE = (
    "Metro deploys CBTC signalling across the urban rail system after a completed test. "
    "The operator will publish implementation results and the commissioning plan for service."
) * 2


def raw_candidate(*, title: str = TITLE, snippet: str = "") -> dict:
    candidate = _make_news_candidate(
        title,
        "2026-08-10",
        "Fixture Source",
        "https://example.com/articles/cbtc",
        snippet,
        "metro cbtc",
        "美國",
        "rss",
        source_href="https://example.com/articles/cbtc",
        query_metadata={"family": "technology", "lang": "en"},
        search_family_resolver=lambda _value: "technology",
        search_language_resolver=lambda _value: "en",
    )
    candidate.update(
        {
            "id": 1,
            "candidate_id": 1,
            "classification": "技術新知",
            "preliminary_type": "技術新知",
            "authoritative_materialization_stage": "post_enrichment",
        }
    )
    return candidate


def prompt_context() -> ReportPromptContext:
    return ReportPromptContext(
        selected_types=["技術新知"],
        include_research_supplement=False,
        standards_enabled=False,
        lookback_int=7,
        date_range="2026-08-04 至 2026-08-10",
        report_title="RC-2 independent fixture",
        report_scope_label="全球",
        research_supplement_period_label="近 90 天",
        research_supplement_start_date=datetime.date(2026, 5, 10),
        today=datetime.date(2026, 8, 10),
        empty_text_by_type={},
        advanced_types=["技術新知"],
        selection_min_items=1,
        selection_max_items=5,
        candidate_snippet_chars=120,
        report_snippet_chars=240,
        get_selection_output_range=lambda _days: "1～5",
        effective_source_url=lambda item: item.get("url", ""),
        domain_from_url=lambda _url: "example.com",
        extract_domain_hint=lambda _url: "example.com",
        infer_preliminary_type=lambda _item: "技術新知",
        shorten=lambda value, limit: str(value or "")[:limit],
        is_standard_update_candidate=lambda _text, _enabled: False,
        source_label_for_report=lambda source, _url, _href, _tier: source,
        source_verb_for_report=lambda _tier, _source: "報導",
    )


def report_text(summary: str) -> str:
    return "\n".join(
        [
            "## 一、技術新知",
            "<!-- candidate_id: 1 -->",
            "🔹 [技術新知] 捷運完成號誌測試",
            "• 發布/事件日期：2026-08-10",
            "• 國家：美國",
            "• 事件摘要：" + summary,
            "• 臺北捷運局啟示：可參考號誌測試與營運轉換管理。",
            "• 資料來源：Fixture Source https://example.com/articles/cbtc",
        ]
    )


class RC2IndependentEvidenceContractTests(unittest.TestCase):
    def test_raw_title_only_materializes_explicit_title_only(self):
        candidate = raw_candidate()
        self.assertEqual(candidate["evidence"], {
            "feed_snippet": "",
            "article_excerpt": "",
            "provenance": "none",
            "richness": "title_only",
        })

    def test_raw_feed_is_not_replaced_by_source_feed_prefetch(self):
        candidate = raw_candidate(snippet=FEED)
        _apply_prefetch_evidence(
            candidate,
            (FEED + " The operator will publish commissioning results and a schedule.") * 2,
            method="source_feed_snippet",
            content_source="candidate_source_feed",
        )
        self.assertEqual(candidate["snippet"], FEED)
        self.assertEqual(candidate["evidence"]["feed_snippet"], FEED)
        self.assertEqual(candidate["evidence"]["article_excerpt"], "")
        self.assertEqual(candidate["evidence"]["richness"], "feed_snippet")

    def test_raw_feed_and_article_remain_separate(self):
        candidate = raw_candidate(snippet=FEED)
        _apply_prefetch_evidence(
            candidate,
            ARTICLE,
            method="direct_article_url",
            content_source="article_html",
            resolved_url=candidate["url"],
        )
        self.assertEqual(candidate["snippet"], FEED)
        self.assertEqual(candidate["evidence"]["feed_snippet"], FEED)
        self.assertEqual(candidate["evidence"]["article_excerpt"], ARTICLE)
        self.assertEqual(candidate["evidence"]["provenance"], "feed+prefetch")
        self.assertEqual(candidate["evidence"]["richness"], "feed+article")

    def test_raw_article_without_feed_is_article_only(self):
        candidate = raw_candidate()
        _apply_prefetch_evidence(
            candidate,
            ARTICLE,
            method="direct_article_url",
            content_source="article_html",
            resolved_url=candidate["url"],
        )
        self.assertEqual(candidate["evidence"]["feed_snippet"], "")
        self.assertTrue(candidate["evidence"]["article_excerpt"])
        self.assertEqual(candidate["evidence"]["provenance"], "prefetch")
        self.assertEqual(candidate["evidence"]["richness"], "article_excerpt")

    def test_prompt_receives_distinct_feed_and_article_values(self):
        candidate = raw_candidate(snippet=FEED)
        _apply_prefetch_evidence(
            candidate,
            ARTICLE,
            method="direct_article_url",
            content_source="article_html",
            resolved_url=candidate["url"],
        )
        payload = json.loads(format_report_candidate(candidate, context=prompt_context()))
        self.assertEqual(payload["evidence"]["feed_snippet"], FEED)
        self.assertIn("Metro deploys CBTC signalling", payload["evidence"]["article_excerpt"])
        self.assertNotEqual(payload["evidence"]["feed_snippet"], payload["evidence"]["article_excerpt"])
        self.assertEqual(payload["snippet"], FEED)

    def test_validator_consumes_raw_contract_for_four_summary_states(self):
        validator_title = "捷運完成新型號誌測試與營運轉換"
        feed_candidate = raw_candidate(title=validator_title, snippet=FEED)
        title_only_candidate = raw_candidate(title=validator_title)
        supported = validate_authoritative_report(
            report_text("營運單位完成號誌測試並評估後續轉換安排。"),
            [feed_candidate],
            selected_types=["技術新知"],
        )
        title_copy = validate_authoritative_report(
            report_text(validator_title),
            [feed_candidate],
            selected_types=["技術新知"],
        )
        title_only = validate_authoritative_report(
            report_text("捷運完成新系統測試。"),
            [title_only_candidate],
            selected_types=["技術新知"],
        )
        self.assertEqual(supported["summary_evidence_status"]["1"], "evidence_supported")
        self.assertEqual(title_copy["summary_evidence_status"]["1"], "title_copy")
        self.assertEqual(title_only["summary_evidence_status"]["1"], "insufficient_evidence")
        paraphrase = validate_authoritative_report(
            report_text("捷運完成新型號誌測試並進入營運轉換"),
            [feed_candidate],
            selected_types=["技術新知"],
        )
        self.assertEqual(paraphrase["summary_evidence_status"]["1"], "title_paraphrase")


if __name__ == "__main__":
    unittest.main()
