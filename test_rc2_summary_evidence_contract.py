import datetime
import json
import unittest

from article_processor import (
    _apply_prefetch_evidence,
    candidate_selection_evidence_text,
    materialize_candidate_evidence,
)
from report_postprocessor import validate_authoritative_report
from report_prompt_service import ReportPromptContext, format_report_candidate
from report_workflow_service import WorkflowConfig, WorkflowDependencies, make_runtime


def _candidate(*, title="Metro deploys CBTC signalling", snippet=""):
    return {
        "id": 1,
        "candidate_id": 1,
        "title": title,
        "snippet": snippet,
        "date": "2026-08-10",
        "region": "美國",
        "country": "美國",
        "classification": "技術新知",
        "preliminary_type": "技術新知",
        "source": "Fixture Source",
        "source_display": "Fixture Source",
        "source_domain": "example.com",
        "source_href": "https://example.com/articles/cbtc",
        "url": "https://example.com/articles/cbtc",
        "source_tier": "B_professional",
        "source_quality": "A",
        "core_systems": [],
        "authoritative_materialization_stage": "post_enrichment",
    }


def _prompt_context():
    return ReportPromptContext(
        selected_types=["技術新知"],
        include_research_supplement=False,
        standards_enabled=False,
        lookback_int=7,
        date_range="2026-08-04 至 2026-08-10",
        report_title="RC-2 fixture",
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


def _report(summary: str) -> str:
    return "\n".join([
        "## 一、技術新知",
        "<!-- candidate_id: 1 -->",
        "🔹 [技術新知] 捷運完成號誌測試",
        "• 發布/事件日期：2026-08-10",
        "• 國家：美國",
        "• 事件摘要：" + summary,
        "• 臺北捷運局啟示：可參考號誌測試與營運轉換管理。",
        "• 資料來源：Fixture Source https://example.com/articles/cbtc",
    ])


def _semantic_judge(payload: dict) -> dict:
    evidence = payload["evidence"]
    field = "feed_snippet" if evidence.get("feed_snippet") else "article_excerpt"
    quote = evidence.get(field, "")
    return {
        "candidate_id": payload["candidate_id"],
        "summary_status": "EVIDENCE_SUPPORTED",
        "semantic_state": "SUPPORTED",
        "failure_reason": "",
        "claims": [{
            "claim_text": payload["event_summary"],
            "support_status": "SUPPORTED",
            "evidence_mappings": [{
                "evidence_field": field,
                "evidence_quote": quote,
            }],
        }],
        "grounding_passed": True,
    }


class RC2SummaryEvidenceContractTests(unittest.TestCase):
    def test_title_only_contract_is_explicit(self):
        candidate = _candidate()
        evidence = materialize_candidate_evidence(candidate)
        self.assertEqual(evidence["richness"], "title_only")
        self.assertEqual(evidence["provenance"], "none")
        self.assertEqual(evidence["article_excerpt"], "")

    def test_feed_only_is_not_polluted_by_feed_prefetch_fallback(self):
        feed = "Metro CBTC signalling deployment was announced for the urban rail system."
        candidate = _candidate(snippet=feed)
        materialize_candidate_evidence(candidate)
        _apply_prefetch_evidence(
            candidate,
            (feed + " The operator will publish the implementation schedule and test results.") * 2,
            method="source_feed_snippet",
            content_source="candidate_source_feed",
        )
        self.assertEqual(candidate["snippet"], feed)
        self.assertEqual(candidate["evidence"]["feed_snippet"], feed)
        self.assertEqual(candidate["evidence"]["article_excerpt"], "")
        self.assertEqual(candidate["evidence"]["richness"], "feed_snippet")

    def test_prefetched_article_body_is_separate_from_feed(self):
        feed = "The metro plans a CBTC signalling deployment."
        article = (
            "Metro deploys CBTC signalling across the urban rail system after testing. "
            "The operator will publish implementation results and the commissioning plan."
        ) * 2
        candidate = _candidate(snippet=feed)
        materialize_candidate_evidence(candidate)
        chars = _apply_prefetch_evidence(
            candidate,
            article,
            method="direct_article_url",
            content_source="article_html",
            resolved_url=candidate["url"],
        )
        self.assertGreater(chars, 0)
        self.assertEqual(candidate["snippet"], feed)
        self.assertEqual(candidate["evidence"]["feed_snippet"], feed)
        self.assertTrue(candidate["evidence"]["article_excerpt"])
        self.assertEqual(candidate["evidence"]["richness"], "feed+article")
        self.assertEqual(candidate["evidence"]["provenance"], "feed+prefetch")

    def test_selector_projection_is_contract_owned(self):
        candidate = _candidate(snippet="Feed evidence")
        materialize_candidate_evidence(candidate, article_excerpt="Article evidence", article_evidence=True)
        self.assertEqual(candidate_selection_evidence_text(candidate), "Feed evidence Article evidence")

    def test_workflow_materialization_preserves_evidence(self):
        config = WorkflowConfig(
            today=datetime.date(2026, 8, 10),
            lookback_days=7,
            selected_types=["技術新知"],
            active_regions=[],
            is_global_scope=True,
            standards_enabled=False,
            include_research_supplement=False,
            fast_mode_enabled=False,
            date_range="2026-08-04 至 2026-08-10",
            report_title="RC-2 fixture",
            report_scope_label="全球",
            report_period_label="週報",
        )
        runtime = make_runtime(config, WorkflowDependencies(prefetch_enabled=False))
        candidate = _candidate(snippet="Feed evidence")
        materialize_candidate_evidence(candidate, article_excerpt="Article evidence", article_evidence=True)
        expected = dict(candidate["evidence"])
        runtime._materialize_authoritative_candidate(candidate)
        self.assertEqual(candidate["evidence"], expected)

    def test_prompt_receives_layered_evidence(self):
        candidate = _candidate(snippet="Feed evidence")
        materialize_candidate_evidence(candidate, article_excerpt="Article evidence", article_evidence=True)
        payload = json.loads(format_report_candidate(candidate, context=_prompt_context()))
        self.assertEqual(payload["evidence"]["feed_snippet"], "Feed evidence")
        self.assertEqual(payload["evidence"]["article_excerpt"], "Article evidence")
        self.assertEqual(payload["evidence"]["richness"], "feed+article")
        self.assertEqual(payload["snippet"], "Feed evidence")

    def test_validator_rejects_title_copy_with_evidence_contract(self):
        candidate = _candidate(title="捷運完成號誌測試", snippet="The operator completed a signalling test.")
        materialize_candidate_evidence(candidate)
        validation = validate_authoritative_report(
            _report("捷運完成號誌測試"),
            [candidate],
            selected_types=["技術新知"],
        )
        self.assertFalse(validation["report_validation_passed"])
        self.assertEqual(validation["summary_evidence_status"]["1"], "title_copy")

    def test_validator_rejects_summary_when_candidate_is_title_only(self):
        candidate = _candidate(title="只有標題的候選")
        materialize_candidate_evidence(candidate)
        validation = validate_authoritative_report(
            _report("捷運完成新系統測試。"),
            [candidate],
            selected_types=["技術新知"],
        )
        self.assertFalse(validation["report_validation_passed"])
        self.assertEqual(validation["summary_evidence_status"]["1"], "insufficient_evidence")

    def test_validator_accepts_non_copy_summary_with_feed_evidence(self):
        candidate = _candidate(snippet="The operator completed a signalling test.")
        materialize_candidate_evidence(candidate)
        validation = validate_authoritative_report(
            _report("營運單位完成號誌測試並評估後續轉換安排。"),
            [candidate],
            selected_types=["技術新知"],
            semantic_judge=_semantic_judge,
            semantic_validation_required=True,
        )
        self.assertEqual(validation["summary_evidence_status"]["1"], "evidence_supported")
        self.assertTrue(validation["report_validation_passed"])


if __name__ == "__main__":
    unittest.main()
