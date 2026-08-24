"""Pure prompt construction and first-stage selection response parsing."""

import datetime
import json
import re
from dataclasses import dataclass
from typing import Callable

from config import (
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
    FORMAL_REPORT_CATEGORY_MAP,
    OPERATIONAL_DYNAMICS_CATEGORY_LABEL,
    SERVICE_OPENING_CATEGORY_KEY,
)
from article_processor import build_formal_report_source


@dataclass(frozen=True)
class ReportPromptContext:
    selected_types: list[str]
    include_research_supplement: bool
    standards_enabled: bool
    lookback_int: int
    date_range: str
    report_title: str
    report_scope_label: str
    research_supplement_period_label: str
    research_supplement_start_date: datetime.date
    today: datetime.date
    empty_text_by_type: dict[str, str]
    advanced_types: list[str]
    selection_min_items: int
    selection_max_items: int
    candidate_snippet_chars: int
    report_snippet_chars: int
    get_selection_output_range: Callable[[int], str]
    effective_source_url: Callable[[dict], str]
    domain_from_url: Callable[[str], str]
    extract_domain_hint: Callable[[str], str]
    infer_preliminary_type: Callable[[dict], str]
    shorten: Callable[[str, int], str]
    is_standard_update_candidate: Callable[[str, bool], bool]
    source_label_for_report: Callable[..., str]
    source_verb_for_report: Callable[[str, str], str]


def formal_selected_type_labels(selected_types: list[str]) -> list[str]:
    labels: list[str] = []
    for category in selected_types or []:
        if category in {"營運政策", "營運爭議", SERVICE_OPENING_CATEGORY_KEY}:
            label = OPERATIONAL_DYNAMICS_CATEGORY_LABEL
        else:
            label = category
        if label and label not in labels:
            labels.append(label)
    return labels


_GENERIC_SOURCE_LABELS = {
    "資料來源未明確辨識",
    "來源未明確",
    "未提供來源名稱",
    "原始候選資料未提供來源",
}

_UNKNOWN_COUNTRY_VALUES = {"", "未判定", "未知", "不明", "未明"}


def _formal_source_display(
    candidate: dict,
    source_url: str,
    *,
    context: ReportPromptContext,
) -> str:
    source_display = str(candidate.get("source_display", "") or "").strip()
    if source_display and source_display not in _GENERIC_SOURCE_LABELS:
        return source_display
    return str(
        candidate.get("source_domain")
        or context.domain_from_url(source_url)
        or context.extract_domain_hint(source_url)
        or ""
    ).strip()


def _authoritative_candidate_classification(
    candidate: dict,
    *,
    context: ReportPromptContext,
) -> str:
    for key in ("classification", "primary_category", "preliminary_type"):
        value = str(candidate.get(key, "") or "").strip()
        if value in context.advanced_types:
            return value
    inferred = str(context.infer_preliminary_type(candidate) or "").strip()
    return inferred if inferred in context.advanced_types else ""


def _formal_report_category(value: str) -> str:
    return FORMAL_REPORT_CATEGORY_MAP.get(value, value)


def format_selection_candidate(
    candidate: dict,
    *,
    context: ReportPromptContext,
) -> str:
    source_url = context.effective_source_url(candidate)
    prompt_card = {
        "id": candidate.get("id", ""),
        "title": candidate.get("title", ""),
        "date": candidate.get("date", ""),
        "source_display": candidate.get(
            "source_display",
            candidate.get("source", ""),
        ),
        "source_domain": (
            candidate.get("source_domain")
            or context.domain_from_url(source_url)
            or context.extract_domain_hint(source_url)
        ),
        "region": candidate.get("region", "未判定"),
        "preliminary_type": candidate.get(
            "preliminary_type",
            context.infer_preliminary_type(candidate),
        ),
        "python_score": candidate.get("python_score", 0),
        "short_snippet": candidate.get(
            "short_snippet",
            context.shorten(
                candidate.get("snippet", ""),
                context.candidate_snippet_chars,
            ),
        ),
        "url": source_url,
    }
    return json.dumps(prompt_card, ensure_ascii=False)


