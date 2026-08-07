"""International journal candidate collection without Streamlit dependencies."""

import datetime
import json
import re
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
    date_fields = [
        "published_date", "publication_date", "online_publication_date",
        "article_date", "release_date", "published", "date",
    ]
    for key in date_fields:
        value = result.get(key) or result.get(key.replace("_", ""))
        date_obj = _parse_full_research_date(str(value or ""))
        if date_obj:
            cutoff_date = context.today - datetime.timedelta(days=context.research_supplement_lookback_days)
            return {
                "published_date": date_obj.isoformat(),
                "date_confidence": "high",
                "date_reason": f"{key} 提供完整日期",
                "is_within_research_period": cutoff_date <= date_obj <= context.today,
            }

    labelled_patterns = [
        r"(?:published date|publication date|online publication date|article date|release date)\s*[:：]\s*([A-Za-z0-9,\-/\s]+)",
        r"(?:發表日期|出版日期|發布日期)\s*[:：]\s*([0-9年月日\-/\s]+)",
    ]
    text = f"{title} {snippet}"
    for pattern in labelled_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        date_obj = _parse_full_research_date(match.group(1))
        if date_obj:
            cutoff_date = context.today - datetime.timedelta(days=context.research_supplement_lookback_days)
            return {
                "published_date": date_obj.isoformat(),
                "date_confidence": "high",
                "date_reason": "摘要提供明確發表/出版/發布日期",
                "is_within_research_period": cutoff_date <= date_obj <= context.today,
            }

    year_only = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    return {
        "published_date": "",
        "date_confidence": "low",
        "date_reason": "只有年份或未提供明確發表日期" if year_only else "未提供明確發表日期",
        "is_within_research_period": False,
    }


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


def _first_meta_content(html: str, names: list[str]) -> str:
    for name in names:
        patterns = [
            rf'<meta[^>]+(?:name|property)=["\\\']{re.escape(name)}["\\\'][^>]+content=["\\\']([^"\\\']+)["\\\']',
            rf'<meta[^>]+content=["\\\']([^"\\\']+)["\\\'][^>]+(?:name|property)=["\\\']{re.escape(name)}["\\\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html or "", flags=re.IGNORECASE | re.DOTALL)
            if match:
                return _html_unescape_clean(match.group(1))
    return ""


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
        return {"metadata_fetch_status": "failed"}
    jsonld = _jsonld_values(html)
    title = (
        _first_meta_content(html, ["citation_title", "dc.title", "og:title", "twitter:title"])
        or _html_unescape_clean(jsonld.get("headline") or jsonld.get("name") or "")
    )
    abstract = (
        _first_meta_content(html, ["citation_abstract", "description", "dc.description", "og:description", "twitter:description"])
        or _html_unescape_clean(jsonld.get("description") or "")
    )
    date_text = (
        _first_meta_content(html, [
            "citation_publication_date", "citation_online_date", "dc.date", "prism.publicationDate",
            "article:published_time", "datePublished", "date", "DC.Date",
        ])
        or jsonld.get("datePublished")
        or jsonld.get("dateCreated")
    )
    doi = _first_meta_content(html, ["citation_doi", "dc.identifier", "prism.doi"])
    if not doi:
        doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", html, flags=re.IGNORECASE)
        doi = doi_match.group(0) if doi_match else ""
    journal_name = _first_meta_content(html, ["citation_journal_title", "prism.publicationName", "dc.source", "og:site_name"])
    published_date = ""
    date_confidence = "low"
    date_reason = "原始頁未解析到完整發表日期"
    date_obj = _parse_full_research_date(date_text or "")
    if date_obj:
        cutoff_date = context.today - datetime.timedelta(days=context.research_supplement_lookback_days)
        published_date = date_obj.isoformat()
        date_confidence = "high"
        date_reason = "原始文章頁 metadata 提供完整發表日期"
    return {
        "metadata_fetch_status": "success",
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
        "journal_name": journal_name,
    }


def _journal_source_page_results(*, context: JournalServiceContext) -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    statuses: list[dict] = []
    fetched = 0
    seen_links: set[str] = set()
    for source_name, page_url in JOURNAL_SOURCE_PAGES:
        if context.status_callback:
            context.status_callback("正在整理候選資料")
        html = _journal_safe_get(page_url, http_session_factory=context.http_session_factory)
        if not html:
            statuses.append({"query": source_name, "status": "來源頁讀取失敗", "count": 0, "url": page_url})
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
        for link in links:
            if fetched >= JOURNAL_ARTICLE_FETCH_LIMIT:
                break
            meta = fetch_journal_page_metadata(link, context=context)
            fetched += 1
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
            })
        statuses.append({"query": source_name, "status": "成功" if links else "無文章連結", "count": len(links), "url": page_url})
    return results, statuses


