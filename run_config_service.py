"""Pure execution settings, report naming, and download filename helpers."""

import datetime
import re
from dataclasses import dataclass
from typing import Callable

from config import OPERATIONAL_DYNAMICS_CATEGORY_LABEL


@dataclass(frozen=True)
class RunSettingsContext:
    today: datetime.date
    lookback_days: int
    selected_types: list[str]
    scope_mode: str
    selected_regions: list[str]
    standards_enabled: bool
    include_research_supplement: bool
    demo_cache_mode_enabled: bool
    current_app_hash: str
    report_period_labels: dict[int, str]
    long_term_target_labels: dict[int, str]
    report_target_by_days: dict[int, int]
    research_supplement_allowed_for_report: Callable[[int], bool]
    get_research_supplement_lookback_days: Callable[[int], int]


@dataclass(frozen=True)
class RunSettings:
    week_start: datetime.date
    date_range: str
    lookback_int: int
    include_research_supplement: bool
    fast_mode_enabled: bool
    demo_cache_mode_enabled: bool
    report_period_label: str
    research_supplement_lookback_days: int
    research_supplement_start_date: datetime.date
    research_supplement_period_label: str
    target_is_enforced: bool
    min_report_items: int
    report_target_display: str
    report_output_requirement: str
    report_quantity_instruction: str
    report_shortfall_summary_line: str
    selected_report_topic: str
    report_title: str
    is_global_scope: bool
    active_regions: list[str]
    report_scope_label: str


def _formal_report_topic_labels(report_types: list[str]) -> list[str]:
    labels: list[str] = []
    operations_added = False
    for category in report_types or []:
        if category in {"營運政策", "營運爭議"}:
            if not operations_added:
                labels.append(OPERATIONAL_DYNAMICS_CATEGORY_LABEL)
                operations_added = True
            continue
        if category not in labels:
            labels.append(category)
    return labels


def build_run_settings(context: RunSettingsContext) -> RunSettings:
    week_start = context.today - datetime.timedelta(days=int(context.lookback_days))
    date_range = f"{week_start.strftime('%Y年%m月%d日')} 至 {context.today.strftime('%Y年%m月%d日')}"
    lookback_int = int(context.lookback_days)
    include_research_supplement = bool(
        context.include_research_supplement
        and context.research_supplement_allowed_for_report(lookback_int)
    )
    fast_mode_enabled = False
    demo_cache_mode_enabled = bool(context.demo_cache_mode_enabled)
    report_period_label = context.report_period_labels.get(lookback_int, "週報")
    research_supplement_lookback_days = (
        context.get_research_supplement_lookback_days(lookback_int)
    )
    research_supplement_start_date = (
        context.today - datetime.timedelta(days=research_supplement_lookback_days)
    )
    research_supplement_period_label = f"近 {research_supplement_lookback_days} 天"
    target_is_enforced = lookback_int in context.report_target_by_days
    min_report_items = context.report_target_by_days.get(lookback_int, 0)
    report_target_display = (
        f"至少 {min_report_items} 則"
        if target_is_enforced
        else context.long_term_target_labels.get(lookback_int, "趨勢回顧")
    )
    report_output_requirement = (
        f"正式報告至少 {min_report_items} 則"
        if target_is_enforced
        else f"{report_target_display}，不強制篇數"
    )
    report_quantity_instruction = (
        f"本期為 {report_period_label}，正式報告建議下限為 {min_report_items} 則。"
        f"請不要在達到 {min_report_items} 則以前提早停止；若高信度新聞不足，"
        f"請優先納入中信度但來源、日期、都市軌道關聯明確的候選；"
        f"不要因摘要較短或連結為 Google News 轉址而過度剔除。"
        f"若最後正式新聞仍不足 {min_report_items} 則，必須在結尾列明不足原因，"
        f"例如：都市軌道來源不足、日期不明、非捷運/非輕軌、來源不合格。"
        f"**品質優先於數量；不得為了湊滿數量，把高鐵、一般鐵路、公車、長途運輸、"
        f"事故、政策、爭議或一般專案消息升格為技術新知。"
        f"規範追蹤清單、持續追蹤中、無單一新聞連結的標準項目，"
        f"不得列入正式規範更新，也不得計入正式新聞數。**"
        if target_is_enforced
        else f"本期為 {report_period_label}，屬長期趨勢 / 規範追蹤模式，不強制篇數。"
             f"請以趨勢分析、事故彙整、真正規範更新、來源品質與重複內容排除為優先；"
             f"不得為了增加篇數納入低關聯、重複、非都市軌道或來源不合格新聞。"
             f"規範追蹤清單、持續追蹤中、無單一新聞連結的標準項目，"
             f"不得列入正式規範更新，也不得計入正式新聞數。"
             f"若有效候選有限，請在報告摘要說明原因。"
    )
    report_shortfall_summary_line = (
        f"**不足 {min_report_items} 則原因**：（僅正式新聞少於 {min_report_items} 則時輸出；若達標，整行不要出現）"
        if target_is_enforced
        else "**長期回顧說明**：（簡述本期趨勢、重複內容排除後有效候選品質與來源限制）"
    )
    selected_report_topic = (
        "、".join(_formal_report_topic_labels(context.selected_types))
        if context.selected_types
        else "技術趨勢"
    )
    report_title = (
        f"【{context.today.strftime('%Y/%m/%d')}】"
        f"國際捷運{selected_report_topic}{report_period_label}"
    )
    is_global_scope = context.scope_mode == "全球（安全白名單來源）"
    active_regions = [] if is_global_scope else context.selected_regions
    report_scope_label = "全球" if is_global_scope else "、".join(active_regions)
    return RunSettings(
        week_start=week_start,
        date_range=date_range,
        lookback_int=lookback_int,
        include_research_supplement=include_research_supplement,
        fast_mode_enabled=fast_mode_enabled,
        demo_cache_mode_enabled=demo_cache_mode_enabled,
        report_period_label=report_period_label,
        research_supplement_lookback_days=research_supplement_lookback_days,
        research_supplement_start_date=research_supplement_start_date,
        research_supplement_period_label=research_supplement_period_label,
        target_is_enforced=target_is_enforced,
        min_report_items=min_report_items,
        report_target_display=report_target_display,
        report_output_requirement=report_output_requirement,
        report_quantity_instruction=report_quantity_instruction,
        report_shortfall_summary_line=report_shortfall_summary_line,
        selected_report_topic=selected_report_topic,
        report_title=report_title,
        is_global_scope=is_global_scope,
        active_regions=active_regions,
        report_scope_label=report_scope_label,
    )


