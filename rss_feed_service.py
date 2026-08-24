"""RSS/Atom collection, fallback handling, and source diagnostics."""

import datetime
import re
from dataclasses import dataclass
from typing import Callable

from article_processor import RawSearchText, build_raw_ingest_id
from config import MAX_ITEMS_PER_SOURCE
from search_service import FeedFetchError


@dataclass
class RssFeedContext:
    lookback_days: int
    feedparser_module: object | None
    http_session_factory: Callable[[], object]
    fetch_feed_callback: Callable[[object, str, object | None], object]
    fallback_url_builder: Callable[[str], str | None]
    url_safety_check: Callable[..., tuple[bool, str]]
    known_bad_source_checker: Callable[[str, str], bool]
    parse_pub_date: Callable[[str], str]
    is_recent: Callable[[str, datetime.datetime], bool]
    entry_pub_str: Callable[[object], str]
    entry_source_href: Callable[[object], str]
    contains_taiwan_reference: Callable[[str], bool]
    is_standards_source: Callable[[str], bool]
    is_standard_update_candidate: Callable[[str], bool]
    is_urban_rail_candidate: Callable[[str, str], bool]
    is_tech_news_only_mode: Callable[[], bool]
    is_technical_news_candidate: Callable[[str, str], bool]
    normalize_title: Callable[[str], str]
    dedupe_url: Callable[[str], str]
    domain_from_url: Callable[[str], str]
    status_callback: Callable[[str], None] | None = None
    now_provider: Callable[[], datetime.datetime] = (
        lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    news_scope: str = "international"


def _fallback_google_news_url(
    source_url: str,
    *,
    lookback_days: int,
    google_news_fallback_builder: Callable[[str, int], str],
) -> str | None:
    from urllib.parse import urlparse

    parsed = urlparse(source_url)
    if "news.google.com" in parsed.netloc:
        return None
    domain = parsed.netloc.lower().removeprefix("www.")
    if not domain:
        return None
    return google_news_fallback_builder(domain, int(lookback_days))


def _fetch_feed(session, url: str, *, context: RssFeedContext):
    return context.fetch_feed_callback(session, url, context.feedparser_module)


def _items_from_parsed_feed(
    parsed_feed,
    cutoff: datetime.datetime,
    seen_titles: set[str],
    seen_urls: set[str],
    source_name: str = "",
    *,
    context: RssFeedContext,
    feed_url: str = "",
    fetched_at: str | None = None,
    retrieval_method: str = "RSS",
) -> tuple[list[dict], int, int, int, int]:
    items: list[dict] = []
    invalid_count = 0
    blocked_count = 0
    duplicate_count = 0
    topic_filtered_count = 0

    for provider_record_index, entry in enumerate(getattr(parsed_feed, "entries", [])):
        raw_title = str(entry.get("title") or "")
        raw_url = str(entry.get("link") or "")
        raw_publication_value = entry.get("published")
        if raw_publication_value is None:
            raw_publication_value = entry.get("updated")
        if raw_publication_value is not None:
            raw_publication_value = str(raw_publication_value)
        title = raw_title.strip()
        link = raw_url.strip()
        desc = (entry.get("summary") or entry.get("description") or "").strip()
        pub_str = context.entry_pub_str(entry)
        source_href = context.entry_source_href(entry)
        provider_source = entry.get("source") or {}
        source_title = (
            provider_source.get("title") or provider_source.get("name")
            if isinstance(provider_source, dict)
            else None
        )
        publisher = entry.get("publisher") or source_title
        if publisher is not None:
            publisher = str(publisher)[:300]

        if not title or not context.is_recent(pub_str, cutoff):
            continue

        candidate_text = f"{title} {desc} {link} {source_href} {pub_str}"

        if context.news_scope == "international" and context.contains_taiwan_reference(candidate_text):
            blocked_count += 1
            continue

        # 規範更新來源必須是「真正更新」，不能只是標準首頁或追蹤清單
        if context.is_standards_source(source_name):
            if not pub_str or not context.is_standard_update_candidate(candidate_text):
                topic_filtered_count += 1
                continue

        if not context.is_urban_rail_candidate(candidate_text, source_name):
            topic_filtered_count += 1
            continue

        if context.is_tech_news_only_mode() and not context.is_technical_news_candidate(
            f"{title} {desc} {link} {source_href}",
            source_name,
        ):
            topic_filtered_count += 1
            continue

        is_valid, reason = context.url_safety_check(link, source_href=source_href)
        if not is_valid:
            if reason in ("被安全規則排除", "範圍排除"):
                blocked_count += 1
            else:
                invalid_count += 1
            continue

        title_key = context.normalize_title(title)
        url_key = context.dedupe_url(link)
        if title_key in seen_titles or url_key in seen_urls:
            duplicate_count += 1
            continue
        seen_titles.add(title_key)
        seen_urls.add(url_key)

        original_provider_metadata = {
            "entry_id": str(entry.get("id") or entry.get("guid") or "")[:500] or None,
            "published": str(entry.get("published"))[:500] if entry.get("published") is not None else None,
            "updated": str(entry.get("updated"))[:500] if entry.get("updated") is not None else None,
            "source_title": str(source_title)[:300] if source_title is not None else None,
            "source_href": str(source_href)[:500] if source_href else None,
            "feed_url": str(feed_url)[:500] if feed_url else None,
            "retrieval_method": str(retrieval_method)[:100],
        }
        raw_provenance = {
            "raw_title": raw_title,
            "raw_url": raw_url,
            "raw_publication_value": raw_publication_value,
            "fetched_at": fetched_at,
            "search_provider": "RSS",
            "publisher": publisher,
            "query": None,
            "query_region": None,
            "original_provider_metadata": original_provider_metadata,
            "raw_ingest_id": build_raw_ingest_id(
                search_provider="RSS",
                raw_title=raw_title,
                raw_url=raw_url,
                raw_publication_value=raw_publication_value,
                source=source_name,
                query=None,
                provider_record_index=provider_record_index,
            ),
        }
        items.append({
            "title": title,
            "link": link,
            "summary": re.sub(r"<[^>]+>", " ", desc)[:500],
            "date": context.parse_pub_date(pub_str),
            "source_href": source_href,
            "_raw_provenance": raw_provenance,
        })

    return items, invalid_count, blocked_count, duplicate_count, topic_filtered_count


def _status_record(
    source_name: str,
    method: str,
    status: str,
    item_count: int,
    error_message: str = "",
    fallback_used: bool = False,
) -> dict:
    return {
        "source_name": source_name,
        "method": method,
        "status": status,
        "item_count": item_count,
        "error_message": error_message,
        "fallback_used": fallback_used,
    }


def build_source_health_summary(source_statuses: list[dict]) -> dict:
    summary = {
        "total": len(source_statuses or []),
        "success": 0,
        "no_articles": 0,
        "non_urban_rail": 0,
        "skipped_known_bad": 0,
        "safety_excluded": 0,
        "fallback_success": 0,
        "fallback_used": 0,
        "other": 0,
    }
    for item in source_statuses or []:
        status = str(item.get("status", "") or "")
        message = str(item.get("error_message", "") or "")
        if item.get("fallback_used"):
            summary["fallback_used"] += 1
        if status in {"成功", "success"}:
            summary["success"] += 1
        elif status == "fallback 成功":
            summary["success"] += 1
            summary["fallback_success"] += 1
        elif status in {"無文章", "no_articles"}:
            summary["no_articles"] += 1
        elif status in {"非都市軌道", "non_urban_rail"}:
            summary["non_urban_rail"] += 1
        elif status == "skipped_known_bad":
            summary["skipped_known_bad"] += 1
        elif status in {"被安全規則排除", "範圍排除", "safety_excluded"} or "安全排除" in message:
            summary["safety_excluded"] += 1
        else:
            summary["other"] += 1
    return summary


def _method_for_url(
    url: str,
    *,
    domain_from_url: Callable[[str], str],
) -> str:
    return "Google News 代理" if "news.google.com" in domain_from_url(url) else "官方 RSS"


def _format_items_block(source_name: str, items: list[dict]) -> str:
    shown = items[:MAX_ITEMS_PER_SOURCE]
    lines = [f"【RSS來源：{source_name}（有效候選 {len(items)} 篇，傳給模型 {len(shown)} 篇）】"]
    for item in shown:
        source_hint = f"\n  原始來源：{item['source_href']}" if item.get("source_href") else ""
        lines.append(
            f"  日期：{item['date']}\n"
            f"  標題：{item['title']}\n"
            f"  摘要：{item['summary']}\n"
            f"  連結：{item['link']}{source_hint}"
        )
    return "\n".join(lines)


def fetch_rss_feeds(
    sources: list[tuple[str, str]],
    *,
    context: RssFeedContext,
    return_status: bool = False,
) -> str | tuple[str, list[dict]]:
    """Collect RSS/Atom sources and retain source-level diagnostics."""
    fetched_at_value = context.now_provider()
    fetched_at = fetched_at_value.isoformat()
    cutoff = fetched_at_value - datetime.timedelta(
        days=max(1, min(int(context.lookback_days), 365))
    )
    all_blocks: list[str] = []
    provenance_records: list[dict] = []
    source_statuses: list[dict] = []
    seen_titles: set[str] = set()
    seen_urls: set[str] = set()
    session = context.http_session_factory()

    for source_name, url in sources:
        if context.status_callback:
            context.status_callback("正在蒐集國際捷運新聞")

        method = _method_for_url(url, domain_from_url=context.domain_from_url)
        if context.known_bad_source_checker(source_name, url):
            source_statuses.append(_status_record(
                source_name,
                method,
                "skipped_known_bad",
                0,
                "已知官方 RSS 長期失效，保留代理或未來自訂 RSS 可能性",
            ))
            all_blocks.append(f"【RSS來源：{source_name}】（skipped_known_bad）")
            continue
        valid_source, source_reason = context.url_safety_check(url)
        if not valid_source and source_reason in ("被安全規則排除", "範圍排除"):
            source_statuses.append(_status_record(source_name, method, source_reason, 0, source_reason))
            all_blocks.append(f"【RSS來源：{source_name}】（{source_reason}）")
            continue

        try:
            parsed_feed = _fetch_feed(session, url, context=context)
            items_found, invalid_count, blocked_count, duplicate_count, topic_filtered_count = _items_from_parsed_feed(
                parsed_feed,
                cutoff,
                seen_titles,
                seen_urls,
                source_name,
                context=context,
                feed_url=url,
                fetched_at=fetched_at,
                retrieval_method=method,
            )
            if items_found:
                all_blocks.append(_format_items_block(source_name, items_found))
                provenance_records.extend(
                    item["_raw_provenance"]
                    for item in items_found[:MAX_ITEMS_PER_SOURCE]
                    if item.get("_raw_provenance")
                )
                source_statuses.append(_status_record(source_name, method, "成功", min(len(items_found), MAX_ITEMS_PER_SOURCE)))
            else:
                status = "非都市軌道" if topic_filtered_count and not (invalid_count or blocked_count) else "被安全規則排除" if blocked_count and not invalid_count else "無文章"
                message = f"無有效候選；非都市軌道 {topic_filtered_count}、無效連結 {invalid_count}、安全排除 {blocked_count}、重複 {duplicate_count}"
                all_blocks.append(f"【RSS來源：{source_name}】（{status}）")
                source_statuses.append(_status_record(source_name, method, status, 0, message))
        except FeedFetchError as exc:
            fallback_url = context.fallback_url_builder(url)
            if fallback_url:
                try:
                    parsed_feed = _fetch_feed(session, fallback_url, context=context)
                    items_found, invalid_count, blocked_count, duplicate_count, topic_filtered_count = _items_from_parsed_feed(
                        parsed_feed,
                        cutoff,
                        seen_titles,
                        seen_urls,
                        f"{source_name}（fallback Google News）",
                        context=context,
                        feed_url=fallback_url,
                        fetched_at=fetched_at,
                        retrieval_method="Google News fallback",
                    )
                    if items_found:
                        all_blocks.append(_format_items_block(f"{source_name}（fallback Google News）", items_found))
                        provenance_records.extend(
                            item["_raw_provenance"]
                            for item in items_found[:MAX_ITEMS_PER_SOURCE]
                            if item.get("_raw_provenance")
                        )
                        source_statuses.append(
                            _status_record(source_name, "Google News fallback", "fallback 成功", min(len(items_found), MAX_ITEMS_PER_SOURCE), f"官方 RSS 失敗：{exc.message}", True)
                        )
                    else:
                        status = "非都市軌道" if topic_filtered_count and not (invalid_count or blocked_count) else "被安全規則排除" if blocked_count and not invalid_count else "無文章"
                        message = f"官方 RSS 失敗：{exc.message}；fallback 無有效候選；非都市軌道 {topic_filtered_count}、無效連結 {invalid_count}、安全排除 {blocked_count}、重複 {duplicate_count}"
                        all_blocks.append(f"【RSS來源：{source_name}】（{status}）")
                        source_statuses.append(_status_record(source_name, "Google News fallback", status, 0, message, True))
                except FeedFetchError as fallback_exc:
                    all_blocks.append(f"【RSS來源：{source_name}】（{exc.status}）")
                    source_statuses.append(
                        _status_record(source_name, method, exc.status, 0, f"官方 RSS：{exc.message}；fallback：{fallback_exc.message}", True)
                    )
            else:
                all_blocks.append(f"【RSS來源：{source_name}】（{exc.status}）")
                source_statuses.append(_status_record(source_name, method, exc.status, 0, exc.message))

    raw_text = RawSearchText("\n\n".join(all_blocks), provenance_records)
    if return_status:
        return raw_text, source_statuses
    return raw_text
