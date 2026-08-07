"""Pure data shaping for the developer debug JSON payload."""

import datetime
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class DeveloperDebugContext:
    current_run_config: dict
    latest_run_config: dict | None
    app_source_hash: str
    latest_report_md: str
    source_health_summary_builder: Callable[[list[dict]], dict]
    candidate_marker_remover: Callable[[str], str]
    now_provider: Callable[[], datetime.datetime] = datetime.datetime.now


def _debug_candidate_rows(items: list[dict]) -> list[dict]:
    rows = []
    for item in items or []:
        rows.append({
            "id": item.get("id", ""),
            "candidate_id": item.get("candidate_id", item.get("id", "")),
            "date": item.get("date", ""),
            "title": item.get("title", ""),
            "search_family": item.get("search_family", ""),
            "search_query": item.get("search_query", item.get("query", "")),
            "search_language": item.get("search_language", ""),
            "query_region": item.get("query_region", ""),
            "source": item.get("source", ""),
            "source_display": item.get("source_display", ""),
            "source_domain_raw": item.get("source_domain_raw", ""),
            "source_domain_normalized": item.get("source_domain_normalized", item.get("source_domain", "")),
            "quality": item.get("source_quality", ""),
            "source_tier": item.get("source_tier", ""),
            "region": item.get("region", ""),
            "type": item.get("source_type", ""),
            "page_type": item.get("page_type", ""),
            "page_type_reason": item.get("page_type_reason", ""),
            "date_validation": item.get("date_validation", ""),
            "urban_rail_gate": item.get("urban_rail_gate", ""),
            "canonical_tags": item.get("canonical_tags", []),
            "category_gates": item.get("category_gates", {}),
            "category_gate_reasons": item.get("category_gate_reasons", {}),
            "primary_category": item.get("primary_category", ""),
            "alternative_category_flags": item.get("alternative_category_flags", []),
            "accident_severity_score": item.get("accident_severity_score", 0),
            "technical_triplet_status": item.get("technical_triplet_status", ""),
            "candidate_level": item.get("candidate_level", ""),
            "preliminary_type": item.get("preliminary_type", ""),
            "python_score": item.get("python_score", ""),
            "score_reason": item.get("score_reason", ""),
            "candidate_flags": ", ".join(item.get("candidate_flags", []) or []),
            "exclude_reason": item.get("exclude_reason", ""),
            "final_exclude_reason": item.get("final_exclude_reason", ""),
            "event_fingerprint": item.get("event_fingerprint", {}),
            "duplicate_of": item.get("duplicate_of", ""),
            "selection_stage": item.get("selection_stage", ""),
            "url": item.get("url", ""),
            "classification": item.get("classification", ""),
            "reason": item.get("selected_reason", ""),
        })
    return rows


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _debug_strip_internal_fields(value):
    if isinstance(value, dict):
        return {
            key: _debug_strip_internal_fields(val)
            for key, val in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, list):
        return [_debug_strip_internal_fields(item) for item in value]
    return value


