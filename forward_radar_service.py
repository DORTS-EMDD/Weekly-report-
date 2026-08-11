"""Standalone monthly forward technology radar pipeline."""

from __future__ import annotations

import datetime
import json
from collections import Counter
from pathlib import Path
from typing import Callable

from article_processor import (
    _make_news_candidate,
    _shorten,
    _date_sort_key,
    dedupe_candidates,
    parse_ddg_candidates,
)
from article_selector import build_selector_api
from config import CANDIDATE_SNIPPET_CHARS
from ddgs_search_service import (
    DdgsSearchContext,
    _search_family_from_query,
    _search_language_from_query,
    build_search_queries,
    run_duckduckgo_searches,
)
from search_service import create_requests_session


DEFAULT_LOOKBACK_DAYS = 30
RADAR_QUERY_FAMILY = "forward_technology"
RADAR_SENTINEL_TYPE = "__forward_technology_radar__"


def _profile_timing_add(timings: dict | None, key: str, elapsed: float) -> None:
    if timings is not None:
        timings[key] = float(timings.get(key, 0.0) or 0.0) + max(0.0, elapsed)


def _resolve_as_of_date(as_of_date: datetime.date | None) -> datetime.date:
    return as_of_date or datetime.date.today()


def _resolve_ddgs_factory(ddgs_client_factory: Callable[[], object] | None):
    if ddgs_client_factory is not None:
        return ddgs_client_factory
    from ddgs import DDGS

    return DDGS


def _build_selector(*, as_of_date: datetime.date, lookback_days: int, query_metadata: dict[str, dict]) -> dict:
    def search_family_resolver(query: str) -> str:
        return _search_family_from_query(query, query_metadata=query_metadata)

    def search_language_resolver(query: str) -> str:
        return _search_language_from_query(query, query_metadata=query_metadata)

    return build_selector_api(
        selected_types=["技術新知"],
        active_regions=[],
        lookback_days=lookback_days,
        lookback_int=lookback_days,
        fast_mode_enabled=False,
        is_global_scope=True,
        today=as_of_date,
        _search_family_from_query=search_family_resolver,
        _search_language_from_query=search_language_resolver,
        create_requests_session=create_requests_session,
        _profile_timing_add=_profile_timing_add,
    )


def _build_candidate_factory(query_metadata: dict[str, dict]):
    def search_family_resolver(query: str) -> str:
        return _search_family_from_query(query, query_metadata=query_metadata)

    def search_language_resolver(query: str) -> str:
        return _search_language_from_query(query, query_metadata=query_metadata)

    def make_candidate(**kwargs) -> dict:
        query = kwargs.get("query", "")
        return _make_news_candidate(
            **kwargs,
            query_metadata=query_metadata.get(query, {}),
            search_family_resolver=search_family_resolver,
            search_language_resolver=search_language_resolver,
        )

    return make_candidate


def _candidate_summary(candidate: dict) -> str:
    return _shorten(
        candidate.get("snippet") or candidate.get("title", ""),
        CANDIDATE_SNIPPET_CHARS,
    )


def _technical_field(candidate: dict) -> str:
    tags = [str(tag).strip() for tag in candidate.get("canonical_tags", []) if str(tag).strip()]
    return "、".join(dict.fromkeys(tags)) or "前瞻技術"


def _candidate_url(candidate: dict) -> str:
    return (
        candidate.get("resolved_article_url")
        or candidate.get("source_href")
        or candidate.get("url", "")
    )


def _candidate_output(candidate: dict) -> dict:
    return {
        "title": candidate.get("title", ""),
        "url": _candidate_url(candidate),
        "source": candidate.get("source_display") or candidate.get("source", ""),
        "date": candidate.get("date", ""),
        "region": candidate.get("region", "未判定"),
        "search_family": candidate.get("search_family", ""),
        "forward_status": candidate.get("forward_status", "rejected"),
        "forward_gate_signals": candidate.get("forward_gate_signals", {}),
        "forward_gate_failure_reasons": candidate.get("forward_gate_failure_reasons", []),
        "radar_watchlist_pass": bool(candidate.get("radar_watchlist_pass")),
        "radar_watchlist_signals": candidate.get("radar_watchlist_signals", {}),
        "radar_watchlist_failure_reasons": candidate.get("radar_watchlist_failure_reasons", []),
        "innovation_score": int(candidate.get("innovation_score", 0) or 0),
        "innovation_level": candidate.get("innovation_level", "C"),
        "final_selection_score": int(candidate.get("final_selection_score", 0) or 0),
        "technical_field": _technical_field(candidate),
        "summary": _candidate_summary(candidate),
    }


