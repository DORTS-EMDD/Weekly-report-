"""Semantic support judgment for authoritative report summaries.

This module owns only the claim-support judgment boundary.  It never
materializes, enriches, or reclassifies candidate evidence.  The caller passes
the immutable ``candidate["evidence"]`` contract and receives a structured
verdict that is grounded back to quoted source text.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Callable


ALLOWED_EVIDENCE_FIELDS = frozenset({"feed_snippet", "article_excerpt"})
ALLOWED_SUPPORT_STATUSES = frozenset({"SUPPORTED", "UNSUPPORTED", "UNCERTAIN"})
ALLOWED_SUMMARY_STATUSES = frozenset(
    {
        "TITLE_COPY",
        "TITLE_PARAPHRASE",
        "TITLE_ONLY",
        "EVIDENCE_SUPPORTED",
        "INSUFFICIENT_EVIDENCE",
    }
)
ALLOWED_SEMANTIC_STATES = frozenset({"SUPPORTED", "SEMANTIC_FAIL"})

SEMANTIC_VALIDATION_UNAVAILABLE = "SEMANTIC_VALIDATION_UNAVAILABLE"
SEMANTIC_VALIDATION_INVALID_RESPONSE = "SEMANTIC_VALIDATION_INVALID_RESPONSE"


class SemanticValidationInvalidResponse(ValueError):
    """Raised when a judge response cannot satisfy the V1 response contract."""


def _candidate_id(candidate: dict) -> int:
    try:
        return int(candidate.get("candidate_id") or candidate.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def _normalized_whitespace(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def build_semantic_validation_payload(
    candidate: dict,
    summary: str,
    *,
    title: str = "",
) -> dict:
    """Build the immutable V1 judge payload without any evidence fallback."""
    evidence = candidate.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    return {
        "candidate_id": _candidate_id(candidate),
        "title": str(title or candidate.get("title") or ""),
        "event_summary": str(summary or ""),
        "evidence": {
            "feed_snippet": str(evidence.get("feed_snippet") or ""),
            "article_excerpt": str(evidence.get("article_excerpt") or ""),
            "provenance": str(evidence.get("provenance") or "none"),
            "richness": str(evidence.get("richness") or "title_only"),
        },
    }


def build_semantic_validation_prompt(payload: dict) -> str:
    """Build a dedicated judgment prompt, separate from report generation."""
    evidence_payload = payload.get("evidence", {}) or {}
    factual_evidence = {
        "feed_snippet": evidence_payload.get("feed_snippet", ""),
        "article_excerpt": evidence_payload.get("article_excerpt", ""),
        "provenance": evidence_payload.get("provenance", "none"),
        "richness": evidence_payload.get("richness", "title_only"),
    }
    request = {
        "candidate_id": payload.get("candidate_id", 0),
        "title": payload.get("title", ""),
        "event_summary": payload.get("event_summary", ""),
        "evidence": factual_evidence,
    }
    return (
        "你是獨立的摘要事實支持判定器，不是報告撰寫器。只能判斷下列 "
        "authoritative evidence 是否支持摘要中的每一項 substantive factual claim。"
        "不得搜尋、補充、改寫或使用標題以外的外部知識。請只回傳 JSON，不要 markdown。\n"
        "輸出 schema：{candidate_id, summary_status, semantic_state, failure_reason, "
        "claims:[{claim_text, support_status, evidence_mappings:[{evidence_field, evidence_quote}]}]}。"
        "support_status 只能是 SUPPORTED、UNSUPPORTED 或 UNCERTAIN；"
        "semantic_state 只能是 SUPPORTED 或 SEMANTIC_FAIL。"
        "每一 claim 必須有至少一個 mapping，mapping 欄位只能是 feed_snippet 或 article_excerpt，"
        "quote 必須逐字存在於指定 evidence 欄位（可忽略空白差異）。"
        "只有所有 substantive claims 都是 SUPPORTED 才可使用 EVIDENCE_SUPPORTED；"
        "partial support、額外事實、實體/日期/數字/金額/營運不一致都必須判定 UNSUPPORTED 或 UNCERTAIN。\n"
        f"INPUT={json.dumps(request, ensure_ascii=False, sort_keys=True)}"
    )


def _parse_provider_response(response: object) -> dict:
    if isinstance(response, dict):
        return deepcopy(response)
    text = str(response or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except (TypeError, ValueError) as exc:
        # Permit a JSON object embedded in a short provider wrapper while
        # remaining strict about the object itself.
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise SemanticValidationInvalidResponse("judge response is not valid JSON") from exc
        try:
            value = json.loads(text[start : end + 1])
        except (TypeError, ValueError) as nested_exc:
            raise SemanticValidationInvalidResponse("judge response is not valid JSON") from nested_exc
    if not isinstance(value, dict):
        raise SemanticValidationInvalidResponse("judge response must be an object")
    return value


def ground_semantic_validation(response: dict, payload: dict) -> dict:
    """Validate schema and quote grounding without performing semantic judgment."""
    if not isinstance(response, dict):
        raise SemanticValidationInvalidResponse("response must be an object")
    try:
        response_id = int(response.get("candidate_id"))
    except (TypeError, ValueError) as exc:
        raise SemanticValidationInvalidResponse("candidate_id is invalid") from exc
    if response_id != int(payload.get("candidate_id") or 0):
        raise SemanticValidationInvalidResponse("candidate_id mismatch")
    summary_status = str(response.get("summary_status") or "").strip().upper()
    semantic_state = str(response.get("semantic_state") or "").strip().upper()
    if summary_status not in ALLOWED_SUMMARY_STATUSES:
        raise SemanticValidationInvalidResponse("summary_status is invalid")
    if semantic_state not in ALLOWED_SEMANTIC_STATES:
        raise SemanticValidationInvalidResponse("semantic_state is invalid")
    if "failure_reason" not in response or not isinstance(response.get("failure_reason"), str):
        raise SemanticValidationInvalidResponse("failure_reason is invalid")
    failure_reason = response["failure_reason"]
    claims = response.get("claims")
    if not isinstance(claims, list) or not claims:
        raise SemanticValidationInvalidResponse("claims must be a non-empty list")

    evidence = payload.get("evidence") or {}
    grounded_claims: list[dict] = []
    for claim in claims:
        if not isinstance(claim, dict):
            raise SemanticValidationInvalidResponse("claim must be an object")
        claim_text = str(claim.get("claim_text") or "").strip()
        support_status = str(claim.get("support_status") or "").strip().upper()
        mappings = claim.get("evidence_mappings")
        if not claim_text or support_status not in ALLOWED_SUPPORT_STATUSES:
            raise SemanticValidationInvalidResponse("claim fields are invalid")
        if not isinstance(mappings, list) or not mappings:
            raise SemanticValidationInvalidResponse("claim evidence mapping is missing")
        grounded_mappings: list[dict] = []
        for mapping in mappings:
            if not isinstance(mapping, dict):
                raise SemanticValidationInvalidResponse("evidence mapping must be an object")
            field = str(mapping.get("evidence_field") or "").strip()
            quote = str(mapping.get("evidence_quote") or "").strip()
            if field not in ALLOWED_EVIDENCE_FIELDS or not quote:
                raise SemanticValidationInvalidResponse("evidence mapping field is invalid")
            source_text = _normalized_whitespace(evidence.get(field, ""))
            normalized_quote = _normalized_whitespace(quote)
            if not source_text or normalized_quote not in source_text:
                raise SemanticValidationInvalidResponse("evidence quote is not grounded")
            grounded_mappings.append({
                "evidence_field": field,
                "evidence_quote": quote,
            })
        grounded_claims.append({
            "claim_text": claim_text,
            "support_status": support_status,
            "evidence_mappings": grounded_mappings,
        })

    all_supported = all(
        claim["support_status"] == "SUPPORTED" for claim in grounded_claims
    )
    if semantic_state == "SUPPORTED" and (summary_status != "EVIDENCE_SUPPORTED" or not all_supported):
        raise SemanticValidationInvalidResponse(
            "SUPPORTED verdict requires EVIDENCE_SUPPORTED and all claims SUPPORTED"
        )
    if semantic_state == "SEMANTIC_FAIL" and all_supported:
        raise SemanticValidationInvalidResponse(
            "SEMANTIC_FAIL requires an unsupported or uncertain claim"
        )
    return {
        "candidate_id": response_id,
        "summary_status": summary_status,
        "semantic_state": semantic_state,
        "failure_reason": failure_reason,
        "claims": grounded_claims,
        "grounding_passed": True,
    }


class SemanticSupportJudge:
    """Independent semantic-support owner backed by an injected provider."""

    def __init__(self, provider: Callable[[str], object], *, max_attempts: int = 2):
        self.provider = provider
        self.max_attempts = max(1, int(max_attempts))

    def validate(self, payload: dict) -> dict:
        prompt = build_semantic_validation_prompt(payload)
        last_error = ""
        unavailable = False
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw_response = self.provider(prompt)
            except Exception as exc:  # provider boundary is intentionally opaque
                unavailable = True
                last_error = str(exc) or exc.__class__.__name__
                continue
            try:
                grounded = ground_semantic_validation(
                    _parse_provider_response(raw_response),
                    payload,
                )
            except SemanticValidationInvalidResponse as exc:
                unavailable = False
                last_error = str(exc)
                continue
            grounded["attempts"] = attempt
            return grounded
        if unavailable:
            state = SEMANTIC_VALIDATION_UNAVAILABLE
        else:
            state = SEMANTIC_VALIDATION_INVALID_RESPONSE
        return {
            "candidate_id": int(payload.get("candidate_id") or 0),
            "summary_status": "INSUFFICIENT_EVIDENCE",
            "semantic_state": state,
            "failure_reason": last_error,
            "claims": [],
            "grounding_passed": False,
            "attempts": self.max_attempts,
        }

    __call__ = validate


def run_semantic_validation(
    summary: str,
    title: str,
    candidate: dict,
    *,
    judge: object | None,
) -> dict:
    """Run one bounded judge operation against the candidate evidence contract."""
    payload = build_semantic_validation_payload(candidate, summary, title=title)
    if judge is None:
        return {
            "candidate_id": payload["candidate_id"],
            "summary_status": "INSUFFICIENT_EVIDENCE",
            "semantic_state": SEMANTIC_VALIDATION_UNAVAILABLE,
            "failure_reason": "semantic judge was not configured",
            "claims": [],
            "grounding_passed": False,
            "attempts": 0,
        }
    try:
        validator = getattr(judge, "validate", None)
        result = validator(payload) if callable(validator) else judge(payload)
    except Exception as exc:
        return {
            "candidate_id": payload["candidate_id"],
            "summary_status": "INSUFFICIENT_EVIDENCE",
            "semantic_state": SEMANTIC_VALIDATION_UNAVAILABLE,
            "failure_reason": str(exc) or exc.__class__.__name__,
            "claims": [],
            "grounding_passed": False,
            "attempts": 1,
        }
    if not isinstance(result, dict):
        return {
            "candidate_id": payload["candidate_id"],
            "summary_status": "INSUFFICIENT_EVIDENCE",
            "semantic_state": SEMANTIC_VALIDATION_INVALID_RESPONSE,
            "failure_reason": "semantic judge returned a non-object",
            "claims": [],
            "grounding_passed": False,
            "attempts": 1,
        }
    result_state = str(result.get("semantic_state") or "").strip().upper()
    if result_state in {
        SEMANTIC_VALIDATION_UNAVAILABLE,
        SEMANTIC_VALIDATION_INVALID_RESPONSE,
    }:
        return {
            "candidate_id": payload["candidate_id"],
            "summary_status": str(result.get("summary_status") or "INSUFFICIENT_EVIDENCE"),
            "semantic_state": result_state,
            "failure_reason": str(result.get("failure_reason") or ""),
            "claims": list(result.get("claims") or []),
            "grounding_passed": False,
            "attempts": int(result.get("attempts") or 1),
        }
    try:
        grounded = ground_semantic_validation(result, payload)
    except SemanticValidationInvalidResponse as exc:
        return {
            "candidate_id": payload["candidate_id"],
            "summary_status": "INSUFFICIENT_EVIDENCE",
            "semantic_state": SEMANTIC_VALIDATION_INVALID_RESPONSE,
            "failure_reason": str(exc),
            "claims": [],
            "grounding_passed": False,
            "attempts": int(result.get("attempts") or 1),
        }
    grounded["attempts"] = int(result.get("attempts") or 1)
    return grounded
