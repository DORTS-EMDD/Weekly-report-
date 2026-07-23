"""Pure-text normalization and postprocessing for completed MaiAgent reports."""

import datetime
import re
from typing import Callable

from article_processor import (
    _domain_from_url,
    _extract_complete_urls,
    _extract_domain_hint,
    _is_article_level_url,
    _is_query_proxy_source_label,
    _normalize_title,
)
from config import ADVANCED_TYPES, EMPTY_TEXT_BY_TYPE, SECTION_NUMBER_BY_TYPE
from maiagent_service import remove_internal_candidate_markers


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
    if not label and domain:
        label = domain
    return label or "資料來源未明確辨識"


def normalize_source_line(line: str) -> str:
    if "資料來源" not in (line or ""):
        return line
    match = re.match(
        r"^\s*(?:[-*]\s*)?(?:•\s*)?(?:\*\*)?資料來源(?:\*\*)?\s*[：:]\s*(.*)$",
        line or "",
    )
    if not match:
        return line
    content = match.group(1).strip()
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
            supplemental_entries.append("，".join([label] + entry_urls) if label else "，".join(entry_urls))
        if supplemental_entries:
            return normalized_primary + "；補充來源：" + "；".join(supplemental_entries)
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
    if not url and urls:
        url = urls[0]
    host = _domain_from_url(url)
    source_ref = url or domain_hint
    source_label = _clean_source_label(content, source_ref, domain_hint or host)
    parts = [source_label]
    if date_text and date_text != "日期未知":
        parts.append(date_text)
    ordered_urls = list(dict.fromkeys(
        [value for value in urls if "news.google.com" not in _domain_from_url(value) and _is_article_level_url(value)]
        + [value for value in urls if "news.google.com" in _domain_from_url(value) and _is_article_level_url(value, allow_google_news=True)]
        + urls
    ))
    if ordered_urls:
        parts.extend(ordered_urls)
    elif source_ref:
        parts.append(source_ref)
    return f"• 資料來源：{'，'.join(part for part in parts if part)}"


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
    for category in ADVANCED_TYPES:
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
        for category in ADVANCED_TYPES:
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
    selected_parts = [category for category in ADVANCED_TYPES if category in selected_types]
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
        normalized = normalized.replace(old, "營運議題")
    return normalized


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
        "營運議題": "三",
        "規範更新": "四",
        "國際學術期刊": "五" if standards_enabled or "規範更新" in selected_types else "四",
    }
    for label, number in section_numbers.items():
        aliases = "(?:國際學術期刊|技術研究補充)" if label == "國際學術期刊" else re.escape(label)
        normalized = re.sub(
            rf"(?m)^\s*#{{0,6}}\s*[一二三四五六七八九十]\s*、\s*{aliases}\s*$",
            f"## {number}、{label}",
            normalized,
        )
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
        r"(?ms)^\s*(🔹\s*\[(?:營運政策|營運爭議)\].*?)"
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
        r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:營運政策|營運爭議|營運議題)\s*$"
    )
    heading_matches = list(heading_pattern.finditer(text))
    spans: list[tuple[int, int]] = []
    blocks: list[str] = []
    next_section_pattern = re.compile(
        r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、|^\s*📊|^\s*⏰"
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
        section_body = "本期未發現符合條件之營運議題。"
    merged_section = f"## 三、營運議題\n\n{section_body}\n\n"

    operations_enabled = bool({"營運政策", "營運爭議"}.intersection(selected_types))
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
            r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:規範更新|國際學術期刊|技術研究補充)\s*$|^\s*📊|^\s*⏰",
            text,
        )
        insert_at = insert_match.start() if insert_match else len(text)
        text = text[:insert_at].rstrip() + "\n\n" + merged_section + text[insert_at:].lstrip()

    text = re.sub(
        r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*規範更新\s*$",
        "## 四、規範更新",
        text,
    )
    research_number = "五" if standards_enabled or "規範更新" in selected_types else "四"
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


def normalize_electromechanical_system_value(value: str, context: str = "") -> str:
    del context
    raw_value = re.sub(r"\s+", " ", (value or "").strip())
    placeholders = {
        "未明確載明機電系統", "未明確載明", "未載明", "不明", "未知", "無", "n/a", "na", "-",
    }
    tokens = [
        token.strip(" \t\r\n、,，;；。")
        for token in re.split(r"[、,，;；]+", raw_value)
    ]
    concrete_tokens = [token for token in tokens if token and token.casefold() not in placeholders]
    retained = concrete_tokens or [token for token in tokens if token]
    unique_tokens: list[str] = []
    seen: set[str] = set()
    for token in retained:
        key = re.sub(r"\s+", "", token).casefold()
        if key and key not in seen:
            seen.add(key)
            unique_tokens.append(token)
    return "、".join(unique_tokens) if unique_tokens else "未明確載明機電系統"


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
    "國家/地區": "國家/地區",
    "相關機電系統": "相關機電系統",
    "事件摘要": "事件摘要",
    "臺北捷運局啟示": "臺北捷運局啟示",
    "資料來源": "資料來源",
}


