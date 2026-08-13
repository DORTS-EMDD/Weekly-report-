"""Standalone monthly monitoring for formal metro electromechanical standard updates."""

from __future__ import annotations

import datetime
import json
import re
from collections import Counter
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from article_processor import (
    _candidate_date_obj,
    _date_sort_key,
    _make_news_candidate,
    _shorten,
    parse_ddg_candidates,
)
from config import DDGS_RESULTS_PER_QUERY
from ddgs_search_service import DdgsSearchContext, run_duckduckgo_searches


STANDARDS_UPDATE_QUERY_FAMILY = "standards_update"
STANDARDS_SENTINEL_TYPE = "__standards_update_monthly__"
DEFAULT_OUTPUT_PREFIX = "standards_monthly"

STANDARDS_UPDATE_QUERIES = (
    'IEC railway metro signalling safety "revised edition" amendment published',
    '(EN OR CEN OR CENELEC) railway metro signalling safety amendment superseded revised',
    'IEEE rail transit signalling train control standard "new edition" revision',
    'ISO railway metro electrical safety standard amendment published',
)

STANDARD_IDENTIFIER_RE = re.compile(
    r"\b(?:IEC|IEEE|EN|ISO)\s*\d{3,6}(?:[.\-/]\d+)*(?::\d{4})?\b",
    re.IGNORECASE,
)

OFFICIAL_STANDARD_DOMAINS = frozenset(
    {
        "iec.ch",
        "webstore.iec.ch",
        "standards.ieee.org",
        "ieeexplore.ieee.org",
        "iso.org",
        "www.iso.org",
        "cen.eu",
        "cencenelec.eu",
        "standards.cencenelec.eu",
        "cenelec.eu",
    }
)

RAIL_RELEVANCE_TERMS = (
    "railway", "rail rail", "rail transit", "metro", "mrt", "subway", "urban rail",
    "light rail", "tram", "transit", "rolling stock", "train control", "cbtc",
    "鐵道", "鐵路", "捷運", "都市軌道", "號誌", "信號", "車輛",
)

ELECTROMECHANICAL_RELEVANCE_TERMS = (
    "signalling", "signaling", "train control", "cbtc", "rams", "safety",
    "software", "cybersecurity", "cyber security", "emc", "telecommunication",
    "communication network", "traction", "electrical", "rolling stock",
    "fire", "life safety", "platform screen door", "power supply", "電力",
    "供電", "號誌", "通訊", "資安", "安全", "車輛", "機電",
)

MARKETING_TERMS = (
    "complies with", "compliant with", "in compliance with", "training course",
    "certification advertisement", "buy standard", "cheap download", "download pdf",
    "標準下載", "便宜下載", "符合 iec", "符合 en", "符合 iso", "培訓課程",
)

DRAFT_OR_PROPOSAL_TERMS = (
    "draft", "draft for comment", "public comment", "public consultation",
    "committee draft", "committee meeting", "working group", "future revision",
    "proposed revision", "under development", "consultation", "discussion",
    "草案", "公開徵詢", "公眾諮詢", "委員會討論", "工作小組", "擬議修訂",
    "研議", "制定中",
)

FORMAL_RELEASE_TERMS = (
    "published", "publication", "released", "release", "issued", "officially",
    "發布", "發佈", "出版", "公告", "正式版本", "正式發布",
)

UPDATE_TYPE_PATTERNS = (
    (
        "withdrawn",
        ("withdrawn", "withdrawal", "廢止", "撤銷", "撤回"),
    ),
    (
        "superseded",
        ("superseded", "supersedes", "被取代", "取代"),
    ),
    (
        "corrigendum",
        ("corrigendum", "勘誤"),
    ),
    (
        "amendment",
        ("amendment", "amended", "增補", "修正案", "增修"),
    ),
    (
        "new_edition",
        ("new edition", "revised edition", "new version", "version released", "新版", "新版發布"),
    ),
    (
        "revision",
        ("revision published", "revised", "修訂發布", "修訂版", "修訂"),
    ),
    (
        "published",
        ("published standard", "standard published", "正式版本", "正式發布"),
    ),
)


def _resolve_as_of_date(as_of_date: datetime.date | None) -> datetime.date:
    return as_of_date or datetime.date.today()


def previous_calendar_month(
    as_of_date: datetime.date | None = None,
) -> tuple[datetime.date, datetime.date]:
    as_of = _resolve_as_of_date(as_of_date)
    first_current = as_of.replace(day=1)
    end_previous = first_current - datetime.timedelta(days=1)
    start_previous = end_previous.replace(day=1)
    return start_previous, end_previous


