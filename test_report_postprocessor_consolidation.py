"""Golden fixtures for the consolidated formal-report postprocessing stages."""

import copy
import datetime
import hashlib
import json
import logging
import os
import unittest

os.environ.setdefault("MAIAGENT_API_KEY", "postprocessor-test")
os.environ.setdefault("MAIAGENT_CHATBOT_ID", "postprocessor-test")
os.environ.setdefault("DEFAULT_RECIPIENTS", "postprocessor@example.invalid")
logging.disable(logging.CRITICAL)

import streamlit_app as app


EXPECTED_SCENARIO_SHA256 = {
    "weekly_without_journal": (
        "99f769d120d58e8d4cbc56828945aad4448853769916d6d16522c2f0d5d1ddca"
    ),
    "weekly_with_journal": (
        "cbc6bbad99c22b0de15c4d1c4db1cf98f401cdec6c99e39eaded06eee6101718"
    ),
    "annual_with_journal": (
        "aa9b3aee058d3a3f351b133fc7141cb4e4a474c7787a625a53cde58a47d1a7d0"
    ),
}
EXPECTED_AGGREGATE_SHA256 = (
    "742989374c29a0a1d2b2032bf126c4e51015f19ea792ce89db03223291abe7c7"
)


class ModuleApi:
    def __init__(self, module):
        object.__setattr__(self, "_module", module)

    def __getattr__(self, name):
        return getattr(self._module, name)

    def __setattr__(self, name, value):
        setattr(self._module, name, value)


