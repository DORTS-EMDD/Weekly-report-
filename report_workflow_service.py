"""Shared non-UI report workflow for Streamlit and automation."""

import datetime
from copy import deepcopy
import time
from dataclasses import dataclass
from typing import Callable

from article_processor import (
    _candidate_date_obj,
    _canonical_candidate_region,
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
    normalize_country,
    dedupe_candidates,
    parse_ddg_candidates,
    parse_rss_candidates,
    source_label_for_report,
    source_verb_for_report,
)
from article_selector import build_selector_api
from electromechanical_taxonomy import classify_candidate_electromechanical
from event_identity import annotate_event_identity
from selector_contract import (
    MODE_BUCKETED_ABSOLUTE as SELECTOR_MODE_BUCKETED_ABSOLUTE,
    MODE_CONTINUOUS_RECENT as SELECTOR_MODE_CONTINUOUS_RECENT,
    validate_selector_entries,
)
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
from temporal_retrieval_service import (
    MODE_BUCKETED_ABSOLUTE,
    TemporalRetrievalRouter,
    temporal_request_for_workflow,
    verify_route_metadata,
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
    count_authoritative_report_items,
    count_authoritative_report_items_by_category,
    count_report_items,
    count_report_items_by_category,
    ensure_journal_summary_conclusion,
    ensure_supplemental_sources_in_report,
    enforce_research_section,
    insert_annual_observation_section,
    merge_operational_report_sections,
    normalize_final_report_md,
    normalize_formal_report_title,
    normalize_journal_section_format,
    normalize_report_section_numbering,
    remove_authoritative_candidate_markers,
    remove_journal_summary_conclusion,
    repair_generic_report_titles,
    repair_journal_dates_in_report,
    repair_report_region_lines,
    has_candidate_section_mismatch,
    reconcile_report_candidate_output,
    restore_missing_selected_report_items,
    remove_missing_data_disclaimers,
    sanitize_report_text,
    validate_authoritative_report,
)


def _category_gate_snapshot(gate_payload: dict) -> dict:
    return {
        "category_gates": deepcopy(gate_payload.get("category_gates", {})),
        "category_gate_reasons": deepcopy(gate_payload.get("category_gate_reasons", {})),
        "primary_category": gate_payload.get("primary_category", ""),
        "operational_subtype": gate_payload.get("operational_subtype", ""),
        "technical_operation_incident": bool(gate_payload.get("technical_operation_incident")),
        "procurement_gate_pass": bool(gate_payload.get("procurement_gate_pass")),
        "service_opening_gate_pass": bool(gate_payload.get("service_opening_gate_pass")),
    }


def _category_gate_change_reason(before: dict, after: dict) -> str:
    before_gates = before.get("category_gates", {}) or {}
    after_gates = after.get("category_gates", {}) or {}
    changed_gates = [
        key for key in sorted(set(before_gates) | set(after_gates))
        if bool(before_gates.get(key)) != bool(after_gates.get(key))
    ]
    if changed_gates:
        reason = "category_gates_changed:" + ",".join(changed_gates)
        if before.get("primary_category") != after.get("primary_category"):
            reason += (
                "; primary_category: "
                f"{before.get('primary_category', '未判定')} -> {after.get('primary_category', '未判定')}"
            )
        return reason
    if before.get("primary_category") != after.get("primary_category"):
        return (
            "primary_category: "
            f"{before.get('primary_category', '未判定')} -> {after.get('primary_category', '未判定')}"
        )
    if before.get("category_gate_reasons") != after.get("category_gate_reasons"):
        return "category_gate_reasons_changed"
    return "no_category_gate_change"
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


class ReportIntegrityError(RuntimeError):
    """Raised before rendering or delivery when the formal report is invalid."""

    def __init__(
        self,
        validation: dict,
        selected_candidates: list[dict],
        *,
        retry_attempted: bool,
    ):
        self.validation = dict(validation or {})
        self.selected_candidates = list(selected_candidates or [])
        self.retry_attempted = bool(retry_attempted)
        reasons = []
        for key in (
            "missing_ids",
            "unknown_ids",
            "duplicate_ids",
            "missing_model_fields",
            "parser_failure_reasons",
            "category_mismatches",
            "multi_candidate_model_blocks",
            "missing_required_sections",
            "content_quality_issues",
            "forbidden_internal_phrases",
        ):
            value = self.validation.get(key)
            if value:
                reasons.append(f"{key}={value}")
        detail = "; ".join(reasons) or "report_validation_passed=false"
        super().__init__(
            "正式報告完整性驗證未通過；已中止正式報告輸出、PDF 與 Email。"
            f" retry_attempted={self.retry_attempted}; {detail}"
        )


