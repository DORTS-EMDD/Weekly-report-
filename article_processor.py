"""Article normalization, source/region inference, candidate schema, and deduplication."""

import datetime
import difflib
import re
import time
import urllib.parse
import requests
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse, urlunparse
from email.utils import parsedate_to_datetime

from config import *
from search_queries import FORMAL_SOURCE_PROXY_LABELS

def _parse_pub_date(pub_str: str) -> str:
    if not pub_str:
        return "日期未知"
    try:
        return parsedate_to_datetime(pub_str).strftime("%Y-%m-%d")
    except Exception:
        pass
    try:
        return datetime.datetime.fromisoformat(
            pub_str.replace("Z", "+00:00")
        ).strftime("%Y-%m-%d")
    except Exception:
        return pub_str[:16]


def _is_recent(pub_str: str, cutoff: datetime.datetime) -> bool:
    if not pub_str:
        return True
    try:
        dt = parsedate_to_datetime(pub_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt > cutoff
    except Exception:
        pass
    try:
        dt = datetime.datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
        return dt > cutoff
    except Exception:
        return True


def _source_tuple(source) -> tuple[str, str]:
    return source[0], source[1]


def _host_matches(host: str, domain: str) -> bool:
    host = host.lower().strip(".")
    domain = domain.lower().strip(".")
    return host == domain or host.endswith("." + domain)


def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _normalize_source_domain(domain: str) -> str:
    host = (domain or "").strip().lower().removeprefix("www.")
    if not host:
        return ""
    aliases = {
        "news.google.com": "",
        "finance.yahoo.com": "yahoo.com",
        "uk.news.yahoo.com": "yahoo.com",
        "ca.news.yahoo.com": "yahoo.com",
        "www.gov.uk": "gov.uk",
    }
    return aliases.get(host, host)


def _extract_site_domain_from_google_news(url: str) -> str:
    try:
        query = parse_qs(urlparse(url).query).get("q", [""])[0]
    except Exception:
        return ""
    match = re.search(r"site:([^\s\)]+)", query)
    return match.group(1).lower().removeprefix("www.") if match else ""


def _is_blocked_host(host: str) -> bool:
    host = host.lower().strip(".")
    if not host:
        return False
    return any(host.endswith(suffix) for suffix in BLOCKED_DOMAINS)


def _is_domestic_taiwan_host(host: str) -> bool:
    host = host.lower().strip(".")
    if not host:
        return False
    return any(host.endswith(suffix) for suffix in DOMESTIC_EXCLUDED_DOMAINS)


def _is_allowed_host(host: str) -> bool:
    if not ALLOWED_NEWS_DOMAINS:
        return True
    return any(_host_matches(host, domain) for domain in ALLOWED_NEWS_DOMAINS)


def _is_valid_news_url(
    url: str,
    source_href: str = "",
    *,
    news_scope: str = DEFAULT_NEWS_SCOPE,
) -> tuple[bool, str]:
    if not url or not url.strip():
        return False, "空網址"
    url = url.strip()
    if url.startswith("/") or "/clev" in url.lower():
        return False, "相對網址或 Google /clev 轉址"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False, "非 http/https 網址"
    if parsed.path in ("", "/") and "news.google.com" not in parsed.netloc:
        return False, "首頁連結"

    lower_url = url.lower()
    blocked_markers = [
        "/login", "/signin", "/sign-in", "/subscribe", "subscription",
        "membership", "/member", "/account", "/advertis", "/sponsor",
        "/privacy", "/terms", "/cookie", "/jobs", "/careers",
    ]
    if any(marker in lower_url for marker in blocked_markers):
        return False, "廣告、會員或非新聞頁"

    safety_url = source_href or url
    host = _domain_from_url(safety_url)
    url_host = _domain_from_url(url)
    if any(
        candidate_host and _host_matches(candidate_host, domain)
        for candidate_host in (host, url_host)
        for domain in LOW_VALUE_EXCLUDED_HOSTS
    ):
        return False, "低價值來源或子網域"
    if _is_blocked_host(host):
        return False, "被安全規則排除"
    if _is_domestic_taiwan_host(host) and news_scope == "international":
        return False, "範圍排除"
    if not _is_allowed_host(host):
        return False, "不在來源白名單"
    return True, ""


def _contains_taiwan_reference(text: str) -> bool:
    text_lower = (text or "").casefold()
    return any(term.casefold() in text_lower for term in DOMESTIC_EXCLUDED_TERMS)


def _domestic_metro_candidate_info(text: str, source: str = "") -> dict[str, object]:
    candidate_text = f"{source} {text}".strip()
    if not _contains_taiwan_reference(candidate_text):
        return {
            "domestic_candidate": False,
            "domestic_system": "",
            "domestic_filter_reason": "非臺灣內容",
        }
    matched_systems = [
        system
        for system, terms in DOMESTIC_METRO_SYSTEM_TERMS.items()
        if _contains_any_term(candidate_text, terms)
        and _contains_any_term(candidate_text, DOMESTIC_METRO_CONTEXT_TERMS)
    ]
    if not matched_systems:
        if _contains_any_term(candidate_text, DOMESTIC_NON_METRO_TERMS):
            reason = "臺鐵、高鐵、一般鐵路、公車、航空或道路內容"
        else:
            reason = "非指定臺灣捷運／都市軌道系統"
        return {
            "domestic_candidate": False,
            "domestic_system": "",
            "domestic_filter_reason": reason,
        }
    airport_only_terms = [
        "airport people mover", "terminal people mover", "機場旅客捷運", "航廈旅客捷運",
    ]
    operational_terms = [
        "train", "rolling stock", "signalling", "signaling", "power supply", "maintenance",
        "monitoring", "system", "列車", "車輛", "號誌", "供電", "維修", "監測", "系統", "營運",
    ]
    if _contains_any_term(candidate_text, airport_only_terms) and not _contains_any_term(candidate_text, operational_terms):
        return {
            "domestic_candidate": False,
            "domestic_system": matched_systems[0],
            "domestic_filter_reason": "純 airport people mover／航空旅遊內容",
        }
    return {
        "domestic_candidate": True,
        "domestic_system": matched_systems[0],
        "domestic_filter_reason": "",
    }


def _contains_any_term(text: str, terms: list[str]) -> bool:
    text_lower = (text or "").casefold()
    for term in terms:
        term_lower = term.casefold()
        if re.fullmatch(r"[a-z0-9][a-z0-9\s/&.\-]*", term_lower):
            if re.search(rf"(?<![a-z0-9]){re.escape(term_lower)}(?![a-z0-9])", text_lower):
                return True
        elif term_lower in text_lower:
            return True
    return False


def _domain_hint_from_source_label(text: str) -> str:
    text_lower = (text or "").casefold()
    for label, domain in SOURCE_DOMAIN_HINT_BY_LABEL.items():
        if label.casefold() in text_lower:
            return domain
    return ""


def _original_source_domain(source: str = "", url: str = "", source_href: str = "", query: str = "") -> str:
    for value in (source_href, url):
        host = _normalize_source_domain(_domain_from_url(value))
        if host and host != "news.google.com":
            return host
    for value in (url, source_href, query):
        domain = _normalize_source_domain(_extract_site_domain_from_google_news(value))
        if domain and domain != "news.google.com":
            return domain
    return _normalize_source_domain(_domain_hint_from_source_label(f"{source} {query}"))


def _strict_source_domain(url: str = "", source_href: str = "", query: str = "") -> str:
    """Return only URL, source_href or explicit site: domains; never infer from display labels."""
    for value in (source_href, url):
        host = _normalize_source_domain(_domain_from_url(value))
        if host and host != "news.google.com":
            return host
    for value in (url, source_href, query):
        domain = _normalize_source_domain(_extract_site_domain_from_google_news(value))
        if domain and domain != "news.google.com":
            return domain
    return ""


def _strip_source_name_noise(text: str) -> str:
    cleaned = text or ""
    for term in SOURCE_NAME_NOISE_TERMS:
        cleaned = re.sub(re.escape(term), " ", cleaned, flags=re.IGNORECASE)
    return cleaned


def clean_source_name_for_ui(source_name: str) -> str:
    """只清理前台顯示名稱；debug 仍保留原始 source_name/method。"""
    cleaned = str(source_name or "")
    cleaned = re.sub(r"[（(]\s*fallback\s*Google\s*News\s*[）)]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"（\s*Google\s*News\s*代理\s*）", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(\s*Google\s*News\s*proxy\s*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"由\s*Google\s*News\s*代理", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Google\s*News\s*地區代理\s*[－\-:：]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Google\s*News\s*代理", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"地區代理\s*[－\-:：]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfallback\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"（\s*）|\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" －-_/|：:")
    return cleaned or str(source_name or "").strip()


def _is_query_proxy_source_label(source_name: str) -> bool:
    raw = str(source_name or "").strip()
    cleaned = clean_source_name_for_ui(raw).strip()
    raw_lower = raw.casefold()
    cleaned_lower = cleaned.casefold()
    if "google news" in raw_lower or "代理" in raw_lower:
        return True
    return any(cleaned_lower == label.casefold() for label in FORMAL_SOURCE_PROXY_LABELS)


def _candidate_region_text(candidate: dict) -> str:
    return " ".join(str(candidate.get(key, "") or "") for key in (
        "region", "title", "snippet", "url", "source_href", "source_domain", "source"
    ))


def _region_from_domain_hints(candidate: dict) -> str:
    source_url = _effective_source_url(candidate)
    hosts = [
        candidate.get("source_domain", ""),
        _domain_from_url(source_url),
        _domain_from_url(candidate.get("source_href", "")),
        _domain_from_url(candidate.get("url", "")),
        _original_source_domain(
            candidate.get("source", ""),
            candidate.get("url", ""),
            candidate.get("source_href", ""),
            "",
        ),
    ]
    for host in hosts:
        for domain, region in REGION_DOMAIN_HINTS.items():
            if host and _host_matches(host, domain):
                return region
    return ""


def _region_guess_from_candidate(candidate: dict) -> str:
    title = str(candidate.get("title", "") or "")
    snippet = str(candidate.get("snippet", "") or "")
    explicit_event_guess = _explicit_event_region_hint(f"{title} {snippet}")
    if explicit_event_guess:
        return explicit_event_guess
    for value in (title, snippet):
        text_guess = guess_region_from_text(value)
        if text_guess != "未判定":
            return text_guess

    source_guess = guess_region_from_text(candidate.get("source", ""))
    if source_guess != "未判定":
        return source_guess
    domain_guess = _region_from_domain_hints(candidate)
    if domain_guess:
        return domain_guess

    existing = str(candidate.get("region", "") or "").strip()
    query_region = str(candidate.get("query_region", "") or "").strip()
    if existing not in {"", "未判定", "國際", "國際研究"} and existing != query_region:
        return existing

    path_text = " ".join(
        urlparse(candidate.get(key, "") or "").path.replace("/", " ")
        for key in ("url", "source_href")
    )
    path_guess = guess_region_from_text(path_text)
    if path_guess != "未判定":
        return path_guess
    if query_region and query_region not in {"global", "unplanned", "domestic", "未判定", "國際", "國際研究"}:
        return query_region
    query_guess = guess_region_from_text(candidate.get("query", ""))
    return query_guess if query_guess != "未判定" else "未判定"


def _region_resolution(candidate: dict) -> tuple[str, str, str]:
    title = str(candidate.get("title", "") or "")
    snippet = str(candidate.get("snippet", "") or "")
    explicit_event_guess = _explicit_event_region_hint(f"{title} {snippet}")
    if explicit_event_guess:
        return explicit_event_guess, "title_snippet_explicit_event", f"{title} {snippet}".strip()
    for field_name, value in (("title", title), ("snippet", snippet)):
        text_guess = guess_region_from_text(value)
        if text_guess != "未判定":
            return text_guess, f"{field_name}_city_system_operator", value
    source = str(candidate.get("source", "") or "")
    source_guess = guess_region_from_text(source)
    if source_guess != "未判定":
        return source_guess, "official_operator_or_source", source
    domain_guess = _region_from_domain_hints(candidate)
    if domain_guess:
        evidence = " ".join(
            str(candidate.get(key, "") or "")
            for key in ("source_domain", "source_href", "url")
        ).strip()
        return domain_guess, "official_source_domain", evidence
    existing = str(candidate.get("region", "") or "").strip()
    query_region = str(candidate.get("query_region", "") or "").strip()
    if existing not in {"", "未判定", "國際", "國際研究"} and existing != query_region:
        return existing, "candidate_region", existing
    path_text = " ".join(
        urlparse(candidate.get(key, "") or "").path.replace("/", " ")
        for key in ("url", "source_href")
    )
    path_guess = guess_region_from_text(path_text)
    if path_guess != "未判定":
        return path_guess, "source_url_path", path_text
    if query_region and query_region not in {"global", "unplanned", "domestic", "未判定", "國際", "國際研究"}:
        return query_region, "query_region_fallback", query_region
    query_guess = guess_region_from_text(candidate.get("query", ""))
    if query_guess != "未判定":
        return query_guess, "query_text_fallback", str(candidate.get("query", "") or "")
    return "未判定", "unresolved", ""


def _canonical_candidate_region(candidate: dict) -> str:
    original_region = str(candidate.get("region", "") or "").strip()
    query_region = str(candidate.get("query_region", "") or "").strip()
    guessed, method, evidence = _region_resolution(candidate)
    region = original_region
    if guessed == "巴西":
        region = "巴西"
    elif guessed != "未判定" and (not region or region in {"未判定", "國際", "國際研究"} or region != guessed):
        region = guessed
    if region in {"Brazil", "Brasil", "São Paulo", "Sao Paulo", "聖保羅", "圣保罗"}:
        region = "巴西"
    if not region:
        region = "未判定"
    candidate["region"] = region
    candidate["resolved_region"] = region
    candidate["region_resolution_method"] = method
    candidate["region_resolution_evidence"] = evidence
    candidate["region_conflict"] = bool(
        query_region
        and query_region not in {"global", "unplanned", "domestic", "未判定", "國際", "國際研究"}
        and method not in {"query_region_fallback", "query_text_fallback"}
        and region != query_region
    )
    candidate["region_query_override"] = bool(
        query_region
        and query_region not in {"global", "unplanned", "未判定", "國際", "國際研究"}
        and method not in {"query_region_fallback", "query_text_fallback"}
        and region != query_region
    )
    candidate["country"] = normalize_country(region)
    return region


_COUNTRY_BY_REGION = {
    "臺北": "臺灣",
    "台北": "臺灣",
    "新北": "臺灣",
    "桃園": "臺灣",
    "臺中": "臺灣",
    "台中": "臺灣",
    "高雄": "臺灣",
    "臺灣": "臺灣",
    "台灣": "臺灣",
    "東京": "日本",
    "大阪": "日本",
    "日本": "日本",
    "首爾": "韓國",
    "韓國": "韓國",
    "新加坡": "新加坡",
    "香港": "香港",
    "倫敦": "英國",
    "London": "英國",
    "Manchester": "英國",
    "Manchester Piccadilly": "英國",
    "英國": "英國",
    "巴黎": "法國",
    "法國": "法國",
    "Berlin": "德國",
    "Munich": "德國",
    "柏林": "德國",
    "慕尼黑": "德國",
    "德國": "德國",
    "New York": "美國",
    "Washington": "美國",
    "Los Angeles": "美國",
    "紐約": "美國",
    "華盛頓": "美國",
    "美國": "美國",
    "Toronto": "加拿大",
    "Vancouver": "加拿大",
    "多倫多": "加拿大",
    "溫哥華": "加拿大",
    "加拿大": "加拿大",
    "Sydney": "澳洲",
    "Melbourne": "澳洲",
    "雪梨": "澳洲",
    "墨爾本": "澳洲",
    "澳洲": "澳洲",
    "Chennai": "印度",
    "印度": "印度",
    "Moscow": "俄羅斯",
    "俄羅斯": "俄羅斯",
}


def normalize_country(region: str) -> str:
    """Convert an event city or region into the formal country label."""
    value = re.sub(r"\s+", " ", str(region or "")).strip()
    if not value:
        return "未判定"
    exact = _COUNTRY_BY_REGION.get(value)
    if exact:
        return exact
    folded = value.casefold()
    for alias, country in sorted(_COUNTRY_BY_REGION.items(), key=lambda item: len(item[0]), reverse=True):
        if alias.casefold() in folded:
            return country
    guessed_region = guess_region_from_text(value)
    if guessed_region != "未判定":
        return _COUNTRY_BY_REGION.get(guessed_region, guessed_region)
    return value


_REGION_ALIASES = {
    "台北": "臺北",
    "台中": "臺中",
    "台南": "臺南",
    "台東": "臺東",
    "台湾": "臺灣",
    "台灣": "臺灣",
    "Taiwan": "臺灣",
}

_TAIWAN_SUBREGIONS = {
    "臺北", "新北", "桃園", "臺中", "臺南", "高雄",
    "基隆", "新竹", "苗栗", "彰化", "南投", "雲林", "嘉義",
    "屏東", "宜蘭", "花蓮", "臺東", "澎湖",
}


def region_matches_selected_regions(region: str, selected_regions: list[str] | tuple[str, ...]) -> bool:
    def normalize(value: str) -> str:
        cleaned = re.sub(r"\s+", "", str(value or "")).strip()
        return _REGION_ALIASES.get(cleaned, cleaned)

    normalized_region = normalize(region)
    normalized_selected = {normalize(value) for value in selected_regions or []}
    if normalized_region in normalized_selected:
        return True
    return normalized_region in _TAIWAN_SUBREGIONS and "臺灣" in normalized_selected


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\u4e00-\u9fff]+", " ", title.casefold())).strip()