@dataclass(frozen=True)
class RunConfigContext:
    today: datetime.date
    week_start: datetime.date
    lookback_int: int
    date_range: str
    report_period_label: str
    report_title: str
    selected_types: list[str]
    scope_mode: str
    is_global_scope: bool
    active_regions: list[str]
    report_scope_label: str
    standards_enabled: bool
    include_research_supplement: bool
    research_supplement_lookback_days: int
    research_supplement_start_date: datetime.date
    fast_mode_enabled: bool
    demo_cache_mode_enabled: bool
    current_app_hash: str


def build_current_run_config(context: RunConfigContext) -> dict:
    return {
        "report_date": context.today.isoformat(),
        "report_date_label": context.today.strftime("%Y/%m/%d"),
        "start_date": context.week_start.isoformat(),
        "end_date": context.today.isoformat(),
        "lookback_days": context.lookback_int,
        "date_range": context.date_range,
        "report_label": context.report_period_label,
        "report_title": context.report_title,
        "selected_types": context.selected_types.copy(),
        "scope_mode": context.scope_mode,
        "selected_regions": (
            ["全球"] if context.is_global_scope else context.active_regions.copy()
        ),
        "report_scope_label": context.report_scope_label,
        "include_standards": context.standards_enabled,
        "include_research_supplement": context.include_research_supplement,
        "research_supplement_period": {
            "lookback_days": context.research_supplement_lookback_days,
            "start_date": context.research_supplement_start_date.isoformat(),
            "end_date": context.today.isoformat(),
        },
        "fast_mode": context.fast_mode_enabled,
        "demo_cache_mode": context.demo_cache_mode_enabled,
        "app_source_hash": context.current_app_hash,
    }


def get_report_type_code(report_label: str, lookback_days: int) -> str:
    label = (report_label or "").strip()
    try:
        days = int(lookback_days)
    except (TypeError, ValueError):
        days = 0
    if days == 7 or label == "週報":
        return "weekly"
    if days == 30 or label == "月報":
        return "monthly"
    if days == 90 or label == "季報":
        return "quarterly"
    if days == 180 or label in {"半年報", "半年度報告"}:
        return "halfyear"
    if days == 365 or label in {"年報", "年度回顧"}:
        return "annual"
    return f"{days}days" if days else "report"


def _compact_date(
    value,
    fallback: datetime.date | None = None,
    *,
    today: datetime.date,
) -> str:
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, datetime.date):
        return value.strftime("%Y%m%d")
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.datetime.strptime(text, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    match = re.search(r"(20\d{2})\D?(\d{1,2})\D?(\d{1,2})", text)
    if match:
        return (
            f"{int(match.group(1)):04d}"
            f"{int(match.group(2)):02d}"
            f"{int(match.group(3)):02d}"
        )
    return (fallback or today).strftime("%Y%m%d")


@dataclass(frozen=True)
class DownloadFilenameContext:
    current_run_config: dict
    lookback_int: int
    today: datetime.date
    report_period_label: str


def build_report_download_filename(
    prefix: str,
    extension: str,
    run_config: dict | None = None,
    *,
    context: DownloadFilenameContext,
) -> str:
    config = run_config or context.current_run_config
    days = int(config.get("lookback_days") or context.lookback_int)
    report_date_obj = context.today
    try:
        report_date_obj = datetime.date.fromisoformat(
            str(config.get("report_date") or context.today.isoformat())
        )
    except ValueError:
        pass
    report_type_code = get_report_type_code(
        config.get("report_label", context.report_period_label),
        days,
    )
    report_date = _compact_date(
        config.get("report_date"),
        report_date_obj,
        today=context.today,
    )
    clean_prefix = re.sub(
        r"[^A-Za-z0-9_]+",
        "_",
        str(prefix or "report"),
    ).strip("_")
    clean_extension = re.sub(
        r"[^A-Za-z0-9]+",
        "",
        str(extension or ""),
    ).lower()
    filename = (
        f"{clean_prefix}_{report_type_code.strip()}_"
        f"{report_date.strip()}.{clean_extension.strip()}"
    )
    return re.sub(r"\s+\.", ".", filename).strip()