def score_journal_candidate(candidate: dict) -> dict:
    text = f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('url', '')} {candidate.get('journal_name', '')} {candidate.get('doi', '')}"
    score = 0
    reasons: list[str] = []
    host = _domain_from_url(candidate.get("url", ""))
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
    queries = JOURNAL_PRECISION_QUERIES + JOURNAL_EXPLORATORY_QUERIES
    candidates: list[dict] = []
    statuses: list[dict] = []
    excluded: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    metadata_fetch_count = 0

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

    def _try_accept_result(result: dict, query: str) -> bool:
        nonlocal metadata_fetch_count
        title = _clean_text(result.get("title") or "")
        snippet = _clean_text(result.get("body") or result.get("excerpt") or result.get("description") or "")
        url = result.get("href") or result.get("url") or ""
        if not title or not url:
            return False
        metadata = result.get("journal_metadata") if isinstance(result.get("journal_metadata"), dict) else {}
        text = f"{title} {snippet} {url} {metadata.get('journal_name', '')} {metadata.get('doi', '')}"
        if any(term.casefold() in text.casefold() for term in JOURNAL_EXCLUDE_TERMS):
            _exclude(query, title, url, "非都市軌道研究場景或排除運具", snippet)
            return False
        if not _is_formal_journal_url_or_doi(url, text):
            _exclude(query, title, url, "缺少 DOI 或正式期刊 URL", snippet)
            return False

        date_info = _research_date_info(result, title, snippet, context=context)
        if (
            date_info["date_confidence"] != "high"
            or not date_info["is_within_research_period"]
        ) and metadata_fetch_count < JOURNAL_ARTICLE_FETCH_LIMIT:
            fetched = fetch_journal_page_metadata(url, context=context)
            metadata_fetch_count += 1
            if fetched.get("metadata_fetch_status") == "success":
                metadata.update(fetched)
                if fetched.get("metadata_title") and len(fetched.get("metadata_title", "")) > len(title):
                    title = fetched["metadata_title"]
                if fetched.get("metadata_abstract") and len(fetched.get("metadata_abstract", "")) > len(snippet):
                    snippet = fetched["metadata_abstract"]
                if fetched.get("published_date"):
                    date_info = {
                        "published_date": fetched.get("published_date", ""),
                        "date_confidence": fetched.get("date_confidence", "low"),
                        "date_reason": fetched.get("date_reason", "原始文章頁 metadata"),
                        "is_within_research_period": fetched.get("is_within_research_period", False),
                    }
                text = f"{title} {snippet} {url} {metadata.get('journal_name', '')} {metadata.get('doi', '')}"

        if not _contains_any_term(text, JOURNAL_RAIL_CONTEXT_TERMS):
            _exclude(query, title, url, "缺少 railway/metro/urban rail 等明確場景", snippet, metadata)
            return False
        if not context.is_urban_rail_candidate(text) and not _contains_any_term(
            text,
            ["metro system", "urban rail transit", "rail transit", "urban metro"],
        ):
            _exclude(query, title, url, "都市軌道關聯不足", snippet, metadata)
            return False
        if date_info["date_confidence"] != "high" or not date_info["is_within_research_period"]:
            if date_info["date_confidence"] == "high" and not date_info["is_within_research_period"]:
                exclude_reason = f"明確發表日期不在{context.research_supplement_period_label}研究補充期間"
            else:
                exclude_reason = date_info["date_reason"]
            _exclude(query, title, url, exclude_reason, snippet, metadata)
            return False

        title_key = _normalize_title(title)
        url_key = _dedupe_url(url)
        if title_key in seen_titles or url_key in seen_urls:
            _exclude(query, title, url, "重複研究候選", snippet, metadata)
            return False
        seen_titles.add(title_key)
        seen_urls.add(url_key)

        source = metadata.get("journal_name") or _domain_from_url(url) or "研究資料庫"
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
        candidate["is_within_research_period"] = date_info["is_within_research_period"]
        candidate["doi"] = metadata.get("doi", "")
        candidate["journal_name"] = metadata.get("journal_name", source)
        candidate["metadata_fetch_status"] = metadata.get("metadata_fetch_status", "not_needed")
        candidate.update(score_journal_candidate(candidate))
        if candidate["journal_score"] < 60:
            _exclude(query, title, url, "journal_score 低於候補門檻", snippet, candidate)
            return False
        candidates.append(candidate)
        return True

    source_results, source_statuses = _journal_source_page_results(context=context)
    statuses.extend(source_statuses)
    source_accepted = 0
    for result in source_results:
        if len(candidates) >= target_max:
            break
        if _try_accept_result(result, result.get("source_page", "學術來源頁")):
            source_accepted += 1
    if source_results:
        statuses.append({"query": "可信學術來源頁彙整", "status": "成功" if source_accepted else "無符合研究", "count": source_accepted})

    for idx, query in enumerate(queries, 1):
        if len(candidates) >= target_max:
            break
        if context.status_callback:
            context.status_callback("正在整理候選資料")
        query_text = f'{query} journal OR research OR paper OR IEEE OR "Transportation Research"'
        try:
            with context.ddgs_client_factory() as ddgs:
                results = ddgs.text(query_text, max_results=JOURNAL_MAX_RESULTS_PER_QUERY, backend="auto")
        except Exception as exc:
            statuses.append({"query": query, "status": f"失敗：{exc}", "count": 0})
            continue

        accepted = 0
        for result in results or []:
            if len(candidates) >= target_max:
                break
            if _try_accept_result(result, query):
                accepted += 1
        statuses.append({"query": query, "status": "成功" if accepted else "無符合研究", "count": accepted})

    high_score = [item for item in candidates if int(item.get("journal_score", 0) or 0) >= 75]
    borderline = [item for item in candidates if 60 <= int(item.get("journal_score", 0) or 0) < 75]
    selected = sorted(
        high_score,
        key=lambda item: (-int(item.get("journal_score", 0) or 0), item.get("published_date", "")),
    )
    if len(selected) < target_min:
        selected.extend(
            sorted(
                borderline,
                key=lambda item: (-int(item.get("journal_score", 0) or 0), item.get("published_date", "")),
            )[: target_min - len(selected)]
        )
    selected = sorted(
        selected,
        key=lambda item: (-int(item.get("journal_score", 0) or 0), item.get("published_date", "")),
    )[:target_max]
    for item in selected:
        item["journal_target_count"] = target_min
        item["journal_selected_count"] = len(selected)
        item["journal_shortfall_reason"] = _journal_shortfall_reason(len(selected), target_min, excluded)
    return selected, statuses, excluded
