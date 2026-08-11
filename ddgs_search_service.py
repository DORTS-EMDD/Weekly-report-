"""DDGS query planning, execution, and diagnostics without Streamlit dependencies."""

import concurrent.futures
import datetime
import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

import requests

from article_processor import (
    _candidate_date_obj,
    _contains_taiwan_reference,
    _host_matches,
    _is_blocked_host,
    _is_domestic_taiwan_host,
)
from config import (
    ADVANCED_TYPES,
    DDGS_GLOBAL_QUERY_LIMIT,
    DDGS_QUERY_CHAR_LIMIT,
    DDGS_REGIONAL_QUERY_LIMIT,
    DDGS_RESULTS_PER_QUERY,
    DEFAULT_NEWS_SCOPE,
    LOW_VALUE_EXCLUDED_HOSTS,
    PORTAL_SOCIAL_LOW_VALUE_DOMAINS,
    REGION_SEARCH_TERMS,
    STANDARDS_WATCHLIST,
)
from search_queries import (
    DOMESTIC_METRO_QUERY_SPECS,
    FORWARD_TECHNOLOGY_QUERY_SPECS,
    QUERY_FAMILY_BY_TYPE_INDEX,
    REGION_QUERY_LANGUAGES,
    SEARCH_LANGUAGE_MARKERS,
    SEARCH_QUERY_SPECS,
)
from search_service import (
    compact_query as service_compact_query,
    ddgs_timelimit_for_lookback as _ddgs_timelimit_for_lookback,
    execute_ddgs_query as service_execute_ddgs_query,
)


@dataclass
class DdgsSearchContext:
    selected_types: list[str]
    active_regions: list[str]
    lookback_days: int
    lookback_int: int
    is_global_scope: bool
    today: datetime.date
    ddgs_client_factory: Callable[[], object] | None
    query_metadata: dict[str, dict] = field(default_factory=dict)
    progress_callback: Callable[[float], None] | None = None
    status_callback: Callable[[str], None] | None = None
    perf_counter: Callable[[], float] = time.perf_counter
    sleep: Callable[[float], None] = time.sleep
    random_uniform: Callable[[float, float], float] = random.uniform
    news_scope: str = DEFAULT_NEWS_SCOPE


DDGS_ERROR_STATUSES = {"http_403", "rate_limited_429", "timeout", "other_exception"}


def _search_language_from_query(
    query: str,
    *,
    query_metadata: dict[str, dict] | None = None,
) -> str:
    metadata = (query_metadata or {}).get(query or "", {}) or {}
    if metadata.get("lang"):
        return metadata["lang"]
    q = query or ""
    q_lower = q.casefold()
    if any(marker in q for marker in ("метро", "трамвай", "фуникулер", "забастовка")):
        return "ru"
    if any(marker in q_lower for marker in ("eletrico", "elétrico", "greve", "investigacao", "investigação", "sinalizacao", "sinalização", "descarrilamento")):
        return "pt"
    if any(marker in q_lower for marker in ("sciopero", "funicolare", "segnalamento", "deragliamento", "collisione")):
        return "it"
    for language, markers in SEARCH_LANGUAGE_MARKERS:
        if any(marker.casefold() in q_lower for marker in markers):
            return language
    return "en"


def _search_family_from_query(
    query: str,
    *,
    query_metadata: dict[str, dict] | None = None,
) -> str:
    metadata = (query_metadata or {}).get(query or "", {}) or {}
    if metadata.get("family"):
        return metadata["family"]
    q = (query or "").casefold()
    if any(term in q for term in ("deragliamento", "descarrilamento", "colisao", "colisão", "collisione", "incendio", "incêndio", "расследование", "сход с рельсов", "столкновение")):
        return "major_accident"
    if any(term in q for term in ("sciopero", "greve", "забастовка", "procurement dispute", "contract dispute", "cost overrun", "arbitration")):
        return "dispute"
    if any(term in q for term in ("apertura linea", "abertura linha", "fare reform", "operating hours", "capacity increase", "service change")):
        return "policy"
    if any(standard.casefold() in q for standards in STANDARDS_WATCHLIST.values() for standard in standards):
        return "standards_update"
    if any(domain in q for domain in ("ntsb.gov", "tsb.gc.ca", "atsb.gov.au", "bea-tt.developpement-durable.gouv.fr", "gov.uk/raib")):
        return "official_investigation"
    if any(term in q for term in (
        "derailment", "collision", "evacuation", "fatal", "killed", "injured",
        "entgleisung", "déraillement", "descarrilamiento", "сход", "脱線",
        "탈선", "脫軌", "脱轨",
    )):
        return "major_accident"
    if any(term in q for term in ("strike", "union dispute", "lawsuit", "procurement dispute", "contract dispute", "cost overrun", "arbitration", "罷工")):
        return "dispute"
    if any(term in q for term in ("line opening", "service restructuring", "fare reform", "operating hours", "capacity increase", "system renewal")):
        return "policy"
    if any(term in q for term in (
        "contactless payment", "rolling stock", "signalling", "signaling", "cbtc",
        "life-cycle management", "fire protection", "track renewal", "biometric",
        "modernisierung", "modernisation", "modernización", "modernização",
    )):
        return "technology"
    if "google news" in q or "site:" in q:
        return "official_site_or_rss"
    return "general"


