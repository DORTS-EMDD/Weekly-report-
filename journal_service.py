"""International journal candidate collection without Streamlit dependencies."""

import datetime
import difflib
import json
import re
import time
import urllib.parse
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Callable

from article_processor import (
    _candidate_date_obj,
    _clean_text,
    _contains_any_term,
    _dedupe_url,
    _domain_from_url,
    _host_matches,
    _normalize_title,
    _shorten,
)
from config import (
    JOURNAL_ALLOWED_SOURCE_DOMAINS,
    JOURNAL_ARTICLE_FETCH_LIMIT,
    JOURNAL_BROAD_DISCOVERY_QUERY_BUDGET,
    ACADEMIC_BROAD_DISCOVERY_TAXONOMY,
    JOURNAL_CORE_SYSTEM_TERMS,
    JOURNAL_EXCLUDE_TERMS,
    JOURNAL_EXPLORATORY_QUERIES,
    JOURNAL_INSIGHT_TERMS,
    JOURNAL_LOW_PRIORITY_TERMS,
    JOURNAL_MAX_RESULTS_PER_QUERY,
    JOURNAL_PRECISION_QUERIES,
    JOURNAL_RAIL_CONTEXT_TERMS,
    JOURNAL_SECONDARY_SYSTEM_TERMS,
    JOURNAL_SOURCE_PAGES,
    JOURNAL_SOURCE_QUERY_BUDGET,
    JOURNAL_SOURCE_QUERY_SPECS,
    JOURNAL_SYSTEM_TERMS,
)


@dataclass(frozen=True)
class JournalServiceContext:
    today: datetime.date
    research_supplement_lookback_days: int
    research_supplement_period_label: str
    include_research_supplement: bool
    ddgs_client_factory: Callable[[], object] | None
    http_session_factory: Callable[[], object]
    make_news_candidate: Callable[..., dict]
    is_urban_rail_candidate: Callable[..., bool]
    status_callback: Callable[[str], None] | None = None


JOURNAL_SOURCE_DOMAIN_HINTS = {
    "Springer": ("springer.com",),
    "ScienceDirect": ("sciencedirect.com", "elsevier.com"),
    "MDPI": ("mdpi.com",),
    "IEEE Xplore": ("ieee.org",),
    "Taylor & Francis": ("tandfonline.com",),
}

JOURNAL_PUBLISHER_DOMAIN_ALIASES = {
    "springer.com": ("springer.com", "link.springer.com"),
    "sciencedirect.com": ("sciencedirect.com", "elsevier.com"),
    "mdpi.com": ("mdpi.com",),
    "ieee.org": ("ieee.org", "ieeexplore.ieee.org"),
    "tandfonline.com": ("tandfonline.com", "taylorfrancis.com", "taylorandfrancis.com"),
    "doi.org": ("doi.org",),
}

JOURNAL_SOURCE_CANONICAL_DOMAINS = {
    "Springer": "springer.com",
    "ScienceDirect": "sciencedirect.com",
    "MDPI": "mdpi.com",
    "IEEE Xplore": "ieee.org",
    "Taylor & Francis": "tandfonline.com",
}

JOURNAL_METADATA_ROUTE_NAMES = (
    "Springer",
    "ScienceDirect",
    "MDPI",
    "IEEE Xplore",
    "Taylor & Francis",
    "Broad Academic",
    "Crossref rescue",
    "Generic Academic",
)


def build_broad_academic_queries(limit: int | None = None) -> list[str]:
    """Build a small generic academic discovery lane without fixture terms."""
    queries = [
        f'"{object_term}" "{technical_family}" {research_signal}'
        for object_term, technical_family, research_signal in ACADEMIC_BROAD_DISCOVERY_TAXONOMY
    ]
    budget = JOURNAL_BROAD_DISCOVERY_QUERY_BUDGET if limit is None else max(0, int(limit))
    return queries[:budget]


def _extract_doi(text: str) -> str:
    match = re.search(
        r"(?:https?://(?:dx\.)?doi\.org/|\bdoi\s*[:：]\s*)?"
        r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
        text or "",
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).rstrip(".,;)]}")


def _extract_pii(text: str) -> str:
    match = re.search(r"(?:/pii/|\bpii\s*[:=]\s*)([A-Z0-9]{8,})", text or "", flags=re.IGNORECASE)
    return match.group(1).upper() if match else ""


