"""
國際捷運技術週報 自動產生器 v4.1
- AI API : MaiAgent 雲端 API（Chatbot completions）
- 搜尋一 : RSS 訂閱源（主要；Railway Gazette / IRJ 等六大媒體，無限速）
- 搜尋二 : ddgs（次要；DuckDuckGo + Bing + Yahoo 多後端，帶重試）
- 寄信   : Gmail SMTP
- 排程   : GitHub Actions（時間請見 .github/workflows/weekly.yml）
"""

import os
import sys
import re
import time
import random
import smtplib
import datetime
import concurrent.futures
from io import BytesIO
from html import escape
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from ddgs import DDGS
import requests

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# ── 環境變數（由 GitHub Secrets 注入）────────────────
MAIAGENT_API_KEY = os.environ["MAIAGENT_API_KEY"]
MAIAGENT_CHATBOT_ID = os.environ["MAIAGENT_CHATBOT_ID"]
MAIAGENT_API_BASE = os.environ.get("MAIAGENT_API_BASE", "https://api.maiagent.ai")
AI_PROVIDER_LABEL = "MaiAgent 雲端 API"
GMAIL_USER     = os.environ["GMAIL_USER"]
GMAIL_APP_PASS = os.environ["GMAIL_APP_PASS"]
RECIPIENTS     = os.environ["RECIPIENTS"]        # 逗號分隔
NEWS_LOOKBACK_DAYS = int(os.environ.get("NEWS_LOOKBACK_DAYS", "7"))
MAIAGENT_TIMEOUT_SECONDS = int(os.environ.get("MAIAGENT_TIMEOUT_SECONDS", "180"))
MAIAGENT_MAX_RSS_CHARS = int(os.environ.get("MAIAGENT_MAX_RSS_CHARS", "45000"))
MAIAGENT_MAX_DDG_CHARS = int(os.environ.get("MAIAGENT_MAX_DDG_CHARS", "25000"))
DDGS_MAX_WORKERS = int(os.environ.get("DDGS_MAX_WORKERS", "4"))
DDGS_MAX_QUERIES = int(os.environ.get("DDGS_MAX_QUERIES", "30"))
ENABLE_DDGS = os.environ.get("ENABLE_DDGS", "1").strip().lower() not in {"0", "false", "no"}

# GitHub 排程版預設聚焦制度透明、軌道技術成熟且對臺北捷運較有借鏡性的國家/地區。
ADVANCED_REGIONS = [
    "日本", "韓國", "新加坡", "香港",
    "美國", "加拿大", "英國", "法國",
    "德國", "荷蘭", "瑞士", "澳洲",
]

REGION_SEARCH_TERMS = {
    "日本": "Japan Tokyo Osaka subway railway operator",
    "韓國": "Korea Seoul metro subway operator",
    "新加坡": "Singapore MRT LTA SMRT",
    "香港": "Hong Kong MTR",
    "美國": "United States New York subway Washington Metro Chicago CTA",
    "加拿大": "Canada Toronto TTC Vancouver SkyTrain Montreal REM",
    "英國": "United Kingdom London Underground Transport for London",
    "法國": "France Paris Metro RATP Grand Paris Express",
    "德國": "Germany Berlin U-Bahn Munich U-Bahn Hamburg U-Bahn",
    "荷蘭": "Netherlands Amsterdam metro Rotterdam metro",
    "瑞士": "Switzerland Zurich tram Lausanne metro",
    "澳洲": "Australia Sydney Metro Melbourne Metro Brisbane rail",
}


# ── 日期 ──────────────────────────────────────────────
today      = datetime.date.today()
week_start = today - datetime.timedelta(days=NEWS_LOOKBACK_DAYS)
date_range = (
    f"{week_start.strftime('%Y年%m月%d日')} 至 {today.strftime('%Y年%m月%d日')}"
)
report_title = f"【{today.strftime('%Y/%m/%d')}】國際捷運技術新知、重大事件週報"


