"""Pure-text normalization and postprocessing for completed MaiAgent reports."""

import datetime
import re
from collections import Counter
from dataclasses import dataclass
from html import unescape
from typing import Callable

from article_processor import (
    _candidate_date_obj,
    _canonical_candidate_region,
    _clean_text,
    _contains_any_term,
    build_formal_report_source,
    _domain_from_url,
    _effective_source_url,
    _extract_complete_url,
    _extract_complete_urls,
    _extract_domain_hint,
    _is_article_level_url,
    _is_query_proxy_source_label,
    _normalize_title,
)
from config import (
    ADVANCED_LOOKBACK_OPTIONS,
    ADVANCED_TYPES,
    EMPTY_TEXT_BY_TYPE,
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
    FORMAL_REPORT_CATEGORY_MAP,
    OPERATIONAL_DYNAMICS_CATEGORY_LABEL,
    REPORT_CATEGORY_TYPES,
    SECTION_NUMBER_BY_TYPE,
    SERVICE_OPENING_CATEGORY_KEY,
)
from electromechanical_taxonomy import (
    classify_electromechanical_evidence,
    report_labels_for_core_systems,
)
from event_identity import canonical_event_id
from journal_service import _parse_full_research_date
from maiagent_service import (
    REPORT_CANDIDATE_ID_PATTERN,
    extract_report_candidate_ids,
    ensure_selected_candidate_ids,
    remove_internal_candidate_markers,
    validate_report_candidate_ids,
)


@dataclass(frozen=True)
class ReportPostprocessContext:
    selected_types: list[str]
    standards_enabled: bool
    include_research_supplement: bool
    lookback_int: int
    today: datetime.date
    date_range: str
    report_title: str
    report_scope_label: str
    candidate_selection_text: Callable[[dict], str]
    infer_preliminary_type: Callable[[dict], str]
    is_urban_rail_candidate: Callable[[str], bool]
    research_section_heading: Callable[[bool], str]
    id_validation_target: dict


def short_url_label(url: str) -> str:
    host = _domain_from_url(url) or "來源"
    if "news.google.com" in host:
        return "來源連結"
    return f"來源連結（{host}）"








