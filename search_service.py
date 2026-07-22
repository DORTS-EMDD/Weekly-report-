"""Import-safe HTTP/RSS/DDGS retrieval primitives for Streamlit V19.4."""

import re
import urllib.parse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class FeedFetchError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def google_news_search_url(query: str, hl: str = "en-US", gl: str = "US", ceid_lang: str = "en") -> str:
    return "https://news.google.com/rss/search?q=" + f"{urllib.parse.quote(query)}&hl={hl}&gl={gl}&ceid={gl}:{ceid_lang}"


def google_news_site_proxy_url(domain: str, days: int, keywords: str, hl: str = "en-US", gl: str = "US", ceid_lang: str = "en") -> str:
    query = f"site:{domain} {keywords} when:{max(1, min(int(days), 365))}d"
    return google_news_search_url(query, hl=hl, gl=gl, ceid_lang=ceid_lang)


def compact_query(query: str, limit: int) -> str:
    q = re.sub(r"\s+", " ", (query or "").strip())
    if len(q) <= limit:
        return q
    words, kept = q.split(" "), []
    for word in words:
        candidate = " ".join(kept + [word])
        if len(candidate) > limit:
            break
        kept.append(word)
    return " ".join(kept).strip() or q[:limit].rstrip()


def ddgs_timelimit_for_lookback(days: int) -> str:
    if int(days) <= 7:
        return "w"
    if int(days) <= 31:
        return "m"
    return "y"


def create_requests_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=2, connect=2, read=2, backoff_factor=0.8, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(["GET"]), raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; TaipeiMetroAIWeekly/5.0; +https://www.dorts.gov.taipei/)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    return session


def fetch_feed(session, url: str, feedparser_module):
    if feedparser_module is None:
        raise FeedFetchError("parse error", "feedparser 套件未安裝")
    try:
        response = session.get(url, timeout=15)
    except requests.exceptions.Timeout as exc:
        raise FeedFetchError("timeout", str(exc)) from exc
    except requests.exceptions.RequestException as exc:
        raise FeedFetchError("parse error", str(exc)) from exc
    if response.status_code == 403:
        raise FeedFetchError("403", "HTTP 403 Forbidden")
    if response.status_code in (404, 405):
        raise FeedFetchError(str(response.status_code), f"HTTP {response.status_code}")
    if response.status_code >= 400:
        raise FeedFetchError("parse error", f"HTTP {response.status_code}")
    parsed = feedparser_module.parse(response.content)
    if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
        raise FeedFetchError("parse error", str(getattr(parsed, "bozo_exception", "RSS/Atom parse error")))
    return parsed


def execute_ddgs_query(ddgs_factory, query: str, *, use_news: bool, max_results: int, timelimit: str, backend: str):
    """Execute one existing DDGS backend attempt and preserve its raw ordering/schema."""
    with ddgs_factory() as ddgs:
        if use_news:
            results = ddgs.news(query, max_results=max_results, timelimit=timelimit, backend=backend)
        else:
            results = ddgs.text(query, max_results=max_results, timelimit=timelimit, backend=backend)
    return list(results or [])