def selected_report_sections(*, context: ReportPromptContext) -> str:
    lines: list[str] = []
    if "技術新知" in context.selected_types:
        lines.append("一、技術新知")
    if "重大事故" in context.selected_types:
        lines.append("二、重大事故")
    if {"營運政策", "營運爭議", SERVICE_OPENING_CATEGORY_KEY}.intersection(context.selected_types):
        lines.append(f"三、{OPERATIONAL_DYNAMICS_CATEGORY_LABEL}")
    if ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL in context.selected_types:
        lines.append("四、機電標案")
    if "規範更新" in context.selected_types:
        standards_number = "五" if ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL in context.selected_types else "四"
        lines.append(f"{standards_number}、規範更新")
    if context.include_research_supplement:
        lines.append(research_section_heading(markdown=False, context=context))
    return "\n".join(lines) if lines else "無"


def section_number_for_index(index: int) -> str:
    numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    if 1 <= index <= len(numerals):
        return numerals[index - 1]
    return str(index)


def research_section_heading(
    markdown: bool = False,
    *,
    context: ReportPromptContext,
) -> str:
    has_procurement = ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL in context.selected_types
    has_standards = context.standards_enabled or "規範更新" in context.selected_types
    section_number = "六" if has_procurement and has_standards else "五" if has_procurement or has_standards else "四"
    heading = f"{section_number}、國際學術期刊"
    return f"## {heading}" if markdown else heading


def selected_empty_section_rules(*, context: ReportPromptContext) -> str:
    lines: list[str] = []
    for category in ("技術新知", "重大事故"):
        if category in context.selected_types:
            lines.append(
                f"- {category}若無符合資料，請寫："
                f"「{context.empty_text_by_type[category]}」"
            )
    if {"營運政策", "營運爭議", SERVICE_OPENING_CATEGORY_KEY}.intersection(context.selected_types):
        lines.append(
            f"- {OPERATIONAL_DYNAMICS_CATEGORY_LABEL}若無符合資料，"
            f"請只寫：「本期未發現符合條件之{OPERATIONAL_DYNAMICS_CATEGORY_LABEL}。」"
        )
    if ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL in context.selected_types:
        lines.append(
            f"- {ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL}若無符合資料，"
            f"請寫：「本期未發現符合條件之{ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL}。」"
        )
    if "規範更新" in context.selected_types:
        lines.append(
            f"- 規範更新若無符合資料，請寫："
            f"「{context.empty_text_by_type['規範更新']}」"
        )
    return (
        "\n".join(lines)
        if lines
        else "- 未勾選新聞類型時，不得自行新增章節。"
    )


def selected_stats_template(*, context: ReportPromptContext) -> str:
    parts = [
        f"{category} N 則"
        for category in context.advanced_types
        if category in context.selected_types
    ]
    return " / ".join(parts) if parts else "無"


def policy_selection_rule(*, context: ReportPromptContext) -> str:
    if "營運政策" not in context.selected_types:
        return ""
    weekly_limit = "7 天週報中，營運政策原則最多 4～5 則。" if context.lookback_int == 7 else "營運政策需保留具制度、系統或治理價值者。"
    return f"""
- {weekly_limit}
- 營運政策優先：票價政策且涉及 AFC/票務系統、大型活動疏運且含班距/加班車/人流或車站管制、新線通車/試營運/系統轉換、建設治理/資產更新、維修窗口且有明確工程或系統影響。
- 營運政策降權或排除：單純假日提醒、活動搭乘資訊、週末服務公告、路線查詢/trip result/route page，或沒有班距、加班車、車站管制、人流管理、設備或系統資訊者。
- 同一週多則大型活動、假日或週末服務公告，請合併為 1 則綜合案例，不要逐則拆列；不得為了湊數納入低價值營運公告。
""".strip()