def _dedupe_url(url: str) -> str:
    parsed = urlparse(url)
    clean = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=parsed.path.rstrip("/"),
        params="",
        query="",
        fragment="",
    )
    return urlunparse(clean)


def _entry_source_href(entry) -> str:
    source = entry.get("source") if hasattr(entry, "get") else None
    if isinstance(source, dict):
        return source.get("href") or source.get("url") or ""
    return ""


def _entry_pub_str(entry) -> str:
    for key in ("published", "updated", "created", "date"):
        value = entry.get(key, "")
        if value:
            return str(value)
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime.datetime.fromtimestamp(time.mktime(value), tz=datetime.timezone.utc).isoformat()
            except Exception:
                pass
    return ""


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _shorten(text: str, max_chars: int = CANDIDATE_SNIPPET_CHARS) -> str:
    text = _clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _is_article_level_url(value: str, allow_google_news: bool = False) -> bool:
    url = _clean_candidate_url(value)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if "news.google.com" in parsed.netloc.casefold():
        return allow_google_news and parsed.path not in {"", "/"}
    return parsed.path not in {"", "/"}


def _effective_source_url(candidate: dict) -> str:
    resolved_url = candidate.get("resolved_article_url") or ""
    source_href = candidate.get("source_href") or ""
    url = candidate.get("url") or ""
    if _is_article_level_url(resolved_url):
        return _clean_candidate_url(resolved_url)
    if _is_article_level_url(source_href):
        return _clean_candidate_url(source_href)
    if _is_article_level_url(url, allow_google_news=True):
        return _clean_candidate_url(url)
    # A Google News article URL is a valid fallback. Never replace it with a
    # synthesized publisher home page, which is not a source article.
    if "news.google.com" in _domain_from_url(url):
        return _clean_candidate_url(url)
    return _clean_candidate_url(source_href or url)