def _resolve_period(
    *,
    as_of_date: datetime.date | None,
    start_date: datetime.date | None,
    end_date: datetime.date | None,
) -> tuple[datetime.date, datetime.date]:
    if (start_date is None) != (end_date is None):
        raise ValueError("start_date and end_date must be provided together")
    if start_date is None:
        return previous_calendar_month(as_of_date)
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    return start_date, end_date


def _standard_query_metadata(query: str, index: int) -> dict:
    return {
        "family": STANDARDS_UPDATE_QUERY_FAMILY,
        "lang": "en",
        "query_region": "global",
        "use_news": True,
        "requested_max_results": DDGS_RESULTS_PER_QUERY,
        "planned_index": index,
    }


def build_standards_update_queries() -> tuple[list[str], dict[str, dict]]:
    queries = list(STANDARDS_UPDATE_QUERIES)
    metadata = {
        query: _standard_query_metadata(query, index)
        for index, query in enumerate(queries, 1)
    }
    return queries, metadata


def _resolve_ddgs_factory(ddgs_client_factory: Callable[[], object] | None):
    if ddgs_client_factory is not None:
        return ddgs_client_factory
    from ddgs import DDGS

    return DDGS


def _build_candidate_factory(query_metadata: dict[str, dict]):
    def search_family_resolver(_query: str) -> str:
        return STANDARDS_UPDATE_QUERY_FAMILY

    def search_language_resolver(_query: str) -> str:
        return "en"

    def make_candidate(**kwargs) -> dict:
        query = kwargs.get("query", "")
        return _make_news_candidate(
            **kwargs,
            query_metadata=query_metadata.get(query, {}),
            search_family_resolver=search_family_resolver,
            search_language_resolver=search_language_resolver,
        )

    return make_candidate


def _candidate_text(candidate: dict) -> str:
    return " ".join(
        str(candidate.get(key, "") or "")
        for key in ("title", "snippet", "source", "url", "source_href")
    ).strip()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in terms)


def _extract_standard_identifier(text: str) -> str:
    match = STANDARD_IDENTIFIER_RE.search(text or "")
    return re.sub(r"\s+", " ", match.group(0).upper()).strip() if match else ""


def _standard_organization(text: str, standard_identifier: str) -> str:
    lowered = text.casefold()
    if "cenelec" in lowered:
        return "CENELEC"
    if re.search(r"\bcen\b", lowered):
        return "CEN"
    return standard_identifier.split(" ", 1)[0] if standard_identifier else ""


def _standard_update_type(text: str) -> str:
    lowered = text.casefold()
    for update_type, terms in UPDATE_TYPE_PATTERNS:
        if any(term.casefold() in lowered for term in terms):
            return update_type
    if re.search(r"\b(?:standard|edition|version)\s+(?:published|released|issued)\b", lowered):
        return "published"
    return ""


def _source_host(candidate: dict) -> str:
    for key in ("resolved_article_url", "source_href", "url"):
        value = str(candidate.get(key, "") or "")
        host = urlparse(value).netloc.casefold().removeprefix("www.")
        if host and host != "news.google.com":
            return host
    return ""


def _is_official_source(candidate: dict) -> bool:
    host = _source_host(candidate)
    return any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_STANDARD_DOMAINS)