def build_selection_prompt(
    candidates: list[dict],
    *,
    context: ReportPromptContext,
) -> str:
    candidate_block = "\n\n".join(
        format_selection_candidate(candidate, context=context)
        for candidate in candidates
    )
    if not candidate_block:
        candidate_block = "本期 Python 初篩後沒有候選新聞。請回傳空的 selected_ids 清單。"
    formal_types = formal_selected_type_labels(context.selected_types)
    selected_types_str = "、".join(formal_types) if formal_types else "無"
    example_type = formal_types[0] if formal_types else "技術新知"
    output_range = context.get_selection_output_range(context.lookback_int)
    return f"""
請依照你在 MaiAgent 後台設定的國際捷運技術週報角色指令，根據以下候選資料執行第一階段選題。不得自行搜尋或補充候選資料以外的新聞、日期、供應商、技術細節或統計數據。

本次是第一階段選題任務；請只判斷候選資料是否適合納入正式報告，不要撰寫正式新聞段落。
報告期間：{context.date_range}
使用者勾選的新聞類型：{selected_types_str}
需要選出的數量：{output_range} 則；高品質候選不足時可少於目標，但不要用低價值資料湊數。

請只使用候選資料中的 id 進行選題；category 必須使用「技術新知」、「重大事故」、「營運動態」或「機電標案」其中之一。營運動態的政策、爭議與 service_opening subtype 仍由 Python 候選資料保留，不得自行重新判斷 eligibility。不得輸出 Markdown 說明。

輸出 JSON 格式：
{{
  "selected_ids": [
    {{
      "id": 1,
      "category": "{example_type}",
      "reason": "入選理由",
      "priority": 1,
      "merge_group": "",
      "include_in_report": true
    }}
  ],
  "exclude_ids": [
    {{
      "id": 2,
      "exclude_reason": "排除理由"
    }}
  ]
}}

## 精簡候選資料
{candidate_block}
""".strip()


def json_loads_loose(text: str):
    candidates = []
    fenced = re.findall(
        r"```(?:json)?\s*(.*?)```",
        text or "",
        flags=re.DOTALL | re.IGNORECASE,
    )
    candidates.extend(fenced)
    candidates.append(text or "")
    for raw in candidates:
        raw = raw.strip()
        if not raw:
            continue
        for start_char, end_char in (("{", "}"), ("[", "]")):
            start = raw.find(start_char)
            end = raw.rfind(end_char)
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start:end + 1])
                except Exception:
                    continue
    return None