def _match_report_field_line(line: str) -> tuple[str, str] | None:
    match = re.match(
        r"^\s*(?:[-*]\s*)?(?:•\s*)?(?:\*\*)?(?:【)?"
        r"(發布/事件日期|國家/地區|相關機電系統|事件摘要|臺北捷運局啟示|資料來源)"
        r"(?:】)?(?:\*\*)?\s*[：:]\s*(.*)$",
        line or "",
    )
    if not match:
        return None
    return REPORT_FIELD_ALIASES[match.group(1)], match.group(2).strip()


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
    }.get(category, "國際捷運案例")


def normalize_report_title_line(line: str) -> str:
    match = re.match(r"^\s*🔹\s*\[([^\]]+)\]\s*(.*?)\s*$", line or "")
    if not match:
        return line
    category = match.group(1).strip()
    title = match.group(2).strip()
    if _title_needs_repair(title, category):
        title = chinese_fallback_title(category, title)
    return f"🔹 [{category}] {title}"


def normalize_final_report_md(md: str) -> str:
    text = md or ""
    text, protected_journal_sections = _protect_journal_sections(text)
    text = re.sub(r"(?m)^\s*[-*]\s*\*\*(發布/事件日期|國家/地區|相關機電系統|事件摘要|臺北捷運局啟示|資料來源)\*\*\s*[：:]", r"• \1：", text)
    text = re.sub(r"(?m)^\s*[-*]\s*\*\*【臺北捷運局啟示】\*\*\s*[：:]", "• 臺北捷運局啟示：", text)
    text = re.sub(r"(?m)^\s*•\s*【臺北捷運局啟示】\s*[：:]", "• 臺北捷運局啟示：", text)
    text = re.sub(r"(?m)^#{3,6}\s+\[([^\]]+)\]\s*(.+)$", r"🔹 [\1] \2", text)

    lines = text.splitlines()
    output: list[str] = []
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
            output.append(normalize_report_title_line(raw_line) if stripped.startswith("🔹") else raw_line)
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
            if field_text:
                output.extend(["• 事件摘要：", field_text, ""])
        elif label == "臺北捷運局啟示":
            insight = _short_formal_sentence(field_text, 180)
            if insight:
                output.extend(["• 臺北捷運局啟示：", insight, ""])
        elif label == "資料來源":
            output.extend([normalize_source_line(f"• 資料來源：{field_text}"), ""])
        elif label == "相關機電系統":
            system_value = normalize_electromechanical_system_value(field_text, context_window)
            if system_value:
                output.extend([f"• 相關機電系統：{system_value}", ""])
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
    return not any(fragment in cleaned for fragment in TITLE_PLACEHOLDER_FRAGMENTS) and cleaned not in {
        re.sub(r"\s+", "", item) for item in TITLE_PLACEHOLDERS
    } and len(
        re.findall(r"[\u3400-\u9fff]", cleaned)
    ) >= 6


def _title_needs_repair(title: str, category: str = "") -> bool:
    cleaned = re.sub(r"\s+", "", title or "")
    if not cleaned:
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
    bullet_count = len(re.findall(r"(?m)^🔹\s*\[(?:技術新知|重大事故|營運政策|營運爭議|規範更新)\]", report_md or ""))
    if bullet_count:
        return bullet_count
    count = 0
    for match in re.finditer(r"^###\s+(.+)$", report_md or "", flags=re.MULTILINE):
        heading = match.group(1)
        if any(category in heading for category in ADVANCED_TYPES):
            count += 1
    return count


def count_report_items_by_category(report_md: str) -> dict[str, int]:
    counts = {category: 0 for category in ADVANCED_TYPES}
    for match in re.finditer(r"(?m)^🔹\s*\[([^\]]+)\]", report_md or ""):
        category = match.group(1).strip()
        if category in counts:
            counts[category] += 1
    if any(counts.values()):
        return counts
    for match in re.finditer(r"^###\s+(.+)$", report_md or "", flags=re.MULTILINE):
        heading = match.group(1)
        for category in ADVANCED_TYPES:
            if category in heading:
                counts[category] += 1
                break
    return counts
