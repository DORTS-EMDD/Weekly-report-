"""Import-safe MaiAgent HTTP and candidate-ID validation services.

Secrets and Streamlit UI objects are deliberately supplied by the caller. Importing
this module performs no HTTP request and does not import Streamlit.
"""

import re
import requests

REPORT_CANDIDATE_ID_PATTERN = re.compile(r"<!--\s*candidate_id\s*:\s*(\d+)\s*-->", flags=re.IGNORECASE)
REPORT_ESCAPED_CANDIDATE_ID_PATTERN = re.compile(r"&lt;!--\s*candidate\\?_id\s*:\s*(\d+)\s*--&gt;", flags=re.IGNORECASE)
INTERNAL_CANDIDATE_MARKER_PATTERN = re.compile(r"<!--\s*candidate\\?_id\s*:\s*[^>]*-->", flags=re.IGNORECASE)
ESCAPED_INTERNAL_CANDIDATE_MARKER_PATTERN = re.compile(r"&lt;!--\s*candidate\\?_id\s*:\s*.*?--&gt;", flags=re.IGNORECASE)


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


def build_maiagent_request_attempts(prompt: str, api_key: str, chatbot_id: str, api_base: str):
    """Return the exact V19.4 endpoint/header/payload attempt sequence."""
    base_url = api_base.rstrip("/")
    endpoint = f"{base_url}/api/chatbots/{chatbot_id}/completions"
    v1_endpoint = f"{base_url}/api/v1/chatbots/{chatbot_id}/completions"
    headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json", "Accept": "application/json"}
    payloads = [
        {"message": {"content": prompt}, "isStreaming": False},
        {"message": {"content": prompt}, "is_streaming": False},
    ]
    return [endpoint + "/", endpoint, v1_endpoint + "/", v1_endpoint], headers, payloads


def call_maiagent_cloud(prompt: str, *, api_key: str, chatbot_id: str, api_base: str, http_client=requests) -> str:
    """Call the Streamlit V19.4 MaiAgent API without any UI dependency."""
    if not api_key:
        raise RuntimeError("未設定 MAIAGENT_API_KEY")
    if not chatbot_id:
        raise RuntimeError("未設定 MAIAGENT_CHATBOT_ID")
    endpoints, headers, payloads = build_maiagent_request_attempts(prompt, api_key, chatbot_id, api_base)
    last_error = None
    for url in endpoints:
        for payload in payloads:
            try:
                response = http_client.post(url, headers=headers, json=payload, timeout=240)
                if response.status_code in (400, 404, 422):
                    last_error = RuntimeError(f"MaiAgent API 回應 {response.status_code}: {response.text[:500]}")
                    continue
                response.raise_for_status()
                try:
                    data = response.json()
                except ValueError:
                    return response.text.strip()
                return extract_maiagent_text(data)
            except Exception as exc:
                last_error = exc
                continue
    raise RuntimeError(f"MaiAgent API 呼叫失敗：{last_error}")


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


def build_report_retry_prompt(original_prompt: str, previous_response: str, validation: dict) -> str:
    return f"""{original_prompt}

## 輸出完整性重試
上一次輸出未通過 candidate_id 驗證。
- 缺少 ID：{validation.get('missing_ids', [])}
- 未知 ID：{validation.get('unknown_ids', [])}
- 重複 ID：{validation.get('duplicate_ids', [])}
請重新輸出完整報告。每個 expected candidate_id 必須且只能出現一次，標記格式必須是 `<!-- candidate_id: N -->`，並緊接在該則正式新聞標題前。不得只補局部段落。

上一次輸出僅供修正格式參考：
{previous_response}
""".strip()
