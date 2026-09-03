import json
import unittest

from report_postprocessor import validate_authoritative_report
from semantic_validation_service import (
    SEMANTIC_VALIDATION_INVALID_RESPONSE,
    SEMANTIC_VALIDATION_UNAVAILABLE,
    SemanticSupportJudge,
    build_semantic_validation_payload,
    ground_semantic_validation,
)


FEED = "The operator announced a CBTC signalling deployment for the urban rail system."
ARTICLE = (
    "The metro completed a CBTC signalling test on Line 1. "
    "The operator will publish the commissioning schedule."
)


def candidate(*, title="Metro announces CBTC deployment", evidence=None):
    return {
        "id": 1,
        "candidate_id": 1,
        "title": title,
        "date": "2026-08-10",
        "country": "美國",
        "classification": "技術新知",
        "preliminary_type": "技術新知",
        "source_display": "Fixture Source",
        "source_domain": "example.com",
        "source_href": "https://example.com/articles/cbtc",
        "url": "https://example.com/articles/cbtc",
        "core_systems": [],
        "evidence": evidence or {
            "feed_snippet": FEED,
            "article_excerpt": ARTICLE,
            "provenance": "feed+prefetch",
            "richness": "feed+article",
        },
    }


def report(summary: str, *, title="捷運完成號誌測試") -> str:
    return "\n".join(
        [
            "## 一、技術新知",
            "<!-- candidate_id: 1 -->",
            f"🔹 [技術新知] {title}",
            "• 發布/事件日期：2026-08-10",
            "• 國家：美國",
            f"• 事件摘要：{summary}",
            "• 臺北捷運局啟示：可參考號誌測試與營運轉換管理。",
            "• 資料來源：Fixture Source https://example.com/articles/cbtc",
        ]
    )


def grounded_result(payload: dict, *, supported=True, quote=None) -> dict:
    evidence = payload["evidence"]
    field = "feed_snippet" if evidence.get("feed_snippet") else "article_excerpt"
    return {
        "candidate_id": payload["candidate_id"],
        "summary_status": "EVIDENCE_SUPPORTED" if supported else "INSUFFICIENT_EVIDENCE",
        "semantic_state": "SUPPORTED" if supported else "SEMANTIC_FAIL",
        "failure_reason": "" if supported else "unsupported factual claim",
        "claims": [
            {
                "claim_text": payload["event_summary"],
                "support_status": "SUPPORTED" if supported else "UNSUPPORTED",
                "evidence_mappings": [
                    {
                        "evidence_field": field,
                        "evidence_quote": quote if quote is not None else evidence[field],
                    }
                ],
            }
        ],
    }