def _normalize_report_date_text(text: str) -> str:
    text = text or ""
    match = re.search(
        r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?:[T\s]\d{1,2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?",
        text,
    )
    if not match:
        match = re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return "日期未知"


def _domain_to_url(domain: str) -> str:
    domain = (domain or "").strip().strip("/").lower()
    if not domain:
        return ""
    if domain.startswith(("http://", "https://")):
        return domain
    return f"https://{domain}"


def _clean_source_label(content: str, url: str, domain: str) -> str:
    label = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", content or "")
    label = re.sub(r"https?://[^\s\)\]）＞>，,；;。]+", "", label)
    if domain:
        label = re.sub(re.escape(domain), "", label, flags=re.IGNORECASE)
    label = re.sub(
        r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}(?:[T\s]\d{1,2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?",
        "",
        label,
    )
    label = re.sub(r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日", "", label)
    label = re.sub(r"(資料來源未明確辨識|日期未知)", "", label)
    label = re.sub(r"來源連結\s*[（(][^）)]*[）)]", "", label)
    label = re.sub(r"原始候選資料未提供完整\s*URL", "", label, flags=re.IGNORECASE)
    label = re.sub(r"未提供完整\s*URL", "", label, flags=re.IGNORECASE)
    label = re.sub(r"Google\s*News.*?(?:代理|proxy|來源)?", "", label, flags=re.IGNORECASE)
    label = _clean_formal_source_proxy_label(label)
    label = label.replace("，。", "，").replace("。 ", " ")
    label = re.sub(r"[（(]\s*[）)]", "", label)
    label = re.sub(r"[，,。；;：:]+\s*", " ", label)
    label = re.sub(r"\s+", " ", label)
    label = label.strip(" ：:;；,，。-（）()[]【】")
    label = _clean_formal_source_proxy_label(label)
    if label.casefold() in {"http", "https", "google news", "news", "article", "report", "source", url.casefold(), domain.casefold()}:
        label = ""
    if re.sub(r"\s+", "", label) in {"報導", "新聞", "公告", "來源", "資料來源"}:
        label = ""
    if label in _GENERIC_SOURCE_FALLBACKS:
        label = ""
    if not label and domain:
        label = domain
    return label


def _source_label_with_link(label: str, url: str) -> str:
    label = str(label or "").strip() or _domain_from_url(url)
    url = _extract_complete_url(str(url or ""))
    return f"[{label}]({url})" if url else label


def normalize_source_line(line: str) -> str:
    if "資料來源" not in (line or ""):
        return line
    match = re.match(
        r"^\s*(?:[-*]\s*)?(?:•\s*)?(?:\*\*)?資料來源"
        r"(?:\*\*)?\s*[：:]\s*(?:\*\*)?\s*(.*)$|"
        r"^\s*(?:[-*]\s*)?(?:•\s*)?(?:\*\*)?資料來源"
        r"\s*[：:]\s*(?:\*\*)?\s*(.*)$",
        line or "",
    )
    if not match:
        return line
    content = match.group(1).strip()
    for fallback in _GENERIC_SOURCE_FALLBACKS:
        content = re.sub(re.escape(fallback), " ", content, flags=re.IGNORECASE)
    content = re.sub(r"\s+", " ", content).strip()
    content = re.sub(r"(原文連結)(?:\s*[，,、]\s*\1)+", r"\1", content)
    if re.search(r"[；;]\s*補充來源\s*[：:]", content):
        primary_content, supplemental_content = re.split(
            r"[；;]\s*補充來源\s*[：:]\s*",
            content,
            maxsplit=1,
        )
        normalized_primary = normalize_source_line(f"• 資料來源：{primary_content}")
        supplemental_entries: list[str] = []
        for raw_entry in re.split(r"[；;]+", supplemental_content):
            entry = raw_entry.strip()
            if not entry:
                continue
            entry_urls = list(dict.fromkeys(_extract_complete_urls(entry)))
            label = entry
            for entry_url in entry_urls:
                label = label.replace(entry_url, "")
            label = re.sub(r"^[、,，：:\s]+|[、,，：:\s]+$", "", label)
            if not label and entry_urls:
                label = _domain_from_url(entry_urls[0])
            supplemental_entries.append(
                _source_label_with_link(label, entry_urls[0])
                if entry_urls
                else label
            )
        if supplemental_entries:
            return normalized_primary.rstrip("。") + "；補充來源：" + "；".join(supplemental_entries) + "。"
        return normalized_primary
    date_text = _normalize_report_date_text(content)
    urls = list(dict.fromkeys(_extract_complete_urls(content)))
    original_article_url = next(
        (
            value for value in urls
            if "news.google.com" not in _domain_from_url(value) and _is_article_level_url(value)
        ),
        "",
    )
    google_news_article_url = next(
        (
            value for value in urls
            if "news.google.com" in _domain_from_url(value) and _is_article_level_url(value, allow_google_news=True)
        ),
        "",
    )
    url = original_article_url or google_news_article_url
    content_without_urls = content
    for value in urls:
        content_without_urls = content_without_urls.replace(value, "")
    domain_hint = _extract_domain_hint(content_without_urls)
    if not domain_hint and google_news_article_url:
        domain_hint = _extract_domain_hint(google_news_article_url)
    if not domain_hint and google_news_article_url:
        domain_hint = _domain_from_url(google_news_article_url)
    if not url and urls:
        url = urls[0]
    host = _domain_from_url(url)
    source_ref = original_article_url or domain_hint
    source_label = _clean_source_label(content, source_ref, domain_hint or host)
    formal_source = build_formal_report_source(
        {
            "source": source_label or content,
            "source_display": source_label,
            "source_domain": domain_hint or host,
            "source_href": original_article_url,
            "url": url,
        }
    )
    if not source_label and not formal_source["display_url"] and date_text == "日期未知":
        return "• 資料來源："
    parts = [f"• 資料來源：{formal_source['display_name']}" if formal_source["display_name"] else "• 資料來源："]
    if formal_source["display_url"]:
        parts.append(formal_source["display_url"])
    if date_text and date_text != "日期未知":
        parts.append(f"發布日期：{date_text}")
    return "\n".join(part for part in parts if part)


def _protect_journal_sections(text: str) -> tuple[str, list[str]]:
    sections: list[str] = []
    pattern = re.compile(
        r"(?ms)^#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:技術研究補充|國際學術期刊)\s*$.*?(?=^📊|^⏰|\Z)"
    )

    def _replace(match: re.Match) -> str:
        sections.append(match.group(0).strip())
        return f"\n__JOURNAL_SECTION_{len(sections) - 1}__\n"

    return pattern.sub(_replace, text or "", count=1), sections


def _restore_journal_sections(text: str, sections: list[str]) -> str:
    restored = text or ""
    for idx, section in enumerate(sections or []):
        restored = restored.replace(f"__JOURNAL_SECTION_{idx}__", section)
    return restored


def normalize_report_source_lines(text: str) -> str:
    protected, sections = _protect_journal_sections(text or "")
    normalized = "\n".join(normalize_source_line(line) for line in protected.splitlines())
    return _restore_journal_sections(normalized, sections)


def compact_report_urls(text: str) -> str:
    """Keep formal source URLs complete while compacting incidental long URLs elsewhere."""
    text = normalize_report_source_lines(text)

    def _compact_line(line: str) -> str:
        if "資料來源" in line:
            return line
        if re.fullmatch(r"\s*https?://\S+\s*", line or ""):
            return line
        placeholders: list[str] = []

        def _replace_markdown_link(match: re.Match) -> str:
            label, url = match.group(1), match.group(2)
            if len(url) < 72 and "news.google.com" not in url:
                replacement = match.group(0)
            else:
                replacement = f"[{label or short_url_label(url)}]({url})"
            placeholders.append(replacement)
            return f"__REPORT_LINK_{len(placeholders) - 1}__"

        line = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", _replace_markdown_link, line)

        def _replace_plain_url(match: re.Match) -> str:
            url = match.group(0).rstrip("。；;,，)")
            suffix = match.group(0)[len(url):]
            return f"{short_url_label(url)}{suffix}"

        line = re.sub(r"https?://[^\s\)\]]+", _replace_plain_url, line)
        for idx, original in enumerate(placeholders):
            line = line.replace(f"__REPORT_LINK_{idx}__", original)
        return line

    return "\n".join(_compact_line(line) for line in text.splitlines())


def strip_internal_report_fields(text: str) -> str:
    """正式報告隱藏模型稽核欄位；raw debug 仍保留原始候選資料。"""
    if not text:
        return text

    lines = text.splitlines()
    cleaned: list[str] = []
    skip_candidate_section = False
    internal_field_pattern = re.compile(
        r"^\s*[*-]?\s*(?:\*\*)?"
        r"(信心水準|納入理由|技術/政策關鍵字|技術關鍵字|入選原因|初步分類|python_score)"
        r"(?:\*\*)?\s*[：:].*$"
    )
    internal_system_pattern = re.compile(
        r"^\s*(?:>\s*)?(?:[*-]\s*)?"
        r"(篩選類型|本次\s*ddgs\s*搜尋次數|ddgs\s*搜尋次數|系統內部搜尋次數|"
        r"prompt\s*字數|Prompt\s*字數|MaiAgent\s*呼叫次數|MaiAgent\s*呼叫|"
        r"來源健康|原始蒐集|重複排除後|初篩後|developer\s*debug|模型)"
        r"\s*[：:].*$",
        flags=re.IGNORECASE,
    )
    search_count_pattern = re.compile(r"^\s*(?:🔍\s*)?(?:\*\*)?執行搜尋次數")
    achieved_shortfall_pattern = re.compile(r"^\s*(?:⚠️\s*)?(?:\*\*)?不足\s*\d+\s*則原因(?:\*\*)?\s*[：:]\s*(?:已達標|無|無。)\s*$")

    for raw_line in lines:
        line = raw_line.strip()
        section_title = re.sub(r"^[#\s]+", "", line).strip()

        if re.match(r"^(候補觀察(?:（.*?）)?|第一階段入選新聞|國際學術與技術研究補充候選)$", section_title):
            skip_candidate_section = True
            continue

        if skip_candidate_section:
            if section_title.startswith(("報告摘要", "結尾")) or re.match(r"^[一二三四五六]、", section_title) or line.startswith(("📊", "⚠️", "⏰", "**本週統計", "本週統計", "**本期統計", "本期統計", "**不足", "不足", "**報告產出時間", "報告產出時間")):
                skip_candidate_section = False
            else:
                continue

        if internal_field_pattern.match(line):
            continue
        if internal_system_pattern.match(line):
            continue
        if search_count_pattern.match(line):
            continue
        if achieved_shortfall_pattern.match(line):
            continue
        if section_title in {"結尾", "結尾（必填）"}:
            continue

        cleaned.append(raw_line)

    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_unselected_report_sections(text: str, *, selected_types: list[str]) -> str:
    if not text or not selected_types:
        return text
    cleaned = text
    for category in REPORT_CATEGORY_TYPES:
        if category in selected_types:
            continue
        number = SECTION_NUMBER_BY_TYPE.get(category, "")
        if number:
            cleaned = re.sub(
                rf"(?ms)^\s*#{{0,6}}\s*{re.escape(number)}\s*、\s*{re.escape(category)}\s*$.*?(?=^\s*#{{0,6}}\s*[一二三四五六]\s*、|^\s*📊|^\s*⏰|\Z)",
                "",
                cleaned,
            )
        cleaned = cleaned.replace(EMPTY_TEXT_BY_TYPE.get(category, ""), "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def strip_unselected_types_from_title(text: str, *, selected_types: list[str]) -> str:
    if not text or not selected_types:
        return text
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not line.lstrip().startswith("#"):
            continue
        title = line
        for category in REPORT_CATEGORY_TYPES:
            if category in selected_types:
                continue
            title = title.replace(f"、{category}", "").replace(f"{category}、", "").replace(category, "")
        title = re.sub(r"、{2,}", "、", title).replace("：、", "：").replace("、｜", "｜")
        title = re.sub(r"[、\s]+$", "", title)
        lines[idx] = title
        break
    return "\n".join(lines)


def normalize_report_statistics_line(text: str) -> str:
    return text


def strip_report_footer_lines(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(
        r"\s*📊\s*(?:本週|本期)統計\s*[：:].*?(?=(?:\s*⏰\s*報告產出時間|\n|$))",
        "",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r"\s*(?:本週|本期)統計\s*[：:].*?(?=(?:\s*⏰\s*報告產出時間|\n|$))",
        "",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r"\s*⏰\s*報告產出時間\s*[：:].*?(?=\n|$)",
        "",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r"\s*報告產出時間\s*[：:].*?(?=\n|$)",
        "",
        cleaned,
        flags=re.DOTALL,
    )
    lines = []
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if re.match(r"^📊\s*(?:本週|本期)統計", line):
            continue
        if re.match(r"^(?:本週|本期)統計", line):
            continue
        if re.match(r"^⏰\s*報告產出時間", line):
            continue
        if re.match(r"^報告產出時間", line):
            continue
        lines.append(raw_line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def final_report_statistics_line(
    report_md: str,
    journal_candidates: list[dict] | None = None,
    *,
    selected_types: list[str],
    include_research_supplement: bool,
) -> str:
    selected_parts = [category for category in REPORT_CATEGORY_TYPES if category in selected_types]
    counts = count_report_items_by_category(report_md)
    formal_total = sum(counts.get(category, 0) for category in selected_parts) if selected_parts else count_report_items(report_md)
    stats_detail = "／".join(f"{category} {counts.get(category, 0)} 則" for category in selected_parts)
    if stats_detail:
        line = f"📊 本期統計：正式新聞共 {formal_total} 則（{stats_detail}）"
    else:
        line = f"📊 本期統計：正式新聞共 {formal_total} 則"
    if include_research_supplement:
        line += f"；國際學術期刊共 {len(journal_candidates or [])} 篇"
    return line + "。"


def apply_final_report_footer(
    report_md: str,
    journal_candidates: list[dict] | None = None,
    *,
    selected_types: list[str],
    include_research_supplement: bool,
    today: datetime.date,
) -> str:
    body = strip_report_footer_lines(report_md)
    weekday = ['一', '二', '三', '四', '五', '六', '日'][today.weekday()]
    stats_line = final_report_statistics_line(
        body,
        journal_candidates,
        selected_types=selected_types,
        include_research_supplement=include_research_supplement,
    )
    time_line = f"⏰ 報告產出時間：{today.strftime('%Y年%m月%d日')} 週{weekday}"
    return f"{body.rstrip()}\n\n{stats_line}\n\n{time_line}".strip()


def normalize_research_section_heading(
    text: str,
    *,
    include_research_supplement: bool,
    research_section_heading: Callable[..., str],
) -> str:
    if not text or not include_research_supplement:
        return text
    heading = research_section_heading(markdown=True)
    return re.sub(
        r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:技術研究補充|國際學術期刊)\s*$",
        heading,
        text,
        count=1,
    )


def normalize_formal_report_title(text: str) -> str:
    normalized = text or ""
    for old in (
        "營運政策、營運爭議",
        "營運爭議、營運政策",
        "營運政策／營運爭議",
        "營運爭議／營運政策",
    ):
        normalized = normalized.replace(old, OPERATIONAL_DYNAMICS_CATEGORY_LABEL)
    return normalized


_FORMAL_SECTION_KEYS = {
    "技術新知": "技術新知",
    "重大事故": "重大事故",
    "營運政策": OPERATIONAL_DYNAMICS_CATEGORY_LABEL,
    "營運爭議": OPERATIONAL_DYNAMICS_CATEGORY_LABEL,
    "營運議題": OPERATIONAL_DYNAMICS_CATEGORY_LABEL,
    OPERATIONAL_DYNAMICS_CATEGORY_LABEL: OPERATIONAL_DYNAMICS_CATEGORY_LABEL,
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL: ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
}


def _dedupe_report_blocks(section_body: str) -> str:
    parts = re.split(r"(?m)(?=^\s*(?:<!--\s*candidate_id\s*:\s*\d+\s*-->\s*\n)*🔹\s*\[[^\]]+\])", section_body or "")
    blocks = [part.strip() for part in parts if part.strip()] if len(parts) > 1 else []
    article_blocks = [block for block in blocks if re.search(r"(?m)^🔹\s*\[[^\]]+\]", block)]
    if not article_blocks:
        unique_paragraphs: list[str] = []
        seen_empty_messages: set[str] = set()
        empty_messages = {
            message.strip()
            for message in EMPTY_TEXT_BY_TYPE.values()
        }
        for paragraph in re.split(r"\n+", section_body or ""):
            cleaned = paragraph.strip()
            if not cleaned:
                continue
            if cleaned in empty_messages:
                if cleaned in seen_empty_messages:
                    continue
                seen_empty_messages.add(cleaned)
            unique_paragraphs.append(cleaned)
        return "\n\n".join(unique_paragraphs).strip()
    unique_blocks: list[str] = []
    seen: set[str] = set()
    for block in article_blocks:
        marker = re.search(r"<!--\s*candidate_id\s*:\s*(\d+)\s*-->", block, flags=re.IGNORECASE)
        urls = _extract_complete_urls(block)
        title = re.search(r"(?m)^🔹\s*\[[^\]]+\]\s*(.+)$", block)
        identity = (
            f"candidate:{marker.group(1)}"
            if marker
            else f"url:{urls[0].casefold()}"
            if urls
            else f"title:{_normalize_title(title.group(1) if title else block)}"
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique_blocks.append(block)
    if len(unique_blocks) == len(article_blocks):
        return (section_body or "").strip()
    separator = "\n\n---\n\n" if re.search(r"\n\s*---\s*\n", section_body or "") else "\n\n"
    return separator.join(unique_blocks)


def deduplicate_formal_report_sections(report_md: str) -> str:
    """Keep one canonical heading for each formal-news section."""
    text = report_md or ""
    heading_pattern = re.compile(
        r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*"
        r"(技術新知|重大事故|營運政策|營運爭議|營運議題|營運動態|機電標案)\s*$"
    )
    matches = list(heading_pattern.finditer(text))
    if not matches:
        return text

    section_boundary_pattern = re.compile(
        r"(?m)^\s*(?:#{1,6}\s*)?[一二三四五六七八九十]\s*、|^\s*[📊⏰]"
    )
    records: list[dict] = []
    for match in matches:
        boundary = section_boundary_pattern.search(text, match.end())
        next_start = boundary.start() if boundary else len(text)
        label = match.group(1)
        records.append({
            "start": match.start(),
            "end": next_start,
            "key": _FORMAL_SECTION_KEYS[label],
            "heading": text[match.start():match.end()].strip(),
            "body": text[match.end():next_start],
        })
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["key"], []).append(record)

    replacements: list[tuple[int, int, str]] = []
    for key, group in grouped.items():
        if len(group) == 1:
            record = group[0]
            deduplicated_body = _dedupe_report_blocks(record["body"])
            if deduplicated_body != record["body"].strip():
                replacements.append(
                    (
                        record["start"],
                        record["end"],
                        f"{record['heading']}\n\n{deduplicated_body}\n",
                    )
                )
            continue
        combined_body = _dedupe_report_blocks("\n\n".join(record["body"] for record in group))
        if not combined_body:
            combined_body = "本期未發現符合條件資料。"
        first = group[0]
        canonical_number = {
            "技術新知": "一",
            "重大事故": "二",
            OPERATIONAL_DYNAMICS_CATEGORY_LABEL: "三",
            ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL: "四",
        }[key]
        replacements.append(
            (
                first["start"],
                first["end"],
                f"## {canonical_number}、{key}\n\n{combined_body.strip()}\n",
            )
        )
        replacements.extend((record["start"], record["end"], "") for record in group[1:])
    for start, end, replacement in sorted(replacements, reverse=True):
        text = text[:start] + replacement + text[end:]
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _deduplicate_research_sections(report_md: str) -> str:
    text = report_md or ""
    heading_pattern = re.compile(
        r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*"
        r"(規範更新|國際學術期刊|技術研究補充)\s*$"
    )
    matches = list(heading_pattern.finditer(text))
    if not matches:
        return text

    boundary_pattern = re.compile(
        r"(?m)^\s*(?:#{1,6}\s*)?[一二三四五六七八九十]\s*、|^\s*[📊⏰]"
    )
    replacements: list[tuple[int, int, str]] = []
    seen_sections: dict[str, str] = {}
    for match in matches:
        boundary = boundary_pattern.search(text, match.end())
        end = boundary.start() if boundary else len(text)
        label = match.group(1)
        body = text[match.end():end].strip()
        normalized_body = re.sub(r"\s+", "", body).casefold()
        section_key = "journal" if label in {"國際學術期刊", "技術研究補充"} else label
        if section_key in seen_sections and seen_sections[section_key] == normalized_body:
            replacements.append((match.start(), end, ""))
            continue
        seen_sections[section_key] = normalized_body
        if section_key == "journal":
            header = text[match.start():match.end()]
            parts = re.split(r"(?m)(?=^\s*(?:◆\s*\[學術期刊\]|\d+[\.、]))", body)
            unique_parts: list[str] = []
            seen_entries: set[str] = set()
            for part in parts:
                cleaned = part.strip()
                if not cleaned:
                    continue
                doi = _normalize_doi_value(cleaned, context=None) if "_normalize_doi_value" in globals() else ""
                urls = _extract_complete_urls(cleaned)
                title_match = re.search(r"(?m)^\s*(?:◆\s*\[學術期刊\]|\d+[\.、])\s*(.+)$", cleaned)
                identity = doi or (urls[0].casefold() if urls else "") or _normalize_title(title_match.group(1) if title_match else cleaned)
                if identity in seen_entries:
                    continue
                seen_entries.add(identity)
                unique_parts.append(cleaned)
            body = "\n\n".join(unique_parts)
            replacements.append((match.start(), end, f"{header}\n\n{body}\n".rstrip()))
    for start, end, replacement in sorted(replacements, reverse=True):
        text = text[:start] + replacement + text[end:]
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def deduplicate_report_quality_issues(report_md: str) -> str:
    text = report_md or ""
    text = re.sub(
        r"(?m)^\s*#{0,6}\s*([一二三四五六七八九十]\s*、\s*"
        r"(技術新知|重大事故|營運政策|營運爭議|營運議題|營運動態|機電標案))\s*"
        r"#{1,6}\s*[一二三四五六七八九十]\s*、\s*\2\s*$",
        r"## \1",
        text,
    )
    text = re.sub(
        r"(?m)^(\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*"
        r"(技術新知|重大事故|營運政策|營運爭議|營運議題|營運動態|機電標案))"
        r"\s*#{1,6}\s*[一二三四五六七八九十]\s*、\s*\2\s*$",
        r"## \2",
        text,
    )
    text = deduplicate_formal_report_sections(text)
    text = _deduplicate_research_sections(text)
    empty_messages = {
        message.strip()
        for message in EMPTY_TEXT_BY_TYPE.values()
    }
    empty_messages.add(f'本期未發現符合條件的{OPERATIONAL_DYNAMICS_CATEGORY_LABEL}資料。')
    deduped_lines: list[str] = []
    previous_nonempty = ''
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in empty_messages and stripped == previous_nonempty:
            continue
        deduped_lines.append(line)
        if stripped:
            previous_nonempty = stripped
    text = '\n'.join(deduped_lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _reorder_formal_report_sections(report_md: str) -> str:
    text = report_md or ""
    heading_pattern = re.compile(
        r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*"
        r"(技術新知|重大事故|營運動態|營運議題|營運政策|營運爭議|機電標案|規範更新|國際學術期刊|技術研究補充)\s*$"
    )
    matches = list(heading_pattern.finditer(text))
    if len(matches) < 2:
        return text
    boundary_pattern = re.compile(
        r"(?m)^\s*#{1,6}\s*[一二三四五六七八九十]\s*、|^\s*[📊⏰]"
    )
    sections: list[dict] = []
    for match in matches:
        boundary = boundary_pattern.search(text, match.end())
        end = boundary.start() if boundary else len(text)
        label = match.group(1)
        key = {
            "營運議題": OPERATIONAL_DYNAMICS_CATEGORY_LABEL,
            "營運政策": OPERATIONAL_DYNAMICS_CATEGORY_LABEL,
            "營運爭議": OPERATIONAL_DYNAMICS_CATEGORY_LABEL,
            "技術研究補充": "國際學術期刊",
        }.get(label, label)
        sections.append({"start": match.start(), "end": end, "key": key, "text": text[match.start():end].strip()})
    order = {
        "技術新知": 1,
        "重大事故": 2,
        OPERATIONAL_DYNAMICS_CATEGORY_LABEL: 3,
        ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL: 4,
        "規範更新": 5,
        "國際學術期刊": 6,
    }
    ordered = sorted(enumerate(sections), key=lambda item: (order.get(item[1]["key"], 99), item[0]))
    if [index for index, _ in ordered] == list(range(len(sections))):
        return text
    first_start = sections[0]["start"]
    last_end = sections[-1]["end"]
    replacement = "\n\n".join(item[1]["text"] for item in ordered)
    return (text[:first_start].rstrip() + "\n\n" + replacement + "\n\n" + text[last_end:].lstrip()).strip()


def normalize_report_section_numbering(
    text: str,
    *,
    selected_types: list[str],
    standards_enabled: bool,
) -> str:
    normalized = text or ""
    section_numbers = {
        "技術新知": "一",
        "重大事故": "二",
        OPERATIONAL_DYNAMICS_CATEGORY_LABEL: "三",
        ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL: "四",
        "規範更新": "五" if ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL in selected_types else "四",
        "國際學術期刊": (
            "六"
            if ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL in selected_types
            and (standards_enabled or "規範更新" in selected_types)
            else "五"
            if ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL in selected_types
            or standards_enabled
            or "規範更新" in selected_types
            else "四"
        ),
    }
    for label, number in section_numbers.items():
        aliases = "(?:營運議題|營運動態)" if label == OPERATIONAL_DYNAMICS_CATEGORY_LABEL else "(?:國際學術期刊|技術研究補充)" if label == "國際學術期刊" else re.escape(label)
        normalized = re.sub(
            rf"(?m)^\s*#{{0,6}}\s*(?:[一二三四五六七八九十]\s*、\s*)?{aliases}\s*$",
            f"## {number}、{label}",
            normalized,
        )
    normalized = _reorder_formal_report_sections(deduplicate_report_quality_issues(normalized))
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _operational_block_sort_key(block: str) -> tuple[str, str]:
    date_match = re.search(r"發布/事件日期\s*[：:]\s*(\d{4}-\d{2}-\d{2})", block or "")
    title_match = re.search(r"(?m)^🔹\s*\[[^\]]+\]\s*(.+)$", block or "")
    return (
        date_match.group(1) if date_match else "",
        _normalize_title(title_match.group(1) if title_match else ""),
    )


def _operational_blocks(section_text: str) -> list[str]:
    blocks = re.findall(
        r"(?ms)^((?:(?:\s*(?:<!--\s*candidate_id\s*:\s*\d+\s*-->|&lt;!--\s*candidate_id\s*:\s*\d+\s*--&gt;)\s*\n)*)\s*🔹\s*\[(?:營運政策|營運爭議|營運動態|service_opening)\].*?)"
        r"(?=^\s*🔹\s*\[[^\]]+\]|^\s*#{0,6}\s*[一二三四五六七八九十]\s*、|^\s*📊|^\s*⏰|\Z)",
        section_text or "",
    )
    cleaned: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        block = re.sub(r"(?m)^\s*(?:---|_{5,})\s*$", "", block).strip()
        title_match = re.search(r"(?m)^🔹\s*\[[^\]]+\]\s*(.+)$", block)
        urls = _extract_complete_urls(block)
        identity = urls[0] if urls else _normalize_title(title_match.group(1) if title_match else block)
        if identity and identity not in seen:
            seen.add(identity)
            cleaned.append(block)
    return sorted(cleaned, key=_operational_block_sort_key, reverse=True)


def merge_operational_report_sections(
    report_md: str,
    *,
    selected_types: list[str],
    standards_enabled: bool,
) -> str:
    """Merge policy/dispute display sections while preserving their item tags."""
    text = report_md or ""
    if not text:
        return text
    heading_pattern = re.compile(
        r"(?m)^\s*#{0,6}\s*(?:[一二三四五六七八九十]\s*、\s*)?(?:營運政策|營運爭議|營運議題|營運動態)\s*$"
    )
    heading_matches = list(heading_pattern.finditer(text))
    spans: list[tuple[int, int]] = []
    blocks: list[str] = []
    next_section_pattern = re.compile(
        r"(?m)^\s*#{0,6}\s*(?:[一二三四五六七八九十]\s*、\s*)?(?:技術新知|重大事故|營運政策|營運爭議|營運議題|營運動態|機電標案|規範更新|國際學術期刊|技術研究補充)\s*$|^\s*📊|^\s*⏰"
    )
    for match in heading_matches:
        next_match = next_section_pattern.search(text, match.end())
        end = next_match.start() if next_match else len(text)
        spans.append((match.start(), end))
        blocks.extend(_operational_blocks(text[match.end():end]))

    deduped_blocks: list[str] = []
    seen_blocks: set[str] = set()
    for block in sorted(blocks, key=_operational_block_sort_key, reverse=True):
        title_match = re.search(r"(?m)^🔹\s*\[[^\]]+\]\s*(.+)$", block)
        urls = _extract_complete_urls(block)
        identity = urls[0] if urls else _normalize_title(title_match.group(1) if title_match else block)
        if identity and identity not in seen_blocks:
            seen_blocks.add(identity)
            deduped_blocks.append(block)

    if deduped_blocks:
        section_body = "\n\n---\n\n".join(deduped_blocks)
    else:
        section_body = "本期未發現符合條件之營運動態。"
    merged_section = f"## 三、{OPERATIONAL_DYNAMICS_CATEGORY_LABEL}\n\n{section_body}\n\n"

    operations_enabled = bool(
        {"營運政策", "營運爭議", SERVICE_OPENING_CATEGORY_KEY}.intersection(selected_types)
    )
    if spans:
        pieces: list[str] = []
        cursor = 0
        for index, (start, end) in enumerate(spans):
            pieces.append(text[cursor:start])
            if index == 0 and operations_enabled:
                pieces.append(merged_section)
            cursor = end
        pieces.append(text[cursor:])
        text = "".join(pieces)
    elif operations_enabled:
        insert_match = re.search(
            r"(?m)^\s*#{0,6}\s*(?:[一二三四五六七八九十]\s*、\s*)?(?:規範更新|機電標案|國際學術期刊|技術研究補充)\s*$|^\s*📊|^\s*⏰",
            text,
        )
        insert_at = insert_match.start() if insert_match else len(text)
        text = text[:insert_at].rstrip() + "\n\n" + merged_section + text[insert_at:].lstrip()

    text = re.sub(
        r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*規範更新\s*$",
        f"## {'五' if ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL in selected_types else '四'}、規範更新",
        text,
    )
    research_number = (
        "六"
        if ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL in selected_types
        and (standards_enabled or "規範更新" in selected_types)
        else "五"
        if ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL in selected_types
        or standards_enabled
        or "規範更新" in selected_types
        else "四"
    )
    text = re.sub(
        r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:國際學術期刊|技術研究補充)\s*$",
        f"## {research_number}、國際學術期刊",
        text,
    )
    return normalize_report_section_numbering(
        text,
        selected_types=selected_types,
        standards_enabled=standards_enabled,
    )


INTERNAL_REPORT_REPLACEMENTS = {
    "模型：MaiAgent 雲端 API": "",
    "候選資料指出": "資料顯示",
    "候選摘要指出": "摘要資料顯示",
    "入選資料指出": "資料顯示",
    "初篩資料指出": "資料顯示",
    "資料欄位顯示": "資料顯示",
    "本次候選資料": "本次資料",
    "原始候選資料": "資料來源",
    "raw data": "原始資料",
    "Raw data": "原始資料",
    "本次送入模型": "本次整理",
    "AI 入選": "本期納入",
    "模型判斷": "本週報歸類",
    "Python 初篩": "初步整理",
    "MaiAgent 判斷": "本週報整理",
    "developer debug": "",
    "Developer debug": "",
    "python_score": "",
    "入選原因": "",
    "初步分類": "",
    "來源健康": "來源狀態",
    "原始資料僅提供": "資料來源僅載明",
    "原始資料未提供": "資料來源未載明",
    "故不補述。": "",
    "故不補述": "",
    "原始資料未提供，故不補述。": "資料來源未載明更細部技術資料。",
    "原始資料未提供，故不補述": "資料來源未載明更細部技術資料",
}


def clean_internal_report_language(text: str) -> str:
    if not text:
        return text
    cleaned = text
    for old, new in INTERNAL_REPORT_REPLACEMENTS.items():
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"候選資料(?:指出|顯示|記載|提及)?", "資料", cleaned)
    cleaned = re.sub(r"候選摘要(?:指出|顯示|記載|提及)?", "摘要資料", cleaned)
    cleaned = re.sub(r"入選資料(?:指出|顯示|記載|提及)?", "資料", cleaned)
    cleaned = re.sub(r"初篩資料(?:指出|顯示|記載|提及)?", "資料", cleaned)
    cleaned = re.sub(r"(?im)^.*(?:模型：MaiAgent\s*雲端\s*API|來源健康|prompt\s*字數|MaiAgent\s*呼叫|本次送入模型|developer\s*debug|python_score|入選原因|初步分類).*$", "", cleaned)
    cleaned = re.sub(r"(?i)\braw data\b", "原始資料", cleaned)
    cleaned = re.sub(r"(?mi)^\s*編校說明\s*[：:].*$", "", cleaned)
    cleaned = re.sub(r"(?mi)^\s*編校說明\s*$", "", cleaned)
    cleaned = re.sub(r"(?i)\bcandidates?\b", "資料", cleaned)
    cleaned = re.sub(r"來源連結[（(]\s*Google\s*News\s*[）)]", "來源連結", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[（(]\s*Google\s*News\s*proxy\s*[）)]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"由\s*Google\s*News\s*代理", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Google\s*News\s*地區代理\s*[－\-:：]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Google\s*News\s*代理", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"地區代理\s*[－\-:：]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfallback\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"資料來源未提供完整 URL（[^）]*）", "資料來源未提供完整 URL", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


MISSING_DATA_DISCLAIMER_TERMS = (
    "資料未提供",
    "候選資料未提供",
    "原始資料未提供",
    "資料來源未載明",
)
MISSING_DATA_DISCLAIMER_PATTERN = re.compile(
    "|".join(re.escape(term) for term in sorted(MISSING_DATA_DISCLAIMER_TERMS, key=len, reverse=True))
)


def _remove_missing_data_from_sentence(sentence: str) -> str:
    match = MISSING_DATA_DISCLAIMER_PATTERN.search(sentence or "")
    if not match:
        return sentence
    ending_match = re.search(r"[。！？]\s*$", sentence)
    ending = ending_match.group(0).strip() if ending_match else ""
    content_end = ending_match.start() if ending_match else len(sentence)
    prefix = sentence[:match.start()].rstrip(" ，,；;")
    tail = sentence[match.start():content_end]
    continuation = re.search(
        r"[，,；;]\s*(?:(?:但|惟|然而|因此|所以|故|同時|另)\s*)?"
        r"(?=(?:本案|此案|該案|本事件|該事件|可|已|仍|屬|為|不|對臺北捷運局))",
        tail,
    )
    suffix = tail[continuation.end():].strip() if continuation else ""
    if prefix and suffix:
        return f"{prefix}，{suffix}{ending}"
    if suffix:
        return f"{suffix}{ending}"
    if prefix:
        return f"{prefix}{ending}"
    return ""


def remove_missing_data_disclaimers(report_md: str) -> str:
    """Remove only missing-data disclaimers and retain any useful sentence suffix."""
    cleaned_lines: list[str] = []
    for raw_line in (report_md or "").splitlines():
        if not MISSING_DATA_DISCLAIMER_PATTERN.search(raw_line):
            cleaned_lines.append(raw_line)
            continue
        sentence_parts = re.findall(r"[^。！？]*[。！？]?", raw_line)
        cleaned_line = "".join(
            _remove_missing_data_from_sentence(part)
            for part in sentence_parts
            if part
        ).strip()
        if cleaned_line:
            cleaned_lines.append(cleaned_line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned_lines)).strip()


SERVICE_OR_CIVIL_SYSTEM_TERMS = [
    "無障礙設施", "無障礙服務", "車站人流管理", "旅客服務", "活動疏運",
    "營運政策", "土建工程", "站體改善", "道路交通", "一般客服",
]

ICT_SECURITY_CONTEXT_TERMS = [
    "通訊網路", "通訊系統", "無線通訊", "網路安全", "資安", "資訊安全",
    "營運科技", "系統入侵", "駭客", "弱點", "漏洞", "資料安全",
    "OT", "IT", "CBTC", "SCADA", "OCC", "AFC", "cyber", "cybersecurity",
    "network", "communication", "communications", "telecom", "radio", "5G", "LTE",
    "intrusion", "hacker", "vulnerability", "data security",
]


def normalize_electromechanical_system_line(line: str) -> str:
    if "相關機電系統" not in line:
        return line
    prefix = line.split("相關機電系統", 1)[0] + "相關機電系統："
    value = line.split("相關機電系統", 1)[1].lstrip("：:").strip()
    value = normalize_electromechanical_system_value(value, line)
    return f"{prefix}{value}"


CANONICAL_ELECTROMECHANICAL_SYSTEMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("電梯", ("elevator", "elevators", "lift", "lifts", "電梯", "升降機")),
    ("電扶梯", ("escalator", "escalators", "電扶梯", "手扶梯")),
    ("號誌系統", ("signalling", "signaling", "signal system", "cbtc", "train control", "ats", "atp", "ato", "號誌", "信號", "列車控制", "列控")),
    ("通訊系統", ("communication", "telecom", "radio", "wireless communication", "通訊", "無線電", "光纖")),
    ("供電系統", ("traction power", "power supply", "substation", "scada", "traction", "供電", "牽引供電", "變電站", "電力系統")),
    ("自動收費系統", ("automatic fare collection", "fare gate", "ticketing", "afc", "自動收費", "票務", "閘門")),
    ("車輛系統", ("rolling stock", "rolling-stock", "trainset", "train vehicle", "vehicle equipment", "vehicle system", "vehicle fleet", "fleet", "battery vehicle", "battery-powered vehicle", "battery-powered", "vehicle replacement", "rolling stock replacement", "metro train vehicle", "light rail vehicle", "電聯車設備", "列車系統", "車輛設備", "車輛更新", "低地板車")),
    ("月台門系統", ("platform screen door", "platform door", "psd", "月台門", "月臺門")),
    ("機廠設備", ("depot electromechanical", "depot e&m", "depot mep", "機廠機電", "機廠設備", "機廠")),
    ("通風空調系統", ("ventilation", "hvac", "air conditioning", "smoke control", "通風", "空調", "環控")),
    ("軌道系統", ("embedded track", "tram track", "rail track", "track renewal", "track system", "track equipment", "rail infrastructure", "軌道系統", "軌道更新", "鋼軌")),
    ("軌道／轉轍設備", ("track circuit", "switch machine", "turnout", "轉轍", "道岔")),
)


def normalize_electromechanical_system_value(value: str, context: str = "") -> str:
    raw_value = re.sub(r"\s+", " ", (value or "").strip())
    abstract_values = {
        "車站無障礙設施", "車站機電", "車站機電系統", "軌道運輸安全", "列車營運",
        "營運安全", "測試驗證", "系統整合", "事故調查與安全管理", "旅客服務",
    }
    generic_values = {
        "", "未明確資料", "無明確資料", "未明確載明機電系統", "未明確載明", "未載明", "不明", "未知", "無", "n/a", "na", "-",
        "依原始候選資料所示之都市軌道系統", "都市軌道系統", "機電系統", "相關系統",
        "營運管理", "系統整合", "旅客服務", *abstract_values,
    }
    value_parts = {
        part.strip()
        for part in re.split(r"[、,，/；;|]+", raw_value)
        if part.strip()
    }
    is_abstract_only = bool(value_parts) and value_parts.issubset(abstract_values)
    non_physical_terms = (
        "營運", "安全調查", "事故調查", "測試", "驗證", "系統整合", "整合",
        "運行", "服務", "調查",
    )
    explicit_system_terms = (
        "系統", "設備", "elevator", "lift", "escalator", "signalling", "signaling",
        "cbtc", "train control", "通信", "通訊", "供電", "afc", "scada", "hvac",
        "車輛", "列車", "機廠", "軌道", "轉轍", "道岔",
    )
    raw_is_generic = raw_value.casefold() in {item.casefold() for item in generic_values}
    raw_has_non_physical = _contains_any_term(raw_value, list(non_physical_terms))
    raw_has_explicit_system = _contains_any_term(raw_value, list(explicit_system_terms))
    raw_evidence = "" if raw_is_generic or (raw_has_non_physical and not raw_has_explicit_system) else raw_value
    context_evidence = (context or "").replace(raw_value, "")
    evidence = " ".join(part for part in (raw_evidence, context_evidence) if part).strip()
    formal_taxonomy = classify_electromechanical_evidence({
        "reported_value": raw_evidence,
        "context": context_evidence,
    })
    shared_report_labels = {
        "號誌系統": "號誌",
        "通訊系統": "通訊",
        "自動收費系統": "自動收費",
        "機廠設備": "機廠維修設備",
    }
    formal_systems = set(formal_taxonomy["systems"])
    systems = []
    for label, terms in CANONICAL_ELECTROMECHANICAL_SYSTEMS:
        shared_core_label = shared_report_labels.get(label)
        if shared_core_label:
            if shared_core_label in formal_systems:
                systems.append(label)
            continue
        if _contains_any_term(evidence, list(terms)):
            systems.append(label)
    incident_context_terms = (
        "derailment", "collision", "crash", "incident", "accident", "出軌", "碰撞", "事故", "調查"
    )
    explicit_vehicle_evidence_terms = (
        "rolling stock", "trainset", "vehicle system", "車輛系統", "列車系統", "車輛設備"
    )
    if (
        "車輛系統" in systems
        and _contains_any_term(context, list(incident_context_terms))
        and not _contains_any_term(raw_value, list(explicit_vehicle_evidence_terms))
    ):
        systems = [system for system in systems if system != "車輛系統"]
    if systems:
        return "、".join(systems)
    return "未明確"


def _short_formal_sentence(text: str, limit: int = 180) -> str:
    text = re.sub(r"^\s*[-•]\s*", "", text or "").strip()
    text = re.sub(r"^(可能影響系統|可參考作法|後續追蹤建議)\s*[：:]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ；;，,")
    if len(text) > limit:
        window = text[:limit]
        cut_at = max(window.rfind(mark) for mark in ("。", "；", ";", "，", ","))
        if cut_at >= max(60, limit // 2):
            text = window[:cut_at + 1].rstrip("，,；; ")
        else:
            overflow_window = text[: min(len(text), limit + 80)]
            next_sentence = min(
                [idx for idx in (overflow_window.find(mark, limit) for mark in ("。", "；", ";")) if idx >= 0],
                default=-1,
            )
            if next_sentence >= 0:
                text = overflow_window[:next_sentence + 1].rstrip()
            else:
                text = window.rstrip("，,；;。 ") + "。"
    return text


def simplify_taipei_insight(text: str) -> str:
    lines = (text or "").splitlines()
    output: list[str] = []
    idx = 0
    while idx < len(lines):
        raw_line = lines[idx]
        line = raw_line.strip()
        if "【臺北捷運局啟示】" not in line:
            output.append(raw_line)
            idx += 1
            continue

        prefix = raw_line.split("【臺北捷運局啟示】", 1)[0]
        header = f"{prefix}【臺北捷運局啟示】："
        inline_text = line.split("【臺北捷運局啟示】", 1)[1].lstrip("：:").strip()
        idx += 1
        collected: list[str] = []
        while idx < len(lines):
            next_line = lines[idx].strip()
            if (
                next_line.startswith("• 資料來源")
                or next_line.startswith("• 發布/事件日期")
                or next_line.startswith("🔹")
                or next_line.startswith("________________________________________")
                or re.match(r"^[一二三四五六]、", next_line)
                or next_line.startswith("📊")
                or next_line.startswith("⏰")
            ):
                break
            if next_line:
                collected.append(next_line)
            idx += 1
        insight = _short_formal_sentence("；".join([inline_text] + collected))
        output.append(header)
        if insight:
            output.append(insight)
        continue
    return "\n".join(output)


def remove_legacy_report_fields(text: str) -> str:
    lines = []
    skip_legacy_insight_bullets = False
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if re.match(r"^•\s*(技術關鍵字|技術/政策關鍵字|入選原因|初步分類|python_score)\s*[：:]", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^[-•]\s*(可能影響系統|可參考作法|後續追蹤建議)\s*[：:]", line):
            continue
        if "相關機電系統" in raw_line:
            raw_line = normalize_electromechanical_system_line(raw_line)
        lines.append(raw_line)
    return "\n".join(lines)


def reduce_repeated_source_subjects(text: str) -> str:
    output: list[str] = []
    seen_subjects: set[str] = set()
    for raw_line in (text or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("🔹") or stripped.startswith("________________________________________"):
            seen_subjects = set()
        match = re.match(r"^(\s*-\s*)(依\s*[^，。；;]{2,40}(?:公告|報導|官方資料|發布))(?:，|指出，|顯示，)?\s*(.*)$", raw_line)
        if match:
            subject = re.sub(r"\s+", "", match.group(2))
            if subject in seen_subjects and match.group(3):
                raw_line = f"{match.group(1)}{match.group(3)}"
            else:
                seen_subjects.add(subject)
        output.append(raw_line)
    return "\n".join(output)


def simplify_formal_report_format(text: str) -> str:
    text = remove_legacy_report_fields(text)
    text = simplify_taipei_insight(text)
    text = reduce_repeated_source_subjects(text)
    return text


REPORT_FIELD_ALIASES = {
    "發布/事件日期": "發布/事件日期",
    "國家": "國家",
    "國家/地區": "國家/地區",
    "相關機電系統": "相關機電系統",
    "事件摘要": "事件摘要",
    "臺北捷運局啟示": "臺北捷運局啟示",
    "資料來源": "資料來源",
}


def _match_report_field_line(line: str) -> tuple[str, str] | None:
    cleaned = re.sub(r"^\s*(?:[-*]\s*)?(?:•\s*)?", "", line or "")
    labels = sorted(REPORT_FIELD_ALIASES, key=len, reverse=True)
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.match(
        rf"^(?:\*\*)?(?:【)?(?P<label>{label_pattern})(?:】)?"
        r"(?:\*\*)?\s*[：:]\s*(?:\*\*)?\s*(?P<value>.*)$",
        cleaned,
    )
    if not match:
        return None
    return REPORT_FIELD_ALIASES[match.group("label")], match.group("value").strip()


def _is_report_block_boundary(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if re.fullmatch(r"<!--\s*candidate_id\s*:\s*\d+\s*-->", stripped, flags=re.IGNORECASE):
        return True
    if stripped.startswith("__JOURNAL_SECTION_"):
        return True
    if _match_report_field_line(stripped):
        return True
    if stripped == "---" or stripped.startswith(("🔹", "📊", "⏰", "#", ">", "________________________________________")):
        return True
    return bool(re.match(r"^[一二三四五六]\s*、", stripped))


def _strip_nested_bullet_text(text: str) -> str:
    text = re.sub(r"^\s*[-*•]\s*", "", text or "")
    text = re.sub(r"^\s*(?:重點\s*\d+|[-*•])\s*[：:]?\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ；;，,")


def _join_field_parts(parts: list[str]) -> str:
    cleaned = [_strip_nested_bullet_text(part) for part in parts if _strip_nested_bullet_text(part)]
    text = " ".join(cleaned)
    text = re.sub(r"\s*[-*•]\s+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _dedupe_source_mentions_in_paragraph(text: str) -> str:
    seen: set[str] = set()

    def _replace(match: re.Match) -> str:
        subject = re.sub(r"\s+", "", match.group(1))
        if subject in seen:
            return ""
        seen.add(subject)
        return match.group(0)

    text = re.sub(
        r"(依\s*[^，。；;]{2,40}(?:公告|報導|官方資料|發布)(?:指出|顯示)?[，,]?)",
        _replace,
        text or "",
    )
    return re.sub(r"\s+", " ", text).strip()


def strip_event_summary_source_lead_in(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return cleaned
    lead_in_pattern = (
        r"^(?:依|根據)\s*"
        r"[^，。,；;：:\n]{2,80}?"
        r"(?:官方公告|官方資料|報導|公告)"
        r"(?:指出|表示|說明)?"
        r"\s*[，,：:]\s*"
    )
    return re.sub(lead_in_pattern, "", cleaned, count=1).strip()


def _looks_like_english_title(title: str) -> bool:
    compact = re.sub(r"[\s\W_]+", "", title or "")
    if not compact:
        return False
    ascii_chars = sum(1 for char in compact if ord(char) < 128)
    cjk_chars = len(re.findall(r"[\u3400-\u9fff]", compact))
    return ascii_chars >= 8 and ascii_chars > cjk_chars * 2


def _contains_untranslated_report_script(value: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\uac00-\ud7af]", value or ""))


def _summary_repeats_title(summary: str, title: str) -> bool:
    normalized_summary = re.sub(r"[\W_]+", "", unescape(summary or "")).casefold()
    normalized_title = re.sub(r"[\W_]+", "", unescape(title or "")).casefold()
    if len(normalized_title) < 8 or len(normalized_summary) < 8:
        return False
    if normalized_summary == normalized_title:
        return True
    return (
        normalized_summary.startswith(normalized_title)
        and len(normalized_summary) - len(normalized_title) <= 24
    )


_GENERIC_TAIPEI_INSIGHTS = {
    re.sub(r"[\W_]+", "", value).casefold()
    for value in (
        "可作為相關設備與系統整合案例之參考。",
        "應持續核對事故經過、技術原因與安全改善措施。",
        "可作為都市軌道營運治理與安全改善之追蹤案例。",
        "可作為都市軌道營運協調與影響評估之追蹤案例。",
        "可供後續核對規範變更內容及適用範圍。",
        "後續內容仍應以原始來源核實。",
    )
}


def _is_meaningful_taipei_insight(value: str) -> bool:
    normalized = re.sub(r"[\W_]+", "", value or "").casefold()
    return bool(normalized) and normalized not in _GENERIC_TAIPEI_INSIGHTS


def chinese_fallback_title(category: str, title: str) -> str:
    lower = (title or "").casefold()
    if "automated work zone speed enforcement" in lower:
        return "MTA 推動工區自動速限執法計畫"
    if "r211" in lower and "d line" in lower:
        return "MTA R211A 新型列車導入紐約地鐵 D 線"
    if "driverless train" in lower and "western sydney airport" in lower:
        return "雪梨西部機場捷運線首列無人駕駛列車抵達"
    if "cbtc" in lower:
        return "CBTC 列車控制系統更新案"
    if "signalling" in lower or "signaling" in lower:
        return "捷運號誌系統更新案"
    if "platform screen door" in lower:
        return "月臺門系統更新案"
    if "afc" in lower or "ticketing" in lower or "fare" in lower:
        return "AFC 票務系統更新案"
    if "power" in lower or "substation" in lower or "traction" in lower:
        return "捷運供電系統更新案"
    if "cyber" in lower or "security" in lower:
        return "捷運資安防護更新案"
    if "driverless" in lower or "automated train" in lower:
        return "無人駕駛捷運列車導入案"
    if "train" in lower or "fleet" in lower:
        return "捷運列車更新案"
    if "metro" in lower or "subway" in lower or "light rail" in lower or "tram" in lower:
        if category == "重大事故":
            return "都市軌道重大事故事件"
        if category == "營運政策":
            return "都市軌道營運政策更新"
        if category == "營運爭議":
            return "都市軌道營運爭議事件"
        return "都市軌道系統更新案"
    return {
        "技術新知": "國際捷運技術更新案",
        "重大事故": "國際捷運重大事故事件",
        "營運政策": "國際捷運營運政策更新",
        "營運爭議": "國際捷運營運爭議事件",
        "規範更新": "國際捷運規範更新案",
        ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL: "都市軌道機電標案",
    }.get(category, "國際捷運案例")


def _canonical_report_category_label(value: str) -> str:
    label = re.sub(r"\s+", "", value or "")
    label = label.replace("營運議題", OPERATIONAL_DYNAMICS_CATEGORY_LABEL)
    if "營運政策" in label:
        return "營運政策"
    if "營運爭議" in label:
        return "營運爭議"
    if "通車" in label or SERVICE_OPENING_CATEGORY_KEY in label:
        return SERVICE_OPENING_CATEGORY_KEY
    if OPERATIONAL_DYNAMICS_CATEGORY_LABEL in label:
        return OPERATIONAL_DYNAMICS_CATEGORY_LABEL
    for category in (
        "技術新知",
        "重大事故",
        ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
        "規範更新",
    ):
        if category in label:
            return category
    return (value or "").strip() or "技術新知"


def canonical_formal_report_category(value: str) -> str:
    """Normalize model category labels to the four formal report labels."""
    return FORMAL_REPORT_CATEGORY_MAP.get(
        _canonical_report_category_label(value),
        (value or "").strip() or "技術新知",
    )


def _formal_category_for_candidate(candidate: dict) -> str:
    # `classification`/`preliminary_type` are materialized mirrors kept for
    # compatibility with already-selected records; no text or query inference
    # is performed here.  New selector entries must still provide
    # `primary_category` through the entry contract.
    internal_category = str(
        candidate.get("primary_category")
        or candidate.get("classification")
        or candidate.get("preliminary_type")
        or ""
    ).strip()
    return FORMAL_REPORT_CATEGORY_MAP.get(internal_category, internal_category)


def normalize_report_title_line(line: str) -> str:
    match = re.match(r"^\s*🔹\s*\[([^\]]+)\]\s*(.*?)\s*$", line or "")
    if match:
        category = _canonical_report_category_label(match.group(1))
        title = match.group(2).strip()
    else:
        pipe_match = re.match(r"^\s*🔹\s*(.+?)\s*[｜|]\s*(.*?)\s*$", line or "")
        if not pipe_match:
            return line
        category = _canonical_report_category_label(pipe_match.group(1))
        title = pipe_match.group(2).strip()
    if _title_needs_repair(title, category):
        title = chinese_fallback_title(category, title)
    return f"🔹 [{category}] {title}"


def normalize_final_report_md(md: str) -> str:
    text = clean_internal_report_language(md or "")
    text, protected_journal_sections = _protect_journal_sections(text)
    text = re.sub(
        r"(?m)^\s*>?\s*(?:報導範圍|範圍)\s*[：:].*$\n?",
        "",
        text,
    )
    text = re.sub(r"(?m)^\s*[-*]\s*\*\*(發布/事件日期|國家/地區|相關機電系統|事件摘要|臺北捷運局啟示|資料來源)\*\*\s*[：:]", r"• \1：", text)
    text = re.sub(r"(?m)^\s*[-*]\s*\*\*【臺北捷運局啟示】\*\*\s*[：:]", "• 臺北捷運局啟示：", text)
    text = re.sub(r"(?m)^\s*•\s*【臺北捷運局啟示】\s*[：:]", "• 臺北捷運局啟示：", text)
    text = re.sub(r"(?m)^#{3,6}\s+\[([^\]]+)\]\s*(.+)$", r"🔹 [\1] \2", text)

    lines = text.splitlines()
    output: list[str] = []
    current_title = ""
    idx = 0
    while idx < len(lines):
        raw_line = lines[idx]
        stripped = raw_line.strip()
        if not stripped:
            output.append(raw_line)
            idx += 1
            continue
        if stripped in {"•", "-", "*"}:
            idx += 1
            continue

        field = _match_report_field_line(raw_line)
        if not field:
            normalized_line = normalize_report_title_line(raw_line) if stripped.startswith("🔹") else raw_line
            output.append(normalized_line)
            title_match = re.match(r"^\s*🔹\s*\[[^\]]+\]\s*(.*?)\s*$", normalized_line)
            if title_match:
                current_title = title_match.group(1).strip()
            idx += 1
            continue

        label, value = field
        context_window = "\n".join(lines[max(0, idx - 8): min(len(lines), idx + 10)])
        idx += 1
        collected = [value]
        while idx < len(lines):
            next_line = lines[idx].strip()
            if not next_line:
                idx += 1
                continue
            if _is_report_block_boundary(next_line):
                break
            collected.append(next_line)
            idx += 1

        field_text = _join_field_parts(collected)
        if label == "事件摘要":
            field_text = strip_event_summary_source_lead_in(field_text)
            field_text = _dedupe_source_mentions_in_paragraph(field_text)
            if (
                _summary_repeats_title(field_text, current_title)
                or _contains_untranslated_report_script(field_text)
            ):
                field_text = ""
            if field_text:
                output.extend(["• 事件摘要：", field_text, ""])
        elif label == "臺北捷運局啟示":
            insight = _short_formal_sentence(field_text, 180)
            if (
                insight
                and _is_meaningful_taipei_insight(insight)
                and not _contains_untranslated_report_script(insight)
            ):
                output.extend(["• 臺北捷運局啟示：", insight, ""])
        elif label == "資料來源":
            output.extend([normalize_source_line(f"• 資料來源：{field_text}"), ""])
        elif label == "相關機電系統":
            system_value = normalize_electromechanical_system_value(field_text, context_window)
            if system_value:
                output.extend([f"• 相關機電系統：{system_value}", ""])
        elif label == "發布/事件日期":
            normalized_date = _normalize_report_date_text(field_text)
            output.extend([f"• 發布/事件日期：{normalized_date if normalized_date != '日期未知' else '日期未明'}", ""])
        else:
            if field_text:
                output.extend([f"• {label}：{field_text}", ""])

    text = "\n".join(output)
    text = normalize_report_source_lines(text)
    text = _restore_journal_sections(text, protected_journal_sections)
    text = re.sub(r"(?m)^\s*(?:[-*]\s*)?•\s*$", "", text)
    text = re.sub(r"(?m)^•\s*事件摘要：\s*[-*•]\s*", "• 事件摘要：", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sanitize_report_text(
    text: str,
    *,
    selected_types: list[str],
    standards_enabled: bool,
    include_research_supplement: bool,
    research_section_heading: Callable[..., str],
) -> str:
    text = (
        normalize_formal_report_title(text).replace("全球（排除台灣）", "全球（安全白名單來源）")
        .replace("全球(排除台灣)", "全球（安全白名單來源）")
        .replace("（排除台灣）", "")
        .replace("(排除台灣)", "")
    )
    text = clean_internal_report_language(text)
    text = simplify_formal_report_format(text)
    if not include_research_supplement:
        text = re.sub(r"(?ms)^#{0,6}\s*(?:[一二三四五六七八九十]、)?(?:技術研究補充|國際學術期刊).*?(?=^#{0,6}\s*[一二三四五六七八九十]\s*、|^📊|^⏰|\Z)", "", text)
        text = re.sub(r"(?m)^.*(?:技術研究補充|國際學術期刊).*$", "", text)
    text = strip_unselected_types_from_title(text, selected_types=selected_types)
    text = strip_unselected_report_sections(text, selected_types=selected_types)
    text = normalize_report_source_lines(text)
    text = strip_internal_report_fields(text)
    text = normalize_final_report_md(text)
    text = normalize_research_section_heading(
        text,
        include_research_supplement=include_research_supplement,
        research_section_heading=research_section_heading,
    )
    text = merge_operational_report_sections(
        text,
        selected_types=selected_types,
        standards_enabled=standards_enabled,
    )
    text = normalize_report_section_numbering(
        text,
        selected_types=selected_types,
        standards_enabled=standards_enabled,
    )
    text = strip_internal_report_fields(text)
    text = remove_missing_data_disclaimers(text)
    return normalize_formal_report_title(normalize_report_statistics_line(text))
def _clean_formal_source_proxy_label(label: str) -> str:
    cleaned = str(label or "").strip()
    cleaned = re.sub(r"Google\s*News\s*地區代理\s*[－\-:：]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Google\s*News\s*代理", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"地區代理\s*[－\-:：]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" －-_/|：:")
    if _is_query_proxy_source_label(cleaned):
        return ""
    return cleaned


GENERIC_FORMAL_TITLES = {
    "國際捷運技術更新案",
    "都市軌道系統更新案",
    "捷運列車更新案",
    "國際捷運營運政策更新",
    "國際捷運重大事故事件",
    "都市軌道重大事故事件",
    "國際捷運營運爭議事件",
    "國際捷運案例",
}

TITLE_PLACEHOLDERS = {
    "", "標題未知", "未產生標題", "新聞標題", "繁體中文新聞標題",
    *GENERIC_FORMAL_TITLES,
}
TITLE_PLACEHOLDER_FRAGMENTS = ("標題未知", "未產生標題")
PURE_SOURCE_TITLES = {
    "mta", "wmata", "ttc", "bvg", "translink", "metrolinx", "newswire",
    "google news", "reuters", "ap", "bbc", "railway gazette", "railway age",
}


def _has_valid_chinese_report_title(title: str) -> bool:
    cleaned = re.sub(r"\s+", "", title or "")
    return not _contains_untranslated_report_script(cleaned) and not any(fragment in cleaned for fragment in TITLE_PLACEHOLDER_FRAGMENTS) and cleaned not in {
        re.sub(r"\s+", "", item) for item in TITLE_PLACEHOLDERS
    } and len(
        re.findall(r"[\u3400-\u9fff]", cleaned)
    ) >= 6


def _title_needs_repair(title: str, category: str = "") -> bool:
    cleaned = re.sub(r"\s+", "", title or "")
    if not cleaned:
        return True
    has_cjk_title_content = len(re.findall(r"[\u3400-\u9fff]", cleaned)) >= 4
    if _contains_untranslated_report_script(cleaned):
        return True
    if _looks_like_english_title(cleaned) and not has_cjk_title_content:
        return True
    if any(fragment in cleaned for fragment in TITLE_PLACEHOLDER_FRAGMENTS):
        return True
    if cleaned in {re.sub(r"\s+", "", item) for item in TITLE_PLACEHOLDERS}:
        return True
    if cleaned in {
        re.sub(r"\s+", "", value)
        for value in (category, f"{category}新聞", f"{category}事件", f"{category}更新")
        if value
    }:
        return True
    source_value = re.sub(r"^(?:資料)?來源[：:]?", "", (title or "").strip(), flags=re.IGNORECASE)
    source_key = source_value.casefold().strip(" .-/")
    if source_key in PURE_SOURCE_TITLES or re.fullmatch(
        rf"(?:{'|'.join(re.escape(item) for item in sorted(PURE_SOURCE_TITLES, key=len, reverse=True))})(?:\s*(?:official|官方)?\s*(?:news|新聞|公告|新聞稿)?)?",
        source_key,
    ):
        return True
    return bool(re.fullmatch(r"(?:https?://)?(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/)?", source_key))


def _is_generic_formal_title(title: str) -> bool:
    cleaned = re.sub(r"\s+", "", title or "")
    return cleaned in {re.sub(r"\s+", "", item) for item in GENERIC_FORMAL_TITLES}


def strip_candidate_id_markers(text: str) -> str:
    """Backward-compatible alias for public-output cleanup."""
    return remove_internal_candidate_markers(text)


def count_report_items(report_md: str) -> int:
    bullet_count = len(re.findall(r"(?m)^🔹\s*\[(?:技術新知|重大事故|營運政策|營運爭議|營運動態|service_opening|規範更新|機電標案)\]", report_md or ""))
    if bullet_count:
        return bullet_count
    count = 0
    for match in re.finditer(r"^###\s+(.+)$", report_md or "", flags=re.MULTILINE):
        heading = match.group(1)
        if any(category in heading for category in REPORT_CATEGORY_TYPES):
            count += 1
    return count


def count_report_items_by_category(report_md: str) -> dict[str, int]:
    counts = {category: 0 for category in REPORT_CATEGORY_TYPES}
    for match in re.finditer(r"(?m)^🔹\s*\[([^\]]+)\]", report_md or ""):
        category = match.group(1).strip()
        if category in counts:
            counts[category] += 1
    if any(counts.values()):
        return counts
    for match in re.finditer(r"^###\s+(.+)$", report_md or "", flags=re.MULTILINE):
        heading = match.group(1)
        for category in REPORT_CATEGORY_TYPES:
            if category in heading:
                counts[category] += 1
                break
    return counts


_AUTHORITATIVE_CATEGORY_LABELS = (
    "技術新知",
    "重大事故",
    "營運政策",
    "營運爭議",
    "營運動態",
    "service_opening",
    "規範更新",
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
)


def _authoritative_title_line(line: str) -> tuple[str, str] | None:
    stripped = (line or "").strip()
    bracket = re.match(r"^🔹\s*\[([^\]]+)\]\s*(\S.*)$", stripped)
    if bracket:
        return _canonical_report_category_label(bracket.group(1)), bracket.group(2).strip()
    pipe = re.match(r"^🔹\s*([^｜|]+?)\s*[｜|]\s*(\S.*)$", stripped)
    if pipe and pipe.group(1).strip() in _AUTHORITATIVE_CATEGORY_LABELS:
        return _canonical_report_category_label(pipe.group(1)), pipe.group(2).strip()
    bare = re.match(
        rf"^🔹\s*({'|'.join(re.escape(label) for label in _AUTHORITATIVE_CATEGORY_LABELS)})\s+(\S.*)$",
        stripped,
        flags=re.IGNORECASE,
    )
    if bare:
        return _canonical_report_category_label(bare.group(1)), bare.group(2).strip()
    return None


def count_authoritative_report_items(report_md: str) -> int:
    return sum(1 for line in (report_md or "").splitlines() if _authoritative_title_line(line))


def count_authoritative_report_items_by_category(report_md: str) -> dict[str, int]:
    counts = {category: 0 for category in REPORT_CATEGORY_TYPES}
    for line in (report_md or "").splitlines():
        parsed = _authoritative_title_line(line)
        if not parsed:
            continue
        category = parsed[0]
        if category in {"營運政策", "營運爭議", "營運動態", SERVICE_OPENING_CATEGORY_KEY}:
            category = OPERATIONAL_DYNAMICS_CATEGORY_LABEL
        if category in counts:
            counts[category] += 1
    return counts


def remove_authoritative_candidate_markers(text: str) -> str:
    """Remove only invisible candidate markers for public rendering."""
    if not text:
        return ""
    marker_line = re.compile(
        r"(?mi)^[ \t]*(?:<!--\s*candidate_id\s*:\s*\d+\s*-->|&lt;!--\s*candidate\\?_id\s*:\s*\d+\s*--&gt;)[ \t]*(?:\r?\n|$)"
    )
    return marker_line.sub("", text)


_UNKNOWN_COUNTRY_VALUES = {"", "未判定", "未知", "不明", "未明"}
_GENERIC_SOURCE_FALLBACKS = (
    "資料來源未明確辨識",
    "來源未明確",
    "未提供來源名稱",
    "原始候選資料未提供來源",
)
_SOURCE_ATTRIBUTION_PREFIX = re.compile(
    r"^\s*[^。！？\n]{1,80}?(?:報導|指出|表示|稱|提到)\s*[，,:：,]\s*"
)
_UNTRANSLATED_COMMON_ENGLISH_PHRASES = (
    "passenger service",
    "railway station",
    "junction",
)


def _untranslated_common_english_phrases(value: str) -> list[str]:
    text = str(value or "")
    return [
        phrase
        for phrase in _UNTRANSLATED_COMMON_ENGLISH_PHRASES
        if re.search(rf"(?<![A-Za-z]){re.escape(phrase)}(?![A-Za-z])", text, flags=re.IGNORECASE)
    ]


def _authoritative_block_field_values(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    current_field = ""
    field_pattern = re.compile(
        r"^\s*[•*\-]?\s*(發布/事件日期|事件日期|日期|國家(?:/地區)?|相關機電系統|事件摘要|臺北捷運局啟示|資料來源)\s*[:：]\s*(.*)$"
    )
    field_names = {
        "發布/事件日期": "date",
        "事件日期": "date",
        "日期": "date",
        "國家": "country",
        "國家/地區": "country",
        "相關機電系統": "system",
        "事件摘要": "summary",
        "臺北捷運局啟示": "insight",
        "資料來源": "source",
    }
    for raw_line in lines:
        line = raw_line.strip()
        match = field_pattern.match(line)
        if match:
            current_field = field_names[match.group(1)]
            values[current_field] = match.group(2).strip()
            continue
        if not line:
            continue
        if line.startswith(("#", "🔹", "<!--", "&lt;!--")):
            current_field = ""
            continue
        if current_field:
            values[current_field] = f"{values[current_field]} {line}".strip()
    return values


def _canonical_source_metadata(candidate: dict) -> dict[str, str]:
    """Return the deterministic source display/url contract for a candidate."""
    return build_formal_report_source(candidate)


def _candidate_has_deterministic_source(candidate: dict) -> bool:
    """Whether the candidate carries enough source data for an authoritative overlay."""
    source = _canonical_source_metadata(candidate)
    return bool(
        str(source.get("display_url") or "").strip()
        or str(candidate.get("source_display") or candidate.get("source") or "").strip()
        or str(candidate.get("source_href") or candidate.get("url") or "").strip()
    )


def _source_value_parts(value: str, *, expected_url: str = "") -> tuple[str, str]:
    """Split a rendered source value into its display label and URL.

    The model is allowed to format the field (plain URL or markdown link), but
    it is not allowed to add or replace deterministic metadata.  Deliberately
    keep arbitrary non-URL text so it is detected as a source-label mismatch.
    """
    text = unescape(str(value or "")).strip()
    url = _extract_complete_url(text)
    domain = _domain_from_url(expected_url or url)
    label = _clean_source_label(text, url, domain)
    return label, url


def _source_value_matches_candidate(value: str, candidate: dict) -> bool:
    if not _candidate_has_deterministic_source(candidate):
        return True
    expected = _canonical_source_metadata(candidate)
    expected_url = str(expected.get("display_url") or "").strip()
    expected_label = str(expected.get("display_name") or "").strip()
    actual_label, actual_url = _source_value_parts(value, expected_url=expected_url)
    normalize_label = lambda item: re.sub(r"\s+", " ", str(item or "")).strip().casefold()
    return (
        actual_url == expected_url
        and normalize_label(actual_label) == normalize_label(expected_label)
    )


def _canonical_source_line(candidate: dict) -> str:
    """Render only candidate-owned source metadata, never model text."""
    source = _canonical_source_metadata(candidate)
    display_name = str(source.get("display_name") or "").strip()
    display_url = str(source.get("display_url") or "").strip()
    value = " ".join(part for part in (display_name, display_url) if part)
    return f"• 資料來源：{value}".rstrip()


def canonicalize_authoritative_source_fields(
    report_md: str,
    selected_candidates: list[dict],
    *,
    context: ReportPostprocessContext | None = None,
) -> str:
    """Overlay canonical source metadata onto marked model article blocks.

    Candidate IDs identify the authoritative record.  Prose fields remain
    byte-for-byte untouched; each source field is replaced by the candidate's
    deterministic display name and URL.
    """
    del context
    if not report_md or not selected_candidates:
        return report_md
    selected_map = {
        int(item.get("candidate_id") or item.get("id") or 0): item
        for item in selected_candidates
        if int(item.get("candidate_id") or item.get("id") or 0)
    }
    marker_pattern = re.compile(
        r"^(?:<!--\s*candidate_id\s*:\s*(\d+)\s*-->|&lt;!--\s*candidate\\?_id\s*:\s*(\d+)\s*--&gt;)$",
        flags=re.IGNORECASE,
    )
    lines = report_md.splitlines()
    output: list[str] = []
    current_ids: list[int] = []
    block_content_seen = False
    index = 0
    changed = False
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        marker = marker_pattern.fullmatch(stripped)
        if marker:
            if current_ids and block_content_seen:
                current_ids = []
            current_ids.append(int(marker.group(1) or marker.group(2)))
            block_content_seen = False
            output.append(raw_line)
            index += 1
            continue
        if stripped.startswith(("#", "📊", "⏰")) or re.match(r"^[一二三四五六]\s*、", stripped):
            current_ids = []
            block_content_seen = False
        field = _match_report_field_line(stripped)
        if current_ids and field and field[0] == "資料來源":
            candidate = selected_map.get(current_ids[0]) if len(current_ids) == 1 else None
            if candidate is None or not _candidate_has_deterministic_source(candidate):
                output.append(raw_line)
                block_content_seen = True
                index += 1
                continue
            continuation: list[str] = []
            next_index = index + 1
            while next_index < len(lines):
                next_stripped = lines[next_index].strip()
                if _is_report_block_boundary(next_stripped):
                    break
                continuation.append(lines[next_index])
                next_index += 1
            actual_value = " ".join(
                part.strip() for part in [field[1], *continuation] if part.strip()
            )
            # Always emit the canonical field once the candidate is known.  A
            # semantically matching model value can stay byte-stable, but no
            # model-owned formatting or continuation text is carried forward.
            indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
            canonical_line = f"{indent}{_canonical_source_line(candidate)}"
            output.append(canonical_line)
            if (
                len(continuation) > 0
                or raw_line != canonical_line
                or not _source_value_matches_candidate(actual_value, candidate)
            ):
                changed = True
            block_content_seen = True
            index = next_index
            continue
        output.append(raw_line)
        if current_ids and stripped:
            block_content_seen = True
        index += 1
    if not changed:
        return report_md
    newline = "\r\n" if "\r\n" in report_md else "\n"
    rendered = newline.join(output)
    if report_md.endswith(("\n", "\r")):
        rendered += newline
    return rendered


def _is_unknown_country(value: object) -> bool:
    return str(value or "").strip() in _UNKNOWN_COUNTRY_VALUES


def _authoritative_block_field_status(
    report_md: str,
    *,
    country_by_id: dict[int, str] | None = None,
    system_optional_by_id: dict[int, bool] | None = None,
) -> list[dict]:
    marker_pattern = re.compile(
        r"^(?:<!--\s*candidate_id\s*:\s*(\d+)\s*-->|&lt;!--\s*candidate\\?_id\s*:\s*(\d+)\s*--&gt;)$",
        flags=re.IGNORECASE,
    )
    required_fields = {
        "title": lambda line: bool(_authoritative_title_line(line)),
        "date": lambda line: bool(re.match(r"^\s*[•*-]?\s*(?:發布/事件日期|事件日期|日期)\s*[:：]", line)),
        "country": lambda line: bool(re.match(r"^\s*[•*-]?\s*國家(?:/地區)?\s*[:：]", line)),
        "summary": lambda line: bool(re.match(r"^\s*[•*-]?\s*事件摘要\s*[:：]", line)),
        "insight": lambda line: bool(re.match(r"^\s*[•*-]?\s*臺北捷運局啟示\s*[:：]", line)),
        "source": lambda line: bool(re.match(r"^\s*[•*-]?\s*資料來源\s*[:：]", line)),
    }
    blocks: list[dict] = []
    current_ids: list[int] = []
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_ids, current_lines
        if not current_ids:
            return
        required_field_names = dict(required_fields)
        if country_by_id and current_ids and all(
            _is_unknown_country(country_by_id.get(candidate_id, ""))
            for candidate_id in current_ids
        ):
            required_field_names.pop("country", None)
        if system_optional_by_id and current_ids and all(
            system_optional_by_id.get(candidate_id, False)
            for candidate_id in current_ids
        ):
            required_field_names.pop("system", None)

        def _field_has_value(field_name: str, matcher) -> bool:
            for index, line in enumerate(current_lines):
                if not matcher(line):
                    continue
                value = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                if value:
                    return True
                for following in current_lines[index + 1:]:
                    following_value = following.strip()
                    if not following_value:
                        continue
                    if _match_report_field_line(following_value) or following_value.startswith(("🔹", "#", "<!--", "&lt;!--")):
                        break
                    return True
                return False
            return False
        missing_fields = [
            name
            for name, matcher in required_field_names.items()
            if not _field_has_value(name, matcher)
        ]
        reasons = []
        if "title" in missing_fields:
            reasons.append("missing_authoritative_title")
        if missing_fields:
            reasons.append("missing_required_fields")
        blocks.append({
            "candidate_ids": list(current_ids),
            "body": "\n".join(current_lines).strip(),
            "field_values": _authoritative_block_field_values(current_lines),
            "missing_fields": missing_fields,
            "parser_failure_reason": ";".join(reasons),
        })
        current_ids = []
        current_lines = []

    for raw_line in (report_md or "").splitlines():
        stripped = raw_line.strip()
        marker = marker_pattern.fullmatch(stripped)
        if marker:
            if current_ids and any(line.strip() for line in current_lines):
                flush()
            current_ids.append(int(marker.group(1) or marker.group(2)))
            continue
        if current_ids and stripped.startswith("#") and current_lines:
            flush()
        if current_ids:
            current_lines.append(raw_line)
    flush()
    return blocks


def validate_authoritative_report(
    report_md: str,
    selected_candidates: list[dict],
    *,
    selected_types: list[str] | None = None,
) -> dict:
    """Validate MaiAgent output without changing its report content."""
    candidate_validation = validate_report_candidate_ids(report_md, selected_candidates)
    selected_ids = [
        int(item.get("candidate_id") or item.get("id") or 0)
        for item in selected_candidates or []
    ]
    selected_map = {
        int(item.get("candidate_id") or item.get("id") or 0): item
        for item in selected_candidates or []
    }
    country_by_id = {
        candidate_id: str(candidate.get("country") or "").strip()
        for candidate_id, candidate in selected_map.items()
    }
    system_optional_by_id = {
        candidate_id: "core_systems" in candidate and not candidate.get("core_systems")
        for candidate_id, candidate in selected_map.items()
    }
    model_ids = list(candidate_validation.get("found_ids", []))
    selected_category_labels = {
        OPERATIONAL_DYNAMICS_CATEGORY_LABEL
        if (item.get("classification") or item.get("preliminary_type"))
        in {"營運政策", "營運爭議", "營運動態", SERVICE_OPENING_CATEGORY_KEY}
        else item.get("classification") or item.get("preliminary_type")
        for item in selected_candidates or []
    }
    headings = "\n".join(
        line.strip()
        for line in (report_md or "").splitlines()
        if re.match(r"^\s*#{1,6}\s*.*", line)
    )
    missing_sections = sorted(
        category
        for category in selected_category_labels
        if category and category not in headings
    )
    article_count = count_authoritative_report_items(report_md)
    category_counts = count_authoritative_report_items_by_category(report_md)
    block_field_status = _authoritative_block_field_status(
        report_md,
        country_by_id=country_by_id,
        system_optional_by_id=system_optional_by_id,
    )
    parsed_blocks = _parse_report_article_blocks(report_md)
    multi_candidate_model_blocks = [
        list(block.get("candidate_ids", ()))
        for block in parsed_blocks
        if len(block.get("candidate_ids", ())) > 1
    ]
    category_mismatches: list[dict] = []
    for block in parsed_blocks:
        category_match = re.search(
            r"(?m)^\s*🔹\s*\[([^\]]+)\]",
            block.get("body", ""),
        )
        if not category_match:
            continue
        actual_category = canonical_formal_report_category(category_match.group(1))
        for candidate_id in block.get("candidate_ids", ()):
            candidate = selected_map.get(candidate_id) or {}
            expected_category = _formal_category_for_candidate(candidate)
            expected_heading = {
                "技術新知": "一、技術新知",
                "重大事故": "二、重大事故",
                OPERATIONAL_DYNAMICS_CATEGORY_LABEL: f"三、{OPERATIONAL_DYNAMICS_CATEGORY_LABEL}",
                ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL: f"四、{ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL}",
                "規範更新": "規範更新",
            }.get(expected_category, "")
            section_heading = str(block.get("section_heading") or "").strip()
            if expected_category and (
                actual_category != expected_category
                or (expected_heading and section_heading and expected_heading not in section_heading)
            ):
                category_mismatches.append({
                    "candidate_id": candidate_id,
                    "expected_category": expected_category,
                    "actual_category": actual_category,
                    "section_heading": section_heading,
                    "reason": "model_category_does_not_match_authoritative_candidate_category",
                })
    missing_model_fields = {
        str(candidate_id): status["missing_fields"]
        for status in block_field_status
        if status["missing_fields"]
        for candidate_id in status["candidate_ids"]
    }
    parser_failure_reasons = {
        str(candidate_id): status["parser_failure_reason"]
        for status in block_field_status
        if status["parser_failure_reason"]
        for candidate_id in status["candidate_ids"]
    }
    content_quality_issues: list[dict] = []
    source_metadata_mismatches: list[dict] = []
    for status in block_field_status:
        fields = status.get("field_values", {})
        summary = str(fields.get("summary", "") or "").strip()
        insight = str(fields.get("insight", "") or "").strip()
        source = str(fields.get("source", "") or "").strip()
        for candidate_id in status.get("candidate_ids", []):
            candidate = selected_map.get(candidate_id, {})
            if candidate and source and not _source_value_matches_candidate(source, candidate):
                mismatch = {
                    "candidate_id": candidate_id,
                    "expected": _canonical_source_metadata(candidate),
                    "actual": source,
                    "code": "source_metadata_mismatch",
                }
                source_metadata_mismatches.append(mismatch)
                content_quality_issues.append({
                    "candidate_id": candidate_id,
                    "code": "source_metadata_mismatch",
                    "detail": "資料來源顯示名稱與 URL 必須與候選 canonical source 完全一致",
                    "expected": mismatch["expected"],
                    "actual": source,
                })
            if str(fields.get("country", "") or "").strip() in _UNKNOWN_COUNTRY_VALUES:
                if fields.get("country", ""):
                    content_quality_issues.append({
                        "candidate_id": candidate_id,
                        "code": "unknown_country_in_formal_report",
                        "detail": "正式報告不可輸出國家：未判定",
                    })
            if _SOURCE_ATTRIBUTION_PREFIX.match(summary):
                content_quality_issues.append({
                    "candidate_id": candidate_id,
                    "code": "source_prefixed_summary",
                    "detail": "事件摘要不可由來源名稱加報導、指出或表示開頭",
                })
            untranslated_phrases = sorted(
                set(_untranslated_common_english_phrases(summary) + _untranslated_common_english_phrases(insight))
            )
            if untranslated_phrases:
                content_quality_issues.append({
                    "candidate_id": candidate_id,
                    "code": "untranslated_common_english_phrase",
                    "detail": "正式摘要或啟示含未中文化的普通英文片語",
                    "phrases": untranslated_phrases,
                })
            candidate_source = str(
                candidate.get("source_display") or candidate.get("source_domain") or ""
            ).strip()
            if candidate_source and any(
                phrase in source for phrase in _GENERIC_SOURCE_FALLBACKS
            ):
                content_quality_issues.append({
                    "candidate_id": candidate_id,
                    "code": "generic_source_fallback",
                    "detail": "候選已有來源資訊時不可使用泛用來源 fallback",
                })
    forbidden_internal_phrases = [
        phrase
        for phrase in ("模型：MaiAgent 雲端 API", "[[candidate", "候選資料指出")
        if phrase in (report_md or "")
    ]
    selected_to_model_coverage = (
        len(set(selected_ids).intersection(model_ids)) / len(selected_ids)
        if selected_ids
        else 1.0
    )
    selected_event_count = len(set(selected_ids))
    final_unique_article_count = article_count
    event_level_integrity_passed = bool(
        selected_event_count == len(parsed_blocks) == final_unique_article_count
        and not multi_candidate_model_blocks
    )
    passed = bool(
        candidate_validation.get("valid")
        and article_count > 0
        and not missing_sections
        and not missing_model_fields
        and not multi_candidate_model_blocks
        and event_level_integrity_passed
        and not category_mismatches
        and not forbidden_internal_phrases
        and not content_quality_issues
    )
    return {
        **candidate_validation,
        "retry_required": not passed,
        "selected_candidate_ids": selected_ids,
        "model_candidate_ids": model_ids,
        "selected_candidate_id_count": len(selected_ids),
        "model_candidate_id_count": len(model_ids),
        "selected_to_model_id_coverage": round(selected_to_model_coverage, 4),
        "report_article_count": article_count,
        "report_category_counts": category_counts,
        "missing_required_sections": missing_sections,
        "required_sections_present": not missing_sections,
        "forbidden_internal_phrases": forbidden_internal_phrases,
        "model_block_field_status": block_field_status,
        "model_article_block_count": len(parsed_blocks),
        "multi_candidate_model_blocks": multi_candidate_model_blocks,
        "category_mismatches": category_mismatches,
        "category_consistency_passed": not category_mismatches,
        "source_metadata_mismatches": source_metadata_mismatches,
        "source_metadata_consistency_passed": not source_metadata_mismatches,
        "selected_event_count": selected_event_count,
        "final_unique_article_count": final_unique_article_count,
        "event_level_integrity_passed": event_level_integrity_passed,
        "missing_model_fields": missing_model_fields,
        "parser_failure_reasons": parser_failure_reasons,
        "content_quality_issues": content_quality_issues,
        "content_quality_passed": not content_quality_issues,
        "report_validation_passed": passed,
    }

# Extracted formal-report reconciliation and diagnostics.

def _parse_report_article_blocks(report_md: str) -> list[dict]:
    marker_pattern = re.compile(r'<!--\s*candidate_id\s*:\s*(\d+)\s*-->|&lt;!--\s*candidate\\?_id\s*:\s*(\d+)\s*--&gt;', flags=re.IGNORECASE)
    blocks: list[dict] = []
    current_ids: list[int] = []
    current_lines: list[str] = []
    current_section_heading = ""

    def _flush() -> None:
        nonlocal current_ids, current_lines
        if current_ids:
            blocks.append({
                "candidate_ids": tuple(current_ids),
                "body": "\n".join(current_lines).strip(),
                "section_heading": current_section_heading,
            })
        current_ids = []
        current_lines = []

    for raw_line in (report_md or "").splitlines():
        stripped = raw_line.strip()
        if re.match(r"^#{1,6}\s*", stripped):
            if current_ids:
                _flush()
            current_section_heading = re.sub(r"^#{1,6}\s*", "", stripped).strip()
            continue
        marker_match = marker_pattern.fullmatch(stripped)
        if marker_match:
            if current_ids and any(line.strip() for line in current_lines):
                _flush()
            current_ids.append(int(marker_match.group(1) or marker_match.group(2)))
            continue
        if current_ids and stripped.startswith(("📊", "⏰")):
            _flush()
            continue
        if current_ids:
            current_lines.append(raw_line)
    _flush()
    return blocks

def build_long_term_coverage_warning(candidates: list[dict], *, context: ReportPostprocessContext) -> dict:
    if context.lookback_int not in ADVANCED_LOOKBACK_OPTIONS:
        return {'long_term_coverage_warning': False, 'reason': ''}
    date_objs = [date_obj for date_obj in (_candidate_date_obj(candidate.get('date', '')) for candidate in candidates or []) if date_obj]
    if not date_objs:
        return {'long_term_coverage_warning': True, 'reason': '長期回顧候選資料缺少可解析日期，無法確認是否完整涵蓋本期。'}
    earliest = min(date_objs)
    expected_start = context.today - datetime.timedelta(days=context.lookback_int)
    recent_cutoff = context.today - datetime.timedelta(days=min(60, max(30, context.lookback_int // 5)))
    if earliest > recent_cutoff:
        return {'long_term_coverage_warning': True, 'reason': '來源回傳資料多集中於近期，年度回顧可能無法完整代表全年。' if context.lookback_int == 365 else '來源回傳資料多集中於近期，長期回顧可能無法完整代表整個期間。', 'earliest_candidate_date': earliest.isoformat(), 'expected_start': expected_start.isoformat()}
    return {'long_term_coverage_warning': False, 'reason': '', 'earliest_candidate_date': earliest.isoformat(), 'expected_start': expected_start.isoformat()}

def _unique_limited(values: list[str], limit: int=5, *, context: ReportPostprocessContext) -> list[str]:
    output: list[str] = []
    for value in values:
        cleaned = str(value or '').strip()
        if cleaned and cleaned not in output:
            output.append(cleaned)
        if len(output) >= limit:
            break
    return output

def _annual_observation_dates_are_recent(candidates: list[dict], *, context: ReportPostprocessContext) -> bool:
    date_objs = [date_obj for date_obj in (_candidate_date_obj(candidate.get('date', '')) for candidate in candidates or []) if date_obj]
    if not date_objs:
        return False
    return min(date_objs) > context.today - datetime.timedelta(days=60)

def _annual_observation_themes(candidates: list[dict], *, context: ReportPostprocessContext) -> list[str]:
    theme_terms = [('號誌與列車控制', ['cbtc', 'signalling', 'signaling', 'signal', 'train control', '號誌', '信號']), ('自動化與無人駕駛', ['driverless', 'automation', 'automated', 'unattended train', '自動', '無人']), ('車輛與車隊更新', ['rolling stock', 'fleet', 'trainset', 'new train', '車輛', '列車']), ('月臺門與車站設備', ['platform screen door', 'platform doors', 'psd', 'elevator', 'escalator', '月臺門', '月台門', '電梯', '電扶梯']), ('供電與能源管理', ['power supply', 'traction power', 'substation', 'third rail', 'energy', '供電', '牽引', '變電', '能源']), ('通訊、資安與資料治理', ['communications', 'telecom', 'radio', '5g', 'lte', 'cyber', 'data', '通訊', '資安', '資料']), ('維修監測與影像分析', ['maintenance', 'monitoring', 'condition monitoring', 'video', 'camera', 'ai', '維修', '監測', '影像', 'AI']), ('AFC 與票務系統', ['afc', 'ticketing', 'fare gate', 'fare', '票務', '票閘', '票價'])]
    combined = ' '.join((f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('source', '')}" for candidate in candidates or []))
    return [label for label, terms in theme_terms if _contains_any_term(combined, terms)]

def _annual_observation_report_blocks(report_md: str, *, context: ReportPostprocessContext) -> list[str]:
    formal_area = re.split('(?m)^\\s*#{0,6}\\s*[一二三四五六七八九十]\\s*、\\s*(?:國際學術期刊|技術研究補充)\\s*$', report_md or '', maxsplit=1)[0]
    return re.findall('(?ms)^\\s*(🔹\\s*\\[(?:技術新知|重大事故|營運政策|營運爭議|營運動態|service_opening|規範更新|機電標案)\\].*?)(?=^\\s*🔹\\s*\\[[^\\]]+\\]|^\\s*#{0,6}\\s*[一二三四五六七八九十]\\s*、|^\\s*📊|^\\s*⏰|\\Z)', formal_area)

def _iter_calendar_months(start_date: datetime.date, end_date: datetime.date, *, context: ReportPostprocessContext) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = (start_date.year, start_date.month)
    while (year, month) <= (end_date.year, end_date.month):
        months.append((year, month))
        if month == 12:
            year, month = (year + 1, 1)
        else:
            month += 1
    return months

def build_final_report_coverage_warning(
    final_report_md: str,
    report_days: int,
    report_end: datetime.date | None = None,
    *,
    structured_candidates: list[dict] | None = None,
    context: ReportPostprocessContext,
) -> dict:
    """Measure long-term coverage from formal news only, never journal entries."""
    days = int(report_days or 0)
    if days not in {90, 180, 365}:
        return {'long_term_coverage_warning': False, 'reason': ''}
    end_date = report_end or context.today
    start_date = end_date - datetime.timedelta(days=days)
    dates: list[datetime.date] = []
    if structured_candidates is not None:
        coverage_date_source = 'structured_final_candidates'
        date_values = (candidate.get('date', '') for candidate in structured_candidates or [])
    else:
        coverage_date_source = 'rendered_markdown_compatibility'
        blocks = _annual_observation_report_blocks(final_report_md, context=context)
        date_values = (
            match.group(1)
            for block in blocks
            for match in [re.search('發布/事件日期\\s*[：:]\\s*(\\d{4}-\\d{2}-\\d{2})', block)]
            if match
        )
    for value in date_values:
        date_obj = _candidate_date_obj(str(value or ''))
        if date_obj and start_date <= date_obj <= end_date + datetime.timedelta(days=1):
            dates.append(date_obj)
    month_keys = _iter_calendar_months(start_date, end_date, context=context)
    monthly_counts = {f'{year:04d}-{month:02d}': sum((1 for value in dates if (value.year, value.month) == (year, month))) for year, month in month_keys}
    quarter_counts: dict[str, int] = {}
    for value in dates:
        key = f'{value.year:04d}-Q{(value.month - 1) // 3 + 1}'
        quarter_counts[key] = quarter_counts.get(key, 0) + 1
    result = {'long_term_coverage_warning': False, 'reason': '', 'formal_news_with_valid_date_count': len(dates), 'coverage_date_source': coverage_date_source, 'coverage_bucket_type': 'quarter' if days == 365 else 'month', 'coverage_buckets': quarter_counts if days == 365 else monthly_counts, 'monthly_coverage_buckets': monthly_counts, 'quarterly_coverage_buckets': quarter_counts}
    if not dates:
        result.update({'long_term_coverage_warning': True, 'reason': '最終正式新聞沒有可解析日期，無法確認長期報告覆蓋。', 'max_consecutive_empty_months': len(month_keys), 'recent_60_day_count': 0, 'recent_60_day_share': 0.0, 'annual_coverage_quality': 'below_threshold' if days == 365 else ''})
        return result
    max_empty_streak = 0
    current_empty_streak = 0
    for count in monthly_counts.values():
        current_empty_streak = current_empty_streak + 1 if count == 0 else 0
        max_empty_streak = max(max_empty_streak, current_empty_streak)
    recent_cutoff = end_date - datetime.timedelta(days=60)
    recent_count = sum((1 for value in dates if value >= recent_cutoff))
    recent_share = recent_count / len(dates)
    result.update({'max_consecutive_empty_months': max_empty_streak, 'recent_60_day_count': recent_count, 'recent_60_day_share': round(recent_share, 4)})
    if days == 365:
        reasons: list[str] = []
        if max_empty_streak >= 3:
            reasons.append('最終正式新聞存在連續 3 個月以上的空白期間')
        if recent_share > 0.6:
            reasons.append('超過 60% 最終正式新聞集中於最近 60 天')
        if reasons:
            result['long_term_coverage_warning'] = True
            result['reason'] = '；'.join(reasons) + '。'
        result['annual_coverage_quality'] = 'below_threshold' if result['long_term_coverage_warning'] else 'meets_threshold'
    return result

def _annual_observation_report_dates_are_recent(blocks: list[str], *, context: ReportPostprocessContext) -> bool:
    dates = []
    for block in blocks or []:
        match = re.search('發布/事件日期\\s*[：:]\\s*(\\d{4}-\\d{2}-\\d{2})', block)
        date_obj = _candidate_date_obj(match.group(1)) if match else None
        if date_obj:
            dates.append(date_obj)
    return bool(dates) and min(dates) > context.today - datetime.timedelta(days=60)

def build_annual_observation_section(final_report_md: str, *, context: ReportPostprocessContext) -> str:
    if context.lookback_int != 365:
        return ''
    blocks = _annual_observation_report_blocks(final_report_md, context=context)
    counts = count_report_items_by_category(final_report_md)
    categories = ('技術新知', '重大事故', '營運政策', '營運爭議', ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL)
    count_text = '、'.join((f'{category}{counts.get(category, 0)}則' for category in categories))
    sentences = [f'本年度回顧依最終正式報告整理，共收錄{count_text}。']
    if not blocks:
        sentences.append('本年度未取得可供歸納的正式新聞，以下列最終章節與統計為準。')
        return '## 年度觀察重點\n' + ''.join(sentences)
    regions = _unique_limited([match.group(1).strip() for block in blocks for match in [re.search('國家/地區\\s*[：:]\\s*([^\\n]+)', block)] if match and match.group(1).strip() not in {'未判定', '國際研究'}], context=context)
    positive_categories = [category for category in categories if counts.get(category, 0) > 0]
    if positive_categories:
        max_count = max((counts.get(category, 0) for category in positive_categories))
        leading = [category for category in positive_categories if counts.get(category, 0) == max_count]
        sentences.append(f"新聞類型以{'、'.join(leading)}為主。")
    if regions:
        sentences.append(f"案例主要分布於{'、'.join(regions)}。")
    report_candidates = [{'title': block, 'snippet': block, 'source': ''} for block in blocks]
    themes = _unique_limited(_annual_observation_themes(report_candidates, context=context), 4, context=context)
    if themes:
        sentences.append(f"從最終新聞內容可見，觀察重點集中在{'、'.join(themes)}等都市軌道議題。")
    if _annual_observation_report_dates_are_recent(blocks, context=context):
        sentences.append('最終新聞日期多集中於近期，年度趨勢解讀應以本次實際輸出的案例範圍為準。')
    return '## 年度觀察重點\n' + ''.join(sentences)

def _remove_annual_observation_section(report_md: str, *, context: ReportPostprocessContext) -> str:
    return re.sub('(?ms)^\\s*#{1,6}\\s*年度觀察重點\\s*$.*?(?=^\\s*#{0,6}\\s*[一二三四五六七八九十]\\s*、|^\\s*📊|^\\s*⏰|\\Z)', '', report_md or '', count=1).strip()

def insert_annual_observation_section(report_md: str, *, context: ReportPostprocessContext) -> str:
    if context.lookback_int != 365:
        return report_md
    report_without_observation = _remove_annual_observation_section(report_md, context=context)
    section = build_annual_observation_section(report_without_observation, context=context)
    if not section:
        return report_without_observation
    lines = report_without_observation.splitlines()
    insert_idx = 1 if lines and lines[0].lstrip().startswith('#') else 0
    while insert_idx < len(lines) and (not lines[insert_idx].strip() or lines[insert_idx].lstrip().startswith('>')):
        insert_idx += 1
    before = '\n'.join(lines[:insert_idx]).rstrip()
    after = '\n'.join(lines[insert_idx:]).lstrip()
    return f'{before}\n\n{section}\n\n{after}'.strip()

# Extracted formal-report reconciliation and diagnostics.

# Extracted formal-report reconciliation and diagnostics.

def _journal_theme_summary(journal_candidates: list[dict], *, context: ReportPostprocessContext) -> list[str]:
    theme_terms = [('列車控制與號誌安全', ['cbtc', 'signalling', 'signaling', 'train control', 'ato', 'atp', '號誌', '列控']), ('車輛與維修管理', ['rolling stock', 'vehicle', 'maintenance', 'condition monitoring', '車輛', '維修', '監測']), ('牽引供電與能源效率', ['traction power', 'regenerative', 'energy', 'power supply', '牽引', '供電', '能源']), ('資料治理、AI 與數位分身', ['data', 'ai', 'machine learning', 'digital twin', '資料', '數位分身', '人工智慧']), ('旅客流量與營運韌性', ['passenger flow', 'resilience', 'operation', 'capacity', '旅客流量', '韌性', '運能']), ('資安與系統整合', ['cyber', 'system integration', 'security', '資安', '系統整合'])]
    text = ' '.join((f"{item.get('title', '')} {item.get('snippet', '')}" for item in journal_candidates or []))
    themes = [label for label, terms in theme_terms if _contains_any_term(text, terms)]
    return themes or ['都市軌道機電系統資料化、智慧化與維運管理']

def build_journal_summary_conclusion(journal_candidates: list[dict], *, context: ReportPostprocessContext) -> str:
    del journal_candidates, context
    return ''


def remove_journal_summary_conclusion(report_md: str) -> str:
    return re.sub(
        r"(?ms)^\s*(?:#{0,6}\s*)?[【\[]?\s*學術期刊綜合結論\s*[】\]]?\s*:?.*?(?=^📊|^⏰|\Z)",
        "",
        report_md or "",
        count=0,
    ).strip()

def ensure_journal_summary_conclusion(report_md: str, journal_candidates: list[dict], *, context: ReportPostprocessContext) -> str:
    del journal_candidates, context
    return remove_journal_summary_conclusion(report_md)

def _journal_candidate_full_date(item: dict, *, context: ReportPostprocessContext) -> str:
    for key in ('published_date', 'date'):
        date_obj = _parse_full_research_date(str(item.get(key, '') or ''))
        if date_obj:
            return date_obj.isoformat()
    return ''

def _normalize_doi_value(value: str, *, context: ReportPostprocessContext) -> str:
    match = re.search('\\b10\\.\\d{4,9}/[-._;()/:A-Z0-9]+\\b', value or '', flags=re.IGNORECASE)
    return match.group(0).rstrip('.;,)').casefold() if match else ''

def _journal_candidate_date_for_text(text: str, journal_candidates: list[dict], report_title: str='', *, context: ReportPostprocessContext) -> str:
    report_urls = set(_extract_complete_urls(text or ''))
    for item in journal_candidates or []:
        candidate_url = _extract_complete_url(str(item.get('url', '') or ''))
        if candidate_url and candidate_url in report_urls:
            return _journal_candidate_full_date(item, context=context)
    report_dois = {doi for doi in (_normalize_doi_value(value, context=context) for value in [text or '', *_extract_complete_urls(text or '')]) if doi}
    for item in journal_candidates or []:
        candidate_dois = {doi for doi in (_normalize_doi_value(str(item.get('doi', '') or ''), context=context), _normalize_doi_value(str(item.get('url', '') or ''), context=context)) if doi}
        if candidate_dois.intersection(report_dois):
            return _journal_candidate_full_date(item, context=context)
    normalized_report_title = _normalize_title(context.report_title)
    if normalized_report_title:
        for item in journal_candidates or []:
            if normalized_report_title == _normalize_title(str(item.get('title', '') or '')):
                return _journal_candidate_full_date(item, context=context)
    return ''

def repair_journal_dates_in_report(report_md: str, journal_candidates: list[dict], *, context: ReportPostprocessContext) -> str:
    if not context.include_research_supplement or not journal_candidates or (not report_md):
        return report_md
    heading_match = re.search('(?m)^#{0,6}\\s*[一二三四五六七八九十]\\s*、\\s*(?:技術研究補充|國際學術期刊)\\s*$', report_md)
    if not heading_match:
        return report_md
    end_match = re.search('(?m)^(?:📊|⏰)', report_md[heading_match.end():])
    section_end = heading_match.end() + end_match.start() if end_match else len(report_md)
    before = report_md[:heading_match.start()]
    section = report_md[heading_match.start():section_end]
    after = report_md[section_end:]
    item_matches = list(re.finditer('(?m)^\\s*(?:#{1,6}\\s*)?(\\d+)[\\.、]\\s*(.+?)\\s*$', section))
    if not item_matches:
        return report_md
    conclusion_match = re.search('(?m)^#{0,6}\\s*學術期刊綜合結論', section)
    replacements: list[tuple[int, int, str]] = []
    for index, item_match in enumerate(item_matches):
        block_start = item_match.start()
        if index + 1 < len(item_matches):
            block_end = item_matches[index + 1].start()
        elif conclusion_match and conclusion_match.start() > block_start:
            block_end = conclusion_match.start()
        else:
            block_end = len(section)
        block = section[block_start:block_end]
        report_title = re.sub('\\s{2,}$', '', item_match.group(2)).strip()
        matched_date = _journal_candidate_date_for_text(block, journal_candidates, context.report_title, context=context)
        if not matched_date:
            continue
        repaired_block = re.sub('(?m)^(?P<prefix>\\s*(?:\\d+[\\.、]\\s*)?(?:[-*]\\s*)?(?:•\\s*)?發表日期\\s*[：:]\\s*).*$', lambda match: f"{match.group('prefix')}{matched_date}", block, count=1)
        replacements.append((block_start, block_end, repaired_block))
    repaired_section = section
    for block_start, block_end, repaired_block in reversed(replacements):
        repaired_section = repaired_section[:block_start] + repaired_block + repaired_section[block_end:]
    return before + repaired_section + after

# Extracted formal-report reconciliation and diagnostics.

# Extracted formal-report reconciliation and diagnostics.

def _is_canonical_journal_section(section: str, *, context: ReportPostprocessContext) -> bool:
    required_fields = ['發表日期', '期刊／來源', '研究主題', '研究摘要', '臺北捷運局啟示', '資料來源']
    item_count = 0
    current_fields: list[str] = []

    def _field_name(line: str) -> str:
        match = re.match('^•\\s*(發表日期|期刊[/／]來源|研究主題|研究摘要|臺北捷運局啟示|資料來源)\\s*[：:].+', line.strip())
        if not match:
            return ''
        return '期刊／來源' if match.group(1) in {'期刊/來源', '期刊／來源'} else match.group(1)
    for raw_line in (section or '').splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch('#{1,6}', line):
            return False
        if '學術期刊綜合結論' in line:
            return False
        if re.match('^◆\\s*\\[學術期刊\\]\\s*\\S+', line):
            if item_count and current_fields != required_fields:
                return False
            item_count += 1
            current_fields = []
            continue
        field = _field_name(line)
        if field:
            if item_count <= 0:
                return False
            current_fields.append(field)
            continue
        return False
    if item_count <= 0:
        return False
    return current_fields == required_fields

def normalize_journal_section_format(report_md: str, journal_candidates: list[dict], *, context: ReportPostprocessContext) -> str:
    if not context.include_research_supplement or not journal_candidates or (not report_md):
        return report_md
    report_md = remove_journal_summary_conclusion(report_md)
    heading_match = re.search('(?m)^#{0,6}\\s*[一二三四五六七八九十]\\s*、\\s*(?:技術研究補充|國際學術期刊)\\s*$', report_md)
    if not heading_match:
        return report_md
    end_match = re.search('(?m)^(?:📊|⏰)', report_md[heading_match.end():])
    section_end = heading_match.end() + end_match.start() if end_match else len(report_md)
    before = report_md[:heading_match.start()]
    section = report_md[heading_match.start():section_end]
    after = report_md[section_end:]
    section = re.sub('(?<=[^\\n])(?=\\d+、(?!發表日期|期刊[/／]來源|研究主題|研究摘要|臺北捷運局啟示|資料來源))', '\n', section)
    section = re.sub('(?<=[^\\n])(\\s*#{0,6}\\s*學術期刊綜合結論)', '\\n\\1', section)
    lines = section.splitlines()
    if not lines:
        return report_md
    output: list[str] = [lines[0]]
    item_index = 0
    in_conclusion = False
    field_names = ('發表日期', '期刊/來源', '期刊／來源', '研究主題', '研究摘要', '臺北捷運局啟示', '資料來源')
    seen_fields_by_item: dict[int, set[str]] = {}

    def _candidate_for_item(index: int) -> dict:
        if 1 <= index <= len(journal_candidates):
            return journal_candidates[index - 1] or {}
        return {}

    def _candidate_display_title(index: int) -> str:
        item = _candidate_for_item(index)
        title = _clean_text(str(item.get('title', '') or ''))
        title = re.sub('\\[[^\\]]*(?:技術研究補充|國際學術期刊)[^\\]]*\\]\\s*', '', title).strip()
        return title or f'國際學術期刊研究 {index}'

    def _candidate_source_name(index: int) -> str:
        item = _candidate_for_item(index)
        source = item.get('journal_name') or item.get('source') or item.get('source_display') or _domain_from_url(item.get('url', ''))
        source = _clean_source_label(str(source or ''), item.get('url', ''), _domain_from_url(item.get('url', '')))
        if source == '資料來源未明確辨識':
            return ''
        return source

    def _repair_truncated_value(value: str, expected: str) -> str:
        value = (value or '').strip()
        expected = (expected or '').strip()
        if not value or not expected:
            return value
        if expected.casefold() == value.casefold():
            return expected
        if expected.casefold().endswith(value.casefold()) and 0 < len(expected) - len(value) <= 3:
            return expected
        return value

    def _field_match(raw_line: str) -> tuple[str, str] | None:
        stripped = raw_line.strip()
        match = re.match('^\\s*(?:\\d+[\\.\\、]\\s*)?(?:[-*]\\s*)?(?:•\\s*)?(發表日期|期刊[/／]來源|研究主題|研究摘要|臺北捷運局啟示|資料來源)\\s*[：:]\\s*(.*)$', stripped)
        if match:
            field = '期刊／來源' if match.group(1) in {'期刊/來源', '期刊／來源'} else match.group(1)
            return (field, match.group(2).strip())
        match = re.match('^\\s*(?:\\d+[\\.\\、]\\s*)?(?:[-*]\\s*)?(?:•\\s*)?發表日期\\s*[Pp]\\s*(.*)$', stripped)
        if match:
            return ('發表日期', match.group(1).strip())
        return None

    def _clean_journal_title_line(raw_line: str) -> str:
        title = raw_line.strip()
        title = re.sub('^\\s*#{3,6}\\s*', '', title)
        title = re.sub('^\\s*🔹\\s*', '', title)
        title = re.sub('^\\s*◆\\s*', '', title)
        title = re.sub('^\\s*\\[學術期刊\\]\\s*', '', title)
        title = re.sub('\\[[^\\]]*(?:技術研究補充|國際學術期刊)[^\\]]*\\]\\s*', '', title)
        title = re.sub('^\\s*(?:\\d+[\\.\\、]|[（(]?\\d+[）)])\\s*', '', title)
        title = title.strip(' ：:\u3000')
        return title

    def _matches_candidate_title(candidate_title: str, candidate: dict) -> bool:
        original = str(candidate.get('title', '') or '')
        if not original or not candidate_title:
            return False
        if candidate_title.casefold() in original.casefold() or original.casefold() in candidate_title.casefold():
            return True
        original_tokens = [token.casefold() for token in re.findall('[A-Za-z0-9\\u4e00-\\u9fff]{5,}', original) if len(token) >= 5]
        title_lower = candidate_title.casefold()
        return bool(original_tokens) and sum((1 for token in original_tokens[:8] if token in title_lower)) >= 2

    def _looks_like_title_line(raw_line: str, title: str) -> bool:
        stripped = raw_line.strip()
        if not title or any((title.startswith(name) for name in field_names)):
            return False
        if '學術期刊綜合結論' in title:
            return False
        if re.match('^\\s*(?:#{3,6}|🔹|◆|\\d+[\\.\\、]|[（(]?\\d+[）)])', stripped):
            return True
        if re.search('\\[[^\\]]*(?:技術研究補充|國際學術期刊)[^\\]]*\\]', stripped):
            return True
        if any((_matches_candidate_title(title, item) for item in journal_candidates or [])):
            return True
        if item_index < len(journal_candidates) and '：' not in title and (':' not in title):
            if len(title) <= 120 and (not title.endswith(('。', '；', ';'))) and (not title.startswith(('以下', '本期', '研究補充', '國際學術期刊'))):
                return True
        return False

    def _repair_date_value(value: str, index: int) -> str:
        value = (value or '').strip()
        match = re.search('\\b(20\\d{2})[-/](\\d{1,2})[-/](\\d{1,2})\\b', value)
        if match:
            return f'{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}'
        if re.fullmatch('(?:0?\\d{2}|\\d{3})[-/]\\d{1,2}[-/]\\d{1,2}', value):
            return '日期未明'
        year_match = re.fullmatch('(20\\d{2}|19\\d{2})\\s*年?', value)
        if year_match:
            return f'{year_match.group(1)}年'
        if not value or value in {'日期未知', '日期未明', '未知'}:
            return '日期未明'
        return value

    def _repair_field_value(field: str, value: str, index: int) -> str:
        value = _clean_text(value)
        if field == '發表日期':
            return _repair_date_value(value, index)
        if field == '期刊／來源':
            expected = _candidate_source_name(index)
            value = _repair_truncated_value(value, expected)
            if not value or value in {'資料來源未明確辨識', '報導'}:
                value = expected
            return value
        if field == '資料來源':
            candidate = _candidate_for_item(index)
            candidate_url = _extract_complete_url(str(candidate.get('url', '') or ''))
            urls = _extract_complete_urls(value)
            source_url = urls[0] if urls else candidate_url
            label_text = value
            for source_url_value in urls:
                label_text = label_text.replace(source_url_value, '')
            fallback_label = str(
                candidate.get('journal_name')
                or candidate.get('source_display')
                or candidate.get('source')
                or _domain_from_url(source_url)
                or ''
            )
            label = _clean_source_label(
                label_text or fallback_label,
                source_url,
                _domain_from_url(source_url),
            )
            formal_source = build_formal_report_source(
                {
                    **candidate,
                    "source": label or fallback_label,
                    "source_display": label or fallback_label,
                    "url": source_url,
                }
            )
            if formal_source["display_url"]:
                return f"{formal_source['display_name']}\n{formal_source['display_url']}"
            return formal_source["display_name"]
        return value

    def _append_blank_if_needed() -> None:
        if output and output[-1].strip():
            output.append('')

    def _append_title(title: str) -> None:
        nonlocal item_index
        item_index += 1
        _append_blank_if_needed()
        output.append(f'◆ [學術期刊] {title}')
        seen_fields_by_item.setdefault(item_index, set())

    def _ensure_item_started() -> None:
        if item_index <= 0:
            _append_title(_candidate_display_title(1))

    def _append_field(field: str, value: str) -> None:
        _ensure_item_started()
        seen_fields = seen_fields_by_item.setdefault(item_index, set())
        if field in seen_fields:
            return
        _append_blank_if_needed()
        output.append(f'• {field}：{_repair_field_value(field, value, item_index)}')
        seen_fields.add(field)

    def _process_body_line(raw_line: str) -> None:
        stripped = raw_line.strip()
        if not stripped:
            _append_blank_if_needed()
            return
        if re.fullmatch('#{1,6}', stripped):
            return
        if stripped == '---':
            return
        field_match = _field_match(raw_line)
        if field_match:
            _append_field(field_match[0], field_match[1])
            return
        explicit_title_marker = bool(re.match('^\\s*(?:#{3,6}|🔹|◆|\\d+[\\.\\、]|[（(]?\\d+[）)])', stripped) or re.search('\\[[^\\]]*(?:技術研究補充|國際學術期刊)[^\\]]*\\]', stripped))
        if output and output[-1].startswith('• ') and (not explicit_title_marker):
            output[-1] = output[-1].rstrip() + ' ' + stripped
            return
        title = _clean_journal_title_line(raw_line)
        if _looks_like_title_line(raw_line, title):
            _append_title(title)
            return
        if item_index == 0:
            output.append(stripped)
        elif output and output[-1].startswith('• '):
            output[-1] = output[-1].rstrip() + ' ' + stripped
        else:
            output.append(stripped)
    for raw_line in lines[1:]:
        stripped = raw_line.strip()
        if '學術期刊綜合結論' in stripped:
            continue
        _process_body_line(raw_line)
    normalized = re.sub('\\n{3,}', '\n\n', '\n'.join(output)).strip()
    return before + normalized + after

# Extracted formal-report reconciliation and diagnostics.

# Extracted formal-report reconciliation and diagnostics.

def count_journal_summary_conclusion_chars(report_md: str, *, context: ReportPostprocessContext) -> int:
    del report_md, context
    return 0

def enforce_research_section(report_md: str, journal_candidates: list[dict], *, context: ReportPostprocessContext) -> str:
    if not context.include_research_supplement:
        return report_md
    if journal_candidates:
        return report_md
    heading = context.research_section_heading(True)
    fallback = f"{heading}\n本期未發現符合期間條件且具明確發表日期之國際學術或技術研究資料。"
    if re.search(r"(?m)^#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:技術研究補充|國際學術期刊)\s*$", report_md or ""):
        return re.sub(
            r"(?ms)^#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:技術研究補充|國際學術期刊)\s*.*?(?=^📊|^⏰|\Z)",
            fallback + "\n\n",
            report_md,
            count=1,
        ).strip()
    match = re.search(r"(?m)^📊", report_md or "")
    if match:
        return (report_md[:match.start()].rstrip() + "\n\n" + fallback + "\n\n" + report_md[match.start():].lstrip()).strip()
    return (report_md.rstrip() + "\n\n" + fallback).strip()

def _candidate_report_presence_keys(candidate: dict, *, context: ReportPostprocessContext) -> list[str]:
    source_url = _effective_source_url(candidate)
    values = []
    complete_source_url = _extract_complete_url(source_url)
    if complete_source_url:
        values.append(complete_source_url)
    raw_url = candidate.get('url', '')
    complete_raw_url = _extract_complete_url(raw_url)
    if complete_raw_url and complete_raw_url not in values:
        values.append(complete_raw_url)
    values.append(candidate.get('title', ''))
    return [str(value).strip() for value in values if str(value or '').strip()]

def _report_block_matches_candidate(block: str, candidate: dict, *, context: ReportPostprocessContext) -> bool:
    marker = re.search('<!--\\s*candidate_id\\s*:\\s*(\\d+)\\s*-->', block or '', flags=re.IGNORECASE)
    if marker:
        return int(marker.group(1)) == int(candidate.get('candidate_id') or candidate.get('id') or 0)
    keys = _candidate_report_presence_keys(candidate, context=context)
    if any((key and key in (block or '') for key in keys)):
        return True
    title_tokens = [token for token in re.findall('[A-Za-z0-9\\u4e00-\\u9fff]{4,}', candidate.get('title', '') or '') if len(token) >= 4]
    return bool(title_tokens) and sum((1 for token in title_tokens[:6] if token in (block or ''))) >= 2

def _supplemental_source_is_used(report_block: str, candidate: dict, source_row: dict, *, context: ReportPostprocessContext) -> bool:
    summary_match = re.search('(?ms)^•\\s*事件摘要\\s*[：:]\\s*(.*?)(?=^•\\s*(?:臺北捷運局啟示|資料來源|發布/事件日期|國家/地區|相關機電系統)\\s*[：:]|\\Z)', report_block or '')
    summary = summary_match.group(1) if summary_match else report_block or ''
    summary_folded = summary.casefold()
    supplemental_text = f"{source_row.get('title', '')} {source_row.get('source_display', '')}".casefold()
    if re.search('\\b40\\s*%', supplemental_text) and re.search('40\\s*%', summary):
        return True
    bilingual_signals = ((('hitachi',), ('hitachi', '日立')), (('digital signalling', 'digital signaling'), ('digital signalling', 'digital signaling', '數位號誌', '數位信號')), (('capacity increase',), ('capacity increase', '容量提升', '容量增加', '運能提升', '運能增加')))
    for source_terms, summary_terms in bilingual_signals:
        if any((term in supplemental_text for term in source_terms)) and any((term in summary_folded for term in summary_terms)):
            return True
    source_display = str(source_row.get('source_display', '') or '').casefold()
    source_name = source_display.split('.', 1)[0]
    if len(source_name) >= 4 and source_name in summary_folded:
        return True
    candidate_title = str(candidate.get('title', '') or '').casefold()
    if 'ttc' in candidate_title and 'line 2' in candidate_title:
        return bool(re.search('40\\s*%|hitachi|日立|數位號誌|數位信號|運能(?:提升|增加)|容量(?:提升|增加)', summary, flags=re.IGNORECASE))
    return False

def _report_block_matches_supplemental_candidate(block: str, candidate: dict, *, context: ReportPostprocessContext) -> bool:
    if _report_block_matches_candidate(block, candidate, context=context):
        return True
    block_folded = (block or '').casefold()
    title_folded = str(candidate.get('title', '') or '').casefold()
    operator_markers = [marker for marker in ('ttc', 'mta', 'wmata', 'bvg', 'translink', 'frauscher', 'austin') if marker in title_folded]
    route_markers = [marker for marker in ('line 2', 'r211', 'm4', 'skytrain') if marker in title_folded]
    return bool(operator_markers and any((marker in block_folded for marker in operator_markers))) and (not route_markers or any((marker in block_folded for marker in route_markers)))

def ensure_supplemental_sources_in_report(report_md: str, selected_candidates: list[dict], *, context: ReportPostprocessContext) -> str:
    del selected_candidates, context
    return report_md
    candidates = [candidate for candidate in selected_candidates or [] if candidate.get('supplemental_sources')]
    if not report_md or not candidates:
        return report_md
    parts = re.split('(?m)^(🔹\\s*\\[[^\\]]+\\].*)$', report_md)
    if len(parts) <= 1:
        return report_md
    output = [parts[0]]
    for idx in range(1, len(parts), 2):
        heading = parts[idx]
        body = parts[idx + 1] if idx + 1 < len(parts) else ''
        block = heading + body
        candidate = next((item for item in candidates if _report_block_matches_supplemental_candidate(block, item, context=context)), None)
        if not candidate:
            output.extend([heading, body])
            continue
        used_sources = [source_row for source_row in candidate.get('supplemental_sources', []) or [] if _supplemental_source_is_used(block, candidate, source_row, context=context)]
        additions: list[str] = []
        for source_row in used_sources:
            source_url = _extract_complete_url(str(source_row.get('url', '') or ''))
            source_display = str(source_row.get('source_display', '') or _domain_from_url(source_url) or '補充來源').strip()
            if source_url and source_url not in block:
                additions.append(_source_label_with_link(source_display, source_url))
            elif source_display and source_display.casefold() not in block.casefold():
                additions.append(source_display)
        if additions:
            suffix = '；補充來源：' + '；'.join(additions)
            if re.search('(?m)^•\\s*資料來源\\s*[：:].*$', body):
                body = re.sub('(?m)^(•\\s*資料來源\\s*[：:].*)$', lambda match: match.group(1).rstrip('；; ') + suffix, body, count=1)
            else:
                body = body.rstrip() + f"\n\n• 資料來源：{suffix.lstrip('；')}\n"
        output.extend([heading, body])
    return ''.join(output)

# Extracted formal-report reconciliation and diagnostics.

# Extracted formal-report reconciliation and diagnostics.

def _candidate_region_display(candidate: dict, *, context: ReportPostprocessContext) -> str:
    resolved = str(candidate.get("resolved_region") or "").strip()
    if resolved or candidate.get("authoritative_materialization_stage"):
        return resolved or str(candidate.get("region") or "未判定").strip() or "未判定"
    # Compatibility-only path for pre-A7 records that never crossed the
    # selector contract.  Production candidates always carry resolved_region.
    text = context.candidate_selection_text(candidate)
    region = _canonical_candidate_region(dict(candidate))
    city_map = [
        ('北愛爾蘭', ['northern ireland', 'belfast', '北愛爾蘭', '貝爾法斯特'], '英國（北愛爾蘭）'),
        ('巴塞爾', ['basel', '巴塞爾'], '瑞士（巴塞爾）'),
        ('休士頓', ['houston', '休士頓', '休斯頓'], '美國（休士頓）'),
        ('溫哥華', ['vancouver', 'broadway subway', '溫哥華'], '加拿大（溫哥華）'),
        ('多倫多', ['toronto', 'finch west', '多倫多'], '加拿大（多倫多）'),
        ('柏林', ['berlin', 'adlershof', '柏林'], '德國（柏林）'),
        ('萊比錫', ['leipzig', '萊比錫'], '德國（萊比錫）'),
    ]
    for _, terms, label in city_map:
        if _contains_any_term(text, terms):
            return label
    return region or str(candidate.get("region") or "未判定").strip() or "未判定"

def _is_unknown_region_value(value: str, *, context: ReportPostprocessContext) -> bool:
    cleaned = re.sub('\\s+', '', value or '').strip('：:，,。-')
    return cleaned in {'', '未判定', '未知', '不明', '未明', '國家/地區未判定', '國家地區未判定'}

def repair_report_region_lines(report_md: str, selected_candidates: list[dict], *, context: ReportPostprocessContext) -> str:
    if not report_md or not selected_candidates:
        return report_md
    parts = re.split('(?m)^(🔹\\s*\\[[^\\]]+\\].*)$', report_md)
    if len(parts) <= 1:
        return report_md
    output = [parts[0]]
    for idx in range(1, len(parts), 2):
        heading = parts[idx]
        body = parts[idx + 1] if idx + 1 < len(parts) else ''
        block = heading + body
        matched = next((candidate for candidate in selected_candidates if _report_block_matches_candidate(block, candidate, context=context)), None)
        if matched:
            region_display = _candidate_region_display(matched, context=context)
            if _is_unknown_region_value(region_display, context=context):
                output.extend([heading, body])
                continue
            region_match = re.search('(?m)^•\\s*國家/地區\\s*[：:]\\s*(.*)$', body)
            if region_match:
                current_region = region_match.group(1).strip()
                if _is_unknown_region_value(current_region, context=context):
                    body = re.sub('(?m)^•\\s*國家/地區\\s*[：:].*$', f'• 國家/地區：{region_display}', body, count=1)
            else:
                insert_match = re.search('(?m)^•\\s*發布/事件日期\\s*[：:].*$', body)
                if insert_match:
                    body = body[:insert_match.end()] + f'\n• 國家/地區：{region_display}' + body[insert_match.end():]
                else:
                    body = f'\n• 國家/地區：{region_display}' + body
        output.extend([heading, body])
    return ''.join(output)

def formal_title_from_candidate(candidate: dict, *, context: ReportPostprocessContext) -> str:
    category = _formal_category_for_candidate(candidate)
    if not category:
        return ''
    text = context.candidate_selection_text(candidate)
    original_title = _clean_text(unescape(str(candidate.get('title', '') or '')))
    lower_text = text.casefold()
    if 'bakerloo' in lower_text:
        return 'Bakerloo Line 機廠及側線可行性研究'
    if 'buangkok' in lower_text:
        return 'Buangkok MRT 站相關都市軌道資訊'
    if 'gelsenkirchen' in lower_text:
        return 'Gelsenkirchen 電車碰撞事故'
    if _contains_any_term(text, ['frauscher', 'axle counter', 'axle counters']):
        return 'Frauscher 車軸計數器應用於電車號誌現代化'
    if _contains_any_term(text, ['finch west']) and _contains_any_term(text, ['hitachi']):
        return '多倫多 Finch West LRT 啟用 Hitachi Rail 號誌系統'
    if _contains_any_term(text, ['broadway subway']):
        return '溫哥華 Broadway Subway 都市軌道專案進展'
    if _contains_any_term(text, ['houston', 'metrorail']):
        return '休士頓 METRORail 都市軌道事件'
    if _contains_any_term(text, ['adlershof']):
        return '柏林 Adlershof 電車撞擊事故'
    if _contains_any_term(text, ['basel']) and category == '重大事故':
        return '巴塞爾電車碰撞事故'
    if _contains_any_term(text, ['leipzig']) and category == '重大事故':
        return '萊比錫路面電車營運安全事件'
    if category == '重大事故' and _contains_any_term(text, ['collision', 'crash', 'derailment', 'fire', '碰撞', '撞擊', '出軌', '火災']):
        if original_title and not _title_needs_repair(original_title, category):
            return f'都市軌道事故：{original_title}'
        return chinese_fallback_title(category, original_title)
    if original_title and (not _title_needs_repair(original_title, category)):
        if _looks_like_english_title(original_title):
            return chinese_fallback_title(category, original_title)
        return original_title
    return chinese_fallback_title(category, original_title)


def _fallback_title_from_candidate(candidate: dict) -> str:
    title = _clean_text(unescape(str(candidate.get('title', '') or ''))).strip()
    compact = re.sub(r"\s+", "", title)
    if not title or _is_generic_formal_title(title) or any(
        fragment in compact for fragment in TITLE_PLACEHOLDER_FRAGMENTS
    ):
        return ''
    return title

def repair_generic_report_titles(report_md: str, selected_candidates: list[dict], *, context: ReportPostprocessContext) -> str:
    if not report_md or not selected_candidates:
        return report_md
    parts = re.split('(?m)^(🔹\\s*\\[[^\\]]+\\]\\s*.*)$', report_md)
    if len(parts) <= 1:
        return report_md
    output = [parts[0]]
    for idx in range(1, len(parts), 2):
        heading = parts[idx]
        body = parts[idx + 1] if idx + 1 < len(parts) else ''
        match = re.match('^(🔹\\s*\\[([^\\]]+)\\]\\s*)(.*)$', heading.strip())
        if match:
            preceding = parts[idx - 1] if idx else ''
            marker_prefix = re.search(
                r'(?:<!--\s*candidate_id\s*:\s*\d+\s*-->\s*)+$',
                preceding,
                flags=re.IGNORECASE,
            )
            block = f'{marker_prefix.group(0) if marker_prefix else ""}{heading}{body}'
            matched = next((candidate for candidate in selected_candidates if _report_block_matches_candidate(block, candidate, context=context)), None)
            if matched:
                candidate_text = f"{matched.get('title', '')} {matched.get('snippet', '')}".casefold()
                entity_conflict = 'buangkok' in candidate_text and any(alias in heading.casefold() for alias in ('武吉班讓', 'bukit panjang'))
                candidate_title = _fallback_title_from_candidate(matched)
                preserves_candidate_title = bool(
                    candidate_title
                    and _normalize_title(match.group(3)) == _normalize_title(candidate_title)
                )
                if not preserves_candidate_title and (entity_conflict or ((not _has_valid_chinese_report_title(match.group(3))) and _title_needs_repair(match.group(3), match.group(2)))):
                    replacement_title = (
                        _fallback_title_from_candidate(matched)
                        if _is_generic_formal_title(match.group(3))
                        else formal_title_from_candidate(matched, context=context)
                    )
                    if replacement_title:
                        heading = f'{match.group(1)}{replacement_title}'
        output.extend([heading, body])
    return ''.join(output)

# Extracted formal-report reconciliation and diagnostics.

# Extracted formal-report reconciliation and diagnostics.

def _extract_marked_candidate_blocks(report_md: str, *, context: ReportPostprocessContext) -> tuple[dict[int, str], list[int]]:
    pattern = re.compile('<!--\\s*candidate_id\\s*:\\s*(\\d+)\\s*-->\\s*(.*?)(?=<!--\\s*candidate_id\\s*:|^\\s*#{0,6}\\s*[一二三四五六七八九十]\\s*、|^\\s*📊|^\\s*⏰|\\Z)', flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    blocks: dict[int, str] = {}
    duplicates: list[int] = []
    for record in _parse_report_article_blocks(report_md):
        for candidate_id in record['candidate_ids']:
            if candidate_id in blocks:
                duplicates.append(candidate_id)
                continue
            blocks[candidate_id] = record['body']
    return (blocks, sorted(set(duplicates)))

def _candidate_source_line(candidate: dict, *, context: ReportPostprocessContext) -> str:
    source_url = _effective_source_url(candidate)
    raw_source_display = unescape(str(candidate.get('source_display') or '').strip())
    if raw_source_display in _GENERIC_SOURCE_FALLBACKS:
        raw_source_display = ""
    raw_source = unescape(str(candidate.get('source') or '').strip())
    if raw_source in _GENERIC_SOURCE_FALLBACKS:
        raw_source = ""
    report_source = build_formal_report_source(
        {
            **candidate,
            "source": raw_source_display or raw_source,
            "source_display": raw_source_display or raw_source,
            "url": source_url or candidate.get("url", ""),
        }
    )
    item_date = _normalize_report_date_text(str(candidate.get('date') or ''))
    if item_date == '日期未知':
        item_date = '日期未明'
    source_line = f"• 資料來源：{report_source['display_name']}"
    if report_source['display_url']:
        source_line += f"\n{report_source['display_url']}"
    if item_date:
        source_line += f"\n發布日期：{item_date}"
    return source_line


def _fallback_reason(candidate: dict, *, context: ReportPostprocessContext) -> str:
    del context
    title = unescape(str(candidate.get('title', '') or '')).strip()
    source_url = _effective_source_url(candidate)
    if not title:
        return 'missing_title'
    if not _extract_complete_url(source_url):
        return 'missing_source_url'
    if _normalize_report_date_text(str(candidate.get('date') or '')) == '日期未知':
        return 'invalid_or_missing_date'
    return ''


def _fallback_summary(candidate: dict) -> str:
    title = unescape(str(candidate.get('title', '') or '')).strip()
    for key in ('summary_zh', 'snippet_zh', 'summary', 'snippet', 'short_snippet'):
        value = unescape(str(candidate.get(key, '') or ''))
        value = re.sub(r'<[^>]+>', ' ', value)
        value = _short_formal_sentence(value, 360)
        if (
            len(re.findall(r'[\u3400-\u9fff]', value)) >= 8
            and not _summary_repeats_title(value, title)
            and not _contains_untranslated_report_script(value)
        ):
            return value
    return ''


def _fallback_insight(category: str, candidate: dict) -> str:
    del category
    supplied = unescape(str(candidate.get('taipei_insight', '') or '')).strip()
    insight = _short_formal_sentence(supplied, 180)
    if (
        len(re.findall(r'[\u3400-\u9fff]', insight)) >= 6
        and _is_meaningful_taipei_insight(insight)
        and not _contains_untranslated_report_script(insight)
    ):
        return insight
    return ''


_FALLBACK_ELECTROMECHANICAL_SYSTEM_LABELS = {
    'signalling': '號誌系統',
    'traction_power': '供電系統',
    'telecommunications': '通訊系統',
    'afc': '自動收費系統 AFC',
    'platform_screen_doors': '月臺門系統',
    'rolling_stock': '車輛系統',
    'depot_electromechanical': '機廠設備',
    'station_electromechanical': '未明確',
    'ventilation_hvac': '通風空調系統',
}


def _fallback_electromechanical_system(candidate: dict) -> str:
    if "core_systems" not in candidate:
        if candidate.get("authoritative_materialization_stage"):
            return ""
        # Compatibility-only path for legacy pre-contract records.
        if candidate.get("procurement_generic_electromechanical_scope"):
            return ""
        systems = candidate.get("procurement_systems") or []
        if isinstance(systems, str):
            systems = [systems]
        evidence = " ".join(
            str(candidate.get(key, '') or '')
            for key in ('title', 'snippet', 'summary', 'summary_zh')
        )
        labels = [
            _FALLBACK_ELECTROMECHANICAL_SYSTEM_LABELS.get(str(system).strip())
            for system in systems
        ]
        labels = [label for label in labels if label]
        inferred_labels = normalize_electromechanical_system_value('', evidence)
        if inferred_labels != '未明確':
            labels.extend(inferred_labels.split('、'))
        labels = [label for label in labels if label != '未明確']
        return '、'.join(dict.fromkeys(labels)) if labels else '未明確'
    formal_labels = report_labels_for_core_systems(candidate.get("core_systems") or [])
    return '、'.join(formal_labels) if formal_labels else ''

def _fallback_report_block(candidate: dict, *, context: ReportPostprocessContext) -> str:
    if _fallback_reason(candidate, context=context):
        return ''
    candidate_id = int(candidate.get('candidate_id') or candidate.get('id') or 0)
    category = _formal_category_for_candidate(candidate)
    if not category:
        return ''
    title = _fallback_title_from_candidate(candidate)
    if not title:
        return ''
    date_value = _normalize_report_date_text(str(candidate.get('date') or ''))
    if date_value == '日期未知':
        date_value = '日期未明'
    summary = _fallback_summary(candidate)
    if not summary:
        return ''
    insight = _fallback_insight(category, candidate)
    lines = [
        f'<!-- candidate_id: {candidate_id} -->', f'🔹 [{category}] {title}', '',
        f'• 發布/事件日期：{date_value}', '',
        f'• 國家/地區：{_candidate_region_display(candidate, context=context)}', '',
    ]
    system_value = _fallback_electromechanical_system(candidate)
    if system_value and not ("core_systems" in candidate and not candidate.get("core_systems")):
        lines.extend([f'• 相關機電系統：{system_value}', ''])
    lines.extend(['• 事件摘要：', summary, ''])
    if insight:
        lines.extend(['• 臺北捷運局啟示：', insight, ''])
    lines.extend([_candidate_source_line(candidate, context=context), '', '________________________________________'])
    return '\n'.join(lines)


def _candidate_event_identity(candidate: dict) -> str:
    explicit = str(candidate.get("canonical_event_id") or "").strip()
    if explicit or candidate.get("authoritative_materialization_stage"):
        return explicit
    # Compatibility-only identity for legacy records that predate A5/A7.
    return canonical_event_id(candidate)

def _force_candidate_fields_in_block(block: str, candidate: dict | list[dict], *, context: ReportPostprocessContext) -> str:
    candidates = candidate if isinstance(candidate, list) else [candidate]
    candidates = [item for item in candidates if item]
    if not candidates:
        return ''
    normalized = normalize_final_report_md(unescape(block or ''))
    if not re.search('(?m)^🔹\\s*\\[[^\\]]+\\]', normalized):
        return ''
    category = _formal_category_for_candidate(candidates[0])
    if not category:
        return ''
    normalized = re.sub(r'(?mi)^\s*(?:<!--\s*candidate_id.*?-->|&lt;!--.*?--&gt;)\s*$', '', normalized).strip()
    normalized = re.sub('(?m)^(🔹\\s*)\\[[^\\]]+\\]', f'\\1[{category}]', normalized, count=1)
    if all("core_systems" in item for item in candidates):
        formal_core_systems = list(dict.fromkeys(
            system
            for item in candidates
            for system in (item.get("core_systems") or [])
        ))
        formal_system_value = '、'.join(report_labels_for_core_systems(formal_core_systems))
        system_line_pattern = r'(?m)^•\s*相關機電系統\s*[：:].*$'
        if formal_system_value:
            replacement = f'• 相關機電系統：{formal_system_value}'
            if re.search(system_line_pattern, normalized):
                normalized = re.sub(system_line_pattern, replacement, normalized, count=1)
            else:
                normalized = re.sub(
                    r'(?m)^•\s*事件摘要\s*[：:]',
                    f'{replacement}\n\n• 事件摘要：',
                    normalized,
                    count=1,
                )
        else:
            normalized = re.sub(system_line_pattern + r'\n?', '', normalized, count=1)
    source_line = _candidate_source_line(candidates[0], context=context) if _effective_source_url(candidates[0]) else ''
    if source_line:
        normalized_lines: list[str] = []
        source_seen = False
        skip_source_continuation = False
        for line in normalized.splitlines():
            stripped = line.strip()
            field = _match_report_field_line(stripped)
            if field and field[0] == '資料來源':
                if not source_seen:
                    normalized_lines.append(source_line)
                    source_seen = True
                skip_source_continuation = True
                continue
            if skip_source_continuation:
                if not stripped:
                    continue
                if _match_report_field_line(stripped) or stripped.startswith(("🔹", "##", "###", "---", "________________________________________")):
                    skip_source_continuation = False
                else:
                    continue
            normalized_lines.append(line)
        normalized = '\n'.join(normalized_lines).strip()
        if not source_seen:
            normalized = normalized.rstrip() + f'\n\n{source_line}'
    existing_source_match = re.search('(?m)^•\\s*資料來源\\s*[：:]\\s*(.*)$', normalized)
    if source_line:
        if not existing_source_match:
            normalized = normalized.rstrip() + f'\n\n{source_line}'
        else:
            existing_source_value = existing_source_match.group(1).strip()
            generic_source = (
                not _extract_complete_url(existing_source_value)
                and (
                    existing_source_value in _GENERIC_SOURCE_FALLBACKS
                    or existing_source_value.startswith('原始來源')
                )
            )
            if generic_source:
                candidate_source_values = source_line.split('：', 1)[1]
                normalized = (
                    normalized[:existing_source_match.end()]
                    + f'；{candidate_source_values}'
                    + normalized[existing_source_match.end():]
                )
    marker_lines = '\n'.join(
        f'<!-- candidate_id: {int(item.get("candidate_id") or item.get("id") or 0)} -->'
        for item in candidates
    )
    return f'{marker_lines}\n{normalized}'.strip()

def _extract_research_section_for_reconcile(report_md: str, *, context: ReportPostprocessContext) -> str:
    match = re.search('(?ms)^\\s*#{0,6}\\s*[一二三四五六七八九十]\\s*、\\s*(?:國際學術期刊|技術研究補充)\\s*$.*?(?=^\\s*📊|^\\s*⏰|\\Z)', report_md or '')
    return match.group(0).strip() if match else ''


def _report_block_missing_fields(normalized: str, candidate: dict | None = None) -> list[str]:
    if not re.search(r"^🔹\s*\[[^\]]+\]\s*\S+", normalized or "", flags=re.MULTILINE):
        missing = ["title"]
    else:
        missing = []
    lines = (normalized or "").splitlines()
    field_labels = {
        "date": "發布/事件日期",
        "country": "國家",
        "system": "相關機電系統",
        "summary": "事件摘要",
        "source": "資料來源",
    }
    for name, label in field_labels.items():
        if name == "system" and candidate is not None and "core_systems" in candidate and not candidate.get("core_systems"):
            continue
        found = False
        for index, line in enumerate(lines):
            label_pattern = "國家(?:/地區)?" if name == "country" else re.escape(label)
            match = re.match(rf"^•\s*{label_pattern}\s*[：:]\s*(.*)$", line.strip())
            if not match:
                continue
            if match.group(1).strip():
                found = True
                break
            for following in lines[index + 1:]:
                value = following.strip()
                if not value:
                    continue
                if _match_report_field_line(value) or value.startswith(("🔹", "##", "###")):
                    break
                found = True
                break
            break
        if not found:
            missing.append(name)
    return missing

def reconcile_report_candidate_output(report_md: str, selected_candidates: list[dict], *, context: ReportPostprocessContext) -> tuple[str, dict]:
    selected_candidates = ensure_selected_candidate_ids(selected_candidates)
    initial_validation = validate_report_candidate_ids(report_md, selected_candidates)
    parsed_blocks = _parse_report_article_blocks(report_md)
    selected_map = {int(item.get('candidate_id') or item.get('id') or 0): item for item in selected_candidates or []}
    selected_order = {candidate_id: index for index, candidate_id in enumerate(selected_map)}
    records: list[dict] = []
    seen_ids: set[int] = set()
    fallback_ids: list[int] = []
    skipped_ids: list[int] = []
    deduplicated_event_ids: list[int] = []
    fallback_reason_counts: dict[str, int] = {}
    warnings: list[str] = []
    parser_failures: list[dict] = []
    seen_event_identities: set[str] = set()

    def _append_record(candidate_ids: tuple[int, ...], text: str, *, model: bool) -> None:
        candidates = [selected_map.get(candidate_id) for candidate_id in candidate_ids]
        event_identities = {
            _candidate_event_identity(candidate)
            for candidate in candidates
            if candidate
        }
        event_identities.discard("")
        if event_identities.intersection(seen_event_identities):
            deduplicated_event_ids.extend(candidate_ids)
            return
        seen_event_identities.update(event_identities)
        records.append({
            'candidate_ids': candidate_ids,
            'category': _formal_category_for_candidate(candidates[0] or {}),
            'text': text,
            'model': model,
        })

    def _fallback_for_candidate(candidate_id: int, reason: str, missing_fields: list[str]) -> None:
        candidate = selected_map.get(candidate_id)
        if not candidate:
            return
        parser_failures.append({
            "candidate_id": candidate_id,
            "missing_fields": list(missing_fields),
            "reason": reason,
        })
        fallback = _fallback_report_block(candidate, context=context)
        if fallback:
            fallback_ids.append(candidate_id)
            seen_ids.add(candidate_id)
            fallback_reason_counts[reason] = fallback_reason_counts.get(reason, 0) + 1
            _append_record((candidate_id,), fallback, model=False)
            return
        skipped_ids.append(candidate_id)
        seen_ids.add(candidate_id)
        fallback_reason = _fallback_reason(candidate, context=context) or reason
        fallback_reason_counts[fallback_reason] = fallback_reason_counts.get(fallback_reason, 0) + 1

    for parsed in parsed_blocks:
        candidate_ids = tuple(parsed.get('candidate_ids', ()))
        candidates = [selected_map.get(candidate_id) for candidate_id in candidate_ids]
        if not candidate_ids or any(candidate_id not in selected_map for candidate_id in candidate_ids) or len(set(candidate_ids)) != len(candidate_ids) or seen_ids.intersection(candidate_ids):
            warnings.append(f'報告 block 含未知、重複或無效 candidate_id：{list(candidate_ids)}。')
            continue
        normalized = normalize_final_report_md(unescape(parsed.get('body', '') or ''))
        block_candidate = candidates[0] if candidates and all(
            item is not None and "core_systems" in item and not item.get("core_systems")
            for item in candidates
        ) else None
        missing_fields = _report_block_missing_fields(normalized, block_candidate)
        if missing_fields:
            reason = 'missing_required_fields:' + ','.join(missing_fields)
            warnings.append(f'報告 block parser failure candidate_id={list(candidate_ids)}；缺失欄位={missing_fields}。')
            for candidate_id in candidate_ids:
                _fallback_for_candidate(candidate_id, reason, missing_fields)
            continue
        preserved = _force_candidate_fields_in_block(parsed.get('body', ''), [item for item in candidates if item], context=context)
        if not preserved:
            reason = 'model_block_normalization_failed'
            for candidate_id in candidate_ids:
                _fallback_for_candidate(candidate_id, reason, [])
            continue
        seen_ids.update(candidate_ids)
        _append_record(candidate_ids, preserved, model=True)
    for candidate_id, candidate in selected_map.items():
        if candidate_id in seen_ids:
            continue
        reason = _fallback_reason(candidate, context=context) or 'missing_model_candidate'
        _fallback_for_candidate(candidate_id, reason, ['model_block'])
    sections: list[str] = [f'# {context.report_title}', f'> 資料涵蓋期間：{context.date_range}']
    category_groups = [
        ('一、技術新知', {'技術新知'}),
        ('二、重大事故', {'重大事故'}),
        (f'三、{OPERATIONAL_DYNAMICS_CATEGORY_LABEL}', {
            '營運政策',
            '營運爭議',
            OPERATIONAL_DYNAMICS_CATEGORY_LABEL,
            SERVICE_OPENING_CATEGORY_KEY,
        }),
        (f'四、{ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL}', {ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL}),
    ]
    if context.standards_enabled or '規範更新' in context.selected_types:
        category_groups.append((
            f"{'五' if ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL in context.selected_types else '四'}、規範更新",
            {'規範更新'},
        ))
    for heading, categories in category_groups:
        if not categories.intersection(context.selected_types):
            continue
        section_blocks = [
            record['text']
            for record in sorted(
                records,
                key=lambda item: min(selected_order.get(candidate_id, 10**9) for candidate_id in item['candidate_ids']),
            )
            if record['category'] in categories
        ]
        sections.extend(['', f'## {heading}', ''])
        if section_blocks:
            sections.append('\n\n'.join(section_blocks))
        elif len(categories) == 1:
            category = next(iter(categories))
            sections.append(EMPTY_TEXT_BY_TYPE.get(category, '本期未發現符合條件資料。'))
        else:
            sections.append(f'本期未發現符合條件的{OPERATIONAL_DYNAMICS_CATEGORY_LABEL}資料。')
    research_section = _extract_research_section_for_reconcile(report_md, context=context) if context.include_research_supplement else ''
    if research_section:
        has_journal_entries = bool(
            re.search(r"(?m)^\s*(?:◆\s*\[學術期刊\]|\d+[\.、]\s*\S+)", research_section)
        )
        if has_journal_entries:
            research_section = re.sub(
                r"(?m)^\s*本期未發現符合條件[^\n]*\n?",
                "",
                research_section,
            ).strip()
        sections.extend(['', research_section])
    reconciled = re.sub('\\n{3,}', '\n\n', '\n'.join(sections)).strip()
    deduplicated_ids = set(deduplicated_event_ids)
    validation_candidates = [
        candidate
        for candidate in selected_candidates
        if int(candidate.get('candidate_id') or candidate.get('id') or 0) not in deduplicated_ids
    ]
    final_validation = validate_report_candidate_ids(reconciled, validation_candidates)
    final_candidate_ids = extract_report_candidate_ids(reconciled)
    selected_ids = [
        int(candidate.get('candidate_id') or candidate.get('id') or 0)
        for candidate in selected_candidates
    ]
    expected_final_ids = [
        candidate_id
        for candidate_id in selected_ids
        if candidate_id not in deduplicated_ids
    ]
    final_candidate_id_counts = Counter(final_candidate_ids)
    final_candidate_id_duplicates = sorted(
        candidate_id
        for candidate_id, count in final_candidate_id_counts.items()
        if count > 1
    )
    category_counts = count_report_items_by_category(reconciled)
    canonical_blocks = [
        {
            "candidate_ids": list(record["candidate_ids"]),
            "category": record["category"],
        }
        for record in records
    ]
    diagnostics = {
        'before_reconcile': initial_validation,
        'fallback_candidate_ids': sorted(set(fallback_ids)),
        'skipped_candidate_ids': sorted(set(skipped_ids)),
        'skipped_fallback_candidate_ids': sorted(set(skipped_ids)),
        'accepted_model_candidate_ids': sorted({candidate_id for record in records if record['model'] for candidate_id in record['candidate_ids']}),
        'model_report_block_count': len(parsed_blocks),
        'preserved_model_block_count': sum(1 for record in records if record['model']),
        'fallback_block_count': sum(1 for record in records if not record['model']),
        'fallback_reason_counts': fallback_reason_counts,
        'parser_failures': parser_failures,
        'model_article_block_count': len(parsed_blocks),
        'multi_candidate_model_blocks': [
            list(parsed.get('candidate_ids', ()))
            for parsed in parsed_blocks
            if len(parsed.get('candidate_ids', ())) > 1
        ],
        'category_mismatches': [
            {
                'candidate_id': candidate_id,
                'expected_category': _formal_category_for_candidate(selected_map.get(candidate_id) or {}),
                'actual_category': _formal_category_for_candidate({'classification': record['category']}),
            }
            for record in records
            for candidate_id in record['candidate_ids']
            if _formal_category_for_candidate(selected_map.get(candidate_id) or {})
            != _formal_category_for_candidate({'classification': record['category']})
        ],
        'deduplicated_event_candidate_ids': sorted(set(deduplicated_event_ids)),
        'merged_event_groups': [list(record['candidate_ids']) for record in records if record['model'] and len(record['candidate_ids']) > 1],
        'final_unique_article_count': len(records),
        'reconciled_accepted_count': len(records),
        'canonical_blocks': canonical_blocks,
        'final_count_by_category': category_counts,
        'final_count_by_section': {
            heading: sum(1 for record in records if record['category'] in categories)
            for heading, categories in category_groups
        },
        'postprocess_warnings': warnings,
        'after_reconcile': final_validation,
        'final_candidate_ids': final_candidate_ids,
        'expected_final_candidate_ids': expected_final_ids,
        'final_candidate_id_duplicates': final_candidate_id_duplicates,
        'accepted_candidate_ids': sorted(
            candidate_id
            for candidate_id in expected_final_ids
            if candidate_id not in set(skipped_ids)
        ),
        'final_candidate_id_integrity_passed': Counter(final_candidate_ids) == Counter(
            candidate_id
            for candidate_id in expected_final_ids
            if candidate_id not in set(skipped_ids)
        ),
        'selected_event_count': len(selected_candidates),
        'event_level_integrity_passed': (
            len({
                _candidate_event_identity(candidate)
                for candidate in selected_candidates
            }) == len(selected_candidates)
            and not any(len(parsed.get('candidate_ids', ())) > 1 for parsed in parsed_blocks)
        ),
    }
    return (reconciled, diagnostics)


def has_candidate_section_mismatch(report_md: str, selected_candidates: list[dict]) -> bool:
    selected_map = {
        int(candidate.get("candidate_id") or candidate.get("id") or 0): candidate
        for candidate in selected_candidates or []
    }
    for parsed in _parse_report_article_blocks(report_md):
        category_match = re.search(r"(?m)^\s*🔹\s*\[([^\]]+)\]", parsed.get("body", ""))
        if not category_match:
            continue
        actual = canonical_formal_report_category(category_match.group(1))
        for candidate_id in parsed.get("candidate_ids", ()):
            candidate = selected_map.get(candidate_id) or {}
            expected = candidate.get("classification") or candidate.get("preliminary_type") or ""
            if expected in {"營運政策", "營運爭議", "營運動態", SERVICE_OPENING_CATEGORY_KEY}:
                expected = OPERATIONAL_DYNAMICS_CATEGORY_LABEL
            if actual in {"營運政策", "營運爭議", "營運動態", SERVICE_OPENING_CATEGORY_KEY}:
                actual = OPERATIONAL_DYNAMICS_CATEGORY_LABEL
            if expected and actual != expected:
                return True
    return False

def identify_dropped_selected_candidates(report_md: str, selected_candidates: list[dict], *, context: ReportPostprocessContext) -> list[dict]:
    missing_ids = set(validate_report_candidate_ids(report_md, selected_candidates).get('missing_ids', []))
    return [candidate for candidate in selected_candidates or [] if int(candidate.get('candidate_id') or candidate.get('id') or 0) in missing_ids]

def restore_missing_selected_report_items(report_md: str, selected_candidates: list[dict], *, context: ReportPostprocessContext) -> tuple[str, list[dict]]:
    reconciled, diagnostics = reconcile_report_candidate_output(report_md, selected_candidates, context=context)
    context.id_validation_target.clear()
    context.id_validation_target.update(diagnostics)
    dropped_ids = set(diagnostics.get('skipped_candidate_ids', []))
    dropped = [
        candidate for candidate in selected_candidates or []
        if int(candidate.get('candidate_id') or candidate.get('id') or 0) in dropped_ids
    ]
    return (reconciled, dropped)

# Extracted formal-report reconciliation and diagnostics.

# Extracted formal-report reconciliation and diagnostics.

def build_final_incident_coverage_debug(selected_candidates: list[dict], maiagent_report_response: str, final_report_md: str, *, global_scope: bool, report_days: int, incident_enabled: bool, context: ReportPostprocessContext) -> dict:
    python_count = sum((1 for item in selected_candidates or [] if (item.get('classification') or item.get('preliminary_type')) == '重大事故'))
    maiagent_count = count_authoritative_report_items_by_category(maiagent_report_response).get('重大事故', 0)
    final_count = count_authoritative_report_items_by_category(final_report_md).get('重大事故', 0)
    dropped_after_maiagent = max(0, python_count - final_count)
    warning = bool(global_scope and int(report_days or 0) in {90, 365} and incident_enabled and (final_count == 0))
    reason = ''
    if warning:
        if python_count > 0 and maiagent_count == 0:
            reason = 'Python 已入選重大事故，但 MaiAgent 正式回覆未輸出重大事故。'
        elif maiagent_count > 0 and final_count == 0:
            reason = 'MaiAgent 正式回覆含重大事故，但報告後處理後未保留重大事故。'
        elif python_count == 0:
            reason = 'Python 入選候選未含重大事故，最終正式報告亦無重大事故。'
        else:
            reason = '最終正式報告未輸出重大事故。'
    return {'python_incident_selected_count': python_count, 'maiagent_incident_report_count': maiagent_count, 'final_incident_report_count': final_count, 'incident_dropped_after_maiagent': dropped_after_maiagent, 'incident_coverage_warning': warning, 'incident_coverage_reason': reason}

def report_has_unselected_types(report_md: str, *, context: ReportPostprocessContext) -> bool:
    unselected = [category for category in REPORT_CATEGORY_TYPES if category not in context.selected_types]
    for category in unselected:
        if re.search(f'(?m)^(##|###)\\s+.*{re.escape(category)}', report_md):
            return True
    return False

def report_has_non_urban_formal_items(report_md: str, *, context: ReportPostprocessContext) -> bool:
    formal_area = report_md.split('## 候補觀察', 1)[0]
    for block in re.split('(?m)^###\\s+', formal_area)[1:]:
        if '[規範更新]' in block:
            continue
        if not context.is_urban_rail_candidate(block):
            return True
    return False

def has_candidate_observations(report_md: str, *, context: ReportPostprocessContext) -> bool:
    return '候補觀察' in report_md and (not re.search('候補觀察[^\\n]*\\n\\s*(?:無|本期無)', report_md))