_GENERIC_SOURCE_DISPLAY_LABELS = {
    "資料來源未明確辨識",
    "來源未明確",
    "未提供來源名稱",
    "原始候選資料未提供來源",
}


def _formal_source_domain(candidate: dict) -> str:
    """Resolve a publisher domain for formal output without trusting a proxy host."""
    for value in (
        candidate.get("resolved_article_url", ""),
        candidate.get("source_href", ""),
        candidate.get("url", ""),
    ):
        host = _normalize_source_domain(_domain_from_url(str(value or "")))
        if host and host != "news.google.com":
            return host
        site_domain = _normalize_source_domain(_extract_site_domain_from_google_news(str(value or "")))
        if site_domain and site_domain != "news.google.com":
            return site_domain
    for value in (
        candidate.get("source_domain", ""),
        candidate.get("source_domain_normalized", ""),
        candidate.get("source_display", ""),
        candidate.get("source", ""),
    ):
        host = _normalize_source_domain(str(value or ""))
        if host and host != "news.google.com" and "." in host:
            return host
        hint = _normalize_source_domain(_domain_hint_from_source_label(str(value or "")))
        if hint and hint != "news.google.com":
            return hint
    return _normalize_source_domain(
        _original_source_domain(
            str(candidate.get("source", "") or ""),
            str(candidate.get("url", "") or ""),
            str(candidate.get("source_href", "") or ""),
            str(candidate.get("query", "") or ""),
        )
    )


def _formal_source_url(candidate: dict, domain: str = "") -> str:
    for value in (
        candidate.get("resolved_article_url", ""),
        candidate.get("source_href", ""),
        candidate.get("url", ""),
    ):
        value = _clean_candidate_url(str(value or ""))
        if _is_article_level_url(value):
            return value
    if domain:
        return f"https://{domain}/"
    return ""


def canonical_source_display_name(
    source: str = "",
    url: str = "",
    source_href: str = "",
    source_domain: str = "",
) -> str:
    domain = _normalize_source_domain(source_domain) or _normalize_source_domain(
        _domain_from_url(url) or _domain_from_url(source_href)
    )
    if not domain:
        domain = _normalize_source_domain(_domain_hint_from_source_label(source))
    for known_domain, label in SOURCE_DISPLAY_BY_DOMAIN.items():
        if domain and _host_matches(domain, known_domain):
            return label
    cleaned = clean_source_name_for_ui(source)
    if cleaned and cleaned not in _GENERIC_SOURCE_DISPLAY_LABELS and "." not in cleaned:
        return cleaned
    return domain or "資料來源未明確辨識"


def build_formal_report_source(candidate: dict) -> dict[str, str]:
    """Return the single visible source contract used by formal report output."""
    domain = _formal_source_domain(candidate)
    url = _formal_source_url(candidate, domain)
    return {
        "display_name": canonical_source_display_name(
            str(candidate.get("source_display") or candidate.get("source") or ""),
            url,
            str(candidate.get("source_href", "") or ""),
            domain,
        ),
        "display_url": url,
    }


def _extract_complete_url(text: str) -> str:
    match = re.search(r"https?://[^\s\)\]）＞>，,；;。]+", text or "")
    if not match:
        return ""
    return match.group(0).rstrip("。；;,，)")


def _extract_complete_urls(text: str) -> list[str]:
    return [
        match.group(0).rstrip("。；;,，)")
        for match in re.finditer(r"https?://[^\s\)\]）＞>，,；;。]+", text or "")
    ]


def _extract_domain_hint(text: str) -> str:
    text = text or ""
    url = _extract_complete_url(text)
    if url:
        return _domain_from_url(url)
    match = re.search(r"\b(?:[a-z0-9-]+\.)+(?:com|org|net|gov|edu|info|co|jp|kr|sg|hk|uk|fr|de|au|ca|tw)\b", text, flags=re.IGNORECASE)
    return match.group(0).lower() if match else ""


def _clean_candidate_url(value: str) -> str:
    value = (value or "").strip()
    if value.casefold() in {"http:", "https:", "http://", "https://"}:
        return ""
    url = _extract_complete_url(value)
    if url:
        return url
    domain = _extract_domain_hint(value)
    return domain or value


def _quality_rank(quality: str) -> int:
    return {"A": 0, "B": 1, "C": 2}.get((quality or "B").upper(), 1)


def _source_tier_rank(tier: str) -> int:
    return {
        "A_official": 0,
        "B_professional": 1,
        "C_media": 2,
        "D_proxy_low_value": 3,
    }.get(tier or "C_media", 2)


