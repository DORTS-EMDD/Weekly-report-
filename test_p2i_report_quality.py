import datetime
import json
import unittest

from report_postprocessor import (
    ReportPostprocessContext,
    count_journal_summary_conclusion_chars,
    normalize_journal_section_format,
    validate_authoritative_report,
)
from report_prompt_service import ReportPromptContext, build_report_prompt, format_report_candidate
from report_workflow_service import WorkflowConfig, WorkflowDependencies, make_runtime


TECHNICAL = "技術新知"


def _prompt_context() -> ReportPromptContext:
    return ReportPromptContext(
        selected_types=[TECHNICAL],
        include_research_supplement=False,
        standards_enabled=False,
        lookback_int=30,
        date_range="2026-07-19 至 2026-08-17",
        report_title="fixture",
        report_scope_label="全球",
        research_supplement_period_label="近 90 天",
        research_supplement_start_date=datetime.date(2026, 5, 19),
        today=datetime.date(2026, 8, 17),
        empty_text_by_type={TECHNICAL: "本期未發現符合條件之技術新知。"},
        advanced_types=[TECHNICAL],
        selection_min_items=1,
        selection_max_items=5,
        candidate_snippet_chars=120,
        report_snippet_chars=240,
        get_selection_output_range=lambda _days: "1～5",
        effective_source_url=lambda candidate: candidate.get("url", ""),
        domain_from_url=lambda _url: "example.com",
        extract_domain_hint=lambda _url: "example.com",
        infer_preliminary_type=lambda _candidate: TECHNICAL,
        shorten=lambda value, _limit: str(value or ""),
        is_standard_update_candidate=lambda _text, _enabled: False,
        source_label_for_report=lambda source, url, source_href, source_tier: source or url,
        source_verb_for_report=lambda _tier, _source: "報導",
    )


def _postprocess_context() -> ReportPostprocessContext:
    return ReportPostprocessContext(
        selected_types=[TECHNICAL],
        standards_enabled=False,
        include_research_supplement=True,
        lookback_int=30,
        today=datetime.date(2026, 8, 17),
        date_range="2026-07-19 至 2026-08-17",
        report_title="fixture",
        report_scope_label="全球",
        candidate_selection_text=lambda candidate: str(candidate.get("title", "")),
        infer_preliminary_type=lambda candidate: str(candidate.get("classification", TECHNICAL)),
        is_urban_rail_candidate=lambda _text: True,
        research_section_heading=lambda _markdown=False: "六、國際學術期刊",
        id_validation_target={},
    )


def _candidate(candidate_id=1, *, country="美國", source_display="Railway-News") -> dict:
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": "Metro deploys a technical system",
        "date": "2026-08-10",
        "country": country,
        "resolved_region": "New York",
        "region_resolution_method": "title_city",
        "region_resolution_evidence": "New York MTA subway",
        "operator": "MTA",
        "system_name": "New York Subway",
        "snippet": "The metro deployed the system.",
        "source_display": source_display,
        "source_domain": "railway-news.com",
        "url": f"https://example.com/article/{candidate_id}",
        "classification": TECHNICAL,
        "preliminary_type": TECHNICAL,
    }


def _report(candidate_id=1, *, country_line="• 國家：美國", summary="都市捷運開始測試新系統。", source="Railway-News https://example.com/article/1") -> str:
    return "\n".join([
        "## 一、技術新知",
        f"<!-- candidate_id: {candidate_id} -->",
        "🔹 技術新知 技術系統測試",
        "• 發布/事件日期：2026-08-10",
        country_line,
        "• 相關機電系統：號誌系統",
        "• 事件摘要：",
        summary,
        "• 臺北捷運局啟示：",
        "可作為系統驗證參考。",
        "• 資料來源：",
        source,
    ])


def _journal_report() -> tuple[str, list[dict]]:
    candidates = [
        {
            "title": f"研究 {index}",
            "published_date": f"2026-0{index}-10",
            "journal_name": "Rail Systems Journal",
            "url": f"https://doi.org/10.1234/fixture.{index}",
        }
        for index in range(1, 5)
    ]
    lines = ["# 報告", "", "## 六、國際學術期刊"]
    for index in range(1, 5):
        lines.extend([
            f"{index}、研究 {index}",
            f"• 發表日期：2026-0{index}-10",
            "• 期刊／來源：Rail Systems Journal",
            "• 研究主題：都市軌道研究",
            "• 研究摘要：研究摘要內容。",
            "• 臺北捷運局啟示：可作為工程參考。",
            f"• 資料來源：https://doi.org/10.1234/fixture.{index}",
        ])
    lines.extend([
        "### 學術期刊綜合結論",
        "這段結論不應保留。",
        "📊 統計",
    ])
    return "\n".join(lines), candidates


