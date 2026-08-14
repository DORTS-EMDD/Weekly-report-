"""Shared non-UI report workflow for Streamlit and automation."""

import datetime
import time
from dataclasses import dataclass
from typing import Callable

from article_processor import (
    _candidate_date_obj,
    _date_sort_key,
    _dedupe_url,
    _domain_from_url,
    _effective_source_url,
    _extract_domain_hint,
    _is_recent,
    _is_valid_news_url,
    _make_news_candidate,
    _normalize_title,
    _parse_pub_date,
    _quality_rank,
    _region_guess_from_candidate,
    _shorten,
    _source_tier_rank,
    dedupe_candidates,
    parse_ddg_candidates,
    parse_rss_candidates,
    source_label_for_report,
    source_verb_for_report,
)
from article_selector import build_selector_api
from config import (
    ADVANCED_TYPES,
    CANDIDATE_SNIPPET_CHARS,
    DEFAULT_NEWS_SCOPE,
    EMPTY_TEXT_BY_TYPE,
    MAX_SELECTION_CANDIDATES,
    REPORT_SNIPPET_CHARS,
    REPORT_CATEGORY_TYPES,
    SELECTION_MAX_ITEMS,
    SELECTION_MIN_ITEMS,
    STANDARDS_WATCHLIST,
    TRANSIT_NEWS_TERMS,
)
from ddgs_search_service import (
    DdgsSearchContext,
    _search_family_from_query,
    _search_language_from_query,
    build_search_queries,
    run_duckduckgo_searches,
)
from maiagent_service import (
    build_report_retry_prompt,
    ensure_selected_candidate_ids,
    extract_report_candidate_ids,
    remove_internal_candidate_markers,
    validate_report_candidate_ids,
)
from report_postprocessor import (
    ReportPostprocessContext,
    apply_final_report_footer,
    build_long_term_coverage_warning,
    build_journal_summary_conclusion,
    ensure_journal_summary_conclusion,
    ensure_supplemental_sources_in_report,
    enforce_research_section,
    insert_annual_observation_section,
    merge_operational_report_sections,
    normalize_final_report_md,
    normalize_formal_report_title,
    normalize_journal_section_format,
    normalize_report_section_numbering,
    repair_generic_report_titles,
    repair_journal_dates_in_report,
    repair_report_region_lines,
    has_candidate_section_mismatch,
    reconcile_report_candidate_output,
    restore_missing_selected_report_items,
    remove_missing_data_disclaimers,
    sanitize_report_text,
)
from report_prompt_service import (
    ReportPromptContext,
    build_report_prompt as service_build_report_prompt,
    research_section_heading,
)
from rss_feed_service import RssFeedContext, fetch_rss_feeds
from run_config_service import (
    RunConfigContext,
    RunSettingsContext,
    build_current_run_config,
    build_run_settings,
)
from search_queries import (
    build_region_news_sources,
    build_rss_sources,
    build_run_news_sources,
    build_standards_news_sources,
)
from search_service import (
    create_requests_session,
    fetch_feed,
    google_news_site_proxy_url,
)


@dataclass(frozen=True)
class WorkflowConfig:
    today: datetime.date
    lookback_days: int
    selected_types: list[str]
    active_regions: list[str]
    is_global_scope: bool
    standards_enabled: bool
    include_research_supplement: bool
    fast_mode_enabled: bool
    date_range: str
    report_title: str
    report_scope_label: str
    report_period_label: str
    news_scope: str = DEFAULT_NEWS_SCOPE
    research_supplement_period_label: str = "近 90 天"
    research_supplement_start_date: datetime.date | None = None

    @property
    def lookback_int(self) -> int:
        return int(self.lookback_days)

    @property
    def research_start_date(self) -> datetime.date:
        return self.research_supplement_start_date or (
            self.today - datetime.timedelta(days=90)
        )


@dataclass
class WorkflowDependencies:
    ddgs_client_factory: Callable[[], object] | None = None
    feedparser_module: object | None = None
    call_maiagent: Callable[[str], str] | None = None
    status_callback: Callable[[str], None] | None = None
    progress_callback: Callable[[float], None] | None = None
    http_session_factory: Callable[[], object] = create_requests_session
    prefetch_enabled: bool = True
    debug_stats_builder: Callable[..., dict] | None = None
    query_metadata: dict[str, dict] | None = None