def build_developer_debug_payload(
    debug_info: dict,
    report_stats: dict,
    source_statuses: list[dict],
    *,
    context: DeveloperDebugContext,
) -> dict:
    latest_stats = debug_info.get("report_stats", report_stats or {}) if debug_info else (report_stats or {})
    run_config = (
        debug_info.get("run_config")
        or latest_stats.get("run_config")
        or context.latest_run_config
        or context.current_run_config
    )
    long_term_coverage = debug_info.get("long_term_coverage") or latest_stats.get("long_term_coverage") or {}
    source_health = debug_info.get("source_statuses", source_statuses) if debug_info else (source_statuses or [])
    source_health_summary = (
        debug_info.get("source_health_summary")
        or latest_stats.get("source_health_summary")
        or context.source_health_summary_builder(source_health)
    )
    return _json_safe({
        "run_info": {
            "generated_at": context.now_provider().isoformat(timespec="seconds"),
            "report_date": run_config.get("report_date"),
            "start_date": run_config.get("start_date"),
            "end_date": run_config.get("end_date"),
            "lookback_days": run_config.get("lookback_days"),
            "date_range": run_config.get("date_range"),
            "report_label": run_config.get("report_label"),
            "report_title": run_config.get("report_title"),
            "selected_types": run_config.get("selected_types", []),
            "selected_regions": run_config.get("selected_regions", []),
            "scope_mode": run_config.get("scope_mode"),
            "include_standards": run_config.get("include_standards"),
            "include_research_supplement": run_config.get("include_research_supplement"),
            "research_supplement_period": run_config.get("research_supplement_period", {}),
            "research_lookback_days": (run_config.get("research_supplement_period", {}) or {}).get("lookback_days"),
            "fast_mode": run_config.get("fast_mode", True),
            "demo_cache_mode": run_config.get("demo_cache_mode", False),
            "app_source_hash": context.app_source_hash,
            "selection_method": latest_stats.get("selection_method", debug_info.get("selection_method", "")),
            "long_term_coverage_warning": long_term_coverage.get("long_term_coverage_warning", False),
            "long_term_coverage_reason": long_term_coverage.get("reason", ""),
        },
        "stats": {
            "raw_count": latest_stats.get("raw_count", 0),
            "dedup_count": latest_stats.get("deduped_count", 0),
            "filtered_count": latest_stats.get("filtered_count", 0),
            "selected_count": latest_stats.get("ai_selected_count", 0),
            "final_report_count": latest_stats.get("formal_count", 0),
            "prompt_chars": latest_stats.get("prompt_chars", 0),
            "raw_chars": latest_stats.get("raw_chars", 0),
            "maiagent_calls": latest_stats.get("maiagent_call_count", 0),
            "category_counts": latest_stats.get("category_counts", {}),
            "journal_count": latest_stats.get("journal_count", 0),
            "source_count": latest_stats.get("source_count", 0),
            "ddgs_query_count": latest_stats.get("ddgs_query_count", 0),
            "ddgs_general_only_query_count": latest_stats.get("ddgs_general_only_query_count", len(debug_info.get("ddgs_general_only_queries", []))),
            "ddgs_search_summary": latest_stats.get("ddgs_search_summary", debug_info.get("ddgs_search_summary", {})),
            "planned_query_count": latest_stats.get("planned_query_count", debug_info.get("ddgs_search_summary", {}).get("planned_query_count", 0)),
            "executed_query_count": latest_stats.get("executed_query_count", debug_info.get("ddgs_search_summary", {}).get("executed_query_count", 0)),
            "query_count_by_region": latest_stats.get("query_count_by_region", debug_info.get("ddgs_search_summary", {}).get("query_count_by_region", {})),
            "query_count_by_family": latest_stats.get("query_count_by_family", debug_info.get("ddgs_search_summary", {}).get("query_count_by_family", {})),
            "query_count_by_language": latest_stats.get("query_count_by_language", debug_info.get("ddgs_search_summary", {}).get("query_count_by_language", {})),
            "no_backend_result_count": latest_stats.get("no_backend_result_count", debug_info.get("ddgs_search_summary", {}).get("no_backend_result_count", 0)),
            "all_results_basic_excluded_count": latest_stats.get("all_results_basic_excluded_count", debug_info.get("ddgs_search_summary", {}).get("all_results_basic_excluded_count", 0)),
            "query_error_count": latest_stats.get("query_error_count", debug_info.get("ddgs_search_summary", {}).get("query_error_count", 0)),
            "added_zero_count": latest_stats.get("added_zero_count", debug_info.get("ddgs_search_summary", {}).get("added_zero_count", 0)),
            "success_with_raw_count": latest_stats.get("success_with_raw_count", debug_info.get("ddgs_search_summary", {}).get("success_with_raw_count", 0)),
            "rate_limited_query_count": latest_stats.get("rate_limited_query_count", debug_info.get("ddgs_search_summary", {}).get("rate_limited_query_count", 0)),
            "DDGS_added_to_raw_count": latest_stats.get("DDGS_added_to_raw_count", debug_info.get("ddgs_search_summary", {}).get("DDGS_added_to_raw_count", 0)),
            "candidate_card_limit": latest_stats.get("candidate_card_limit", 0),
            "candidate_card_count": latest_stats.get("candidate_card_count", 0),
            "elapsed_seconds_total": latest_stats.get("elapsed_seconds_total", 0),
            "elapsed_seconds_rss": latest_stats.get("elapsed_seconds_rss", 0),
            "elapsed_seconds_ddgs": latest_stats.get("elapsed_seconds_ddgs", 0),
            "elapsed_seconds_candidate_pool": latest_stats.get("elapsed_seconds_candidate_pool", 0),
            "candidate_pool_timings": latest_stats.get("candidate_pool_timings", debug_info.get("candidate_pool_timings", debug_info.get("pipeline_debug_stats", {}).get("candidate_pool_timings", {}))),
            "elapsed_seconds_journal": latest_stats.get("elapsed_seconds_journal", 0),
            "elapsed_seconds_selection": latest_stats.get("elapsed_seconds_selection", 0),
            "elapsed_seconds_python_selection": latest_stats.get("elapsed_seconds_python_selection", 0),
            "elapsed_seconds_report": latest_stats.get("elapsed_seconds_report", 0),
            "elapsed_seconds_pdf": latest_stats.get("elapsed_seconds_pdf", 0),
            "source_health_summary": source_health_summary,
            "pipeline_counts": latest_stats.get("pipeline_counts", debug_info.get("pipeline_debug_stats", {}).get("pipeline_counts", {})),
            "prefetch_stats": latest_stats.get("prefetch_stats", debug_info.get("prefetch_stats", debug_info.get("pipeline_debug_stats", {}).get("prefetch_stats", {}))),
            "prefetch_attempted_count": latest_stats.get("prefetch_attempted_count", 0),
            "prefetch_success_count": latest_stats.get("prefetch_success_count", 0),
            "top_excluded_valuable_count": latest_stats.get("top_excluded_valuable_count", len(debug_info.get("top_excluded_valuable_candidates", []))),
            "dropped_selected_ids": latest_stats.get("dropped_selected_ids", debug_info.get("dropped_selected_ids", [])),
            "dropped_selected_titles": latest_stats.get("dropped_selected_titles", debug_info.get("dropped_selected_titles", [])),
            "dropped_selected_reasons": latest_stats.get("dropped_selected_reasons", debug_info.get("dropped_selected_reasons", [])),
            "strict_selected_count": latest_stats.get("strict_selected_count", debug_info.get("selection_debug", {}).get("strict_selected_count", 0)),
            "borderline_added_count": latest_stats.get("borderline_added_count", debug_info.get("selection_debug", {}).get("borderline_added_count", 0)),
            "B_added_count": latest_stats.get("B_added_count", debug_info.get("selection_debug", {}).get("B_added_count", 0)),
            "B_backfill_triggered": latest_stats.get("B_backfill_triggered", debug_info.get("selection_debug", {}).get("B_backfill_triggered", False)),
            "B_backfill_cap": latest_stats.get("B_backfill_cap", debug_info.get("selection_debug", {}).get("B_backfill_cap", 0)),
            "B_backfill_considered_count": latest_stats.get("B_backfill_considered_count", debug_info.get("selection_debug", {}).get("B_backfill_considered_count", 0)),
            "B_backfill_appended_ids": latest_stats.get("B_backfill_appended_ids", debug_info.get("selection_debug", {}).get("B_backfill_appended_ids", [])),
            "B_backfill_append_stage": latest_stats.get("B_backfill_append_stage", debug_info.get("selection_debug", {}).get("B_backfill_append_stage", "")),
            "shortfall_before_backfill": latest_stats.get("shortfall_before_backfill", debug_info.get("selection_debug", {}).get("shortfall_before_backfill", 0)),
            "shortfall_after_backfill": latest_stats.get("shortfall_after_backfill", debug_info.get("selection_debug", {}).get("shortfall_after_backfill", 0)),
            "backfill_reason": latest_stats.get("backfill_reason", debug_info.get("selection_debug", {}).get("backfill_reason", "")),
            "page_type_exclusion_counts": latest_stats.get("page_type_exclusion_counts", debug_info.get("pipeline_debug_stats", {}).get("page_type_exclusion_counts", {})),
            "no_category_gate_count": latest_stats.get("no_category_gate_count", debug_info.get("pipeline_debug_stats", {}).get("no_category_gate_count", 0)),
            "out_of_range_excluded_count": latest_stats.get("out_of_range_excluded_count", debug_info.get("pipeline_debug_stats", {}).get("out_of_range_excluded_count", 0)),
            "category_gate_pass_counts": latest_stats.get("category_gate_pass_counts", debug_info.get("pipeline_debug_stats", {}).get("category_gate_pass_counts", {})),
            "category_reclassification_records": latest_stats.get("category_reclassification_records", debug_info.get("pipeline_debug_stats", {}).get("category_reclassification_records", [])),
            "region_resolution_method_counts": latest_stats.get("region_resolution_method_counts", debug_info.get("pipeline_debug_stats", {}).get("region_resolution_method_counts", {})),
            "A_candidate_count": latest_stats.get("A_candidate_count", debug_info.get("pipeline_debug_stats", {}).get("A_candidate_count", 0)),
            "B_candidate_count": latest_stats.get("B_candidate_count", debug_info.get("pipeline_debug_stats", {}).get("B_candidate_count", 0)),
            "C_candidate_count": latest_stats.get("C_candidate_count", debug_info.get("pipeline_debug_stats", {}).get("C_candidate_count", 0)),
            "source_tier_counts": latest_stats.get("source_tier_counts", debug_info.get("pipeline_debug_stats", {}).get("source_tier_counts", {})),
            "multilingual_candidate_counts": latest_stats.get("multilingual_candidate_counts", debug_info.get("pipeline_debug_stats", {}).get("multilingual_candidate_counts", {})),
            "normalized_domain_change_count": latest_stats.get("normalized_domain_change_count", debug_info.get("pipeline_debug_stats", {}).get("normalized_domain_change_count", 0)),
            "incident_search_raw_count": latest_stats.get("incident_search_raw_count", debug_info.get("selection_debug", {}).get("incident_search_raw_count", 0)),
            "incident_gate_pass_count": latest_stats.get("incident_gate_pass_count", debug_info.get("selection_debug", {}).get("incident_gate_pass_count", 0)),
            "incident_selected_count": latest_stats.get("incident_selected_count", debug_info.get("selection_debug", {}).get("incident_selected_count", 0)),
            "python_incident_selected_count": latest_stats.get("python_incident_selected_count", debug_info.get("selection_debug", {}).get("python_incident_selected_count", 0)),
            "maiagent_incident_report_count": latest_stats.get("maiagent_incident_report_count", debug_info.get("selection_debug", {}).get("maiagent_incident_report_count", 0)),
            "final_incident_report_count": latest_stats.get("final_incident_report_count", debug_info.get("selection_debug", {}).get("final_incident_report_count", 0)),
            "incident_dropped_after_maiagent": latest_stats.get("incident_dropped_after_maiagent", debug_info.get("selection_debug", {}).get("incident_dropped_after_maiagent", 0)),
            "incident_coverage_warning": latest_stats.get("incident_coverage_warning", debug_info.get("selection_debug", {}).get("incident_coverage_warning", False)),
            "incident_coverage_reason": latest_stats.get("incident_coverage_reason", debug_info.get("selection_debug", {}).get("incident_coverage_reason", "")),
            "python_evaluated_candidate_count": latest_stats.get("python_evaluated_candidate_count", latest_stats.get("model_candidate_count", 0)),
            "filtered_candidates_entered_python_selection": latest_stats.get("filtered_candidates_entered_python_selection", True),
            "candidate_card_limit_applied_to_python_selection": latest_stats.get("candidate_card_limit_applied_to_python_selection", False),
            "journal_target_count": latest_stats.get("journal_target_count", debug_info.get("journal_target_count", 0)),
            "journal_selected_count": latest_stats.get("journal_selected_count", debug_info.get("journal_selected_count", 0)),
            "journal_shortfall_reason": latest_stats.get("journal_shortfall_reason", debug_info.get("journal_shortfall_reason", "")),
            "journal_summary_conclusion_chars": latest_stats.get("journal_summary_conclusion_chars", debug_info.get("journal_summary_conclusion_chars", 0)),
            "journal_exclusion_stats": latest_stats.get("journal_exclusion_stats", debug_info.get("journal_exclusion_stats", {})),
            "selection_method": latest_stats.get("selection_method", debug_info.get("selection_method", "")),
            "demo_cache_mode": latest_stats.get("demo_cache_mode", run_config.get("demo_cache_mode", False)),
            "include_research_supplement": latest_stats.get("include_research_supplement", run_config.get("include_research_supplement", False)),
            "research_supplement_period": latest_stats.get("research_supplement_period", run_config.get("research_supplement_period", {})),
            "research_lookback_days": (latest_stats.get("research_supplement_period", run_config.get("research_supplement_period", {})) or {}).get("lookback_days"),
            "report_retry_attempted": latest_stats.get("report_retry_attempted", False),
            "report_id_validation_before_retry": latest_stats.get("report_id_validation_before_retry", {}),
            "report_id_validation_after_retry": latest_stats.get("report_id_validation_after_retry", {}),
            "report_id_reconciliation": latest_stats.get("report_id_reconciliation", {}),
            "model_report_block_count": latest_stats.get("model_report_block_count", 0),
            "preserved_model_block_count": latest_stats.get("preserved_model_block_count", 0),
            "fallback_block_count": latest_stats.get("fallback_block_count", 0),
            "fallback_reason_counts": latest_stats.get("fallback_reason_counts", {}),
            "merged_event_groups": latest_stats.get("merged_event_groups", []),
            "final_unique_article_count": latest_stats.get("final_unique_article_count", latest_stats.get("formal_count", 0)),
            "final_count_by_category": latest_stats.get("final_count_by_category", latest_stats.get("category_counts", {})),
            "final_count_by_section": latest_stats.get("final_count_by_section", {}),
            "postprocess_warnings": latest_stats.get("postprocess_warnings", []),
        },
        "selection_method": latest_stats.get("selection_method", debug_info.get("selection_method", "")),
        "source_health_summary": source_health_summary,
        "source_health": source_health,
        "raw_candidates": _debug_strip_internal_fields(debug_info.get("raw_candidates", [])) if debug_info else [],
        "deduped_candidates": _debug_strip_internal_fields(debug_info.get("deduped_candidates", [])) if debug_info else [],
        "filtered_candidates": _debug_strip_internal_fields(debug_info.get("filtered_candidates", [])) if debug_info else [],
        "candidate_cards": _debug_strip_internal_fields(debug_info.get("candidate_cards", [])) if debug_info else [],
        "selected_candidates": _debug_strip_internal_fields(debug_info.get("selected_candidates", [])) if debug_info else [],
        "selected_ids": debug_info.get("selected_ids", []) if debug_info else [],
        "dropped_selected_ids": latest_stats.get("dropped_selected_ids", debug_info.get("dropped_selected_ids", [])),
        "dropped_selected_titles": latest_stats.get("dropped_selected_titles", debug_info.get("dropped_selected_titles", [])),
        "dropped_selected_reasons": latest_stats.get("dropped_selected_reasons", debug_info.get("dropped_selected_reasons", [])),
        "selection_debug": debug_info.get("selection_debug", {}) if debug_info else {},
        "pipeline_debug_stats": debug_info.get("pipeline_debug_stats", {}) if debug_info else {},
        "candidate_pool_timings": debug_info.get("candidate_pool_timings", debug_info.get("pipeline_debug_stats", {}).get("candidate_pool_timings", {})) if debug_info else {},
        "ddgs_query_statuses": debug_info.get("ddgs_query_statuses", []) if debug_info else [],
        "ddgs_search_summary": debug_info.get("ddgs_search_summary", latest_stats.get("ddgs_search_summary", {})) if debug_info else latest_stats.get("ddgs_search_summary", {}),
        "ddgs_no_backend_result_queries": debug_info.get("ddgs_no_backend_result_queries", []) if debug_info else [],
        "ddgs_all_results_basic_excluded_queries": debug_info.get("ddgs_all_results_basic_excluded_queries", []) if debug_info else [],
        "ddgs_query_errors": debug_info.get("ddgs_query_errors", []) if debug_info else [],
        "ddgs_added_zero_queries": debug_info.get("ddgs_added_zero_queries", []) if debug_info else [],
        "ddgs_success_with_raw_queries": debug_info.get("ddgs_success_with_raw_queries", []) if debug_info else [],
        "ddgs_general_only_queries": debug_info.get("ddgs_general_only_queries", []) if debug_info else [],
        "prefetch_stats": debug_info.get("prefetch_stats", debug_info.get("pipeline_debug_stats", {}).get("prefetch_stats", {})) if debug_info else {},
        "top_excluded_valuable_candidates": debug_info.get("top_excluded_valuable_candidates", debug_info.get("pipeline_debug_stats", {}).get("top_excluded_valuable_candidates", [])) if debug_info else [],
        "borderline_candidates": debug_info.get("borderline_candidates", []) if debug_info else [],
        "duplicate_event_records": debug_info.get("duplicate_event_records", []) if debug_info else [],
        "long_term_coverage": long_term_coverage,
        "report_id_validation_before_retry": debug_info.get("report_id_validation_before_retry", {}) if debug_info else {},
        "report_id_validation_after_retry": debug_info.get("report_id_validation_after_retry", {}) if debug_info else {},
        "report_id_reconciliation": debug_info.get("report_id_reconciliation", {}) if debug_info else {},
        "enriched_selected_candidates": _debug_strip_internal_fields(debug_info.get("enriched_selected_candidates", debug_info.get("selected_candidates", []))) if debug_info else [],
        "excluded_candidates": _debug_strip_internal_fields(debug_info.get("excluded_candidates", [])) if debug_info else [],
        "exclusion_stats": debug_info.get("exclusion_stats", {}) if debug_info else {},
        "dedupe_stats": debug_info.get("dedupe_stats", {}) if debug_info else {},
        "ai_unselected_stats": debug_info.get("ai_unselected_stats", {}) if debug_info else {},
        "python_unselected_stats": debug_info.get("python_unselected_stats", {}) if debug_info else {},
        "research_lookback_days": (run_config.get("research_supplement_period", {}) or {}).get("lookback_days"),
        "journal_candidates": debug_info.get("journal_candidates", []) if debug_info else [],
        "journal_selected_candidates": debug_info.get("journal_selected_candidates", debug_info.get("journal_candidates", [])) if debug_info else [],
        "journal_statuses": debug_info.get("journal_statuses", []) if debug_info else [],
        "journal_source_statuses": debug_info.get("journal_source_statuses", debug_info.get("journal_statuses", [])) if debug_info else [],
        "journal_excluded_candidates": debug_info.get("journal_excluded_candidates", []) if debug_info else [],
        "journal_exclusion_stats": debug_info.get("journal_exclusion_stats", {}) if debug_info else {},
        "journal_target_count": debug_info.get("journal_target_count", 0) if debug_info else 0,
        "journal_selected_count": debug_info.get("journal_selected_count", 0) if debug_info else 0,
        "journal_shortfall_reason": debug_info.get("journal_shortfall_reason", "") if debug_info else "",
        "journal_summary_conclusion_chars": debug_info.get("journal_summary_conclusion_chars", 0) if debug_info else 0,
        "maiagent": {
            "selection_prompt": debug_info.get("selection_prompt", "") if debug_info else "",
            "selection_response": debug_info.get("selection_response", "") if debug_info else "",
            "ai_selection_response": debug_info.get("ai_selection_response", "") if debug_info else "",
            "report_prompt": debug_info.get("report_prompt", "") if debug_info else "",
            "initial_raw_report": debug_info.get("initial_raw_report", "") if debug_info else "",
            "raw_report": debug_info.get("raw_report", "") if debug_info else "",
            "raw_report_candidate_ids": debug_info.get("raw_report_candidate_ids", []) if debug_info else [],
            "initial_report_response": debug_info.get("initial_report_response", "") if debug_info else "",
            "report_response": debug_info.get("report_response", "") if debug_info else "",
        },
        "selection_response": debug_info.get("selection_response", "") if debug_info else "",
        "ai_selection_response": debug_info.get("ai_selection_response", "") if debug_info else "",
        "report_prompt": debug_info.get("report_prompt", "") if debug_info else "",
        "report_response": debug_info.get("report_response", "") if debug_info else "",
        "raw_report_candidate_ids": debug_info.get("raw_report_candidate_ids", []) if debug_info else [],
        "report_id_validation_before_clean": debug_info.get("report_id_validation_before_clean", {}) if debug_info else {},
        "final_report_md": context.candidate_marker_remover(
            debug_info.get("latest_report_md", context.latest_report_md)
            if debug_info else context.latest_report_md
        ),
    })