def classify_source_quality(source: str, url: str, source_href: str = "") -> tuple[str, str]:
    strict_host = _strict_source_domain(url, source_href)
    label_host = _domain_hint_from_source_label(source)
    host = strict_host or label_host
    text = f"{source} {url} {source_href}".casefold()

    if host and any(_host_matches(host, domain) for domain in PORTAL_REPOST_DOMAINS | PORTAL_SOCIAL_LOW_VALUE_DOMAINS):
        return "C", "入口、轉載或社群平台"
    if strict_host and any(_host_matches(strict_host, domain) for domain in SOURCE_QUALITY_A_DOMAINS):
        return "A", "官方/營運機構/政府交通機關/專業鐵道媒體"
    if host and any(_host_matches(host, domain) for domain in SOURCE_QUALITY_C_DOMAINS):
        return "C", "轉載、旅遊或低信度網站"
    if any(term.casefold() in text for term in LOW_QUALITY_CONTENT_TERMS):
        return "C", "旅遊、SEO 或內容農場線索"
    return "B", "一般新聞媒體或未分級來源"


def classify_source_tier(source: str, url: str, source_href: str = "") -> tuple[str, str]:
    strict_host = _strict_source_domain(url, source_href)
    label_host = _domain_hint_from_source_label(source)
    host = strict_host or label_host
    text = f"{source} {url} {source_href}".casefold()
    path_lower = urlparse(url or "").path.casefold()

    if host and any(_host_matches(host, domain) for domain in LOW_VALUE_EXCLUDED_HOSTS):
        return "D_proxy_low_value", "低價值來源或子網域"
    if host and any(_host_matches(host, domain) for domain in PORTAL_SOCIAL_LOW_VALUE_DOMAINS):
        return "D_proxy_low_value", "入口、轉載或社群平台"
    if any(marker in path_lower for marker in LOW_INFORMATION_PATH_MARKERS):
        return "D_proxy_low_value", "入口頁、查詢頁、路線頁、PDF 或低資訊頁"
    if any(term.casefold() in text for term in LOW_INFORMATION_PAGE_TERMS):
        return "D_proxy_low_value", "入口頁、分類頁或低資訊內容"
    if host and any(_host_matches(host, domain) for domain in PORTAL_REPOST_DOMAINS):
        return "C_media", "一般入口或轉載媒體"
    if strict_host and any(_host_matches(strict_host, domain) for domain in SOURCE_TIER_OFFICIAL_DOMAINS):
        return "A_official", "官方公告、政府交通主管機關或營運機構"
    if host and any(_host_matches(host, domain) for domain in SOURCE_TIER_PROFESSIONAL_DOMAINS):
        return "B_professional", "專業鐵道或大眾運輸媒體"
    if host and any(_host_matches(host, domain) for domain in SOURCE_QUALITY_C_DOMAINS):
        return "C_media", "一般媒體、轉載或入口媒體"
    if "news.google.com" in _domain_from_url(url) and not host:
        return "D_proxy_low_value", "Google News 代理且原始來源未明確辨識"
    return "C_media", "一般新聞媒體或未分級來源"


def source_label_for_report(source: str, url: str, source_href: str = "", tier: str = "") -> str:
    strict_host = _strict_source_domain(url, source_href)
    label_host = _domain_hint_from_source_label(source)
    display_host = strict_host or (
        label_host
        if label_host and any(_host_matches(label_host, domain) for domain in SOURCE_TIER_PROFESSIONAL_DOMAINS)
        else ""
    )
    for domain, label in SOURCE_DISPLAY_BY_DOMAIN.items():
        if display_host and _host_matches(display_host, domain):
            return label

    source_clean = clean_source_name_for_ui(source)
    if _is_query_proxy_source_label(source):
        if display_host and display_host != "news.google.com":
            return display_host
        return "資料來源未明確辨識"

    if source_clean and source_clean not in {"RSS", "ddgs", "Google News"}:
        if tier == "A_official" and "官方" not in source_clean:
            return f"{source_clean} 官方公告"
        return source_clean
    if display_host and display_host != "news.google.com":
        return display_host
    if "news.google.com" in _domain_from_url(url):
        return "資料來源未明確辨識"
    return "資料來源未明確辨識"


def source_verb_for_report(tier: str, label: str) -> str:
    if tier == "A_official" or "官方" in (label or ""):
        return "公告"
    if tier == "B_professional":
        return "報導"
    return "報導"


def _region_term_matches(text_lower: str, term: str) -> bool:
    term_lower = (term or "").casefold()
    if not term_lower:
        return False
    if re.fullmatch(r"[a-z0-9.\-]+", term_lower) and len(term_lower.replace(".", "").replace("-", "")) <= 4:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(term_lower)}(?![a-z0-9])", text_lower))
    return term_lower in text_lower


def _explicit_event_region_hint(text: str) -> str:
    text_lower = (text or "").casefold()
    # Ambiguous operator names are paired with an event city before generic
    # query or publisher hints are considered.
    explicit_hints = [
        ("英國", ["translink northern ireland", "translink ni", "belfast", "northern ireland", "manchester", "manchester piccadilly", "metrolink"]),
        ("美國", ["austin transit partnership", "austin light rail", "wmata", "washington metro", "new york subway", "nyct", "mta"]),
        ("加拿大", ["ttc", "toronto subway", "toronto", "translink vancouver", "vancouver translink", "vancouver", "skytrain"]),
        ("德國", ["bvg", "berlin", "berlin tram"]),
        ("印度", ["chennai", "chennai metro", "chennai metro rail", "cmrl"]),
    ]
    for region, terms in explicit_hints:
        if any(_region_term_matches(text_lower, term) for term in terms):
            return region
    return ""


def _event_region_hint_from_text(text: str) -> str:
    text_lower = (text or "").casefold()
    for region, terms in EVENT_REGION_PRIORITY_HINTS:
        if any(_region_term_matches(text_lower, term) for term in terms):
            return region
    return ""


def guess_region_from_text(text: str) -> str:
    text_lower = (text or "").casefold()
    priority_hint = _event_region_hint_from_text(text)
    if priority_hint:
        return priority_hint
    aliases = {
        "日本": ["japan", "tokyo", "osaka", "日本", "東京", "大阪"],
        "韓國": ["korea", "seoul", "韓國", "韩国", "서울"],
        "新加坡": ["singapore", "lta", "smrt", "新加坡"],
        "香港": ["hong kong", "mtr.com.hk", "香港", "港鐵", "港铁"],
        "臺北": ["taipei metro", "taipei mrt", "trtc", "臺北捷運", "台北捷運", "北捷"],
        "新北": ["new taipei metro", "new taipei light rail", "新北捷運", "新北輕軌"],
        "桃園": ["taoyuan metro", "taoyuan mrt", "taoyuan airport mrt", "桃園捷運", "桃園機場捷運", "桃捷"],
        "臺中": ["taichung metro", "taichung mrt", "臺中捷運", "台中捷運", "中捷"],
        "高雄": ["kaohsiung metro", "kaohsiung mrt", "krtc", "高雄捷運", "高捷"],
        "臺灣": ["taiwan metro", "taiwan mrt", "台灣捷運", "臺灣捷運", "臺灣都市軌道", "台灣都市軌道"],
        "澳洲": ["australia", "sydney", "melbourne", "brisbane", "澳洲"],
        "英國": ["united kingdom", "uk", "london", "tfl", "underground", "manchester", "metrolink", "英國", "英国", "倫敦"],
        "法國": ["france", "paris", "ratp", "法國", "法国", "巴黎"],
        "德國": ["germany", "berlin", "munich", "hamburg", "u-bahn", "德國", "德国"],
        "美國": [
            "united states", "new york", "nyc", "manhattan", "washington", "chicago",
            "seattle", "federal way", "star lake", "sound transit", "link light rail",
            "wmata", "cta", "mta.info", "soundtransit.org", "美國", "美国",
        ],
        "加拿大": [
            "canada", "toronto", "vancouver", "yaletown-roundhouse",
            "yaletown–roundhouse", "ttc", "skytrain", "加拿大",
        ],
        "西班牙": ["spain", "madrid", "barcelona", "西班牙"],
        "巴西": ["brazil", "brasil", "são paulo", "sao paulo", "sao-paulo", "saopaulo", "巴西", "聖保羅", "圣保罗"],
        "印度": ["india", "mumbai", "delhi metro", "chennai", "chennai metro", "cmrl", "印度", "孟買", "孟买"],
        "荷蘭": ["netherlands", "amsterdam", "rotterdam", "荷蘭", "荷兰"],
        "瑞士": ["switzerland", "zurich", "lausanne", "瑞士"],
        "義大利": ["italy", "milan", "rome", "turin", "義大利", "意大利"],
        "瑞典": ["sweden", "stockholm", "gothenburg", "瑞典"],
        "奧地利": ["austria", "vienna", "wien", "奧地利", "奥地利"],
        "丹麥": ["denmark", "copenhagen", "丹麥", "丹麦"],
        "挪威": ["norway", "oslo", "挪威"],
    }
    for region, terms in aliases.items():
        if any(_region_term_matches(text_lower, term) for term in terms):
            return region
    return "未判定"