@dataclass
class WorkflowResult:
    report_md: str
    selected_candidates: list[dict]
    model_candidates: list[dict]
    raw_rss: str
    raw_ddg: str
    report_prompt: str
    report_id_validation: dict
    retry_attempted: bool
    source_statuses: list[dict]
    ddgs_statuses: list[dict]
    search_count: int


def _profile_timing_add(timings: dict | None, key: str, elapsed: float) -> None:
    if timings is not None:
        timings[key] = float(timings.get(key, 0.0) or 0.0) + max(0.0, elapsed)


class WorkflowRuntime:
    def __init__(self, config: WorkflowConfig, dependencies: WorkflowDependencies):
        self.config = config
        self.dependencies = dependencies
        self.query_metadata: dict[str, dict] = dependencies.query_metadata or {}
        self.selector_api = build_selector_api(
            selected_types=config.selected_types,
            active_regions=config.active_regions,
            lookback_days=config.lookback_days,
            lookback_int=config.lookback_int,
            fast_mode_enabled=config.fast_mode_enabled,
            is_global_scope=config.is_global_scope,
            today=config.today,
            news_scope=config.news_scope,
            _search_family_from_query=self._search_family_from_query,
            _search_language_from_query=self._search_language_from_query,
            create_requests_session=dependencies.http_session_factory,
            _profile_timing_add=_profile_timing_add,
        )

    def _search_family_from_query(self, query: str) -> str:
        return _search_family_from_query(
            query,
            query_metadata=self.query_metadata,
        )

    def _search_language_from_query(self, query: str) -> str:
        return _search_language_from_query(
            query,
            query_metadata=self.query_metadata,
        )

    def _make_candidate(
        self,
        title: str,
        date: str,
        source: str,
        url: str,
        snippet: str,
        query: str,
        region: str,
        source_type: str,
        source_href: str = "",
    ) -> dict:
        return _make_news_candidate(
            title,
            date,
            source,
            url,
            snippet,
            query,
            region,
            source_type,
            source_href,
            query_metadata=self.query_metadata.get(query or "", {}),
            search_family_resolver=self._search_family_from_query,
            search_language_resolver=self._search_language_from_query,
        )

    def parse_candidates(self, raw_rss: str, raw_ddg: str) -> list[dict]:
        return parse_rss_candidates(
            raw_rss,
            lambda **kwargs: self._make_candidate(**kwargs),
        ) + parse_ddg_candidates(
            raw_ddg,
            lambda **kwargs: self._make_candidate(**kwargs),
        )

    def _rss_context(self) -> RssFeedContext:
        selector = self.selector_api
        return RssFeedContext(
            lookback_days=self.config.lookback_days,
            feedparser_module=self.dependencies.feedparser_module,
            http_session_factory=self.dependencies.http_session_factory,
            fetch_feed_callback=fetch_feed,
            fallback_url_builder=lambda source_url: self._fallback_google_news_url(source_url),
            url_safety_check=lambda url, source_href="": _is_valid_news_url(
                url,
                source_href=source_href,
                news_scope=self.config.news_scope,
            ),
            known_bad_source_checker=selector["_is_known_bad_official_rss"] if "_is_known_bad_official_rss" in selector else self._known_bad_source,
            parse_pub_date=_parse_pub_date,
            is_recent=_is_recent,
            entry_pub_str=self._entry_pub_str,
            entry_source_href=self._entry_source_href,
            contains_taiwan_reference=self._contains_taiwan_reference,
            is_standards_source=selector["_is_standards_source"],
            is_standard_update_candidate=selector["_is_standard_update_candidate"],
            is_urban_rail_candidate=selector["_is_urban_rail_candidate"],
            is_tech_news_only_mode=selector["_is_tech_news_only_mode"],
            is_technical_news_candidate=selector["_is_technical_news_candidate"],
            normalize_title=_normalize_title,
            dedupe_url=_dedupe_url,
            domain_from_url=_domain_from_url,
            status_callback=self.dependencies.status_callback,
            news_scope=self.config.news_scope,
        )

    def _fallback_google_news_url(self, source_url: str) -> str | None:
        from rss_feed_service import _fallback_google_news_url

        return _fallback_google_news_url(
            source_url,
            lookback_days=self.config.lookback_days,
            google_news_fallback_builder=lambda domain, days: google_news_site_proxy_url(
                domain,
                days,
                TRANSIT_NEWS_TERMS,
            ),
        )

    def _known_bad_source(self, source_name: str, url: str) -> bool:
        from search_queries import _is_known_bad_official_rss

        return _is_known_bad_official_rss(source_name, url)

    def _is_recent(self, pub_str: str, cutoff: datetime.datetime) -> bool:
        if not pub_str:
            return True
        try:
            value = datetime.datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=datetime.timezone.utc)
            return value > cutoff
        except Exception:
            return True

    @staticmethod
    def _entry_pub_str(entry) -> str:
        return str(entry.get("published") or entry.get("updated") or "").strip()

    @staticmethod
    def _entry_source_href(entry) -> str:
        source = entry.get("source") or {}
        if isinstance(source, dict):
            return str(source.get("href") or "").strip()
        return ""

    @staticmethod
    def _contains_taiwan_reference(text: str) -> bool:
        from article_processor import _contains_taiwan_reference

        return _contains_taiwan_reference(text)

    def build_sources(self) -> tuple[list[tuple[str, str]], list[dict]]:
        region_sources = build_region_news_sources(
            self.config.active_regions,
            self.config.lookback_days,
            fast_mode=self.config.fast_mode_enabled,
        )
        standards_sources = (
            build_standards_news_sources(self.config.lookback_days)
            if self.config.standards_enabled
            else []
        )
        return build_run_news_sources(
            region_sources,
            standards_sources,
            self.config.fast_mode_enabled,
            rss_sources=build_rss_sources(self.config.lookback_days),
            lookback_days=self.config.lookback_days,
            lookback_int=self.config.lookback_int,
            standards_enabled=self.config.standards_enabled,
            return_skipped=True,
        )

    def search(self) -> tuple[str, str, list[dict], list[dict], int]:
        sources, skipped = self.build_sources()
        rss_result, fetched_statuses = fetch_rss_feeds(
            sources,
            context=self._rss_context(),
            return_status=True,
        )
        ddgs_context = DdgsSearchContext(
            selected_types=self.config.selected_types,
            active_regions=self.config.active_regions,
            lookback_days=self.config.lookback_days,
            lookback_int=self.config.lookback_int,
            is_global_scope=self.config.is_global_scope,
            today=self.config.today,
            news_scope=self.config.news_scope,
            ddgs_client_factory=self.dependencies.ddgs_client_factory,
            query_metadata=self.query_metadata,
            progress_callback=self.dependencies.progress_callback,
            status_callback=self.dependencies.status_callback,
        )
        queries, news_indices = build_search_queries(context=ddgs_context)
        ddg_result, ddgs_statuses, _ = run_duckduckgo_searches(
            context=ddgs_context,
            search_queries=queries,
            news_query_indices=news_indices,
        )
        return (
            rss_result,
            ddg_result,
            skipped + fetched_statuses,
            ddgs_statuses,
            len(queries),
        )

    def prepare_candidate_pool(self, raw_rss: str, raw_ddg: str) -> dict:
        pool_started = time.perf_counter()
        selector = self.selector_api
        parsed_candidates = self.parse_candidates(raw_rss, raw_ddg)
        raw_candidates: list[dict] = []
        excluded_candidates: list[dict] = []
        exclusion_stats: dict[str, int] = {}
        timings = {"candidate_count": len(parsed_candidates)}
        for candidate in parsed_candidates:
            candidate["page_type"], candidate["page_type_reason"] = selector[
                "_compute_candidate_page_type"
            ](candidate)
            candidate.update(selector["evaluate_category_gates"](candidate))
            reason = selector["hard_low_value_candidate_reason"](candidate)
            if reason:
                excluded_candidates.append(
                    selector["annotate_candidate_for_scheme_d"](candidate, reason, timings)
                )
                exclusion_stats[reason] = exclusion_stats.get(reason, 0) + 1
            else:
                raw_candidates.append(
                    selector["annotate_candidate_for_scheme_d"](candidate, profile_timings=timings)
                )

        deduped_candidates, dedupe_stats = dedupe_candidates(
            raw_candidates,
            self.config.lookback_days,
        )
        if self.dependencies.prefetch_enabled:
            prefetch_stats = selector["prefetch_candidates_before_filter"](deduped_candidates)
        else:
            prefetch_stats = {
                "limit": 0,
                "eligible_count": 0,
                "attempted_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "skipped_limit_count": 0,
                "elapsed_seconds": 0.0,
            }

        filtered_candidates: list[dict] = []
        for candidate in deduped_candidates:
            if candidate.get("prefetch_status") == "success":
                refreshed = selector["annotate_candidate_for_scheme_d"](
                    candidate,
                    profile_timings=timings,
                )
                candidate.clear()
                candidate.update(refreshed)
            keep, reason = selector["preliminary_filter_candidate"](candidate)
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

        filtered_candidates.sort(
            key=lambda item: (
                -int(item.get("final_selection_score", item.get("python_score", 0)) or 0),
                -int(item.get("python_score", 0) or 0),
                _source_tier_rank(item.get("source_tier", "C_media")),
                _quality_rank(item.get("source_quality", "B")),
                0 if item.get("source_type") in {"官方 RSS", "Google News 代理"} else 1,
                -_date_sort_key(item),
            )
        )
        candidate_limit = min(
            selector["get_selection_candidate_limit"](
                self.config.lookback_int,
                fast_mode=self.config.fast_mode_enabled,
            ),
            MAX_SELECTION_CANDIDATES,
        )
        model_candidates = [
            dict(item, id=index, candidate_id=index)
            for index, item in enumerate(filtered_candidates, 1)
        ]
        candidate_cards = [
            selector["build_candidate_card"](candidate)
            for candidate in model_candidates[:candidate_limit]
        ]
        pipeline_debug_stats = (
            self.dependencies.debug_stats_builder(
                raw_candidates,
                deduped_candidates,
                model_candidates,
                excluded_candidates,
                prefetch_stats,
            )
            if self.dependencies.debug_stats_builder
            else {
                "pipeline_counts": {
                    "raw": len(raw_candidates),
                    "dedup": len(deduped_candidates),
                    "filtered": len(model_candidates),
                    "selected": 0,
                },
                "prefetch_stats": prefetch_stats,
            }
        )
        candidate_pool_timings = {
            "unit": "seconds",
            "candidate_count": len(parsed_candidates),
            "total": round(time.perf_counter() - pool_started, 4),
        }
        pipeline_debug_stats["candidate_pool_timings"] = candidate_pool_timings
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

    def select_candidates(self, model_candidates: list[dict]) -> list[dict]:
        return ensure_selected_candidate_ids(
            self.selector_api["select_candidates_by_python"](model_candidates)
        )

    def _prompt_context(self) -> ReportPromptContext:
        selector = self.selector_api
        return ReportPromptContext(
            selected_types=self.config.selected_types,
            include_research_supplement=self.config.include_research_supplement,
            standards_enabled=self.config.standards_enabled,
            lookback_int=self.config.lookback_int,
            date_range=self.config.date_range,
            report_title=self.config.report_title,
            report_scope_label=self.config.report_scope_label,
            research_supplement_period_label=self.config.research_supplement_period_label,
            research_supplement_start_date=self.config.research_start_date,
            today=self.config.today,
            empty_text_by_type=EMPTY_TEXT_BY_TYPE,
            advanced_types=REPORT_CATEGORY_TYPES,
            selection_min_items=SELECTION_MIN_ITEMS,
            selection_max_items=SELECTION_MAX_ITEMS,
            candidate_snippet_chars=CANDIDATE_SNIPPET_CHARS,
            report_snippet_chars=REPORT_SNIPPET_CHARS,
            get_selection_output_range=selector["get_selection_output_range"],
            effective_source_url=_effective_source_url,
            domain_from_url=_domain_from_url,
            extract_domain_hint=_extract_domain_hint,
            infer_preliminary_type=selector["infer_preliminary_type"],
            shorten=_shorten,
            is_standard_update_candidate=selector["_is_standard_update_candidate"],
            source_label_for_report=source_label_for_report,
            source_verb_for_report=source_verb_for_report,
        )

    def postprocess_context(self, id_validation_target: dict) -> ReportPostprocessContext:
        prompt_context = self._prompt_context()
        return ReportPostprocessContext(
            selected_types=self.config.selected_types,
            standards_enabled=self.config.standards_enabled,
            include_research_supplement=self.config.include_research_supplement,
            lookback_int=self.config.lookback_int,
            today=self.config.today,
            date_range=self.config.date_range,
            report_title=self.config.report_title,
            report_scope_label=self.config.report_scope_label,
            candidate_selection_text=self.selector_api["_candidate_selection_text"],
            infer_preliminary_type=self.selector_api["infer_preliminary_type"],
            is_urban_rail_candidate=self.selector_api["_is_urban_rail_candidate"],
            research_section_heading=lambda markdown=False: research_section_heading(
                markdown,
                context=prompt_context,
            ),
            id_validation_target=id_validation_target,
        )

    def build_report_prompt(
        self,
        selected_candidates: list[dict],
        journal_candidates: list[dict],
        search_count: int,
    ) -> str:
        return service_build_report_prompt(
            selected_candidates,
            journal_candidates,
            search_count,
            context=self._prompt_context(),
        )

    def postprocess_report_with_diagnostics(
        self,
        raw_report: str,
        selected_candidates: list[dict],
        journal_candidates: list[dict] | None = None,
        id_validation_target: dict | None = None,
    ) -> dict:
        journal_candidates = journal_candidates or []
        validation_target = id_validation_target if id_validation_target is not None else {}
        context = self.postprocess_context(validation_target)
        validated = sanitize_report_text(
            raw_report,
            selected_types=self.config.selected_types,
            standards_enabled=self.config.standards_enabled,
            include_research_supplement=self.config.include_research_supplement,
            research_section_heading=context.research_section_heading,
        )
        validated = enforce_research_section(validated, journal_candidates, context=context)
        validated = ensure_journal_summary_conclusion(validated, journal_candidates, context=context)
        validated = normalize_final_report_md(validated)
        validated = repair_journal_dates_in_report(validated, journal_candidates, context=context)
        validated = normalize_journal_section_format(validated, journal_candidates, context=context)
        validated, dropped = restore_missing_selected_report_items(
            validated,
            selected_candidates,
            context=context,
        )
        validated = repair_report_region_lines(validated, selected_candidates, context=context)
        validated = repair_generic_report_titles(validated, selected_candidates, context=context)
        validated = merge_operational_report_sections(
            validated,
            selected_types=self.config.selected_types,
            standards_enabled=self.config.standards_enabled,
        )
        validated = normalize_report_section_numbering(
            validated,
            selected_types=self.config.selected_types,
            standards_enabled=self.config.standards_enabled,
        )
        final_reconciliation = dict(context.id_validation_target)
        final_validation = validate_report_candidate_ids(validated, selected_candidates)
        if not final_validation.get("valid") or has_candidate_section_mismatch(
            validated,
            selected_candidates,
        ):
            validated, final_reconciliation = reconcile_report_candidate_output(
                validated,
                selected_candidates,
                context=context,
            )
        context.id_validation_target.clear()
        context.id_validation_target.update(final_reconciliation)
        final_skipped_ids = set(final_reconciliation.get("skipped_candidate_ids", []))
        dropped = [
            candidate
            for candidate in selected_candidates
            if int(candidate.get("candidate_id") or candidate.get("id") or 0) in final_skipped_ids
        ]
        validated = ensure_supplemental_sources_in_report(validated, selected_candidates, context=context)
        validated = remove_missing_data_disclaimers(validated)
        validated = insert_annual_observation_section(validated, context=context)
        clean = remove_internal_candidate_markers(validated)
        clean = normalize_formal_report_title(clean)
        clean = apply_final_report_footer(
            clean,
            journal_candidates,
            selected_types=self.config.selected_types,
            include_research_supplement=self.config.include_research_supplement,
            today=self.config.today,
        )
        return {
            "validated_report": validated,
            "clean_report": clean,
            "id_validation": validation_target,
            "dropped_candidates": dropped,
        }

    def postprocess_report(
        self,
        raw_report: str,
        selected_candidates: list[dict],
        journal_candidates: list[dict] | None = None,
    ) -> tuple[str, dict, list[dict]]:
        result = self.postprocess_report_with_diagnostics(
            raw_report,
            selected_candidates,
            journal_candidates,
        )
        return (
            result["clean_report"],
            result["id_validation"],
            result["dropped_candidates"],
        )


