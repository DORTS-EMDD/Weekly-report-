"""Import-safe MaiAgent HTTP and candidate-ID validation services.

Secrets and Streamlit UI objects are deliberately supplied by the caller. Importing
this module performs no HTTP request and does not import Streamlit.
"""

import os
import re
import json
import requests

from config import (
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
    FORMAL_REPORT_CATEGORY_MAP,
)

REPORT_CANDIDATE_ID_PATTERN = re.compile(r"<!--\s*candidate_id\s*:\s*(\d+)\s*-->", flags=re.IGNORECASE)
REPORT_ESCAPED_CANDIDATE_ID_PATTERN = re.compile(r"&lt;!--\s*candidate\\?_id\s*:\s*(\d+)\s*--&gt;", flags=re.IGNORECASE)
INTERNAL_CANDIDATE_MARKER_PATTERN = re.compile(r"<!--\s*candidate\\?_id\s*:\s*[^>]*-->", flags=re.IGNORECASE)
ESCAPED_INTERNAL_CANDIDATE_MARKER_PATTERN = re.compile(r"&lt;!--\s*candidate\\?_id\s*:\s*.*?--&gt;", flags=re.IGNORECASE)

MAIAGENT_CONNECT_TIMEOUT_SECONDS = 15
MAIAGENT_READ_TIMEOUT_SECONDS = 660
MAIAGENT_CONNECT_TIMEOUT_MIN_SECONDS = 1
MAIAGENT_CONNECT_TIMEOUT_MAX_SECONDS = 120
MAIAGENT_READ_TIMEOUT_MIN_SECONDS = 1
MAIAGENT_READ_TIMEOUT_MAX_SECONDS = 1800