def _profile_timing_add(timings: dict | None, key: str, elapsed: float) -> None:
    if timings is not None:
        timings[key] = float(timings.get(key, 0.0) or 0.0) + max(0.0, elapsed)


class WorkflowRuntime:
    def __init__(self, config: WorkflowConfig, dependencies: WorkflowDependencies):
        self.config = config
        self.dependencies = dependencies
        self.query_metadata: dict[str, dict] = dependencies.query_metadata or {}
        self.temporal_router = TemporalRetrievalRouter()
        self.temporal_plan = None
        self.temporal_route_metadata_by_url: dict[str, dict] = {}
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
        self.last_selection_event_consolidation_stats: dict = {
            "input_count": 0,
            "output_count": 0,
            "duplicate_count": 0,
            "duplicate_event_records": [],
        }

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
        raw_provenance: dict | None = None,
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
            raw_provenance=raw_provenance,
        )

    def parse_candidates(self, raw_rss: str, raw_ddg: str) -> list[dict]:
        return parse_rss_candidates(
            raw_rss,
            lambda **kwargs: self._make_candidate(**kwargs),
        ) + parse_ddg_candidates(
            raw_ddg,
            lambda **kwargs: self._make_candidate(**kwargs),
        )

    def _temporal_verify_result(
        self,
        route_metadata: dict,
        raw_publication_value: object,
        date_source: str,
    ) -> dict:
        verification = verify_route_metadata(
            route_metadata,
            raw_publication_value,
            date_source=date_source,
        )
        if self.temporal_plan is not None:
            route_id = str(route_metadata.get("route_id") or "")
            if route_id:
                self.temporal_plan.record(route_id, "retrieved")
                self.temporal_plan.record(route_id, verification.status)
        return {
            "status": verification.status,
            "normalized_publication_date": verification.normalized_publication_date,
            "date_source": verification.date_source,
            "verified_bucket": verification.verified_bucket,
        }

    def _temporal_event(self, route_metadata: dict, status: str) -> None:
        if self.temporal_plan is None:
            return
        route_id = str(route_metadata.get("route_id") or "")
        if route_id:
            self.temporal_plan.record(route_id, status)

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
            temporal_route_metadata_by_url=self.temporal_route_metadata_by_url,
            temporal_result_verifier=self._temporal_verify_result,
            temporal_event_callback=self._temporal_event,
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
        sources, skipped = build_run_news_sources(
            region_sources,
            standards_sources,
            self.config.fast_mode_enabled,
            rss_sources=build_rss_sources(self.config.lookback_days),
            lookback_days=self.config.lookback_days,
            lookback_int=self.config.lookback_int,
            standards_enabled=self.config.standards_enabled,
            return_skipped=True,
        )
        request = temporal_request_for_workflow(
            report_date=self.config.today,
            lookback_days=self.config.lookback_days,
            selected_types=self.config.selected_types,
            active_regions=self.config.active_regions,
            include_forward_technology="技術新知" in self.config.selected_types,
        )
        self.temporal_plan = self.temporal_router.build_plan(request)
        self.temporal_route_metadata_by_url = {}
        if self.temporal_plan.mode == MODE_BUCKETED_ABSOLUTE:
            temporal_sources = []
            for route in self.temporal_plan.routes:
                temporal_sources.append((route.source_name, route.url))
                self.temporal_route_metadata_by_url[route.url] = route.metadata
            sources.extend(temporal_sources)
        return sources, skipped

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
        include_forward_technology = (
            "技術新知" in self.config.selected_types
        )
        queries, news_indices = build_search_queries(
            context=ddgs_context,
            include_forward_technology=include_forward_technology,
        )
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

    def _record_temporal_candidate_stage(self, candidate: dict, field: str) -> None:
        if self.temporal_plan is None or self.temporal_plan.mode != MODE_BUCKETED_ABSOLUTE:
            return
        route_ids = list(candidate.get("retrieval_lanes") or [])
        if not route_ids and candidate.get("route_id"):
            route_ids = [str(candidate.get("route_id"))]
        for route_id in dict.fromkeys(str(value) for value in route_ids if value):
            self.temporal_plan.record(route_id, field)

    def _materialize_authoritative_candidate(self, candidate: dict, *, authoritative: bool = True) -> dict:
        """Materialize all formal fields after the latest enrichment pass."""
        resolved_region = _canonical_candidate_region(candidate)
        candidate["resolved_region"] = resolved_region
        candidate["country"] = normalize_country(resolved_region)

        taxonomy = classify_candidate_electromechanical(candidate)
        candidate["core_systems"] = list(taxonomy.get("systems", []) or [])
        candidate["electromechanical_classification"] = list(candidate["core_systems"])
        candidate["electromechanical_winning_evidence"] = list(
            taxonomy.get("winning_evidence", []) or []
        )[:16]
        candidate["electromechanical_rejected_evidence"] = list(
            taxonomy.get("rejected_evidence", []) or []
        )[:12]
        candidate["electromechanical_classification_reason"] = str(
            taxonomy.get("classification_reason", "") or ""
        )
        candidate["authoritative_materialization_stage"] = (
            "post_enrichment" if authoritative else "provisional"
        )

        gate_payload = self.selector_api["evaluate_category_gates"](candidate)
        candidate.update(gate_payload)
        primary_category = str(candidate.get("primary_category") or "").strip()
        candidate["classification"] = primary_category
        candidate["preliminary_type"] = primary_category

        # The A5 owner is the only place that materializes/reconciles event IDs.
        annotate_event_identity(candidate)
        return candidate

    def _selector_temporal_mode(self) -> str:
        if self.config.today is None or self.config.lookback_days is None:
            raise RuntimeError("PIPELINE_CONTRACT_ERROR: temporal mode/report date is missing")
        if self.temporal_plan is not None:
            if self.temporal_plan.mode == MODE_BUCKETED_ABSOLUTE:
                return SELECTOR_MODE_BUCKETED_ABSOLUTE
            if self.temporal_plan.mode == SELECTOR_MODE_CONTINUOUS_RECENT:
                return SELECTOR_MODE_CONTINUOUS_RECENT
            raise RuntimeError("PIPELINE_CONTRACT_ERROR: temporal mode is invalid")
        return (
            SELECTOR_MODE_BUCKETED_ABSOLUTE
            if int(self.config.lookback_days) >= 365
            else SELECTOR_MODE_CONTINUOUS_RECENT
        )

    def _validate_selector_entry(self, candidates: list[dict]) -> tuple[list[dict], list[dict]]:
        accepted, excluded = validate_selector_entries(
            candidates,
            temporal_mode=self._selector_temporal_mode(),
            today=self.config.today,
            lookback_days=self.config.lookback_days,
        )
        for candidate in accepted:
            candidate["recent_window_valid"] = (
                self._selector_temporal_mode() == SELECTOR_MODE_CONTINUOUS_RECENT
                and candidate.get("date_validation") == "valid_in_range"
            )
        return accepted, excluded

    def prepare_candidate_pool(self, raw_rss: str, raw_ddg: str) -> dict:
        pool_started = time.perf_counter()
        selector = self.selector_api
        parse_started = time.perf_counter()
        parsed_candidates = self.parse_candidates(raw_rss, raw_ddg)
        parse_elapsed = time.perf_counter() - parse_started
        raw_candidates: list[dict] = []
        excluded_candidates: list[dict] = []
        exclusion_stats: dict[str, int] = {}
        timings = {
            "candidate_count": len(parsed_candidates),
            "parse_candidates": parse_elapsed,
        }
        gate_started = time.perf_counter()
        for candidate in parsed_candidates:
            candidate["page_type"], candidate["page_type_reason"] = selector[
                "_compute_candidate_page_type"
            ](candidate)
            self._materialize_authoritative_candidate(candidate, authoritative=False)
            initial_gate_snapshot = _category_gate_snapshot(candidate)
            candidate["category_gate_before_enrichment"] = initial_gate_snapshot
            candidate["category_gate_after_enrichment"] = deepcopy(initial_gate_snapshot)
            candidate["category_changed_after_enrichment"] = False
            candidate["category_change_reason"] = "not_enriched"
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
        timings["page_type_and_category_gates"] = time.perf_counter() - gate_started

        dedupe_started = time.perf_counter()
        deduped_candidates, dedupe_stats = dedupe_candidates(
            raw_candidates,
            self.config.lookback_days,
        )
        timings["event_dedupe"] = time.perf_counter() - dedupe_started
        prefetch_started = time.perf_counter()
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
                "rescue_candidate_count": 0,
                "rescue_enrichment_attempted_count": 0,
                "rescue_enrichment_success_count": 0,
                "forward_enrichment_budget": 0,
                "general_rescue_budget": 0,
                "annual_general_rescue_budget": 0,
                "forward_enrichment_candidate_count": 0,
                "forward_enrichment_attempted_count": 0,
                "forward_enrichment_success_count": 0,
                "forward_enrichment_skipped_count": 0,
                "forward_enrichment_failure_reason_counts": {},
                "annual_rescue_candidate_count": 0,
                "annual_rescue_attempted_by_bucket": {},
                "annual_rescue_success_by_bucket": {},
                "track_b_gate_pass_before_enrichment_count": 0,
                "track_b_gate_pass_after_enrichment_count": 0,
                "elapsed_seconds": 0.0,
            }
        timings["prefetch"] = time.perf_counter() - prefetch_started

        filtered_candidates: list[dict] = []
        preliminary_started = time.perf_counter()
        for candidate in deduped_candidates:
            if candidate.get("prefetch_status") == "success":
                before_enrichment = candidate.get("category_gate_before_enrichment") or _category_gate_snapshot(
                    candidate
                )
                self._materialize_authoritative_candidate(candidate)
                after_enrichment = _category_gate_snapshot(candidate)
                candidate["category_gate_before_enrichment"] = deepcopy(before_enrichment)
                candidate["category_gate_after_enrichment"] = deepcopy(after_enrichment)
                candidate["category_changed_after_enrichment"] = before_enrichment != after_enrichment
                candidate["category_change_reason"] = _category_gate_change_reason(
                    before_enrichment,
                    after_enrichment,
                )
                refreshed = selector["annotate_candidate_for_scheme_d"](
                    candidate,
                    profile_timings=timings,
                )
                candidate.clear()
                candidate.update(refreshed)
            else:
                self._materialize_authoritative_candidate(candidate)
            keep, reason = selector["preliminary_filter_candidate"](candidate)
            if keep:
                if any((candidate.get("category_gates") or {}).values()):
                    self._record_temporal_candidate_stage(candidate, "gate_pass")
                candidate["recent_window_valid"] = candidate.get("date_validation") == "valid_in_range"
                candidate["exclude_reason"] = ""
                candidate["final_exclude_reason"] = ""
                candidate["selection_stage"] = "candidate_pool"
                self._record_temporal_candidate_stage(candidate, "selector_input")
                filtered_candidates.append(candidate)
            else:
                candidate["exclude_reason"] = reason
                candidate["final_exclude_reason"] = reason
                candidate["selection_stage"] = "excluded"
                excluded_candidates.append(candidate)
                exclusion_stats[reason] = exclusion_stats.get(reason, 0) + 1
        timings["preliminary_filter"] = time.perf_counter() - preliminary_started

        contract_started = time.perf_counter()
        contract_ready, contract_excluded = self._validate_selector_entry(filtered_candidates)
        if contract_excluded:
            excluded_candidates.extend(contract_excluded)
            exclusion_stats["selector_contract_violation"] = len(contract_excluded)
        filtered_candidates = contract_ready
        timings["selector_entry_contract"] = time.perf_counter() - contract_started

        # A5 reconciliation is an upstream event-identity operation.  Run it
        # once more after enrichment so that evidence revealed by prefetch can
        # participate in the canonical event decision before selector entry.
        post_enrichment_dedupe_started = time.perf_counter()
        filtered_candidates, post_enrichment_dedupe_stats = dedupe_candidates(
            filtered_candidates,
            self.config.lookback_days,
        )
        timings["post_enrichment_event_identity"] = (
            time.perf_counter() - post_enrichment_dedupe_started
        )

        for candidate in filtered_candidates:
            selector["materialize_selector_quality"](candidate)

        event_consolidation_started = time.perf_counter()
        consolidate_events = selector.get("consolidate_event_candidates")
        if callable(consolidate_events):
            filtered_candidates, event_consolidation_stats = consolidate_events(filtered_candidates)
        else:
            event_consolidation_stats = {
                "input_count": len(filtered_candidates),
                "output_count": len(filtered_candidates),
                "duplicate_count": 0,
                "duplicate_event_records": [],
            }
        timings["event_consolidation"] = time.perf_counter() - event_consolidation_started

        sorting_started = time.perf_counter()
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
        timings["sorting_and_card_build"] = time.perf_counter() - sorting_started
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
        candidate_pool_timings.update({
            name: round(value, 4)
            for name, value in timings.items()
            if name != "candidate_count" and isinstance(value, (int, float))
        })
        pipeline_debug_stats["candidate_pool_timings"] = candidate_pool_timings
        pipeline_debug_stats.setdefault("pipeline_stages", {}).update({
            "raw": len(raw_candidates),
            "dedup": len(deduped_candidates),
            "filtered": len(filtered_candidates),
            "gate_pass": sum(
                1
                for item in filtered_candidates
                if any((item.get("category_gates") or {}).values())
            ),
            "rescue_candidate": int(prefetch_stats.get("rescue_candidate_count", 0) or 0),
            "rescue_enriched": int(prefetch_stats.get("rescue_enrichment_success_count", 0) or 0),
            "selected": 0,
            "model": len(model_candidates),
            "final": 0,
        })
        pipeline_debug_stats["event_consolidation_stats"] = event_consolidation_stats
        pipeline_debug_stats["post_enrichment_dedupe_stats"] = post_enrichment_dedupe_stats
        pipeline_debug_stats["temporal_retrieval"] = self.temporal_router.diagnostics(
            self.temporal_plan
        )
        return {
            "raw_candidates": raw_candidates,
            "deduped_candidates": deduped_candidates,
            "filtered_candidates": model_candidates,
            "excluded_candidates": excluded_candidates,
            "model_candidates": model_candidates,
            "candidate_cards": candidate_cards,
            "candidate_card_limit": candidate_limit,
            "dedupe_stats": dedupe_stats,
            "post_enrichment_dedupe_stats": post_enrichment_dedupe_stats,
            "event_consolidation_stats": event_consolidation_stats,
            "prefetch_stats": prefetch_stats,
            "exclusion_stats": exclusion_stats,
            "pipeline_debug_stats": pipeline_debug_stats,
            "candidate_pool_timings": candidate_pool_timings,
            "raw_count": len(raw_candidates),
            "deduped_count": len(deduped_candidates),
            "filtered_count": len(model_candidates),
            "temporal_diagnostics": self.temporal_router.diagnostics(self.temporal_plan),
        }

    def select_candidates(self, model_candidates: list[dict]) -> list[dict]:
        incoming_candidates = list(model_candidates or [])
        model_candidates, contract_excluded = self._validate_selector_entry(
            incoming_candidates
        )
        for candidate in model_candidates:
            self.selector_api["materialize_selector_quality"](candidate)
        selected = ensure_selected_candidate_ids(
            self.selector_api["select_candidates_by_python"](model_candidates)
        )
        consolidate_events = self.selector_api.get("consolidate_event_candidates")
        if not callable(consolidate_events):
            self.last_selection_event_consolidation_stats = {
                "input_count": len(selected),
                "output_count": len(selected),
                "duplicate_count": 0,
                "duplicate_event_records": [],
                "stage": "post_selection",
            }
            for candidate in selected:
                self._record_temporal_candidate_stage(candidate, "selected")
            return selected

        selected_ids_before = [
            int(item.get("candidate_id") or item.get("id") or 0)
            for item in selected
        ]
        selected, stats = consolidate_events(selected)
        stats = dict(stats)
        stats.update({
            "stage": "post_selection",
            "selected_ids_before_consolidation": selected_ids_before,
            "selected_ids_after_consolidation": [
                int(item.get("candidate_id") or item.get("id") or 0)
                for item in selected
            ],
        })
        if stats.get("duplicate_count", 0):
            for index, candidate in enumerate(selected, 1):
                candidate["id"] = index
                candidate["candidate_id"] = index
            stats["selected_ids_after_id_assignment"] = [
                int(item.get("candidate_id") or item.get("id") or 0)
                for item in selected
            ]
        self.last_selection_event_consolidation_stats = stats
        for candidate in selected:
            self._record_temporal_candidate_stage(candidate, "selected")
        return ensure_selected_candidate_ids(selected)

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
        authoritative_report_md = raw_report if isinstance(raw_report, str) else str(raw_report or "")
        validation_target = id_validation_target if id_validation_target is not None else {}
        if self.config.include_research_supplement:
            authoritative_report_md = remove_journal_summary_conclusion(authoritative_report_md)
            if journal_candidates:
                authoritative_report_md = normalize_journal_section_format(
                    authoritative_report_md,
                    journal_candidates,
                    context=self.postprocess_context(validation_target),
                )
        validation = validate_authoritative_report(
            authoritative_report_md,
            selected_candidates,
            selected_types=self.config.selected_types,
        )
        model_ids = list(validation.get("model_candidate_ids", []))
        selected_ids = list(validation.get("selected_candidate_ids", []))
        article_count = int(validation.get("report_article_count", 0) or 0)
        category_counts = dict(validation.get("report_category_counts", {}))
        validation.update({
            "postprocess_mode": "authoritative_passthrough",
            "final_candidate_ids": model_ids,
            "expected_final_candidate_ids": selected_ids,
            "final_candidate_id_count": len(set(model_ids)),
            "final_candidate_id_integrity_passed": bool(validation.get("valid")),
            "selected_to_final_id_coverage": validation.get("selected_to_model_id_coverage", 1.0),
            "final_unique_article_count": article_count,
            "reconciled_accepted_count": article_count,
            "final_rendered_report_count": article_count,
            "final_count_by_category": category_counts,
            "rendered_count_by_category": category_counts,
            "fallback_candidate_ids": [],
            "fallback_block_count": 0,
            "fallback_reason_counts": {},
            "skipped_candidate_ids": [],
            "intentional_exclusion_ids": [],
            "model_report_block_count": article_count,
            "preserved_model_block_count": article_count,
            "postprocess_warnings": [],
            "after_reconcile": dict(validation),
        })
        validation_target.clear()
        validation_target.update(validation)
        clean = remove_authoritative_candidate_markers(authoritative_report_md)
        dropped = []
        return {
            "validated_report": authoritative_report_md,
            "clean_report": clean,
            "id_validation": validation_target,
            "dropped_candidates": dropped,
            "reconciled_accepted_count": article_count,
            "final_rendered_report_count": article_count,
            "final_count_by_category": category_counts,
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
    validation = validate_authoritative_report(
        raw_report,
        selected_candidates,
        selected_types=config.selected_types,
    )
    retry_attempted = False
    if validation.get("retry_required"):
        retry_attempted = True
        raw_report = dependencies.call_maiagent(
            build_report_retry_prompt(
                report_prompt,
                raw_report,
                validation,
                selected_candidates=selected_candidates,
            )
        )
    final_validation = validate_authoritative_report(
        raw_report,
        selected_candidates,
        selected_types=config.selected_types,
    )
    if not final_validation.get("report_validation_passed"):
        raise ReportIntegrityError(
            final_validation,
            selected_candidates,
            retry_attempted=retry_attempted,
        )
    final_report, _, _ = runtime.postprocess_report(raw_report, selected_candidates)
    return WorkflowResult(
        report_md=final_report,
        selected_candidates=selected_candidates,
        model_candidates=candidate_pool["model_candidates"],
        raw_rss=raw_rss,
        raw_ddg=raw_ddg,
        report_prompt=report_prompt,
        report_id_validation=final_validation,
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