def _candidate_date_obj(date_text: str) -> datetime.date | None:
    text = (date_text or "").strip()
    if not text or "未知" in text:
        return None
    date_match = re.search(r"(?<!\d)(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?!\d)", text)
    if date_match:
        try:
            return datetime.date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
        except ValueError:
            return None
    try:
        return parsedate_to_datetime(text).date()
    except Exception:
        pass
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        pass
    for pattern in (r"(\d{4})年(\d{1,2})月(\d{1,2})日",):
        match = re.search(pattern, text)
        if match:
            try:
                return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except Exception:
                return None
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            return datetime.date(int(year_match.group(1)), 1, 1)
        except Exception:
            return None
    return None


def _date_from_url_path(*urls: str) -> datetime.date | None:
    """Extract an explicit calendar date from an article URL path."""
    for raw_url in urls:
        if not raw_url:
            continue
        path = unquote(urlparse(raw_url).path or "")
        for pattern in (
            r"(?<!\d)(20\d{2})/(\d{1,2})/(\d{1,2})(?!\d)",
            r"(?<!\d)(20\d{2})-(\d{1,2})-(\d{1,2})(?!\d)",
        ):
            match = re.search(pattern, path)
            if not match:
                continue
            try:
                return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                continue
    return None


def _date_sort_key(candidate: dict) -> int:
    date_obj = _candidate_date_obj(candidate.get("date", ""))
    return date_obj.toordinal() if date_obj else 0


def _make_news_candidate(
    title: str,
    date: str,
    source: str,
    url: str,
    snippet: str,
    query: str,
    region: str,
    source_type: str,
    source_href: str = "",
    *, query_metadata: dict | None = None, search_family_resolver=None,
    search_language_resolver=None,
) -> dict:
    normalized_date = _clean_text(date)
    if not _candidate_date_obj(normalized_date):
        url_date = _date_from_url_path(source_href, url)
        if url_date:
            normalized_date = url_date.isoformat()
    raw_domain = _domain_from_url(source_href or url) or _extract_site_domain_from_google_news(url) or _domain_hint_from_source_label(source)
    original_domain = _normalize_source_domain(_original_source_domain(source, url, source_href, query))
    quality, quality_reason = classify_source_quality(source, url, source_href)
    source_tier, source_tier_reason = classify_source_tier(source, url, source_href)
    source_display = source_label_for_report(source, url, source_href, source_tier)
    source_verb = source_verb_for_report(source_tier, source_display)
    query_metadata = query_metadata or {}
    search_family = query_metadata.get("family") or search_family_resolver(query or source)
    search_language = query_metadata.get("lang") or search_language_resolver(query or source)
    candidate = {
        "title": _clean_text(title),
        "date": normalized_date or "日期未知",
        "source": _clean_text(source) or (_domain_from_url(source_href or url) or "未判定來源"),
        "url": (url or "").strip(),
        "snippet": _shorten(snippet, REPORT_SNIPPET_CHARS),
        "query": _clean_text(query),
        "region": region if region and region != "未判定" else "未判定",
        "source_type": source_type,
        "source_href": (source_href or "").strip(),
        "source_quality": quality,
        "source_quality_reason": quality_reason,
        "source_tier": source_tier,
        "source_tier_reason": source_tier_reason,
        "source_display": source_display,
        "source_verb": source_verb,
        "source_domain_raw": raw_domain,
        "source_domain": original_domain or _normalize_source_domain(_domain_from_url(source_href or url)),
        "source_domain_normalized": original_domain or _normalize_source_domain(_domain_from_url(source_href or url)),
        "search_family": search_family,
        "search_query": _clean_text(query),
        "search_language": search_language,
        "query_region": query_metadata.get("query_region", ""),
    }
    proxy_url = next(
        (
            value.strip()
            for value in (url, source_href)
            if "news.google.com" in _domain_from_url(value)
        ),
        "",
    )
    if proxy_url:
        candidate["source_proxy_url"] = proxy_url
    if query_metadata.get("query_region"):
        candidate["query_region"] = query_metadata["query_region"]
    if query_metadata.get("selected_regions"):
        candidate["query_selected_regions"] = list(query_metadata["selected_regions"])
    if query_metadata.get("region_group"):
        candidate["query_region_group"] = list(query_metadata["region_group"])
    if query_metadata.get("date_bucket"):
        candidate["date_bucket"] = query_metadata["date_bucket"]
    if query_metadata.get("annual_bucket_families"):
        candidate["annual_bucket_families"] = list(query_metadata["annual_bucket_families"])
    if query_metadata.get("topic"):
        candidate["forward_topic"] = query_metadata["topic"]
    retrieval_lane = str(query_metadata.get("retrieval_lane", "") or "").strip()
    if retrieval_lane:
        candidate["retrieval_lane"] = retrieval_lane
        candidate["retrieval_lanes"] = [retrieval_lane]
        candidate["retrieval_provenance"] = [{
            "retrieval_lane": retrieval_lane,
            "query_family": search_family,
            "query": _clean_text(query),
            "source_domain": raw_domain,
            "timelimit": query_metadata.get("timelimit", ""),
        }]
    if query_metadata.get("forward_subtopic"):
        candidate["forward_subtopic"] = query_metadata["forward_subtopic"]
    candidate["region"] = _region_guess_from_candidate(candidate)
    return candidate


def parse_rss_candidates(raw_rss: str, candidate_factory=_make_news_candidate) -> list[dict]:
    candidates: list[dict] = []
    for block in re.split(r"(?=^【RSS來源：)", raw_rss or "", flags=re.MULTILINE):
        block = block.strip()
        if not block.startswith("【RSS來源："):
            continue
        header, *body_lines = block.splitlines()
        source_match = re.match(r"^【RSS來源：(.+?)(?:（|】)", header)
        source_name = source_match.group(1).strip() if source_match else "RSS"
        source_type = "Google News 代理" if "Google News" in source_name or "代理" in source_name else "官方 RSS"
        current: dict[str, str] = {}

        def _flush_current():
            if current.get("title") and current.get("url"):
                candidates.append(candidate_factory(
                    title=current.get("title", ""),
                    date=current.get("date", ""),
                    source=source_name,
                    url=current.get("url", ""),
                    snippet=current.get("snippet", ""),
                    query=source_name,
                    region=guess_region_from_text(f"{source_name} {current.get('title', '')}"),
                    source_type=source_type,
                    source_href=current.get("source_href", ""),
                ))

        for raw_line in body_lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("日期："):
                _flush_current()
                current = {"date": line.split("：", 1)[1].strip()}
            elif line.startswith("標題："):
                current["title"] = line.split("：", 1)[1].strip()
            elif line.startswith("摘要："):
                current["snippet"] = line.split("：", 1)[1].strip()
            elif line.startswith("連結："):
                link_text = line.split("：", 1)[1].strip()
                link_parts = link_text.split("原始來源：", 1)
                current["url"] = link_parts[0].strip()
                if len(link_parts) > 1:
                    current["source_href"] = link_parts[1].strip()
            elif line.startswith("原始來源："):
                current["source_href"] = line.split("：", 1)[1].strip()
        _flush_current()
    return candidates