def truthy_report_flag(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    text = str(value).strip().casefold()
    return text not in {"false", "no", "否", "不納入", "不建議", "0"}


def parse_selection_response(
    response_text: str,
    candidates: list[dict],
    *,
    context: ReportPromptContext,
) -> list[dict]:
    candidate_map = {int(candidate["id"]): candidate for candidate in candidates}
    selected: list[dict] = []
    seen_ids: set[int] = set()

    parsed = json_loads_loose(response_text)
    items = []
    if isinstance(parsed, dict):
        if isinstance(parsed.get("selected_ids"), list):
            for raw_item in parsed["selected_ids"]:
                if isinstance(raw_item, dict):
                    items.append(raw_item)
                else:
                    items.append({"id": raw_item})
        for key in ("selected", "items", "入選", "selections"):
            if isinstance(parsed.get(key), list):
                items.extend(parsed[key])
                break
    elif isinstance(parsed, list):
        items = parsed

    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id") or item.get("編號") or item.get("number") or item.get("candidate_id")
        try:
            candidate_id = int(raw_id)
        except Exception:
            continue
        if candidate_id not in candidate_map or candidate_id in seen_ids:
            continue
        if not truthy_report_flag(item.get("include_in_report", item.get("是否建議納入正式週報"))):
            continue
        candidate = dict(candidate_map[candidate_id])
        classification = _authoritative_candidate_classification(candidate, context=context)
        if classification not in context.selected_types:
            continue
        candidate["classification"] = classification
        candidate["selected_reason"] = item.get("selected_reason") or item.get("入選理由") or item.get("reason") or "MaiAgent 第一階段選題入選。"
        candidate["selection_priority"] = item.get("priority", "")
        candidate["merge_group"] = item.get("merge_group", "")
        candidate["include_in_report"] = True
        selected.append(candidate)
        seen_ids.add(candidate_id)
        if len(selected) >= context.selection_max_items:
            return selected

    if selected:
        return selected

    fallback_ids: list[int] = []
    for match in re.finditer(r"(?:編號|候選|ID|id|#)\s*[:：]?\s*(\d{1,3})", response_text or ""):
        candidate_id = int(match.group(1))
        if candidate_id in candidate_map and candidate_id not in fallback_ids:
            fallback_ids.append(candidate_id)
    if not fallback_ids:
        for line in (response_text or "").splitlines():
            match = re.match(r"^\s*(\d{1,3})[\.、\)]", line)
            if match:
                candidate_id = int(match.group(1))
                if candidate_id in candidate_map and candidate_id not in fallback_ids:
                    fallback_ids.append(candidate_id)

    for candidate_id in fallback_ids[:context.selection_max_items]:
        candidate = dict(candidate_map[candidate_id])
        candidate["classification"] = _authoritative_candidate_classification(candidate, context=context)
        if candidate["classification"] not in context.selected_types:
            continue
        candidate["selected_reason"] = "MaiAgent 第一階段回應未完全符合 JSON，已依回應中的候選編號納入。"
        candidate["include_in_report"] = True
        selected.append(candidate)

    if selected:
        return selected

    fallback_count = min(
        context.selection_min_items,
        len(candidates),
        context.selection_max_items,
    )
    for candidate in candidates[:fallback_count]:
        backup = dict(candidate)
        backup["classification"] = _authoritative_candidate_classification(backup, context=context)
        if backup["classification"] not in context.selected_types:
            continue
        backup["selected_reason"] = "MaiAgent 第一階段回應格式無法解析；依 Python 初篩排序備援納入。"
        backup["include_in_report"] = True
        selected.append(backup)
    return selected


def format_report_candidate(
    candidate: dict,
    *,
    context: ReportPromptContext,
) -> str:
    report_source = build_formal_report_source(candidate)
    source_display = report_source["display_name"]
    classification = _authoritative_candidate_classification(candidate, context=context)
    formal_category = _formal_report_category(classification)
    raw_country = candidate.get("country")
    country = str(raw_country or "").strip()
    if country in _UNKNOWN_COUNTRY_VALUES:
        country = ""
    prompt_item = {
        "candidate_id": candidate.get("candidate_id", candidate.get("id", "")),
        "title": candidate.get("title", ""),
        "date": candidate.get("date", ""),
        "report_source": report_source,
        "source_verb": candidate.get("source_verb", context.source_verb_for_report(candidate.get("source_tier", ""), source_display)),
        "core_systems": candidate.get("core_systems", []),
        "technical_themes": candidate.get("technical_themes", []),
        "classification": formal_category,
        "formal_category": formal_category,
        "snippet": context.shorten(candidate.get("snippet", ""), context.report_snippet_chars),
        "source_domain": candidate.get("source_domain") or context.domain_from_url(report_source["display_url"]) or context.extract_domain_hint(report_source["display_url"]),
        "resolved_region": candidate.get("resolved_region", ""),
        "region_resolution_method": candidate.get("region_resolution_method", ""),
        "region_resolution_evidence": candidate.get("region_resolution_evidence", ""),
        "operator": candidate.get("operator") or candidate.get("operator_name") or candidate.get("operator_key", ""),
        "system_name": candidate.get("system_name") or candidate.get("system") or "",
    }
    if country:
        prompt_item["country"] = country
    return json.dumps(prompt_item, ensure_ascii=False)


def build_report_prompt(
    selected_candidates: list[dict],
    journal_candidates: list[dict],
    search_count: int,
    *,
    context: ReportPromptContext,
) -> str:
    selected_types_str = "、".join(formal_selected_type_labels(context.selected_types)) if context.selected_types else "無"
    selected_sections = selected_report_sections(context=context)
    selected_empty_rules = selected_empty_section_rules(context=context)
    research_heading = research_section_heading(markdown=False, context=context)
    candidate_block = "\n\n".join(
        format_report_candidate(candidate, context=context)
        for candidate in selected_candidates
    )
    if not candidate_block:
        candidate_block = "Python 選題流程沒有入選新聞。請只依已勾選章節輸出沒有符合資料的固定文字，不得自行補新聞。"

    journal_input_section = ""
    if context.include_research_supplement:
        if journal_candidates:
            journal_block = "\n".join(
                json.dumps({
                    "title": item.get("title", ""),
                    "date": item.get("published_date", "") or item.get("date", ""),
                    "journal_name": item.get("journal_name", item.get("source", "")),
                    "doi": item.get("doi", ""),
                    "journal_score": item.get("journal_score", ""),
                    "journal_score_reason": item.get("journal_score_reason", ""),
                    "url": item.get("url", ""),
                    "snippet": context.shorten(item.get("snippet", ""), context.report_snippet_chars),
                }, ensure_ascii=False)
                for item in journal_candidates
            )
        else:
            journal_block = "無符合期間條件且具明確發表日期之研究候選。"
        journal_input_section = f"""
## 國際學術與技術研究補充候選
研究補充已啟用；本次研究補充期間為{context.research_supplement_period_label}（{context.research_supplement_start_date.isoformat()} 至 {context.today.isoformat()}）。

如有候選，正式報告最後必須輸出「{research_heading}」，並嚴格使用下列格式：

## {research_heading}

1、繁體中文研究標題

• 發表日期：YYYY-MM-DD

• 期刊／來源：期刊完整名稱

• 研究主題：研究主題

• 研究摘要：完整段落

• 臺北捷運局啟示：完整段落

• 資料來源：完整 URL

2、繁體中文研究標題

• 發表日期：YYYY-MM-DD

• 期刊／來源：期刊完整名稱

• 研究主題：研究主題

• 研究摘要：完整段落

• 臺北捷運局啟示：完整段落

• 資料來源：完整 URL

期刊格式要求：
- 只有每篇期刊標題可以使用「1、」「2、」等流水編號。
- 每個欄位名稱與欄位內容必須在同一行，不得將日期、期刊名稱、研究主題或資料來源移到下一行。
- 統一使用「期刊／來源」，不得使用「期刊/來源」。
- 不得重複日期、期刊名稱、研究主題或資料來源。
- 不得在各欄位前新增流水編號，不得使用「[技術研究補充]」。
- 各篇期刊之間保留清楚空行，不得使用「---」分隔。
- 最後一篇期刊結束後直接結束本章，不得輸出「學術期刊綜合結論」或任何綜合結論文字。
- 請勿在期刊章節後輸出本期統計、報告產出時間或系統資訊。

若沒有候選，請只寫：「本期未發現符合期間條件且具明確發表日期之國際學術或技術研究資料。」

研究候選：
{journal_block}
""".strip()
    journal_input_text = f"\n\n{journal_input_section}" if journal_input_section else ""

    return f"""
請依照 MaiAgent 後台設定的國際捷運技術週報角色指令，根據以下已入選新聞撰寫正式報告。不得自行搜尋，不得補充候選資料以外的新聞、日期、國家、城市、路線、供應商、技術細節、事故原因、統計數據或金額。

本次是第二階段正式報告撰寫任務。
報告標題：{context.report_title}
資料涵蓋期間：{context.date_range}
勾選類型：{selected_types_str}
正式報告章節：
{selected_sections}
空章節文字：
{selected_empty_rules}

正式報告開頭固定：
# {context.report_title}
> 資料涵蓋期間：{context.date_range}

正式報告每則新聞請使用以下格式，不得改成表格、簡報式卡片或多層條列，不得新增「技術關鍵字」欄位，不得把「臺北捷運局啟示」拆成子欄位。正式新聞類型標籤只能使用「技術新知」、「重大事故」、「營運動態」或「機電標案」；不得把 Python internal subtype 當成正式標籤。候選資料中的 country 是正式國家欄位；若 payload 未提供 country，僅可依候選證據判斷，仍無法判斷時省略「國家」欄位；core_systems 為空時，完全省略「相關機電系統」欄位，不得自行補上通用名稱：
🔹 [新聞類型] 繁體中文新聞標題

• 發布/事件日期：YYYY-MM-DD

• 國家：

• 相關機電系統：（僅在 core_systems 非空時輸出七大主系統名稱）

• 事件摘要：
完整段落

• 臺北捷運局啟示：
完整段落

• 資料來源：

每則新聞之間使用：
---

必要寫作提醒：
- 只根據下方已入選新聞資料撰寫；正式報告只輸出已勾選章節，不得輸出未勾選類型。
- 營運動態（含政策、爭議與 service_opening subtype）統一置於「三、營運動態」章節；不得另外輸出 subtype 章節，並依日期新至舊排列。
- 機電標案是獨立的「四、機電標案」章節；來源明確提供時，可摘要路線／系統、標案／採購內容、廠商與金額。來源未提供的廠商、金額或技術細節不得自行補寫。
- 下方共 {len(selected_candidates)} 則新聞已由 Python 完成「入選」及同事件來源整理。每個 selected candidate_id 代表一則獨立正式新聞；明顯屬於非都市軌道、刑事治安、旅遊、公車或其他禁止範圍的候選可排除。不得自行新增候選資料以外的事件。
- 每則正式新聞標題正前方必須原樣輸出唯一一個 `<!-- candidate_id: N -->`，其中 N 必須等於候選資料的 candidate_id；不得省略、改號或自行產生 ID。
- 一個正式新聞 block 只能包含一個 candidate_id marker；每個 selected candidate 必須各自輸出一個完整 block，即使候選描述相同事件也不得合併。不得把另一個 candidate marker 放入目前 block，任何 candidate ID 不得省略、重複或合併。
- 除非 Python 候選本身已完成同事件合併，輸出的正式新聞則數必須等於 {len(selected_candidates)}；不得因翻譯標題、摘要相近或來源網址相似而省略候選。
- 每則候選 payload 的 report_source 只有 display_name 與 display_url；正式來源名稱與 URL 必須原樣沿用。若 display_url 是可信 publisher 首頁，代表原始文章 URL 尚未解析，不得自行補造文章路徑。
- 候選資料未提供可靠中文名稱時，保留原文站名、路線、車型、供應商與地名，可使用「原文＋中文通用類型」（例如 `Buangkok MRT 站`、`Bakerloo Line`）；不得依模型記憶把一個外國實體替換成另一個既有中文名稱。
- 正式報告新聞數必須等於本次入選數；不得因同一事件、翻譯標題、摘要相近或來源網址相似而省略或合併候選。
- 候選資料中的 classification 已由 Python 完成選題與分類，是正式章節的權威欄位；請依 classification 指定的章節撰寫，不得自行跨章節重新分類。
- 營運動態及其 Python subtype 均須留在「三、營運動態」；同事件來源已由 Python 在送入模型前整理，模型不得再合併候選或改到其他章節。

新聞類型判斷原則：
- 技術新知：原始資料明確描述都市軌道機電設備或系統的新導入、擴充、升級、汰換、改善、測試驗證或正式投入營運。包括新型車輛投入營運、生物辨識或 AFC 系統應用、新票閘設備、號誌與列車控制、供電、通訊、月臺門、行控、機廠維修設備、維修監測、能源管理、系統整合、系統保證及資安等具體案例；純電梯、電扶梯或空調汰換不因設備名稱本身列入。
- 技術新知不限於採購、合約或正式上線事件；候選若明確說明都市軌道機電技術原理、工程挑戰或系統應用，即使屬專業技術文章仍應保留。Frauscher 軸計數器與電車號誌工程文章即屬此類，不得只因缺少單一專案事件而刪除。
- AI、機器學習、影像分析、預測維護、狀態監測、數位分身、資料治理、資安、RAMS、SIL、驗證、系統整合、互通性、智慧調度或維修決策支援等跨系統技術，只要候選資料同時具備明確都市軌道場景與實際技術應用即可保留；不得因 core_systems 為空就刪除，也不得把跨系統主題臆造為七大主系統。
- 重大事故：已實際發生，且涉及傷亡、出軌、碰撞、火災、重大設備損壞、停駛、重大營運中斷，或具有明確系統安全檢討價值的事件。
- 事故後的安全改善、設施改善、監管檢討、治理或政策回應，若不是本期新發生事故，應歸入營運動態，不得僅因提到 accident、fatal、safety 或 incident 改列重大事故。
- 營運動態（政策類型）：票價、服務調整、營運諮詢、預定封閉、例行維修、一般工程安排、旅客服務及治理措施。若新聞同時具有明確設備導入、系統升級或技術驗證內容，應優先歸為技術新知。
- 營運動態（爭議類型）：罷工、勞資、票價、合約、預算、工程延誤、訴訟或公共爭議。
- 規範更新：必須具備明確新版、修訂、增補、草案、公告、徵詢、撤回或取代資訊。
- 既有設備單純發生故障，不得列為技術新知；預定封閉、例行維修及一般工程進度不得列為重大事故；不得只因新聞出現 AI、系統、設備、測試或 Metro 等字詞，就判定為技術新知。

地區與來源判斷：
- 國家／地區以事件實際發生地為準，不得以旅客國籍、媒體所在地、搜尋語言或來源網站所在地判斷。
- 若標題或摘要已明確出現城市、國家或營運機構，應更正程式初判。例如 Mumbai 應判為印度、St. Paul 應判為美國、Moscow 應判為俄羅斯；原始資料確實無法判定時，才寫「未判定」。
- 若 Python payload 已提供非空 country，正式報告的「國家」欄位必須原樣沿用，不得改成城市或其他地區。若 payload 未提供 country，可僅依候選提供的城市、地名、營運機構、捷運系統名稱、來源及事件文字判斷最可能的國家；此權限僅限國家欄位，不得因此補充其他事件事實。仍無法合理判斷時，省略「國家」欄位，絕不得輸出「國家：未判定」。
- 只有政府機關、交通主管機關、捷運營運機構及其官方網站，才可使用「公告」或「官方資料」。MSN、Yahoo、一般新聞媒體、入口網站與轉載平台一律使用「報導」，不得寫成「官方公告」。
- source_display 或 source_verb 若與 source_domain 明顯矛盾，應以 source_domain 所代表的實際來源性質為準。

內容與格式要求：
- 每則新聞標題必須翻成繁體中文正式標題；機構、車型或系統縮寫可保留。
- 發布／事件日期統一顯示為 YYYY-MM-DD，不得輸出 ISO 時間、時區或 `T00:00:00+00:00`。
- 「事件摘要：」與「臺北捷運局啟示：」後方必須換行，摘要與啟示不得使用條列。
- 事件摘要第一句必須直接進入事件主體，不得以媒體、網站或來源名稱加「報導／指出／表示」開頭；來源歸屬統一置於「資料來源」欄位。
- 事件摘要僅根據候選資料撰寫，重點為事件本身、都市軌道場景、涉及的機電系統或營運管理意義。原始資料未提供細節時應保守表述，不得自行補述數字、供應商、金額、GoA 等級、測試項目、車輛規格、事故原因或導入時程。
- 資料不足時直接縮短摘要，不得於正文列舉技術規格、時程、測試內容或其他未提供項目。
- 每則「臺北捷運局啟示」只選擇與該事件最直接相關的一至二項工程重點，不得每則同時羅列系統整合、資料治理、維修管理、資安、能源效率及風險控管。例如票閘設備著重 AFC 介面、容量與維修；電梯汰換著重設備生命週期、施工界面與無障礙服務；號誌事故著重故障隔離、備援與營運應變。
- 「相關機電系統」只可從候選 core_systems 原樣選用：電聯車、號誌、供電、通訊、自動收費、機廠維修設備、月臺門。車門、轉向架、聯結器、CBTC、CCTV、SCADA、AI、資安、RAMS、環控、電梯、電扶梯與軌道只能在摘要或啟示中作為技術主題；core_systems 為空時省略本欄位，不得寫「未明確」或泛稱「都市軌道系統」。
- 資料來源欄必須同時顯示 report_source.display_name 與 report_source.display_url；不得輸出 Google News proxy URL。display_name 已由 Python 依明確來源 metadata 或 canonical domain mapping 整理，禁止自行改名或杜撰媒體名稱。
- 若事件摘要使用 supplemental_sources 的供應商、技術或數據資訊，資料來源欄必須同時列出主要來源與相應補充來源的完整連結。例如 TTC Line 2 摘要若使用 Hitachi 數位號誌或 40% 容量資訊，必須同時列出 TTC 主要來源及 Hitachi／Newswire 補充來源。
- 不得在正式報告正文使用 MaiAgent、Python 初篩、developer debug、python_score、候選 flags、入選原因或其他模型處理語氣。
- 請勿輸出「本期統計」、「報告產出時間」、搜尋次數、候選數量或任何系統執行資訊；這些內容將由程式後續統一產生。
- 未啟用國際學術期刊時，正式報告正文結束於最後一則新聞；啟用期刊時，正文結束於最後一篇期刊，不得輸出「學術期刊綜合結論」。

## 已入選新聞資料
{candidate_block}
{journal_input_text}

## 最高優先正文規則
正式正文禁止出現「資料未提供」、「候選資料未提供」、「原始資料未提供」、「資料來源未載明」等缺漏說明。資訊不足時直接縮短內容，不得列舉缺少的規格、時程、金額、測試內容、設備項目或其他未提供資料。
""".strip()