# ─────────────────────────────────────────────────────
# RSS 訂閱源（主要數據來源；無需 API 金鑰、不受限速）
# ─────────────────────────────────────────────────────
RSS_SOURCES = [
    ("Railway Gazette International",
     "https://www.railwaygazette.com/rss/latest"),
    ("International Railway Journal",
     "https://www.railjournal.com/feed/"),
    ("Railway Technology News",
     "https://www.railway-technology.com/news/feed/"),
    ("Global Railway Review",
     "https://www.globalrailwayreview.com/feed/"),
    ("Intelligent Transport",
     "https://www.intelligenttransport.com/feed/"),
    ("UITP – Global Public Transport",
     "https://www.uitp.org/rss.xml"),
]

def fetch_rss_feeds() -> str:
    """從六大國際鐵道/交通期刊 RSS 取得近 30 天文章，不受任何配額限制。"""
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=30)
    )
    all_blocks: list[str] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MetroWeeklyBot/4.1)"}

    for source_name, url in RSS_SOURCES:
        print(f"[INFO] RSS 抓取：{source_name}")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as f:
                raw = f.read()
            root = ET.fromstring(raw)

            items_found: list[tuple[str, str, str, str]] = []
            ATOM = "http://www.w3.org/2005/Atom"

            # ── RSS 2.0 ──
            for item in root.findall(".//item"):
                title    = (item.findtext("title") or "").strip()
                link     = (item.findtext("link")  or "").strip()
                desc     = (item.findtext("description") or "").strip()[:400]
                pub_str  = (item.findtext("pubDate") or "").strip()
                if not title:
                    continue
                date_label = _parse_pub_date(pub_str)
                if _is_recent(pub_str, cutoff):
                    items_found.append((title, link, desc, date_label))

            # ── Atom ──
            if not items_found:
                for entry in root.findall(f".//{{{ATOM}}}entry"):
                    title  = (entry.findtext(f"{{{ATOM}}}title")   or "").strip()
                    link_el = entry.find(f"{{{ATOM}}}link")
                    link   = link_el.get("href", "") if link_el is not None else ""
                    summ   = (entry.findtext(f"{{{ATOM}}}summary") or "").strip()[:400]
                    pub_str = (
                        entry.findtext(f"{{{ATOM}}}published")
                        or entry.findtext(f"{{{ATOM}}}updated")
                        or ""
                    ).strip()
                    if not title:
                        continue
                    date_label = _parse_pub_date(pub_str)
                    if _is_recent(pub_str, cutoff):
                        items_found.append((title, link, summ, date_label))

            if items_found:
                lines = [f"【RSS來源：{source_name}（共 {len(items_found)} 篇）】"]
                for t, l, d, dt in items_found[:20]:
                    lines.append(
                        f"  日期：{dt}\n  標題：{t}\n  摘要：{d}\n  連結：{l}"
                    )
                all_blocks.append("\n".join(lines))
                print(f"[INFO]   → 取得 {len(items_found)} 篇近30天文章")
            else:
                all_blocks.append(f"【RSS來源：{source_name}】（近30天無新文章）")
                print(f"[INFO]   → 無近30天文章")

        except Exception as exc:
            all_blocks.append(f"【RSS來源：{source_name}】⚠️ 失敗：{exc}")
            print(f"[WARN] RSS {source_name} 失敗：{exc}")

    return "\n\n".join(all_blocks)