def _radar_sort_key(candidate: dict) -> tuple:
    level_rank = {"A": 0, "B": 1, "C": 2}
    return (
        level_rank.get(candidate.get("innovation_level", "C"), 2),
        -int(candidate.get("innovation_score", 0) or 0),
        -int(candidate.get("final_selection_score", 0) or 0),
        str(candidate.get("source_quality", "C")),
        -_date_sort_key(candidate),
        str(candidate.get("title", "")),
        str(candidate.get("url", "")),
    )


def _rejected_summary(candidates: list[dict]) -> dict:
    reason_counts: Counter[str] = Counter()
    for candidate in candidates:
        reasons = candidate.get("forward_gate_failure_reasons", []) or []
        if not reasons:
            reasons = candidate.get("radar_watchlist_failure_reasons", []) or []
        for reason in reasons:
            reason_counts[str(reason)] += 1
    return {
        "count": len(candidates),
        "failure_reasons": dict(sorted(reason_counts.items())),
    }


def _build_markdown(result: dict) -> str:
    period = result["period"]
    counts = result["counts"]
    lines = [
        "# 國際捷運前瞻技術雷達",
        "",
        f"監測期間：{period['start_date']} ～ {period['end_date']}",
        "",
        "## 一、本期摘要",
        "",
        f"- 搜尋候選：{counts['raw']}",
        f"- 都市軌道有效：{counts['urban_rail']}",
        f"- 正式前瞻技術：{counts['report_eligible']}",
        f"- 雷達觀察：{counts['radar_watchlist']}",
        "",
        "## 二、前瞻技術案例",
        "",
    ]
    eligible = result["report_eligible"]
    if not eligible:
        lines.append("本期未發現符合正式前瞻技術門檻之案例。")
    else:
        for item in eligible:
            lines.extend(_markdown_candidate(item, include_reason=False))

    lines.extend(["", "## 三、技術雷達觀察", ""])
    watchlist = result["radar_watchlist"]
    if not watchlist:
        if eligible:
            lines.append("本期未發現需列入雷達觀察之案例。")
        else:
            lines.append("本期未發現符合前瞻技術或雷達觀察門檻之案例。")
    else:
        for item in watchlist:
            lines.extend(_markdown_candidate(item, include_reason=True))
    return "\n".join(lines).rstrip() + "\n"


def _markdown_candidate(item: dict, *, include_reason: bool) -> list[str]:
    lines = [
        f"### {item['title']}",
        "",
        f"- 日期：{item['date']}",
        f"- 國家／地區：{item['region']}",
        f"- 技術領域：{item['technical_field']}",
        f"- 原始來源：{item['source']}",
        f"- 原文連結：{item['url']}",
        f"- 創新等級：{item['innovation_level']}",
        f"- 創新分數：{item['innovation_score']}",
    ]
    if include_reason:
        reasons = item.get("forward_gate_failure_reasons", []) or [
            "嚴格 forward gate 未通過"
        ]
        lines.append(f"- 尚未進正式案例原因：{'；'.join(reasons)}")
    lines.extend(["", "摘要：", "", item["summary"], ""])
    return lines


def _build_json_payload(result: dict) -> dict:
    return {
        "period": result["period"],
        "query_family": RADAR_QUERY_FAMILY,
        "query_count": result["query_count"],
        "counts": result["counts"],
        "report_eligible": result["report_eligible"],
        "radar_watchlist": result["radar_watchlist"],
        "rejected_summary": result["rejected_summary"],
    }


def _build_period(*, as_of_date: datetime.date, lookback_days: int) -> dict:
    start_date = as_of_date - datetime.timedelta(days=max(1, lookback_days))
    return {
        "start_date": start_date.isoformat(),
        "end_date": as_of_date.isoformat(),
        "lookback_days": lookback_days,
    }


