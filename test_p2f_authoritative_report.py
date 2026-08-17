import datetime
import unittest

from report_postprocessor import (
    remove_authoritative_candidate_markers,
    validate_authoritative_report,
)
from report_workflow_service import (
    WorkflowConfig,
    WorkflowDependencies,
    make_runtime,
)


TECHNICAL = "技術新知"
ACCIDENT = "重大事故"
OPERATIONAL = "營運動態"
PROCUREMENT = "機電標案"


def _config() -> WorkflowConfig:
    return WorkflowConfig(
        today=datetime.date(2026, 8, 17),
        lookback_days=30,
        selected_types=[TECHNICAL, ACCIDENT, OPERATIONAL, PROCUREMENT],
        active_regions=["全球"],
        is_global_scope=True,
        standards_enabled=False,
        include_research_supplement=False,
        fast_mode_enabled=False,
        date_range="2026-07-18 至 2026-08-17",
        report_title="fixture",
        report_scope_label="全球",
        report_period_label="近 30 天",
    )


def _candidate(candidate_id: int, category: str) -> dict:
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "classification": category,
        "preliminary_type": category,
        "title": f"Fixture article {candidate_id}",
    }


def _selected_candidates() -> list[dict]:
    categories = {
        **{candidate_id: TECHNICAL for candidate_id in range(1, 5)},
        **{candidate_id: ACCIDENT for candidate_id in range(5, 7)},
        **{candidate_id: OPERATIONAL for candidate_id in range(7, 12)},
        **{candidate_id: PROCUREMENT for candidate_id in range(12, 15)},
    }
    return [_candidate(candidate_id, categories[candidate_id]) for candidate_id in range(1, 15)]


def _authoritative_fixture() -> str:
    blocks = [
        (1, "🔹 [技術新知] New Urban Track control system", TECHNICAL),
        (2, "🔹 技術新知 Edmonds system trial", TECHNICAL),
        (3, "🔹 技術新知 Manchester Piccadilly derailment study", TECHNICAL),
        (4, "🔹 技術新知 MTA modernized elevator", TECHNICAL),
        (5, "🔹 [重大事故] Line 5 service incident", ACCIDENT),
        (6, "🔹 重大事故 Station power interruption", ACCIDENT),
        (7, "🔹 [營運動態] New service opening", OPERATIONAL),
        (8, "🔹 營運動態 Passenger service update", OPERATIONAL),
        (9, "🔹 營運動態 Network operating notice", OPERATIONAL),
        (10, "🔹 營運動態 Timetable improvement", OPERATIONAL),
        (12, "🔹 [機電標案] Signalling equipment procurement", PROCUREMENT),
        (13, "🔹 機電標案 Rolling stock maintenance contract", PROCUREMENT),
        (14, "🔹 機電標案 Platform screen door tender", PROCUREMENT),
    ]
    lines = [
        "# 國際捷運技術週報",
        "## 一、技術新知",
    ]
    for candidate_id, title, category in blocks:
        if candidate_id == 9:
            lines.append("<!-- candidate_id: 11 -->")
            lines.append("<!-- candidate_id: 9 -->")
        else:
            lines.append(f"<!-- candidate_id: {candidate_id} -->")
        lines.extend([
            title,
            f"• 日期：2026-08-{candidate_id + 1:02d}",
            "• 國家：美國",
            "• 相關機電系統：車輛系統",
            f"• 事件摘要：{category} fixture event {candidate_id} with preserved evidence.",
            "• 臺北捷運局啟示：保留模型提供的工程參考內容。",
            f"• 資料來源：Fixture Source https://example.com/article/{candidate_id}",
            "",
        ])
        if candidate_id == 4:
            lines.append("## 二、重大事故")
        elif candidate_id == 6:
            lines.append("## 三、營運動態")
        elif candidate_id == 10:
            lines.append("## 四、機電標案")
    return "\n".join(lines)


class AuthoritativeReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.selected = _selected_candidates()
        self.runtime = make_runtime(
            _config(),
            WorkflowDependencies(prefetch_enabled=False),
        )

    def test_authoritative_body_preserved_and_multi_marker_ids_retained(self):
        raw = _authoritative_fixture()
        result = self.runtime.postprocess_report_with_diagnostics(raw, self.selected)
        diagnostics = result["id_validation"]

        self.assertEqual(result["validated_report"], raw)
        self.assertEqual(result["clean_report"], remove_authoritative_candidate_markers(raw))
        self.assertNotIn("candidate_id", result["clean_report"])
        self.assertIn("New Urban Track control system", result["clean_report"])
        self.assertIn("Fixture Source https://example.com/article/4", result["clean_report"])
        self.assertIn("<!-- candidate_id: 11 -->", result["validated_report"])
        self.assertIn("<!-- candidate_id: 9 -->", result["validated_report"])
        self.assertEqual(diagnostics["selected_candidate_id_count"], 14)
        self.assertEqual(diagnostics["model_candidate_id_count"], 14)
        self.assertEqual(diagnostics["selected_to_model_id_coverage"], 1.0)
        self.assertEqual(diagnostics["selected_to_final_id_coverage"], 1.0)
        self.assertEqual(diagnostics["report_article_count"], 13)
        self.assertTrue(diagnostics["report_validation_passed"])
        self.assertEqual(diagnostics["postprocess_mode"], "authoritative_passthrough")
        self.assertEqual(diagnostics["fallback_block_count"], 0)
        self.assertEqual(diagnostics["skipped_candidate_ids"], [])

    def test_missing_candidate_fails_validation_without_fallback(self):
        raw = "\n".join([
            "## 一、技術新知",
            "<!-- candidate_id: 1 -->",
            "🔹 [技術新知] Only selected candidate one",
            "• 事件摘要：原文摘要。",
        ])
        result = self.runtime.postprocess_report_with_diagnostics(raw, self.selected[:2])
        diagnostics = result["id_validation"]

        self.assertEqual(result["validated_report"], raw)
        self.assertEqual(result["clean_report"], remove_authoritative_candidate_markers(raw))
        self.assertIn(2, diagnostics["missing_ids"])
        self.assertIn("1", diagnostics["missing_model_fields"])
        self.assertEqual(
            diagnostics["parser_failure_reasons"]["1"],
            "missing_required_fields",
        )
        self.assertFalse(diagnostics["report_validation_passed"])
        self.assertEqual(diagnostics["fallback_block_count"], 0)
        self.assertEqual(result["dropped_candidates"], [])

    def test_tolerant_title_formats_are_validation_only(self):
        raw = "\n".join([
            "## 一、技術新知",
            "<!-- candidate_id: 1 -->",
            "🔹 [技術新知] Bracket title",
            "• 日期：2026-08-17",
            "• 國家：美國",
            "• 相關機電系統：號誌系統",
            "• 事件摘要：Bracket summary.",
            "• 臺北捷運局啟示：Bracket insight.",
            "• 資料來源：Fixture Source https://example.com/1",
            "## 二、重大事故",
            "<!-- candidate_id: 2 -->",
            "🔹 重大事故 Bare title",
            "• 日期：2026-08-17",
            "• 國家：英國",
            "• 相關機電系統：車輛系統",
            "• 事件摘要：Bare summary.",
            "• 臺北捷運局啟示：Bare insight.",
            "• 資料來源：Fixture Source https://example.com/2",
            "## 三、營運動態",
            "<!-- candidate_id: 3 -->",
            "🔹 營運動態｜Pipe title",
            "• 日期：2026-08-17",
            "• 國家：加拿大",
            "• 相關機電系統：供電系統",
            "• 事件摘要：Pipe summary.",
            "• 臺北捷運局啟示：Pipe insight.",
            "• 資料來源：Fixture Source https://example.com/3",
        ])
        validation = validate_authoritative_report(
            raw,
            [
                _candidate(1, TECHNICAL),
                _candidate(2, ACCIDENT),
                _candidate(3, OPERATIONAL),
            ],
            selected_types=[TECHNICAL, ACCIDENT, OPERATIONAL],
        )

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["report_article_count"], 3)
        self.assertTrue(validation["report_validation_passed"])

    def test_public_report_body_is_single_render_source(self):
        raw = _authoritative_fixture()
        public_report, diagnostics, dropped = self.runtime.postprocess_report(raw, self.selected)

        self.assertEqual(public_report, remove_authoritative_candidate_markers(raw))
        self.assertNotIn("<!-- candidate_id:", public_report)
        self.assertEqual(dropped, [])
        self.assertEqual(diagnostics["postprocess_mode"], "authoritative_passthrough")
        self.assertEqual(public_report, self.runtime.postprocess_report(raw, self.selected)[0])


if __name__ == "__main__":
    unittest.main()
