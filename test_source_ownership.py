import datetime
import unittest

from article_processor import build_formal_report_source
from report_postprocessor import (
    canonicalize_authoritative_source_fields,
    validate_authoritative_report,
)
from report_workflow_service import WorkflowConfig, WorkflowDependencies, make_runtime


TECHNICAL = "技術新知"


def _candidate(
    candidate_id: int = 1,
    *,
    url: str = "https://criticalcomms.com/articles/facial-recognition",
    source_href: str | None = None,
    resolved_article_url: str = "",
) -> dict:
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": "London Underground tests a new signalling system",
        "date": "2026-08-20",
        "country": "英國",
        "resolved_region": "倫敦",
        "region_resolution_method": "title_city",
        "region_resolution_evidence": "London Underground",
        "source": "CriticalComms",
        "source_display": "CriticalComms",
        "source_domain": "criticalcomms.com",
        "source_href": source_href or url,
        "url": url,
        "resolved_article_url": resolved_article_url,
        "classification": TECHNICAL,
        "preliminary_type": TECHNICAL,
        "core_systems": ["號誌"],
    }


def _report(source: str, *, candidate_id: int = 1) -> str:
    return "\n".join([
        "## 一、技術新知",
        f"<!-- candidate_id: {candidate_id} -->",
        "🔹 [技術新知] 倫敦地鐵號誌測試",
        "• 發布/事件日期：2026-08-20",
        "• 國家/地區：英國",
        "• 相關機電系統：號誌系統",
        "• 事件摘要：倫敦地鐵完成新號誌系統測試並評估營運效益。",
        "• 臺北捷運局啟示：可作為號誌測試與營運轉換管理參考。",
        f"• 資料來源：{source}",
    ])


def _config() -> WorkflowConfig:
    return WorkflowConfig(
        today=datetime.date(2026, 8, 27),
        lookback_days=30,
        selected_types=[TECHNICAL],
        active_regions=["全球"],
        is_global_scope=True,
        standards_enabled=False,
        include_research_supplement=False,
        fast_mode_enabled=False,
        date_range="2026-07-29 至 2026-08-27",
        report_title="fixture",
        report_scope_label="全球",
        report_period_label="近 30 天",
    )


class SourceOwnershipTests(unittest.TestCase):
    def test_arbitrary_model_suffix_is_removed_and_canonical_source_restored(self):
        candidate = _candidate()
        raw = _report("Wrong Publisher https://wrong.example/article suffix from model")
        output = canonicalize_authoritative_source_fields(raw, [candidate])
        expected = build_formal_report_source(candidate)
        self.assertIn(expected["display_name"], output)
        self.assertIn(expected["display_url"], output)
        self.assertNotIn("suffix from model", output)
        self.assertNotIn("wrong.example", output)
        self.assertIn("倫敦地鐵完成新號誌系統測試並評估營運效益。", output)

    def test_matching_canonical_source_is_left_byte_stable(self):
        candidate = _candidate()
        formal = build_formal_report_source(candidate)
        raw = _report(f"{formal['display_name']} {formal['display_url']}")
        self.assertEqual(canonicalize_authoritative_source_fields(raw, [candidate]), raw)

    def test_validator_rejects_model_display_name_mismatch(self):
        candidate = _candidate()
        formal = build_formal_report_source(candidate)
        validation = validate_authoritative_report(
            _report(f"Other Publisher {formal['display_url']}"),
            [candidate],
            selected_types=[TECHNICAL],
        )
        self.assertFalse(validation["report_validation_passed"])
        self.assertIn("source_metadata_mismatch", [item["code"] for item in validation["content_quality_issues"]])

    def test_validator_rejects_model_url_mismatch(self):
        candidate = _candidate()
        validation = validate_authoritative_report(
            _report("CriticalComms https://criticalcomms.com/"),
            [candidate],
            selected_types=[TECHNICAL],
        )
        self.assertFalse(validation["report_validation_passed"])
        self.assertEqual(len(validation["source_metadata_mismatches"]), 1)

    def test_article_level_url_beats_publisher_homepage(self):
        article_url = "https://criticalcomms.com/articles/facial-recognition"
        candidate = _candidate(url="https://criticalcomms.com/", source_href=article_url)
        output = canonicalize_authoritative_source_fields(
            _report("CriticalComms https://criticalcomms.com/"),
            [candidate],
        )
        self.assertIn(article_url, output)
        self.assertNotIn("資料來源：CriticalComms https://criticalcomms.com/\n", output)

    def test_google_proxy_is_preserved_when_no_direct_article_exists(self):
        proxy_url = "https://news.google.com/rss/articles/ABC123?q=criticalcomms"
        candidate = _candidate(url=proxy_url, source_href=proxy_url)
        output = canonicalize_authoritative_source_fields(
            _report("CriticalComms https://criticalcomms.com/"),
            [candidate],
        )
        self.assertIn(proxy_url, output)

    def test_direct_article_url_wins_over_google_proxy(self):
        proxy_url = "https://news.google.com/rss/articles/ABC123?q=criticalcomms"
        direct_url = "https://criticalcomms.com/articles/facial-recognition"
        candidate = _candidate(url=proxy_url, source_href=proxy_url, resolved_article_url=direct_url)
        output = canonicalize_authoritative_source_fields(
            _report(f"CriticalComms {proxy_url}"),
            [candidate],
        )
        self.assertIn(direct_url, output)
        self.assertNotIn(proxy_url, output)

    def test_runtime_postprocess_overlays_source_before_final_validation(self):
        candidate = _candidate()
        raw = _report("criticalcomms.com:https://criticalcomms.com/articles/facial-recognition 白小姐")
        result = make_runtime(
            _config(),
            WorkflowDependencies(prefetch_enabled=False),
        ).postprocess_report_with_diagnostics(raw, [candidate])
        expected = build_formal_report_source(candidate)
        self.assertTrue(result["id_validation"]["report_validation_passed"])
        self.assertIn(expected["display_url"], result["clean_report"])
        self.assertNotIn("白小姐", result["clean_report"])

    def test_prose_fields_are_not_rewritten_by_source_overlay(self):
        candidate = _candidate()
        summary = "倫敦地鐵完成新號誌系統測試並評估營運效益。"
        insight = "可作為號誌測試與營運轉換管理參考。"
        raw = _report("Wrong Publisher https://wrong.example/article suffix")
        output = canonicalize_authoritative_source_fields(raw, [candidate])
        self.assertIn(summary, output)
        self.assertIn(insight, output)

    def test_each_marked_block_uses_its_own_candidate_source(self):
        first = _candidate(1)
        second = _candidate(
            2,
            url="https://railwaygazette.com/articles/metro-control",
            source_href="https://railwaygazette.com/articles/metro-control",
        )
        raw = "\n\n".join([
            _report("Wrong first https://wrong.example/one", candidate_id=1),
            _report("Wrong second https://wrong.example/two", candidate_id=2),
        ])
        output = canonicalize_authoritative_source_fields(raw, [first, second])
        self.assertIn("https://criticalcomms.com/articles/facial-recognition", output)
        self.assertIn("https://railwaygazette.com/articles/metro-control", output)
        self.assertNotIn("wrong.example", output)


if __name__ == "__main__":
    unittest.main()