def _sha256(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _selected_candidates():
    return [
        {
            "id": 1,
            "candidate_id": 1,
            "title": "TTC Line 2 System Upgrade",
            "date": "2026-07-20",
            "source": "TTC",
            "source_display": "TTC",
            "source_tier": "A",
            "region": "未判定",
            "classification": "技術新知",
            "preliminary_type": "技術新知",
            "snippet": "TTC Line 2 導入 Hitachi 數位號誌並提升運能。",
            "url": "https://www.ttc.ca/news/line-2-upgrade",
            "supplemental_sources": [
                {
                    "title": "Hitachi digital signalling capacity increase 40%",
                    "source_display": "Hitachi Rail",
                    "url": "https://www.hitachirail.com/ttc-line-2",
                }
            ],
        },
        {
            "id": 2,
            "candidate_id": 2,
            "title": "Basel tram collision disrupts service",
            "date": "2026-06-18",
            "source": "Basel Police",
            "source_display": "Basel Police",
            "source_tier": "A",
            "region": "未判定",
            "classification": "重大事故",
            "preliminary_type": "重大事故",
            "snippet": "Basel tram collision caused a service disruption.",
            "url": "https://www.bs.ch/news/tram-collision",
        },
        {
            "id": 3,
            "candidate_id": 3,
            "title": "Metro fare reform",
            "date": "2026-05-10",
            "source": "Metro Authority",
            "source_display": "Metro Authority",
            "source_tier": "A",
            "region": "美國",
            "classification": "營運政策",
            "preliminary_type": "營運政策",
            "snippet": "Metro Authority 公告 AFC 票價制度調整。",
            "url": "https://metro.example/fare-reform",
        },
        {
            "id": 4,
            "candidate_id": 4,
            "title": "Union service dispute",
            "date": "2026-04-02",
            "source": "Rail News",
            "source_display": "Rail News",
            "source_tier": "B",
            "region": "英國",
            "classification": "營運爭議",
            "preliminary_type": "營運爭議",
            "snippet": "Metro union 提出營運服務爭議。",
            "url": "https://rail.example/union-dispute",
        },
    ]


def _journal_candidates():
    return [
        {
            "title": "Condition monitoring for urban rail",
            "published_date": "2026-06-30",
            "date": "2026-06-30",
            "journal_name": "Journal of Rail Systems",
            "source": "Journal of Rail Systems",
            "doi": "10.1234/fixture.2026.1",
            "url": "https://doi.org/10.1234/fixture.2026.1",
            "snippet": "都市軌道狀態監測與預測維護研究。",
        }
    ]


def _raw_report(include_journal):
    journal = (
        """

## 四、國際學術期刊

1、Condition monitoring for urban rail
• 發表日期：日期未知
• 期刊／來源：Journal of Rail Systems
• 研究主題：狀態監測
• 研究摘要：研究探討都市軌道狀態監測。
• 臺北捷運局啟示：可作為預測維護參考。
• 資料來源：https://doi.org/10.1234/fixture.2026.1
"""
        if include_journal
        else ""
    )
    return (
        """# 舊報告標題
> 資料涵蓋期間：fixture
> 報導範圍：fixture

## 一、技術新知

<!-- candidate_id: 1 -->
🔹 [技術新知] System Upgrade

• 發布/事件日期：2026-07-20
• 國家/地區：未判定
• 相關機電系統：號誌系統
• 事件摘要：
TTC Line 2 採用 Hitachi 數位號誌，預期運能提升 40%。
• 臺北捷運局啟示：
可追蹤號誌更新之介面與驗證。
• 資料來源：TTC，2026-07-20，https://www.ttc.ca/news/line-2-upgrade

## 三、營運政策

<!-- candidate_id: 3 -->
🔹 [營運政策] Metro fare reform
• 發布/事件日期：2026-05-10
• 國家/地區：美國
• 相關機電系統：AFC
• 事件摘要：
Metro Authority 公告 AFC 票價制度調整。
• 臺北捷運局啟示：
可追蹤票務介面與旅客服務影響。
• 資料來源：Metro Authority，2026-05-10，https://metro.example/fare-reform

## 四、營運爭議

<!-- candidate_id: 4 -->
🔹 [營運爭議] Union service dispute
• 發布/事件日期：2026-04-02
• 國家/地區：英國
• 相關機電系統：營運管理
• 事件摘要：
Metro union 提出營運服務爭議。
• 臺北捷運局啟示：
可追蹤勞資事件之營運衝擊。
• 資料來源：Rail News，2026-04-02，https://rail.example/union-dispute
"""
        + journal
    ).strip()


def run_scenario(api, *, lookback_days, include_journal):
    selected = _selected_candidates()
    journals = _journal_candidates() if include_journal else []
    api.selected_types = [
        "技術新知",
        "重大事故",
        "營運政策",
        "營運爭議",
    ]
    api.standards_enabled = False
    api.include_research_supplement = include_journal
    api.lookback_int = lookback_days
    api.today = datetime.date(2026, 7, 23)
    api.date_range = (
        "2025年07月23日 至 2026年07月23日"
        if lookback_days == 365
        else "2026年07月16日 至 2026年07月23日"
    )
    api.report_title = (
        "【2026/07/23】國際捷運年度回顧"
        if lookback_days == 365
        else "【2026/07/23】國際捷運技術週報"
    )
    api.report_scope_label = "全球"
    api.LAST_REPORT_ID_VALIDATION = {}

    report = api.sanitize_report_text(_raw_report(include_journal))
    steps = {"sanitized": report}
    report = api.enforce_research_section(report, journals)
    steps["research_enforced"] = report
    report = api.ensure_journal_summary_conclusion(report, journals)
    steps["journal_conclusion"] = report
    report = api.normalize_final_report_md(report)
    steps["normalized"] = report
    report = api.repair_journal_dates_in_report(report, journals)
    steps["journal_dates"] = report
    report = api.normalize_journal_section_format(report, journals)
    steps["journal_format"] = report
    report, dropped = api.restore_missing_selected_report_items(
        report,
        selected,
    )
    steps["reconciled"] = report
    report = api.repair_report_region_lines(report, selected)
    steps["regions"] = report
    report = api.repair_generic_report_titles(report, selected)
    steps["titles"] = report
    report = api.merge_operational_report_sections(report)
    steps["operations_merged"] = report
    report = api.normalize_report_section_numbering(report)
    steps["sections_numbered"] = report
    report = api.ensure_supplemental_sources_in_report(report, selected)
    steps["supplemental_sources"] = report
    report = api.remove_missing_data_disclaimers(report)
    steps["missing_data_removed"] = report
    report = api.insert_annual_observation_section(report)
    steps["annual_observation"] = report

    id_validation = api.validate_report_candidate_ids(report, selected)
    clean_report = api.remove_internal_candidate_markers(report)
    clean_report = api.normalize_formal_report_title(clean_report)
    clean_report = api.apply_final_report_footer(clean_report, journals)
    coverage = api.build_final_report_coverage_warning(
        clean_report,
        lookback_days,
        api.today,
    )
    incident = api.build_final_incident_coverage_debug(
        selected,
        _raw_report(include_journal),
        clean_report,
        global_scope=True,
        report_days=lookback_days,
        incident_enabled=True,
    )
    result = {
        "steps": steps,
        "final_report": clean_report,
        "formal_count": api.count_report_items(clean_report),
        "category_counts": api.count_report_items_by_category(clean_report),
        "dropped_candidates": dropped,
        "id_validation": id_validation,
        "id_reconciliation": copy.deepcopy(
            api.LAST_REPORT_ID_VALIDATION
        ),
        "coverage": coverage,
        "incident": incident,
        "journal_conclusion_chars": (
            api.count_journal_summary_conclusion_chars(clean_report)
        ),
    }
    return result


class ConsolidatedReportPostprocessorGoldenTests(unittest.TestCase):
    def setUp(self):
        self.api = ModuleApi(app)
        self.original = {
            name: copy.deepcopy(getattr(app, name))
            for name in (
                "selected_types",
                "standards_enabled",
                "include_research_supplement",
                "lookback_int",
                "today",
                "date_range",
                "report_title",
                "report_scope_label",
                "LAST_REPORT_ID_VALIDATION",
            )
        }

    def tearDown(self):
        for name, value in self.original.items():
            setattr(app, name, value)

    def test_all_postprocessing_stages_match_pre_split(self):
        scenarios = {
            "weekly_without_journal": run_scenario(
                self.api,
                lookback_days=7,
                include_journal=False,
            ),
            "weekly_with_journal": run_scenario(
                self.api,
                lookback_days=7,
                include_journal=True,
            ),
            "annual_with_journal": run_scenario(
                self.api,
                lookback_days=365,
                include_journal=True,
            ),
        }
        hashes = {
            name: _sha256(result)
            for name, result in scenarios.items()
        }
        self.assertEqual(hashes, EXPECTED_SCENARIO_SHA256)
        self.assertEqual(
            _sha256(scenarios),
            EXPECTED_AGGREGATE_SHA256,
        )
        annual = scenarios["annual_with_journal"]
        self.assertIn("年度觀察重點", annual["final_report"])
        self.assertIn("學術期刊綜合結論", annual["final_report"])
        self.assertTrue(annual["dropped_candidates"])
        self.assertTrue(
            annual["id_reconciliation"]["after_reconcile"]["valid"]
        )
        self.assertEqual(annual["id_validation"]["missing_ids"], [])
        self.assertIn(
            "Hitachi Rail",
            annual["steps"]["supplemental_sources"],
        )
        self.assertNotIn(
            "未判定",
            annual["steps"]["regions"].split("🔹 [技術新知]", 1)[1].split(
                "🔹",
                1,
            )[0],
        )


if __name__ == "__main__":
    unittest.main()