def run_forward_radar(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    as_of_date: datetime.date | None = None,
    ddgs_client_factory: Callable[[], object] | None = None,
    status_callback: Callable[[str], None] | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> dict:
    """Run only the forward technology family and return Markdown/JSON data."""
    lookback_days = int(lookback_days)
    if lookback_days <= 0:
        raise ValueError("lookback_days must be positive")
    as_of = _resolve_as_of_date(as_of_date)
    query_metadata: dict[str, dict] = {}
    context = DdgsSearchContext(
        selected_types=[RADAR_SENTINEL_TYPE],
        active_regions=[],
        lookback_days=lookback_days,
        lookback_int=lookback_days,
        is_global_scope=True,
        today=as_of,
        ddgs_client_factory=_resolve_ddgs_factory(ddgs_client_factory),
        query_metadata=query_metadata,
        status_callback=status_callback,
        progress_callback=progress_callback,
        sleep=lambda _seconds: None,
        random_uniform=lambda _start, _end: 0.0,
    )
    queries, news_query_indices = build_search_queries(
        context=context,
        include_forward_technology=True,
    )
    query_families = {
        query_metadata.get(query, {}).get("family", "")
        for query in queries
    }
    if query_families != {RADAR_QUERY_FAMILY}:
        raise RuntimeError(f"Radar query family violation: {sorted(query_families)}")

    raw_ddg, _statuses, _search_summary = run_duckduckgo_searches(
        context=context,
        search_queries=queries,
        news_query_indices=news_query_indices,
    )
    candidates = parse_ddg_candidates(
        raw_ddg,
        _build_candidate_factory(query_metadata),
    )
    candidates = [
        candidate
        for candidate in candidates
        if candidate.get("search_family") == RADAR_QUERY_FAMILY
    ]

    selector = _build_selector(
        as_of_date=as_of,
        lookback_days=lookback_days,
        query_metadata=query_metadata,
    )
    enriched_candidates: list[dict] = []
    for index, candidate in enumerate(candidates, 1):
        candidate["id"] = index
        candidate["candidate_id"] = index
        candidate["page_type"], candidate["page_type_reason"] = selector[
            "_compute_candidate_page_type"
        ](candidate)
        candidate.update(selector["evaluate_category_gates"](candidate))
        enriched = selector["annotate_candidate_for_scheme_d"](candidate)
        enriched["id"] = index
        enriched["candidate_id"] = index
        enriched_candidates.append(enriched)

    deduplicated, dedupe_stats = dedupe_candidates(enriched_candidates, lookback_days)
    deduplicated = sorted(deduplicated, key=_radar_sort_key)
    eligible = [
        candidate for candidate in deduplicated
        if candidate.get("forward_status") == "report_eligible"
    ]
    watchlist = [
        candidate for candidate in deduplicated
        if candidate.get("forward_status") == "radar_watchlist"
    ]
    rejected = [
        candidate for candidate in deduplicated
        if candidate.get("forward_status") == "rejected"
    ]
    eligible_output = [_candidate_output(candidate) for candidate in eligible]
    watchlist_output = [_candidate_output(candidate) for candidate in watchlist]
    counts = {
        "raw": len(enriched_candidates),
        "deduplicated": len(deduplicated),
        "urban_rail": sum(bool(candidate.get("urban_rail_gate")) for candidate in deduplicated),
        "report_eligible": len(eligible_output),
        "radar_watchlist": len(watchlist_output),
        "rejected": len(rejected),
    }
    result = {
        "period": _build_period(as_of_date=as_of, lookback_days=lookback_days),
        "query_count": len(queries),
        "query_families": sorted(query_families),
        "queries": list(queries),
        "counts": counts,
        "report_eligible": eligible_output,
        "radar_watchlist": watchlist_output,
        "rejected_summary": _rejected_summary(rejected),
        "dedupe_stats": dedupe_stats,
    }
    result["markdown"] = _build_markdown(result)
    result["json"] = json.dumps(
        _build_json_payload(result),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    return result


def write_forward_radar_outputs(result: dict, output_dir: str | Path = "output") -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    date_label = result["period"]["end_date"].replace("-", "")
    markdown_path = output_path / f"forward_radar_{date_label}.md"
    json_path = output_path / f"forward_radar_{date_label}.json"
    markdown_path.write_text(result["markdown"], encoding="utf-8")
    json_path.write_text(result["json"], encoding="utf-8")
    return {"markdown": markdown_path, "json": json_path}