def _bounded_timeout_seconds(
    env_name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(os.environ.get(env_name, ""))
    except (TypeError, ValueError):
        return default
    if not minimum <= value <= maximum:
        return default
    return value


def get_maiagent_timeout_seconds() -> tuple[int, int]:
    """Return bounded connect/read timeouts without changing the retry policy."""
    connect_timeout = _bounded_timeout_seconds(
        "MAIAGENT_CONNECT_TIMEOUT_SECONDS",
        MAIAGENT_CONNECT_TIMEOUT_SECONDS,
        minimum=MAIAGENT_CONNECT_TIMEOUT_MIN_SECONDS,
        maximum=MAIAGENT_CONNECT_TIMEOUT_MAX_SECONDS,
    )
    read_timeout = _bounded_timeout_seconds(
        "MAIAGENT_READ_TIMEOUT_SECONDS",
        MAIAGENT_READ_TIMEOUT_SECONDS,
        minimum=MAIAGENT_READ_TIMEOUT_MIN_SECONDS,
        maximum=MAIAGENT_READ_TIMEOUT_MAX_SECONDS,
    )
    return connect_timeout, read_timeout


def extract_maiagent_text(data) -> str:
    """寬鬆解析 MaiAgent 不同版本可能回傳的文字欄位。"""
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        for key in ("content", "text", "answer", "output", "response"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        message = data.get("message")
        if isinstance(message, dict):
            for key in ("content", "text", "answer"):
                value = message.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        content_payload = data.get("contentPayload") or data.get("content_payload")
        if isinstance(content_payload, dict):
            for key in ("content", "text", "answer"):
                value = content_payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            items = content_payload.get("items")
            if isinstance(items, list):
                texts = []
                for item in items:
                    if isinstance(item, dict):
                        value = item.get("text") or item.get("content") or item.get("answer")
                        if value:
                            texts.append(str(value))
                if texts:
                    return "\n".join(texts).strip()
        for key in ("result", "data"):
            nested = data.get(key)
            if isinstance(nested, (dict, str)):
                nested_text = extract_maiagent_text(nested)
                if nested_text and nested_text != str(nested):
                    return nested_text
    text = str(data).strip()
    if text:
        return text
    raise ValueError("MaiAgent 回應無文字內容")


def build_maiagent_request(prompt: str, api_key: str, chatbot_id: str, api_base: str):
    """Return the single request required by the MaiAgent v1 completions API."""
    base_url = api_base.rstrip("/")
    endpoint = f"{base_url}/api/v1/chatbots/{chatbot_id}/completions/"
    headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json", "Accept": "application/json"}
    payload = {
        "conversation": None,
        "message": {"content": prompt, "attachments": []},
        "is_streaming": False,
    }
    return endpoint, headers, payload


def _maiagent_log_excerpt(value, *, api_key: str, prompt: str) -> str:
    text = str(value or "")
    if api_key:
        text = text.replace(api_key, "[REDACTED_API_KEY]")
    if prompt:
        text = text.replace(prompt, "[REDACTED_PROMPT]")
    return text[:500]


def _format_maiagent_attempt_log(attempts: list[dict]) -> str:
    lines = ["MaiAgent attempt log:"]
    for index, attempt in enumerate(attempts, start=1):
        lines.extend([
            f"Attempt {index}:",
            f"  URL: {attempt.get('url', '')}",
            f"  Payload streaming field: {attempt.get('payload_streaming_field', '')}",
            f"  HTTP status: {attempt.get('http_status', '')}",
            f"  Timeout: connect={attempt.get('connect_timeout_seconds', '')}s, read={attempt.get('read_timeout_seconds', '')}s",
            f"  Response body: {attempt.get('response_body', '')}",
            f"  Location: {attempt.get('location', '')}",
            f"  Allow: {attempt.get('allow', '')}",
        ])
    return "\n".join(lines)


def call_maiagent_cloud(prompt: str, *, api_key: str, chatbot_id: str, api_base: str, http_client=requests) -> str:
    """Call the Streamlit V19.4 MaiAgent API without any UI dependency."""
    if not api_key:
        raise RuntimeError("未設定 MAIAGENT_API_KEY")
    if not chatbot_id:
        raise RuntimeError("未設定 MAIAGENT_CHATBOT_ID")
    url, headers, payload = build_maiagent_request(prompt, api_key, chatbot_id, api_base)
    connect_timeout, read_timeout = get_maiagent_timeout_seconds()
    payload_streaming_field = (
        "isStreaming" if "isStreaming" in payload
        else "is_streaming" if "is_streaming" in payload
        else "none"
    )
    attempt_log: list[dict] = []
    try:
        response = http_client.post(
            url,
            headers=headers,
            json=payload,
            timeout=(connect_timeout, read_timeout),
        )
    except Exception as exc:
        attempt_log.append({
            "url": _maiagent_log_excerpt(url, api_key=api_key, prompt=prompt),
            "payload_streaming_field": payload_streaming_field,
            "http_status": "N/A",
            "connect_timeout_seconds": connect_timeout,
            "read_timeout_seconds": read_timeout,
            "response_body": _maiagent_log_excerpt(
                f"Request error: {exc}", api_key=api_key, prompt=prompt
            ),
            "location": "",
            "allow": "",
        })
        raise RuntimeError(
            f"MaiAgent API 所有嘗試均失敗。\n{_format_maiagent_attempt_log(attempt_log)}"
        ) from exc

    attempt_log.append({
        "url": _maiagent_log_excerpt(url, api_key=api_key, prompt=prompt),
        "payload_streaming_field": payload_streaming_field,
        "http_status": response.status_code,
        "connect_timeout_seconds": connect_timeout,
        "read_timeout_seconds": read_timeout,
        "response_body": _maiagent_log_excerpt(
            response.text, api_key=api_key, prompt=prompt
        ),
        "location": _maiagent_log_excerpt(
            response.headers.get("Location", ""), api_key=api_key, prompt=prompt
        ),
        "allow": _maiagent_log_excerpt(
            response.headers.get("Allow", ""), api_key=api_key, prompt=prompt
        ),
    })

    if not 200 <= response.status_code < 300:
        raise RuntimeError(
            f"MaiAgent API 所有嘗試均失敗。\n{_format_maiagent_attempt_log(attempt_log)}"
        )

    try:
        data = response.json()
    except ValueError:
        return response.text.strip()
    return extract_maiagent_text(data)


def ensure_selected_candidate_ids(selected_candidates: list[dict]) -> list[dict]:
    seen: set[int] = set()
    for candidate in selected_candidates or []:
        candidate_id = int(candidate.get("candidate_id") or candidate.get("id") or 0)
        if candidate_id <= 0 or candidate_id in seen:
            raise ValueError(f"selected candidate_id 無效或重複：{candidate_id}")
        seen.add(candidate_id)
        candidate["candidate_id"] = candidate_id
    return selected_candidates


def extract_report_candidate_ids(text: str) -> list[int]:
    matches = [(match.start(), int(match.group(1))) for pattern in (REPORT_CANDIDATE_ID_PATTERN, REPORT_ESCAPED_CANDIDATE_ID_PATTERN) for match in pattern.finditer(text or "")]
    return [candidate_id for _, candidate_id in sorted(matches)]


def remove_internal_candidate_markers(text: str) -> str:
    if not text:
        return ""
    cleaned = INTERNAL_CANDIDATE_MARKER_PATTERN.sub("", text)
    cleaned = ESCAPED_INTERNAL_CANDIDATE_MARKER_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def validate_report_candidate_ids(report_md: str, selected_candidates: list[dict]) -> dict:
    expected_ids = [int(item.get("candidate_id") or item.get("id") or 0) for item in selected_candidates or []]
    found_ids = extract_report_candidate_ids(report_md)
    expected_set, found_set = set(expected_ids), set(found_ids)
    duplicate_ids = sorted({value for value in found_ids if found_ids.count(value) > 1})
    return {"expected_ids": expected_ids, "found_ids": found_ids, "missing_ids": [value for value in expected_ids if value not in found_set], "unknown_ids": sorted(found_set - expected_set), "duplicate_ids": duplicate_ids, "valid": found_set == expected_set and not duplicate_ids and len(found_ids) == len(expected_ids)}


_FORMAL_RETRY_CATEGORIES = {
    "技術新知",
    "重大事故",
    "營運動態",
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
}


def _canonical_retry_category(value: object) -> str:
    category = str(value or "").strip()
    if category == "營運議題":
        return "營運動態"
    if category == ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY:
        return ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL
    return FORMAL_REPORT_CATEGORY_MAP.get(category, category)


def _retry_category_map(selected_candidates: list[dict] | None) -> dict[str, str]:
    category_map: dict[str, str] = {}
    for candidate in selected_candidates or []:
        raw_id = candidate.get("candidate_id") or candidate.get("id")
        try:
            candidate_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if candidate_id <= 0:
            continue
        raw_category = next(
            (
                candidate.get(key)
                for key in (
                    "classification",
                    "primary_category",
                    "preliminary_type",
                    "category",
                    "category_key",
                )
                if candidate.get(key)
            ),
            "",
        )
        category_map[str(candidate_id)] = _canonical_retry_category(raw_category)
    return category_map


def build_report_retry_prompt(
    original_prompt: str,
    previous_response: str,
    validation: dict,
    *,
    selected_candidates: list[dict] | None = None,
) -> str:
    quality_issues = validation.get("content_quality_issues", [])
    multi_candidate_blocks = validation.get("multi_candidate_model_blocks", [])
    duplicate_ids = validation.get("duplicate_ids", [])
    category_mismatches = validation.get("category_mismatches", [])
    category_map = _retry_category_map(selected_candidates)
    category_map_text = json.dumps(category_map, ensure_ascii=False, sort_keys=True)
    category_mismatches_text = json.dumps(
        category_mismatches,
        ensure_ascii=False,
        sort_keys=True,
    )
    return f"""{original_prompt}

## 輸出完整性重試
上一次輸出未通過正式報告驗證。
- 缺少 ID：{validation.get('missing_ids', [])}
- 未知 ID：{validation.get('unknown_ids', [])}
- 重複 ID：{duplicate_ids}
- 多候選 marker block：{multi_candidate_blocks}
- 內容品質問題：{quality_issues}
這是 COMPLETE REPLACEMENT REPORT（完整替換報告），不是 append、patch 或 delta。請忽略上一次報告的版面結構，從權威候選全集重新建立一份完整報告；只輸出這份完整替換報告，不得在舊報告後附加修正。
權威 candidate/category map（只能依此分類；依候選資料中的 authoritative classification 建立）：{category_map_text}
每個 selected candidate_id 必須恰好出現一次，不能遺漏、不能使用未知 ID、不能重複；正式類別只能是「技術新知」、「重大事故」、「營運動態」或「機電標案」。標記格式必須是 `<!-- candidate_id: N -->`，並緊接在該則正式新聞標題前。每個正式新聞 block 必須且只能包含一個 candidate marker。
若重複 ID 不為空，這些 runtime candidate IDs 各出現超過一次；每個 ID 只保留一個 block，移除該 ID 的其他重複 block，不得以其他 candidate ID 取代，也不得把重複 ID 合併成單一 block。
若「多候選 marker block」不為空，列出的每組 candidate IDs 均為無效 block；請將它們改寫為各自獨立的完整新聞 block。即使描述同一事件也不得合併，不得把任何 candidate ID 靜默省略，所有有效 candidate IDs 必須各出現一次。不得只補局部段落。
分類不一致診斷：{category_mismatches_text}
若分類不一致診斷不為空，請逐一依 candidate_id 對照上方權威 map 修正：expected_category 是唯一正確類別，actual_category 只是錯誤診斷；將該 block 移至 expected category 的正式章節，不得把 candidate 移到其他類別或以另一個 candidate 取代。

## INVALID PREVIOUS OUTPUT — REFERENCE ONLY
以下上一次輸出只能用來辨識錯誤，禁止盲目複製其結構，禁止在其後附加修正，不得輸出 patch/delta；請依上述權威候選與分類 map 重新建立完整 replacement report：
{previous_response}
""".strip()