def make_runtime(config: WorkflowConfig, dependencies: WorkflowDependencies | None = None) -> WorkflowRuntime:
    return WorkflowRuntime(config, dependencies or WorkflowDependencies())


def build_report_prompt(
    selected_candidates: list[dict],
    journal_candidates: list[dict],
    search_count: int,
    *,
    config: WorkflowConfig,
    runtime: WorkflowRuntime | None = None,
) -> str:
    runtime = runtime or make_runtime(config, WorkflowDependencies(prefetch_enabled=False))
    return runtime.build_report_prompt(selected_candidates, journal_candidates, search_count)


def select_candidates_by_python(
    model_candidates: list[dict],
    *,
    config: WorkflowConfig,
    runtime: WorkflowRuntime | None = None,
) -> list[dict]:
    runtime = runtime or make_runtime(config, WorkflowDependencies(prefetch_enabled=False))
    return runtime.select_candidates(model_candidates)


def run_report_workflow(
    *,
    config: WorkflowConfig,
    dependencies: WorkflowDependencies,
) -> WorkflowResult:
    runtime = make_runtime(config, dependencies)
    raw_rss, raw_ddg, source_statuses, ddgs_statuses, search_count = runtime.search()
    candidate_pool = runtime.prepare_candidate_pool(raw_rss, raw_ddg)
    selected_candidates = runtime.select_candidates(candidate_pool["model_candidates"])
    report_prompt = runtime.build_report_prompt(selected_candidates, [], search_count)
    if not dependencies.call_maiagent:
        raise RuntimeError("未提供 MaiAgent callable")
    raw_report = dependencies.call_maiagent(report_prompt)
    validation = validate_report_candidate_ids(raw_report, selected_candidates)
    retry_attempted = False
    if not validation.get("valid"):
        retry_attempted = True
        raw_report = dependencies.call_maiagent(
            build_report_retry_prompt(report_prompt, raw_report, validation)
        )
    final_report, _, _ = runtime.postprocess_report(raw_report, selected_candidates)
    return WorkflowResult(
        report_md=final_report,
        selected_candidates=selected_candidates,
        model_candidates=candidate_pool["model_candidates"],
        raw_rss=raw_rss,
        raw_ddg=raw_ddg,
        report_prompt=report_prompt,
        report_id_validation=validate_report_candidate_ids(raw_report, selected_candidates),
        retry_attempted=retry_attempted,
        source_statuses=source_statuses,
        ddgs_statuses=ddgs_statuses,
        search_count=search_count,
    )


