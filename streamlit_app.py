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
    remove_legacy_report_fields,
    remove_missing_data_disclaimers,
    short_url_label,
    simplify_formal_report_format,
    simplify_taipei_insight,
    strip_candidate_id_markers,
    strip_event_summary_source_lead_in,
    strip_internal_report_fields,
    strip_report_footer_lines,
    apply_final_report_footer as service_apply_final_report_footer,
    final_report_statistics_line as service_final_report_statistics_line,
    merge_operational_report_sections as service_merge_operational_report_sections,
    normalize_report_section_numbering as service_normalize_report_section_numbering,
    normalize_research_section_heading as service_normalize_research_section_heading,
    sanitize_report_text as service_sanitize_report_text,
    strip_unselected_report_sections as service_strip_unselected_report_sections,
    strip_unselected_types_from_title as service_strip_unselected_types_from_title,
)
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
from pdf_exporter import (
    streamlit_markdown_to_pdf_bytes as streamlit_pdf_renderer,
    pdf_rich_text as shared_pdf_rich_text,
    _soft_wrap_long_tokens as shared_soft_wrap_long_tokens,
)
from email_service import send_streamlit_email
from config import *
import article_selector as selector_service
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
    page_title="國際捷運技術週報 AI 系統",
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
st.session_state["_app_source_hash"] = current_app_hash

# ── 日期與常數 ──────────────────────────────────────────────
today = datetime.date.today()
APP_DIR = Path(__file__).resolve().parent
REPORTS_DIR = APP_DIR / "reports"

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
        default_selected_types=DEFAULT_SELECTED_TYPES,
        advanced_types=ADVANCED_TYPES,
        normal_lookback_options=NORMAL_LOOKBACK_OPTIONS,
        advanced_lookback_options=ADVANCED_LOOKBACK_OPTIONS,
        report_period_labels=REPORT_PERIOD_LABELS,
        long_term_target_labels=LONG_TERM_TARGET_LABELS,
        default_regions=DEFAULT_REGIONS,
        advanced_regions=ADVANCED_REGIONS,
        standards_watchlist=STANDARDS_WATCHLIST,
        get_research_supplement_lookback_days=get_research_supplement_lookback_days,
    )
)
recipient_input = sidebar_selection.recipient_input
lookback_days = sidebar_selection.lookback_days
selected_types = sidebar_selection.selected_types
standards_enabled = sidebar_selection.standards_enabled
standard_count = sidebar_selection.standard_count
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
            scope_mode=scope_mode,
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

    category_gate_pass_counts: dict[str, int] = {}
    for item in filtered_candidates or []:
        for gate, enabled in (item.get("category_gates") or {}).items():
            if enabled:
                category_gate_pass_counts[gate] = category_gate_pass_counts.get(gate, 0) + 1
    gate_pass_count = sum(1 for item in filtered_candidates or [] if any((item.get("category_gates") or {}).values()))
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
        "top_excluded_valuable_candidates": build_top_excluded_valuable_candidates(excluded_candidates, 20),
        "page_type_exclusion_counts": _count_by(excluded_candidates, "page_type"),
        "no_category_gate_count": sum(1 for item in excluded_candidates or [] if item.get("final_exclude_reason") == "no_category_gate" or item.get("exclude_reason") == "no_category_gate"),
        "category_gate_pass_counts": category_gate_pass_counts,
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
    }