def _compact_query(query: str, limit: int = DDGS_QUERY_CHAR_LIMIT) -> str:
    return service_compact_query(query, limit)


def _query_with_period(query: str, *, context: DdgsSearchContext) -> str:
    q = query.strip()
    if context.lookback_int > 31:
        q = f"{q} {context.today:%Y}"
    return _compact_query(q)


def _active_query_specs(family: str) -> list[dict]:
    specs = [spec for spec in SEARCH_QUERY_SPECS if spec.get("family") == family]
    if family == "domestic_metro":
        specs.extend(DOMESTIC_METRO_QUERY_SPECS)
    if family == "forward_technology":
        specs.extend(FORWARD_TECHNOLOGY_QUERY_SPECS)
    return specs


def _selected_query_families(*, context: DdgsSearchContext) -> list[str]:
    families: list[str] = []
    for type_index, family in QUERY_FAMILY_BY_TYPE_INDEX.items():
        if type_index < len(ADVANCED_TYPES) and ADVANCED_TYPES[type_index] in context.selected_types:
            families.append(family)
    if "major_accident" in families:
        families.append("official_investigation")
    return families


def _query_metadata_for(query: str, *, context: DdgsSearchContext) -> dict:
    metadata = context.query_metadata.get(query or "", {}) or {}
    if metadata:
        return metadata
    return {
        "family": _search_family_from_query(query, query_metadata=context.query_metadata),
        "lang": _search_language_from_query(query, query_metadata=context.query_metadata),
        "query_region": "unplanned",
        "use_news": True,
        "timelimit": _ddgs_timelimit_for_lookback(context.lookback_int),
        "requested_max_results": DDGS_RESULTS_PER_QUERY,
    }


def _regional_query_spec_sequence(families: list[str], preferred_lang: str) -> list[dict]:
    selected_specs: list[dict] = []
    selected_ids: set[int] = set()

    for family in families:
        family_specs = _active_query_specs(family)
        preferred = next((spec for spec in family_specs if spec.get("lang") == preferred_lang), None)
        fallback = next((spec for spec in family_specs if spec.get("lang") == "en"), None)
        chosen = preferred or fallback or (family_specs[0] if family_specs else None)
        if chosen:
            selected_specs.append(chosen)
            selected_ids.add(id(chosen))

    for language in (preferred_lang, "en"):
        for family in families:
            for spec in _active_query_specs(family):
                if id(spec) in selected_ids or spec.get("lang") != language:
                    continue
                selected_specs.append(spec)
                selected_ids.add(id(spec))

    for family in families:
        for spec in _active_query_specs(family):
            if id(spec) not in selected_ids:
                selected_specs.append(spec)
                selected_ids.add(id(spec))
    return selected_specs


def _standard_search_queries():
    for standards in STANDARDS_WATCHLIST.values():
        for standard in standards:
            yield f'"{standard}" revision amendment published draft metro rail standard'