def _parse_pub_date(pub_str: str) -> str:
    """解析多種日期格式，回傳 YYYY-MM-DD 字串；解析失敗則原文回傳。"""
    if not pub_str:
        return "日期未知"
    try:
        dt = parsedate_to_datetime(pub_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    try:
        dt = datetime.datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return pub_str[:16]


def _is_recent(pub_str: str, cutoff: datetime.datetime) -> bool:
    """判斷文章是否在 cutoff 之後；解析失敗一律納入（不漏）。"""
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


# ─────────────────────────────────────────────────────
# 20 組精準查詢詞（技術新知 / 事故分析 / 營運爭議 / 地區官方）
# ─────────────────────────────────────────────────────
SEARCH_QUERIES = [
    # 技術新知：用「技術名詞 + metro/rail + announcement/trial」提高命中率
    f"metro railway CBTC GoA4 driverless signalling contract trial {today:%Y}",
    f"metro railway digital twin predictive maintenance AI condition monitoring {today:%Y}",
    f"metro rail artificial intelligence fault detection maintenance announcement {today:%Y}",
    f"railway metro FRMCS 5G communications pilot migration trial {today:%Y}",
    f"metro rail platform screen door automation upgrade technology {today:%Y}",
    f"metro railway cybersecurity operations control centre incident response {today:%Y}",
    f"railway metro battery energy storage regenerative braking supercapacitor {today:%Y}",
    f"metro train traction inverter SiC silicon carbide new rolling stock {today:%Y}",
    f"metro rail open payment fare gate QR code account based ticketing {today:%Y}",
    f"railway metro EULYNX digital interlocking standard deployment {today:%Y}",
    f"metro extension opening trial operation new line {today:%B %Y}",
    f"railway metro official press release technology upgrade {today:%B %Y}",
    # 重大事故：用新聞常見詞彙補足 derailment 以外的事故型態
    f"metro subway service suspended signal failure power outage {today:%B %Y}",
    f"metro subway train derailment collision evacuation {today:%B %Y}",
    f"metro rail fire smoke evacuation station incident {today:%B %Y}",
    f"metro subway track intrusion person struck service disruption {today:%B %Y}",
    f"metro train door fault passenger evacuation delay {today:%B %Y}",
    f"light rail tram accident collision derailment service suspended {today:%B %Y}",
    f"鉄道 地下鉄 事故 脱線 信号障害 運休 {today:%Y年%m月}",
    f"지하철 사고 탈선 신호 장애 운행 중단 {today:%Y년 %m월}",
    # 營運爭議：勞資、票價、停駛、工程延期、公眾反彈
    f"metro subway transit strike labor dispute service disruption {today:%B %Y}",
    f"metro subway fare increase public opposition transit authority {today:%B %Y}",
    f"metro rail construction delay cost overrun controversy {today:%B %Y}",
    f"metro subway long term closure replacement bus passenger complaints {today:%B %Y}",
    f"metro transit safety crime passenger complaints operations controversy {today:%B %Y}",
    # 地區官方與重點城市
    f"MTR Hong Kong incident service disruption press release {today:%B %Y}",
    f"Singapore MRT LTA SMRT disruption incident announcement {today:%B %Y}",
    f"Japan subway railway operator incident service suspension {today:%Y年%m月}",
    f"Korea metro subway operator incident service disruption {today:%B %Y}",
    f"London Underground Paris Metro Berlin U-Bahn incident disruption {today:%B %Y}",
    f"New York subway Washington Metro Chicago CTA incident disruption {today:%B %Y}",
]

for region in ADVANCED_REGIONS:
    term = REGION_SEARCH_TERMS[region]
    SEARCH_QUERIES.extend([
        f"{term} metro rail technology upgrade press release {today:%B %Y}",
        f"{term} metro subway incident disruption accident {today:%B %Y}",
        f"{term} metro transit fare strike construction delay controversy {today:%B %Y}",
    ])

# 事故/爭議類查詢編號（1-based），使用 news() 搜尋更有效
_NEWS_QUERY_INDICES = set(range(13, len(SEARCH_QUERIES) + 1))


def _run_single_ddg_query(i: int, query: str, use_news: bool, news_timelimit: str) -> tuple[int, str]:
    """執行單一 ddgs 查詢（可安全在背景執行緒平行執行）。"""
    # 隨機抖動起跑時間，避免多執行緒同時擊中 DDGS 觸發瞬間限速
    time.sleep(random.uniform(0.1, 0.8))
    result_block = None

    for backend in ["auto", "bing"]:
        for attempt in range(1, 3):        # 每個後端最多嘗試 2 次
            try:
                with DDGS() as ddgs:
                    if use_news:
                        results = ddgs.news(
                            query, max_results=8,
                            timelimit=news_timelimit, backend=backend
                        )
                    else:
                        results = ddgs.text(
                            query, max_results=10,
                            timelimit="m", backend=backend
                        )

                if results:
                    lines = [f"【DDG {i}（{backend}）】{query}"]
                    for r in results:
                        body = (
                            r.get("body")
                            or r.get("excerpt")
                            or r.get("description")
                            or ""
                        )[:300]
                        href = r.get("href") or r.get("url") or ""
                        lines.append(
                            f"  標題：{r.get('title','')}\n"
                            f"  日期：{r.get('date','')}\n"
                            f"  摘要：{body}\n"
                            f"  連結：{href}"
                        )
                    result_block = "\n".join(lines)
                else:
                    result_block = (
                        f"【DDG {i}（{backend}）】{query}\n"
                        f"  （{backend} 無結果）"
                    )
                break   # 成功，跳出 attempt 迴圈

            except Exception as exc:
                err = str(exc)
                is_rate = any(
                    k in err for k in
                    ("Ratelimit", "429", "403", "vqd", "No results")
                )
                wait = attempt * 1.0 + random.uniform(0.5, 1.5)
                time.sleep(wait)
                if not is_rate:
                    result_block = (
                        f"【DDG {i}】{query}\n"
                        f"  ⚠️ {type(exc).__name__}: {err[:120]}"
                    )
                    break   # 非限速錯誤，不切後端

        if result_block and "無結果" not in result_block and "⚠️" not in result_block:
            break   # 已取得有效結果，無需切後端

    return i, (
        result_block
        or f"【DDG {i}】{query}\n  ⚠️ 兩個後端均無法取得結果，已略過"
    )


def run_duckduckgo_searches() -> str:
    """
    平行執行基礎關鍵字與先進國家/地區補充搜尋（ddgs v9 多後端）。
    - 技術類：text()  + backend=auto
    - 事故/爭議類：news() + backend=auto
    - 限速時自動切換後備後端（bing），最多重試 2 次
    - 同時最多 6 條併發，兼顧速度與避免被 DDGS 判定為濫用流量
    - 相較舊版序列執行（56 組查詢逐一等待，最壞情況可能超過 GitHub Actions
      15 分鐘 timeout 被強制取消），平行化後總時間大幅縮短。
    """
    if not ENABLE_DDGS:
        print("[INFO] DDGS 已由環境變數 ENABLE_DDGS=0 停用")
        return "【DDGS】本次依設定停用 ddgs 搜尋，僅使用 RSS 來源。"

    active_queries = SEARCH_QUERIES[:max(1, min(DDGS_MAX_QUERIES, len(SEARCH_QUERIES)))]
    total = len(active_queries)
    news_timelimit = "w" if NEWS_LOOKBACK_DAYS <= 7 else "m"
    results_map: dict[int, str] = {}
    max_workers = max(1, min(DDGS_MAX_WORKERS, total))
    print(f"[INFO] DDG 啟動：{total}/{len(SEARCH_QUERIES)} 組查詢，併發 {max_workers}，timelimit={news_timelimit}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_single_ddg_query, i, query, i in _NEWS_QUERY_INDICES, news_timelimit
            ): i
            for i, query in enumerate(active_queries, 1)
        }
        done_count = 0
        for future in concurrent.futures.as_completed(futures):
            i, block = future.result()
            results_map[i] = block
            done_count += 1
            print(f"[INFO] DDG 已完成 {done_count:02d}/{total}")

    return "\n\n".join(results_map[i] for i in sorted(results_map))