def _edition_marker(text: str) -> str:
    match = re.search(
        r"(?:edition|version|revision|amendment|修訂版|新版)[^\d]{0,14}(20\d{2})",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _standard_event_key(candidate: dict) -> tuple[str, str, str, str]:
    text = _candidate_text(candidate)
    date = _candidate_date_obj(candidate.get("date", ""))
    month = date.strftime("%Y-%m") if date else "undated"
    return (
        candidate.get("standard_organization", ""),
        candidate.get("standard_identifier", ""),
        candidate.get("standard_update_type", ""),
        _edition_marker(text) or month,
    )


def _candidate_preference(candidate: dict) -> tuple:
    quality_rank = {"A": 0, "B": 1, "C": 2}.get(candidate.get("source_quality", "C"), 2)
    return (
        0 if candidate.get("standards_update_gate_pass") else 1,
        0 if candidate.get("source_official") else 1,
        quality_rank,
        -_date_sort_key(candidate),
        str(candidate.get("title", "")),
        str(candidate.get("url", "")),
    )


def _dedupe_standard_events(candidates: list[dict]) -> tuple[list[dict], dict[str, int]]:
    groups: dict[tuple[str, str, str, str], list[dict]] = {}
    for candidate in candidates:
        groups.setdefault(_standard_event_key(candidate), []).append(candidate)
    deduped: list[dict] = []
    duplicate_count = 0
    for key in sorted(groups, key=lambda value: tuple(str(part) for part in value)):
        group = sorted(groups[key], key=_candidate_preference)
        deduped.append(group[0])
        duplicate_count += max(0, len(group) - 1)
    return deduped, {"standard_event_duplicate": duplicate_count}


def _evaluate_candidate(candidate: dict, start_date: datetime.date, end_date: datetime.date) -> dict:
    text = _candidate_text(candidate)
    standard_identifier = _extract_standard_identifier(text)
    organization = _standard_organization(text, standard_identifier)
    update_type = _standard_update_type(text)
    source_official = _is_official_source(candidate)
    date_obj = _candidate_date_obj(candidate.get("date", ""))
    has_rail = _contains_any(text, RAIL_RELEVANCE_TERMS)
    has_electromechanical = _contains_any(text, ELECTROMECHANICAL_RELEVANCE_TERMS)
    draft_signal = _contains_any(text, DRAFT_OR_PROPOSAL_TERMS)
    formal_release = _contains_any(text, FORMAL_RELEASE_TERMS)
    marketing_signal = _contains_any(text, MARKETING_TERMS)
    failure_reasons: list[str] = []
    relevance_signals: list[str] = []

    if standard_identifier:
        relevance_signals.append("standard_identifier")
    else:
        failure_reasons.append("standard_identifier_missing")
    if organization:
        relevance_signals.append("standard_organization")
    if update_type:
        relevance_signals.append(update_type)
    else:
        failure_reasons.append("no_update_event")
    if has_rail:
        relevance_signals.append("railway_relevance")
    else:
        failure_reasons.append("non_rail_standard")
    if has_electromechanical:
        relevance_signals.append("electromechanical_scope")
    else:
        failure_reasons.append("no_rail_electromechanical_relevance")
    if date_obj is None:
        failure_reasons.append("date_missing")
    elif not start_date <= date_obj <= end_date:
        failure_reasons.append("date_out_of_period")
    else:
        relevance_signals.append("date_in_period")
    if not source_official:
        failure_reasons.append("official_source_missing")
    else:
        relevance_signals.append("official_source")
    if draft_signal and not formal_release:
        failure_reasons.append("draft_or_proposal")
    if marketing_signal:
        failure_reasons.append("marketing_content")

    candidate.update(
        {
            "standard_organization": organization,
            "standard_identifier": standard_identifier,
            "standard_update_type": update_type,
            "relevance_signals": list(dict.fromkeys(relevance_signals)),
            "source_official": source_official,
            "standards_update_gate_pass": not failure_reasons,
            "failure_reasons": list(dict.fromkeys(failure_reasons)),
            "change_details_available": False,
            "draft_or_proposal": draft_signal,
            "standard_event_key": "|".join(_standard_event_key({**candidate, "standard_organization": organization, "standard_identifier": standard_identifier, "standard_update_type": update_type})),
        }
    )
    return candidate


def _item_output(candidate: dict) -> dict:
    return {
        "organization": candidate.get("standard_organization", ""),
        "standard_organization": candidate.get("standard_organization", ""),
        "standard_identifier": candidate.get("standard_identifier", ""),
        "title": candidate.get("title", ""),
        "update_type": candidate.get("standard_update_type", ""),
        "standard_update_type": candidate.get("standard_update_type", ""),
        "publication_date": candidate.get("date", ""),
        "relevance_signals": candidate.get("relevance_signals", []),
        "relevance": "、".join(candidate.get("relevance_signals", [])),
        "source": candidate.get("source_display") or candidate.get("source", ""),
        "url": candidate.get("resolved_article_url") or candidate.get("source_href") or candidate.get("url", ""),
        "source_quality": "A" if candidate.get("source_official") else candidate.get("source_quality", "C"),
        "source_official": bool(candidate.get("source_official")),
        "gate_pass": bool(candidate.get("standards_update_gate_pass")),
        "standards_update_gate_pass": bool(candidate.get("standards_update_gate_pass")),
        "failure_reasons": candidate.get("failure_reasons", []),
        "change_details_available": bool(candidate.get("change_details_available")),
        "summary": _shorten(candidate.get("snippet") or candidate.get("title", ""), 280),
    }


def _sorted_candidates(candidates: list[dict]) -> list[dict]:
    return sorted(
        candidates,
        key=lambda candidate: (
            0 if candidate.get("standards_update_gate_pass") else 1,
            0 if candidate.get("source_official") else 1,
            -_date_sort_key(candidate),
            candidate.get("standard_identifier", ""),
            candidate.get("title", ""),
            candidate.get("url", ""),
        ),
    )


def _build_markdown(result: dict) -> str:
    lines = [
        "# 捷運機電規範更新月報",
        "",
        f"> 監測期間：{result['period']['start_date']} ～ {result['period']['end_date']}",
        "",
        "## 規範更新",
        "",
    ]
    if not result["items"]:
        lines.append("本期未發現符合條件之捷運機電規範更新。")
    else:
        for item in result["items"]:
            lines.extend(
                [
                    f"### {item['standard_identifier']}｜{item['title']}",
                    "",
                    f"- 標準組織：{item['organization']}",
                    f"- 更新類型：{item['update_type']}",
                    f"- 日期：{item['publication_date']}",
                    f"- 與捷運機電的關聯：{item['relevance']}",
                    f"- 來源：{item['source']}",
                    f"- 原始連結：{item['url']}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _build_json(result: dict) -> str:
    payload = {
        "period": result["period"],
        "query_family": STANDARDS_UPDATE_QUERY_FAMILY,
        "query_count": result["query_count"],
        "raw_count": result["raw_count"],
        "normalized_count": result["normalized_count"],
        "eligible_count": result["eligible_count"],
        "rejected_count": result["rejected_count"],
        "items": result["items"],
        "rejected_items": result["rejected_items"],
        "queries": result["queries"],
        "dedupe_stats": result["dedupe_stats"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def run_standards_monitor(
    *,
    as_of_date: datetime.date | None = None,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
    ddgs_client_factory: Callable[[], object] | None = None,
    status_callback: Callable[[str], None] | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> dict:
    start, end = _resolve_period(
        as_of_date=as_of_date,
        start_date=start_date,
        end_date=end_date,
    )
    lookback_days = (end - start).days + 1
    queries, query_metadata = build_standards_update_queries()
    context = DdgsSearchContext(
        selected_types=[STANDARDS_SENTINEL_TYPE],
        active_regions=[],
        lookback_days=lookback_days,
        lookback_int=lookback_days,
        is_global_scope=True,
        today=end,
        ddgs_client_factory=_resolve_ddgs_factory(ddgs_client_factory),
        query_metadata=query_metadata,
        status_callback=status_callback,
        progress_callback=progress_callback,
        sleep=lambda _seconds: None,
        random_uniform=lambda _start, _end: 0.0,
    )
    raw_text, statuses, search_summary = run_duckduckgo_searches(
        context=context,
        search_queries=queries,
        news_query_indices=set(range(1, len(queries) + 1)),
    )
    candidates = parse_ddg_candidates(raw_text, _build_candidate_factory(query_metadata))
    evaluated = [_evaluate_candidate(candidate, start, end) for candidate in candidates]
    deduped, dedupe_stats = _dedupe_standard_events(evaluated)
    ordered = _sorted_candidates(deduped)
    eligible = [_item_output(candidate) for candidate in ordered if candidate.get("standards_update_gate_pass")]
    rejected = [_item_output(candidate) for candidate in ordered if not candidate.get("standards_update_gate_pass")]
    period = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "as_of_date": _resolve_as_of_date(as_of_date).isoformat(),
    }
    result = {
        "period": period,
        "query_family": STANDARDS_UPDATE_QUERY_FAMILY,
        "query_count": len(queries),
        "queries": list(queries),
        "raw_count": int(search_summary.get("DDGS_added_to_raw_count", 0) or 0),
        "normalized_count": len(candidates),
        "date_valid_count": sum(
            1
            for candidate in candidates
            if start <= (_candidate_date_obj(candidate.get("date", "")) or datetime.date.min) <= end
        ),
        "eligible_count": len(eligible),
        "rejected_count": len(rejected),
        "items": eligible,
        "rejected_items": rejected,
        "dedupe_stats": dedupe_stats,
        "search_statuses": statuses,
        "search_summary": search_summary,
    }
    result["markdown"] = _build_markdown(result)
    result["json"] = _build_json(result)
    return result


def write_standards_outputs(result: dict, output_dir: str | Path = "output") -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    month_label = result["period"]["start_date"][:7].replace("-", "")
    markdown_path = output_path / f"{DEFAULT_OUTPUT_PREFIX}_{month_label}.md"
    json_path = output_path / f"{DEFAULT_OUTPUT_PREFIX}_{month_label}.json"
    markdown_path.write_text(result["markdown"], encoding="utf-8")
    json_path.write_text(result["json"], encoding="utf-8")
    return {"markdown": markdown_path, "json": json_path}