def _academic_domain(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "://" in text:
        text = _domain_from_url(text)
    else:
        text = text.split("/", 1)[0].split(":", 1)[0].removeprefix("www.")
    text = text.strip(".")
    for canonical, aliases in JOURNAL_PUBLISHER_DOMAIN_ALIASES.items():
        if any(_host_matches(text, alias) for alias in aliases):
            return canonical
    return text


def _academic_publisher_domain(url: str, metadata: dict | None = None) -> str:
    domain = _academic_domain(url)
    if domain != "doi.org":
        return domain
    publisher_text = " ".join(
        str((metadata or {}).get(key) or "")
        for key in ("publisher", "journal_name", "container-title")
    ).casefold()
    publisher_aliases = (
        ("springer.com", ("springer",)),
        ("sciencedirect.com", ("elsevier",)),
        ("mdpi.com", ("mdpi",)),
        ("ieee.org", ("ieee", "institute of electrical")),
        ("tandfonline.com", ("taylor", "francis", "routledge", "informa")),
    )
    for canonical, tokens in publisher_aliases:
        if any(token in publisher_text for token in tokens):
            return canonical
    return domain


def _journal_source_family_for_url(url: str) -> str:
    domain = _academic_domain(url)
    for source_name, canonical in JOURNAL_SOURCE_CANONICAL_DOMAINS.items():
        if domain == canonical:
            return source_name
    return ""


def _journal_source_label(source_name: str) -> str:
    value = str(source_name or "").casefold()
    if "springer" in value:
        return "Springer"
    if "sciencedirect" in value or "elsevier" in value:
        return "ScienceDirect"
    if "mdpi" in value:
        return "MDPI"
    if "ieee" in value:
        return "IEEE Xplore"
    if "taylor" in value or "tandfonline" in value:
        return "Taylor & Francis"
    if "broad_academic" in value or "broad academic" in value:
        return "Broad Academic"
    if value in {"precision_queries", "exploratory_queries", "generic_academic"}:
        return "Generic Academic"
    return str(source_name or "Generic Academic")


def _metadata_route_for_candidate(
    source_family: str = "",
    url: str = "",
    metadata: dict | None = None,
) -> str:
    publisher_route = _journal_source_family_for_url(url)
    if publisher_route:
        return publisher_route
    source_route = _journal_source_label(source_family)
    if source_route in JOURNAL_METADATA_ROUTE_NAMES and source_route != "Generic Academic":
        return source_route
    publisher_domain = _academic_publisher_domain(url, metadata)
    for source_name, canonical_domain in JOURNAL_SOURCE_CANONICAL_DOMAINS.items():
        if publisher_domain == canonical_domain:
            return source_name
    if source_route == "Broad Academic":
        return source_route
    if _extract_doi(url) or (metadata or {}).get("doi"):
        return "Crossref rescue"
    return "Generic Academic"


def _metadata_priority_for_result(result: dict, source_family: str = "") -> tuple[int, dict, str]:
    metadata = result.get("journal_metadata") if isinstance(result.get("journal_metadata"), dict) else {}
    title = _clean_text(result.get("title") or "")
    snippet = _clean_text(result.get("body") or result.get("excerpt") or result.get("description") or "")
    url = _journal_result_url(result)
    doi = _extract_doi(f"{url} {title} {snippet} {metadata.get('doi', '')}")
    pii = str(metadata.get("pii") or _extract_pii(f"{url} {title} {snippet}") or "")
    page_type = classify_academic_page_type(url, title, doi=doi, pii=pii)
    text = f"{title} {snippet} {url}"
    components = {
        "article_page": 40 if page_type == "ARTICLE_PAGE" else 0,
        "credible_identifier": 20 if doi else (18 if pii else 0),
        "urban_rail_context": 12 if _contains_any_term(text, JOURNAL_RAIL_CONTEXT_TERMS) else 0,
        "technical_context": 0,
        "specific_title": 0 if is_generic_academic_title(title) else 4,
        "complete_title": 0 if is_truncated_academic_title(title) else 3,
        "date_hint": 1 if _has_explicit_full_date(_discovery_date_hint(result, title, snippet)) else 0,
    }
    if _contains_any_term(text, JOURNAL_CORE_SYSTEM_TERMS):
        components["technical_context"] = 10
    elif _contains_any_term(text, JOURNAL_SECONDARY_SYSTEM_TERMS):
        components["technical_context"] = 7
    elif _contains_any_term(text, JOURNAL_INSIGHT_TERMS):
        components["technical_context"] = 5
    score = sum(components.values())
    route = _metadata_route_for_candidate(source_family, url, metadata)
    return score, components, route


def _prioritize_metadata_results(results: list[dict], source_family: str = "") -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    route_sequence: list[str] = []
    for index, result in enumerate(results or []):
        if not isinstance(result, dict):
            continue
        score, components, route = _metadata_priority_for_result(result, source_family)
        enriched = dict(result)
        enriched["_metadata_priority_score"] = score
        enriched["_metadata_priority_components"] = components
        enriched["_metadata_route"] = route
        enriched["_metadata_discovery_index"] = index
        grouped.setdefault(route, []).append(enriched)
        route_sequence.append(route)
    for route, items in grouped.items():
        items.sort(
            key=lambda item: (
                -int(item.get("_metadata_priority_score", 0) or 0),
                _normalize_title(item.get("title", "")),
                _dedupe_url(_journal_result_url(item)),
                int(item.get("_metadata_discovery_index", 0) or 0),
            )
        )
        for rank, item in enumerate(items, start=1):
            item["_metadata_route_rank_before"] = rank
    positions: dict[str, int] = {}
    prioritized: list[dict] = []
    for route in route_sequence:
        position = positions.get(route, 0)
        prioritized.append(grouped[route][position])
        positions[route] = position + 1
    return prioritized


def _new_metadata_route_metrics() -> dict:
    return {
        "query_count": 0,
        "raw_count": 0,
        "domain_match_count": 0,
        "metadata_eligible_count": 0,
        "metadata_attempted_count": 0,
        "metadata_resolved_count": 0,
        "urban_rail_pass_count": 0,
        "accepted_count": 0,
        "metadata_budget_skipped_count": 0,
        "metadata_failure_reason_counts": {},
    }


def _journal_result_url(result: dict) -> str:
    """Prefer a publisher/canonical URL over a search redirect when present."""
    values: list[str] = []
    for key in (
        "canonical_url", "final_url", "resolved_url", "original_url",
        "source_url", "href", "url", "link",
    ):
        value = str(result.get(key) or "").strip()
        if value and value not in values:
            values.append(value)
    for value in values:
        parsed = urllib.parse.urlparse(value)
        if parsed.netloc and _academic_domain(value) in JOURNAL_PUBLISHER_DOMAIN_ALIASES:
            return value
        if parsed.netloc and _academic_domain(value) == "doi.org":
            return value
        query = urllib.parse.parse_qs(parsed.query)
        for key in ("url", "q", "target", "redirect"):
            nested = query.get(key, [""])[0]
            if nested.startswith(("http://", "https://")):
                return nested
    return values[0] if values else ""


_ACADEMIC_TITLE_STOPWORDS = {
    "a", "an", "the", "and", "for", "of", "to", "in", "on", "with",
    "online", "system", "platform", "page",
}
_ACADEMIC_GENERIC_TITLE_TOKENS = {
    "ieee", "xplore", "sciencedirect", "springerlink", "mdpi", "taylor",
    "francis", "publications", "research", "home", "search", "journal",
    "journals", "article", "articles", "paper", "papers", "online", "homepage",
    "results", "landing",
}
_ACADEMIC_ARTICLE_PATH_MARKERS = (
    "/article/", "/articles/", "/science/article/", "/document/", "/doi/",
    "/full/", "/abstract/", "/abs/", "/view/", "/paper/", "/publication/",
)
_ACADEMIC_LANDING_PATH_MARKERS = (
    "/home", "/search", "/journals", "/journal", "/publications", "/issue",
    "/issues", "/authors", "/author", "/about",
)


def _academic_meaningful_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", str(text or "").casefold())
    return [token for token in tokens if token not in _ACADEMIC_TITLE_STOPWORDS and len(token) > 1]


def is_generic_academic_title(title: str) -> bool:
    tokens = _academic_meaningful_tokens(title)
    normalized = _normalize_title(title)
    if not tokens:
        return True
    if normalized in {
        "ieee xplore", "sciencedirect", "springerlink", "mdpi",
        "taylor francis online", "publications research", "journal homepage",
        "search results", "home", "search",
        "journal", "journals", "articles", "article",
    }:
        return True
    return len(tokens) <= 3 and set(tokens).issubset(_ACADEMIC_GENERIC_TITLE_TOKENS)


def is_truncated_academic_title(title: str) -> bool:
    return bool(re.search(r"(?:\.\.\.|…|﹍|︙)\s*$", str(title or "").strip()))


def classify_academic_page_type(
    url: str,
    title: str = "",
    *,
    doi: str = "",
    pii: str = "",
) -> str:
    parsed = urllib.parse.urlparse(str(url or ""))
    path = parsed.path.casefold()
    query = urllib.parse.parse_qs(parsed.query)
    if any(key in query for key in ("q", "query", "search")) or "/search" in path:
        return "SEARCH_RESULT"
    if any(marker in path for marker in ("/issue", "/issues")):
        return "ISSUE_PAGE"
    if "/journal" in path or "/journals" in path:
        return "JOURNAL_HOME"
    has_identifier = bool(_extract_doi(f"{url} {doi}") or pii)
    if any(marker in path for marker in _ACADEMIC_ARTICLE_PATH_MARKERS) or has_identifier:
        return "ARTICLE_PAGE"
    if any(marker in path for marker in _ACADEMIC_LANDING_PATH_MARKERS) or is_generic_academic_title(title):
        return "GENERIC_LANDING"
    return "UNKNOWN"


def _journal_source_domain_matches(url: str, source_family: str = "") -> bool:
    domain = _academic_domain(url)
    if not domain:
        return False
    source_name = _journal_source_label(source_family) if source_family else ""
    hints = JOURNAL_SOURCE_DOMAIN_HINTS.get(source_name)
    if hints:
        return domain in {
            _academic_domain(hint)
            for hint in hints
        }
    return domain in {
        _academic_domain(domain_hint)
        for domain_hint in JOURNAL_ALLOWED_SOURCE_DOMAINS
    }


def _journal_pipeline_counts() -> dict:
    return {
        "backend_raw_count": 0,
        "result_url_count": 0,
        "domain_match_count": 0,
        "metadata_attempted_count": 0,
        "metadata_resolved_count": 0,
        "metadata_rescued_count": 0,
        "metadata_eligible_count": 0,
        "article_page_count": 0,
        "metadata_false_match_rejected_count": 0,
        "metadata_budget_skipped_count": 0,
        "metadata_failure_reason_counts": {},
        "date_pass_count": 0,
        "urban_rail_pass_count": 0,
        "journal_score_pass_count": 0,
        "accepted_count": 0,
    }


def _journal_year(item: dict) -> str:
    for value in (item.get("date", ""), item.get("title", ""), item.get("snippet", "")):
        match = re.search(r"\b(20\d{2}|19\d{2})\b", value or "")
        if match:
            return match.group(1)
    return "年份未標示"


def _has_explicit_full_date(date_text: str) -> bool:
    text = date_text or ""
    if re.search(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}", text):
        return True
    try:
        parsedate_to_datetime(text)
        return bool(re.search(r"\b\d{1,2}\b.*\b(20\d{2}|19\d{2})\b", text))
    except Exception:
        return False


def _journal_priority(date_text: str, *, context: JournalServiceContext) -> tuple[int, str]:
    cutoff_date = context.today - datetime.timedelta(days=context.research_supplement_lookback_days)
    date_obj = _candidate_date_obj(date_text)
    has_full_date = _has_explicit_full_date(date_text)
    if has_full_date and date_obj and cutoff_date <= date_obj <= context.today + datetime.timedelta(days=1):
        return 0, f"明確日期且符合{context.research_supplement_period_label}研究補充期間"
    if has_full_date and date_obj:
        return 99, f"明確日期不在{context.research_supplement_period_label}研究補充期間"
    if date_obj and date_obj.year >= cutoff_date.year:
        return 1, "僅年份或日期不完整，降低優先度"
    return 2, "無明確發表日期，降低優先度"


def _parse_full_research_date(date_text: str) -> datetime.date | None:
    text = (date_text or "").strip()
    if not text or not _has_explicit_full_date(text):
        return None
    date_obj = _candidate_date_obj(text)
    return date_obj


def _research_date_info(
    result: dict,
    title: str,
    snippet: str,
    *,
    context: JournalServiceContext,
) -> dict:
    metadata = result.get("journal_metadata") if isinstance(result.get("journal_metadata"), dict) else {}
    authoritative_fields = (
        "published_date", "publication_date", "metadata_date_text",
        "citation_publication_date", "citation_online_date", "citation_date",
        "datePublished", "online_publication_date", "article:published_time",
        "prism.publicationDate", "dc.date", "date",
    )
    for key in authoritative_fields:
        value = metadata.get(key) or metadata.get(key.replace("_", ""))
        date_obj = _parse_full_research_date(str(value or ""))
        if not date_obj:
            continue
        cutoff_date = context.today - datetime.timedelta(days=context.research_supplement_lookback_days)
        return {
            "published_date": date_obj.isoformat(),
            "date_confidence": "high",
            "date_reason": str(metadata.get("date_reason") or f"{key} 提供完整日期"),
            "date_source": str(metadata.get("metadata_source") or "publisher_metadata"),
            "date_authoritative": True,
            "date_resolution_method": key,
            "metadata_source": str(metadata.get("metadata_source") or "publisher_metadata"),
            "metadata_fields_seen": list(metadata.get("metadata_fields_seen") or [key]),
            "discovery_date_hint": _discovery_date_hint(result, title, snippet),
            "is_within_research_period": cutoff_date <= date_obj <= context.today,
        }

    text = f"{title} {snippet}"
    year_only = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    return {
        "published_date": "",
        "date_confidence": "low",
        "date_reason": (
            "僅有搜尋結果日期提示，未取得 authoritative 發表日期"
            if _discovery_date_hint(result, title, snippet)
            else ("只有年份或未提供明確發表日期" if year_only else "未提供明確發表日期")
        ),
        "date_source": str(metadata.get("metadata_source") or result.get("metadata_source") or "search_result"),
        "date_authoritative": False,
        "date_resolution_method": "search_result_hint_only" if _discovery_date_hint(result, title, snippet) else "unresolved",
        "metadata_source": str(metadata.get("metadata_source") or result.get("metadata_source") or "search_result"),
        "metadata_fields_seen": list(metadata.get("metadata_fields_seen") or result.get("metadata_fields_seen") or []),
        "discovery_date_hint": _discovery_date_hint(result, title, snippet),
        "is_within_research_period": False,
    }


def _discovery_date_hint(result: dict, title: str, snippet: str) -> str:
    for key in ("publication_date", "online_publication_date", "article_date", "release_date", "published", "published_date", "date"):
        value = str(result.get(key) or "").strip()
        if value:
            return value
    text = f"{title} {snippet}"
    match = re.search(
        r"(?:published date|publication date|online publication date|article date|release date|發表日期|出版日期|發布日期)\s*[:：]\s*([^.;，。]+)",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _has_doi_text(text: str) -> bool:
    return re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text or "", flags=re.IGNORECASE) is not None


def _is_formal_journal_url_or_doi(url: str, text: str) -> bool:
    host = _domain_from_url(url)
    if _has_doi_text(f"{url} {text}"):
        return True
    if host and any(_host_matches(host, domain) for domain in JOURNAL_ALLOWED_SOURCE_DOMAINS):
        return True
    return False


def get_journal_target_count(days: int) -> tuple[int, int]:
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 90
    if days >= 365:
        return 6, 8
    if days >= 180:
        return 4, 4
    return 2, 2


def _journal_safe_get(
    url: str,
    timeout: int = 8,
    *,
    http_session_factory: Callable[[], object],
) -> str:
    if not url or not str(url).startswith(("http://", "https://")):
        return ""
    try:
        session = http_session_factory()
        response = session.get(url, timeout=timeout, headers={"Accept": "text/html,application/xhtml+xml,*/*"})
        if response.status_code >= 400:
            return ""
        return response.text or ""
    except Exception:
        return ""


def _html_unescape_clean(text: str) -> str:
    return _clean_text(unescape(re.sub(r"<[^>]+>", " ", text or "")))


def _meta_content_entries(html: str, names: list[str]) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for name in names:
        patterns = [
            rf'<meta[^>]+(?:name|property)=["\\\']{re.escape(name)}["\\\'][^>]+content=["\\\']([^"\\\']+)["\\\']',
            rf'<meta[^>]+content=["\\\']([^"\\\']+)["\\\'][^>]+(?:name|property)=["\\\']{re.escape(name)}["\\\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html or "", flags=re.IGNORECASE | re.DOTALL)
            if match:
                entries.append((name, _html_unescape_clean(match.group(1))))
                break
    return entries


def _first_meta_content(html: str, names: list[str]) -> str:
    entries = _meta_content_entries(html, names)
    return entries[0][1] if entries else ""


def _jsonld_values(html: str) -> dict:
    values: dict[str, str] = {}
    for block in re.findall(r'<script[^>]+type=["\\\']application/ld\+json["\\\'][^>]*>(.*?)</script>', html or "", flags=re.IGNORECASE | re.DOTALL):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop(0)
            if isinstance(item, dict):
                for key in ("datePublished", "dateCreated", "dateModified", "headline", "name", "description"):
                    if key in item and not values.get(key):
                        values[key] = str(item.get(key) or "")
                for value in item.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(item, list):
                stack.extend(item)
    return values


def fetch_journal_page_metadata(url: str, *, context: JournalServiceContext) -> dict:
    html = _journal_safe_get(url, http_session_factory=context.http_session_factory)
    if not html:
        return {
            "metadata_fetch_status": "failed",
            "metadata_source": "publisher_page",
            "metadata_fields_seen": [],
        }
    jsonld = _jsonld_values(html)
    metadata_entries = _meta_content_entries(
        html,
        [
            "citation_title", "dc.title", "og:title", "twitter:title",
            "citation_abstract", "description", "dc.description", "og:description", "twitter:description",
            "citation_publication_date", "citation_online_date", "citation_date", "dc.date",
            "prism.publicationDate", "article:published_time", "datePublished", "date", "DC.Date",
            "citation_doi", "dc.identifier", "prism.doi", "citation_pii", "prism.url",
            "citation_journal_title", "prism.publicationName", "dc.source", "og:site_name",
        ],
    )
    metadata_by_name = dict(metadata_entries)
    metadata_fields_seen = [name for name, _ in metadata_entries]
    title = (
        next((metadata_by_name[name] for name in ("citation_title", "dc.title", "og:title", "twitter:title") if metadata_by_name.get(name)), "")
        or _html_unescape_clean(jsonld.get("headline") or jsonld.get("name") or "")
    )
    abstract = (
        next((metadata_by_name[name] for name in ("citation_abstract", "description", "dc.description", "og:description", "twitter:description") if metadata_by_name.get(name)), "")
        or _html_unescape_clean(jsonld.get("description") or "")
    )
    date_metadata_name = next((name for name in (
            "citation_publication_date", "citation_online_date", "citation_date", "dc.date",
            "prism.publicationDate", "article:published_time", "datePublished", "date", "DC.Date",
        ) if metadata_by_name.get(name)), "")
    date_text = metadata_by_name.get(date_metadata_name) or jsonld.get("datePublished") or jsonld.get("dateCreated")
    doi = next((metadata_by_name[name] for name in ("citation_doi", "dc.identifier", "prism.doi") if metadata_by_name.get(name)), "")
    if not doi:
        doi = _extract_doi(html)
    doi = _extract_doi(doi) or doi
    pii = metadata_by_name.get("citation_pii") or _extract_pii(f"{url} {html}")
    journal_name = next((metadata_by_name[name] for name in ("citation_journal_title", "prism.publicationName", "dc.source", "og:site_name") if metadata_by_name.get(name)), "")
    published_date = ""
    date_confidence = "low"
    date_reason = "原始頁未解析到完整發表日期"
    date_obj = _parse_full_research_date(date_text or "")
    if date_obj:
        cutoff_date = context.today - datetime.timedelta(days=context.research_supplement_lookback_days)
        published_date = date_obj.isoformat()
        date_confidence = "high"
        date_reason = "原始文章頁 metadata 提供完整發表日期"
    metadata_fields_seen.extend(f"jsonld.{key}" for key in jsonld if jsonld.get(key))
    if date_metadata_name.startswith("citation_"):
        metadata_source = "publisher_citation_meta"
    elif date_metadata_name.startswith(("og:", "article:")):
        metadata_source = "publisher_opengraph"
    elif date_text and ("datePublished" in jsonld or "dateCreated" in jsonld):
        metadata_source = "publisher_jsonld"
    else:
        metadata_source = "publisher_page"
    return {
        "metadata_fetch_status": "success",
        "metadata_source": metadata_source,
        "metadata_fields_seen": metadata_fields_seen,
        "metadata_title": title,
        "metadata_abstract": abstract,
        "metadata_date_text": date_text or "",
        "published_date": published_date,
        "date_confidence": date_confidence,
        "date_reason": date_reason,
        "is_within_research_period": bool(published_date) and (
            context.today - datetime.timedelta(days=context.research_supplement_lookback_days)
            <= _candidate_date_obj(published_date)
            <= context.today
        ),
        "doi": doi,
        "pii": pii,
        "journal_name": journal_name,
    }


def fetch_doi_metadata(doi: str, *, context: JournalServiceContext) -> dict:
    normalized_doi = _extract_doi(doi)
    if not normalized_doi:
        return {"metadata_fetch_status": "not_attempted", "metadata_source": "doi_metadata", "metadata_fields_seen": []}
    endpoint = f"https://api.crossref.org/works/{urllib.parse.quote(normalized_doi, safe='')}"
    payload = _journal_safe_get(endpoint, timeout=8, http_session_factory=context.http_session_factory)
    if not payload:
        return {"metadata_fetch_status": "failed", "metadata_source": "doi_metadata", "metadata_fields_seen": []}
    try:
        message = json.loads(payload).get("message", {})
    except (TypeError, ValueError):
        return {"metadata_fetch_status": "failed", "metadata_source": "doi_metadata", "metadata_fields_seen": []}
    if not isinstance(message, dict):
        return {"metadata_fetch_status": "failed", "metadata_source": "doi_metadata", "metadata_fields_seen": []}
    fields_seen = [key for key in ("title", "container-title", "published-online", "published-print", "issued", "created", "DOI") if message.get(key)]
    date_text = ""
    for date_key in ("published-online", "published-print", "issued", "created"):
        parts = ((message.get(date_key) or {}).get("date-parts") or [])
        if parts and isinstance(parts[0], list) and len(parts[0]) >= 3:
            date_text = "-".join(str(int(value)).zfill(2) if index else str(int(value)) for index, value in enumerate(parts[0][:3]))
            break
    date_obj = _parse_full_research_date(date_text)
    published_date = date_obj.isoformat() if date_obj else ""
    return {
        "metadata_fetch_status": "success",
        "metadata_source": "doi_metadata",
        "metadata_fields_seen": fields_seen,
        "metadata_title": " ".join(str(value) for value in (message.get("title") or [])[:1]),
        "metadata_date_text": date_text,
        "published_date": published_date,
        "date_confidence": "high" if published_date else "low",
        "date_reason": "DOI metadata 提供完整發表日期" if published_date else "DOI metadata 僅提供年份或日期不完整",
        "is_within_research_period": bool(published_date) and (
            context.today - datetime.timedelta(days=context.research_supplement_lookback_days)
            <= date_obj
            <= context.today
        ),
        "doi": normalized_doi,
        "journal_name": " ".join(str(value) for value in (message.get("container-title") or [])[:1]),
    }


def _metadata_has_authoritative_date(metadata: dict) -> bool:
    return bool(
        metadata.get("date_confidence") == "high"
        and _parse_full_research_date(str(metadata.get("published_date") or ""))
    )


def _crossref_publisher_matches(
    publisher: str,
    publisher_domain: str,
    expected_publisher: str = "",
) -> bool:
    publisher_text = str(publisher or "").casefold()
    domain = _academic_domain(publisher_domain)
    if expected_publisher:
        expected_tokens = set(_academic_meaningful_tokens(expected_publisher))
        actual_tokens = set(_academic_meaningful_tokens(publisher_text))
        if expected_tokens and expected_tokens.intersection(actual_tokens):
            return True
    publisher_tokens = {
        "springer.com": ("springer",),
        "sciencedirect.com": ("elsevier",),
        "mdpi.com": ("mdpi",),
        "ieee.org": ("ieee", "institute of electrical"),
        "tandfonline.com": ("taylor", "francis", "routledge", "informa"),
    }.get(domain, ())
    return bool(publisher_text and publisher_tokens and any(token in publisher_text for token in publisher_tokens))


def fetch_scholarly_title_metadata(
    title: str,
    *,
    publisher_domain: str = "",
    publisher_name: str = "",
    discovery_date_hint: str = "",
    snippet: str = "",
    url: str = "",
    doi: str = "",
    pii: str = "",
    page_type: str = "",
    context: JournalServiceContext,
) -> dict:
    raw_title = str(title or "").strip()
    clean_title = _clean_text(raw_title)
    lookup_title = re.sub(r"(?:\.\.\.|…|﹍|︙)\s*$", "", clean_title).strip()
    resolved_page_type = page_type or classify_academic_page_type(url, raw_title, doi=doi, pii=pii)
    base = {
        "metadata_source": "scholarly_title_lookup",
        "page_type": resolved_page_type,
        "metadata_fields_seen": [],
        "metadata_lookup_candidate_title": lookup_title,
        "metadata_lookup_resolved_title": "",
        "metadata_title_prefix_match": False,
        "metadata_publisher_match": False,
        "metadata_year_match": False,
    }
    if url and resolved_page_type != "ARTICLE_PAGE" and not (doi or pii):
        return {
            **base,
            "metadata_fetch_status": "skipped",
            "metadata_lookup_skipped_reason": "generic_landing_page_title",
            "metadata_match_status": "generic_landing_page",
        }
    if is_generic_academic_title(raw_title):
        return {
            **base,
            "metadata_fetch_status": "skipped",
            "metadata_lookup_skipped_reason": "generic_landing_page_title",
            "metadata_match_status": "generic_landing_page",
        }
    clean_title = lookup_title
    if not clean_title or not publisher_domain:
        return {
            **base,
            "metadata_fetch_status": "not_attempted",
            "metadata_reject_reason": "缺少可用候選標題或出版者網域",
        }
    params = urllib.parse.urlencode({"query.bibliographic": clean_title, "rows": 5})
    endpoint = f"https://api.crossref.org/works?{params}"
    payload = _journal_safe_get(endpoint, timeout=8, http_session_factory=context.http_session_factory)
    if not payload:
        return {
            **base,
            "metadata_fetch_status": "failed",
            "metadata_reject_reason": "Crossref lookup 無回應",
        }
    try:
        items = json.loads(payload).get("message", {}).get("items", [])
    except (TypeError, ValueError):
        items = []
    if not isinstance(items, list):
        items = []
    normalized_title = _normalize_title(clean_title)
    hint_year_match = re.search(r"\b(20\d{2}|19\d{2})\b", str(discovery_date_hint or ""))
    hint_year = hint_year_match.group(1) if hint_year_match else ""
    truncated = is_truncated_academic_title(raw_title)
    prefix_tokens = _academic_meaningful_tokens(clean_title)
    snippet_tokens = set(_academic_meaningful_tokens(snippet))
    last_reject_reason = "找不到符合高信度條件的 scholarly metadata"
    for item in items:
        if not isinstance(item, dict):
            continue
        item_title = _clean_text(" ".join(str(value) for value in (item.get("title") or [])[:1]))
        item_normalized = _normalize_title(item_title)
        similarity = difflib.SequenceMatcher(None, normalized_title, item_normalized).ratio()
        prefix_match = bool(
            truncated
            and len(prefix_tokens) >= 4
            and item_normalized.startswith(normalized_title)
        )
        if not item_normalized or (item_normalized != normalized_title and not prefix_match and similarity < 0.93):
            last_reject_reason = "標題未達 exact/near-exact 或截斷前綴匹配"
            continue
        if is_generic_academic_title(item_title):
            last_reject_reason = "回傳標題為 generic landing/page title"
            continue
        item_type = str(item.get("type") or "").casefold()
        if item_type and item_type not in {"journal-article", "article", "proceedings-article", "posted-content"}:
            last_reject_reason = "Crossref item type 不是可接受學術文章"
            continue
        publisher_match = _crossref_publisher_matches(
            item.get("publisher", ""),
            publisher_domain,
            publisher_name,
        )
        if not publisher_match:
            last_reject_reason = "出版者與候選 publisher/domain 不一致"
            continue
        date_text = ""
        for date_key in ("published-online", "published-print", "issued", "created"):
            parts = ((item.get(date_key) or {}).get("date-parts") or [])
            if parts and isinstance(parts[0], list) and len(parts[0]) >= 3:
                date_text = "-".join(
                    str(int(value)).zfill(2) if index else str(int(value))
                    for index, value in enumerate(parts[0][:3])
                )
                break
        date_obj = _parse_full_research_date(date_text)
        if not date_obj:
            last_reject_reason = "Crossref 未提供完整 publication date"
            continue
        year_match = not hint_year or str(date_obj.year) == hint_year
        if not year_match:
            last_reject_reason = "publication year 與 discovery date hint 衝突"
            continue
        if truncated and (not snippet_tokens or len(snippet_tokens.intersection(set(_academic_meaningful_tokens(item_title)))) < 2):
            last_reject_reason = "截斷標題缺少足夠 snippet concept overlap"
            continue
        fields_seen = [key for key in ("title", "publisher", "container-title", "published-online", "published-print", "issued", "DOI") if item.get(key)]
        return {
            **base,
            "metadata_fetch_status": "success",
            "metadata_fields_seen": fields_seen,
            "metadata_title": item_title,
            "metadata_lookup_resolved_title": item_title,
            "metadata_title_prefix_match": prefix_match,
            "metadata_publisher_match": publisher_match,
            "metadata_year_match": year_match,
            "metadata_date_text": date_text,
            "published_date": date_obj.isoformat(),
            "date_confidence": "high",
            "date_reason": "Crossref title lookup 以標題、出版者與年份高信度匹配",
            "is_within_research_period": (
                context.today - datetime.timedelta(days=context.research_supplement_lookback_days)
                <= date_obj
                <= context.today
            ),
            "doi": _extract_doi(str(item.get("DOI") or "")),
            "journal_name": " ".join(str(value) for value in (item.get("container-title") or [])[:1]),
            "publisher": str(item.get("publisher") or ""),
            "metadata_match_similarity": round(similarity, 4),
        }
    return {
        **base,
        "metadata_fetch_status": "failed",
        "metadata_reject_reason": last_reject_reason,
        "metadata_match_status": "low_confidence",
    }


def resolve_journal_metadata(
    url: str,
    *,
    doi: str = "",
    pii: str = "",
    title: str = "",
    snippet: str = "",
    publisher_name: str = "",
    discovery_date_hint: str = "",
    page_type: str = "",
    context: JournalServiceContext,
) -> dict:
    resolved_page_type = page_type or classify_academic_page_type(url, title, doi=doi, pii=pii)
    page_metadata = fetch_journal_page_metadata(url, context=context)
    page_metadata.setdefault("page_type", resolved_page_type)
    attempt_methods = ["publisher_page"]
    if _metadata_has_authoritative_date(page_metadata):
        page_metadata["metadata_attempt_method"] = "publisher_page"
        return page_metadata
    doi_metadata = fetch_doi_metadata(doi or page_metadata.get("doi", ""), context=context)
    merged = dict(page_metadata)
    if doi_metadata.get("metadata_fetch_status") == "success":
        attempt_methods.append("doi_metadata")
        for key, value in doi_metadata.items():
            if value not in ("", [], None):
                merged[key] = value
        merged["metadata_source"] = "doi_metadata"
        merged["metadata_fields_seen"] = list(dict.fromkeys(
            list(merged.get("metadata_fields_seen") or [])
            + list(doi_metadata.get("metadata_fields_seen") or [])
        ))
        if _metadata_has_authoritative_date(merged):
            merged["metadata_attempt_method"] = " -> ".join(attempt_methods)
            return merged
    elif doi or page_metadata.get("doi"):
        attempt_methods.append("doi_metadata")
    title_metadata = fetch_scholarly_title_metadata(
        title,
        publisher_domain=_academic_publisher_domain(url, {**page_metadata, **doi_metadata}),
        publisher_name=publisher_name or str(page_metadata.get("publisher") or page_metadata.get("journal_name") or ""),
        discovery_date_hint=discovery_date_hint,
        snippet=snippet,
        url=url,
        doi=doi or page_metadata.get("doi", ""),
        pii=pii or page_metadata.get("pii", ""),
        page_type=resolved_page_type,
        context=context,
    )
    attempt_methods.append("scholarly_title_lookup")
    if title_metadata.get("metadata_fetch_status") == "success":
        for key, value in title_metadata.items():
            if value not in ("", [], None):
                merged[key] = value
        merged["metadata_source"] = "scholarly_title_lookup"
        merged["metadata_fields_seen"] = list(dict.fromkeys(
            list(merged.get("metadata_fields_seen") or [])
            + list(title_metadata.get("metadata_fields_seen") or [])
        ))
    else:
        if title_metadata.get("metadata_lookup_skipped_reason"):
            merged["metadata_lookup_skipped_reason"] = title_metadata["metadata_lookup_skipped_reason"]
            merged["metadata_match_status"] = title_metadata.get("metadata_match_status", "generic_landing_page")
            merged["metadata_fetch_status"] = "skipped"
        elif merged.get("metadata_fetch_status") != "success":
            merged["metadata_fetch_status"] = title_metadata.get("metadata_fetch_status", "failed")
            merged["metadata_source"] = title_metadata.get("metadata_source", "scholarly_title_lookup")
        if title_metadata.get("metadata_reject_reason"):
            merged["metadata_reject_reason"] = title_metadata["metadata_reject_reason"]
        for key in (
            "metadata_lookup_candidate_title", "metadata_lookup_resolved_title",
            "metadata_title_prefix_match", "metadata_publisher_match", "metadata_year_match",
        ):
            if key in title_metadata:
                merged[key] = title_metadata[key]
    if title_metadata.get("metadata_fetch_status") == "success":
        merged["metadata_attempt_method"] = " -> ".join(attempt_methods)
    else:
        merged["metadata_attempt_method"] = " -> ".join(attempt_methods)
    return merged


def _journal_source_page_results(*, context: JournalServiceContext) -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    statuses: list[dict] = []
    fetched = 0
    seen_links: set[str] = set()
    for source_name, page_url in JOURNAL_SOURCE_PAGES:
        source_started = time.perf_counter()
        if context.status_callback:
            context.status_callback("正在整理候選資料")
        html = _journal_safe_get(page_url, http_session_factory=context.http_session_factory)
        if not html:
            statuses.append({"query": source_name, "status": "來源頁讀取失敗", "count": 0, "accepted_count": 0, **_journal_pipeline_counts(), "url": page_url, "elapsed_seconds": round(time.perf_counter() - source_started, 3), "timing_stage": "source_page_fetch"})
            continue
        links = []
        for href in re.findall(r'href=["\\\']([^"\\\']*(?:/article/)[^"\\\']+)["\\\']', html, flags=re.IGNORECASE):
            if href.startswith("/"):
                href = urllib.parse.urljoin(page_url, href)
            if href.startswith("http") and href not in seen_links:
                seen_links.add(href)
                links.append(href)
            if len(links) >= JOURNAL_ARTICLE_FETCH_LIMIT:
                break
        source_pipeline_counts = _journal_pipeline_counts()
        source_pipeline_counts["backend_raw_count"] = len(links)
        source_pipeline_counts["result_url_count"] = len(links)
        source_pipeline_counts["domain_match_count"] = sum(
            1 for link in links if _journal_source_domain_matches(link, source_name)
        )
        for link in links:
            if fetched >= JOURNAL_ARTICLE_FETCH_LIMIT:
                break
            source_pipeline_counts["metadata_attempted_count"] += 1
            meta = resolve_journal_metadata(
                link,
                doi=_extract_doi(link),
                title="",
                context=context,
            )
            fetched += 1
            if _metadata_has_authoritative_date(meta):
                source_pipeline_counts["metadata_resolved_count"] += 1
            title = meta.get("metadata_title") or link.rsplit("/", 1)[-1]
            snippet = meta.get("metadata_abstract") or ""
            results.append({
                "title": title,
                "body": snippet,
                "href": link,
                "url": link,
                "date": meta.get("published_date") or meta.get("metadata_date_text") or "",
                "journal_metadata": meta,
                "source_page": source_name,
                "discovery_source": "publisher_source_page",
            })
        statuses.append({"query": source_name, "status": "成功" if links else "無文章連結", "count": len(links), "accepted_count": 0, **source_pipeline_counts, "url": page_url, "elapsed_seconds": round(time.perf_counter() - source_started, 3), "timing_stage": "source_page_fetch"})
    return results, statuses


def score_journal_candidate(candidate: dict) -> dict:
    text = f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('url', '')} {candidate.get('journal_name', '')} {candidate.get('doi', '')}"
    score = 0
    reasons: list[str] = []
    host = _academic_domain(candidate.get("publisher_domain") or candidate.get("url", ""))
    has_core_system = _contains_any_term(text, JOURNAL_CORE_SYSTEM_TERMS)
    has_secondary_system = _contains_any_term(text, JOURNAL_SECONDARY_SYSTEM_TERMS)
    has_low_priority_topic = _contains_any_term(text, JOURNAL_LOW_PRIORITY_TERMS)
    if candidate.get("doi") or (host and any(_host_matches(host, domain) for domain in JOURNAL_ALLOWED_SOURCE_DOMAINS)):
        score += 20
        reasons.append("正式期刊來源、DOI 或可信研究頁面 +20")
    if candidate.get("published_date") and candidate.get("is_within_research_period"):
        score += 20
        reasons.append("發表日期明確且符合期間 +20")
    if _contains_any_term(text, ["urban rail", "urban rail transit", "metro", "subway", "mrt", "light rail", "tram", "都市軌道", "捷運", "地鐵"]):
        score += 20
        reasons.append("都市軌道場景明確 +20")
    if _contains_any_term(text, JOURNAL_SYSTEM_TERMS):
        system_points = 25 if has_core_system else (10 if has_secondary_system else 0)
        if system_points:
            score += system_points
            reasons.append(f"機電/系統研究議題明確 +{system_points}")
    if _contains_any_term(text, JOURNAL_INSIGHT_TERMS):
        score += 15
        reasons.append("具規劃、維修、能源、安全或資料治理啟示 +15")
    if has_core_system:
        score += 25
        reasons.append("符合捷運機電核心研究範圍 +25")
    elif has_secondary_system:
        score += 10
        reasons.append("屬施工介面或監測等次要補充研究 +10")
    else:
        score -= 20
        reasons.append("未見明確捷運機電核心研究內容 -20")
    if has_low_priority_topic:
        score -= 35
        reasons.append("偏人力排班、旅客行為、純土建或一般營運研究 -35")
    if not has_core_system:
        score_cap = 50 if has_low_priority_topic else (70 if has_secondary_system else 55)
        if score > score_cap:
            score = score_cap
            reasons.append(f"非核心機電研究分數上限 {score_cap}")
    return {"journal_score": max(0, min(100, score)), "journal_score_reason": "；".join(reasons) or "未符合主要評分條件"}


def _journal_exclusion_stats(excluded: list[dict]) -> dict:
    stats: dict[str, int] = {}
    for item in excluded or []:
        reason = item.get("exclude_reason", "未分類") or "未分類"
        stats[reason] = stats.get(reason, 0) + 1
    return stats


def journal_query_source_outcomes(statuses: list[dict]) -> dict[str, dict]:
    outcomes: dict[str, dict] = {}
    domain_hints = {
        "IEEE Xplore": "ieeexplore.ieee.org",
        "ScienceDirect": "sciencedirect.com",
        "MDPI": "mdpi.com",
        "Taylor & Francis": "tandfonline.com",
        "Springer": "link.springer.com",
    }
    for row in statuses or []:
        source_name = str(row.get("source_family") or "").strip()
        if not source_name:
            query = str(row.get("query") or "")
            source_name = "source_pages" if row.get("timing_stage") == "source_page_fetch" else (
                "precision_queries" if query in JOURNAL_PRECISION_QUERIES else (
                    "exploratory_queries" if query in JOURNAL_EXPLORATORY_QUERIES else "other_queries"
                )
            )
        outcome = outcomes.setdefault(
            source_name,
            {
                "query_count": 0,
                "executed_query_count": 0,
                "backend_raw_count": 0,
                "result_url_count": 0,
                "domain_match_count": 0,
                "metadata_eligible_count": 0,
                "metadata_attempted_count": 0,
                "metadata_resolved_count": 0,
                "metadata_budget_skipped_count": 0,
                "metadata_failure_reason_counts": {},
                "urban_rail_pass_count": 0,
                "journal_score_pass_count": 0,
                "accepted_count": 0,
                "nonzero_result_query_count": 0,
                "failed_query_count": 0,
                "domains": [],
                "statuses": [],
            },
        )
        outcome["query_count"] += 1
        outcome["executed_query_count"] += 1
        accepted_count = int(row.get("accepted_count", row.get("count", 0)) or 0)
        for key in (
            "backend_raw_count", "result_url_count", "domain_match_count",
            "metadata_eligible_count", "metadata_attempted_count", "metadata_resolved_count",
            "metadata_budget_skipped_count",
            "urban_rail_pass_count", "journal_score_pass_count",
        ):
            outcome[key] += int(row.get(key, 0) or 0)
        for reason, count in (row.get("metadata_failure_reason_counts") or {}).items():
            reasons = outcome.setdefault("metadata_failure_reason_counts", {})
            reasons[reason] = int(reasons.get(reason, 0) or 0) + int(count or 0)
        outcome["accepted_count"] += accepted_count
        status = str(row.get("status") or "")
        if accepted_count or status == "成功":
            outcome["nonzero_result_query_count"] += 1
        if status.startswith("失敗") or "失敗" in status:
            outcome["failed_query_count"] += 1
        domain = _academic_domain(str(row.get("url") or "")) or _academic_domain(domain_hints.get(source_name, ""))
        if domain and domain not in outcome["domains"]:
            outcome["domains"].append(domain)
        outcome["statuses"].append(status or "未提供狀態")
    return outcomes


def academic_source_diagnostics(
    statuses: list[dict],
    candidates: list[dict] | None = None,
    selected: list[dict] | None = None,
) -> dict:
    """Return source-level discovery/rescue/selection metrics for debug output."""
    source_rows: dict[str, dict] = {}
    for row in statuses or []:
        if row.get("timing_stage") == "summary":
            continue
        source_family = str(row.get("source_family") or row.get("query") or "Generic Academic")
        source = _journal_source_label(source_family)
        if row.get("timing_stage") == "source_page_fetch":
            source = _journal_source_label(str(row.get("query") or source))
        metrics = source_rows.setdefault(source, {
            "query_calls": 0,
            "backend_raw_count": 0,
            "result_url_count": 0,
            "normalized_domain_match_count": 0,
            "metadata_eligible_count": 0,
            "metadata_attempted_count": 0,
            "metadata_resolved_count": 0,
            "metadata_budget_skipped_count": 0,
            "metadata_failure_reason_counts": {},
            "urban_rail_pass_count": 0,
            "journal_score_pass_count": 0,
            "accepted_count": 0,
            "domains": [],
        })
        metrics["query_calls"] += 1
        metrics["backend_raw_count"] += int(row.get("backend_raw_count", 0) or 0)
        metrics["result_url_count"] += int(row.get("result_url_count", 0) or 0)
        metrics["normalized_domain_match_count"] += int(row.get("domain_match_count", 0) or 0)
        metrics["metadata_eligible_count"] += int(row.get("metadata_eligible_count", 0) or 0)
        metrics["metadata_attempted_count"] += int(row.get("metadata_attempted_count", 0) or 0)
        metrics["metadata_resolved_count"] += int(row.get("metadata_resolved_count", 0) or 0)
        metrics["metadata_budget_skipped_count"] += int(row.get("metadata_budget_skipped_count", 0) or 0)
        for reason, count in (row.get("metadata_failure_reason_counts") or {}).items():
            reasons = metrics.setdefault("metadata_failure_reason_counts", {})
            reasons[reason] = int(reasons.get(reason, 0) or 0) + int(count or 0)
        metrics["urban_rail_pass_count"] += int(row.get("urban_rail_pass_count", 0) or 0)
        metrics["journal_score_pass_count"] += int(row.get("journal_score_pass_count", 0) or 0)
        metrics["accepted_count"] += int(row.get("accepted_count", row.get("count", 0)) or 0)
        domain = _academic_domain(str(row.get("url") or ""))
        if domain and domain not in metrics["domains"]:
            metrics["domains"].append(domain)

    def _candidate_source(item: dict) -> str:
        source = _journal_source_family_for_url(str(item.get("publisher_domain") or item.get("url") or ""))
        return source or _journal_source_label(str(item.get("discovery_source") or "Generic Academic"))

    candidate_counts: dict[str, int] = {}
    selected_counts: dict[str, int] = {}
    for item in candidates or []:
        source = _candidate_source(item)
        candidate_counts[source] = candidate_counts.get(source, 0) + 1
    for item in selected or []:
        source = _candidate_source(item)
        selected_counts[source] = selected_counts.get(source, 0) + 1
    for source, count in candidate_counts.items():
        source_rows.setdefault(source, {
            "query_calls": 0,
            "backend_raw_count": 0,
            "result_url_count": 0,
            "normalized_domain_match_count": 0,
            "metadata_eligible_count": 0,
            "metadata_attempted_count": 0,
            "metadata_resolved_count": 0,
            "metadata_budget_skipped_count": 0,
            "metadata_failure_reason_counts": {},
            "urban_rail_pass_count": 0,
            "journal_score_pass_count": 0,
            "accepted_count": 0,
            "domains": [],
        })["candidate_count"] = count
    for source, count in selected_counts.items():
        source_rows.setdefault(source, {"candidate_count": 0})["selected_count"] = count
    for metrics in source_rows.values():
        metrics.setdefault("candidate_count", 0)
        metrics.setdefault("selected_count", 0)
    selected_domains = {
        _academic_domain(str(item.get("publisher_domain") or item.get("url") or ""))
        for item in selected or []
    }
    selected_domains.discard("")
    return {
        "academic_discovery_by_source": source_rows,
        "academic_metadata_rescue_by_source": {
            source: metrics.get("metadata_resolved_count", 0)
            for source, metrics in source_rows.items()
        },
        "academic_selected_by_source": selected_counts,
        "academic_source_diversity_count": len(selected_domains),
    }


def _journal_shortfall_reason(selected_count: int, target_min: int, excluded: list[dict]) -> str:
    if selected_count >= target_min:
        return "已達學術期刊目標篇數下限。"
    stats = _journal_exclusion_stats(excluded)
    if not stats:
        return "未搜尋到足夠可信學術候選。"
    top = sorted(stats.items(), key=lambda x: -x[1])[:3]
    return "符合條件研究不足；主要排除原因：" + "、".join(f"{k} {v} 篇" for k, v in top)


def collect_journal_candidates(
    *,
    context: JournalServiceContext,
) -> tuple[list[dict], list[dict], list[dict]]:
    if not context.include_research_supplement:
        return [], [], []
    if context.ddgs_client_factory is None:
        return [], [{"query": "國際學術期刊補充", "status": "ddgs 套件未安裝", "count": 0}], []

    target_min, target_max = get_journal_target_count(context.research_supplement_lookback_days)
    total_started = time.perf_counter()
    query_specs = [
        *(("precision_queries", query) for query in JOURNAL_PRECISION_QUERIES),
        *(("exploratory_queries", query) for query in JOURNAL_EXPLORATORY_QUERIES),
        *(("broad_academic", query) for query in build_broad_academic_queries()),
    ]
    candidates: list[dict] = []
    statuses: list[dict] = []
    excluded: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    metadata_cache: dict[str, dict] = {}
    metadata_fetch_count = 0
    metadata_route_attempts: dict[str, int] = {}
    metadata_route_stats: dict[str, dict] = {}
    metadata_route_cap = max(1, int(JOURNAL_ARTICLE_FETCH_LIMIT) // len(JOURNAL_METADATA_ROUTE_NAMES))
    metadata_resolution = {
        "attempted": 0,
        "success": 0,
        "failed": 0,
        "rescued": 0,
        "year_only_rejected": 0,
    }
    journal_timings = {
        "source_page_fetch": 0.0,
        "ddgs_search": 0.0,
        "metadata_fetch": 0.0,
        "candidate_scoring": 0.0,
        "dedupe_and_selection": 0.0,
    }

    def _route_metrics(route: str) -> dict:
        return metadata_route_stats.setdefault(route, _new_metadata_route_metrics())

    def _record_route_failure(route: str, reason: str) -> None:
        if not reason:
            return
        metrics = _route_metrics(route)
        reasons = metrics.setdefault("metadata_failure_reason_counts", {})
        reasons[reason] = int(reasons.get(reason, 0) or 0) + 1

    def _record_pipeline_failure(pipeline_counts: dict | None, reason: str) -> None:
        if pipeline_counts is None or not reason:
            return
        reasons = pipeline_counts.setdefault("metadata_failure_reason_counts", {})
        reasons[reason] = int(reasons.get(reason, 0) or 0) + 1

    def _exclude(query: str, title: str, url: str, reason: str, snippet: str = "", extra: dict | None = None) -> None:
        if len(excluded) < 120:
            item = {
                "query": query,
                "title": title,
                "url": url,
                "snippet": _shorten(snippet, 220),
                "exclude_reason": reason,
            }
            if extra:
                item.update(extra)
            excluded.append(item)

    def _try_accept_result(
        result: dict,
        query: str,
        *,
        source_family: str = "",
        pipeline_counts: dict[str, int] | None = None,
    ) -> bool:
        nonlocal metadata_fetch_count
        title = _clean_text(result.get("title") or "")
        snippet = _clean_text(result.get("body") or result.get("excerpt") or result.get("description") or "")
        url = _journal_result_url(result)
        if not title or not url:
            return False
        metadata = dict(result.get("journal_metadata") or {}) if isinstance(result.get("journal_metadata"), dict) else {}
        doi = _extract_doi(f"{url} {title} {snippet} {metadata.get('doi', '')}")
        pii = metadata.get("pii") or _extract_pii(f"{url} {title} {snippet}")
        if doi:
            metadata["doi"] = doi
        if pii:
            metadata["pii"] = pii
        metadata["publisher_domain"] = _academic_publisher_domain(url, metadata)
        metadata["discovery_source"] = str(
            result.get("discovery_source")
            or source_family
            or _journal_source_family_for_url(url)
            or "generic_academic"
        )
        metadata["discovery_date_hint"] = _discovery_date_hint(result, title, snippet)
        metadata_route = _metadata_route_for_candidate(source_family, url, metadata)
        route_metrics = _route_metrics(metadata_route)
        metadata["metadata_priority_score"] = int(result.get("_metadata_priority_score", 0) or 0)
        metadata["metadata_priority_components"] = dict(result.get("_metadata_priority_components") or {})
        metadata["route_rank_before_metadata"] = int(result.get("_metadata_route_rank_before", 0) or 0)
        text = f"{title} {snippet} {url} {metadata.get('journal_name', '')} {doi} {pii}"
        if pipeline_counts is not None and _journal_source_domain_matches(url, source_family):
            pipeline_counts["domain_match_count"] += 1
            route_metrics["domain_match_count"] += 1
        if any(term.casefold() in text.casefold() for term in JOURNAL_EXCLUDE_TERMS):
            _exclude(query, title, url, "非都市軌道研究場景或排除運具", snippet)
            return False
        if not _is_formal_journal_url_or_doi(url, text):
            _exclude(query, title, url, "缺少 DOI 或正式期刊 URL", snippet)
            return False

        page_type = classify_academic_page_type(url, title, doi=doi, pii=pii)
        if pipeline_counts is not None:
            if page_type == "ARTICLE_PAGE":
                pipeline_counts["article_page_count"] += 1
            if page_type == "ARTICLE_PAGE" or doi or pii:
                pipeline_counts["metadata_eligible_count"] += 1
        if page_type == "ARTICLE_PAGE" or doi or pii:
            route_metrics["metadata_eligible_count"] += 1

        if not _contains_any_term(text, JOURNAL_RAIL_CONTEXT_TERMS):
            _exclude(query, title, url, "缺少 railway/metro/urban rail 等明確場景", snippet, metadata)
            return False
        if not context.is_urban_rail_candidate(text) and not _contains_any_term(
            text,
            ["metro system", "urban rail transit", "rail transit", "urban metro"],
        ):
            _exclude(query, title, url, "都市軌道關聯不足", snippet, metadata)
            return False
        if pipeline_counts is not None:
            pipeline_counts["urban_rail_pass_count"] += 1
        route_metrics["urban_rail_pass_count"] += 1

        date_info = _research_date_info(result, title, snippet, context=context)
        initial_date_info = dict(date_info)
        if date_info["date_confidence"] == "high" and date_info["is_within_research_period"]:
            metadata["metadata_resolution_status"] = "METADATA_NOT_NEEDED"
        elif page_type != "ARTICLE_PAGE" and not (doi or pii):
            metadata["metadata_resolution_status"] = "METADATA_SKIPPED_GENERIC_PAGE"
            metadata["metadata_lookup_skipped_reason"] = "generic_landing_page_title"
            if pipeline_counts is not None:
                pipeline_counts["metadata_false_match_rejected_count"] += 1
        else:
            cache_key = _dedupe_url(url)
            fetched = metadata_cache.get(cache_key)
            if fetched is None and metadata_fetch_count < JOURNAL_ARTICLE_FETCH_LIMIT and metadata_route_attempts.get(metadata_route, 0) < metadata_route_cap:
                metadata_started = time.perf_counter()
                metadata_resolution["attempted"] += 1
                metadata_route_attempts[metadata_route] = metadata_route_attempts.get(metadata_route, 0) + 1
                route_metrics["metadata_attempted_count"] += 1
                if pipeline_counts is not None:
                    pipeline_counts["metadata_attempted_count"] += 1
                fetched = resolve_journal_metadata(
                    url,
                    doi=doi,
                    pii=pii,
                    title=title,
                    snippet=snippet,
                    discovery_date_hint=date_info.get("discovery_date_hint", ""),
                    page_type=page_type,
                    context=context,
                )
                metadata_cache[cache_key] = dict(fetched)
                journal_timings["metadata_fetch"] += time.perf_counter() - metadata_started
                metadata_fetch_count += 1
            elif fetched is None:
                fetched = {
                    "metadata_fetch_status": "budget_skipped",
                    "metadata_source": "metadata_budget",
                    "metadata_reject_reason": (
                        "已達 metadata route budget"
                        if metadata_route_attempts.get(metadata_route, 0) >= metadata_route_cap
                        else "已達 metadata fetch budget"
                    ),
                }
                metadata_route_stats.setdefault(metadata_route, _new_metadata_route_metrics())[
                    "metadata_budget_skipped_count"
                ] += 1
                if pipeline_counts is not None:
                    pipeline_counts["metadata_budget_skipped_count"] += 1
                    reason = fetched["metadata_reject_reason"]
                    failure_reasons = pipeline_counts.setdefault("metadata_failure_reason_counts", {})
                    failure_reasons[reason] = int(failure_reasons.get(reason, 0) or 0) + 1
                _record_route_failure(metadata_route, fetched["metadata_reject_reason"])
            metadata["metadata_resolution_status"] = "METADATA_ATTEMPTED"
            if fetched.get("metadata_fetch_status") == "skipped":
                metadata["metadata_resolution_status"] = "METADATA_SKIPPED_GENERIC_PAGE"
                metadata["metadata_lookup_skipped_reason"] = fetched.get("metadata_lookup_skipped_reason", "generic_landing_page_title")
                if pipeline_counts is not None:
                    pipeline_counts["metadata_false_match_rejected_count"] += 1
                _record_pipeline_failure(pipeline_counts, metadata["metadata_lookup_skipped_reason"])
            elif fetched.get("metadata_fetch_status") == "budget_skipped":
                metadata["metadata_resolution_status"] = "METADATA_BUDGET_SKIPPED"
                metadata["metadata_reject_reason"] = fetched.get("metadata_reject_reason", "已達 metadata budget")
            elif fetched.get("metadata_fetch_status") == "success":
                metadata_resolution["success"] += 1
                metadata.update(fetched)
                route_metrics["metadata_resolved_count"] += 1
                metadata["publisher_domain"] = _academic_publisher_domain(url, metadata)
                if fetched.get("metadata_title") and len(fetched.get("metadata_title", "")) > len(title):
                    title = fetched["metadata_title"]
                if fetched.get("metadata_abstract") and len(fetched.get("metadata_abstract", "")) > len(snippet):
                    snippet = fetched["metadata_abstract"]
                result_with_metadata = dict(result)
                result_with_metadata["journal_metadata"] = metadata
                date_info = _research_date_info(result_with_metadata, title, snippet, context=context)
                rescued = initial_date_info["date_confidence"] != "high" and date_info["date_confidence"] == "high"
                if rescued:
                    metadata_resolution["rescued"] += 1
                    metadata["metadata_resolution_status"] = "METADATA_RESCUED"
                    if pipeline_counts is not None:
                        pipeline_counts["metadata_rescued_count"] += 1
                if pipeline_counts is not None and _metadata_has_authoritative_date(metadata):
                    pipeline_counts["metadata_resolved_count"] += 1
            else:
                metadata_resolution["failed"] += 1
                metadata["metadata_resolution_status"] = "METADATA_FAILED"
                if fetched.get("metadata_reject_reason"):
                    metadata["metadata_reject_reason"] = fetched["metadata_reject_reason"]
                if fetched.get("metadata_match_status") == "low_confidence" and pipeline_counts is not None:
                    pipeline_counts["metadata_false_match_rejected_count"] += 1
                failure_reason = str(fetched.get("metadata_reject_reason") or "metadata lookup failed")
                _record_pipeline_failure(pipeline_counts, failure_reason)
                _record_route_failure(metadata_route, failure_reason)
            if date_info["date_confidence"] != "high":
                metadata_resolution["year_only_rejected"] += 1
            text = f"{title} {snippet} {url} {metadata.get('journal_name', '')} {metadata.get('doi', doi)} {metadata.get('pii', pii)}"
        if date_info["date_confidence"] != "high":
            metadata_resolution["year_only_rejected"] += 1
        if date_info["date_confidence"] != "high" or not date_info["is_within_research_period"]:
            if date_info["date_confidence"] == "high" and not date_info["is_within_research_period"]:
                exclude_reason = f"明確發表日期不在{context.research_supplement_period_label}研究補充期間"
            else:
                exclude_reason = date_info["date_reason"]
            metadata["metadata_disposition"] = (
                "DISCOVERED_BUT_METADATA_REJECTED"
                if date_info["date_confidence"] != "high"
                else "DATE_OUT_OF_RESEARCH_PERIOD"
            )
            _exclude(query, title, url, exclude_reason, snippet, metadata)
            return False
        if pipeline_counts is not None:
            pipeline_counts["date_pass_count"] += 1

        title_key = _normalize_title(title)
        url_key = _dedupe_url(url)
        if title_key in seen_titles or url_key in seen_urls:
            _exclude(query, title, url, "重複研究候選", snippet, metadata)
            return False
        seen_titles.add(title_key)
        seen_urls.add(url_key)

        source = metadata.get("journal_name") or _academic_domain(url) or "研究資料庫"
        candidate = context.make_news_candidate(
            title=title,
            date=date_info["published_date"],
            source=source,
            url=url,
            snippet=snippet,
            query=query,
            region="國際研究",
            source_type="國際學術/技術研究",
        )
        candidate["year"] = _journal_year(candidate)
        candidate["published_date"] = date_info["published_date"]
        candidate["date_confidence"] = date_info["date_confidence"]
        candidate["date_reason"] = date_info["date_reason"]
        candidate["date_source"] = date_info.get("date_source", "")
        candidate["date_authoritative"] = bool(date_info.get("date_authoritative"))
        candidate["date_resolution_method"] = date_info.get("date_resolution_method", "")
        candidate["metadata_source"] = date_info.get("metadata_source") or metadata.get("metadata_source", "search_result")
        candidate["publication_date"] = date_info["published_date"]
        candidate["metadata_fields_seen"] = list(dict.fromkeys(
            list(date_info.get("metadata_fields_seen") or [])
            + list(metadata.get("metadata_fields_seen") or [])
        ))
        candidate["is_within_research_period"] = date_info["is_within_research_period"]
        candidate["doi"] = metadata.get("doi", doi)
        candidate["pii"] = metadata.get("pii", pii)
        candidate["journal_name"] = metadata.get("journal_name", source)
        candidate["metadata_fetch_status"] = metadata.get("metadata_fetch_status", "not_needed")
        candidate["metadata_route"] = metadata_route
        candidate["metadata_priority_score"] = metadata.get("metadata_priority_score", 0)
        candidate["metadata_priority_components"] = dict(metadata.get("metadata_priority_components") or {})
        candidate["route_rank_before_metadata"] = metadata.get("route_rank_before_metadata", 0)
        candidate["metadata_attempted"] = metadata.get("metadata_resolution_status") in {
            "METADATA_ATTEMPTED",
            "METADATA_RESCUED",
            "METADATA_FAILED",
            "METADATA_BUDGET_SKIPPED",
        }
        candidate["metadata_method"] = metadata.get("metadata_attempt_method", "")
        candidate["metadata_resolved"] = _metadata_has_authoritative_date(metadata)
        candidate["metadata_failure_reason"] = (
            metadata.get("metadata_reject_reason")
            or metadata.get("metadata_lookup_skipped_reason")
            or ""
        )
        candidate["page_type"] = page_type
        candidate["publisher_domain"] = _academic_publisher_domain(url, metadata)
        candidate["discovery_source"] = metadata.get("discovery_source") or source_family or "generic_academic"
        candidate["discovery_date_hint"] = date_info.get("discovery_date_hint", "")
        scoring_started = time.perf_counter()
        candidate.update(score_journal_candidate(candidate))
        journal_timings["candidate_scoring"] += time.perf_counter() - scoring_started
        if candidate["journal_score"] < 60:
            _exclude(query, title, url, "journal_score 低於候補門檻", snippet, candidate)
            return False
        if pipeline_counts is not None:
            pipeline_counts["journal_score_pass_count"] += 1
        candidates.append(candidate)
        route_metrics["accepted_count"] += 1
        if pipeline_counts is not None:
            pipeline_counts["accepted_count"] += 1
        return True

    source_results, source_statuses = _journal_source_page_results(context=context)
    statuses.extend(source_statuses)
    source_accepted = 0
    source_stage_counts: dict[str, dict[str, int]] = {}
    for result in _prioritize_metadata_results(source_results, "source_pages"):
        if len(candidates) >= target_max:
            break
        source_name = result.get("source_page", "學術來源頁")
        result_counts = _journal_pipeline_counts()
        if _try_accept_result(
            result,
            source_name,
            source_family=source_name,
            pipeline_counts=result_counts,
        ):
            source_accepted += 1
        stage_counts = source_stage_counts.setdefault(source_name, _journal_pipeline_counts())
        for key in (
            "domain_match_count", "metadata_attempted_count", "metadata_resolved_count",
            "urban_rail_pass_count", "journal_score_pass_count", "accepted_count",
        ):
            stage_counts[key] += result_counts[key]
    for row in source_statuses:
        stage_counts = source_stage_counts.get(row.get("query", ""))
        if not stage_counts:
            continue
        for key in (
            "domain_match_count", "metadata_attempted_count", "metadata_resolved_count",
            "urban_rail_pass_count", "journal_score_pass_count", "accepted_count",
        ):
            row[key] = stage_counts[key]
    if source_results:
        statuses.append({"query": "可信學術來源頁彙整", "status": "成功" if source_accepted else "無符合研究", "count": source_accepted})

    for source_family, query in query_specs:
        if len(candidates) >= target_max:
            break
        if context.status_callback:
            context.status_callback("正在整理候選資料")
        query_text = f'{query} journal OR research OR paper OR IEEE OR "Transportation Research"'
        pipeline_counts = _journal_pipeline_counts()
        query_started = time.perf_counter()
        try:
            with context.ddgs_client_factory() as ddgs:
                results = ddgs.text(query_text, max_results=JOURNAL_MAX_RESULTS_PER_QUERY, backend="auto")
        except Exception as exc:
            elapsed = time.perf_counter() - query_started
            journal_timings["ddgs_search"] += elapsed
            statuses.append({"query": query_text, "source_family": source_family, "status": f"失敗：{exc}", "count": 0, "accepted_count": 0, **pipeline_counts, "elapsed_seconds": round(elapsed, 3), "timing_stage": "ddgs_search"})
            continue

        results = list(results or [])
        pipeline_counts["backend_raw_count"] = len(results)
        pipeline_counts["result_url_count"] = sum(1 for result in results if _journal_result_url(result))
        accepted = 0
        for result in _prioritize_metadata_results(results, source_family):
            if len(candidates) >= target_max:
                break
            if _try_accept_result(result, query, source_family=source_family, pipeline_counts=pipeline_counts):
                accepted += 1
        elapsed = time.perf_counter() - query_started
        journal_timings["ddgs_search"] += elapsed
        statuses.append({"query": query_text, "source_family": source_family, "status": "成功" if accepted else "無符合研究", "count": accepted, "accepted_count": accepted, **pipeline_counts, "elapsed_seconds": round(elapsed, 3), "timing_stage": "ddgs_search"})

    for source_name, query in JOURNAL_SOURCE_QUERY_SPECS:
        for _ in range(max(0, int(JOURNAL_SOURCE_QUERY_BUDGET))):
            query_started = time.perf_counter()
            query_text = f"{query} journal research paper"
            pipeline_counts = _journal_pipeline_counts()
            try:
                with context.ddgs_client_factory() as ddgs:
                    results = ddgs.text(query_text, max_results=JOURNAL_MAX_RESULTS_PER_QUERY, backend="auto")
            except Exception as exc:
                elapsed = time.perf_counter() - query_started
                journal_timings["ddgs_search"] += elapsed
                statuses.append({"query": query_text, "source_family": source_name, "status": f"失敗：{exc}", "count": 0, "accepted_count": 0, **pipeline_counts, "elapsed_seconds": round(elapsed, 3), "timing_stage": "ddgs_search"})
                continue
            results = list(results or [])
            pipeline_counts["backend_raw_count"] = len(results)
            pipeline_counts["result_url_count"] = sum(1 for result in results if _journal_result_url(result))
            accepted = 0
            for result in _prioritize_metadata_results(results, source_name):
                if _try_accept_result(result, query_text, source_family=source_name, pipeline_counts=pipeline_counts):
                    accepted += 1
            elapsed = time.perf_counter() - query_started
            journal_timings["ddgs_search"] += elapsed
            statuses.append({"query": query_text, "source_family": source_name, "status": "成功" if accepted else "無符合研究", "count": accepted, "accepted_count": accepted, **pipeline_counts, "elapsed_seconds": round(elapsed, 3), "timing_stage": "ddgs_search"})

    high_score = [item for item in candidates if int(item.get("journal_score", 0) or 0) >= 75]
    borderline = [item for item in candidates if 60 <= int(item.get("journal_score", 0) or 0) < 75]
    def _select_with_source_diversity(items: list[dict], limit: int | None = None) -> list[dict]:
        remaining = list(items)
        selected_items: list[dict] = []
        seen_domains: set[str] = set()
        while remaining and (limit is None or len(selected_items) < limit):
            def _priority(item: dict) -> tuple:
                domain = _academic_domain(item.get("publisher_domain") or item.get("url", "")) or "unknown"
                score = int(item.get("journal_score", 0) or 0)
                diversity_bonus = 4 if domain not in seen_domains else 0
                return (
                    score + diversity_bonus,
                    score,
                    item.get("published_date", ""),
                    item.get("journal_name", ""),
                    domain,
                )
            chosen = max(remaining, key=_priority)
            remaining.remove(chosen)
            domain = _academic_domain(chosen.get("publisher_domain") or chosen.get("url", "")) or "unknown"
            chosen["journal_source_diversity_bonus"] = 4 if domain not in seen_domains else 0
            seen_domains.add(domain)
            selected_items.append(chosen)
        return selected_items

    selection_started = time.perf_counter()
    selected = _select_with_source_diversity(high_score)
    if len(selected) < target_min:
        selected.extend(_select_with_source_diversity(borderline, target_min - len(selected)))
    selected = sorted(
        selected,
        key=lambda item: (-int(item.get("journal_score", 0) or 0), item.get("journal_name", ""), item.get("published_date", "")),
    )[:target_max]
    journal_timings["dedupe_and_selection"] = time.perf_counter() - selection_started
    domain_candidate_counts: dict[str, int] = {}
    journal_selected_counts: dict[str, int] = {}
    domain_selected_counts: dict[str, int] = {}
    for item in candidates:
        domain = _academic_domain(item.get("publisher_domain") or item.get("url", "")) or "unknown"
        domain_candidate_counts[domain] = domain_candidate_counts.get(domain, 0) + 1
    for item in selected:
        journal = str(item.get("journal_name") or item.get("source") or "unknown")
        domain = _academic_domain(item.get("publisher_domain") or item.get("url", "")) or "unknown"
        journal_selected_counts[journal] = journal_selected_counts.get(journal, 0) + 1
        domain_selected_counts[domain] = domain_selected_counts.get(domain, 0) + 1
    elapsed_by_source: dict[str, float] = {}
    for row in statuses:
        if row.get("timing_stage") not in {"source_page_fetch", "ddgs_search"}:
            continue
        source_key = str(row.get("source_family") or row.get("query") or "unknown")
        elapsed_by_source[source_key] = round(
            elapsed_by_source.get(source_key, 0.0) + float(row.get("elapsed_seconds", 0) or 0),
            3,
        )
    journal_timings["source_page_fetch"] = sum(
        float(row.get("elapsed_seconds", 0) or 0)
        for row in statuses
        if row.get("timing_stage") == "source_page_fetch"
    )
    journal_timings = {
        key: round(value, 3)
        for key, value in journal_timings.items()
    }
    journal_timings["total"] = round(time.perf_counter() - total_started, 3)
    for row in statuses:
        if row.get("timing_stage") not in {"source_page_fetch", "ddgs_search"}:
            continue
        source_route = _journal_source_label(str(row.get("source_family") or row.get("query") or "Generic Academic"))
        if source_route not in JOURNAL_METADATA_ROUTE_NAMES:
            source_route = "Generic Academic"
        route_metrics = _route_metrics(source_route)
        route_metrics["query_count"] += 1
        route_metrics["raw_count"] += int(row.get("backend_raw_count", row.get("count", 0)) or 0)
    for route in JOURNAL_METADATA_ROUTE_NAMES:
        _route_metrics(route)
    source_pipeline_counts = journal_query_source_outcomes(statuses)
    academic_diagnostics = academic_source_diagnostics(statuses, candidates, selected)
    statuses.append({
        "query": "journal_diagnostics",
        "status": "summary",
        "count": len(candidates),
        "journal_candidate_count_by_domain": domain_candidate_counts,
        "journal_selected_count_by_journal": journal_selected_counts,
        "journal_selected_count_by_domain": domain_selected_counts,
        "journal_elapsed_by_source": elapsed_by_source,
        "journal_timings": journal_timings,
        "journal_query_source_outcomes": source_pipeline_counts,
        "journal_metadata_route_outcomes": metadata_route_stats,
        "journal_source_pipeline_counts": source_pipeline_counts,
        **academic_diagnostics,
        "journal_metadata_resolution": metadata_resolution,
        "timing_stage": "summary",
    })
    for item in selected:
        item["journal_target_count"] = target_min
        item["journal_selected_count"] = len(selected)
        item["journal_shortfall_reason"] = _journal_shortfall_reason(len(selected), target_min, excluded)
    return selected, statuses, excluded