class P2IReportQualityTests(unittest.TestCase):
    def test_known_country_is_sent_as_formal_country(self):
        payload = json.loads(format_report_candidate(_candidate(country="美國"), context=_prompt_context()))
        self.assertEqual(payload["country"], "美國")

    def test_unknown_country_is_omitted_but_evidence_is_sent(self):
        candidate = _candidate(country="未判定")
        candidate["resolved_region"] = "Twin Cities"
        payload = json.loads(format_report_candidate(candidate, context=_prompt_context()))
        self.assertNotIn("country", payload)
        self.assertEqual(payload["resolved_region"], "Twin Cities")
        self.assertEqual(payload["operator"], "MTA")
        prompt = build_report_prompt([candidate], [], 1, context=_prompt_context())
        self.assertIn("若 payload 未提供 country", prompt)
        self.assertIn("絕不得輸出「國家：未判定」", prompt)

    def test_unknown_country_formal_field_fails_but_omitted_country_passes(self):
        selected = [_candidate(country="未判定")]
        omitted = _report(country_line="", summary="都市捷運開始測試新系統。")
        self.assertTrue(validate_authoritative_report(omitted, selected, selected_types=[TECHNICAL])["report_validation_passed"])
        unknown = _report(country_line="• 國家：未判定")
        validation = validate_authoritative_report(unknown, selected, selected_types=[TECHNICAL])
        self.assertFalse(validation["report_validation_passed"])
        self.assertIn("unknown_country_in_formal_report", [item["code"] for item in validation["content_quality_issues"]])

    def test_source_prefixed_summary_fails(self):
        validation = validate_authoritative_report(
            _report(summary="Railway-News 報導，都市捷運開始測試新系統。"),
            [_candidate()],
            selected_types=[TECHNICAL],
        )
        self.assertFalse(validation["report_validation_passed"])
        self.assertIn("source_prefixed_summary", [item["code"] for item in validation["content_quality_issues"]])

    def test_direct_event_summary_passes(self):
        validation = validate_authoritative_report(
            _report(summary="都市捷運開始測試新系統。"),
            [_candidate()],
            selected_types=[TECHNICAL],
        )
        self.assertTrue(validation["report_validation_passed"])

    def test_generic_source_fallback_fails_when_candidate_has_source(self):
        validation = validate_authoritative_report(
            _report(source="資料來源未明確辨識 https://example.com/article/1"),
            [_candidate()],
            selected_types=[TECHNICAL],
        )
        self.assertFalse(validation["report_validation_passed"])
        self.assertIn("generic_source_fallback", [item["code"] for item in validation["content_quality_issues"]])

    def test_journal_fields_have_blank_lines_and_conclusion_is_removed(self):
        report, journals = _journal_report()
        normalized = normalize_journal_section_format(report, journals, context=_postprocess_context())
        self.assertNotIn("學術期刊綜合結論", normalized)
        self.assertIn("◆ [學術期刊] 研究 1\n\n• 發表日期", normalized)
        self.assertIn("• 研究主題：都市軌道研究\n\n• 研究摘要", normalized)
        self.assertEqual(count_journal_summary_conclusion_chars(normalized, context=_postprocess_context()), 0)

    def test_authoritative_passthrough_preserves_model_content(self):
        config = WorkflowConfig(
            today=datetime.date(2026, 8, 17),
            lookback_days=30,
            selected_types=[TECHNICAL],
            active_regions=["全球"],
            is_global_scope=True,
            standards_enabled=False,
            include_research_supplement=False,
            fast_mode_enabled=False,
            date_range="2026-07-19 至 2026-08-17",
            report_title="fixture",
            report_scope_label="全球",
            report_period_label="近 30 天",
        )
        selected = [_candidate()]
        raw = _report()
        result = make_runtime(config, WorkflowDependencies(prefetch_enabled=False)).postprocess_report_with_diagnostics(raw, selected)
        self.assertEqual(result["validated_report"], raw)
        self.assertIn("技術系統測試", result["clean_report"])
        self.assertIn("Railway-News", result["clean_report"])
        self.assertNotIn("candidate_id", result["clean_report"])
        self.assertEqual(result["id_validation"]["postprocess_mode"], "authoritative_passthrough")
        self.assertEqual(result["id_validation"]["selected_to_model_id_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
