"""
國際捷運技術週報 AI 自動產生系統。

本程式以 Streamlit 建置操作介面，透過 RSS、Google News 代理及 DDGS 蒐集國際捷運新聞與學術資料，並由 Python 進行日期檢核、來源判斷、去重、排除無關內容、初步分類及候選排序。入選資料再交由 MaiAgent 依固定格式撰寫正式報告，內容涵蓋技術新知、重大事故、營運政策、營運爭議、規範更新及國際學術期刊。系統支援週報至年度回顧、PDF 輸出、Email 寄送、除錯 JSON 及排程自動寄送。
"""

import os
import re
import json
import hashlib
import time
import random
import difflib
import datetime
import smtplib
from io import BytesIO
from html import escape
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs, unquote
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from report_formatter import (
    streamlit_markdown_to_html as streamlit_html_renderer,
    markdown_fragment_to_html as shared_fragment_renderer,
)
from report_postprocessor import (
    _clean_formal_source_proxy_label,
    _clean_source_label,
    _dedupe_source_mentions_in_paragraph,
    _domain_to_url,
    _has_valid_chinese_report_title,
    _is_generic_formal_title,
    _is_report_block_boundary,
    _join_field_parts,
    _looks_like_english_title,
    _match_report_field_line,
    _normalize_report_date_text,
    _operational_block_sort_key,
    _operational_blocks,
    _protect_journal_sections,
    _remove_missing_data_from_sentence,
    _restore_journal_sections,
    _short_formal_sentence,
    _strip_nested_bullet_text,
    _title_needs_repair,
    chinese_fallback_title,
    clean_internal_report_language,
    compact_report_urls,
    count_authoritative_report_items,
    count_authoritative_report_items_by_category,
    count_report_items,
    count_report_items_by_category,
    normalize_electromechanical_system_line,
    normalize_electromechanical_system_value,
    normalize_final_report_md,
    normalize_formal_report_title,
    normalize_report_source_lines,
    normalize_report_statistics_line,
    normalize_report_title_line,
    normalize_source_line,
    reduce_repeated_source_subjects,
    remove_authoritative_candidate_markers,
    remove_legacy_report_fields,
    remove_missing_data_disclaimers,
    short_url_label,
    simplify_formal_report_format,
    simplify_taipei_insight,
    strip_candidate_id_markers,
    strip_event_summary_source_lead_in,
    strip_internal_report_fields,
    strip_report_footer_lines,
    validate_authoritative_report as service_validate_authoritative_report,
    apply_final_report_footer as service_apply_final_report_footer,
    final_report_statistics_line as service_final_report_statistics_line,
    merge_operational_report_sections as service_merge_operational_report_sections,
    normalize_report_section_numbering as service_normalize_report_section_numbering,
    normalize_research_section_heading as service_normalize_research_section_heading,
    sanitize_report_text as service_sanitize_report_text,
    strip_unselected_report_sections as service_strip_unselected_report_sections,
    strip_unselected_types_from_title as service_strip_unselected_types_from_title,
)
import report_postprocessor as report_postprocess_service
from journal_service import (
    JournalServiceContext,
    _first_meta_content,
    _has_doi_text,
    _has_explicit_full_date,
    _html_unescape_clean,
    _is_formal_journal_url_or_doi,
    _journal_exclusion_stats,
    _journal_shortfall_reason,
    _journal_year,
    _jsonld_values,
    _parse_full_research_date,
    get_journal_target_count,
    score_journal_candidate,
    _journal_priority as service_journal_priority,
    _journal_safe_get as service_journal_safe_get,
    _journal_source_page_results as service_journal_source_page_results,
    _research_date_info as service_research_date_info,
    collect_journal_candidates as service_collect_journal_candidates,
    fetch_journal_page_metadata as service_fetch_journal_page_metadata,
    journal_query_source_outcomes,
)
from ddgs_search_service import (
    DDGS_ERROR_STATUSES,
    DdgsSearchContext,
    _active_query_specs,
    _basic_search_url_exclusion_reason,
    _compact_query,
    _ddgs_exception_status,
    _ddgs_timelimit_for_lookback,
    _format_ddg_block,
    _regional_query_spec_sequence,
    _search_result_date_hint,
    _standard_search_queries,
    build_ddgs_search_summary,
    ddgs_general_only_queries,
    ddgs_queries_by_outcome,
    _basic_search_date_exclusion_reason as service_basic_search_date_exclusion_reason,
    _ddgs_query_status_template as service_ddgs_query_status_template,
    _query_metadata_for as service_query_metadata_for,
    _query_with_period as service_query_with_period,
    _run_single_query as service_run_single_query,
    _search_family_from_query as service_search_family_from_query,
    _search_language_from_query as service_search_language_from_query,
    _selected_query_families as service_selected_query_families,
    build_search_queries as service_build_search_queries,
    run_duckduckgo_searches as service_run_duckduckgo_searches,
)
from rss_feed_service import (
    RssFeedContext,
    _format_items_block,
    _status_record,
    build_source_health_summary,
    _fallback_google_news_url as service_fallback_google_news_url,
    _fetch_feed as service_rss_fetch_feed,
    _items_from_parsed_feed as service_items_from_parsed_feed,
    _method_for_url as service_method_for_url,
    fetch_rss_feeds as service_fetch_rss_feeds,
)
from developer_debug_service import (
    DeveloperDebugContext,
    _debug_candidate_rows as service_debug_candidate_rows,
    _debug_strip_internal_fields as service_debug_strip_internal_fields,
    _json_safe as service_json_safe,
    build_runtime_module_fingerprint,
    build_runtime_version,
    build_developer_debug_payload as service_build_developer_debug_payload,
)
from ui_style_service import load_streamlit_css
from run_config_service import (
    DownloadFilenameContext,
    RunConfigContext,
    RunSettingsContext,
    _compact_date as service_compact_date,
    _formal_report_topic_labels as service_formal_report_topic_labels,
    build_current_run_config as service_build_current_run_config,
    build_report_download_filename as service_build_report_download_filename,
    build_run_settings,
    get_report_type_code as service_get_report_type_code,
)
from streamlit_sidebar_ui import SidebarContext, render_sidebar
from streamlit_report_ui import (
    MainDashboardContext,
    ReportDisplayContext,
    render_main_dashboard as service_render_main_dashboard,
    render_report_display,
)
from streamlit_debug_ui import DebugUiContext, render_developer_debug_ui
from report_prompt_service import (
    ReportPromptContext,
    build_report_prompt as service_build_report_prompt,
    build_selection_prompt as service_build_selection_prompt,
    format_report_candidate as service_format_report_candidate,
    format_selection_candidate as service_format_selection_candidate,
    json_loads_loose as service_json_loads_loose,
    parse_selection_response as service_parse_selection_response,
    policy_selection_rule as service_policy_selection_rule,
    research_section_heading as service_research_section_heading,
    section_number_for_index as service_section_number_for_index,
    selected_empty_section_rules as service_selected_empty_section_rules,
    selected_report_sections as service_selected_report_sections,
    selected_stats_template as service_selected_stats_template,
    truthy_report_flag as service_truthy_report_flag,
)
from pdf_exporter import (
    streamlit_markdown_to_pdf_bytes as streamlit_pdf_renderer,
    pdf_rich_text as shared_pdf_rich_text,
    _soft_wrap_long_tokens as shared_soft_wrap_long_tokens,
)
from email_service import send_streamlit_email
from config import *
import article_selector as selector_service
import report_workflow_service as workflow_service
from article_selector import build_selector_api, REPORT_SELECTION_DEBUG_DEFAULT
from article_processor import (
    _parse_pub_date, _is_recent, _source_tuple, _host_matches, _domain_from_url,
    _normalize_source_domain, _extract_site_domain_from_google_news, _is_blocked_host,
    _is_domestic_taiwan_host, _is_valid_news_url, _contains_taiwan_reference, _contains_any_term,
    _domain_hint_from_source_label, _original_source_domain, _strict_source_domain,
    _strip_source_name_noise, clean_source_name_for_ui, _is_query_proxy_source_label,
    _candidate_region_text, _region_from_domain_hints,
    _region_guess_from_candidate, _canonical_candidate_region, _normalize_title,
    _dedupe_url, _entry_source_href, _entry_pub_str, _clean_text, _shorten,
    _is_article_level_url, _effective_source_url, _clean_candidate_url, _quality_rank,
    _source_tier_rank, classify_source_quality, classify_source_tier,
    source_label_for_report, source_verb_for_report, _region_term_matches,
    _explicit_event_region_hint, _event_region_hint_from_text, guess_region_from_text,
    _candidate_date_obj, _date_from_url_path, _date_sort_key,
    _make_news_candidate as service_make_news_candidate,
    parse_rss_candidates as service_parse_rss_candidates,
    parse_ddg_candidates as service_parse_ddg_candidates,
    _dedupe_entity_tokens, _dedupe_route_line_tokens,
    _dedupe_titles_conflict_on_entities, _is_similar_title_duplicate,
    dedupe_candidates as service_dedupe_candidates,
    _extract_complete_url, _extract_complete_urls, _extract_domain_hint,
    _canonical_url_from_html, _resolve_google_news_article_url,
    _prefetch_url_for_candidate, _extract_prefetch_text, _prefetch_candidate_article,
)
from search_queries import (
    build_rss_sources, KNOWN_BAD_OFFICIAL_RSS_HOSTS, KNOWN_BAD_OFFICIAL_RSS_LABELS,
    FORMAL_SOURCE_PROXY_LABELS, REGION_NEWS_QUERIES, FAST_SOURCE_KEYWORDS,
    _source_skip_record, _source_identity, _is_known_bad_official_rss,
    _conditional_news_sources as service_conditional_news_sources,
    build_region_news_sources, build_standards_news_sources,
    select_fast_rss_sources, build_run_news_sources as service_build_run_news_sources,
)
from search_service import (
    FeedFetchError as ServiceFeedFetchError,
    google_news_search_url as service_google_news_search_url,
    google_news_site_proxy_url as service_google_news_site_proxy_url,
    create_requests_session as service_create_requests_session,
    fetch_feed as service_fetch_feed,
)
from maiagent_service import (
    call_maiagent_cloud as call_maiagent_service,
    extract_maiagent_text,
    ensure_selected_candidate_ids as service_ensure_selected_candidate_ids,
    extract_report_candidate_ids as service_extract_report_candidate_ids,
    remove_internal_candidate_markers as service_remove_internal_candidate_markers,
    validate_report_candidate_ids as service_validate_report_candidate_ids,
    build_report_retry_prompt as service_build_report_retry_prompt,
    REPORT_CANDIDATE_ID_PATTERN as SERVICE_REPORT_CANDIDATE_ID_PATTERN,
    REPORT_ESCAPED_CANDIDATE_ID_PATTERN as SERVICE_REPORT_ESCAPED_CANDIDATE_ID_PATTERN,
    INTERNAL_CANDIDATE_MARKER_PATTERN as SERVICE_INTERNAL_CANDIDATE_MARKER_PATTERN,
    ESCAPED_INTERNAL_CANDIDATE_MARKER_PATTERN as SERVICE_ESCAPED_INTERNAL_CANDIDATE_MARKER_PATTERN,
)

try:
    from ddgs import DDGS
except ModuleNotFoundError:
    DDGS = None

try:
    import feedparser
except ModuleNotFoundError:
    feedparser = None


# ══════════════════════════════════════════════════════
#  金鑰讀取
# ══════════════════════════════════════════════════════
def get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, default)