class RC3DSemanticValidationTests(unittest.TestCase):
    def test_payload_preserves_layered_evidence_and_never_uses_legacy_snippet(self):
        item = candidate()
        item["snippet"] = "legacy merged fallback must not be read"
        payload = build_semantic_validation_payload(
            item,
            "The metro completed a signalling test.",
        )
        self.assertEqual(payload["evidence"]["feed_snippet"], FEED)
        self.assertEqual(payload["evidence"]["article_excerpt"], ARTICLE)
        self.assertNotIn("legacy merged fallback must not be read", json.dumps(payload))

    def test_grounding_requires_contiguous_quote_and_allowed_field(self):
        item = candidate()
        payload = build_semantic_validation_payload(item, "The metro completed a signalling test.")
        valid = ground_semantic_validation(grounded_result(payload), payload)
        self.assertTrue(valid["grounding_passed"])
        invalid_quote = grounded_result(payload, quote="text not present")
        with self.assertRaises(ValueError):
            ground_semantic_validation(invalid_quote, payload)
        invalid_field = grounded_result(payload)
        invalid_field["claims"][0]["evidence_mappings"][0]["evidence_field"] = "snippet"
        with self.assertRaises(ValueError):
            ground_semantic_validation(invalid_field, payload)

    def test_judge_retries_unavailable_once_then_returns_invalid_or_unavailable(self):
        calls = []

        def unavailable(_prompt):
            calls.append(True)
            raise TimeoutError("timeout")

        judge = SemanticSupportJudge(unavailable)
        result = judge.validate(
            build_semantic_validation_payload(candidate(), "A summary.")
        )
        self.assertEqual(result["semantic_state"], SEMANTIC_VALIDATION_UNAVAILABLE)
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(len(calls), 2)

    def test_judge_retries_malformed_response_once(self):
        calls = []

        def malformed(_prompt):
            calls.append(True)
            return "not json"

        judge = SemanticSupportJudge(malformed)
        result = judge.validate(
            build_semantic_validation_payload(candidate(), "A summary.")
        )
        self.assertEqual(result["semantic_state"], SEMANTIC_VALIDATION_INVALID_RESPONSE)
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(len(calls), 2)

    def test_judge_accepts_structured_grounded_response(self):
        item = candidate()

        def provider(prompt):
            payload = json.loads(prompt.split("INPUT=", 1)[1])
            return json.dumps(grounded_result(payload), ensure_ascii=False)

        result = SemanticSupportJudge(provider).validate(
            build_semantic_validation_payload(item, "The operator announced a CBTC deployment.")
        )
        self.assertEqual(result["semantic_state"], "SUPPORTED")
        self.assertTrue(result["grounding_passed"])

    def test_unsupported_fare_change_is_not_accepted_by_lexical_overlap(self):
        item = candidate()

        def fail_judge(payload):
            return grounded_result(payload, supported=False)

        validation = validate_authoritative_report(
            report("The operator announced fare changes for the urban rail system."),
            [item],
            selected_types=["技術新知"],
            semantic_judge=fail_judge,
            semantic_validation_required=True,
        )
        self.assertEqual(validation["summary_evidence_status"]["1"], "insufficient_evidence")
        self.assertFalse(validation["report_validation_passed"])
        self.assertEqual(validation["semantic_validation_states"], ["SEMANTIC_FAIL"])

    def test_semantic_unavailable_blocks_without_requesting_report_retry(self):
        item = candidate()

        def unavailable(_payload):
            raise TimeoutError("provider unavailable")

        validation = validate_authoritative_report(
            report("The operator announced a signalling deployment."),
            [item],
            selected_types=["技術新知"],
            semantic_judge=unavailable,
            semantic_validation_required=True,
        )
        self.assertFalse(validation["report_validation_passed"])
        self.assertFalse(validation["report_retry_allowed"])
        self.assertEqual(
            validation["summary_evidence_status"]["1"],
            "semantic_validation_unavailable",
        )

    def test_semantic_fail_is_the_only_semantic_state_that_allows_one_report_retry(self):
        item = candidate()

        def fail_judge(payload):
            return grounded_result(payload, supported=False)

        validation = validate_authoritative_report(
            report("The operator announced fare changes for the urban rail system."),
            [item],
            selected_types=["技術新知"],
            semantic_judge=fail_judge,
            semantic_validation_required=True,
        )
        self.assertTrue(validation["report_retry_allowed"])

    def test_supported_summary_requires_all_claims_supported(self):
        item = candidate()

        def invalid_supported(payload):
            result = grounded_result(payload)
            result["claims"][0]["support_status"] = "UNSUPPORTED"
            return result

        validation = validate_authoritative_report(
            report("The agency began passenger service tomorrow."),
            [item],
            selected_types=["技術新知"],
            semantic_judge=invalid_supported,
            semantic_validation_required=True,
        )
        self.assertFalse(validation["report_validation_passed"])
        self.assertIn("semantic_validation_invalid_response", {
            issue["code"] for issue in validation["content_quality_issues"]
        })

    def test_title_states_precede_semantic_judge_and_title_only_never_retries(self):
        calls = []

        def judge(payload):
            calls.append(payload)
            return grounded_result(payload)

        rich = candidate(title="Metro announces CBTC deployment")
        title_copy = validate_authoritative_report(
            report("Metro announces CBTC deployment", title="Metro announces CBTC deployment"),
            [rich],
            selected_types=["技術新知"],
            semantic_judge=judge,
            semantic_validation_required=True,
        )
        self.assertEqual(title_copy["summary_evidence_status"]["1"], "title_copy")
        self.assertEqual(calls, [])

        title_only = candidate(
            title="Only a headline",
            evidence={
                "feed_snippet": "",
                "article_excerpt": "",
                "provenance": "none",
                "richness": "title_only",
            },
        )
        title_only_result = validate_authoritative_report(
            report("A new event occurred", title="Only a headline"),
            [title_only],
            selected_types=["技術新知"],
            semantic_judge=judge,
            semantic_validation_required=True,
        )
        self.assertEqual(title_only_result["summary_evidence_status"]["1"], "insufficient_evidence")
        self.assertFalse(title_only_result["report_retry_allowed"])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