# ─────────────────────────────────────────────────────
def _limit_chars(text: str, max_chars: int, label: str) -> str:
    """避免一次送進 MaiAgent 的 prompt 過長導致 GitHub Actions 卡住或 API 逾時。"""
    text = text or ""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[- max_chars // 2 :]
    return (
        f"{head}\n\n【系統提示：{label} 原始資料共 {len(text):,} 字元，"
        f"為避免雲端 API 逾時，已截取前後各半，保留代表性候選。】\n\n{tail}"
    )


def build_prompt(rss_results: str, ddg_results: str) -> str:
    weekday_zh = ["一","二","三","四","五","六","日"][today.weekday()]
    return f"""
# 角色
你是專業捷運機電技術分析師，服務對象為台北市政府捷運工程局處長及技術同仁。

# 任務
以下是透過「RSS 訂閱源」與「ddgs 多後端搜尋」蒐集到的國際軌道交通原始資料（涵蓋近 30 天）。
請嚴格依照三大領域與查核原則，整理出週報（目標期間：{date_range}）。
請先合併重複來源，再保留具公共運輸安全、工程技術、營運管理參考價值的事件；不要因為來源摘要較短就直接排除。

## ━━ 第一部分：RSS 訂閱源（Railway Gazette / IRJ 等六大媒體）━━
{rss_results}

## ━━ 第二部分：關鍵字搜尋結果（ddgs 多後端）━━
{ddg_results}

## ⚠️ 最高查核原則（零容忍，違反即捨棄該則）
1. **只使用上方原始資料中出現的資訊**，禁止自行編造
2. **日期判斷（依類別分級）**：
   - 事故類、爭議類：「新聞發布日」與「事件發生日」皆須在 {date_range} 內
   - 技術新知類：「新聞發布日」或「技術發表/測試日」在過去 30 天內即可納入
3. **禁止舊聞充數**：超過 30 天的歷史案例一律捨棄
4. **無付費牆**：確保 URL 可公開存取，付費牆來源捨棄
5. **寧缺勿濫**：確實無符合條件者，直接回報「本週無符合條件之重大異動」
6. **數量原則**：若原始資料足夠，至少輸出 8 則；若不足 8 則，說明是因來源或日期條件不足，而非自行補舊聞。

## 三大核心主題領域

### 領域 A：技術新知（聚焦「次世代」與「首創」）
- **信號與通訊**：GoA4、CBTC、FRMCS/5G/6G、虛擬聯結（Virtual Coupling）
- **智慧化與數據**：AI 預防性維修、數位雙生（Digital Twin）、邊緣運算（Edge AI）、資安
- **硬體與能源**：SiC 牽引變流器、超級電容回生儲能、氫能列車、新型電聯車首發
- **標準與政策**：EULYNX、綠能減碳政策、重大建設進度

### 領域 B：事故分析（根因導向）
- 出軌、號誌故障、機電異常、延誤
- 每則須分析根因：人為 / 系統 / 環境 / 機電介面

### 領域 C：營運爭議
- 勞資罷工、票價政策變動、系統轉換困難或延宕

## 優先關注區域
{", ".join(ADVANCED_REGIONS)}

## 輸出格式（每則獨立區塊，目標 8–15 則）

# {report_title}
> 資料涵蓋期間：{date_range}（技術新知可納入近 30 天）

---

### 🔹 [技術新知/重大事故/營運爭議] 國家/地區：（一句有力主標題）
* **發布/事件日期**：（原文發布年月日）
* **事件摘要**：
  - （列點精要說明，3–5 點）
* **技術關鍵字**：（英漢對照，例：FRMCS / 未來鐵道行動通訊系統）
* **資料來源**：[來源名稱](完整 https:// 網址)
* **【臺北捷運啟示】**：（對北捷系統的具體參考價值；無關聯請寫「暫無直接關聯」）

---

## 結尾（必填）
---
📊 **本週統計**：共 N 則（技術新知 N 則 / 重大事故 N 則 / 營運爭議 N 則）
🔍 **執行搜尋次數**：RSS {len(RSS_SOURCES)} 源 + ddgs {len(SEARCH_QUERIES)} 次關鍵字搜尋
⏰ **報告產出時間**：{today.strftime('%Y年%m月%d日')} 週{weekday_zh}
"""


# ─────────────────────────────────────────────────────
def _extract_maiagent_text(data) -> str:
    """寬鬆解析 MaiAgent 不同版本可能回傳的文字欄位。"""
    if isinstance(data, str):
        return data.strip()

    if isinstance(data, dict):
        for key in ("content", "text", "answer", "output", "response"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        message = data.get("message")
        if isinstance(message, dict):
            for key in ("content", "text", "answer"):
                value = message.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        content_payload = data.get("contentPayload") or data.get("content_payload")
        if isinstance(content_payload, dict):
            for key in ("content", "text", "answer"):
                value = content_payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            items = content_payload.get("items")
            if isinstance(items, list):
                texts = []
                for item in items:
                    if isinstance(item, dict):
                        value = item.get("text") or item.get("content") or item.get("answer")
                        if value:
                            texts.append(str(value))
                if texts:
                    return "\n".join(texts).strip()

        for key in ("result", "data"):
            nested = data.get(key)
            if isinstance(nested, (dict, str)):
                nested_text = _extract_maiagent_text(nested)
                if nested_text and nested_text != str(nested):
                    return nested_text

    text = str(data).strip()
    if text:
        return text
    raise ValueError("MaiAgent 回應無文字內容")


def _maiagent_endpoint_candidates(base_url: str, chatbot_id: str) -> list[str]:
    """
    MaiAgent 文件中的 completions 端點目前以 /api/chatbots/{id}/completions/ 為準。
    但不同環境可能仍保留 /api/v1/...，因此保留 fallback。
    """
    base_url = base_url.rstrip("/")
    candidates: list[str] = []

    if base_url.endswith("/api/v1"):
        candidates.append(f"{base_url}/chatbots/{chatbot_id}/completions/")
        candidates.append(f"{base_url[:-3]}/chatbots/{chatbot_id}/completions/")
    elif base_url.endswith("/api"):
        candidates.append(f"{base_url}/chatbots/{chatbot_id}/completions/")
        candidates.append(f"{base_url}/v1/chatbots/{chatbot_id}/completions/")
    else:
        candidates.append(f"{base_url}/api/chatbots/{chatbot_id}/completions/")
        candidates.append(f"{base_url}/api/v1/chatbots/{chatbot_id}/completions/")

    # 去重但保留順序
    seen = set()
    unique = []
    for url in candidates:
        if url not in seen:
            unique.append(url)
            seen.add(url)
    return unique


def _extract_maiagent_response_text(response: requests.Response) -> str:
    """
    MaiAgent completions 可能回 JSON，也可能回串流文字。
    這裡同時支援 JSON 與 data: {...} 的 SSE 形式。
    """
    content_type = (response.headers.get("Content-Type") or "").lower()

    if "application/json" in content_type:
        return _extract_maiagent_text(response.json())

    raw = response.text.strip()
    if not raw:
        return ""

    # 嘗試解析 SSE: data: {"content": "..."}
    chunks = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload in {"[DONE]", "DONE"}:
            continue
        try:
            import json
            obj = json.loads(payload)
            text = _extract_maiagent_text(obj)
            if text:
                chunks.append(text)
        except Exception:
            if payload:
                chunks.append(payload)

    if chunks:
        return "\n".join(chunks).strip()

    return raw


def call_maiagent_cloud(prompt: str) -> str:
    """呼叫 MaiAgent 雲端 Chatbot completions API 產生報告。"""
    if not MAIAGENT_API_KEY:
        raise RuntimeError("未設定 MAIAGENT_API_KEY")
    if not MAIAGENT_CHATBOT_ID:
        raise RuntimeError("未設定 MAIAGENT_CHATBOT_ID")

    headers = {
        "Authorization": f"Api-Key {MAIAGENT_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream, text/plain",
    }

    # 官方文件使用 is_streaming；保留 isStreaming 作為相容 fallback。
    payloads = [
        {"message": {"content": prompt}, "is_streaming": False},
        {"message": {"content": prompt}, "isStreaming": False},
        {"message": {"content": prompt}, "is_streaming": True},
    ]

    endpoints = _maiagent_endpoint_candidates(MAIAGENT_API_BASE, MAIAGENT_CHATBOT_ID)
    last_error = None

    for url in endpoints:
        for payload in payloads:
            try:
                safe_url = url.replace(MAIAGENT_API_BASE.rstrip("/"), "***").replace(MAIAGENT_CHATBOT_ID, "***")
                print(f"[INFO] 送出 MaiAgent API：timeout={MAIAGENT_TIMEOUT_SECONDS}s，endpoint={safe_url}")
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=MAIAGENT_TIMEOUT_SECONDS,
                    allow_redirects=False,
                )
            except requests.exceptions.Timeout as exc:
                raise RuntimeError(
                    f"MaiAgent API 超過 {MAIAGENT_TIMEOUT_SECONDS}s 未回應；"
                    "請降低 DDGS_MAX_QUERIES / MAIAGENT_MAX_DDG_CHARS，或提高 MAIAGENT_TIMEOUT_SECONDS。"
                ) from exc
            except Exception as exc:
                last_error = exc
                continue

            # 301/302/307/308：通常是少了或多了尾斜線，不讓 requests 自動把 POST 轉成 GET。
            if response.status_code in (301, 302, 307, 308):
                last_error = RuntimeError(
                    f"MaiAgent API 重新導向 {response.status_code}：{response.headers.get('Location', '')}"
                )
                continue

            # 405 很常見於端點版本錯誤或 POST 被 redirect 成 GET；繼續試下一個 endpoint。
            if response.status_code in (400, 404, 405, 422):
                last_error = RuntimeError(
                    f"MaiAgent API 回應 {response.status_code}: {response.text[:500]}"
                )
                print(f"[WARN] {last_error}")
                continue

            response.raise_for_status()
            text = _extract_maiagent_response_text(response)
            if text:
                return text

            last_error = RuntimeError("MaiAgent API 回應成功但未解析到文字內容")

    raise RuntimeError(f"MaiAgent API 呼叫失敗：{last_error}")

def generate_report() -> str:
    print(f"[INFO] AI：{AI_PROVIDER_LABEL}")
    print(f"[INFO] 期間：{date_range}")

    # Step 1：RSS 訂閱源（主要，穩定）
    print("\n[INFO] ── Step 1：RSS 訂閱源抓取 ──")
    rss_results = fetch_rss_feeds()
    print(f"[INFO] RSS 資料量：{len(rss_results):,} 字元")

    # Step 2：ddgs 搜尋（補充，可能受限速）
    print("\n[INFO] ── Step 2：ddgs 多後端搜尋 ──")
    ddg_results = run_duckduckgo_searches()
    print(f"[INFO] DDG 資料量：{len(ddg_results):,} 字元")

    # Step 3：MaiAgent 雲端 API 分析整理
    print("\n[INFO] ── Step 3：MaiAgent 雲端 API 分析整理 ──")
    rss_for_prompt = _limit_chars(rss_results, MAIAGENT_MAX_RSS_CHARS, "RSS")
    ddg_for_prompt = _limit_chars(ddg_results, MAIAGENT_MAX_DDG_CHARS, "DDGS")
    prompt = build_prompt(rss_for_prompt, ddg_for_prompt)
    print(f"[INFO] Prompt 資料量：約 {len(prompt):,} 字元（RSS上限 {MAIAGENT_MAX_RSS_CHARS:,} / DDGS上限 {MAIAGENT_MAX_DDG_CHARS:,}）")
    return call_maiagent_cloud(prompt)


# ─────────────────────────────────────────────────────
def markdown_to_html(md: str) -> str:
    h = md
    h = re.sub(r'^# (.+)$',   r'<h1>\1</h1>', h, flags=re.MULTILINE)
    h = re.sub(r'^## (.+)$',  r'<h2>\1</h2>', h, flags=re.MULTILINE)
    h = re.sub(r'^### (.+)$', r'<h3>\1</h3>', h, flags=re.MULTILINE)
    h = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', h)
    h = re.sub(r'\[(.+?)\]\((https?://[^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', h)
    h = re.sub(r'^> (.+)$',  r'<blockquote>\1</blockquote>', h, flags=re.MULTILINE)
    h = re.sub(r'^\* (.+)$', r'<li>\1</li>', h, flags=re.MULTILINE)
    h = re.sub(r'^- (.+)$',  r'<li>\1</li>', h, flags=re.MULTILINE)
    h = re.sub(r'^---$', r'<hr>', h, flags=re.MULTILINE)
    h = h.replace('\n\n', '</p><p>').replace('\n', '<br>')
    return f"""<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<style>
  body{{font-family:'Noto Sans TC',Arial,sans-serif;line-height:1.8;
       max-width:820px;margin:0 auto;padding:24px;color:#333}}
  h1{{color:#1a3a5c;border-bottom:3px solid #1a3a5c;padding-bottom:8px}}
  h2{{color:#2c5f8a}}
  h3{{color:#1a6e4a;background:#f0f8f4;padding:8px 12px;
      border-left:4px solid #1a6e4a;border-radius:0 4px 4px 0}}
  blockquote{{background:#f5f5f5;border-left:4px solid #ccc;
              margin:0;padding:8px 16px;color:#666}}
  li{{margin:4px 0}} a{{color:#2c5f8a}}
  hr{{border:none;border-top:1px solid #ddd;margin:24px 0}}
  strong{{color:#1a3a5c}}
  .footer{{background:#f5f8fc;padding:12px;border-radius:6px;
           margin-top:24px;font-size:.9em;color:#666}}
</style></head><body>
<p>{h}</p>
<div class="footer">
  📧 此報告由 AI 自動產生 | MaiAgent 雲端 API + RSS + ddgs | 僅供參考，請交叉驗證原始來源
</div></body></html>"""


def markdown_to_pdf_bytes(md: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    for style_name in ("Title", "Heading1", "Heading2", "Heading3", "BodyText"):
        styles[style_name].fontName = "MSung-Light"
        styles[style_name].leading = max(styles[style_name].leading, 16)
    styles["BodyText"].fontSize = 10.5

    story = []
    for raw_line in md.splitlines():
        line = raw_line.strip()
        if not line or line == "---":
            story.append(Spacer(1, 8))
            continue
        if line.startswith("# "):
            story.append(Paragraph(escape(line[2:]), styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(escape(line[3:]), styles["Heading2"]))
        elif line.startswith("### "):
            story.append(Paragraph(escape(line[4:]), styles["Heading3"]))
        else:
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            line = re.sub(r"\[(.+?)\]\((https?://[^\)]+)\)", r"\1：\2", line)
            story.append(Paragraph(escape(line), styles["BodyText"]))
    doc.build(story)
    return buffer.getvalue()


def try_markdown_to_pdf_bytes(md: str) -> bytes | None:
    try:
        return markdown_to_pdf_bytes(md)
    except ModuleNotFoundError:
        print("[WARN] reportlab 未安裝，略過 PDF 附件")
        return None


# ─────────────────────────────────────────────────────
def save_report(text: str) -> str:
    os.makedirs("reports", exist_ok=True)
    path = f"reports/report_{today.strftime('%Y%m%d')}.md"
    for p in [path, "reports/latest.md"]:
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"[INFO] 已儲存：{path}")
    return path


def send_email(text: str, recipients: list) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = report_title
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(markdown_to_html(text), "html", "utf-8"))
    pdf_bytes = try_markdown_to_pdf_bytes(text)
    if pdf_bytes:
        pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_part.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"metro_report_{today.strftime('%Y%m%d')}.pdf",
        )
        msg.attach(pdf_part)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_APP_PASS)
            s.sendmail(GMAIL_USER, recipients, msg.as_string())
        print(f"[INFO] ✅ 已寄送至：{', '.join(recipients)}")
        return True
    except Exception as e:
        print(f"[ERROR] 寄信失敗：{e}")
        return False


# ─────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  國際捷運技術週報 自動產生器 v4.1")
    print(f"  日期：{today.strftime('%Y年%m月%d日')}")
    print(f"  AI：{AI_PROVIDER_LABEL}")
    print(f"  新聞天數：{NEWS_LOOKBACK_DAYS} 天")
    print(f"  MaiAgent timeout：{MAIAGENT_TIMEOUT_SECONDS}s")
    print(f"  搜尋：RSS {len(RSS_SOURCES)} 源 + ddgs 最多 {min(DDGS_MAX_QUERIES, len(SEARCH_QUERIES))}/{len(SEARCH_QUERIES)} 次")
    print("=" * 55)

    report = generate_report()
    save_report(report)
    recipients = [r.strip() for r in RECIPIENTS.split(",") if r.strip()]
    send_email(report, recipients)
    print("\n✅ 完成！")


if __name__ == "__main__":
    main()