def build_automation_run_config(
    *,
    today: datetime.date,
    lookback_days: int,
    selected_types: list[str],
    active_regions: list[str],
    news_scope: str = DEFAULT_NEWS_SCOPE,
) -> tuple[WorkflowConfig, dict]:
    scope_mode = "指定先進國家/地區"
    settings = build_run_settings(
        RunSettingsContext(
            today=today,
            lookback_days=lookback_days,
            selected_types=selected_types,
            scope_mode=scope_mode,
            selected_regions=active_regions,
            standards_enabled=False,
            include_research_supplement=False,
            demo_cache_mode_enabled=False,
            current_app_hash="automation",
            report_period_labels={7: "週報", 30: "月報"},
            long_term_target_labels={},
            report_target_by_days={7: 3, 30: 6},
            research_supplement_allowed_for_report=lambda days: False,
            get_research_supplement_lookback_days=lambda days: 90,
        )
    )
    config = WorkflowConfig(
        today=today,
        lookback_days=settings.lookback_int,
        selected_types=selected_types,
        active_regions=settings.active_regions,
        is_global_scope=settings.is_global_scope,
        standards_enabled=False,
        include_research_supplement=False,
        fast_mode_enabled=False,
        date_range=settings.date_range,
        report_title=settings.report_title,
        report_scope_label=settings.report_scope_label,
        report_period_label=settings.report_period_label,
        news_scope=news_scope,
    )
    run_config = build_current_run_config(
        RunConfigContext(
            today=today,
            week_start=settings.week_start,
            lookback_int=settings.lookback_int,
            date_range=settings.date_range,
            report_period_label=settings.report_period_label,
            report_title=settings.report_title,
            selected_types=selected_types,
            scope_mode=scope_mode,
            is_global_scope=settings.is_global_scope,
            active_regions=settings.active_regions,
            report_scope_label=settings.report_scope_label,
            standards_enabled=False,
            include_research_supplement=False,
            research_supplement_lookback_days=90,
            research_supplement_start_date=today - datetime.timedelta(days=90),
            fast_mode_enabled=False,
            demo_cache_mode_enabled=False,
            current_app_hash="automation",
        )
    )
    return config, run_config