def parse_ddg_candidates(raw_ddg: str, candidate_factory=_make_news_candidate) -> list[dict]:
    candidates: list[dict] = []
    for block in re.split(r"(?=^【搜尋\s+\d+)", raw_ddg or "", flags=re.MULTILINE):
        block = block.strip()
        if not block.startswith("【搜尋"):
            continue
        header, *body_lines = block.splitlines()
        query_match = re.match(r"^【搜尋\s+\d+（[^）]+）】(.+?)(?:（有效候選|\s*$)", header)
        query = query_match.group(1).strip() if query_match else header
        current: dict[str, str] = {}

        def _flush_current():
            if current.get("title") and current.get("url"):
                source_domain = _domain_from_url(current.get("url", ""))
                candidates.append(candidate_factory(
                    title=current.get("title", ""),
                    date=current.get("date", ""),
                    source=source_domain or "ddgs",
                    url=current.get("url", ""),
                    snippet=current.get("snippet", ""),
                    query=query,
                    region=guess_region_from_text(f"{query} {current.get('title', '')} {current.get('snippet', '')}"),
                    source_type="ddgs",
                ))

        for raw_line in body_lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("日期："):
                _flush_current()
                current = {"date": line.split("：", 1)[1].strip()}
            elif line.startswith("標題："):
                current["title"] = line.split("：", 1)[1].strip()
            elif line.startswith("摘要："):
                current["snippet"] = line.split("：", 1)[1].strip()
            elif line.startswith("連結："):
                current["url"] = line.split("：", 1)[1].strip()
        _flush_current()
    return candidates


