import unittest

from maiagent_service import build_report_retry_prompt
from report_postprocessor import (
    canonical_formal_report_category,
    validate_authoritative_report,
)
import streamlit_app as app


FORMAL_CATEGORY_CONTRACT = "正式新聞類型標籤只能使用「技術新知」、「重大事故」、「營運動態」或「機電標案」"


def _candidate(candidate_id: int, category: str) -> dict:
    url = f"https://example.com/p2k5-12r2h/{candidate_id}"
    return {
        "candidate_id": candidate_id,
        "id": candidate_id,
        "title": f"Fixture event {candidate_id}",
        "snippet": "都市軌道系統發生可核實的設備或營運事件。",
        "date": "2026-08-18",
        "country": "日本",
        "classification": category,
        "preliminary_type": category,
        "core_systems": ["號誌系統"],
        "source_display": "Fixture Source",
        "source_domain": "example.com",
        "url": url,
        "source_href": url,
    }


def _block(candidate_id: int, category: str, url: str) -> str:
    return "\n".join([
        f"<!-- candidate_id: {candidate_id} -->",
        f"🔹 [{category}] Fixture event {candidate_id}",
        "• 發布/事件日期：2026-08-18",
        "• 國家：日本",
        "• 相關機電系統：號誌系統",
        "• 事件摘要：都市軌道系統發生可核實的設備或營運事件。",
        "• 臺北捷運局啟示：可作為系統備援與事件驗證安排的參考。",
        f"• 資料來源：Fixture Source，2026-08-18，{url}",
    ])


def _validate(expected: str, actual: str) -> dict:
    candidate = _candidate(7, expected)
    heading = {
        "技術新知": "一、技術新知",
        "重大事故": "二、重大事故",
        "營運政策": "三、營運動態",
        "營運爭議": "三、營運動態",
        "營運動態": "三、營運動態",
        "機電標案": "四、機電標案",
    }[expected]
    report = f"## {heading}\n{_block(7, actual, candidate['url'])}"
    return validate_authoritative_report(
        report,
        [candidate],
        selected_types=[expected],
    )


class P2K5R2HCategoryContractTests(unittest.TestCase):
    def test_operational_policy_alias_passes_as_formal_dynamics(self):
        validation = _validate("營運動態", "營運政策")
        self.assertTrue(validation["report_validation_passed"])

    def test_operational_dispute_alias_passes_as_formal_dynamics(self):
        validation = _validate("營運動態", "營運爭議")
        self.assertTrue(validation["report_validation_passed"])

    def test_canonical_operational_label_passes(self):
        validation = _validate("營運動態", "營運動態")
        self.assertTrue(validation["report_validation_passed"])

    def test_technical_candidate_cannot_use_operational_alias(self):
        validation = _validate("技術新知", "營運政策")
        self.assertFalse(validation["report_validation_passed"])
        self.assertEqual(validation["category_mismatches"][0]["actual_category"], "營運動態")

    def test_accident_candidate_cannot_use_operational_label(self):
        validation = _validate("重大事故", "營運動態")
        self.assertFalse(validation["report_validation_passed"])

    def test_procurement_candidate_cannot_use_operational_label(self):
        validation = _validate("機電標案", "營運動態")
        self.assertFalse(validation["report_validation_passed"])

    def test_reconciliation_keeps_candidate_id_and_authoritative_category(self):
        candidate = _candidate(7, "營運政策")
        report = _block(7, "營運政策", candidate["url"])
        original_types = app.selected_types
        try:
            app.selected_types = ["營運政策"]
            output, diagnostics = app.reconcile_report_candidate_output(report, [candidate])
        finally:
            app.selected_types = original_types
        self.assertEqual(app.extract_report_candidate_ids(output), [7])
        self.assertIn("🔹 [營運動態]", output)
        self.assertEqual(diagnostics["skipped_candidate_ids"], [])
        self.assertEqual(diagnostics["fallback_block_count"], 0)

    def test_retry_prompt_reuses_formal_category_contract(self):
        retry = build_report_retry_prompt(
            FORMAL_CATEGORY_CONTRACT,
            "previous response",
            {"missing_ids": [], "unknown_ids": [], "duplicate_ids": []},
        )
        self.assertIn(FORMAL_CATEGORY_CONTRACT, retry)
        self.assertIn("依候選資料中的 authoritative classification", retry)

    def test_normal_report_prompt_declares_formal_category_contract(self):
        candidate = _candidate(7, "營運政策")
        prompt = app.build_report_prompt([candidate], [], 1)
        self.assertIn(FORMAL_CATEGORY_CONTRACT, prompt)
        self.assertNotIn("🔹 [營運政策]", prompt)
        self.assertNotIn("🔹 [營運爭議]", prompt)

    def test_alias_normalization_is_narrow_and_cross_category_mismatch_remains(self):
        self.assertEqual(canonical_formal_report_category("營運政策"), "營運動態")
        self.assertEqual(canonical_formal_report_category("營運爭議"), "營運動態")
        self.assertEqual(canonical_formal_report_category("技術新知"), "技術新知")
        self.assertNotEqual(canonical_formal_report_category("技術新知"), "營運動態")


if __name__ == "__main__":
    unittest.main()