def build_search_queries(
    *,
    context: DdgsSearchContext,
    include_forward_technology: bool = False,
) -> tuple[list[str], set[int]]:
    context.query_metadata.clear()
    queries: list[str] = []
    news_indices: set[int] = set()
    seen_queries: set[str] = set()
    query_limit = DDGS_GLOBAL_QUERY_LIMIT if context.is_global_scope else DDGS_REGIONAL_QUERY_LIMIT
    timelimit = _ddgs_timelimit_for_lookback(context.lookback_int)

    def _add(
        query: str,
        family: str,
        lang: str = "en",
        use_news: bool = True,
        query_region: str = "global",
        domestic_topic: str = "",
    ) -> bool:
        if len(queries) >= query_limit:
            return False
        final_query = _query_with_period(query, context=context)
        if not final_query or final_query in seen_queries:
            return False
        seen_queries.add(final_query)
        queries.append(final_query)
        context.query_metadata[final_query] = {
            "family": family,
            "lang": lang,
            "query_region": query_region,
            "use_news": use_news,
            "timelimit": timelimit,
            "requested_max_results": DDGS_RESULTS_PER_QUERY,
            "planned_index": len(queries),
        }
        if domestic_topic:
            context.query_metadata[final_query]["domestic_topic"] = domestic_topic
        if use_news:
            news_indices.add(len(queries))
        return True

    selected_families = _selected_query_families(context=context)
    include_official = "official_investigation" in selected_families
    content_families = [family for family in selected_families if family != "official_investigation"]
    if include_forward_technology:
        content_families.insert(0, "forward_technology")

    if context.news_scope in {"domestic", "both"}:
        selected_type_set = set(context.selected_types)
        for spec in DOMESTIC_METRO_QUERY_SPECS:
            if selected_type_set.intersection(spec.get("types", ())):
                _add(
                    spec.get("query", ""),
                    family="domestic_metro",
                    lang=spec.get("lang", "zh"),
                    use_news=bool(spec.get("use_news", True)),
                    query_region="domestic",
                    domestic_topic=spec.get("domestic_topic", ""),
                )

    if context.news_scope != "domestic" and context.is_global_scope:
        for family in content_families:
            for spec in _active_query_specs(family):
                _add(
                    spec.get("query", ""),
                    family=spec.get("family", family),
                    lang=spec.get("lang", "en"),
                    use_news=bool(spec.get("use_news", True)),
                )
    elif context.news_scope != "domestic" and content_families and context.active_regions:
        regions = list(dict.fromkeys(context.active_regions))
        official_reserve = 1 if include_official else 0
        country_budget = max(0, query_limit - official_reserve)
        max_per_country = min(4, max(2, len(content_families)))
        allocations = {region: min(2, country_budget // max(1, len(regions))) for region in regions}
        remaining = country_budget - sum(allocations.values())
        while remaining > 0 and any(count < max_per_country for count in allocations.values()):
            for region in regions:
                if remaining <= 0:
                    break
                if allocations[region] < max_per_country:
                    allocations[region] += 1
                    remaining -= 1

        for region in regions:
            preferred_lang = REGION_QUERY_LANGUAGES.get(region, "en")
            specs = _regional_query_spec_sequence(content_families, preferred_lang)
            prefix = REGION_SEARCH_TERMS.get(region, region)
            for spec in specs[:allocations[region]]:
                _add(
                    f"{prefix} {spec.get('query', '')}",
                    family=spec.get("family", "general"),
                    lang=spec.get("lang", preferred_lang),
                    use_news=bool(spec.get("use_news", True)),
                    query_region=region,
                )

    if context.news_scope != "domestic" and include_official:
        official_spec = next(iter(_active_query_specs("official_investigation")), None)
        if official_spec:
            _add(
                official_spec.get("query", ""),
                family="official_investigation",
                lang=official_spec.get("lang", "en"),
                use_news=bool(official_spec.get("use_news", False)),
                query_region="global",
            )

    if context.news_scope != "domestic" and len(ADVANCED_TYPES) > 4 and ADVANCED_TYPES[4] in context.selected_types:
        for query in _standard_search_queries():
            if not _add(query, family="standards_update", lang="en", use_news=True):
                break
    return queries, news_indices


def _format_ddg_block(i: int, backend: str, query: str, items: list[dict], status: str) -> str:
    if not items:
        return f"【搜尋 {i}（{backend}）】{query}\n  {status}"
    lines = [f"【搜尋 {i}（{backend}）】{query}（有效候選 {len(items)} 篇）"]
    for item in items:
        lines.append(
            f"  日期：{item['date']}\n"
            f"  標題：{item['title']}\n"
            f"  摘要：{item['summary']}\n"
            f"  連結：{item['link']}"
        )
    return "\n".join(lines)


def _search_result_date_hint(date_text: str, fallback_text: str = "") -> str:
    if _candidate_date_obj(date_text):
        return date_text
    match = re.search(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", fallback_text or "")
    if match:
        return match.group(0)
    match = re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2}\b", fallback_text or "", flags=re.IGNORECASE)
    if match:
        return match.group(0)
    match = re.search(r"\b20\d{2}\b", fallback_text or "")
    return match.group(0) if match else date_text


def _ddgs_query_status_template(
    query: str,
    news_timelimit: str,
    *,
    context: DdgsSearchContext,
) -> dict:
    metadata = _query_metadata_for(query, context=context) or {}
    family = metadata.get("family", "general")
    language = metadata.get("lang", "en")
    requested = int(metadata.get("requested_max_results", DDGS_RESULTS_PER_QUERY) or DDGS_RESULTS_PER_QUERY)
    return {
        "search_family": family,
        "search_language": language,
        "query": query,
        "query_region": metadata.get("query_region", "unplanned"),
        "use_news": bool(metadata.get("use_news", True)),
        "timelimit": metadata.get("timelimit") or news_timelimit,
        "requested_max_results": requested,
        "returned_count": 0,
        "valid_url_count": 0,
        "date_valid_count": 0,
        "basic_excluded_count": 0,
        "added_to_raw_count": 0,
        "excluded_counts_by_reason": {},
        "backend": "",
        "execution_status": "not_executed",
        "error_message": "",
        "elapsed_seconds": 0.0,
        "planned_index": int(metadata.get("planned_index", 0) or 0),
        # Backward-compatible aliases retained for existing developer tooling.
        "family": family,
        "lang": language,
        "requested": requested,
    }


def ddgs_queries_by_outcome(statuses: list[dict], outcome: str) -> list[dict]:
    rows = statuses or []
    if outcome == "no_backend_result":
        return [row for row in rows if row.get("execution_status") == "zero_results"]
    if outcome == "all_results_basic_excluded":
        return [row for row in rows if row.get("execution_status") == "all_results_basic_excluded"]
    if outcome == "query_error":
        return [row for row in rows if row.get("execution_status") in DDGS_ERROR_STATUSES]
    if outcome == "added_zero":
        return [row for row in rows if int(row.get("added_to_raw_count", 0) or 0) == 0]
    if outcome == "success_with_raw":
        return [row for row in rows if int(row.get("added_to_raw_count", 0) or 0) > 0]
    return []


def ddgs_general_only_queries(statuses: list[dict]) -> list[dict]:
    return [
        row for row in statuses or []
        if (row.get("search_family") or row.get("family") or "general") == "general"
    ]


def _ddgs_exception_status(exc: Exception) -> str:
    message = str(exc).casefold()
    if "no results found" in message or "no result found" in message:
        return "zero_results"
    if "429" in message or "ratelimit" in message or "rate limit" in message:
        return "rate_limited_429"
    if "403" in message or "forbidden" in message:
        return "http_403"
    if isinstance(exc, (TimeoutError, requests.Timeout)) or "timeout" in message or "timed out" in message:
        return "timeout"
    return "other_exception"


def _basic_search_url_exclusion_reason(
    title: str,
    href: str,
    candidate_text: str,
    *,
    news_scope: str = DEFAULT_NEWS_SCOPE,
) -> str:
    if not title:
        return "empty_title"
    if not href:
        return "empty_url"
    try:
        parsed = urlparse(href)
    except Exception:
        return "unparseable_result"
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "invalid_url"
    host = parsed.netloc.lower().removeprefix("www.")
    if _is_blocked_host(host) or any(
        _host_matches(host, domain)
        for domain in LOW_VALUE_EXCLUDED_HOSTS | PORTAL_SOCIAL_LOW_VALUE_DOMAINS
    ):
        return "blocked_or_low_value_domain"
    if news_scope == "international" and (_is_domestic_taiwan_host(host) or _contains_taiwan_reference(candidate_text)):
        return "taiwan_news"
    return ""


def _basic_search_date_exclusion_reason(
    date_text: str,
    *,
    context: DdgsSearchContext,
) -> str:
    date_obj = _candidate_date_obj(date_text)
    if not date_obj:
        return ""
    cutoff_date = context.today - datetime.timedelta(days=max(1, min(int(context.lookback_days), 365)) + 3)
    if date_obj < cutoff_date or date_obj > context.today + datetime.timedelta(days=1):
        return "date_out_of_range"
    return ""


def build_ddgs_search_summary(statuses: list[dict], planned_query_count: int | None = None) -> dict:
    rows = statuses or []

    def _count_by(key: str, fallback_key: str = "") -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            value = row.get(key) or (row.get(fallback_key) if fallback_key else "") or "unassigned"
            counts[str(value)] = counts.get(str(value), 0) + 1
        return counts

    return {
        "planned_query_count": int(planned_query_count if planned_query_count is not None else len(rows)),
        "executed_query_count": sum(1 for row in rows if row.get("execution_status") not in {"not_executed", "not_executed_dependency_missing"}),
        "query_count_by_region": _count_by("query_region"),
        "query_count_by_family": _count_by("search_family", "family"),
        "query_count_by_language": _count_by("search_language", "lang"),
        "no_backend_result_count": len(ddgs_queries_by_outcome(rows, "no_backend_result")),
        "all_results_basic_excluded_count": len(ddgs_queries_by_outcome(rows, "all_results_basic_excluded")),
        "query_error_count": len(ddgs_queries_by_outcome(rows, "query_error")),
        "added_zero_count": len(ddgs_queries_by_outcome(rows, "added_zero")),
        "success_with_raw_count": len(ddgs_queries_by_outcome(rows, "success_with_raw")),
        "rate_limited_query_count": sum(1 for row in rows if row.get("execution_status") in {"http_403", "rate_limited_429"}),
        "DDGS_added_to_raw_count": sum(int(row.get("added_to_raw_count", 0) or 0) for row in rows),
        "outcome_definitions": {
            "no_backend_result_count": "execution_status=zero_results",
            "all_results_basic_excluded_count": "backend returned results but every result failed basic exclusions",
            "query_error_count": "403, 429, timeout, or other exception",
            "added_zero_count": "added_to_raw_count=0 across all planned queries",
            "success_with_raw_count": "added_to_raw_count>0",
        },
    }


def _run_single_query(
    i: int,
    query: str,
    use_news: bool,
    news_timelimit: str,
    *,
    context: DdgsSearchContext,
) -> tuple[int, str, str, list[dict], str, dict]:
    started = context.perf_counter()
    status_row = _ddgs_query_status_template(query, news_timelimit, context=context)
    context.sleep(context.random_uniform(0.1, 0.4))
    result_items: list[dict] = []
    final_backend = ""
    last_exception: Exception | None = None
    errors: list[str] = []
    received_response = False
    zero_result_response = False

    for backend in ["auto", "bing"]:
        final_backend = backend
        for attempt in range(1, 3):
            try:
                result_list = service_execute_ddgs_query(
                    context.ddgs_client_factory,
                    query,
                    use_news=use_news,
                    max_results=status_row["requested_max_results"],
                    timelimit=status_row["timelimit"],
                    backend=backend,
                )
                received_response = True
                status_row["returned_count"] = len(result_list)
                if not result_list:
                    break
                for result in result_list:
                    if not isinstance(result, dict):
                        reason = "unparseable_result"
                        status_row["excluded_counts_by_reason"][reason] = status_row["excluded_counts_by_reason"].get(reason, 0) + 1
                        continue
                    body = (result.get("body") or result.get("excerpt") or result.get("description") or "")[:350]
                    href = result.get("href") or result.get("url") or ""
                    title = (result.get("title") or "").strip()
                    item_date = _search_result_date_hint(
                        result.get("date") or result.get("published") or "",
                        f"{title} {body}",
                    )
                    candidate_text = f"{title} {body} {href} {item_date}"
                    reason = _basic_search_url_exclusion_reason(
                        title,
                        href,
                        candidate_text,
                        news_scope=context.news_scope,
                    )
                    if reason:
                        status_row["excluded_counts_by_reason"][reason] = status_row["excluded_counts_by_reason"].get(reason, 0) + 1
                        continue
                    status_row["valid_url_count"] += 1
                    date_reason = _basic_search_date_exclusion_reason(item_date, context=context)
                    if date_reason:
                        status_row["excluded_counts_by_reason"][date_reason] = status_row["excluded_counts_by_reason"].get(date_reason, 0) + 1
                        continue
                    if _candidate_date_obj(item_date):
                        status_row["date_valid_count"] += 1
                    result_items.append({
                        "title": title,
                        "summary": body,
                        "link": href,
                        "date": item_date or "日期未知",
                    })
                break
            except Exception as exc:
                exception_status = _ddgs_exception_status(exc)
                if exception_status == "zero_results":
                    received_response = True
                    zero_result_response = True
                    last_exception = None
                    break
                last_exception = exc
                errors.append(f"{backend} attempt {attempt}: {str(exc)[:220]}")
                wait = attempt * 0.8 + context.random_uniform(0.2, 0.9)
                context.sleep(wait)
                if exception_status not in {"http_403", "rate_limited_429"}:
                    break

        if status_row["returned_count"] > 0 or zero_result_response:
            break

    status_row["basic_excluded_count"] = sum(status_row["excluded_counts_by_reason"].values())
    status_row["added_to_raw_count"] = len(result_items)
    status_row["backend"] = final_backend
    if status_row["returned_count"] > 0 and result_items:
        execution_status = "success"
    elif status_row["returned_count"] > 0:
        execution_status = "all_results_basic_excluded"
    elif received_response:
        execution_status = "zero_results"
    elif last_exception is not None:
        execution_status = _ddgs_exception_status(last_exception)
    else:
        execution_status = "not_executed"
    status_row["execution_status"] = execution_status
    status_row["error_message"] = " | ".join(errors)[-600:]
    status_row["elapsed_seconds"] = round(context.perf_counter() - started, 2)
    return i, query, final_backend or "auto", result_items, execution_status, status_row


def run_duckduckgo_searches(
    *,
    context: DdgsSearchContext,
    search_queries: list[str] | None = None,
    news_query_indices: set[int] | None = None,
) -> tuple[str, list[dict], dict]:
    """Execute planned DDGS queries and return text plus developer diagnostics."""
    statuses: list[dict] = []
    if not context.selected_types:
        return "未勾選任何新聞類型，略過搜尋。", statuses, build_ddgs_search_summary([], 0)

    if search_queries is None or news_query_indices is None:
        search_queries, news_query_indices = build_search_queries(context=context)
    total = len(search_queries)
    news_timelimit = _ddgs_timelimit_for_lookback(int(context.lookback_days))
    if context.ddgs_client_factory is None:
        for query in search_queries:
            row = _ddgs_query_status_template(query, news_timelimit, context=context)
            row["execution_status"] = "not_executed_dependency_missing"
            row["error_message"] = "ddgs package is not installed"
            statuses.append(row)
        return (
            "ddgs 套件未安裝，略過 ddgs 搜尋；請確認 requirements.txt 已包含 ddgs。",
            statuses,
            build_ddgs_search_summary(statuses, total),
        )
    if not search_queries:
        return "沒有規劃 DDGS 查詢。", statuses, build_ddgs_search_summary([], 0)

    results_map: dict[int, str] = {}
    done_count = 0
    max_workers = max(1, min(6, total))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_single_query,
                i,
                query,
                i in news_query_indices,
                news_timelimit,
                context=context,
            ): i
            for i, query in enumerate(search_queries, 1)
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                i, query, backend, items, status, query_status = future.result()
            except Exception as exc:
                i = futures[future]
                query = search_queries[i - 1] if 0 < i <= len(search_queries) else ""
                backend = "auto"
                items = []
                status = _ddgs_exception_status(exc)
                query_status = _ddgs_query_status_template(query, news_timelimit, context=context)
                query_status["execution_status"] = status
                query_status["error_message"] = str(exc)[:300]
            statuses.append(query_status)
            results_map[i] = _format_ddg_block(i, backend, query, items, status)
            done_count += 1
            if context.status_callback:
                context.status_callback("正在蒐集國際捷運新聞")
            if context.progress_callback:
                context.progress_callback(done_count / total)

    statuses = sorted(
        statuses,
        key=lambda row: (int(row.get("planned_index", 0) or 0), str(row.get("query", ""))),
    )
    summary = build_ddgs_search_summary(statuses, total)
    return "\n\n".join(results_map[i] for i in sorted(results_map)), statuses, summary