def _dedupe_entity_tokens(candidate: dict) -> set[str]:
    text = " ".join(str(candidate.get(key, "") or "") for key in ("title", "url", "source_href"))
    text = urllib.parse.unquote(text).casefold()
    tokens: set[str] = set()
    patterns = [
        r"\b(?:line|route|service|tram|lrt|mrt|u-bahn|u)\s*[-#]?\s*[a-z0-9]{1,6}\b",
        r"\b[a-z]\s*line\b",
        r"\bline\s*[a-z0-9]{1,6}\b",
        r"\broute\s*[a-z0-9]{1,6}\b",
        r"\b(?:station|stop|depot)\s+[a-z0-9][a-z0-9\- ]{1,40}\b",
        r"\b[a-z0-9][a-z0-9\- ]{1,40}\s+(?:station|stop|depot)\b",
        r"[a-z0-9一二三四五六七八九十東西南北中環港島觀塘荃灣屯馬將軍澳迪士尼]{1,12}[線綫]",
        r"[a-z0-9一二三四五六七八九十東西南北中環港島觀塘荃灣屯馬將軍澳迪士尼]{1,12}[站]",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            token = re.sub(r"\s+", " ", match if isinstance(match, str) else " ".join(match)).strip()
            if len(token) >= 2:
                tokens.add(token)
    return tokens


def _dedupe_route_line_tokens(candidate: dict) -> set[str]:
    text = " ".join(str(candidate.get(key, "") or "") for key in ("title", "url", "source_href"))
    text = urllib.parse.unquote(text).casefold().replace("_", "-")
    tokens: set[str] = set()
    patterns = [
        r"\b(?:line|route|service|tram|lrt|mrt|u-bahn|u)\s*[-#]?\s*[a-z0-9]{1,6}\b",
        r"\b(?:line|route|service|tram|lrt|mrt|u-bahn|u)[-/][a-z0-9]{1,6}\b",
        r"\b[a-z]\s*line\b",
        r"\bline\s*[a-z0-9]{1,6}\b",
        r"\broute\s*[a-z0-9]{1,6}\b",
        r"[a-z0-9一二三四五六七八九十東西南北中環港島觀塘荃灣屯馬將軍澳迪士尼]{1,12}[線綫]",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            token = re.sub(r"[\s/_]+", "-", match if isinstance(match, str) else " ".join(match)).strip("-")
            if len(token) >= 2:
                tokens.add(token)
    return tokens


def _dedupe_numbered_line_tokens(candidate: dict) -> set[str]:
    text = " ".join(str(candidate.get(key, "") or "") for key in ("title", "url", "source_href"))
    text = urllib.parse.unquote(text).casefold().replace("_", "-")
    return {
        re.sub(r"\s+", "-", match).strip("-")
        for match in re.findall(r"\bline\s*[-#]?\s*\d{1,6}\b", text)
    }


def _dedupe_titles_conflict_on_entities(candidate: dict, existing: dict) -> bool:
    left_region = candidate.get("region", "")
    right_region = existing.get("region", "")
    if left_region and right_region and left_region != right_region:
        return True
    left_lines = _dedupe_route_line_tokens(candidate)
    right_lines = _dedupe_route_line_tokens(existing)
    if left_lines and right_lines and left_lines.isdisjoint(right_lines):
        return True
    left_numbered_lines = _dedupe_numbered_line_tokens(candidate)
    right_numbered_lines = _dedupe_numbered_line_tokens(existing)
    if left_numbered_lines and right_numbered_lines and left_numbered_lines.isdisjoint(right_numbered_lines):
        return True
    left_tokens = _dedupe_entity_tokens(candidate)
    right_tokens = _dedupe_entity_tokens(existing)
    if left_tokens and right_tokens and left_tokens.isdisjoint(right_tokens):
        return True
    left_date = _candidate_date_obj(candidate.get("date", ""))
    right_date = _candidate_date_obj(existing.get("date", ""))
    if left_date and right_date and abs((left_date - right_date).days) > 7:
        return True
    return False


def _is_similar_title_duplicate(candidate: dict, existing: dict, threshold: float) -> bool:
    candidate_key = _normalize_title(candidate.get("title", ""))
    existing_key = _normalize_title(existing.get("title", ""))
    if not candidate_key or not existing_key:
        return False
    similarity = difflib.SequenceMatcher(None, candidate_key, existing_key).ratio()
    if similarity < threshold:
        return False
    return not _dedupe_titles_conflict_on_entities(candidate, existing)


_SAME_EVENT_ENTITY_STOPWORDS = {
    "after",
    "announced",
    "appointed",
    "city",
    "collision",
    "company",
    "contract",
    "design",
    "driver",
    "fire",
    "for",
    "hurt",
    "injured",
    "line",
    "metro",
    "new",
    "passengers",
    "selected",
    "several",
    "station",
    "study",
    "support",
    "tram",
    "upgrade",
    "wins",
}

_SAME_EVENT_TOPIC_TERMS = {
    "collision": ("collision", "accident", "unfall", "crash", "derailment"),
    "fire": ("fire", "brand", "feuer"),
    "upgrade": ("upgrade", "modernisation", "modernization", "renewal", "更新"),
    "study": ("study", "feasibility", "research", "studie"),
    "contract": ("contract", "procurement", "tender", "selected", "appointed"),
    "deployment": ("deploy", "deployment", "install", "installation", "einführung"),
    "testing": ("test", "trial", "pilot", "validation", "versuch"),
}


def _same_event_text(candidate: dict) -> str:
    return urllib.parse.unquote(
        " ".join(str(candidate.get(key, "") or "") for key in ("title", "snippet"))
    ).casefold()


def _same_event_route_tokens(candidate: dict) -> set[str]:
    text = _same_event_text(candidate).replace("_", "-")
    tokens: set[str] = set()
    for pattern in (
        r"\b[a-z][a-z0-9-]{2,}\s+line\b",
        r"\bline\s*[-#]?\s*[a-z0-9]{1,6}\b",
    ):
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            token = re.sub(r"\s+", "-", match).strip("-")
            if token not in {"metro-line", "red-line", "blue-line", "green-line"}:
                tokens.add(token)
    return tokens


def _same_event_named_entities(candidate: dict) -> set[str]:
    raw_text = " ".join(str(candidate.get(key, "") or "") for key in ("title", "snippet"))
    entities: set[str] = set()
    for match in re.findall(r"\b[A-Z][A-Za-zÀ-ÖØ-öø-ÿ]{2,}\b", raw_text):
        token = match.casefold()
        if token not in _SAME_EVENT_ENTITY_STOPWORDS and not token.isdigit():
            entities.add(token)
    return entities


def _same_event_topic_term_present(text: str, term: str) -> bool:
    if any(ord(character) > 127 for character in term) or len(term) >= 5:
        return term in text
    pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _same_event_topics(candidate: dict) -> set[str]:
    text = _same_event_text(candidate)
    return {
        topic
        for topic, terms in _SAME_EVENT_TOPIC_TERMS.items()
        if any(_same_event_topic_term_present(text, term) for term in terms)
    }


def _is_same_event_duplicate(candidate: dict, existing: dict, max_days: int = 3) -> bool:
    left_date = _candidate_date_obj(candidate.get("date", ""))
    right_date = _candidate_date_obj(existing.get("date", ""))
    if not left_date or not right_date or abs((left_date - right_date).days) > max_days:
        return False
    left_region = candidate.get("region", "")
    right_region = existing.get("region", "")
    if left_region and right_region and left_region != right_region:
        return False
    left_routes = _same_event_route_tokens(candidate)
    right_routes = _same_event_route_tokens(existing)
    if left_routes and right_routes and left_routes.isdisjoint(right_routes):
        return False
    if not _same_event_named_entities(candidate) & _same_event_named_entities(existing):
        return False
    if not _same_event_topics(candidate) & _same_event_topics(existing):
        return False
    return True


def _merge_retrieval_provenance(existing: dict, duplicate: dict) -> bool:
    existing_lanes = list(existing.get("retrieval_lanes") or ([existing.get("retrieval_lane")] if existing.get("retrieval_lane") else []))
    duplicate_lanes = list(duplicate.get("retrieval_lanes") or ([duplicate.get("retrieval_lane")] if duplicate.get("retrieval_lane") else []))
    before_lanes = set(existing_lanes)
    for lane in duplicate_lanes:
        if lane and lane not in existing_lanes:
            existing_lanes.append(lane)
    if existing_lanes:
        existing["retrieval_lane"] = existing_lanes[0]
        existing["retrieval_lanes"] = existing_lanes
    existing_provenance = list(existing.get("retrieval_provenance") or [])
    duplicate_provenance = list(duplicate.get("retrieval_provenance") or [])
    seen_provenance = {
        (
            row.get("retrieval_lane", ""),
            row.get("query", ""),
            row.get("source_domain", ""),
        )
        for row in existing_provenance
        if isinstance(row, dict)
    }
    for row in duplicate_provenance:
        if not isinstance(row, dict):
            continue
        signature = (
            row.get("retrieval_lane", ""),
            row.get("query", ""),
            row.get("source_domain", ""),
        )
        if signature not in seen_provenance:
            existing_provenance.append(row)
            seen_provenance.add(signature)
    if existing_provenance:
        existing["retrieval_provenance"] = existing_provenance
    return len(existing_lanes) > 1 and len(before_lanes) < 2


def dedupe_candidates(candidates: list[dict], lookback_days: int) -> tuple[list[dict], dict[str, int]]:
    stats = {
        "URL 重複": 0,
        "標題正規化重複": 0,
        "標題相似重複": 0,
        "同事件重複": 0,
        "multi_lane_candidates": 0,
    }
    seen_urls: set[str] = set()
    seen_title_keys: set[str] = set()
    title_entries: list[dict] = []
    deduped: list[dict] = []
    similarity_threshold = 0.84 if int(lookback_days) in ADVANCED_LOOKBACK_OPTIONS else 0.90

    sorted_candidates = sorted(
        candidates,
        key=lambda item: (
            _source_tier_rank(item.get("source_tier", "C_media")),
            _quality_rank(item.get("source_quality", "B")),
            0 if item.get("source_type") in {"官方 RSS", "Google News 代理"} else 1,
            -_date_sort_key(item),
        ),
    )

    for candidate in sorted_candidates:
        url_key = _dedupe_url(candidate.get("url", ""))
        title_key = _normalize_title(candidate.get("title", ""))
        if url_key and url_key in seen_urls:
            existing = next((item for item in deduped if _dedupe_url(item.get("url", "")) == url_key), None)
            if existing and _merge_retrieval_provenance(existing, candidate):
                stats["multi_lane_candidates"] += 1
            stats["URL 重複"] += 1
            continue
        if title_key and title_key in seen_title_keys:
            existing = next((item for item in title_entries if _normalize_title(item.get("title", "")) == title_key), None)
            if existing and _merge_retrieval_provenance(existing, candidate):
                stats["multi_lane_candidates"] += 1
            stats["標題正規化重複"] += 1
            continue
        similar_existing = next(
            (
                existing
                for existing in title_entries
                if _is_similar_title_duplicate(candidate, existing, similarity_threshold)
            ),
            None,
        )
        if title_key and similar_existing:
            if _merge_retrieval_provenance(similar_existing, candidate):
                stats["multi_lane_candidates"] += 1
            stats["標題相似重複"] += 1
            continue
        same_event_existing = next(
            (existing for existing in deduped if _is_same_event_duplicate(candidate, existing)),
            None,
        )
        if same_event_existing:
            if _merge_retrieval_provenance(same_event_existing, candidate):
                stats["multi_lane_candidates"] += 1
            stats["同事件重複"] += 1
            continue
        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_title_keys.add(title_key)
            title_entries.append(candidate)
        deduped.append(candidate)
    return deduped, stats



def _canonical_url_from_html(html: str, base_url: str) -> str:
    for pattern in (
        r'<link[^>]+rel=["\'][^"\']*canonical[^"\']*["\'][^>]+href=["\']([^"\']+)',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\'][^"\']*canonical[^"\']*["\']',
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:url["\']',
    ):
        match = re.search(pattern, html or "", flags=re.IGNORECASE)
        if match:
            return urllib.parse.urljoin(base_url, unescape(match.group(1)).strip())
    return ""


def _resolve_google_news_article_url(candidate: dict, session: requests.Session) -> str:
    original_url = _clean_candidate_url(candidate.get("url", ""))
    if "news.google.com" not in _domain_from_url(original_url):
        return original_url if _is_article_level_url(original_url) else ""
    existing = _clean_candidate_url(candidate.get("resolved_article_url", ""))
    if _is_article_level_url(existing):
        return existing
    started = time.perf_counter()
    candidate["google_news_original_url"] = original_url
    try:
        response = session.get(
            original_url,
            timeout=PREFETCH_TIMEOUT_SECONDS,
            headers={"Accept": "text/html,application/xhtml+xml,*/*"},
            allow_redirects=True,
        )
        candidates = [getattr(response, "url", "")]
        for hop in getattr(response, "history", []) or []:
            candidates.append(getattr(hop, "headers", {}).get("Location", ""))
            candidates.append(getattr(hop, "url", ""))
        candidates.append(_canonical_url_from_html(getattr(response, "text", ""), getattr(response, "url", original_url)))
        for value in candidates:
            resolved = _clean_candidate_url(value)
            if _is_article_level_url(resolved) and "news.google.com" not in _domain_from_url(resolved):
                candidate["resolved_article_url"] = resolved
                candidate["google_news_resolution_status"] = "resolved"
                candidate["google_news_resolution_error"] = ""
                candidate["google_news_resolution_elapsed_seconds"] = round(time.perf_counter() - started, 3)
                candidate["_resolved_article_html"] = getattr(response, "text", "")
                candidate["_resolved_article_content_type"] = getattr(response, "headers", {}).get("Content-Type", "")
                return resolved
        candidate["google_news_resolution_status"] = "unresolved_keep_google_news_url"
        candidate["google_news_resolution_error"] = "no_article_level_redirect_or_canonical"
    except Exception as exc:
        candidate["google_news_resolution_status"] = "unresolved_keep_google_news_url"
        candidate["google_news_resolution_error"] = str(exc)[:180]
    candidate["google_news_resolution_elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return ""


def _prefetch_url_for_candidate(candidate: dict, session: requests.Session | None = None) -> str:
    if session is not None and "news.google.com" in _domain_from_url(candidate.get("url", "")):
        _resolve_google_news_article_url(candidate, session)
    for raw_url in (candidate.get("resolved_article_url", ""), candidate.get("source_href", ""), candidate.get("url", "")):
        url = _clean_candidate_url(raw_url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        if "news.google.com" in parsed.netloc.casefold():
            continue
        if parsed.path in {"", "/"}:
            continue
        return url
    return ""


def _extract_prefetch_text(html: str) -> str:
    html = (html or "")[: PREFETCH_MAX_CHARS * 4]
    pieces: list[str] = []
    for pattern in (
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\']',
        r"<title[^>]*>(.*?)</title>",
    ):
        pieces.extend(re.findall(pattern, html, flags=re.IGNORECASE | re.DOTALL))
    cleaned_html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", cleaned_html)
    pieces.extend(paragraphs[:10])
    text = " ".join(_clean_text(unescape(piece)) for piece in pieces)
    return _shorten(text, PREFETCH_MAX_CHARS)


def _invalidate_candidate_selection_caches(candidate: dict) -> None:
    for key in (
        "_selection_text_cache", "_selection_text_fingerprint", "_score_cache",
        "_score_cache_fingerprint", "_analysis_cache", "_analysis_cache_fingerprint",
    ):
        candidate.pop(key, None)


def _apply_prefetch_evidence(
    candidate: dict,
    text: str,
    *,
    method: str,
    content_source: str,
    resolved_url: str = "",
) -> int:
    text = _shorten(_clean_text(text), PREFETCH_MAX_CHARS)
    if len(text) < 120:
        return 0
    if resolved_url:
        candidate["resolved_article_url"] = resolved_url
    candidate["prefetched_text_snippet"] = _shorten(text, REPORT_SNIPPET_CHARS)
    candidate["snippet"] = _shorten(
        f"{candidate.get('snippet', '')} {text}",
        REPORT_SNIPPET_CHARS,
    )
    candidate["enrichment_method"] = method
    candidate["enriched_content_source"] = content_source
    candidate["enriched_snippet_chars"] = len(text)
    candidate["enrichment_failure_reason"] = ""
    _invalidate_candidate_selection_caches(candidate)
    return len(text)


def _source_domain_followup_url(candidate: dict) -> str:
    title = _clean_text(str(candidate.get("title", "") or ""))
    if not title:
        return ""
    for raw_value in (candidate.get("source_href", ""), candidate.get("source_domain", "")):
        raw_value = str(raw_value or "").strip()
        if not raw_value:
            continue
        base_url = raw_value if "://" in raw_value else f"https://{raw_value}"
        host = _domain_from_url(base_url)
        if not host or "news.google.com" in host:
            continue
        return f"https://{host}/search/?q={urllib.parse.quote_plus(title)}"
    return ""


def _source_article_link_from_search(html: str, base_url: str, candidate: dict) -> str:
    source_host = _domain_from_url(base_url)
    title_tokens = {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9\u3400-\u9fff]{4,}", str(candidate.get("title", "") or ""))
    }
    if not source_host or len(title_tokens) < 2:
        return ""
    matches: list[tuple[int, str]] = []
    for match in re.finditer(
        r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    ):
        link = urllib.parse.urljoin(base_url, unescape(match.group(1)).strip())
        if not _is_article_level_url(link) or not _host_matches(_domain_from_url(link), source_host):
            continue
        anchor_text = re.sub(r"<[^>]+>", " ", unescape(match.group(2)))
        link_text = f"{anchor_text} {link}".casefold()
        overlap = sum(1 for token in title_tokens if token in link_text)
        if overlap >= 2:
            matches.append((overlap, link))
    if not matches:
        return ""
    matches.sort(key=lambda item: (-item[0], len(item[1])))
    return matches[0][1]


def _prefetch_from_source_domain(candidate: dict, session: requests.Session) -> dict:
    lookup_url = _source_domain_followup_url(candidate)
    if not lookup_url:
        return {"reason": "no_known_source_domain"}
    try:
        lookup_response = session.get(
            lookup_url,
            timeout=PREFETCH_TIMEOUT_SECONDS,
            headers={"Accept": "text/html,application/xhtml+xml,text/plain,*/*"},
        )
        if getattr(lookup_response, "status_code", 200) >= 400:
            return {"reason": f"source_lookup_http_{lookup_response.status_code}"}
        lookup_html = getattr(lookup_response, "text", "") or ""
        article_url = _source_article_link_from_search(lookup_html, lookup_url, candidate)
        if article_url:
            article_response = session.get(
                article_url,
                timeout=PREFETCH_TIMEOUT_SECONDS,
                headers={"Accept": "text/html,application/xhtml+xml,text/plain,*/*"},
            )
            content_type = getattr(article_response, "headers", {}).get("Content-Type", "").casefold()
            if getattr(article_response, "status_code", 200) < 400 and (
                not content_type or any(kind in content_type for kind in ("html", "text", "xml"))
            ):
                article_text = _extract_prefetch_text(getattr(article_response, "text", ""))
                if len(article_text) >= 120:
                    return {
                        "text": article_text,
                        "resolved_url": article_url,
                        "reason": "source_domain_article_lookup",
                    }
        search_text = _extract_prefetch_text(lookup_html)
        if len(search_text) >= 120 and _normalize_title(str(candidate.get("title", ""))) in _normalize_title(search_text):
            return {"text": search_text, "reason": "source_domain_search_snippet"}
        return {"reason": "source_domain_article_not_found"}
    except Exception as exc:
        return {"reason": f"source_lookup_exception:{str(exc)[:140]}"}


def _prefetch_candidate_article(candidate: dict, session: requests.Session) -> dict:
    started = time.perf_counter()
    candidate.setdefault("enrichment_method", "")
    candidate.setdefault("enrichment_failure_reason", "")
    candidate.setdefault("resolved_article_url", "")
    candidate.setdefault("enriched_snippet_chars", 0)
    candidate.setdefault("enriched_content_source", "")
    url = _prefetch_url_for_candidate(candidate, session)
    direct_reason = "no_direct_article_url"
    try:
        resolved_html = candidate.pop("_resolved_article_html", "")
        resolved_content_type = candidate.pop("_resolved_article_content_type", "").casefold()
        if resolved_html and (not resolved_content_type or any(kind in resolved_content_type for kind in ("html", "text", "xml"))):
            article_text = _extract_prefetch_text(resolved_html)
            chars = _apply_prefetch_evidence(
                candidate, article_text, method="resolved_article_url",
                content_source="resolved_article_html", resolved_url=url,
            )
            if chars:
                return {"status": "success", "chars": chars, "elapsed_seconds": round(time.perf_counter() - started, 2), "reason": "resolved_google_news_redirect", "enrichment_method": "resolved_article_url", "enriched_content_source": "resolved_article_html"}
            direct_reason = "resolved_article_too_short"
        if url:
            response = session.get(
                url,
                timeout=PREFETCH_TIMEOUT_SECONDS,
                headers={"Accept": "text/html,application/xhtml+xml,text/plain,*/*"},
            )
            content_type = response.headers.get("Content-Type", "").casefold()
            if response.status_code >= 400:
                direct_reason = f"http_{response.status_code}"
            elif content_type and not any(kind in content_type for kind in ("html", "text", "xml")):
                direct_reason = content_type[:80]
            else:
                article_text = _extract_prefetch_text(response.text)
                chars = _apply_prefetch_evidence(
                    candidate, article_text,
                    method="direct_article_url",
                    content_source="article_html",
                    resolved_url=url,
                )
                if chars:
                    return {"status": "success", "chars": chars, "elapsed_seconds": round(time.perf_counter() - started, 2), "reason": "direct_article_url", "enrichment_method": "direct_article_url", "enriched_content_source": "article_html"}
                direct_reason = "direct_article_too_short"
    except Exception as exc:
        direct_reason = f"direct_fetch_exception:{str(exc)[:140]}"

    followup = _prefetch_from_source_domain(candidate, session)
    if followup.get("text"):
        chars = _apply_prefetch_evidence(
            candidate,
            followup["text"],
            method="source_domain_followup",
            content_source="source_domain_search",
            resolved_url=followup.get("resolved_url", ""),
        )
        if chars:
            return {"status": "success", "chars": chars, "elapsed_seconds": round(time.perf_counter() - started, 2), "reason": followup.get("reason", "source_domain_followup"), "enrichment_method": "source_domain_followup", "enriched_content_source": "source_domain_search"}

    feed_snippet = _clean_text(str(candidate.get("snippet", "") or ""))
    if len(feed_snippet) >= 120:
        chars = _apply_prefetch_evidence(
            candidate,
            feed_snippet,
            method="source_feed_snippet",
            content_source="candidate_source_feed",
        )
        if chars:
            return {"status": "success", "chars": chars, "elapsed_seconds": round(time.perf_counter() - started, 2), "reason": "source_feed_snippet", "enrichment_method": "source_feed_snippet", "enriched_content_source": "candidate_source_feed"}

    reason = followup.get("reason") or direct_reason
    candidate["enrichment_failure_reason"] = reason
    return {"status": "failed_enrichment", "chars": 0, "elapsed_seconds": round(time.perf_counter() - started, 2), "reason": reason, "enrichment_method": "", "enriched_content_source": ""}
