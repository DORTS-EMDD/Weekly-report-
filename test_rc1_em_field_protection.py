import datetime
import unittest

from report_workflow_service import (
    WorkflowConfig,
    WorkflowDependencies,
    make_runtime,
)


def _runtime():
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
        report_title="RC-1 fixture",
        report_scope_label="全球",
        report_period_label="週報",
    )
    return make_runtime(config, WorkflowDependencies(prefetch_enabled=False))


def _candidate() -> dict:
    return {
        "id": 1,
        "candidate_id": 1,
        "title": "Metro deploys CBTC signalling",
        "snippet": "The metro deployed a CBTC signalling system.",
        "date": "2026-08-10",
        "region": "美國",
        "query_region": "美國",
        "source": "Fixture Source",
        "source_display": "Fixture Source",
        "source_domain": "example.com",
        "source_href": "https://example.com/rc1",
        "url": "https://example.com/rc1",
        "source_tier": "B_professional",
        "source_quality": "A",
    }


def _model_report(system_value: str) -> str:
    return "\n".join([
        "## 一、技術新知",
        "<!-- candidate_id: 1 -->",
        "🔹 [技術新知] CBTC 號誌部署",
        "• 發布/事件日期：2026-08-10",
        "• 國家：美國",
        f"• 相關機電系統：{system_value}",
        "• 事件摘要：捷運完成 CBTC 號誌系統部署。",
        "• 臺北捷運局啟示：可參考號誌系統驗證與介面管理。",
        "• 資料來源：Fixture Source https://example.com/rc1",
    ])


class RC1EMFieldProtectionTests(unittest.TestCase):
    def test_taxonomy_to_final_report_protects_candidate_owned_system(self):
        runtime = _runtime()
        candidate = _candidate()
        runtime._materialize_authoritative_candidate(candidate)

        self.assertEqual(candidate["core_systems"], ["號誌"])
        result = runtime.postprocess_report_with_diagnostics(
            _model_report("都市軌道系統（模型自行判斷）"),
            [candidate],
        )

        rendered = result["clean_report"]
        self.assertIn("• 相關機電系統：號誌系統", rendered)
        self.assertNotIn("都市軌道系統（模型自行判斷）", rendered)
        self.assertTrue(result["id_validation"]["report_validation_passed"])

    def test_explicit_empty_core_systems_removes_model_system_line(self):
        runtime = _runtime()
        candidate = _candidate()
        candidate.update({
            "core_systems": [],
            "authoritative_materialization_stage": "post_enrichment",
        })

        result = runtime.postprocess_report_with_diagnostics(
            _model_report("泛稱都市軌道系統"),
            [candidate],
        )

        rendered = result["clean_report"]
        self.assertNotIn("相關機電系統", rendered)
        self.assertNotIn("泛稱都市軌道系統", rendered)
        self.assertTrue(result["id_validation"]["report_validation_passed"])


if __name__ == "__main__":
    unittest.main()