_selector_api = build_selector_api(
    selected_types=selected_types, active_regions=active_regions,
    lookback_days=lookback_days, lookback_int=lookback_int,
    fast_mode_enabled=fast_mode_enabled, is_global_scope=is_global_scope, today=today,
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
_is_short_term_service_notice = _selector_api["_is_short_term_service_notice"]
_compute_passes_high_value_policy_gate = _selector_api["_compute_passes_high_value_policy_gate"]
_passes_high_value_policy_gate = _selector_api["_passes_high_value_policy_gate"]
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
    selected = _service_select_candidates_by_python(model_candidates)
    LAST_PYTHON_SELECTION_DEBUG = selector_service.LAST_PYTHON_SELECTION_DEBUG
    return selected


def _profile_timing_add(timings: dict | None, key: str, elapsed: float) -> None:
    if timings is not None:
        timings[key] = float(timings.get(key, 0.0) or 0.0) + max(0.0, elapsed)


def _profile_call(timings: dict, key: str, function, *args):
    started = time.perf_counter()
    try:
        return function(*args)
    finally:
        _profile_timing_add(timings, key, time.perf_counter() - started)


def _prepare_candidate_objects(parsed_candidates: list[dict], parsing_seconds: float = 0.0) -> dict:
    pool_started = time.perf_counter()
    candidate_pool_timings = {
        "unit": "seconds",
        "parsing": parsing_seconds,
        "region_detection": 0.0,
        "text_normalization": 0.0,
        "page_type": 0.0,
        "category_gates": 0.0,
        "scoring": 0.0,
        "event_fingerprint": 0.0,
        "dedupe": 0.0,
        "preliminary_filter": 0.0,
        "prefetch": 0.0,
        "total": 0.0,
        "candidate_count": len(parsed_candidates or []),
    }
    raw_candidates: list[dict] = []
    hard_excluded_candidates: list[dict] = []
    hard_exclusion_stats: dict[str, int] = {}
    for candidate in parsed_candidates or []:
        _profile_call(candidate_pool_timings, "region_detection", _canonical_candidate_region, candidate)
        _profile_call(candidate_pool_timings, "text_normalization", _candidate_selection_text, candidate)
        page_type, page_type_reason = _profile_call(candidate_pool_timings, "page_type", _candidate_page_type, candidate)
        candidate["page_type"] = page_type
        candidate["page_type_reason"] = page_type_reason
        candidate.update(_profile_call(candidate_pool_timings, "category_gates", evaluate_category_gates, candidate))
        hard_reason = _profile_call(candidate_pool_timings, "preliminary_filter", hard_low_value_candidate_reason, candidate)
        if hard_reason:
            hard_excluded_candidates.append(annotate_candidate_for_scheme_d(candidate, hard_reason, candidate_pool_timings))
            hard_exclusion_stats[hard_reason] = hard_exclusion_stats.get(hard_reason, 0) + 1
        else:
            raw_candidates.append(annotate_candidate_for_scheme_d(candidate, profile_timings=candidate_pool_timings))

    deduped_candidates, dedupe_stats = _profile_call(candidate_pool_timings, "dedupe", dedupe_candidates, raw_candidates)
    prefetch_started = time.perf_counter()
    prefetch_stats = prefetch_candidates_before_filter(deduped_candidates)
    _profile_timing_add(candidate_pool_timings, "prefetch", time.perf_counter() - prefetch_started)
    filtered_candidates: list[dict] = []
    excluded_candidates: list[dict] = hard_excluded_candidates.copy()
    exclusion_stats: dict[str, int] = hard_exclusion_stats.copy()

    for candidate in deduped_candidates:
        if candidate.get("prefetch_status") == "success":
            refreshed = annotate_candidate_for_scheme_d(candidate, profile_timings=candidate_pool_timings)
            candidate.clear()
            candidate.update(refreshed)
        keep, reason = _profile_call(candidate_pool_timings, "preliminary_filter", preliminary_filter_candidate, candidate)
        if keep:
            candidate["exclude_reason"] = ""
            candidate["final_exclude_reason"] = ""
            candidate["selection_stage"] = "candidate_pool"
            filtered_candidates.append(candidate)
        else:
            candidate["exclude_reason"] = reason
            candidate["final_exclude_reason"] = reason
            candidate["selection_stage"] = "excluded"
            excluded_candidates.append(candidate)
            exclusion_stats[reason] = exclusion_stats.get(reason, 0) + 1

    filtered_candidates = sorted(
        filtered_candidates,
        key=lambda item: (
            -int(item.get("python_score", 0) or 0),
            _source_tier_rank(item.get("source_tier", "C_media")),
            _quality_rank(item.get("source_quality", "B")),
            0 if item.get("source_type") in {"官方 RSS", "Google News 代理"} else 1,
            -_date_sort_key(item),
        ),
    )
    candidate_limit = min(get_selection_candidate_limit(lookback_int, fast_mode=fast_mode_enabled), MAX_SELECTION_CANDIDATES)
    model_candidates = [dict(item, id=idx, candidate_id=idx) for idx, item in enumerate(filtered_candidates, 1)]
    pipeline_debug_stats = build_pipeline_debug_stats(raw_candidates, deduped_candidates, model_candidates, excluded_candidates, prefetch_stats)
    candidate_pool_timings["total"] = time.perf_counter() - pool_started + parsing_seconds
    for key, value in list(candidate_pool_timings.items()):
        if isinstance(value, float):
            candidate_pool_timings[key] = round(value, 4)
    pipeline_debug_stats["candidate_pool_timings"] = candidate_pool_timings
    candidate_cards = [build_candidate_card(candidate) for candidate in model_candidates[:candidate_limit]]
    return {
        "raw_candidates": raw_candidates,
        "deduped_candidates": deduped_candidates,
        "filtered_candidates": model_candidates,
        "excluded_candidates": excluded_candidates,
        "model_candidates": model_candidates,
        "candidate_cards": candidate_cards,
        "candidate_card_limit": candidate_limit,
        "dedupe_stats": dedupe_stats,
        "prefetch_stats": prefetch_stats,
        "exclusion_stats": exclusion_stats,
        "pipeline_debug_stats": pipeline_debug_stats,
        "candidate_pool_timings": candidate_pool_timings,
        "raw_count": len(raw_candidates),
        "deduped_count": len(deduped_candidates),
        "filtered_count": len(model_candidates),
    }


def prepare_candidate_pool(raw_rss: str, raw_ddg: str) -> dict:
    parsing_started = time.perf_counter()
    parsed_candidates = parse_rss_candidates(raw_rss) + parse_ddg_candidates(raw_ddg)
    parsing_seconds = time.perf_counter() - parsing_started
    return _prepare_candidate_objects(parsed_candidates, parsing_seconds)


def build_long_term_coverage_warning(candidates: list[dict]) -> dict:
    if lookback_int not in ADVANCED_LOOKBACK_OPTIONS:
        return {"long_term_coverage_warning": False, "reason": ""}
    date_objs = [
        date_obj for date_obj in (_candidate_date_obj(candidate.get("date", "")) for candidate in candidates or [])
        if date_obj
    ]
    if not date_objs:
        return {
            "long_term_coverage_warning": True,
            "reason": "長期回顧候選資料缺少可解析日期，無法確認是否完整涵蓋本期。",
        }
    earliest = min(date_objs)
    expected_start = today - datetime.timedelta(days=lookback_int)
    recent_cutoff = today - datetime.timedelta(days=min(60, max(30, lookback_int // 5)))
    if earliest > recent_cutoff:
        return {
            "long_term_coverage_warning": True,
            "reason": "來源回傳資料多集中於近期，年度回顧可能無法完整代表全年。" if lookback_int == 365 else "來源回傳資料多集中於近期，長期回顧可能無法完整代表整個期間。",
            "earliest_candidate_date": earliest.isoformat(),
            "expected_start": expected_start.isoformat(),
        }
    return {
        "long_term_coverage_warning": False,
        "reason": "",
        "earliest_candidate_date": earliest.isoformat(),
        "expected_start": expected_start.isoformat(),
    }


def _unique_limited(values: list[str], limit: int = 5) -> list[str]:
    output: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in output:
            output.append(cleaned)
        if len(output) >= limit:
            break
    return output


def _annual_observation_dates_are_recent(candidates: list[dict]) -> bool:
    date_objs = [
        date_obj for date_obj in (_candidate_date_obj(candidate.get("date", "")) for candidate in candidates or [])
        if date_obj
    ]
    if not date_objs:
        return False
    return min(date_objs) > today - datetime.timedelta(days=60)


def _annual_observation_themes(candidates: list[dict]) -> list[str]:
    theme_terms = [
        ("號誌與列車控制", ["cbtc", "signalling", "signaling", "signal", "train control", "號誌", "信號"]),
        ("自動化與無人駕駛", ["driverless", "automation", "automated", "unattended train", "自動", "無人"]),
        ("車輛與車隊更新", ["rolling stock", "fleet", "trainset", "new train", "車輛", "列車"]),
        ("月臺門與車站設備", ["platform screen door", "platform doors", "psd", "elevator", "escalator", "月臺門", "月台門", "電梯", "電扶梯"]),
        ("供電與能源管理", ["power supply", "traction power", "substation", "third rail", "energy", "供電", "牽引", "變電", "能源"]),
        ("通訊、資安與資料治理", ["communications", "telecom", "radio", "5g", "lte", "cyber", "data", "通訊", "資安", "資料"]),
        ("維修監測與影像分析", ["maintenance", "monitoring", "condition monitoring", "video", "camera", "ai", "維修", "監測", "影像", "AI"]),
        ("AFC 與票務系統", ["afc", "ticketing", "fare gate", "fare", "票務", "票閘", "票價"]),
    ]
    combined = " ".join(
        f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('source', '')}"
        for candidate in candidates or []
    )
    return [label for label, terms in theme_terms if _contains_any_term(combined, terms)]


def _annual_observation_report_blocks(report_md: str) -> list[str]:
    formal_area = re.split(
        r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:國際學術期刊|技術研究補充)\s*$",
        report_md or "",
        maxsplit=1,
    )[0]
    return re.findall(
        r"(?ms)^\s*(🔹\s*\[(?:技術新知|重大事故|營運政策|營運爭議|規範更新)\].*?)"
        r"(?=^\s*🔹\s*\[[^\]]+\]|^\s*#{0,6}\s*[一二三四五六七八九十]\s*、|^\s*📊|^\s*⏰|\Z)",
        formal_area,
    )


def _iter_calendar_months(start_date: datetime.date, end_date: datetime.date) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        months.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


def build_final_report_coverage_warning(
    final_report_md: str,
    report_days: int,
    report_end: datetime.date | None = None,
) -> dict:
    """Measure long-term coverage from formal news only, never journal entries."""
    days = int(report_days or 0)
    if days not in {90, 180, 365}:
        return {"long_term_coverage_warning": False, "reason": ""}
    end_date = report_end or today
    start_date = end_date - datetime.timedelta(days=days)
    blocks = _annual_observation_report_blocks(final_report_md)
    dates: list[datetime.date] = []
    for block in blocks:
        match = re.search(r"發布/事件日期\s*[：:]\s*(\d{4}-\d{2}-\d{2})", block)
        date_obj = _candidate_date_obj(match.group(1)) if match else None
        if date_obj and start_date <= date_obj <= end_date + datetime.timedelta(days=1):
            dates.append(date_obj)

    month_keys = _iter_calendar_months(start_date, end_date)
    monthly_counts = {
        f"{year:04d}-{month:02d}": sum(1 for value in dates if (value.year, value.month) == (year, month))
        for year, month in month_keys
    }
    quarter_counts: dict[str, int] = {}
    for value in dates:
        key = f"{value.year:04d}-Q{((value.month - 1) // 3) + 1}"
        quarter_counts[key] = quarter_counts.get(key, 0) + 1

    result = {
        "long_term_coverage_warning": False,
        "reason": "",
        "formal_news_with_valid_date_count": len(dates),
        "coverage_bucket_type": "quarter" if days == 365 else "month",
        "coverage_buckets": quarter_counts if days == 365 else monthly_counts,
        "monthly_coverage_buckets": monthly_counts,
        "quarterly_coverage_buckets": quarter_counts,
    }
    if not dates:
        result.update({
            "long_term_coverage_warning": True,
            "reason": "最終正式新聞沒有可解析日期，無法確認長期報告覆蓋。",
            "max_consecutive_empty_months": len(month_keys),
            "recent_60_day_count": 0,
            "recent_60_day_share": 0.0,
        })
        return result

    max_empty_streak = 0
    current_empty_streak = 0
    for count in monthly_counts.values():
        current_empty_streak = current_empty_streak + 1 if count == 0 else 0
        max_empty_streak = max(max_empty_streak, current_empty_streak)
    recent_cutoff = end_date - datetime.timedelta(days=60)
    recent_count = sum(1 for value in dates if value >= recent_cutoff)
    recent_share = recent_count / len(dates)
    result.update({
        "max_consecutive_empty_months": max_empty_streak,
        "recent_60_day_count": recent_count,
        "recent_60_day_share": round(recent_share, 4),
    })
    if days == 365:
        reasons: list[str] = []
        if max_empty_streak >= 3:
            reasons.append("最終正式新聞存在連續 3 個月以上的空白期間")
        if recent_share > 0.60:
            reasons.append("超過 60% 最終正式新聞集中於最近 60 天")
        if reasons:
            result["long_term_coverage_warning"] = True
            result["reason"] = "；".join(reasons) + "。"
    return result


def _annual_observation_report_dates_are_recent(blocks: list[str]) -> bool:
    dates = []
    for block in blocks or []:
        match = re.search(r"發布/事件日期\s*[：:]\s*(\d{4}-\d{2}-\d{2})", block)
        date_obj = _candidate_date_obj(match.group(1)) if match else None
        if date_obj:
            dates.append(date_obj)
    return bool(dates) and min(dates) > today - datetime.timedelta(days=60)


def build_annual_observation_section(final_report_md: str) -> str:
    if lookback_int != 365:
        return ""
    blocks = _annual_observation_report_blocks(final_report_md)
    counts = count_report_items_by_category(final_report_md)
    categories = ("技術新知", "重大事故", "營運政策", "營運爭議")
    count_text = "、".join(f"{category}{counts.get(category, 0)}則" for category in categories)
    sentences = [f"本年度回顧依最終正式報告整理，共收錄{count_text}。"]
    if not blocks:
        sentences.append("本年度未取得可供歸納的正式新聞，以下列最終章節與統計為準。")
        return "## 年度觀察重點\n" + "".join(sentences)

    regions = _unique_limited([
        match.group(1).strip()
        for block in blocks
        for match in [re.search(r"國家/地區\s*[：:]\s*([^\n]+)", block)]
        if match and match.group(1).strip() not in {"未判定", "國際研究"}
    ])
    positive_categories = [category for category in categories if counts.get(category, 0) > 0]
    if positive_categories:
        max_count = max(counts.get(category, 0) for category in positive_categories)
        leading = [category for category in positive_categories if counts.get(category, 0) == max_count]
        sentences.append(f"新聞類型以{'、'.join(leading)}為主。")
    if regions:
        sentences.append(f"案例主要分布於{'、'.join(regions)}。")

    report_candidates = [{"title": block, "snippet": block, "source": ""} for block in blocks]
    themes = _unique_limited(_annual_observation_themes(report_candidates), 4)
    if themes:
        sentences.append(f"從最終新聞內容可見，觀察重點集中在{'、'.join(themes)}等都市軌道議題。")
    if _annual_observation_report_dates_are_recent(blocks):
        sentences.append("最終新聞日期多集中於近期，年度趨勢解讀應以本次實際輸出的案例範圍為準。")
    return "## 年度觀察重點\n" + "".join(sentences)


def _remove_annual_observation_section(report_md: str) -> str:
    return re.sub(
        r"(?ms)^\s*#{1,6}\s*年度觀察重點\s*$.*?"
        r"(?=^\s*#{0,6}\s*[一二三四五六七八九十]\s*、|^\s*📊|^\s*⏰|\Z)",
        "",
        report_md or "",
        count=1,
    ).strip()


def insert_annual_observation_section(report_md: str) -> str:
    if lookback_int != 365:
        return report_md
    report_without_observation = _remove_annual_observation_section(report_md)
    section = build_annual_observation_section(report_without_observation)
    if not section:
        return report_without_observation
    lines = report_without_observation.splitlines()
    insert_idx = 1 if lines and lines[0].lstrip().startswith("#") else 0
    while insert_idx < len(lines) and (not lines[insert_idx].strip() or lines[insert_idx].lstrip().startswith(">")):
        insert_idx += 1
    before = "\n".join(lines[:insert_idx]).rstrip()
    after = "\n".join(lines[insert_idx:]).lstrip()
    return f"{before}\n\n{section}\n\n{after}".strip()


def format_selection_candidate(candidate: dict) -> str:
    source_url = _effective_source_url(candidate)
    prompt_card = {
        "id": candidate.get("id", ""),
        "title": candidate.get("title", ""),
        "date": candidate.get("date", ""),
        "source_display": candidate.get("source_display", candidate.get("source", "")),
        "source_domain": candidate.get("source_domain") or _domain_from_url(source_url) or _extract_domain_hint(source_url),
        "region": candidate.get("region", "未判定"),
        "preliminary_type": candidate.get("preliminary_type", infer_preliminary_type(candidate)),
        "python_score": candidate.get("python_score", 0),
        "short_snippet": candidate.get("short_snippet", _shorten(candidate.get("snippet", ""), CANDIDATE_SNIPPET_CHARS)),
        "url": source_url,
    }
    return json.dumps(prompt_card, ensure_ascii=False)


def _selected_report_sections() -> str:
    lines: list[str] = []
    if "技術新知" in selected_types:
        lines.append("一、技術新知")
    if "重大事故" in selected_types:
        lines.append("二、重大事故")
    if {"營運政策", "營運爭議"}.intersection(selected_types):
        lines.append("三、營運議題")
    if "規範更新" in selected_types:
        lines.append("四、規範更新")
    if include_research_supplement:
        lines.append(research_section_heading(markdown=False))
    return "\n".join(lines) if lines else "無"


def _section_number_for_index(index: int) -> str:
    numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    if 1 <= index <= len(numerals):
        return numerals[index - 1]
    return str(index)


def research_section_heading(markdown: bool = False) -> str:
    section_number = "五" if standards_enabled or "規範更新" in selected_types else "四"
    heading = f"{section_number}、國際學術期刊"
    return f"## {heading}" if markdown else heading


def _selected_empty_section_rules() -> str:
    lines: list[str] = []
    for category in ("技術新知", "重大事故"):
        if category in selected_types:
            lines.append(f"- {category}若無符合資料，請寫：「{EMPTY_TEXT_BY_TYPE[category]}」")
    if {"營運政策", "營運爭議"}.intersection(selected_types):
        lines.append("- 營運政策與營運爭議皆無符合資料時，請只寫：「本期未發現符合條件之營運議題。」")
    if "規範更新" in selected_types:
        lines.append(f"- 規範更新若無符合資料，請寫：「{EMPTY_TEXT_BY_TYPE['規範更新']}」")
    return "\n".join(lines) if lines else "- 未勾選新聞類型時，不得自行新增章節。"


def _selected_stats_template() -> str:
    parts = [f"{category} N 則" for category in ADVANCED_TYPES if category in selected_types]
    return " / ".join(parts) if parts else "無"


def _policy_selection_rule() -> str:
    if "營運政策" not in selected_types:
        return ""
    weekly_limit = "7 天週報中，營運政策原則最多 4～5 則。" if lookback_int == 7 else "營運政策需保留具制度、系統或治理價值者。"
    return f"""
- {weekly_limit}
- 營運政策優先：票價政策且涉及 AFC/票務系統、大型活動疏運且含班距/加班車/人流或車站管制、新線通車/試營運/系統轉換、建設治理/資產更新、維修窗口且有明確工程或系統影響。
- 營運政策降權或排除：單純假日提醒、活動搭乘資訊、週末服務公告、路線查詢/trip result/route page，或沒有班距、加班車、車站管制、人流管理、設備或系統資訊者。
- 同一週多則大型活動、假日或週末服務公告，請合併為 1 則綜合案例，不要逐則拆列；不得為了湊數納入低價值營運公告。
""".strip()


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
    candidate_block = "\n\n".join(format_selection_candidate(candidate) for candidate in candidates)
    if not candidate_block:
        candidate_block = "本期 Python 初篩後沒有候選新聞。請回傳空的 selected_ids 清單。"
    selected_types_str = "、".join(selected_types) if selected_types else "無"
    example_type = selected_types[0] if selected_types else "技術新知"
    output_range = get_selection_output_range(lookback_int)
    return f"""
請依照你在 MaiAgent 後台設定的國際捷運技術週報角色指令，根據以下候選資料執行第一階段選題。不得自行搜尋或補充候選資料以外的新聞、日期、供應商、技術細節或統計數據。

本次是第一階段選題任務；請只判斷候選資料是否適合納入正式報告，不要撰寫正式新聞段落。
報告期間：{date_range}
使用者勾選的新聞類型：{selected_types_str}
需要選出的數量：{output_range} 則；高品質候選不足時可少於目標，但不要用低價值資料湊數。

請只使用候選資料中的 id 進行選題；category 必須從使用者勾選的新聞類型中選擇。不得輸出 Markdown 說明。

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


def _json_loads_loose(text: str):
    candidates = []
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text or "", flags=re.DOTALL | re.IGNORECASE)
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


def _truthy_report_flag(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    text = str(value).strip().casefold()
    return text not in {"false", "no", "否", "不納入", "不建議", "0"}


def parse_selection_response(response_text: str, candidates: list[dict]) -> list[dict]:
    candidate_map = {int(candidate["id"]): candidate for candidate in candidates}
    selected: list[dict] = []
    seen_ids: set[int] = set()

    parsed = _json_loads_loose(response_text)
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
        if not _truthy_report_flag(item.get("include_in_report", item.get("是否建議納入正式週報"))):
            continue
        classification = (
            item.get("classification")
            or item.get("category")
            or item.get("分類")
            or item.get("topic_type")
            or item.get("類型")
            or item.get("preliminary_type")
            or "技術新知"
        )
        if classification not in ADVANCED_TYPES:
            classification = next((category for category in ADVANCED_TYPES if category in str(item)), "技術新知")
        if classification not in selected_types:
            continue
        candidate = dict(candidate_map[candidate_id])
        candidate["classification"] = classification
        candidate["selected_reason"] = item.get("selected_reason") or item.get("入選理由") or item.get("reason") or "MaiAgent 第一階段選題入選。"
        candidate["selection_priority"] = item.get("priority", "")
        candidate["merge_group"] = item.get("merge_group", "")
        candidate["include_in_report"] = True
        selected.append(candidate)
        seen_ids.add(candidate_id)
        if len(selected) >= SELECTION_MAX_ITEMS:
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

    for candidate_id in fallback_ids[:SELECTION_MAX_ITEMS]:
        candidate = dict(candidate_map[candidate_id])
        candidate["classification"] = next((category for category in selected_types if category in response_text), selected_types[0] if selected_types else "技術新知")
        candidate["selected_reason"] = "MaiAgent 第一階段回應未完全符合 JSON，已依回應中的候選編號納入。"
        candidate["include_in_report"] = True
        selected.append(candidate)

    if selected:
        return selected

    fallback_count = min(SELECTION_MIN_ITEMS, len(candidates), SELECTION_MAX_ITEMS)
    for candidate in candidates[:fallback_count]:
        backup = dict(candidate)
        if "規範更新" in selected_types and _is_standard_update_candidate(f"{backup.get('title')} {backup.get('snippet')} {backup.get('url')}", True):
            backup["classification"] = "規範更新"
        else:
            backup["classification"] = selected_types[0] if selected_types else "技術新知"
        backup["selected_reason"] = "MaiAgent 第一階段回應格式無法解析；依 Python 初篩排序備援納入。"
        backup["include_in_report"] = True
        selected.append(backup)
    return selected


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
    source_url = _effective_source_url(candidate)
    source_display = candidate.get("source_display") or source_label_for_report(
        candidate.get("source", ""), candidate.get("url", ""), candidate.get("source_href", ""), candidate.get("source_tier", "")
    )
    prompt_item = {
        "candidate_id": candidate.get("candidate_id", candidate.get("id", "")),
        "title": candidate.get("title", ""),
        "date": candidate.get("date", ""),
        "source_display": source_display,
        "source_verb": candidate.get("source_verb", source_verb_for_report(candidate.get("source_tier", ""), source_display)),
        "region": candidate.get("region", "未判定"),
        "preliminary_type": candidate.get("classification") or candidate.get("preliminary_type", infer_preliminary_type(candidate)),
        "url": source_url,
        "snippet": _shorten(candidate.get("snippet", ""), REPORT_SNIPPET_CHARS),
        "source_domain": candidate.get("source_domain") or _domain_from_url(source_url) or _extract_domain_hint(source_url),
        "supplemental_sources": candidate.get("supplemental_sources", []),
    }
    return json.dumps(prompt_item, ensure_ascii=False)


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
    selected_types_str = "、".join(selected_types) if selected_types else "無"
    selected_sections = _selected_report_sections()
    selected_empty_rules = _selected_empty_section_rules()
    research_heading = research_section_heading(markdown=False)
    candidate_block = "\n\n".join(format_report_candidate(candidate) for candidate in selected_candidates)
    if not candidate_block:
        candidate_block = "Python 選題流程沒有入選新聞。請只依已勾選章節輸出沒有符合資料的固定文字，不得自行補新聞。"

    journal_input_section = ""
    if include_research_supplement:
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
                    "snippet": _shorten(item.get("snippet", ""), REPORT_SNIPPET_CHARS),
                }, ensure_ascii=False)
                for item in journal_candidates
            )
        else:
            journal_block = "無符合期間條件且具明確發表日期之研究候選。"
        journal_input_section = f"""
## 國際學術與技術研究補充候選
研究補充已啟用；本次研究補充期間為{research_supplement_period_label}（{research_supplement_start_date.isoformat()} 至 {today.isoformat()}）。

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
- 各篇期刊之間保留一個空行，不得使用「---」分隔。
- 所有期刊完成後，另起一行輸出「### 學術期刊綜合結論」，並撰寫 300～500 字完整段落。
- 綜合結論僅能依候選研究歸納共同技術趨勢及對臺北捷運局之啟示，不得杜撰研究成果。
- 請勿在期刊章節後輸出本期統計、報告產出時間或系統資訊。

若沒有候選，請只寫：「本期未發現符合期間條件且具明確發表日期之國際學術或技術研究資料。」

研究候選：
{journal_block}
""".strip()
    journal_input_text = f"\n\n{journal_input_section}" if journal_input_section else ""

    return f"""
請依照 MaiAgent 後台設定的國際捷運技術週報角色指令，根據以下已入選新聞撰寫正式報告。不得自行搜尋，不得補充候選資料以外的新聞、日期、國家、城市、路線、供應商、技術細節、事故原因、統計數據或金額。

本次是第二階段正式報告撰寫任務。
報告標題：{report_title}
資料涵蓋期間：{date_range}
報導範圍：{report_scope_label}
勾選類型：{selected_types_str}
正式報告章節：
{selected_sections}
空章節文字：
{selected_empty_rules}

正式報告開頭固定：
# {report_title}
> 資料涵蓋期間：{date_range}
> 報導範圍：{report_scope_label}

正式報告每則新聞請使用以下固定格式，不得改成表格、簡報式卡片或多層條列，不得自行增減欄位，不得新增「技術關鍵字」欄位，不得把「臺北捷運局啟示」拆成子欄位：
🔹 [新聞類型] 繁體中文新聞標題

• 發布/事件日期：YYYY-MM-DD

• 國家/地區：

• 相關機電系統：

• 事件摘要：
完整段落

• 臺北捷運局啟示：
完整段落

• 資料來源：

每則新聞之間使用：
---

必要寫作提醒：
- 只根據下方已入選新聞資料撰寫；正式報告只輸出已勾選章節，不得輸出未勾選類型。
- 營運政策與營運爭議統一置於「三、營運議題」章節；每則仍保留 [營運政策] 或 [營運爭議] 類型標記，並依日期新至舊排列。不得另外輸出「三、營運政策」或「四、營運爭議」。
- 下方共 {len(selected_candidates)} 則新聞已由 Python 完成「入選」。所有不同且符合範圍的事件原則上均須保留。同一事件的不同來源必須合併；明顯屬於非都市軌道、刑事治安、旅遊、公車或其他禁止範圍的候選可排除。不得自行新增候選資料以外的事件。
- 每則正式新聞標題正前方必須原樣輸出 `<!-- candidate_id: N -->`，其中 N 必須等於候選資料的 candidate_id；不得省略、改號或自行產生 ID。
- 除非 Python 候選本身已完成同事件合併，輸出的正式新聞則數必須等於 {len(selected_candidates)}；不得因翻譯標題、摘要相近或來源網址相似而省略候選。
- 資料來源 URL 必須逐字沿用候選資料的 url；禁止改寫、縮成首頁 domain 或自行產生網址。Python 會在輸出後再次以 candidate_id 驗證並覆寫 URL。
- 正式報告新聞數可因同一事件合併或明顯錯誤候選排除而小於入選數，不得因後處理或自行新增事件而大於本次入選數。
- 候選資料中的 preliminary_type、classification、region、source_display 與 source_verb 均為程式初步判定，不是最終答案。請根據 title、snippet、date、source_domain 與 url 重新判斷新聞類型、事件所在地及來源性質。
- 可在本次已勾選的新聞類型之間更正分類；不同且符合範圍的事件原則上保留，同一事件必須合併，明顯錯誤候選可排除，且不得新增未勾選章節。

新聞類型判斷原則：
- 技術新知：原始資料明確描述都市軌道機電設備或系統的新導入、擴充、升級、汰換、改善、測試驗證或正式投入營運。包括新型車輛投入營運、生物辨識或 AFC 系統應用、新票閘設備、電梯或電扶梯汰換、號誌與列車控制、供電、通訊、月臺門、行控、機廠設備、維修監測、能源管理、系統整合、系統保證及資安等具體案例。
- 技術新知不限於採購、合約或正式上線事件；候選若明確說明都市軌道機電技術原理、工程挑戰或系統應用，即使屬專業技術文章仍應保留。Frauscher 軸計數器與電車號誌工程文章即屬此類，不得只因缺少單一專案事件而刪除。
- 重大事故：已實際發生，且涉及傷亡、出軌、碰撞、火災、重大設備損壞、停駛、重大營運中斷，或具有明確系統安全檢討價值的事件。
- 營運政策：票價、服務調整、營運諮詢、預定封閉、例行維修、一般工程安排、旅客服務及治理措施。若新聞同時具有明確設備導入、系統升級或技術驗證內容，應優先歸為技術新知。
- 營運爭議：罷工、勞資、票價、合約、預算、工程延誤、訴訟或公共爭議。
- 規範更新：必須具備明確新版、修訂、增補、草案、公告、徵詢、撤回或取代資訊。
- 既有設備單純發生故障，不得列為技術新知；預定封閉、例行維修及一般工程進度不得列為重大事故；不得只因新聞出現 AI、系統、設備、測試或 Metro 等字詞，就判定為技術新知。

地區與來源判斷：
- 國家／地區以事件實際發生地為準，不得以旅客國籍、媒體所在地、搜尋語言或來源網站所在地判斷。
- 若標題或摘要已明確出現城市、國家或營運機構，應更正程式初判。例如 Mumbai 應判為印度、St. Paul 應判為美國、Moscow 應判為俄羅斯；原始資料確實無法判定時，才寫「未判定」。
- 只有政府機關、交通主管機關、捷運營運機構及其官方網站，才可使用「公告」或「官方資料」。MSN、Yahoo、一般新聞媒體、入口網站與轉載平台一律使用「報導」，不得寫成「官方公告」。
- source_display 或 source_verb 若與 source_domain 明顯矛盾，應以 source_domain 所代表的實際來源性質為準。

內容與格式要求：
- 每則新聞標題必須翻成繁體中文正式標題；機構、車型或系統縮寫可保留。
- 發布／事件日期統一顯示為 YYYY-MM-DD，不得輸出 ISO 時間、時區或 `T00:00:00+00:00`。
- 「事件摘要：」與「臺北捷運局啟示：」後方必須換行，摘要與啟示不得使用條列。
- 事件摘要僅根據候選資料撰寫，重點為事件本身、都市軌道場景、涉及的機電系統或營運管理意義。原始資料未提供細節時應保守表述，不得自行補述數字、供應商、金額、GoA 等級、測試項目、車輛規格、事故原因或導入時程。
- 資料不足時直接縮短摘要，不得於正文列舉技術規格、時程、測試內容或其他未提供項目。
- 每則「臺北捷運局啟示」只選擇與該事件最直接相關的一至二項工程重點，不得每則同時羅列系統整合、資料治理、維修管理、資安、能源效率及風險控管。例如票閘設備著重 AFC 介面、容量與維修；電梯汰換著重設備生命週期、施工界面與無障礙服務；號誌事故著重故障隔離、備援與營運應變。
- 「相關機電系統」應保留候選內容可支持的具體且合理用語；不得把「車站無障礙設施、車站機電」降級為「車站、車站機電」，也不得自行擴寫成「電梯、車站電梯」等重複詞。
- 資料來源請依 source_domain、source_display、date 與 url 表達；連結依「原始文章 URL、Google News 文章 URL、domain」順序選用。若有完整 URL，必須保留該 URL；若只有 domain，顯示 domain；若無可用連結，僅列來源名稱且不得說明資料缺漏。不得自行編造 URL。
- 若事件摘要使用 supplemental_sources 的供應商、技術或數據資訊，資料來源欄必須同時列出主要來源與相應補充來源的完整連結。例如 TTC Line 2 摘要若使用 Hitachi 數位號誌或 40% 容量資訊，必須同時列出 TTC 主要來源及 Hitachi／Newswire 補充來源。
- 不得在正式報告正文使用 MaiAgent、Python 初篩、developer debug、python_score、候選 flags、入選原因或其他模型處理語氣。
- 請勿輸出「本期統計」、「報告產出時間」、搜尋次數、候選數量或任何系統執行資訊；這些內容將由程式後續統一產生。
- 未啟用國際學術期刊時，正式報告正文結束於最後一則新聞；啟用期刊時，正文結束於「學術期刊綜合結論」。

## 已入選新聞資料
{candidate_block}
{journal_input_text}

## 最高優先正文規則
正式正文禁止出現「資料未提供」、「候選資料未提供」、「原始資料未提供」、「資料來源未載明」等缺漏說明。資訊不足時直接縮短內容，不得列舉缺少的規格、時程、金額、測試內容、設備項目或其他未提供資料。
""".strip()

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


def apply_final_report_footer(report_md: str, journal_candidates: list[dict] | None = None) -> str:
    return service_apply_final_report_footer(
        report_md,
        journal_candidates,
        selected_types=selected_types,
        include_research_supplement=include_research_supplement,
        today=today,
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
    theme_terms = [
        ("列車控制與號誌安全", ["cbtc", "signalling", "signaling", "train control", "ato", "atp", "號誌", "列控"]),
        ("車輛與維修管理", ["rolling stock", "vehicle", "maintenance", "condition monitoring", "車輛", "維修", "監測"]),
        ("牽引供電與能源效率", ["traction power", "regenerative", "energy", "power supply", "牽引", "供電", "能源"]),
        ("資料治理、AI 與數位分身", ["data", "ai", "machine learning", "digital twin", "資料", "數位分身", "人工智慧"]),
        ("旅客流量與營運韌性", ["passenger flow", "resilience", "operation", "capacity", "旅客流量", "韌性", "運能"]),
        ("資安與系統整合", ["cyber", "system integration", "security", "資安", "系統整合"]),
    ]
    text = " ".join(f"{item.get('title','')} {item.get('snippet','')}" for item in journal_candidates or [])
    themes = [label for label, terms in theme_terms if _contains_any_term(text, terms)]
    return themes or ["都市軌道機電系統資料化、智慧化與維運管理"]


def build_journal_summary_conclusion(journal_candidates: list[dict]) -> str:
    themes = _unique_limited(_journal_theme_summary(journal_candidates), 4)
    theme_text = "、".join(themes)
    source_names = _unique_limited([
        item.get("journal_name") or item.get("source") or _domain_from_url(item.get("url", ""))
        for item in journal_candidates or []
    ], 4)
    source_text = "、".join(source_names) if source_names else "本期入選研究來源"
    return (
        f"本期國際學術期刊補充依系統取得之正式期刊或可信研究頁面整理，入選研究主要來自{source_text}，"
        f"觀察主題集中於{theme_text}等方向。整體而言，近期都市軌道研究已由單一設備改善，逐步轉向以資料、模型與系統整合支撐營運安全、維修決策及能源效率管理。"
        f"相關研究對臺北捷運局之啟示，在於新線規劃與既有系統更新時，應及早界定資料來源、欄位格式、系統介面、模型驗證、維修流程與營運安全邊界；"
        f"導入 AI、數位分身或預測維護等工具時，也應避免僅著重演算法展示，而需同步建立資料品質、資安權限、異常處置與跨系統驗證機制。"
        f"後續可將此類研究作為機電系統需求規劃、維修管理制度、能源效率策略及風險控管之參考來源，並以可追溯、可驗證、可維運為技術導入原則。"
    )


def ensure_journal_summary_conclusion(report_md: str, journal_candidates: list[dict]) -> str:
    if not include_research_supplement or not journal_candidates:
        return report_md
    if "學術期刊綜合結論" in (report_md or ""):
        return report_md
    conclusion = "【學術期刊綜合結論】\n" + build_journal_summary_conclusion(journal_candidates)
    match = re.search(r"(?m)^📊", report_md or "")
    if match:
        return (report_md[:match.start()].rstrip() + "\n\n" + conclusion + "\n\n" + report_md[match.start():].lstrip()).strip()
    return (report_md or "").rstrip() + "\n\n" + conclusion


def _journal_candidate_full_date(item: dict) -> str:
    for key in ("published_date", "date"):
        date_obj = _parse_full_research_date(str(item.get(key, "") or ""))
        if date_obj:
            return date_obj.isoformat()
    return ""


def _normalize_doi_value(value: str) -> str:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", value or "", flags=re.IGNORECASE)
    return match.group(0).rstrip(".;,)").casefold() if match else ""


def _journal_candidate_date_for_text(
    text: str,
    journal_candidates: list[dict],
    report_title: str = "",
) -> str:
    report_urls = set(_extract_complete_urls(text or ""))
    for item in journal_candidates or []:
        candidate_url = _extract_complete_url(str(item.get("url", "") or ""))
        if candidate_url and candidate_url in report_urls:
            return _journal_candidate_full_date(item)

    report_dois = {
        doi
        for doi in (_normalize_doi_value(value) for value in [text or "", *_extract_complete_urls(text or "")])
        if doi
    }
    for item in journal_candidates or []:
        candidate_dois = {
            doi
            for doi in (
                _normalize_doi_value(str(item.get("doi", "") or "")),
                _normalize_doi_value(str(item.get("url", "") or "")),
            )
            if doi
        }
        if candidate_dois.intersection(report_dois):
            return _journal_candidate_full_date(item)

    normalized_report_title = _normalize_title(report_title)
    if normalized_report_title:
        for item in journal_candidates or []:
            if normalized_report_title == _normalize_title(str(item.get("title", "") or "")):
                return _journal_candidate_full_date(item)
    return ""


def repair_journal_dates_in_report(report_md: str, journal_candidates: list[dict]) -> str:
    if not include_research_supplement or not journal_candidates or not report_md:
        return report_md
    heading_match = re.search(
        r"(?m)^#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:技術研究補充|國際學術期刊)\s*$",
        report_md,
    )
    if not heading_match:
        return report_md
    end_match = re.search(r"(?m)^(?:📊|⏰)", report_md[heading_match.end():])
    section_end = heading_match.end() + end_match.start() if end_match else len(report_md)
    before = report_md[:heading_match.start()]
    section = report_md[heading_match.start():section_end]
    after = report_md[section_end:]

    item_matches = list(re.finditer(r"(?m)^\s*(?:#{1,6}\s*)?(\d+)[\.、]\s*(.+?)\s*$", section))
    if not item_matches:
        return report_md
    conclusion_match = re.search(r"(?m)^#{0,6}\s*學術期刊綜合結論", section)
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
        report_title = re.sub(r"\s{2,}$", "", item_match.group(2)).strip()
        matched_date = _journal_candidate_date_for_text(block, journal_candidates, report_title)
        if not matched_date:
            continue
        repaired_block = re.sub(
            r"(?m)^(?P<prefix>\s*(?:\d+[\.、]\s*)?(?:[-*]\s*)?(?:•\s*)?發表日期\s*[：:]\s*).*$",
            lambda match: f"{match.group('prefix')}{matched_date}",
            block,
            count=1,
        )
        replacements.append((block_start, block_end, repaired_block))

    repaired_section = section
    for block_start, block_end, repaired_block in reversed(replacements):
        repaired_section = repaired_section[:block_start] + repaired_block + repaired_section[block_end:]
    return before + repaired_section + after


def _is_canonical_journal_section(section: str) -> bool:
    required_fields = ["發表日期", "期刊／來源", "研究主題", "研究摘要", "臺北捷運局啟示", "資料來源"]
    item_count = 0
    current_fields: list[str] = []
    conclusion_count = 0
    in_conclusion = False

    def _field_name(line: str) -> str:
        match = re.match(
            r"^•\s*(發表日期|期刊[/／]來源|研究主題|研究摘要|臺北捷運局啟示|資料來源)\s*[：:].+",
            line.strip(),
        )
        if not match:
            return ""
        return "期刊／來源" if match.group(1) in {"期刊/來源", "期刊／來源"} else match.group(1)

    for raw_line in (section or "").splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch(r"#{1,6}", line):
            return False
        if "學術期刊綜合結論" in line:
            conclusion_count += 1
            if conclusion_count > 1:
                return False
            if item_count and current_fields != required_fields:
                return False
            in_conclusion = True
            continue
        if in_conclusion:
            continue
        if re.match(r"^\d+、\S+", line):
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
    return current_fields == required_fields or in_conclusion


def normalize_journal_section_format(report_md: str, journal_candidates: list[dict]) -> str:
    if not include_research_supplement or not journal_candidates or not report_md:
        return report_md
    heading_match = re.search(
        r"(?m)^#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:技術研究補充|國際學術期刊)\s*$",
        report_md,
    )
    if not heading_match:
        return report_md
    end_match = re.search(r"(?m)^(?:📊|⏰)", report_md[heading_match.end():])
    section_end = heading_match.end() + end_match.start() if end_match else len(report_md)
    before = report_md[:heading_match.start()]
    section = report_md[heading_match.start():section_end]
    after = report_md[section_end:]

    if _is_canonical_journal_section(section):
        return report_md

    section = re.sub(
        r"(?<=[^\n])(?=\d+、(?!發表日期|期刊[/／]來源|研究主題|研究摘要|臺北捷運局啟示|資料來源))",
        "\n",
        section,
    )
    section = re.sub(r"(?<=[^\n])(\s*#{0,6}\s*學術期刊綜合結論)", r"\n\1", section)

    lines = section.splitlines()
    if not lines:
        return report_md
    output: list[str] = [lines[0]]
    item_index = 0
    in_conclusion = False
    field_names = ("發表日期", "期刊/來源", "期刊／來源", "研究主題", "研究摘要", "臺北捷運局啟示", "資料來源")
    seen_fields_by_item: dict[int, set[str]] = {}

    def _candidate_for_item(index: int) -> dict:
        if 1 <= index <= len(journal_candidates):
            return journal_candidates[index - 1] or {}
        return {}

    def _candidate_display_title(index: int) -> str:
        item = _candidate_for_item(index)
        title = _clean_text(str(item.get("title", "") or ""))
        title = re.sub(r"\[[^\]]*(?:技術研究補充|國際學術期刊)[^\]]*\]\s*", "", title).strip()
        return title or f"國際學術期刊研究 {index}"

    def _candidate_source_name(index: int) -> str:
        item = _candidate_for_item(index)
        source = (
            item.get("journal_name")
            or item.get("source")
            or item.get("source_display")
            or _domain_from_url(item.get("url", ""))
        )
        source = _clean_source_label(str(source or ""), item.get("url", ""), _domain_from_url(item.get("url", "")))
        if source == "資料來源未明確辨識":
            return ""
        return source

    def _repair_truncated_value(value: str, expected: str) -> str:
        value = (value or "").strip()
        expected = (expected or "").strip()
        if not value or not expected:
            return value
        if expected.casefold() == value.casefold():
            return expected
        if expected.casefold().endswith(value.casefold()) and 0 < len(expected) - len(value) <= 3:
            return expected
        return value

    def _field_match(raw_line: str) -> tuple[str, str] | None:
        stripped = raw_line.strip()
        match = re.match(
            r"^\s*(?:\d+[\.\、]\s*)?(?:[-*]\s*)?(?:•\s*)?"
            r"(發表日期|期刊[/／]來源|研究主題|研究摘要|臺北捷運局啟示|資料來源)"
            r"\s*[：:]\s*(.*)$",
            stripped,
        )
        if match:
            field = "期刊／來源" if match.group(1) in {"期刊/來源", "期刊／來源"} else match.group(1)
            return field, match.group(2).strip()
        match = re.match(
            r"^\s*(?:\d+[\.\、]\s*)?(?:[-*]\s*)?(?:•\s*)?發表日期\s*[Pp]\s*(.*)$",
            stripped,
        )
        if match:
            return "發表日期", match.group(1).strip()
        return None

    def _clean_journal_title_line(raw_line: str) -> str:
        title = raw_line.strip()
        title = re.sub(r"^\s*#{3,6}\s*", "", title)
        title = re.sub(r"^\s*🔹\s*", "", title)
        title = re.sub(r"\[[^\]]*(?:技術研究補充|國際學術期刊)[^\]]*\]\s*", "", title)
        title = re.sub(r"^\s*(?:\d+[\.\、]|[（(]?\d+[）)])\s*", "", title)
        title = title.strip(" ：:　")
        return title

    def _matches_candidate_title(candidate_title: str, candidate: dict) -> bool:
        original = str(candidate.get("title", "") or "")
        if not original or not candidate_title:
            return False
        if candidate_title.casefold() in original.casefold() or original.casefold() in candidate_title.casefold():
            return True
        original_tokens = [
            token.casefold()
            for token in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{5,}", original)
            if len(token) >= 5
        ]
        title_lower = candidate_title.casefold()
        return bool(original_tokens) and sum(1 for token in original_tokens[:8] if token in title_lower) >= 2

    def _looks_like_title_line(raw_line: str, title: str) -> bool:
        stripped = raw_line.strip()
        if not title or any(title.startswith(name) for name in field_names):
            return False
        if "學術期刊綜合結論" in title:
            return False
        if re.match(r"^\s*(?:#{3,6}|🔹|\d+[\.\、]|[（(]?\d+[）)])", stripped):
            return True
        if re.search(r"\[[^\]]*(?:技術研究補充|國際學術期刊)[^\]]*\]", stripped):
            return True
        if any(_matches_candidate_title(title, item) for item in journal_candidates or []):
            return True
        if item_index < len(journal_candidates) and "：" not in title and ":" not in title:
            if len(title) <= 120 and not title.endswith(("。", "；", ";")) and not title.startswith(("以下", "本期", "研究補充", "國際學術期刊")):
                return True
        return False

    def _repair_date_value(value: str, index: int) -> str:
        value = (value or "").strip()
        match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", value)
        if match:
            return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        if re.fullmatch(r"(?:0?\d{2}|\d{3})[-/]\d{1,2}[-/]\d{1,2}", value):
            return "日期未明"
        year_match = re.fullmatch(r"(20\d{2}|19\d{2})\s*年?", value)
        if year_match:
            return f"{year_match.group(1)}年"
        if not value or value in {"日期未知", "日期未明", "未知"}:
            return "日期未明"
        return value

    def _repair_field_value(field: str, value: str, index: int) -> str:
        value = _clean_text(value)
        if field == "發表日期":
            return _repair_date_value(value, index)
        if field == "期刊／來源":
            expected = _candidate_source_name(index)
            value = _repair_truncated_value(value, expected)
            if not value or value in {"資料來源未明確辨識", "報導"}:
                value = expected
            return value
        return value

    def _append_blank_if_needed() -> None:
        if output and output[-1].strip():
            output.append("")

    def _append_title(title: str) -> None:
        nonlocal item_index
        item_index += 1
        _append_blank_if_needed()
        output.append(f"{item_index}、{title}")
        seen_fields_by_item.setdefault(item_index, set())

    def _ensure_item_started() -> None:
        if item_index <= 0:
            _append_title(_candidate_display_title(1))

    def _append_field(field: str, value: str) -> None:
        _ensure_item_started()
        seen_fields = seen_fields_by_item.setdefault(item_index, set())
        if field in seen_fields:
            return
        output.append(f"• {field}：{_repair_field_value(field, value, item_index)}")
        seen_fields.add(field)

    def _process_body_line(raw_line: str) -> None:
        stripped = raw_line.strip()
        if not stripped:
            _append_blank_if_needed()
            return
        if re.fullmatch(r"#{1,6}", stripped):
            return
        if stripped == "---":
            return
        field_match = _field_match(raw_line)
        if field_match:
            _append_field(field_match[0], field_match[1])
            return
        explicit_title_marker = bool(
            re.match(r"^\s*(?:#{3,6}|🔹|\d+[\.\、]|[（(]?\d+[）)])", stripped)
            or re.search(r"\[[^\]]*(?:技術研究補充|國際學術期刊)[^\]]*\]", stripped)
        )
        if output and output[-1].startswith("• ") and not explicit_title_marker:
            output[-1] = output[-1].rstrip() + " " + stripped
            return
        title = _clean_journal_title_line(raw_line)
        if _looks_like_title_line(raw_line, title):
            _append_title(title)
            return
        if item_index == 0:
            output.append(stripped)
        elif output and output[-1].startswith("• "):
            output[-1] = output[-1].rstrip() + " " + stripped
        else:
            output.append(stripped)

    for raw_line in lines[1:]:
        stripped = raw_line.strip()
        if in_conclusion:
            output.append(raw_line)
            continue
        if "學術期刊綜合結論" in stripped:
            prefix, _, suffix = raw_line.partition("學術期刊綜合結論")
            prefix_clean = re.sub(r"^#{1,6}\s*$", "", prefix.strip())
            if prefix_clean:
                _process_body_line(prefix)
            _append_blank_if_needed()
            output.append("學術期刊綜合結論")
            suffix = suffix.strip(" ：:】]「」")
            if suffix:
                output.append(suffix)
            in_conclusion = True
            continue
        _process_body_line(raw_line)

    normalized = re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()
    return before + normalized + after


def count_journal_summary_conclusion_chars(report_md: str) -> int:
    match = re.search(r"學術期刊綜合結論[】\]]?\s*\n?(.+?)(?=^📊|^⏰|\Z)", report_md or "", flags=re.DOTALL | re.MULTILINE)
    if not match:
        return 0
    return len(re.sub(r"\s+", "", match.group(1)))


def enforce_research_section(report_md: str, journal_candidates: list[dict]) -> str:
    if not include_research_supplement:
        return report_md
    if journal_candidates:
        return report_md
    heading = research_section_heading(markdown=True)
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


def _candidate_report_presence_keys(candidate: dict) -> list[str]:
    source_url = _effective_source_url(candidate)
    values = []
    complete_source_url = _extract_complete_url(source_url)
    if complete_source_url:
        values.append(complete_source_url)
    raw_url = candidate.get("url", "")
    complete_raw_url = _extract_complete_url(raw_url)
    if complete_raw_url and complete_raw_url not in values:
        values.append(complete_raw_url)
    values.append(candidate.get("title", ""))
    return [str(value).strip() for value in values if str(value or "").strip()]


def _report_block_matches_candidate(block: str, candidate: dict) -> bool:
    marker = re.search(r"<!--\s*candidate_id\s*:\s*(\d+)\s*-->", block or "", flags=re.IGNORECASE)
    if marker:
        return int(marker.group(1)) == int(candidate.get("candidate_id") or candidate.get("id") or 0)
    keys = _candidate_report_presence_keys(candidate)
    if any(key and key in (block or "") for key in keys):
        return True
    title_tokens = [
        token for token in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{4,}", candidate.get("title", "") or "")
        if len(token) >= 4
    ]
    return bool(title_tokens) and sum(1 for token in title_tokens[:6] if token in (block or "")) >= 2


def _supplemental_source_is_used(report_block: str, candidate: dict, source_row: dict) -> bool:
    summary_match = re.search(
        r"(?ms)^•\s*事件摘要\s*[：:]\s*(.*?)"
        r"(?=^•\s*(?:臺北捷運局啟示|資料來源|發布/事件日期|國家/地區|相關機電系統)\s*[：:]|\Z)",
        report_block or "",
    )
    summary = summary_match.group(1) if summary_match else report_block or ""
    summary_folded = summary.casefold()
    supplemental_text = f"{source_row.get('title', '')} {source_row.get('source_display', '')}".casefold()

    if re.search(r"\b40\s*%", supplemental_text) and re.search(r"40\s*%", summary):
        return True
    bilingual_signals = (
        (("hitachi",), ("hitachi", "日立")),
        (("digital signalling", "digital signaling"), ("digital signalling", "digital signaling", "數位號誌", "數位信號")),
        (("capacity increase",), ("capacity increase", "容量提升", "容量增加", "運能提升", "運能增加")),
    )
    for source_terms, summary_terms in bilingual_signals:
        if any(term in supplemental_text for term in source_terms) and any(term in summary_folded for term in summary_terms):
            return True

    source_display = str(source_row.get("source_display", "") or "").casefold()
    source_name = source_display.split(".", 1)[0]
    if len(source_name) >= 4 and source_name in summary_folded:
        return True
    candidate_title = str(candidate.get("title", "") or "").casefold()
    if "ttc" in candidate_title and "line 2" in candidate_title:
        return bool(re.search(r"40\s*%|hitachi|日立|數位號誌|數位信號|運能(?:提升|增加)|容量(?:提升|增加)", summary, flags=re.IGNORECASE))
    return False


def _report_block_matches_supplemental_candidate(block: str, candidate: dict) -> bool:
    if _report_block_matches_candidate(block, candidate):
        return True
    block_folded = (block or "").casefold()
    title_folded = str(candidate.get("title", "") or "").casefold()
    operator_markers = [marker for marker in ("ttc", "mta", "wmata", "bvg", "translink", "frauscher", "austin") if marker in title_folded]
    route_markers = [marker for marker in ("line 2", "r211", "m4", "skytrain") if marker in title_folded]
    return bool(operator_markers and any(marker in block_folded for marker in operator_markers)) and (
        not route_markers or any(marker in block_folded for marker in route_markers)
    )


def ensure_supplemental_sources_in_report(report_md: str, selected_candidates: list[dict]) -> str:
    candidates = [candidate for candidate in selected_candidates or [] if candidate.get("supplemental_sources")]
    if not report_md or not candidates:
        return report_md
    parts = re.split(r"(?m)^(🔹\s*\[[^\]]+\].*)$", report_md)
    if len(parts) <= 1:
        return report_md
    output = [parts[0]]
    for idx in range(1, len(parts), 2):
        heading = parts[idx]
        body = parts[idx + 1] if idx + 1 < len(parts) else ""
        block = heading + body
        candidate = next(
            (item for item in candidates if _report_block_matches_supplemental_candidate(block, item)),
            None,
        )
        if not candidate:
            output.extend([heading, body])
            continue
        used_sources = [
            source_row for source_row in candidate.get("supplemental_sources", []) or []
            if _supplemental_source_is_used(block, candidate, source_row)
        ]
        additions: list[str] = []
        for source_row in used_sources:
            source_url = _extract_complete_url(str(source_row.get("url", "") or ""))
            source_display = str(source_row.get("source_display", "") or _domain_from_url(source_url) or "補充來源").strip()
            if source_url and source_url not in block:
                additions.append(f"{source_display}，{source_url}")
            elif source_display and source_display.casefold() not in block.casefold():
                additions.append(source_display)
        if additions:
            suffix = "；補充來源：" + "；".join(additions)
            if re.search(r"(?m)^•\s*資料來源\s*[：:].*$", body):
                body = re.sub(
                    r"(?m)^(•\s*資料來源\s*[：:].*)$",
                    lambda match: match.group(1).rstrip("；; ") + suffix,
                    body,
                    count=1,
                )
            else:
                body = body.rstrip() + f"\n\n• 資料來源：{suffix.lstrip('；')}\n"
        output.extend([heading, body])
    return "".join(output)


def _candidate_region_display(candidate: dict) -> str:
    text = _candidate_selection_text(candidate)
    region = _canonical_candidate_region(dict(candidate))
    city_map = [
        ("北愛爾蘭", ["northern ireland", "belfast", "北愛爾蘭", "貝爾法斯特"], "英國（北愛爾蘭）"),
        ("巴塞爾", ["basel", "巴塞爾"], "瑞士（巴塞爾）"),
        ("休士頓", ["houston", "休士頓", "休斯頓"], "美國（休士頓）"),
        ("溫哥華", ["vancouver", "broadway subway", "溫哥華"], "加拿大（溫哥華）"),
        ("多倫多", ["toronto", "finch west", "多倫多"], "加拿大（多倫多）"),
        ("柏林", ["berlin", "adlershof", "柏林"], "德國（柏林）"),
        ("萊比錫", ["leipzig", "萊比錫"], "德國（萊比錫）"),
    ]
    for _, terms, label in city_map:
        if _contains_any_term(text, terms):
            return label
    return region or "未判定"


def _is_unknown_region_value(value: str) -> bool:
    cleaned = re.sub(r"\s+", "", value or "").strip("：:，,。-")
    return cleaned in {"", "未判定", "未知", "不明", "未明", "國家/地區未判定", "國家地區未判定"}


def repair_report_region_lines(report_md: str, selected_candidates: list[dict]) -> str:
    if not report_md or not selected_candidates:
        return report_md
    parts = re.split(r"(?m)^(🔹\s*\[[^\]]+\].*)$", report_md)
    if len(parts) <= 1:
        return report_md
    output = [parts[0]]
    for idx in range(1, len(parts), 2):
        heading = parts[idx]
        body = parts[idx + 1] if idx + 1 < len(parts) else ""
        block = heading + body
        matched = next((candidate for candidate in selected_candidates if _report_block_matches_candidate(block, candidate)), None)
        if matched:
            region_display = _candidate_region_display(matched)
            if _is_unknown_region_value(region_display):
                output.extend([heading, body])
                continue
            region_match = re.search(r"(?m)^•\s*國家/地區\s*[：:]\s*(.*)$", body)
            if region_match:
                current_region = region_match.group(1).strip()
                if _is_unknown_region_value(current_region):
                    body = re.sub(r"(?m)^•\s*國家/地區\s*[：:].*$", f"• 國家/地區：{region_display}", body, count=1)
            else:
                insert_match = re.search(r"(?m)^•\s*發布/事件日期\s*[：:].*$", body)
                if insert_match:
                    body = body[:insert_match.end()] + f"\n• 國家/地區：{region_display}" + body[insert_match.end():]
                else:
                    body = f"\n• 國家/地區：{region_display}" + body
        output.extend([heading, body])
    return "".join(output)


def formal_title_from_candidate(candidate: dict) -> str:
    category = candidate.get("classification") or candidate.get("preliminary_type") or infer_preliminary_type(candidate)
    text = _candidate_selection_text(candidate)
    original_title = _clean_text(candidate.get("title", ""))
    if _contains_any_term(text, ["frauscher", "axle counter", "axle counters"]):
        return "Frauscher 車軸計數器應用於電車號誌現代化"
    if _contains_any_term(text, ["finch west", "hitachi"]):
        return "多倫多 Finch West LRT 啟用 Hitachi Rail 號誌系統"
    if _contains_any_term(text, ["broadway subway"]):
        return "溫哥華 Broadway Subway 都市軌道專案進展"
    if _contains_any_term(text, ["houston", "metrorail"]):
        return "休士頓 METRORail 都市軌道事件"
    if _contains_any_term(text, ["adlershof"]):
        return "柏林 Adlershof 電車撞擊事故"
    if _contains_any_term(text, ["basel"]) and category == "重大事故":
        return "巴塞爾電車碰撞事故"
    if _contains_any_term(text, ["leipzig"]) and category == "重大事故":
        return "萊比錫路面電車營運安全事件"

    if original_title and not _title_needs_repair(original_title, category):
        if _looks_like_english_title(original_title):
            return chinese_fallback_title(category, original_title)
        return original_title
    return chinese_fallback_title(category, original_title)


def repair_generic_report_titles(report_md: str, selected_candidates: list[dict]) -> str:
    if not report_md or not selected_candidates:
        return report_md
    parts = re.split(r"(?m)^(🔹\s*\[[^\]]+\]\s*.*)$", report_md)
    if len(parts) <= 1:
        return report_md
    output = [parts[0]]
    for idx in range(1, len(parts), 2):
        heading = parts[idx]
        body = parts[idx + 1] if idx + 1 < len(parts) else ""
        match = re.match(r"^(🔹\s*\[([^\]]+)\]\s*)(.*)$", heading.strip())
        if match and not _has_valid_chinese_report_title(match.group(3)) and _title_needs_repair(match.group(3), match.group(2)):
            block = heading + body
            matched = next((candidate for candidate in selected_candidates if _report_block_matches_candidate(block, candidate)), None)
            if matched:
                heading = f"{match.group(1)}{formal_title_from_candidate(matched)}"
        output.extend([heading, body])
    return "".join(output)


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
    pattern = re.compile(
        r"<!--\s*candidate_id\s*:\s*(\d+)\s*-->\s*(.*?)"
        r"(?=<!--\s*candidate_id\s*:|^\s*#{0,6}\s*[一二三四五六七八九十]\s*、|^\s*📊|^\s*⏰|\Z)",
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    blocks: dict[int, str] = {}
    duplicates: list[int] = []
    for match in pattern.finditer(report_md or ""):
        candidate_id = int(match.group(1))
        if candidate_id in blocks:
            duplicates.append(candidate_id)
            continue
        blocks[candidate_id] = match.group(2).strip()
    return blocks, sorted(set(duplicates))


def _candidate_source_line(candidate: dict) -> str:
    source_url = _effective_source_url(candidate)
    source_display = candidate.get("source_display") or candidate.get("source") or _domain_from_url(source_url) or "原始來源"
    item_date = candidate.get("date") or "日期未知"
    return f"• 資料來源：{source_display}，{item_date}，{source_url}"


def _fallback_report_block(candidate: dict) -> str:
    candidate_id = int(candidate.get("candidate_id") or candidate.get("id") or 0)
    category = candidate.get("classification") or candidate.get("preliminary_type") or infer_preliminary_type(candidate)
    title = formal_title_from_candidate(candidate)
    summary = _clean_text(candidate.get("snippet", "")) or _clean_text(candidate.get("title", ""))
    summary = _short_formal_sentence(summary, 360) or "候選資料僅提供標題與來源，未提供更多可核實細節。"
    return "\n".join([
        f"<!-- candidate_id: {candidate_id} -->",
        f"🔹 [{category}] {title}",
        "",
        f"• 發布/事件日期：{candidate.get('date') or '日期未知'}",
        "",
        f"• 國家/地區：{_candidate_region_display(candidate)}",
        "",
        "• 相關機電系統：依原始候選資料所示之都市軌道系統",
        "",
        "• 事件摘要：",
        summary,
        "",
        "• 臺北捷運局啟示：",
        "本案可納入後續技術、營運或安全追蹤，具體內容以原始來源為準。",
        "",
        _candidate_source_line(candidate),
        "",
        "________________________________________",
    ])


def _force_candidate_fields_in_block(block: str, candidate: dict) -> str:
    normalized = normalize_final_report_md(block or "")
    if not re.search(r"(?m)^🔹\s*\[[^\]]+\]", normalized):
        return _fallback_report_block(candidate)
    candidate_id = int(candidate.get("candidate_id") or candidate.get("id") or 0)
    category = candidate.get("classification") or candidate.get("preliminary_type") or infer_preliminary_type(candidate)
    normalized = REPORT_CANDIDATE_ID_PATTERN.sub("", normalized).strip()
    normalized = re.sub(
        r"(?m)^(🔹\s*)\[[^\]]+\]",
        rf"\1[{category}]",
        normalized,
        count=1,
    )
    source_line = _candidate_source_line(candidate)
    if re.search(r"(?m)^•\s*資料來源\s*[：:].*$", normalized):
        normalized = re.sub(r"(?m)^•\s*資料來源\s*[：:].*$", source_line, normalized, count=1)
    else:
        normalized = normalized.rstrip() + f"\n\n{source_line}"
    return f"<!-- candidate_id: {candidate_id} -->\n{normalized}".strip()


def _extract_research_section_for_reconcile(report_md: str) -> str:
    match = re.search(
        r"(?ms)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:國際學術期刊|技術研究補充)\s*$.*?"
        r"(?=^\s*📊|^\s*⏰|\Z)",
        report_md or "",
    )
    return match.group(0).strip() if match else ""


def reconcile_report_candidate_output(report_md: str, selected_candidates: list[dict]) -> tuple[str, dict]:
    selected_candidates = ensure_selected_candidate_ids(selected_candidates)
    initial_validation = validate_report_candidate_ids(report_md, selected_candidates)
    marked_blocks, extracted_duplicates = _extract_marked_candidate_blocks(report_md)
    selected_map = {
        int(item.get("candidate_id") or item.get("id") or 0): item
        for item in selected_candidates or []
    }
    accepted_blocks: dict[int, str] = {}
    fallback_ids: list[int] = []
    for candidate_id, candidate in selected_map.items():
        if candidate_id in marked_blocks and candidate_id not in extracted_duplicates:
            accepted_blocks[candidate_id] = _force_candidate_fields_in_block(marked_blocks[candidate_id], candidate)
        else:
            accepted_blocks[candidate_id] = _fallback_report_block(candidate)
            fallback_ids.append(candidate_id)

    sections: list[str] = [
        f"# {report_title}",
        f"> 資料涵蓋期間：{date_range}",
        f"> 報導範圍：{report_scope_label}",
    ]
    category_groups = [
        ("一、技術新知", {"技術新知"}),
        ("二、重大事故", {"重大事故"}),
        ("三、營運議題", {"營運政策", "營運爭議"}),
    ]
    if standards_enabled or "規範更新" in selected_types:
        category_groups.append(("四、規範更新", {"規範更新"}))
    for heading, categories in category_groups:
        if not categories.intersection(selected_types):
            continue
        section_blocks = [
            accepted_blocks[int(item.get("candidate_id") or item.get("id") or 0)]
            for item in selected_candidates
            if (item.get("classification") or item.get("preliminary_type")) in categories
        ]
        sections.extend(["", f"## {heading}", ""])
        if section_blocks:
            sections.append("\n\n".join(section_blocks))
        elif len(categories) == 1:
            category = next(iter(categories))
            sections.append(EMPTY_TEXT_BY_TYPE.get(category, "本期未發現符合條件資料。"))
        else:
            sections.append("本期未發現符合條件的營運議題資料。")

    research_section = _extract_research_section_for_reconcile(report_md) if include_research_supplement else ""
    if research_section:
        sections.extend(["", research_section])
    reconciled = re.sub(r"\n{3,}", "\n\n", "\n".join(sections)).strip()
    final_validation = validate_report_candidate_ids(reconciled, selected_candidates)
    diagnostics = {
        "before_reconcile": initial_validation,
        "fallback_candidate_ids": fallback_ids,
        "accepted_model_candidate_ids": sorted(set(selected_map) - set(fallback_ids)),
        "after_reconcile": final_validation,
    }
    return reconciled, diagnostics


def identify_dropped_selected_candidates(report_md: str, selected_candidates: list[dict]) -> list[dict]:
    missing_ids = set(validate_report_candidate_ids(report_md, selected_candidates).get("missing_ids", []))
    return [
        candidate for candidate in selected_candidates or []
        if int(candidate.get("candidate_id") or candidate.get("id") or 0) in missing_ids
    ]


def restore_missing_selected_report_items(report_md: str, selected_candidates: list[dict]) -> tuple[str, list[dict]]:
    global LAST_REPORT_ID_VALIDATION
    dropped = identify_dropped_selected_candidates(report_md, selected_candidates)
    reconciled, diagnostics = reconcile_report_candidate_output(report_md, selected_candidates)
    LAST_REPORT_ID_VALIDATION = diagnostics
    return reconciled, dropped


def compact_report_line_for_pdf(line: str) -> str:
    line = normalize_source_line(remove_internal_candidate_markers(line))
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    if "資料來源" in line:
        line = re.sub(
            r"https?://[^\s\)\]）＞>，,；;。]+",
            lambda match: f"[原文連結]({match.group(0).rstrip('。；;,，)')})",
            line,
        )
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


def build_final_incident_coverage_debug(
    selected_candidates: list[dict],
    maiagent_report_response: str,
    final_report_md: str,
    *,
    global_scope: bool,
    report_days: int,
    incident_enabled: bool,
) -> dict:
    python_count = sum(
        1
        for item in selected_candidates or []
        if (item.get("classification") or item.get("preliminary_type")) == "重大事故"
    )
    maiagent_count = count_report_items_by_category(maiagent_report_response).get("重大事故", 0)
    final_count = count_report_items_by_category(final_report_md).get("重大事故", 0)
    dropped_after_maiagent = max(0, python_count - final_count)
    warning = bool(
        global_scope
        and int(report_days or 0) in {90, 365}
        and incident_enabled
        and final_count == 0
    )
    reason = ""
    if warning:
        if python_count > 0 and maiagent_count == 0:
            reason = "Python 已入選重大事故，但 MaiAgent 正式回覆未輸出重大事故。"
        elif maiagent_count > 0 and final_count == 0:
            reason = "MaiAgent 正式回覆含重大事故，但報告後處理後未保留重大事故。"
        elif python_count == 0:
            reason = "Python 入選候選未含重大事故，最終正式報告亦無重大事故。"
        else:
            reason = "最終正式報告未輸出重大事故。"
    return {
        "python_incident_selected_count": python_count,
        "maiagent_incident_report_count": maiagent_count,
        "final_incident_report_count": final_count,
        "incident_dropped_after_maiagent": dropped_after_maiagent,
        "incident_coverage_warning": warning,
        "incident_coverage_reason": reason,
    }


def report_has_unselected_types(report_md: str) -> bool:
    unselected = [category for category in ADVANCED_TYPES if category not in selected_types]
    for category in unselected:
        if re.search(rf"(?m)^(##|###)\s+.*{re.escape(category)}", report_md):
            return True
    return False


def report_has_non_urban_formal_items(report_md: str) -> bool:
    formal_area = report_md.split("## 候補觀察", 1)[0]
    for block in re.split(r"(?m)^###\s+", formal_area)[1:]:
        if "[規範更新]" in block:
            continue
        if not _is_urban_rail_candidate(block):
            return True
    return False


def has_candidate_observations(report_md: str) -> bool:
    return "候補觀察" in report_md and not re.search(r"候補觀察[^\n]*\n\s*(?:無|本期無)", report_md)


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
    sections: list[str] = [
        f"# {report_title}",
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

    if demo_md_path.exists():
        report_text = demo_md_path.read_text(encoding="utf-8")
        source = str(demo_md_path)
    else:
        report_text = str(debug_payload.get("final_report_md") or "").strip()
        if report_text:
            source = str(demo_debug_path)
        else:
            report_text = _builtin_demo_report_text()

    report_text = remove_internal_candidate_markers(sanitize_report_text(report_text))
    report_text = enforce_research_section(report_text, [])
    report_text = normalize_final_report_md(report_text)
    report_text = apply_final_report_footer(report_text, [])

    if demo_pdf_path.exists():
        pdf_bytes = demo_pdf_path.read_bytes()
    else:
        pdf_bytes = try_markdown_to_pdf_bytes(report_text)

    return report_text, pdf_bytes, {
        "demo_source": source,
        "demo_markdown_path": str(demo_md_path),
        "demo_pdf_path": str(demo_pdf_path) if demo_pdf_path.exists() else "",
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
            report_id_validation_before_retry = validate_report_candidate_ids(raw_report, selected_candidates)
            report_retry_attempted = False
            if not report_id_validation_before_retry.get("valid"):
                report_retry_attempted = True
                retry_prompt = build_report_retry_prompt(
                    report_prompt,
                    raw_report,
                    report_id_validation_before_retry,
                )
                raw_report = call_maiagent_cloud(retry_prompt)
                maiagent_call_count += 1
            report_id_validation_after_retry = validate_report_candidate_ids(raw_report, selected_candidates)
            raw_report_candidate_ids = extract_report_candidate_ids(raw_report)
            maiagent_report_response_count = count_report_items(raw_report)
            timings["elapsed_seconds_report"] = round(time.perf_counter() - stage_start, 2)
            maiagent_call_count += 1
            progress_bar.progress(0.88)

            status_text.text("正在進行報告撰寫")
            pdf_stage_start = time.perf_counter()
            validated_report = sanitize_report_text(raw_report)
            validated_report = enforce_research_section(validated_report, journal_candidates)
            validated_report = ensure_journal_summary_conclusion(validated_report, journal_candidates)
            validated_report = normalize_final_report_md(validated_report)
            validated_report = repair_journal_dates_in_report(validated_report, journal_candidates)
            validated_report = normalize_journal_section_format(validated_report, journal_candidates)
            validated_report, dropped_selected_candidates = restore_missing_selected_report_items(
                validated_report, selected_candidates
            )
            validated_report = repair_report_region_lines(validated_report, selected_candidates)
            validated_report = repair_generic_report_titles(validated_report, selected_candidates)
            validated_report = merge_operational_report_sections(validated_report)
            validated_report = normalize_report_section_numbering(validated_report)
            validated_report = ensure_supplemental_sources_in_report(validated_report, selected_candidates)
            validated_report = remove_missing_data_disclaimers(validated_report)
            validated_report = insert_annual_observation_section(validated_report)

            # Internal IDs remain available through reconciliation and count validation.
            report_id_validation_before_clean = validate_report_candidate_ids(
                validated_report, selected_candidates
            )
            validated_report_count = count_report_items(validated_report)
            selected_final_count_validation_passed = bool(
                report_id_validation_before_clean.get("valid")
                and validated_report_count == len(selected_candidates)
            )

            # Everything below this boundary is public report content.
            clean_report = remove_internal_candidate_markers(validated_report)
            clean_report = normalize_formal_report_title(clean_report)
            clean_report = apply_final_report_footer(clean_report, journal_candidates)
            long_term_coverage = build_final_report_coverage_warning(clean_report, lookback_int, today)
            pdf_bytes = try_markdown_to_pdf_bytes(clean_report)
            dropped_selected_ids = [int(item.get("id", 0) or 0) for item in dropped_selected_candidates]
            dropped_selected_titles = [item.get("title", "") for item in dropped_selected_candidates]
            dropped_selected_reasons = [
                "MaiAgent 重試後仍未輸出該 candidate_id；已依原始候選資料產生保守 fallback。"
                for _ in dropped_selected_candidates
            ]
            formal_count = count_report_items(clean_report)
            postprocess_news_count_delta = formal_count - maiagent_report_response_count
            category_counts = count_report_items_by_category(clean_report)
            has_standard_updates = category_counts.get("規範更新", 0) > 0 or bool(
                re.search(r"(?m)^🔹\s*\[規範更新\]", clean_report)
            )
            prompt_chars = len(report_prompt)
            raw_chars = len(rss_results) + len(ddg_results)
            pipeline_debug_stats = candidate_pool.get("pipeline_debug_stats", {})
            pipeline_counts = pipeline_debug_stats.setdefault("pipeline_counts", {})
            pipeline_counts["selected"] = len(selected_candidates)
            pipeline_debug_stats["selected_count"] = len(selected_candidates)
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

            os.makedirs("reports", exist_ok=True)
            with open("reports/latest.md", "w", encoding="utf-8") as f:
                f.write(clean_report)
            with open(f"reports/report_{today.strftime('%Y%m%d')}.md", "w", encoding="utf-8") as f:
                f.write(clean_report)

            report_stats = {
                "raw_count": candidate_pool["raw_count"],
                "deduped_count": candidate_pool["deduped_count"],
                "filtered_count": candidate_pool["filtered_count"],
                "ai_selected_count": len(selected_candidates),
                "formal_count": formal_count,
                "maiagent_report_response_count": maiagent_report_response_count,
                "postprocess_news_count_delta": postprocess_news_count_delta,
                "postprocess_news_count_invariant_passed": formal_count == len(selected_candidates),
                "selected_final_count_invariant_passed": selected_final_count_validation_passed,
                "report_retry_attempted": report_retry_attempted,
                "report_id_validation_before_retry": report_id_validation_before_retry,
                "report_id_validation_after_retry": report_id_validation_after_retry,
                "report_id_validation_before_clean": report_id_validation_before_clean,
                "raw_report_candidate_ids": raw_report_candidate_ids,
                "validated_report_count": validated_report_count,
                "clean_report_marker_count": len(extract_report_candidate_ids(clean_report)),
                "report_id_reconciliation": LAST_REPORT_ID_VALIDATION,
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
                "category_gate_pass_counts": pipeline_debug_stats.get("category_gate_pass_counts", {}),
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