# ── 頁面設定 ──────────────────────────────────────────
st.set_page_config(
    page_title="捷運技術週報 AI 系統",
    page_icon="🚇",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(load_streamlit_css(Path(__file__).resolve().parent), unsafe_allow_html=True)


def get_app_source_hash() -> str:
    try:
        return hashlib.sha1(Path(__file__).read_bytes()).hexdigest()
    except Exception:
        return "unknown"


def clear_old_report_state() -> None:
    keys_to_clear = [
        "latest_report_md", "latest_report_html", "latest_pdf",
        "latest_debug_payload", "latest_run_config",
        "report_generated", "email_sent", "last_run_result",
        "latest_report", "latest_report_summary", "latest_report_stats",
        "latest_debug_info", "latest_source_statuses",
    ]
    for key in keys_to_clear:
        st.session_state.pop(key, None)


current_app_hash = get_app_source_hash()
previous_app_hash = st.session_state.get("_app_source_hash")
current_runtime_version = build_runtime_version()
current_runtime_fingerprint = build_runtime_module_fingerprint(current_runtime_version)
previous_runtime_fingerprint = st.session_state.get("_runtime_module_fingerprint")
if not previous_runtime_fingerprint:
    latest_debug_payload = st.session_state.get("latest_debug_payload")
    if not isinstance(latest_debug_payload, dict):
        latest_debug_payload = {}
    previous_runtime_version = (
        st.session_state.get("_runtime_version")
        or latest_debug_payload.get("run_info", {}).get("runtime_version", {})
    )
    previous_runtime_fingerprint = build_runtime_module_fingerprint(previous_runtime_version)
runtime_changed = (
    bool(previous_app_hash and previous_app_hash != current_app_hash)
    or bool(previous_runtime_fingerprint and previous_runtime_fingerprint != current_runtime_fingerprint)
)
st.session_state["_app_source_hash"] = current_app_hash
st.session_state["_runtime_module_fingerprint"] = current_runtime_fingerprint
st.session_state["_runtime_version"] = current_runtime_version
if runtime_changed:
    clear_old_report_state()
    st.session_state["_runtime_change_notice_pending"] = True
if st.session_state.pop("_runtime_change_notice_pending", False):
    st.info("偵測到新版程式，已清除上一版本報告。")

# ── 日期與常數 ──────────────────────────────────────────────
today = datetime.date.today()
DEMO_REPORT_DATE = datetime.date(2026, 7, 7)
APP_DIR = Path(__file__).resolve().parent
REPORTS_DIR = APP_DIR / "reports"


def _write_report_markdown_files(
    report_md: str,
    report_date: datetime.date,
) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = REPORTS_DIR / "latest.md"
    dated_path = REPORTS_DIR / f"report_{report_date.strftime('%Y%m%d')}.md"
    latest_path.write_text(report_md, encoding="utf-8")
    dated_path.write_text(report_md, encoding="utf-8")
    return latest_path, dated_path

PDF_FONT_CANDIDATES = [
    ("project", APP_DIR / "fonts" / "NotoSansTC-Regular.ttf"),
    ("project", APP_DIR / "fonts" / "NotoSansCJKtc-Regular.otf"),
    ("project", APP_DIR / "fonts" / "NotoSansCJK-Regular.ttc"),
    ("linux_noto", Path("/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf")),
    ("linux_noto", Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")),
    ("linux_noto", Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc")),
    ("linux_noto", Path("/usr/share/fonts/truetype/noto/NotoSansTC-Regular.ttf")),
    ("linux_wqy", Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")),
    ("linux_wqy", Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc")),
    ("linux_fallback", Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf")),
    ("linux_fallback", Path("/usr/share/fonts/truetype/arphic/uming.ttc")),
    ("windows", Path(r"C:\Windows\Fonts\msjh.ttc")),
    ("windows", Path(r"C:\Windows\Fonts\msjh.ttf")),
    ("windows", Path(r"C:\Windows\Fonts\msjhl.ttc")),
    ("windows", Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf")),
    ("windows", Path(r"C:\Windows\Fonts\msyh.ttc")),
]
LAST_PDF_FONT_INFO: dict[str, str] = {}
LAST_PDF_ERROR = ""


class PdfFontUnavailableError(RuntimeError):
    pass


def iter_pdf_font_candidates():
    """Yield configured and discovered CJK fonts in deployment priority order."""
    seen: set[str] = set()

    def _yield(source: str, path: Path):
        key = os.path.normcase(os.path.abspath(str(path)))
        if key not in seen:
            seen.add(key)
            return source, path
        return None

    configured_path = os.environ.get("METRO_REPORT_PDF_FONT_PATH", "").strip()
    if configured_path:
        candidate = _yield("environment", Path(configured_path))
        if candidate:
            yield candidate

    for source, path in PDF_FONT_CANDIDATES:
        if source != "project":
            continue
        candidate = _yield(source, path)
        if candidate:
            yield candidate

    project_fonts_dir = APP_DIR / "fonts"
    if project_fonts_dir.is_dir():
        for pattern in ("*.ttf", "*.ttc"):
            for path in sorted(project_fonts_dir.rglob(pattern)):
                candidate = _yield("project", path)
                if candidate:
                    yield candidate

    for source, path in PDF_FONT_CANDIDATES:
        if source == "project":
            continue
        candidate = _yield(source, path)
        if candidate:
            yield candidate

    discovery_specs = (
        ("linux_noto", Path("/usr/share/fonts"), "NotoSans*TC*.ttf"),
        ("linux_wqy", Path("/usr/share/fonts"), "wqy-*.ttc"),
        ("linux_fallback", Path("/usr/share/fonts"), "*Fallback*.ttf"),
    )
    for source, root, pattern in discovery_specs:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob(pattern)):
            candidate = _yield(source, path)
            if candidate:
                yield candidate


# ── 金鑰狀態 ──────────────────────────────────────────
# AI 報告產製改用 MaiAgent 雲端 API。
# 請在 Streamlit Cloud Secrets 或環境變數設定：
# MAIAGENT_API_KEY、MAIAGENT_CHATBOT_ID、MAIAGENT_API_BASE
maiagent_api_key = get_secret("MAIAGENT_API_KEY")
maiagent_chatbot_id = get_secret("MAIAGENT_CHATBOT_ID")
maiagent_api_base = get_secret("MAIAGENT_API_BASE", "https://api.maiagent.ai")
model_choice = "MaiAgent 雲端 API"

gmail_user = get_secret("GMAIL_USER")
gmail_pass = get_secret("GMAIL_APP_PASS")

sidebar_selection = render_sidebar(
    SidebarContext(
        default_recipients=get_secret("DEFAULT_RECIPIENTS", ""),
        default_selected_types=STREAMLIT_DEFAULT_SELECTED_TYPES,
        advanced_types=BACKEND_CATEGORY_TYPES,
        normal_lookback_options=NORMAL_LOOKBACK_OPTIONS,
        advanced_lookback_options=ADVANCED_LOOKBACK_OPTIONS,
        report_period_labels=REPORT_PERIOD_LABELS,
        long_term_target_labels=LONG_TERM_TARGET_LABELS,
        default_regions=DEFAULT_REGIONS,
        advanced_regions=ADVANCED_REGIONS,
        standards_watchlist=STANDARDS_WATCHLIST,
        get_research_supplement_lookback_days=get_research_supplement_lookback_days,
        default_news_scope="both",
    )
)
recipient_input = sidebar_selection.recipient_input
lookback_days = sidebar_selection.lookback_days
selected_types = sidebar_selection.selected_types
standards_enabled = sidebar_selection.standards_enabled
standard_count = sidebar_selection.standard_count
news_scope = sidebar_selection.news_scope
scope_mode = sidebar_selection.scope_mode
selected_regions = sidebar_selection.selected_regions
long_term_mode = sidebar_selection.long_term_mode
include_research_supplement = sidebar_selection.include_research_supplement
show_developer_info = sidebar_selection.show_developer_info
demo_cache_mode = sidebar_selection.demo_cache_mode

run_settings = build_run_settings(
    RunSettingsContext(
        today=today,
        lookback_days=lookback_days,
        selected_types=selected_types,
        scope_mode=scope_mode,
        selected_regions=selected_regions,
        standards_enabled=standards_enabled,
        include_research_supplement=include_research_supplement,
        demo_cache_mode_enabled=bool(st.session_state.get("demo_cache_mode", False)),
        current_app_hash=current_app_hash,
        report_period_labels=REPORT_PERIOD_LABELS,
        long_term_target_labels=LONG_TERM_TARGET_LABELS,
        report_target_by_days=REPORT_TARGET_BY_DAYS,
        research_supplement_allowed_for_report=research_supplement_allowed_for_report,
        get_research_supplement_lookback_days=get_research_supplement_lookback_days,
        news_scope=news_scope,
    )
)
week_start = run_settings.week_start
date_range = run_settings.date_range
lookback_int = run_settings.lookback_int
include_research_supplement = run_settings.include_research_supplement
fast_mode_enabled = run_settings.fast_mode_enabled
demo_cache_mode_enabled = run_settings.demo_cache_mode_enabled
report_period_label = run_settings.report_period_label
research_supplement_lookback_days = run_settings.research_supplement_lookback_days
research_supplement_start_date = run_settings.research_supplement_start_date
research_supplement_period_label = run_settings.research_supplement_period_label
target_is_enforced = run_settings.target_is_enforced
min_report_items = run_settings.min_report_items
report_target_display = run_settings.report_target_display
report_output_requirement = run_settings.report_output_requirement
report_quantity_instruction = run_settings.report_quantity_instruction
report_shortfall_summary_line = run_settings.report_shortfall_summary_line
selected_report_topic = run_settings.selected_report_topic
report_title = run_settings.report_title
is_global_scope = run_settings.is_global_scope
active_regions = run_settings.active_regions
report_scope_label = run_settings.report_scope_label


def _workflow_config() -> workflow_service.WorkflowConfig:
    return workflow_service.WorkflowConfig(
        today=today,
        lookback_days=lookback_int,
        selected_types=list(selected_types),
        active_regions=list(active_regions),
        is_global_scope=is_global_scope,
        standards_enabled=standards_enabled,
        include_research_supplement=include_research_supplement,
        fast_mode_enabled=fast_mode_enabled,
        date_range=date_range,
        report_title=report_title,
        report_scope_label=report_scope_label,
        report_period_label=report_period_label,
        news_scope=news_scope,
        research_supplement_period_label=research_supplement_period_label,
        research_supplement_start_date=research_supplement_start_date,
    )


def _formal_report_topic_labels(report_types: list[str]) -> list[str]:
    return service_formal_report_topic_labels(report_types)


def _run_config_context() -> RunConfigContext:
    return RunConfigContext(
        today=today,
        week_start=week_start,
        lookback_int=lookback_int,
        date_range=date_range,
        report_period_label=report_period_label,
        report_title=report_title,
        selected_types=selected_types,
        scope_mode=scope_mode,
        is_global_scope=is_global_scope,
        active_regions=active_regions,
        report_scope_label=report_scope_label,
        standards_enabled=standards_enabled,
        include_research_supplement=include_research_supplement,
        research_supplement_lookback_days=research_supplement_lookback_days,
        research_supplement_start_date=research_supplement_start_date,
        fast_mode_enabled=fast_mode_enabled,
        demo_cache_mode_enabled=demo_cache_mode_enabled,
        current_app_hash=current_app_hash,
        news_scope=news_scope,
    )


def build_current_run_config() -> dict:
    return service_build_current_run_config(_run_config_context())


current_run_config = build_current_run_config()


def get_report_type_code(report_label: str, lookback_days: int) -> str:
    return service_get_report_type_code(report_label, lookback_days)


def _compact_date(value, fallback: datetime.date | None = None) -> str:
    return service_compact_date(value, fallback, today=today)


def build_report_download_filename(
    prefix: str,
    extension: str,
    run_config: dict | None = None,
) -> str:
    return service_build_report_download_filename(
        prefix,
        extension,
        run_config,
        context=DownloadFilenameContext(
            current_run_config=current_run_config,
            lookback_int=lookback_int,
            today=today,
            report_period_label=report_period_label,
        ),
    )


def google_news_search_url(query: str, hl: str = "en-US", gl: str = "US", ceid_lang: str = "en") -> str:
    return service_google_news_search_url(query, hl=hl, gl=gl, ceid_lang=ceid_lang)


def google_news_site_proxy_url(domain: str, days: int, keywords: str = TRANSIT_NEWS_TERMS, hl: str = "en-US", gl: str = "US", ceid_lang: str = "en") -> str:
    return service_google_news_site_proxy_url(domain, days, keywords, hl=hl, gl=gl, ceid_lang=ceid_lang)


RSS_SOURCES = build_rss_sources(int(lookback_days))


def _conditional_news_sources(fast_mode: bool) -> tuple[list[tuple[str, str]], list[dict]]:
    return service_conditional_news_sources(
        fast_mode, int(lookback_days), lookback_int, standards_enabled,
    )


def build_run_news_sources(
    region_sources: list[tuple[str, str]], standards_sources: list[tuple[str, str]],
    fast_mode: bool, return_skipped: bool = False,
):
    return service_build_run_news_sources(
        region_sources, standards_sources, fast_mode, rss_sources=RSS_SOURCES,
        lookback_days=int(lookback_days), lookback_int=lookback_int,
        standards_enabled=standards_enabled, return_skipped=return_skipped,
    )




initial_region_sources = build_region_news_sources(active_regions, int(lookback_days), fast_mode=fast_mode_enabled)
initial_standard_sources = build_standards_news_sources(int(lookback_days)) if standards_enabled else []
initial_combined_sources = build_run_news_sources(initial_region_sources, initial_standard_sources, fast_mode_enabled)
generate_btn, send_after_generate, progress_placeholder, status_placeholder = (
    service_render_main_dashboard(
        source_count=len(initial_combined_sources),
        standards_count=sum(len(v) for v in STANDARDS_WATCHLIST.values()),
        context=MainDashboardContext(
            is_global_scope=is_global_scope,
            selected_regions=selected_regions,
            report_period_label=report_period_label,
            today=today,
            week_start=week_start,
            scope_mode=report_scope_label,
            demo_cache_mode_enabled=demo_cache_mode_enabled,
        ),
    )
)


def _make_news_candidate(title: str, date: str, source: str, url: str, snippet: str, query: str, region: str, source_type: str, source_href: str = "") -> dict:
    return service_make_news_candidate(
        title, date, source, url, snippet, query, region, source_type, source_href,
        query_metadata=LAST_DDGS_QUERY_METADATA.get(query or "", {}) or {},
        search_family_resolver=_search_family_from_query,
        search_language_resolver=_search_language_from_query,
    )


def parse_rss_candidates(raw_rss: str) -> list[dict]:
    return service_parse_rss_candidates(raw_rss, _make_news_candidate)


def parse_ddg_candidates(raw_ddg: str) -> list[dict]:
    return service_parse_ddg_candidates(raw_ddg, _make_news_candidate)


def dedupe_candidates(candidates: list[dict]) -> tuple[list[dict], dict[str, int]]:
    return service_dedupe_candidates(candidates, int(lookback_days))


FeedFetchError = ServiceFeedFetchError


create_requests_session = service_create_requests_session


def _rss_feed_context(status_text=None) -> RssFeedContext:
    return RssFeedContext(
        lookback_days=lookback_days,
        feedparser_module=feedparser,
        http_session_factory=create_requests_session,
        fetch_feed_callback=service_fetch_feed,
        fallback_url_builder=_fallback_google_news_url,
        url_safety_check=_is_valid_news_url,
        known_bad_source_checker=_is_known_bad_official_rss,
        parse_pub_date=_parse_pub_date,
        is_recent=_is_recent,
        entry_pub_str=_entry_pub_str,
        entry_source_href=_entry_source_href,
        contains_taiwan_reference=_contains_taiwan_reference,
        is_standards_source=_is_standards_source,
        is_standard_update_candidate=_is_standard_update_candidate,
        is_urban_rail_candidate=_is_urban_rail_candidate,
        is_tech_news_only_mode=_is_tech_news_only_mode,
        is_technical_news_candidate=_is_technical_news_candidate,
        normalize_title=_normalize_title,
        dedupe_url=_dedupe_url,
        domain_from_url=_domain_from_url,
        status_callback=status_text.text if status_text else None,
        now_provider=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


def _fallback_google_news_url(source_url: str) -> str | None:
    return service_fallback_google_news_url(
        source_url,
        lookback_days=int(lookback_days),
        google_news_fallback_builder=google_news_site_proxy_url,
    )


def _fetch_feed(session: requests.Session, url: str):
    return service_rss_fetch_feed(session, url, context=_rss_feed_context())


def _items_from_parsed_feed(
    parsed_feed,
    cutoff: datetime.datetime,
    seen_titles: set[str],
    seen_urls: set[str],
    source_name: str = "",
) -> tuple[list[dict], int, int, int, int]:
    return service_items_from_parsed_feed(
        parsed_feed,
        cutoff,
        seen_titles,
        seen_urls,
        source_name,
        context=_rss_feed_context(),
    )


def _method_for_url(url: str) -> str:
    return service_method_for_url(url, domain_from_url=_domain_from_url)


def fetch_rss_feeds(
    sources: list[tuple[str, str]] | None = None,
    status_text=None,
    return_status: bool = False,
) -> str | tuple[str, list[dict]]:
    """通用 RSS/Atom 抓取函式，使用 feedparser + requests retry/backoff。"""
    if sources is None:
        sources = RSS_SOURCES
    return service_fetch_rss_feeds(
        sources,
        context=_rss_feed_context(status_text),
        return_status=return_status,
    )


def _ddgs_search_context(
    progress_bar=None,
    status_text=None,
    *,
    query_metadata: dict[str, dict] | None = None,
) -> DdgsSearchContext:
    return DdgsSearchContext(
        selected_types=selected_types,
        active_regions=active_regions,
        lookback_days=lookback_days,
        lookback_int=lookback_int,
        is_global_scope=is_global_scope,
        today=today,
        news_scope=news_scope,
        ddgs_client_factory=DDGS,
        query_metadata=LAST_DDGS_QUERY_METADATA if query_metadata is None else query_metadata,
        progress_callback=progress_bar.progress if progress_bar else None,
        status_callback=status_text.text if status_text else None,
        perf_counter=time.perf_counter,
        sleep=time.sleep,
        random_uniform=random.uniform,
    )


def _search_language_from_query(query: str) -> str:
    return service_search_language_from_query(
        query,
        query_metadata=LAST_DDGS_QUERY_METADATA,
    )


def _search_family_from_query(query: str) -> str:
    return service_search_family_from_query(
        query,
        query_metadata=LAST_DDGS_QUERY_METADATA,
    )


def _query_with_period(query: str) -> str:
    return service_query_with_period(query, context=_ddgs_search_context())


def _selected_query_families() -> list[str]:
    return service_selected_query_families(context=_ddgs_search_context())


def _query_metadata_for(query: str) -> dict:
    return service_query_metadata_for(query, context=_ddgs_search_context())


def build_search_queries() -> tuple[list[str], set[int]]:
    global LAST_DDGS_QUERY_METADATA
    query_metadata: dict[str, dict] = {}
    result = service_build_search_queries(
        context=_ddgs_search_context(query_metadata=query_metadata),
        include_forward_technology="技術新知" in selected_types,
    )
    LAST_DDGS_QUERY_METADATA = query_metadata
    return result


def _ddgs_query_status_template(query: str, news_timelimit: str) -> dict:
    return service_ddgs_query_status_template(
        query,
        news_timelimit,
        context=_ddgs_search_context(),
    )


def _basic_search_date_exclusion_reason(date_text: str) -> str:
    return service_basic_search_date_exclusion_reason(
        date_text,
        context=_ddgs_search_context(),
    )


def _run_single_query(
    i: int,
    query: str,
    use_news: bool,
    news_timelimit: str,
) -> tuple[int, str, str, list[dict], str, dict]:
    return service_run_single_query(
        i,
        query,
        use_news,
        news_timelimit,
        context=_ddgs_search_context(),
    )


def run_duckduckgo_searches(progress_bar=None, status_text=None) -> str:
    """Execute the planned DDGS queries and retain per-query developer diagnostics."""
    global LAST_DDGS_QUERY_STATUSES, LAST_DDGS_SEARCH_SUMMARY
    LAST_DDGS_QUERY_STATUSES = []
    LAST_DDGS_SEARCH_SUMMARY = {}

    search_queries: list[str] = []
    news_query_indices: set[int] = set()
    if selected_types:
        search_queries, news_query_indices = build_search_queries()

    result_text, query_statuses, search_summary = service_run_duckduckgo_searches(
        context=_ddgs_search_context(progress_bar, status_text),
        search_queries=search_queries,
        news_query_indices=news_query_indices,
    )
    LAST_DDGS_QUERY_STATUSES = query_statuses
    LAST_DDGS_SEARCH_SUMMARY = search_summary
    return result_text


def build_pipeline_debug_stats(
    raw_candidates: list[dict],
    deduped_candidates: list[dict],
    filtered_candidates: list[dict],
    excluded_candidates: list[dict],
    prefetch_stats: dict | None = None,
) -> dict:
    def _count_by(items: list[dict], key: str) -> dict:
        counts: dict[str, int] = {}
        for item in items or []:
            value = item.get(key, "") or "未標記"
            if isinstance(value, dict):
                for sub_key, enabled in value.items():
                    if enabled:
                        counts[sub_key] = counts.get(sub_key, 0) + 1
            else:
                counts[str(value)] = counts.get(str(value), 0) + 1
        return counts

    def _annual_bucket(item: dict) -> str:
        explicit = str(item.get("date_bucket", "") or "").strip()
        if explicit:
            return explicit
        date_value = _candidate_date_obj(item.get("date", ""))
        if not date_value:
            return ""
        return f"{date_value.year:04d}-Q{((date_value.month - 1) // 3) + 1}"

    def _quality_count(items: list[dict], key: str) -> dict[str, int]:
        return _count_by(items, key)

    category_gate_pass_counts: dict[str, int] = {}
    for item in filtered_candidates or []:
        for gate, enabled in (item.get("category_gates") or {}).items():
            if enabled:
                category_gate_pass_counts[gate] = category_gate_pass_counts.get(gate, 0) + 1
    gate_pass_count = sum(1 for item in filtered_candidates or [] if any((item.get("category_gates") or {}).values()))
    query_count_by_family = (LAST_DDGS_SEARCH_SUMMARY or {}).get("query_count_by_family", {})
    if not query_count_by_family:
        query_count_by_family = {
            family: sum(1 for status in LAST_DDGS_QUERY_STATUSES if status.get("search_family") == family)
            for family in ("policy", "dispute", "service_opening")
        }
    policy_raw_candidates = [
        item for item in raw_candidates or [] if item.get("search_family") == "policy"
    ]
    dispute_raw_candidates = [
        item for item in raw_candidates or [] if item.get("search_family") == "dispute"
    ]
    service_opening_raw_candidates = [
        item for item in raw_candidates or [] if item.get("search_family") == "service_opening"
    ]
    gate_failure_reason_stats = {"policy": {}, "dispute": {}, "service_opening": {}}
    for item in filtered_candidates or []:
        gate_payload = item.get("category_gates") or {}
        gate_reasons = item.get("category_gate_reasons") or {}
        for category, gate_name in (
            ("policy", "operational_policy"),
            ("dispute", "operational_dispute"),
            ("service_opening", "service_opening"),
        ):
            if gate_payload.get(gate_name):
                continue
            reason = gate_reasons.get(gate_name) or "未通過該分類 gate"
            gate_failure_reason_stats[category][reason] = gate_failure_reason_stats[category].get(reason, 0) + 1
    category_reclassification_records = [
        item.get("category_reclassification")
        for item in (filtered_candidates or []) + (excluded_candidates or [])
        if item.get("category_reclassification")
    ]
    region_resolution_method_counts: dict[str, int] = {}
    for item in (filtered_candidates or []) + (excluded_candidates or []):
        method = item.get("region_resolution_method") or "未記錄"
        region_resolution_method_counts[method] = region_resolution_method_counts.get(method, 0) + 1
    raw_candidate_count_by_family = _count_by(raw_candidates, "search_family")
    search_summary = LAST_DDGS_SEARCH_SUMMARY or {}
    forward_raw_candidates = [
        item for item in raw_candidates or []
        if item.get("search_family") == "forward_technology"
    ]
    forward_gate_pass_count = sum(
        1 for item in filtered_candidates or []
        if (item.get("category_gates") or {}).get("forward_technology")
        or item.get("passes_forward_technology_gate") is True
    )
    forward_evaluated_candidates = [
        item
        for item in (filtered_candidates or []) + (excluded_candidates or [])
        if item.get("search_family") == "forward_technology"
    ]
    track_b_exclusion_reason_counts: dict[str, int] = {}
    for item in forward_evaluated_candidates:
        for reason in item.get("track_b_failure_reasons", []) or []:
            track_b_exclusion_reason_counts[reason] = track_b_exclusion_reason_counts.get(reason, 0) + 1
    annual_raw_by_bucket: dict[str, int] = {}
    for item in raw_candidates or []:
        bucket = _annual_bucket(item)
        if bucket:
            annual_raw_by_bucket[bucket] = annual_raw_by_bucket.get(bucket, 0) + 1
    annual_gate_pass_by_bucket: dict[str, int] = {}
    for item in filtered_candidates or []:
        bucket = _annual_bucket(item)
        if bucket and any((item.get("category_gates") or {}).values()):
            annual_gate_pass_by_bucket[bucket] = annual_gate_pass_by_bucket.get(bucket, 0) + 1
    final_source_tier_counts = _count_by(filtered_candidates, "source_tier")
    official_count = final_source_tier_counts.get("A_official", 0)
    official_ratio = round(official_count / len(filtered_candidates), 4) if filtered_candidates else 0.0
    evidence_strength_counts = _quality_count(filtered_candidates, "evidence_strength")
    technology_maturity_counts = _quality_count(filtered_candidates, "technology_maturity")
    event_importance_counts = _quality_count(filtered_candidates, "event_importance")
    innovation_type_counts = _quality_count(filtered_candidates, "innovation_type")
    return {
        "pipeline_counts": {
            "raw": len(raw_candidates or []),
            "dedup": len(deduped_candidates or []),
            "filtered": len(filtered_candidates or []),
            "gate_pass": gate_pass_count,
            "A": sum(1 for item in filtered_candidates or [] if item.get("candidate_level") == "A"),
            "B": sum(1 for item in filtered_candidates or [] if item.get("candidate_level") == "B"),
            "selected": 0,
        },
        "prefetch_stats": prefetch_stats or {},
        "pipeline_stages": {
            "raw": len(raw_candidates or []),
            "dedup": len(deduped_candidates or []),
            "filtered": len(filtered_candidates or []),
            "gate_pass": gate_pass_count,
            "rescue_candidate": int((prefetch_stats or {}).get("rescue_candidate_count", 0) or 0),
            "rescue_enriched": int((prefetch_stats or {}).get("rescue_enrichment_success_count", 0) or 0),
            "selected": 0,
            "model": len(filtered_candidates or []),
            "final": 0,
        },
        "rescue_candidate_count": int((prefetch_stats or {}).get("rescue_candidate_count", 0) or 0),
        "rescue_enrichment_attempted_count": int((prefetch_stats or {}).get("rescue_enrichment_attempted_count", 0) or 0),
        "rescue_enrichment_success_count": int((prefetch_stats or {}).get("rescue_enrichment_success_count", 0) or 0),
        "top_excluded_valuable_candidates": build_top_excluded_valuable_candidates(excluded_candidates, 20),
        "page_type_exclusion_counts": _count_by(excluded_candidates, "page_type"),
        "no_category_gate_count": sum(1 for item in excluded_candidates or [] if item.get("final_exclude_reason") == "no_category_gate" or item.get("exclude_reason") == "no_category_gate"),
        "out_of_range_excluded_count": sum(
            1 for item in excluded_candidates or []
            if item.get("date_validation") in {"out_of_range_old", "future_date"}
        ),
        "category_gate_pass_counts": category_gate_pass_counts,
        "category_reclassification_records": category_reclassification_records,
        "region_resolution_method_counts": region_resolution_method_counts,
        "A_candidate_count": sum(1 for item in filtered_candidates or [] if item.get("candidate_level") == "A"),
        "B_candidate_count": sum(1 for item in filtered_candidates or [] if item.get("candidate_level") == "B"),
        "C_candidate_count": sum(1 for item in filtered_candidates or [] if item.get("candidate_level") == "C"),
        "source_tier_counts": _count_by(filtered_candidates, "source_tier"),
        "multilingual_candidate_counts": _count_by(
            [item for item in raw_candidates or [] if item.get("search_language", "en") != "en"],
            "search_language",
        ),
        "normalized_domain_change_count": sum(
            1 for item in raw_candidates or []
            if item.get("source_domain_raw")
            and item.get("source_domain_normalized")
            and _normalize_source_domain(item.get("source_domain_raw", "")) != item.get("source_domain_normalized")
        ),
        "incident_search_raw_count": sum(
            1 for item in raw_candidates or []
            if item.get("search_family") in {"major_accident", "official_investigation"}
            or _contains_any_term(
                _candidate_selection_text(item),
                selector_service.ACCIDENT_SIGNAL_TERMS + selector_service.SAFETY_INCIDENT_DETAIL_TERMS,
            )
        ),
        "incident_gate_pass_count": sum(
            1 for item in filtered_candidates or []
            if (item.get("category_gates") or {}).get("major_accident")
        ),
        "policy_query_count": int(query_count_by_family.get("policy", 0) or 0),
        "dispute_query_count": int(query_count_by_family.get("dispute", 0) or 0),
        "policy_raw_candidate_count": len(policy_raw_candidates),
        "dispute_raw_candidate_count": len(dispute_raw_candidates),
        "policy_raw_candidates": [build_candidate_card(item) for item in policy_raw_candidates],
        "dispute_raw_candidates": [build_candidate_card(item) for item in dispute_raw_candidates],
        "service_opening_query_count": int(query_count_by_family.get("service_opening", 0) or 0),
        "service_opening_raw_candidate_count": len(service_opening_raw_candidates),
        "service_opening_raw_candidates": [build_candidate_card(item) for item in service_opening_raw_candidates],
        "policy_gate_pass_count": sum(
            1 for item in filtered_candidates or []
            if (item.get("category_gates") or {}).get("operational_policy")
        ),
        "dispute_gate_pass_count": sum(
            1 for item in filtered_candidates or []
            if (item.get("category_gates") or {}).get("operational_dispute")
        ),
        "service_opening_gate_pass_count": sum(
            1 for item in filtered_candidates or []
            if (item.get("category_gates") or {}).get("service_opening")
        ),
        "gate_failure_reason_stats": gate_failure_reason_stats,
        "operational_topic_selected_count": 0,
        "planned_query_count_by_family": search_summary.get("planned_query_count_by_family", {}),
        "executed_query_count_by_family": search_summary.get("executed_query_count_by_family", {}),
        "raw_candidate_count_by_family": raw_candidate_count_by_family,
        "gate_pass_count_by_category": category_gate_pass_counts,
        "forward_technology_query_count": search_summary.get("forward_technology_query_count", 0),
        "forward_technology_fallback_query_count": search_summary.get("forward_technology_fallback_query_count", 0),
        "forward_technology_raw_count": len(forward_raw_candidates),
        "forward_technology_gate_pass_count": forward_gate_pass_count,
        "forward_technology_selected_count": 0,
        "track_a_gate_pass_count": sum(
            1 for item in forward_evaluated_candidates if item.get("track_a_gate_pass") is True
        ),
        "track_b_gate_pass_count": sum(
            1 for item in forward_evaluated_candidates if item.get("track_b_gate_pass") is True
        ),
        "track_a_selected_count": 0,
        "track_b_selected_count": 0,
        "track_b_exclusion_reason_counts": track_b_exclusion_reason_counts,
        "track_b_rescue_candidate_count": sum(1 for item in forward_evaluated_candidates if item.get("rescue_candidate")),
        "track_b_enrichment_attempted_count": sum(1 for item in forward_evaluated_candidates if item.get("rescue_enrichment_attempted")),
        "track_b_enrichment_success_count": sum(1 for item in forward_evaluated_candidates if item.get("rescue_enrichment_success")),
        "track_b_gate_pass_after_enrichment_count": sum(
            1 for item in forward_evaluated_candidates
            if item.get("rescue_enrichment_success") and item.get("track_b_gate_pass") is True
        ),
        "annual_raw_by_bucket": annual_raw_by_bucket,
        "annual_gate_pass_by_bucket": annual_gate_pass_by_bucket,
        "annual_selected_by_bucket": {},
        "annual_coverage_target": 12,
        "final_source_tier_counts": final_source_tier_counts,
        "official_source_ratio": official_ratio,
        "evidence_strength_counts": evidence_strength_counts,
        "technology_maturity_counts": technology_maturity_counts,
        "event_importance_counts": event_importance_counts,
        "innovation_type_counts": innovation_type_counts,
        "quality_acceptance": {
            "pipeline_stage_contract": "PASS",
            "source_attribution": "PASS" if filtered_candidates else "WARN",
            "evidence_strength": "PASS" if evidence_strength_counts.get("high", 0) or evidence_strength_counts.get("medium", 0) else "WARN",
            "annual_coverage": "PENDING",
        },
        "forward_technology_material_candidate_count": sum(
            1 for item in forward_raw_candidates
            if item.get("innovation_level") in {"A", "B"}
            or item.get("novelty_evidence")
            or item.get("validation_evidence")
            or item.get("benefit_evidence")
        ),
    }


def _workflow_dependencies(*, prefetch_enabled: bool) -> workflow_service.WorkflowDependencies:
    return workflow_service.WorkflowDependencies(
        ddgs_client_factory=DDGS,
        feedparser_module=feedparser,
        http_session_factory=create_requests_session,
        prefetch_enabled=prefetch_enabled,
        debug_stats_builder=build_pipeline_debug_stats if prefetch_enabled else None,
        query_metadata=dict(globals().get("LAST_DDGS_QUERY_METADATA", {}) or {}),
    )


_selector_api = build_selector_api(
    selected_types=selected_types, active_regions=active_regions,
    lookback_days=lookback_days, lookback_int=lookback_int,
    fast_mode_enabled=fast_mode_enabled, is_global_scope=is_global_scope, today=today,
    news_scope=news_scope,
    _search_family_from_query=_search_family_from_query,
    _search_language_from_query=_search_language_from_query,
    create_requests_session=create_requests_session,
    _profile_timing_add=lambda timings, key, elapsed: timings.__setitem__(key, round(timings.get(key, 0.0) + elapsed, 4)) if timings is not None else None,
)
_has_high_value_operational_detail = _selector_api["_has_high_value_operational_detail"]
_has_clear_urban_rail_context = _selector_api["_has_clear_urban_rail_context"]
_is_airport_people_mover_only_text = _selector_api["_is_airport_people_mover_only_text"]
_trusted_source_title_technical_signal = _selector_api["_trusted_source_title_technical_signal"]
_candidate_has_high_value_operational_detail = _selector_api["_candidate_has_high_value_operational_detail"]
_is_low_value_service_notice_text = _selector_api["_is_low_value_service_notice_text"]
hard_low_value_candidate_reason = _selector_api["hard_low_value_candidate_reason"]
_wordish_count = _selector_api["_wordish_count"]
_information_quality_issue = _selector_api["_information_quality_issue"]
_is_standards_source = _selector_api["_is_standards_source"]
_is_standard_update_query = _selector_api["_is_standard_update_query"]
_is_standard_update_candidate = _selector_api["_is_standard_update_candidate"]
_is_allowed_international_candidate = _selector_api["_is_allowed_international_candidate"]
_is_urban_rail_candidate = _selector_api["_is_urban_rail_candidate"]
_is_tech_news_only_mode = _selector_api["_is_tech_news_only_mode"]
_is_technical_news_candidate = _selector_api["_is_technical_news_candidate"]
_compute_candidate_page_type = _selector_api["_compute_candidate_page_type"]
_candidate_page_type = _selector_api["_candidate_page_type"]
_prefetch_limit_for_period = _selector_api["_prefetch_limit_for_period"]
_candidate_prefetch_signal = _selector_api["_candidate_prefetch_signal"]
_is_short_snippet_rescue_candidate = _selector_api["_is_short_snippet_rescue_candidate"]
_is_procurement_rescue_candidate = _selector_api["_is_procurement_rescue_candidate"]
_is_pre_gate_rescue_candidate = _selector_api["_is_pre_gate_rescue_candidate"]
build_cross_period_coverage_debug = _selector_api["build_cross_period_coverage_debug"]
prefetch_candidates_before_filter = _selector_api["prefetch_candidates_before_filter"]
preliminary_filter_candidate = _selector_api["preliminary_filter_candidate"]
_excluded_candidate_value_reasons = _selector_api["_excluded_candidate_value_reasons"]
build_top_excluded_valuable_candidates = _selector_api["build_top_excluded_valuable_candidates"]
_canonical_tags_from_text = _selector_api["_canonical_tags_from_text"]
_candidate_selection_text = _selector_api["_candidate_selection_text"]
_candidate_analysis_fingerprint = _selector_api["_candidate_analysis_fingerprint"]
_candidate_analysis_cache = _selector_api["_candidate_analysis_cache"]
_cached_candidate_bool = _selector_api["_cached_candidate_bool"]
_candidate_urban_rail_gate = _selector_api["_candidate_urban_rail_gate"]
_compute_technical_system_gate = _selector_api["_compute_technical_system_gate"]
_technical_system_gate = _selector_api["_technical_system_gate"]
_compute_technical_action_gate = _selector_api["_compute_technical_action_gate"]
_technical_action_gate = _selector_api["_technical_action_gate"]
_compute_passes_technical_triad = _selector_api["_compute_passes_technical_triad"]
_passes_technical_triad = _selector_api["_passes_technical_triad"]
_candidate_event_fragments = _selector_api["_candidate_event_fragments"]
_fragment_has_urban_rail_context = _selector_api["_fragment_has_urban_rail_context"]
_is_single_person_rail_incident = _selector_api["_is_single_person_rail_incident"]
_has_single_person_incident_exception = _selector_api["_has_single_person_incident_exception"]
_compute_passes_major_accident_gate = _selector_api["_compute_passes_major_accident_gate"]
_passes_major_accident_gate = _selector_api["_passes_major_accident_gate"]
_compute_passes_operational_dispute_gate = _selector_api["_compute_passes_operational_dispute_gate"]
_passes_operational_dispute_gate = _selector_api["_passes_operational_dispute_gate"]
_compute_passes_operational_dispute_primary_gate = _selector_api.get(
    "_compute_passes_operational_dispute_primary_gate",
    _compute_passes_operational_dispute_gate,
)
_passes_operational_dispute_primary_gate = _selector_api.get(
    "_passes_operational_dispute_primary_gate",
    _passes_operational_dispute_gate,
)
_compute_passes_operational_dispute_secondary_gate = _selector_api.get(
    "_compute_passes_operational_dispute_secondary_gate",
    lambda candidate: False,
)
_passes_operational_dispute_secondary_gate = _selector_api.get(
    "_passes_operational_dispute_secondary_gate",
    lambda candidate: False,
)
_is_dispute_dominant = _selector_api.get(
    "_is_dispute_dominant",
    _passes_operational_dispute_gate,
)
_is_policy_dominant = _selector_api.get(
    "_is_policy_dominant",
    lambda candidate: False,
)
_is_short_term_service_notice = _selector_api["_is_short_term_service_notice"]
_compute_passes_high_value_policy_gate = _selector_api["_compute_passes_high_value_policy_gate"]
_passes_high_value_policy_gate = _selector_api["_passes_high_value_policy_gate"]
_compute_service_opening_gate = _selector_api["_compute_service_opening_gate"]
_compute_passes_service_opening_gate = _selector_api["_compute_passes_service_opening_gate"]
_passes_service_opening_gate = _selector_api["_passes_service_opening_gate"]
evaluate_category_gates = _selector_api["evaluate_category_gates"]
_candidate_level = _selector_api["_candidate_level"]
_is_accident_signal_text = _selector_api["_is_accident_signal_text"]
_has_strong_technical_detail_text = _selector_api["_has_strong_technical_detail_text"]
_has_explicit_technical_system_detail = _selector_api["_has_explicit_technical_system_detail"]
_has_good_report_signal = _selector_api["_has_good_report_signal"]
_has_low_value_official_notice = _selector_api["_has_low_value_official_notice"]
_has_procurement_list_notice = _selector_api["_has_procurement_list_notice"]
_is_financial_market_candidate = _selector_api["_is_financial_market_candidate"]
_is_low_value_ceremonial_candidate = _selector_api["_is_low_value_ceremonial_candidate"]
_is_security_or_crime_candidate = _selector_api["_is_security_or_crime_candidate"]
_has_major_security_rail_impact = _selector_api["_has_major_security_rail_impact"]
_has_core_metro_technical_content = _selector_api["_has_core_metro_technical_content"]
_has_general_rail_exclusion = _selector_api["_has_general_rail_exclusion"]
_has_substantive_detail_for_low_value_notice = _selector_api["_has_substantive_detail_for_low_value_notice"]
_has_long_term_report_value = _selector_api["_has_long_term_report_value"]
_is_low_value_long_term_candidate = _selector_api["_is_low_value_long_term_candidate"]
_is_technical_news_selection_candidate = _selector_api["_is_technical_news_selection_candidate"]
get_selection_candidate_limit = _selector_api["get_selection_candidate_limit"]
get_selection_output_range = _selector_api["get_selection_output_range"]
infer_preliminary_type = _selector_api["infer_preliminary_type"]
build_candidate_flags = _selector_api["build_candidate_flags"]
score_news_candidate = _selector_api["score_news_candidate"]
_candidate_score_fingerprint = _selector_api["_candidate_score_fingerprint"]
annotate_candidate_for_scheme_d = _selector_api["annotate_candidate_for_scheme_d"]
build_candidate_card = _selector_api["build_candidate_card"]
_is_low_value_policy_candidate = _selector_api["_is_low_value_policy_candidate"]
rebalance_selected_candidates = _selector_api["rebalance_selected_candidates"]
_selection_target_range = _selector_api["_selection_target_range"]
_selection_classification = _selector_api["_selection_classification"]
_has_source_reference = _selector_api["_has_source_reference"]
_selection_good_flag_count = _selector_api["_selection_good_flag_count"]
_selection_bad_flag_count = _selector_api["_selection_bad_flag_count"]
_candidate_month_key = _selector_api["_candidate_month_key"]
_candidate_system_theme = _selector_api["_candidate_system_theme"]
_candidate_operator_key = _selector_api["_candidate_operator_key"]
_candidate_incident_type = _selector_api["_candidate_incident_type"]
_candidate_action_key = _selector_api["_candidate_action_key"]
_canonical_event_geo = _selector_api["_canonical_event_geo"]
build_event_fingerprint = _selector_api["build_event_fingerprint"]
_candidate_specific_event_location = _selector_api["_candidate_specific_event_location"]
_candidate_event_location = _selector_api["_candidate_event_location"]
_event_date_close = _selector_api["_event_date_close"]
_event_similarity_text = _selector_api["_event_similarity_text"]
_is_project_series_candidate = _selector_api["_is_project_series_candidate"]
_candidate_project_stage = _selector_api["_candidate_project_stage"]
_same_project_stage_or_unspecified = _selector_api["_same_project_stage_or_unspecified"]
_duplicate_event_reason = _selector_api["_duplicate_event_reason"]
_is_same_report_event = _selector_api["_is_same_report_event"]
_is_duplicate_selected_event = _selector_api["_is_duplicate_selected_event"]
_python_selection_sort_key = _selector_api["_python_selection_sort_key"]
_python_selection_dynamic_key = _selector_api["_python_selection_dynamic_key"]
_long_term_diversity_skip_reason = _selector_api["_long_term_diversity_skip_reason"]
_python_candidate_allowed_for_scope = _selector_api["_python_candidate_allowed_for_scope"]
_is_low_value_python_selection_candidate = _selector_api["_is_low_value_python_selection_candidate"]
_is_strict_technical_candidate = _selector_api["_is_strict_technical_candidate"]
_event_source_preference_key = _selector_api["_event_source_preference_key"]
_supplemental_source_record = _selector_api["_supplemental_source_record"]
_merge_duplicate_event_sources = _selector_api["_merge_duplicate_event_sources"]
_take_next_python_candidate = _selector_api["_take_next_python_candidate"]
_is_hard_excluded_for_borderline = _selector_api["_is_hard_excluded_for_borderline"]
_is_b_level_technical_candidate = _selector_api["_is_b_level_technical_candidate"]
_is_borderline_report_candidate = _selector_api["_is_borderline_report_candidate"]
_selection_lower_bound = _selector_api["_selection_lower_bound"]
_borderline_cap = _selector_api["_borderline_cap"]
_selection_debug_reset = _selector_api["_selection_debug_reset"]
_select_from_grouped_pools = _selector_api["_select_from_grouped_pools"]
_backfill_borderline_candidates = _selector_api["_backfill_borderline_candidates"]
_service_select_candidates_by_python = _selector_api["select_candidates_by_python"]

def select_candidates_by_python(model_candidates: list[dict]) -> list[dict]:
    global LAST_PYTHON_SELECTION_DEBUG
    runtime = workflow_service.make_runtime(
        _workflow_config(),
        _workflow_dependencies(prefetch_enabled=False),
    )
    selected = runtime.select_candidates(model_candidates)
    LAST_PYTHON_SELECTION_DEBUG = selector_service.LAST_PYTHON_SELECTION_DEBUG
    return selected


def _profile_timing_add(timings: dict | None, key: str, elapsed: float) -> None:
    if timings is not None:
        timings[key] = float(timings.get(key, 0.0) or 0.0) + max(0.0, elapsed)


def prepare_candidate_pool(raw_rss: str, raw_ddg: str) -> dict:
    runtime = workflow_service.make_runtime(
        _workflow_config(),
        _workflow_dependencies(prefetch_enabled=True),
    )
    return runtime.prepare_candidate_pool(raw_rss, raw_ddg)


def _report_postprocess_context():
    return report_postprocess_service.ReportPostprocessContext(
        selected_types=selected_types,
        standards_enabled=standards_enabled,
        include_research_supplement=include_research_supplement,
        lookback_int=lookback_int,
        today=today,
        date_range=date_range,
        report_title=report_title,
        report_scope_label=report_scope_label,
        candidate_selection_text=_candidate_selection_text,
        infer_preliminary_type=infer_preliminary_type,
        is_urban_rail_candidate=_is_urban_rail_candidate,
        research_section_heading=research_section_heading,
        id_validation_target=LAST_REPORT_ID_VALIDATION,
    )


def build_long_term_coverage_warning(candidates: list[dict]) -> dict:
    return report_postprocess_service.build_long_term_coverage_warning(candidates, context=_report_postprocess_context())


def _unique_limited(values: list[str], limit: int=5) -> list[str]:
    return report_postprocess_service._unique_limited(values, limit, context=_report_postprocess_context())


def _annual_observation_dates_are_recent(candidates: list[dict]) -> bool:
    return report_postprocess_service._annual_observation_dates_are_recent(candidates, context=_report_postprocess_context())


def _annual_observation_themes(candidates: list[dict]) -> list[str]:
    return report_postprocess_service._annual_observation_themes(candidates, context=_report_postprocess_context())


def _annual_observation_report_blocks(report_md: str) -> list[str]:
    return report_postprocess_service._annual_observation_report_blocks(report_md, context=_report_postprocess_context())


def _iter_calendar_months(start_date: datetime.date, end_date: datetime.date) -> list[tuple[int, int]]:
    return report_postprocess_service._iter_calendar_months(start_date, end_date, context=_report_postprocess_context())


def build_final_report_coverage_warning(final_report_md: str, report_days: int, report_end: datetime.date | None=None) -> dict:
    return report_postprocess_service.build_final_report_coverage_warning(final_report_md, report_days, report_end, context=_report_postprocess_context())


def _annual_observation_report_dates_are_recent(blocks: list[str]) -> bool:
    return report_postprocess_service._annual_observation_report_dates_are_recent(blocks, context=_report_postprocess_context())


def build_annual_observation_section(final_report_md: str) -> str:
    return report_postprocess_service.build_annual_observation_section(final_report_md, context=_report_postprocess_context())


def _remove_annual_observation_section(report_md: str) -> str:
    return report_postprocess_service._remove_annual_observation_section(report_md, context=_report_postprocess_context())


def insert_annual_observation_section(report_md: str) -> str:
    return report_postprocess_service.insert_annual_observation_section(report_md, context=_report_postprocess_context())


def _report_prompt_context() -> ReportPromptContext:
    return ReportPromptContext(
        selected_types=selected_types,
        include_research_supplement=include_research_supplement,
        standards_enabled=standards_enabled,
        lookback_int=lookback_int,
        date_range=date_range,
        report_title=report_title,
        report_scope_label=report_scope_label,
        research_supplement_period_label=research_supplement_period_label,
        research_supplement_start_date=research_supplement_start_date,
        today=today,
        empty_text_by_type=EMPTY_TEXT_BY_TYPE,
        advanced_types=REPORT_CATEGORY_TYPES,
        selection_min_items=SELECTION_MIN_ITEMS,
        selection_max_items=SELECTION_MAX_ITEMS,
        candidate_snippet_chars=CANDIDATE_SNIPPET_CHARS,
        report_snippet_chars=REPORT_SNIPPET_CHARS,
        get_selection_output_range=get_selection_output_range,
        effective_source_url=_effective_source_url,
        domain_from_url=_domain_from_url,
        extract_domain_hint=_extract_domain_hint,
        infer_preliminary_type=infer_preliminary_type,
        shorten=_shorten,
        is_standard_update_candidate=_is_standard_update_candidate,
        source_label_for_report=source_label_for_report,
        source_verb_for_report=source_verb_for_report,
    )


def format_selection_candidate(candidate: dict) -> str:
    return service_format_selection_candidate(
        candidate,
        context=_report_prompt_context(),
    )


def _selected_report_sections() -> str:
    return service_selected_report_sections(context=_report_prompt_context())


def _section_number_for_index(index: int) -> str:
    return service_section_number_for_index(index)


def research_section_heading(markdown: bool = False) -> str:
    return service_research_section_heading(
        markdown,
        context=_report_prompt_context(),
    )


def _selected_empty_section_rules() -> str:
    return service_selected_empty_section_rules(
        context=_report_prompt_context(),
    )


def _selected_stats_template() -> str:
    return service_selected_stats_template(context=_report_prompt_context())


def _policy_selection_rule() -> str:
    return service_policy_selection_rule(context=_report_prompt_context())


WORK_ZONE_MONITORING_TERMS = [
    "work zone", "speed enforcement", "construction zone", "maintenance safety",
    "工區", "施工區", "速限執法", "維修作業安全", "施工安全", "安全監測",
]

WORK_ZONE_TECH_DETAIL_TERMS = [
    "sensor", "camera", "video", "monitoring equipment", "automated monitoring",
    "backend platform", "communication", "network", "感測", "攝影", "影像",
    "監測設備", "自動化監測", "後端平台", "通訊", "網路",
]

SOURCE_QUALITY_C_DOMAINS.update(PORTAL_REPOST_DOMAINS | PORTAL_SOCIAL_LOW_VALUE_DOMAINS)


STRICT_HIGH_VALUE_POLICY_TEXT_TERMS = [
    "fare reform", "payment policy", "service restructure", "service restructuring",
    "headway", "service frequency", "operating hours", "capacity", "trial operation",
    "system conversion", "line closure", "full line closure", "major closure",
    "maintenance closure", "long closure", "seven week closure", "seven-week closure",
    "accessibility plan", "fleet deployment", "budget approval", "governance decision",
    "replacement bus service", "alternative transport", "major engineering works",
    "票務制度", "支付政策", "班距", "營運時間", "容量", "試營運", "系統轉換",
    "全線封閉", "多站封閉", "無障礙改善計畫", "預算核准", "治理決策",
]


LAST_PYTHON_SELECTION_DEBUG: dict = dict(REPORT_SELECTION_DEBUG_DEFAULT)


def build_selection_prompt(candidates: list[dict]) -> str:
    return service_build_selection_prompt(
        candidates,
        context=_report_prompt_context(),
    )


def _json_loads_loose(text: str):
    return service_json_loads_loose(text)


def _truthy_report_flag(value) -> bool:
    return service_truthy_report_flag(value)


def parse_selection_response(response_text: str, candidates: list[dict]) -> list[dict]:
    return service_parse_selection_response(
        response_text,
        candidates,
        context=_report_prompt_context(),
    )


def build_python_unselected_stats(model_candidates: list[dict], selected_candidates: list[dict]) -> dict:
    selected_ids = {int(item.get("id", 0) or 0) for item in selected_candidates}
    stats: dict[str, int] = {}
    examples: list[dict] = []
    for candidate in model_candidates or []:
        candidate_id = int(candidate.get("id", 0) or 0)
        if candidate_id in selected_ids:
            continue
        classification = _selection_classification(candidate)
        flags = set(candidate.get("candidate_flags", []) or [])
        if classification not in selected_types:
            reason = "類型未勾選"
        elif classification == "技術新知" and not _is_strict_technical_candidate(dict(candidate, classification=classification)):
            reason = "技術新知缺少明確機電/系統細節或屬低價值公告"
        elif not _python_candidate_allowed_for_scope(dict(candidate, classification=classification)):
            reason = "國家/地區不在指定範圍"
        elif _is_low_value_python_selection_candidate(candidate):
            reason = "Python 規則排除低價值或資訊不足候選"
        elif flags.intersection({"low_value_service_notice", "insufficient_information", "short_snippet", "low_value_official_notice", "procurement_list_notice", "general_rail_exclusion"}):
            reason = "低價值或摘要不足旗標降權後未入選"
        else:
            reason = "Python 規則排序、候補機制與類別平衡後未入選"
        stats[reason] = stats.get(reason, 0) + 1
        if len(examples) < 20:
            examples.append({
                "id": candidate_id,
                "title": candidate.get("title", ""),
                "classification": classification,
                "python_score": candidate.get("python_score", 0),
                "source_tier": candidate.get("source_tier", ""),
                "candidate_flags": candidate.get("candidate_flags", []),
                "reason": reason,
            })
    return {"summary": stats, "examples": examples}

def build_ai_unselected_stats(model_candidates: list[dict], selected_candidates: list[dict]) -> dict:
    selected_ids = {int(item.get("id", 0) or 0) for item in selected_candidates}
    stats: dict[str, int] = {}
    examples: list[dict] = []
    for candidate in model_candidates or []:
        candidate_id = int(candidate.get("id", 0) or 0)
        if candidate_id in selected_ids:
            continue
        text = f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('source', '')}"
        quality = candidate.get("source_quality", "B")
        if quality == "C":
            reason = "C級來源降權或未被第一階段選題納入"
        elif _contains_any_term(text, TECH_NEWS_SOFT_EXCLUDE_TERMS):
            reason = "可能偏事故、政策、爭議或缺少技術細節"
        elif not _contains_any_term(text, TECH_NEWS_REQUIRED_TERMS) and candidate.get("classification") == "技術新知":
            reason = "技術關鍵字不足"
        else:
            reason = "MaiAgent 第一階段未回傳該候選編號"
        stats[reason] = stats.get(reason, 0) + 1
        if len(examples) < 20:
            examples.append({
                "id": candidate_id,
                "title": candidate.get("title", ""),
                "quality": quality,
                "source": candidate.get("source", ""),
                "reason": reason,
            })
    return {"summary": stats, "examples": examples}


def format_report_candidate(candidate: dict) -> str:
    return service_format_report_candidate(
        candidate,
        context=_report_prompt_context(),
    )


ensure_selected_candidate_ids = service_ensure_selected_candidate_ids


def _journal_service_context(status_text=None) -> JournalServiceContext:
    status_callback = status_text.text if status_text else None
    return JournalServiceContext(
        today=today,
        research_supplement_lookback_days=research_supplement_lookback_days,
        research_supplement_period_label=research_supplement_period_label,
        include_research_supplement=include_research_supplement,
        ddgs_client_factory=DDGS,
        http_session_factory=create_requests_session,
        make_news_candidate=_make_news_candidate,
        is_urban_rail_candidate=_is_urban_rail_candidate,
        status_callback=status_callback,
    )


def _journal_priority(date_text: str) -> tuple[int, str]:
    return service_journal_priority(date_text, context=_journal_service_context())


def _research_date_info(result: dict, title: str, snippet: str) -> dict:
    return service_research_date_info(
        result,
        title,
        snippet,
        context=_journal_service_context(),
    )


def _journal_safe_get(url: str, timeout: int = 8) -> str:
    return service_journal_safe_get(
        url,
        timeout,
        http_session_factory=create_requests_session,
    )


def fetch_journal_page_metadata(url: str) -> dict:
    return service_fetch_journal_page_metadata(
        url,
        context=_journal_service_context(),
    )


def _journal_source_page_results(status_text=None) -> tuple[list[dict], list[dict]]:
    return service_journal_source_page_results(
        context=_journal_service_context(status_text),
    )


def collect_journal_candidates(status_text=None) -> tuple[list[dict], list[dict], list[dict]]:
    return service_collect_journal_candidates(
        context=_journal_service_context(status_text),
    )


# V18.2 Prompt-only 測試版：僅調整正式報告撰寫 Prompt，不變更搜尋、選題、評分、去重及輸出流程。
def build_report_prompt(selected_candidates: list[dict], journal_candidates: list[dict], search_count: int) -> str:
    return workflow_service.build_report_prompt(
        selected_candidates,
        journal_candidates,
        search_count,
        config=_workflow_config(),
        runtime=workflow_service.make_runtime(
            _workflow_config(),
            _workflow_dependencies(prefetch_enabled=False),
        ),
    )

_extract_maiagent_text = extract_maiagent_text


def call_maiagent_cloud(prompt: str) -> str:
    return call_maiagent_service(
        prompt, api_key=maiagent_api_key, chatbot_id=maiagent_chatbot_id,
        api_base=maiagent_api_base,
    )


def markdown_to_html(md: str) -> str:
    return streamlit_html_renderer(md, remove_internal_candidate_markers)


def markdown_fragment_to_html(md: str) -> str:
    return shared_fragment_renderer(md, remove_internal_candidate_markers, compact_report_urls)


def strip_unselected_report_sections(text: str) -> str:
    return service_strip_unselected_report_sections(text, selected_types=selected_types)


def strip_unselected_types_from_title(text: str) -> str:
    return service_strip_unselected_types_from_title(text, selected_types=selected_types)


def final_report_statistics_line(report_md: str, journal_candidates: list[dict] | None = None) -> str:
    return service_final_report_statistics_line(
        report_md,
        journal_candidates,
        selected_types=selected_types,
        include_research_supplement=include_research_supplement,
    )


def apply_final_report_footer(
    report_md: str,
    journal_candidates: list[dict] | None = None,
    *,
    report_date: datetime.date | None = None,
    selected_types_override: list[str] | None = None,
) -> str:
    return service_apply_final_report_footer(
        report_md,
        journal_candidates,
        selected_types=(
            selected_types_override
            if selected_types_override is not None
            else selected_types
        ),
        include_research_supplement=include_research_supplement,
        today=report_date or today,
    )


def normalize_research_section_heading(text: str) -> str:
    return service_normalize_research_section_heading(
        text,
        include_research_supplement=include_research_supplement,
        research_section_heading=research_section_heading,
    )


def normalize_report_section_numbering(text: str) -> str:
    return service_normalize_report_section_numbering(
        text,
        selected_types=selected_types,
        standards_enabled=standards_enabled,
    )


def merge_operational_report_sections(report_md: str) -> str:
    return service_merge_operational_report_sections(
        report_md,
        selected_types=selected_types,
        standards_enabled=standards_enabled,
    )


def sanitize_report_text(text: str) -> str:
    return service_sanitize_report_text(
        text,
        selected_types=selected_types,
        standards_enabled=standards_enabled,
        include_research_supplement=include_research_supplement,
        research_section_heading=research_section_heading,
    )


def _journal_theme_summary(journal_candidates: list[dict]) -> list[str]:
    return report_postprocess_service._journal_theme_summary(journal_candidates, context=_report_postprocess_context())


def build_journal_summary_conclusion(journal_candidates: list[dict]) -> str:
    return report_postprocess_service.build_journal_summary_conclusion(journal_candidates, context=_report_postprocess_context())


def ensure_journal_summary_conclusion(report_md: str, journal_candidates: list[dict]) -> str:
    return report_postprocess_service.ensure_journal_summary_conclusion(report_md, journal_candidates, context=_report_postprocess_context())


def _journal_candidate_full_date(item: dict) -> str:
    return report_postprocess_service._journal_candidate_full_date(item, context=_report_postprocess_context())


def _normalize_doi_value(value: str) -> str:
    return report_postprocess_service._normalize_doi_value(value, context=_report_postprocess_context())


def _journal_candidate_date_for_text(text: str, journal_candidates: list[dict], report_title: str='') -> str:
    return report_postprocess_service._journal_candidate_date_for_text(text, journal_candidates, report_title, context=_report_postprocess_context())


def repair_journal_dates_in_report(report_md: str, journal_candidates: list[dict]) -> str:
    return report_postprocess_service.repair_journal_dates_in_report(report_md, journal_candidates, context=_report_postprocess_context())


def _is_canonical_journal_section(section: str) -> bool:
    return report_postprocess_service._is_canonical_journal_section(section, context=_report_postprocess_context())


def normalize_journal_section_format(report_md: str, journal_candidates: list[dict]) -> str:
    return report_postprocess_service.normalize_journal_section_format(report_md, journal_candidates, context=_report_postprocess_context())


def count_journal_summary_conclusion_chars(report_md: str) -> int:
    return report_postprocess_service.count_journal_summary_conclusion_chars(report_md, context=_report_postprocess_context())


def enforce_research_section(report_md: str, journal_candidates: list[dict]) -> str:
    return report_postprocess_service.enforce_research_section(report_md, journal_candidates, context=_report_postprocess_context())


def _candidate_report_presence_keys(candidate: dict) -> list[str]:
    return report_postprocess_service._candidate_report_presence_keys(candidate, context=_report_postprocess_context())


def _report_block_matches_candidate(block: str, candidate: dict) -> bool:
    return report_postprocess_service._report_block_matches_candidate(block, candidate, context=_report_postprocess_context())


def _supplemental_source_is_used(report_block: str, candidate: dict, source_row: dict) -> bool:
    return report_postprocess_service._supplemental_source_is_used(report_block, candidate, source_row, context=_report_postprocess_context())


def _report_block_matches_supplemental_candidate(block: str, candidate: dict) -> bool:
    return report_postprocess_service._report_block_matches_supplemental_candidate(block, candidate, context=_report_postprocess_context())


def ensure_supplemental_sources_in_report(report_md: str, selected_candidates: list[dict]) -> str:
    return report_postprocess_service.ensure_supplemental_sources_in_report(report_md, selected_candidates, context=_report_postprocess_context())


def _candidate_region_display(candidate: dict) -> str:
    return report_postprocess_service._candidate_region_display(candidate, context=_report_postprocess_context())


def _is_unknown_region_value(value: str) -> bool:
    return report_postprocess_service._is_unknown_region_value(value, context=_report_postprocess_context())


def repair_report_region_lines(report_md: str, selected_candidates: list[dict]) -> str:
    return report_postprocess_service.repair_report_region_lines(report_md, selected_candidates, context=_report_postprocess_context())


def formal_title_from_candidate(candidate: dict) -> str:
    return report_postprocess_service.formal_title_from_candidate(candidate, context=_report_postprocess_context())


def repair_generic_report_titles(report_md: str, selected_candidates: list[dict]) -> str:
    return report_postprocess_service.repair_generic_report_titles(report_md, selected_candidates, context=_report_postprocess_context())


REPORT_CANDIDATE_ID_PATTERN = SERVICE_REPORT_CANDIDATE_ID_PATTERN
REPORT_ESCAPED_CANDIDATE_ID_PATTERN = SERVICE_REPORT_ESCAPED_CANDIDATE_ID_PATTERN
INTERNAL_CANDIDATE_MARKER_PATTERN = SERVICE_INTERNAL_CANDIDATE_MARKER_PATTERN
ESCAPED_INTERNAL_CANDIDATE_MARKER_PATTERN = SERVICE_ESCAPED_INTERNAL_CANDIDATE_MARKER_PATTERN
LAST_REPORT_ID_VALIDATION: dict = {}


extract_report_candidate_ids = service_extract_report_candidate_ids


remove_internal_candidate_markers = service_remove_internal_candidate_markers


validate_report_candidate_ids = service_validate_report_candidate_ids


build_report_retry_prompt = service_build_report_retry_prompt


def _extract_marked_candidate_blocks(report_md: str) -> tuple[dict[int, str], list[int]]:
    return report_postprocess_service._extract_marked_candidate_blocks(report_md, context=_report_postprocess_context())


def _candidate_source_line(candidate: dict) -> str:
    return report_postprocess_service._candidate_source_line(candidate, context=_report_postprocess_context())


def _fallback_report_block(candidate: dict) -> str:
    return report_postprocess_service._fallback_report_block(candidate, context=_report_postprocess_context())


def _force_candidate_fields_in_block(block: str, candidate: dict) -> str:
    return report_postprocess_service._force_candidate_fields_in_block(block, candidate, context=_report_postprocess_context())


def _extract_research_section_for_reconcile(report_md: str) -> str:
    return report_postprocess_service._extract_research_section_for_reconcile(report_md, context=_report_postprocess_context())


def reconcile_report_candidate_output(report_md: str, selected_candidates: list[dict]) -> tuple[str, dict]:
    return report_postprocess_service.reconcile_report_candidate_output(report_md, selected_candidates, context=_report_postprocess_context())


def identify_dropped_selected_candidates(report_md: str, selected_candidates: list[dict]) -> list[dict]:
    return report_postprocess_service.identify_dropped_selected_candidates(report_md, selected_candidates, context=_report_postprocess_context())


def restore_missing_selected_report_items(report_md: str, selected_candidates: list[dict]) -> tuple[str, list[dict]]:
    return report_postprocess_service.restore_missing_selected_report_items(report_md, selected_candidates, context=_report_postprocess_context())


def compact_report_line_for_pdf(line: str) -> str:
    line = normalize_source_line(remove_internal_candidate_markers(line))
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    if "資料來源" in line:
        protected_links: list[str] = []

        def _protect_link(match: re.Match) -> str:
            protected_links.append(match.group(0))
            return f"__PDF_SOURCE_LINK_{len(protected_links) - 1}__"

        line = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", _protect_link, line)
        line = re.sub(
            r"https?://[^\s\)\]）＞>，,；;。]+",
            lambda match: f"[原文連結]({match.group(0).rstrip('。；;,，)')})",
            line,
        )
        for index, link in enumerate(protected_links):
            line = line.replace(f"__PDF_SOURCE_LINK_{index}__", link)
    return line


def display_report_markdown(md: str) -> str:
    display_md = compact_report_urls(remove_internal_candidate_markers(md))
    return re.sub(r"(?m)^#\s+(.+)$", r"### \1", display_md, count=1)


def register_pdf_fonts() -> tuple[str, str]:
    """Register an embeddable CJK font or fail explicitly."""
    global LAST_PDF_FONT_INFO
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_name = "MetroReportCJK"
    try:
        pdfmetrics.getFont(font_name)
        if LAST_PDF_FONT_INFO.get("path"):
            return font_name, font_name
    except Exception:
        pass

    attempted: list[str] = []
    existing_count = 0
    failure_details: list[str] = []
    required_cjk_chars = "繁體中文捷運號誌"
    for source, font_path in iter_pdf_font_candidates():
        path = str(font_path)
        attempted.append(path)
        if not font_path.exists():
            continue
        existing_count += 1
        for kwargs in ({"subfontIndex": 0}, {"subfontIndex": 1}, {}):
            try:
                font = TTFont(font_name, path, **kwargs)
                char_map = getattr(font.face, "charToGlyph", {}) or {}
                missing_chars = [char for char in required_cjk_chars if ord(char) not in char_map]
                if missing_chars:
                    raise ValueError(f"缺少繁體中文字形：{''.join(missing_chars)}")
                pdfmetrics.registerFont(font)
                LAST_PDF_FONT_INFO = {
                    "font_name": font_name,
                    "path": path,
                    "source": source,
                    "embedded_required": "true",
                }
                return font_name, font_name
            except Exception as exc:
                if len(failure_details) < 6:
                    failure_details.append(f"{font_path.name}: {exc}")
                continue

    LAST_PDF_FONT_INFO = {
        "font_name": "",
        "path": "",
        "source": "missing",
        "embedded_required": "true",
        "attempted_count": str(len(attempted)),
        "existing_count": str(existing_count),
        "failure_details": " | ".join(failure_details),
    }
    raise PdfFontUnavailableError(
        "找不到 ReportLab 可嵌入且含繁體中文字形的字型，PDF 未產生。"
        "Linux 請確認 packages.txt 已安裝 fonts-wqy-zenhei；"
        "也可將可嵌入的 CJK TrueType 字型放入程式 fonts 目錄，"
        "或以 METRO_REPORT_PDF_FONT_PATH 指定完整路徑。"
        f" 已檢查 {len(attempted)} 個候選，其中 {existing_count} 個檔案存在。"
    )


pdf_rich_text = shared_pdf_rich_text


def category_badge_class(category: str) -> str:
    return {
        "技術新知": "badge-tech",
        "重大事故": "badge-incident",
        "營運政策": "badge-policy",
        "營運爭議": "badge-dispute",
        "規範更新": "badge-standard",
    }.get(category, "badge-neutral")


def detect_category(text: str) -> str:
    for category in ADVANCED_TYPES:
        if category in text:
            return category
    return "其他"


def build_final_incident_coverage_debug(selected_candidates: list[dict], maiagent_report_response: str, final_report_md: str, *, global_scope: bool, report_days: int, incident_enabled: bool) -> dict:
    return report_postprocess_service.build_final_incident_coverage_debug(selected_candidates, maiagent_report_response, final_report_md, global_scope=global_scope, report_days=report_days, incident_enabled=incident_enabled, context=_report_postprocess_context())


def report_has_unselected_types(report_md: str) -> bool:
    return report_postprocess_service.report_has_unselected_types(report_md, context=_report_postprocess_context())


def report_has_non_urban_formal_items(report_md: str) -> bool:
    return report_postprocess_service.report_has_non_urban_formal_items(report_md, context=_report_postprocess_context())


def has_candidate_observations(report_md: str) -> bool:
    return report_postprocess_service.has_candidate_observations(report_md, context=_report_postprocess_context())


def split_report_summary(report_md: str) -> tuple[str, str]:
    match = re.search(r"(?m)^##\s*報告摘要.*$", report_md)
    if not match:
        return report_md.strip(), ""
    main_report = report_md[:match.start()].strip()
    summary = report_md[match.end():].strip()
    summary = re.sub(r"(?m)^---\s*$", "", summary).strip()
    return main_report, summary


def trim_report_card_body(body: str) -> str:
    body = re.split(r"(?m)^##\s+", body, maxsplit=1)[0]
    body = re.sub(r"(?m)^---\s*$", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def render_report_cards(report_md: str) -> None:
    main_report, summary = split_report_summary(report_md)
    parts = re.split(r"(?m)^###\s+", main_report)
    if len(parts) <= 1:
        st.markdown(compact_report_urls(main_report))
        if summary:
            st.markdown(
                f"""
                <div class="section-title">報告摘要</div>
                <div class="report-summary-card">
                  <div class="report-card-body">{markdown_fragment_to_html(summary)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        return

    intro = parts[0].strip()
    if intro:
        st.markdown(compact_report_urls(intro))

    for part in parts[1:]:
        if not part.strip():
            continue
        lines = part.splitlines()
        heading = lines[0].strip()
        if re.sub(r"^[#\s]+", "", heading).strip().startswith(("報告摘要", "候補觀察")):
            continue
        body = trim_report_card_body("\n".join(lines[1:]).strip())
        category = detect_category(heading)
        st.markdown(
            f"""
            <div class="report-card">
              <span class="type-badge {category_badge_class(category)}">{escape(category)}</span>
              <h4>{escape(heading)}</h4>
              <div class="report-card-body">{markdown_fragment_to_html(body)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if summary:
        st.markdown(
            f"""
            <div class="section-title">報告摘要</div>
            <div class="report-summary-card">
              <div class="report-card-body">{markdown_fragment_to_html(summary)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def markdown_to_pdf_bytes(md: str) -> bytes:
    return streamlit_pdf_renderer(
        md, marker_cleaner=remove_internal_candidate_markers,
        font_registrar=register_pdf_fonts, line_compactor=compact_report_line_for_pdf,
        rich_text_renderer=pdf_rich_text, token_wrapper=_soft_wrap_long_tokens,
        candidate_id_pattern=REPORT_CANDIDATE_ID_PATTERN,
    )


_soft_wrap_long_tokens = shared_soft_wrap_long_tokens


def try_markdown_to_pdf_bytes(md: str) -> bytes | None:
    global LAST_PDF_ERROR
    LAST_PDF_ERROR = ""
    try:
        return markdown_to_pdf_bytes(md)
    except Exception as exc:
        LAST_PDF_ERROR = f"PDF 產生失敗：{exc}"
        return None


def _read_demo_debug_payload(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _builtin_demo_report_text() -> str:
    demo_report_title = report_title.replace("營運動態", "營運議題")
    sections: list[str] = [
        f"# {demo_report_title}",
        f"> 資料涵蓋期間：{date_range}",
        f"> 報導範圍：{report_scope_label}",
        "",
        "一、技術新知",
        "",
        "🔹 [技術新知] 展示用捷運機電監測案例",
        "",
        "• 發布/事件日期：日期未知",
        "",
        "• 國家/地區：展示資料",
        "",
        "• 相關機電系統：號誌、通訊、車輛、供電與維修監測",
        "",
        "• 事件摘要：",
        "本段為展覽快速版內建展示文字，用於現場快速呈現週報格式、PDF 下載與 Email 寄送流程。內容不代表即時搜尋結果，也未連線查詢新聞來源或呼叫 AI 服務。",
        "",
        "• 臺北捷運局啟示：",
        "展示模式可先確認輸出流程與畫面穩定性，正式測試時請取消展覽快速版。",
        "",
        "• 資料來源：展覽快速版預產展示資料，日期未知，未提供完整 URL",
        "",
        "________________________________________",
    ]
    if "規範更新" in selected_types:
        sections.extend([
            "",
            "四、規範更新",
            "本期未發現符合條件資料。",
        ])
    if include_research_supplement:
        sections.extend([
            "",
            research_section_heading(markdown=True),
            "本期未發現符合期間條件且具明確發表日期之國際學術或技術研究資料。",
        ])
    sections.extend([
        "",
        "📊 本期統計：共 1 則（技術新知 1 則）",
        f"⏰ 報告產出時間：{today.strftime('%Y年%m月%d日')}",
    ])
    return "\n".join(sections)


def load_demo_report_cache() -> tuple[str, bytes | None, dict]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    demo_md_path = REPORTS_DIR / "demo_report.md"
    demo_pdf_path = REPORTS_DIR / "demo_report.pdf"
    demo_debug_path = REPORTS_DIR / "demo_debug.json"
    debug_payload = _read_demo_debug_payload(demo_debug_path)
    source = "內建展示文字"

    try:
        demo_md_exists = demo_md_path.exists()
    except OSError:
        demo_md_exists = False
    if demo_md_exists:
        try:
            report_text = demo_md_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            report_text = str(debug_payload.get("final_report_md") or "").strip()
            if report_text:
                source = str(demo_debug_path)
            else:
                report_text = _builtin_demo_report_text()
        else:
            source = str(demo_md_path)
    else:
        report_text = str(debug_payload.get("final_report_md") or "").strip()
        if report_text:
            source = str(demo_debug_path)
        else:
            report_text = _builtin_demo_report_text()

    report_text = remove_internal_candidate_markers(sanitize_report_text(report_text))
    report_text = report_text.replace("營運動態", "營運議題")
    report_text = enforce_research_section(report_text, [])
    report_text = normalize_final_report_md(report_text)
    demo_selected_types = [
        category
        for category in selected_types
        if category != ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL
    ]
    report_text = apply_final_report_footer(
        report_text,
        [],
        selected_types_override=demo_selected_types,
        report_date=DEMO_REPORT_DATE,
    )

    try:
        demo_pdf_exists = demo_pdf_path.exists()
    except OSError:
        demo_pdf_exists = False
    if demo_pdf_exists:
        try:
            pdf_bytes = demo_pdf_path.read_bytes()
        except OSError:
            pdf_bytes = None
        if not pdf_bytes:
            pdf_bytes = try_markdown_to_pdf_bytes(report_text)
    else:
        pdf_bytes = try_markdown_to_pdf_bytes(report_text)

    return report_text, pdf_bytes, {
        "demo_source": source,
        "demo_markdown_path": str(demo_md_path),
        "demo_pdf_path": str(demo_pdf_path) if demo_pdf_exists else "",
        "demo_debug_path": str(demo_debug_path) if demo_debug_path.exists() else "",
        "demo_debug_payload_found": bool(debug_payload),
    }


def send_email_func(text: str, recipients: list, gmail_user: str, gmail_pass: str) -> bool:
    text = remove_internal_candidate_markers(text)
    email_run_config = st.session_state.get("latest_run_config", current_run_config)
    return send_streamlit_email(
        text, recipients,
        subject=email_run_config.get("report_title", report_title),
        sender=gmail_user, password=gmail_pass,
        html_renderer=markdown_to_html, pdf_renderer=try_markdown_to_pdf_bytes,
        pdf_filename=build_report_download_filename("metro_report", "pdf", email_run_config),
        on_error=st.error,
    )


def send_current_report_email(report_md: str, status_target=None, progress_target=None) -> bool:
    report_md = remove_internal_candidate_markers(report_md)
    recipients = [r.strip() for r in recipient_input.splitlines() if r.strip()]
    if not report_md:
        if status_target:
            status_target.warning("⚠️ 請先產生報告，再寄送 Email。")
        return False
    if not recipients:
        if status_target:
            status_target.warning("⚠️ 請在左側填入收件信箱")
        return False
    if not gmail_user or not gmail_pass:
        if status_target:
            status_target.warning("⚠️ GMAIL_USER 或 GMAIL_APP_PASS 未在 Secrets 中設定")
        return False
    if progress_target:
        progress_target.progress(0.95)
    if status_target:
        status_target.text("📧 正在寄送 Email 至公務信箱……")
    ok = send_email_func(report_md, recipients, gmail_user, gmail_pass)
    if ok:
        if progress_target:
            progress_target.progress(1.0)
        if status_target:
            status_target.success("✅ Email 已寄送完成。")
        st.success(f"📧 已成功寄送至：{', '.join(recipients)}")
    return ok


if generate_btn:
    if demo_cache_mode_enabled:
        run_config = current_run_config.copy()
        clear_old_report_state()
        st.session_state["latest_run_config"] = run_config
        st.session_state["report_generated"] = False
        st.session_state["email_sent"] = False
        progress_bar = progress_placeholder.progress(0.15)
        status_text = status_placeholder

        try:
            run_start = time.perf_counter()
            status_text.text("正在進行報告撰寫")
            report_text, pdf_bytes, demo_meta = load_demo_report_cache()
            progress_bar.progress(0.70)

            formal_count = count_report_items(report_text)
            category_counts = count_report_items_by_category(report_text)
            has_standard_updates = category_counts.get("規範更新", 0) > 0 or bool(
                re.search(r"(?m)^🔹\s*\[規範更新\]", report_text)
            )
            elapsed_total = round(time.perf_counter() - run_start, 2)
            source_statuses = [{
                "source_name": "展覽快速版預產報告",
                "method": "預產報告",
                "status": "skipped_demo_cache_mode",
                "item_count": 0,
                "error_message": "展覽快速版啟用，未執行 RSS、Google News、DDGS、MaiAgent、規範查詢或學術查詢",
                "fallback_used": False,
            }]
            source_health_summary = build_source_health_summary(source_statuses)
            report_stats = {
                "raw_count": 0,
                "deduped_count": 0,
                "filtered_count": 0,
                "ai_selected_count": 0,
                "formal_count": formal_count,
                "prompt_chars": 0,
                "raw_chars": len(report_text),
                "maiagent_call_count": 0,
                "category_counts": category_counts,
                "journal_count": 0,
                "model_candidate_count": 0,
                "source_count": 0,
                "ddgs_query_count": 0,
                "policy_query_count": 0,
                "dispute_query_count": 0,
                "service_opening_query_count": 0,
                "policy_raw_candidate_count": 0,
                "dispute_raw_candidate_count": 0,
                "service_opening_raw_candidate_count": 0,
                "policy_raw_candidates": [],
                "dispute_raw_candidates": [],
                "service_opening_raw_candidates": [],
                "policy_gate_pass_count": 0,
                "dispute_gate_pass_count": 0,
                "service_opening_gate_pass_count": 0,
                "gate_failure_reason_stats": {},
                "operational_topic_selected_count": 0,
                "candidate_card_limit": 0,
                "candidate_card_count": 0,
                "elapsed_seconds_total": elapsed_total,
                "elapsed_seconds_rss": 0.0,
                "elapsed_seconds_ddgs": 0.0,
                "elapsed_seconds_candidate_pool": 0.0,
                "elapsed_seconds_journal": 0.0,
                "elapsed_seconds_selection": 0.0,
                "elapsed_seconds_python_selection": 0.0,
                "elapsed_seconds_report": 0.0,
                "elapsed_seconds_pdf": 0.0,
                "source_health_summary": source_health_summary,
                "selection_method": "demo_cache",
                "demo_cache_mode": True,
                "include_research_supplement": include_research_supplement,
                "research_supplement_period": run_config.get("research_supplement_period", {}),
                "run_config": run_config,
            }
            debug_info = {
                "run_config": run_config,
                "raw_candidates": [],
                "deduped_candidates": [],
                "filtered_candidates": [],
                "excluded_candidates": [],
                "model_candidates": [],
                "candidate_cards": [],
                "selected_candidates": [],
                "selected_ids": [],
                "enriched_selected_candidates": [],
                "journal_candidates": [],
                "journal_statuses": [],
                "journal_excluded_candidates": [],
                "selection_prompt": "",
                "selection_response": "",
                "selection_method": "demo_cache",
                "ai_selection_response": "",
                "python_unselected_stats": {},
                "report_prompt": "",
                "report_response": "",
                "latest_report_md": report_text,
                "ai_unselected_stats": {},
                "dedupe_stats": {},
                "exclusion_stats": {},
                "source_statuses": source_statuses,
                "source_health_summary": source_health_summary,
                "report_stats": report_stats,
                "long_term_coverage": {"long_term_coverage_warning": False, "reason": ""},
                "demo_meta": demo_meta,
            }
            st.session_state["latest_report_md"] = report_text
            st.session_state["latest_report"] = report_text
            st.session_state["latest_pdf"] = pdf_bytes
            st.session_state["latest_report_summary"] = {
                "formal_count": formal_count,
                "has_standards": has_standard_updates,
                "category_counts": category_counts,
            }
            st.session_state["latest_report_stats"] = report_stats
            st.session_state["latest_run_config"] = run_config
            st.session_state["report_generated"] = True
            st.session_state["latest_debug_info"] = debug_info
            st.session_state["latest_source_statuses"] = source_statuses
            st.session_state["latest_debug_payload"] = {
                "run_info": {
                    "demo_cache_mode": True,
                    "include_research_supplement": include_research_supplement,
                    "research_supplement_period": run_config.get("research_supplement_period", {}),
                },
                "stats": report_stats,
                "source_health": source_statuses,
                "source_health_summary": source_health_summary,
                "final_report_md": report_text,
            }

            email_note = "未自動寄送 Email"
            if send_after_generate:
                email_ok = send_current_report_email(
                    st.session_state["latest_report_md"],
                    status_target=status_text,
                    progress_target=progress_bar,
                )
                email_note = "Email 已寄送" if email_ok else "Email 未寄出，請檢查收件設定或 Secrets"
                st.session_state["email_sent"] = bool(email_ok)
            else:
                progress_bar.progress(0.95)

            progress_bar.progress(1.0)
            status_text.text("報告產製完成")
        except Exception as e:
            progress_placeholder.empty()
            status_text.error(f"❌ 展覽快速版載入失敗：{e}")
    elif not maiagent_api_key:
        status_placeholder.error("❌ MaiAgent API Key 未設定，請至 Streamlit Cloud App Settings → Secrets 填入 MAIAGENT_API_KEY")
    elif not maiagent_chatbot_id:
        status_placeholder.error("❌ MaiAgent Chatbot ID 未設定，請至 Streamlit Cloud App Settings → Secrets 填入 MAIAGENT_CHATBOT_ID")
    elif not selected_types:
        status_placeholder.error("❌ 尚未勾選新聞類型，請至左側選單勾選想要搜尋的主題。")
    elif not is_global_scope and not active_regions:
        status_placeholder.error("❌ 指定先進國家/地區模式下，請至少勾選一個國家/地區。")
    else:
        run_config = current_run_config.copy()
        clear_old_report_state()
        st.session_state["latest_run_config"] = run_config
        st.session_state["report_generated"] = False
        st.session_state["email_sent"] = False
        progress_bar = progress_placeholder.progress(0.10)
        status_text = status_placeholder

        class ProgressRange:
            def __init__(self, progress_bar_obj, start: float, end: float):
                self.progress_bar_obj = progress_bar_obj
                self.start = start
                self.end = end

            def progress(self, value: float):
                value = max(0.0, min(1.0, float(value)))
                self.progress_bar_obj.progress(self.start + (self.end - self.start) * value)

        try:
            maiagent_call_count = 0
            run_start = time.perf_counter()
            timings = {
                "elapsed_seconds_total": 0.0,
                "elapsed_seconds_rss": 0.0,
                "elapsed_seconds_ddgs": 0.0,
                "elapsed_seconds_candidate_pool": 0.0,
                "elapsed_seconds_journal": 0.0,
                "elapsed_seconds_selection": 0.0,
                "elapsed_seconds_python_selection": 0.0,
                "elapsed_seconds_report": 0.0,
                "elapsed_seconds_pdf": 0.0,
            }

            # Step 1：RSS 訂閱源 + 指定模式地區代理 + 規範更新代理
            region_sources = build_region_news_sources(active_regions, int(lookback_days), fast_mode=fast_mode_enabled)
            standards_sources = build_standards_news_sources(int(lookback_days)) if standards_enabled else []
            combined_sources, skipped_source_statuses = build_run_news_sources(
                region_sources,
                standards_sources,
                fast_mode_enabled,
                return_skipped=True,
            )
            status_text.text("正在蒐集國際捷運新聞")
            stage_start = time.perf_counter()
            rss_results, fetched_source_statuses = fetch_rss_feeds(
                combined_sources, status_text=status_text, return_status=True
            )
            source_statuses = skipped_source_statuses + fetched_source_statuses
            source_health_summary = build_source_health_summary(source_statuses)
            timings["elapsed_seconds_rss"] = round(time.perf_counter() - stage_start, 2)
            progress_bar.progress(0.25)
            st.session_state["latest_source_statuses"] = source_statuses

            status_text.text("正在蒐集國際捷運新聞")
            ddg_progress = ProgressRange(progress_bar, 0.25, 0.40)
            search_count = len(build_search_queries()[0])
            stage_start = time.perf_counter()
            ddg_results = run_duckduckgo_searches(ddg_progress, status_text)
            timings["elapsed_seconds_ddgs"] = round(time.perf_counter() - stage_start, 2)
            progress_bar.progress(0.42)

            status_text.text("正在整理候選資料")
            stage_start = time.perf_counter()
            candidate_pool = prepare_candidate_pool(rss_results, ddg_results)
            timings["elapsed_seconds_candidate_pool"] = round(time.perf_counter() - stage_start, 2)
            model_candidates = candidate_pool["model_candidates"]
            long_term_coverage = build_long_term_coverage_warning(candidate_pool["filtered_candidates"])
            progress_bar.progress(0.52)

            status_text.text("正在整理候選資料")
            time.sleep(0.1)
            progress_bar.progress(0.58)

            # Step 2：Python 規則選題
            status_text.text("正在整理候選資料")
            selection_prompt = ""
            selection_response = ""
            stage_start = time.perf_counter()
            selected_candidates = ensure_selected_candidate_ids(select_candidates_by_python(model_candidates))
            timings["elapsed_seconds_python_selection"] = round(time.perf_counter() - stage_start, 2)
            timings["elapsed_seconds_selection"] = timings["elapsed_seconds_python_selection"]
            selected_ids = [int(item.get("candidate_id", item.get("id", 0)) or 0) for item in selected_candidates]
            python_unselected_stats = build_python_unselected_stats(model_candidates, selected_candidates)
            ai_unselected_stats = python_unselected_stats
            selected_long_term_coverage = build_long_term_coverage_warning(selected_candidates)
            if selected_long_term_coverage.get("long_term_coverage_warning"):
                long_term_coverage = selected_long_term_coverage
            progress_bar.progress(0.70)

            journal_candidates: list[dict] = []
            journal_statuses: list[dict] = []
            journal_excluded_candidates: list[dict] = []
            stage_start = time.perf_counter()
            if include_research_supplement:
                journal_candidates, journal_statuses, journal_excluded_candidates = collect_journal_candidates(status_text)
            timings["elapsed_seconds_journal"] = round(time.perf_counter() - stage_start, 2)
            progress_bar.progress(0.76)

            # Step 3：MaiAgent 第二階段正式報告
            status_text.text("正在進行報告撰寫")
            report_prompt = build_report_prompt(selected_candidates, journal_candidates, search_count)
            stage_start = time.perf_counter()
            raw_report = call_maiagent_cloud(report_prompt)
            initial_raw_report = raw_report
            report_id_validation_before_retry = service_validate_authoritative_report(
                raw_report,
                selected_candidates,
                selected_types=selected_types,
            )
            report_retry_attempted = False
            if report_id_validation_before_retry.get("retry_required"):
                report_retry_attempted = True
                retry_prompt = build_report_retry_prompt(
                    report_prompt,
                    raw_report,
                    report_id_validation_before_retry,
                )
                raw_report = call_maiagent_cloud(retry_prompt)
                maiagent_call_count += 1
            report_id_validation_after_retry = service_validate_authoritative_report(
                raw_report,
                selected_candidates,
                selected_types=selected_types,
            )
            raw_report_candidate_ids = extract_report_candidate_ids(raw_report)
            maiagent_report_response_count = count_authoritative_report_items(raw_report)
            timings["elapsed_seconds_report"] = round(time.perf_counter() - stage_start, 2)
            maiagent_call_count += 1
            progress_bar.progress(0.88)

            status_text.text("正在進行報告撰寫")
            pdf_stage_start = time.perf_counter()
            postprocess_runtime = workflow_service.make_runtime(
                _workflow_config(),
                _workflow_dependencies(prefetch_enabled=False),
            )
            postprocess_result = postprocess_runtime.postprocess_report_with_diagnostics(
                raw_report,
                selected_candidates,
                journal_candidates,
                id_validation_target=LAST_REPORT_ID_VALIDATION,
            )
            validated_report = postprocess_result["validated_report"]
            clean_report = postprocess_result["clean_report"]
            dropped_selected_candidates = postprocess_result["dropped_candidates"]
            reconciliation_diagnostics = dict(postprocess_result["id_validation"])

            # Internal IDs remain available through reconciliation and count validation.
            report_id_validation_before_clean = reconciliation_diagnostics.get(
                "after_reconcile", {}
            )
            reconciled_accepted_count = postprocess_result.get(
                "reconciled_accepted_count",
                reconciliation_diagnostics.get("reconciled_accepted_count", 0),
            )
            rendered_report_count = postprocess_result.get(
                "final_rendered_report_count",
                count_report_items(clean_report),
            )
            validated_report_count = rendered_report_count
            selected_final_count_validation_passed = bool(
                reconciliation_diagnostics.get("report_validation_passed", False)
            )

            long_term_coverage = build_final_report_coverage_warning(clean_report, lookback_int, today)
            pdf_bytes = try_markdown_to_pdf_bytes(clean_report)
            dropped_selected_ids = [int(item.get("id", 0) or 0) for item in dropped_selected_candidates]
            dropped_selected_titles = [item.get("title", "") for item in dropped_selected_candidates]
            skipped_report_ids = set(reconciliation_diagnostics.get("skipped_candidate_ids", []))
            dropped_selected_reasons = [
                (
                    "MaiAgent block 缺失、重複或驗證失敗，已排除並記錄。"
                    if int(item.get("id", 0) or 0) in skipped_report_ids
                    else "候選未保留於正式報告，已排除並記錄。"
                )
                for item in dropped_selected_candidates
            ]
            formal_count = rendered_report_count
            postprocess_news_count_delta = formal_count - maiagent_report_response_count
            category_counts = postprocess_result.get(
                "final_count_by_category",
                count_authoritative_report_items_by_category(clean_report),
            )
            has_standard_updates = category_counts.get("規範更新", 0) > 0 or bool(
                re.search(r"(?m)^🔹\s*\[規範更新\]", clean_report)
            )
            prompt_chars = len(report_prompt)
            raw_chars = len(rss_results) + len(ddg_results)
            pipeline_debug_stats = candidate_pool.get("pipeline_debug_stats", {})
            pipeline_counts = pipeline_debug_stats.setdefault("pipeline_counts", {})
            pipeline_counts["selected"] = len(selected_candidates)
            pipeline_counts["reconciled_accepted"] = reconciled_accepted_count
            pipeline_counts["rendered"] = rendered_report_count
            pipeline_stages = pipeline_debug_stats.setdefault("pipeline_stages", {})
            pipeline_stages["selected"] = len(selected_candidates)
            pipeline_stages["final"] = rendered_report_count
            annual_selected_by_bucket: dict[str, int] = {}
            for item in selected_candidates:
                date_value = _candidate_date_obj(item.get("date", ""))
                bucket = str(item.get("date_bucket", "") or "")
                if not bucket and date_value:
                    bucket = f"{date_value.year:04d}-Q{((date_value.month - 1) // 3) + 1}"
                if bucket:
                    annual_selected_by_bucket[bucket] = annual_selected_by_bucket.get(bucket, 0) + 1
            pipeline_debug_stats["annual_selected_by_bucket"] = annual_selected_by_bucket
            pipeline_debug_stats["quality_acceptance"] = {
                **pipeline_debug_stats.get("quality_acceptance", {}),
                "annual_coverage": (
                    "PASS"
                    if lookback_int < 365 or len(annual_selected_by_bucket) >= 3
                    else "WARN"
                ),
            }
            pipeline_debug_stats["selected_count"] = len(selected_candidates)
            operational_topic_selected_count = sum(
                1
                for item in selected_candidates
                if item.get("classification") in {"營運政策", "營運爭議"}
            )
            pipeline_debug_stats["operational_topic_selected_count"] = operational_topic_selected_count
            pipeline_debug_stats["operational_dynamics_selected_count"] = LAST_PYTHON_SELECTION_DEBUG.get(
                "operational_dynamics_selected_count", operational_topic_selected_count
            )
            pipeline_debug_stats["service_opening_selected_count"] = LAST_PYTHON_SELECTION_DEBUG.get(
                "service_opening_selected_count", 0
            )
            forward_selected_candidates = [
                item for item in selected_candidates
                if item.get("search_family") == "forward_technology"
                or item.get("forward_status")
            ]
            pipeline_debug_stats["forward_technology_selected_count"] = len(forward_selected_candidates)
            pipeline_debug_stats["forward_technology_material_selected_count"] = sum(
                1 for item in forward_selected_candidates
                if item.get("innovation_level") in {"A", "B"}
                or item.get("novelty_evidence")
                or item.get("validation_evidence")
                or item.get("benefit_evidence")
            )
            pipeline_debug_stats["track_a_selected_count"] = sum(
                1 for item in forward_selected_candidates if item.get("track_a_gate_pass") is True
            )
            pipeline_debug_stats["track_b_selected_count"] = sum(
                1 for item in forward_selected_candidates if item.get("track_b_gate_pass") is True
            )
            pipeline_debug_stats["strict_selected_count"] = LAST_PYTHON_SELECTION_DEBUG.get("strict_selected_count", 0)
            pipeline_debug_stats["B_added_count"] = LAST_PYTHON_SELECTION_DEBUG.get("B_added_count", 0)
            incident_coverage = build_final_incident_coverage_debug(
                selected_candidates,
                raw_report,
                clean_report,
                global_scope=is_global_scope,
                report_days=lookback_int,
                incident_enabled="重大事故" in selected_types,
            )
            incident_selected_count = incident_coverage["python_incident_selected_count"]
            incident_coverage_warning = incident_coverage["incident_coverage_warning"]
            incident_coverage_reason = incident_coverage["incident_coverage_reason"]
            LAST_PYTHON_SELECTION_DEBUG["incident_search_raw_count"] = pipeline_debug_stats.get("incident_search_raw_count", 0)
            LAST_PYTHON_SELECTION_DEBUG["incident_gate_pass_count"] = pipeline_debug_stats.get("incident_gate_pass_count", 0)
            LAST_PYTHON_SELECTION_DEBUG["incident_selected_count"] = incident_selected_count
            LAST_PYTHON_SELECTION_DEBUG.update(incident_coverage)
            LAST_PYTHON_SELECTION_DEBUG["incident_coverage_warning"] = incident_coverage_warning
            LAST_PYTHON_SELECTION_DEBUG["incident_coverage_reason"] = incident_coverage_reason

            _write_report_markdown_files(clean_report, today)

            report_stats = {
                "raw_count": candidate_pool["raw_count"],
                "deduped_count": candidate_pool["deduped_count"],
                "filtered_count": candidate_pool["filtered_count"],
                "ai_selected_count": len(selected_candidates),
                "formal_count": formal_count,
                "maiagent_report_response_count": maiagent_report_response_count,
                "postprocess_news_count_delta": postprocess_news_count_delta,
                "postprocess_news_count_invariant_passed": formal_count == reconciled_accepted_count,
                "reconciled_accepted_count": reconciled_accepted_count,
                "final_rendered_report_count": rendered_report_count,
                "selected_final_count_invariant_passed": selected_final_count_validation_passed,
                "report_retry_attempted": report_retry_attempted,
                "report_id_validation_before_retry": report_id_validation_before_retry,
                "report_id_validation_after_retry": report_id_validation_after_retry,
                "report_id_validation_before_clean": report_id_validation_before_clean,
                "raw_report_candidate_ids": raw_report_candidate_ids,
                "selected_candidate_ids": reconciliation_diagnostics.get(
                    "selected_candidate_ids", []
                ),
                "model_candidate_ids": reconciliation_diagnostics.get(
                    "model_candidate_ids", []
                ),
                "missing_candidate_ids": reconciliation_diagnostics.get(
                    "missing_ids", []
                ),
                "unknown_candidate_ids": reconciliation_diagnostics.get(
                    "unknown_ids", []
                ),
                "duplicate_candidate_ids": reconciliation_diagnostics.get(
                    "duplicate_ids", []
                ),
                "missing_model_fields": reconciliation_diagnostics.get(
                    "missing_model_fields", {}
                ),
                "parser_failure_reasons": reconciliation_diagnostics.get(
                    "parser_failure_reasons", {}
                ),
                "selected_candidate_id_count": reconciliation_diagnostics.get(
                    "selected_candidate_id_count", len(selected_candidates)
                ),
                "model_candidate_id_count": reconciliation_diagnostics.get(
                    "model_candidate_id_count", len(raw_report_candidate_ids)
                ),
                "selected_to_model_id_coverage": reconciliation_diagnostics.get(
                    "selected_to_model_id_coverage", 0.0
                ),
                "selected_to_final_id_coverage": reconciliation_diagnostics.get(
                    "selected_to_final_id_coverage", 0.0
                ),
                "report_validation_passed": reconciliation_diagnostics.get(
                    "report_validation_passed", False
                ),
                "postprocess_mode": reconciliation_diagnostics.get(
                    "postprocess_mode", ""
                ),
                "validated_report_count": validated_report_count,
                "clean_report_marker_count": len(extract_report_candidate_ids(clean_report)),
                "report_id_reconciliation": LAST_REPORT_ID_VALIDATION,
                "model_report_block_count": reconciliation_diagnostics.get("model_report_block_count", 0),
                "preserved_model_block_count": reconciliation_diagnostics.get("preserved_model_block_count", 0),
                "fallback_block_count": reconciliation_diagnostics.get("fallback_block_count", 0),
                "fallback_reason_counts": reconciliation_diagnostics.get("fallback_reason_counts", {}),
                "merged_event_groups": reconciliation_diagnostics.get("merged_event_groups", []),
                "final_unique_article_count": rendered_report_count,
                "final_count_by_category": category_counts,
                "rendered_count_by_category": category_counts,
                "final_count_by_section": reconciliation_diagnostics.get("final_count_by_section", {}),
                "postprocess_warnings": reconciliation_diagnostics.get("postprocess_warnings", []),
                "prompt_chars": prompt_chars,
                "raw_chars": raw_chars,
                "maiagent_call_count": maiagent_call_count,
                "category_counts": category_counts,
                "journal_count": len(journal_candidates),
                "model_candidate_count": len(model_candidates),
                "source_count": len(combined_sources),
                "ddgs_query_count": search_count,
                "ddgs_general_only_query_count": len(ddgs_general_only_queries(LAST_DDGS_QUERY_STATUSES)),
                "ddgs_search_summary": LAST_DDGS_SEARCH_SUMMARY,
                **LAST_DDGS_SEARCH_SUMMARY,
                "policy_query_count": pipeline_debug_stats.get("policy_query_count", 0),
                "dispute_query_count": pipeline_debug_stats.get("dispute_query_count", 0),
                "service_opening_query_count": pipeline_debug_stats.get("service_opening_query_count", 0),
                "policy_raw_candidates": pipeline_debug_stats.get("policy_raw_candidates", []),
                "dispute_raw_candidates": pipeline_debug_stats.get("dispute_raw_candidates", []),
                "service_opening_raw_candidates": pipeline_debug_stats.get("service_opening_raw_candidates", []),
                "policy_raw_candidate_count": pipeline_debug_stats.get("policy_raw_candidate_count", 0),
                "dispute_raw_candidate_count": pipeline_debug_stats.get("dispute_raw_candidate_count", 0),
                "service_opening_raw_candidate_count": pipeline_debug_stats.get("service_opening_raw_candidate_count", 0),
                "policy_gate_pass_count": pipeline_debug_stats.get("policy_gate_pass_count", 0),
                "dispute_gate_pass_count": pipeline_debug_stats.get("dispute_gate_pass_count", 0),
                "service_opening_gate_pass_count": pipeline_debug_stats.get("service_opening_gate_pass_count", 0),
                "gate_failure_reason_stats": pipeline_debug_stats.get("gate_failure_reason_stats", {}),
                "operational_topic_selected_count": operational_topic_selected_count,
                "operational_dynamics_selected_count": pipeline_debug_stats.get(
                    "operational_dynamics_selected_count", operational_topic_selected_count
                ),
                "service_opening_selected_count": pipeline_debug_stats.get("service_opening_selected_count", 0),
                "eligible_A_count": LAST_PYTHON_SELECTION_DEBUG.get("eligible_A_count", 0),
                "eligible_after_event_dedupe_count": LAST_PYTHON_SELECTION_DEBUG.get("eligible_after_event_dedupe_count", 0),
                "final_selected_count": LAST_PYTHON_SELECTION_DEBUG.get("final_selected_count", len(selected_candidates)),
                "excluded_by_hard_quality_count": LAST_PYTHON_SELECTION_DEBUG.get("excluded_by_hard_quality_count", 0),
                "excluded_by_same_event_count": LAST_PYTHON_SELECTION_DEBUG.get("excluded_by_same_event_count", 0),
                "excluded_by_count_cap_count": LAST_PYTHON_SELECTION_DEBUG.get("excluded_by_count_cap_count", 0),
                "planned_query_count_by_family": pipeline_debug_stats.get("planned_query_count_by_family", {}),
                "executed_query_count_by_family": pipeline_debug_stats.get("executed_query_count_by_family", {}),
                "raw_candidate_count_by_family": pipeline_debug_stats.get("raw_candidate_count_by_family", {}),
                "gate_pass_count_by_category": pipeline_debug_stats.get("gate_pass_count_by_category", {}),
                "forward_technology_query_count": pipeline_debug_stats.get("forward_technology_query_count", 0),
                "forward_technology_raw_count": pipeline_debug_stats.get("forward_technology_raw_count", 0),
                "forward_technology_gate_pass_count": pipeline_debug_stats.get("forward_technology_gate_pass_count", 0),
                "forward_technology_selected_count": pipeline_debug_stats.get("forward_technology_selected_count", 0),
                "forward_technology_material_candidate_count": pipeline_debug_stats.get("forward_technology_material_candidate_count", 0),
                "forward_technology_material_selected_count": pipeline_debug_stats.get("forward_technology_material_selected_count", 0),
                "track_a_gate_pass_count": pipeline_debug_stats.get("track_a_gate_pass_count", 0),
                "track_b_gate_pass_count": pipeline_debug_stats.get("track_b_gate_pass_count", 0),
                "track_a_selected_count": pipeline_debug_stats.get("track_a_selected_count", 0),
                "track_b_selected_count": pipeline_debug_stats.get("track_b_selected_count", 0),
                "track_b_exclusion_reason_counts": pipeline_debug_stats.get("track_b_exclusion_reason_counts", {}),
                "candidate_card_limit": candidate_pool.get("candidate_card_limit", len(candidate_pool["candidate_cards"])),
                "candidate_card_count": len(candidate_pool["candidate_cards"]),
                "elapsed_seconds_total": timings["elapsed_seconds_total"],
                "elapsed_seconds_rss": timings["elapsed_seconds_rss"],
                "elapsed_seconds_ddgs": timings["elapsed_seconds_ddgs"],
                "elapsed_seconds_candidate_pool": timings["elapsed_seconds_candidate_pool"],
                "candidate_pool_timings": candidate_pool.get("candidate_pool_timings", {}),
                "elapsed_seconds_journal": timings["elapsed_seconds_journal"],
                "elapsed_seconds_selection": timings["elapsed_seconds_selection"],
                "elapsed_seconds_python_selection": timings["elapsed_seconds_python_selection"],
                "elapsed_seconds_report": timings["elapsed_seconds_report"],
                "elapsed_seconds_pdf": timings["elapsed_seconds_pdf"],
                "source_health_summary": source_health_summary,
                "pipeline_counts": pipeline_debug_stats.get("pipeline_counts", {}),
                "prefetch_stats": candidate_pool.get("prefetch_stats", {}),
                "prefetch_attempted_count": candidate_pool.get("prefetch_stats", {}).get("attempted_count", 0),
                "prefetch_success_count": candidate_pool.get("prefetch_stats", {}).get("success_count", 0),
                "top_excluded_valuable_count": len(pipeline_debug_stats.get("top_excluded_valuable_candidates", [])),
                "dropped_selected_ids": dropped_selected_ids,
                "dropped_selected_titles": dropped_selected_titles,
                "dropped_selected_reasons": dropped_selected_reasons,
                "strict_selected_count": LAST_PYTHON_SELECTION_DEBUG.get("strict_selected_count", 0),
                "borderline_added_count": LAST_PYTHON_SELECTION_DEBUG.get("borderline_added_count", 0),
                "B_added_count": LAST_PYTHON_SELECTION_DEBUG.get("B_added_count", 0),
                "B_backfill_triggered": LAST_PYTHON_SELECTION_DEBUG.get("B_backfill_triggered", False),
                "B_backfill_cap": LAST_PYTHON_SELECTION_DEBUG.get("B_backfill_cap", 0),
                "B_backfill_considered_count": LAST_PYTHON_SELECTION_DEBUG.get("B_backfill_considered_count", 0),
                "B_backfill_appended_ids": LAST_PYTHON_SELECTION_DEBUG.get("B_backfill_appended_ids", []),
                "B_backfill_append_stage": LAST_PYTHON_SELECTION_DEBUG.get("B_backfill_append_stage", ""),
                "shortfall_before_backfill": LAST_PYTHON_SELECTION_DEBUG.get("shortfall_before_backfill", 0),
                "shortfall_after_backfill": LAST_PYTHON_SELECTION_DEBUG.get("shortfall_after_backfill", 0),
                "backfill_reason": LAST_PYTHON_SELECTION_DEBUG.get("backfill_reason", ""),
                "page_type_exclusion_counts": pipeline_debug_stats.get("page_type_exclusion_counts", {}),
                "no_category_gate_count": pipeline_debug_stats.get("no_category_gate_count", 0),
                "out_of_range_excluded_count": pipeline_debug_stats.get("out_of_range_excluded_count", 0),
                "category_gate_pass_counts": pipeline_debug_stats.get("category_gate_pass_counts", {}),
                "category_reclassification_records": pipeline_debug_stats.get("category_reclassification_records", []),
                "region_resolution_method_counts": pipeline_debug_stats.get("region_resolution_method_counts", {}),
                "A_candidate_count": pipeline_debug_stats.get("A_candidate_count", 0),
                "B_candidate_count": pipeline_debug_stats.get("B_candidate_count", 0),
                "C_candidate_count": pipeline_debug_stats.get("C_candidate_count", 0),
                "source_tier_counts": pipeline_debug_stats.get("source_tier_counts", {}),
                "multilingual_candidate_counts": pipeline_debug_stats.get("multilingual_candidate_counts", {}),
                "normalized_domain_change_count": pipeline_debug_stats.get("normalized_domain_change_count", 0),
                "incident_search_raw_count": pipeline_debug_stats.get("incident_search_raw_count", 0),
                "incident_gate_pass_count": pipeline_debug_stats.get("incident_gate_pass_count", 0),
                "incident_selected_count": incident_selected_count,
                **incident_coverage,
                "incident_coverage_warning": incident_coverage_warning,
                "incident_coverage_reason": incident_coverage_reason,
                "python_evaluated_candidate_count": len(model_candidates),
                "filtered_candidates_entered_python_selection": len(model_candidates) == candidate_pool["filtered_count"],
                "candidate_card_limit_applied_to_python_selection": False,
                "journal_target_count": get_journal_target_count(research_supplement_lookback_days)[0] if include_research_supplement else 0,
                "journal_selected_count": len(journal_candidates),
                "journal_exclusion_stats": _journal_exclusion_stats(journal_excluded_candidates),
                "journal_query_source_outcomes": journal_query_source_outcomes(journal_statuses),
                "journal_shortfall_reason": _journal_shortfall_reason(len(journal_candidates), get_journal_target_count(research_supplement_lookback_days)[0], journal_excluded_candidates) if include_research_supplement else "",
                "journal_summary_conclusion_chars": count_journal_summary_conclusion_chars(clean_report),
                "selection_method": "python_score_rules",
                "long_term_coverage": long_term_coverage,
                "demo_cache_mode": False,
                "include_research_supplement": include_research_supplement,
                "research_supplement_period": run_config.get("research_supplement_period", {}),
                "run_config": run_config,
            }
            st.session_state["latest_report_md"] = clean_report
            st.session_state["latest_report"] = clean_report
            st.session_state["latest_pdf"] = pdf_bytes
            st.session_state["latest_report_summary"] = {
                "formal_count": formal_count,
                "has_standards": has_standard_updates,
                "category_counts": category_counts,
            }
            st.session_state["latest_report_stats"] = report_stats
            st.session_state["latest_run_config"] = run_config
            st.session_state["report_generated"] = True
            st.session_state["latest_debug_info"] = {
                "run_config": run_config,
                "raw_candidates": candidate_pool["raw_candidates"],
                "deduped_candidates": candidate_pool["deduped_candidates"],
                "filtered_candidates": candidate_pool["filtered_candidates"],
                "excluded_candidates": candidate_pool["excluded_candidates"],
                "model_candidates": model_candidates,
                "candidate_cards": candidate_pool["candidate_cards"],
                "selected_candidates": selected_candidates,
                "selected_ids": selected_ids,
                "enriched_selected_candidates": selected_candidates,
                "journal_candidates": journal_candidates,
                "journal_statuses": journal_statuses,
                "journal_excluded_candidates": journal_excluded_candidates,
                "journal_selected_candidates": journal_candidates,
                "journal_exclusion_stats": _journal_exclusion_stats(journal_excluded_candidates),
                "journal_query_source_outcomes": journal_query_source_outcomes(journal_statuses),
                "journal_source_statuses": journal_statuses,
                "journal_target_count": get_journal_target_count(research_supplement_lookback_days)[0] if include_research_supplement else 0,
                "journal_selected_count": len(journal_candidates),
                "journal_shortfall_reason": _journal_shortfall_reason(len(journal_candidates), get_journal_target_count(research_supplement_lookback_days)[0], journal_excluded_candidates) if include_research_supplement else "",
                "journal_summary_conclusion_chars": count_journal_summary_conclusion_chars(clean_report),
                "selection_debug": LAST_PYTHON_SELECTION_DEBUG,
                "pipeline_debug_stats": pipeline_debug_stats,
                "candidate_pool_timings": candidate_pool.get("candidate_pool_timings", {}),
                "ddgs_query_statuses": LAST_DDGS_QUERY_STATUSES,
                "ddgs_search_summary": LAST_DDGS_SEARCH_SUMMARY,
                "ddgs_no_backend_result_queries": ddgs_queries_by_outcome(LAST_DDGS_QUERY_STATUSES, "no_backend_result"),
                "ddgs_all_results_basic_excluded_queries": ddgs_queries_by_outcome(LAST_DDGS_QUERY_STATUSES, "all_results_basic_excluded"),
                "ddgs_query_errors": ddgs_queries_by_outcome(LAST_DDGS_QUERY_STATUSES, "query_error"),
                "ddgs_added_zero_queries": ddgs_queries_by_outcome(LAST_DDGS_QUERY_STATUSES, "added_zero"),
                "ddgs_success_with_raw_queries": ddgs_queries_by_outcome(LAST_DDGS_QUERY_STATUSES, "success_with_raw"),
                "ddgs_general_only_queries": ddgs_general_only_queries(LAST_DDGS_QUERY_STATUSES),
                "prefetch_stats": candidate_pool.get("prefetch_stats", {}),
                "top_excluded_valuable_candidates": pipeline_debug_stats.get("top_excluded_valuable_candidates", []),
                "borderline_candidates": LAST_PYTHON_SELECTION_DEBUG.get("borderline_candidates", []),
                "duplicate_event_records": LAST_PYTHON_SELECTION_DEBUG.get("duplicate_event_records", []),
                "selection_prompt": selection_prompt,
                "selection_response": selection_response,
                "selection_method": "python_score_rules",
                "ai_selection_response": "",
                "python_unselected_stats": python_unselected_stats,
                "report_prompt": report_prompt,
                "initial_raw_report": initial_raw_report,
                "raw_report": raw_report,
                "initial_report_response": initial_raw_report,
                "report_response": raw_report,
                "raw_report_candidate_ids": raw_report_candidate_ids,
                "report_id_validation_before_retry": report_id_validation_before_retry,
                "report_id_validation_after_retry": report_id_validation_after_retry,
                "report_id_validation_before_clean": report_id_validation_before_clean,
                "report_id_reconciliation": LAST_REPORT_ID_VALIDATION,
                "latest_report_md": clean_report,
                "ai_unselected_stats": ai_unselected_stats,
                "dedupe_stats": candidate_pool["dedupe_stats"],
                "exclusion_stats": candidate_pool["exclusion_stats"],
                "source_statuses": source_statuses,
                "source_health_summary": source_health_summary,
                "dropped_selected_ids": dropped_selected_ids,
                "dropped_selected_titles": dropped_selected_titles,
                "dropped_selected_reasons": dropped_selected_reasons,
                "report_stats": report_stats,
                "long_term_coverage": long_term_coverage,
            }

            email_note = "未自動寄送 Email"
            if send_after_generate:
                email_ok = send_current_report_email(
                    st.session_state["latest_report_md"],
                    status_target=status_text,
                    progress_target=progress_bar,
                )
                email_note = "Email 已寄送" if email_ok else "Email 未寄出，請檢查收件設定或 Secrets"
                st.session_state["email_sent"] = bool(email_ok)
            else:
                progress_bar.progress(0.95)

            timings["elapsed_seconds_pdf"] = round(time.perf_counter() - pdf_stage_start, 2)
            timings["elapsed_seconds_total"] = round(time.perf_counter() - run_start, 2)
            report_stats.update(timings)
            st.session_state["latest_report_stats"] = report_stats
            st.session_state["latest_debug_info"]["report_stats"] = report_stats

            summary = st.session_state["latest_report_summary"]
            standards_note = (
                f"｜規範更新：{'包含' if summary['has_standards'] else '未包含'}"
                if standards_enabled
                else ""
            )
            progress_bar.progress(1.0)
            status_text.text("報告產製完成")

        except Exception as e:
            progress_placeholder.empty()
            status_text.error(f"❌ 發生錯誤：{e}")
            st.info("請確認 MaiAgent API Key、Chatbot ID 與 API Base 正確，且該雲端 API 可由目前執行環境連線。")

# ── 報告顯示區 ──────────────────────────────────────
report_display = render_report_display(
    ReportDisplayContext(
        current_run_config=current_run_config,
        report_period_label=report_period_label,
        current_app_hash=current_app_hash,
        last_pdf_error=LAST_PDF_ERROR,
        progress_placeholder=progress_placeholder,
        status_placeholder=status_placeholder,
        candidate_marker_remover=remove_internal_candidate_markers,
        final_report_normalizer=normalize_final_report_md,
        report_markdown_renderer=display_report_markdown,
        pdf_renderer=try_markdown_to_pdf_bytes,
        download_filename_builder=build_report_download_filename,
        email_sender=send_current_report_email,
    )
)
source_statuses = report_display.source_statuses
display_run_config = report_display.display_run_config
display_report_label = report_display.display_report_label
report_stats = report_display.report_stats
latest_report_md = report_display.latest_report_md
report_to_show = report_display.report_to_show

# ── 開發者除錯資訊 ───────────────────────────────────
def _developer_debug_context() -> DeveloperDebugContext:
    return DeveloperDebugContext(
        current_run_config=current_run_config,
        latest_run_config=st.session_state.get("latest_run_config"),
        app_source_hash=st.session_state.get("_app_source_hash", ""),
        latest_report_md=st.session_state.get("latest_report_md", ""),
        source_health_summary_builder=build_source_health_summary,
        candidate_marker_remover=remove_internal_candidate_markers,
        now_provider=datetime.datetime.now,
    )


def _debug_candidate_rows(items: list[dict]) -> list[dict]:
    return service_debug_candidate_rows(items)


def _json_safe(value):
    return service_json_safe(value)


def _debug_strip_internal_fields(value):
    return service_debug_strip_internal_fields(value)


def build_developer_debug_payload(debug_info: dict, report_stats: dict, source_statuses: list[dict]) -> dict:
    return service_build_developer_debug_payload(
        debug_info,
        report_stats,
        source_statuses,
        context=_developer_debug_context(),
    )


debug_info = st.session_state.get("latest_debug_info", {})
render_developer_debug_ui(
    DebugUiContext(
        show_developer_info=show_developer_info,
        report_stats=report_stats,
        source_statuses=source_statuses,
        display_run_config=display_run_config,
        payload_builder=build_developer_debug_payload,
        download_filename_builder=build_report_download_filename,
    )
)
