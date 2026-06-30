"""
國際捷運技術週報 — Streamlit 展示介面 v4.2（展示加速版）
- 搜尋一：Google News 代理（主要；聚焦捷運/輕軌專業媒體）
- 搜尋二：ddgs 關鍵字搜尋（次要；精簡查詢量 + 平行抓取）
- 所有外部請求改為 ThreadPoolExecutor 平行執行，目標 20–30 秒內產出報告
  （正式週報排程 main.py／GitHub Actions 仍保留完整地毯式查詢，不受此檔影響）
- 收件人欄位使用 session_state 保留編輯狀態
- 下拉選單文字顯示修正（黑字）
"""

import os
import re
import datetime
import concurrent.futures
import smtplib
from io import BytesIO
from html import escape
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

import streamlit as st
from ddgs import DDGS
from google import genai
from google.genai import types


# ══════════════════════════════════════════════════════
#  金鑰讀取
# ══════════════════════════════════════════════════════
def get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, default)


# ── 頁面設定 ──────────────────────────────────────────
st.set_page_config(
    page_title="國際捷運技術週報 AI 系統",
    page_icon="🚇",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  [data-testid="stSidebar"] { background-color: #1a3a5c; }
  [data-testid="stSidebar"], [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] p, [data-testid="stSidebar"] span,
  [data-testid="stSidebar"] div, [data-testid="stSidebar"] .stMarkdown {
    color: white !important;
  }
  [data-testid="stSidebar"] input,
  [data-testid="stSidebar"] textarea {
    color: #111 !important; background-color: #f5f5f5 !important;
  }
  [data-testid="stSidebar"] [data-baseweb="select"],
  [data-testid="stSidebar"] [data-baseweb="select"] *,
  [data-testid="stSidebar"] [data-baseweb="select"] div,
  [data-testid="stSidebar"] [data-baseweb="select"] span,
  [data-testid="stSidebar"] [data-baseweb="select"] input,
  [data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] div,
  [data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] span {
    color: #111111 !important;
    background-color: #f5f5f5 !important;
  }
  [data-baseweb="option"],
  [data-baseweb="option"] *,
  [role="option"],
  [data-baseweb="menu"] li,
  [data-baseweb="popover"] li,
  [data-baseweb="popover"] [role="option"] {
    color: #111111 !important;
    background-color: #ffffff !important;
  }
  [data-baseweb="option"]:hover,
  [data-baseweb="option"][aria-selected="true"],
  [role="option"]:hover {
    background-color: #dbeafe !important;
    color: #111111 !important;
  }
  .main-title {
    font-size: 2rem; font-weight: 700; color: #1a3a5c;
    border-bottom: 3px solid #1a3a5c; padding-bottom: 8px; margin-bottom: 4px;
  }
  .subtitle { color: #666; font-size: 0.95rem; margin-bottom: 14px; }
  .warn-box {
    background: #fff8e6; border-left: 4px solid #f59e0b;
    padding: 12px 16px; border-radius: 0 6px 6px 0; margin: 12px 0;
  }
  .ok-box {
    background: #f0f8f4; border-left: 4px solid #1a6e4a;
    padding: 12px 16px; border-radius: 0 6px 6px 0; margin: 12px 0;
  }
  .stat-card {
    background: white; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 16px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.08);
  }
  .stat-num { font-size: 2rem; font-weight: 700; color: #1a3a5c; }
  .stat-label { color: #666; font-size: 0.85rem; }
  div[data-testid="stVerticalBlock"] > div:has(.main-title) { gap: .35rem; }
  [data-testid="stSidebar"] .stButton button,
  [data-testid="stSidebar"] .stButton button *,
  [data-testid="stSidebar"] .stButton button p,
  [data-testid="stSidebar"] .stButton button span {
    color: #111111 !important;
    background-color: #f5f5f5 !important;
  }

  [data-testid="stSidebar"] .stButton button:hover,
  [data-testid="stSidebar"] .stButton button:hover *,
  [data-testid="stSidebar"] .stButton button:hover p,
  [data-testid="stSidebar"] .stButton button:hover span {
    color: #111111 !important;
    background-color: #e2e8f0 !important;
  }

  /* ── Expander 標題文字（白底上顯示白字問題） ── */
  [data-testid="stSidebar"] [data-testid="stExpander"] {
    border: 1px solid rgba(255,255,255,0.25) !important;
    border-radius: 6px !important;
    background-color: rgba(255,255,255,0.08) !important;
  }
  [data-testid="stSidebar"] [data-testid="stExpander"] summary,
  [data-testid="stSidebar"] [data-testid="stExpander"] summary p,
  [data-testid="stSidebar"] [data-testid="stExpander"] summary span,
  [data-testid="stSidebar"] details summary,
  [data-testid="stSidebar"] details summary * {
    color: white !important;
    background-color: transparent !important;
  }
  [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
    background-color: rgba(255,255,255,0.12) !important;
  }

  /* ── number_input +/- 按鈕配色 ── */
  [data-testid="stSidebar"] [data-testid="stNumberInputStepDown"],
  [data-testid="stSidebar"] [data-testid="stNumberInputStepUp"] {
    background-color: #2c5f8a !important;
    color: white !important;
    border-color: rgba(255,255,255,0.3) !important;
  }
  [data-testid="stSidebar"] [data-testid="stNumberInputStepDown"]:hover,
  [data-testid="stSidebar"] [data-testid="stNumberInputStepUp"]:hover {
    background-color: #3a7ab5 !important;
    color: white !important;
  }
  [data-testid="stSidebar"] [data-testid="stNumberInputStepDown"] svg,
  [data-testid="stSidebar"] [data-testid="stNumberInputStepUp"] svg {
    fill: white !important;
    stroke: white !important;
  }
</style>
""", unsafe_allow_html=True)

# ── 日期 ──────────────────────────────────────────────
today = datetime.date.today()

# ── 金鑰狀態 ──────────────────────────────────────────
api_key    = get_secret("GEMINI_API_KEY")
gmail_user = get_secret("GMAIL_USER")
gmail_pass = get_secret("GMAIL_APP_PASS")

# ── 側邊欄 ──────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚇 捷運週報系統")

    st.markdown("### ⚙️ 模型設定")
    model_choice = st.selectbox(
        "選擇 Gemini 模型",
        ["gemini-3.1-flash-lite", "gemini-3.5-flash"],
        index=0,
        help=(
            "gemini-3.1-flash-lite：輕量版，速度快、省配額。\n"
            "gemini-3.5-flash：接近 Pro 等級，細節更完整。"
        ),
    )
    lookback_days = st.number_input(
        "新聞搜尋天數",
        min_value=3,
        max_value=30,
        value=7,
        step=1,
        help="事故、營運爭議、技術新知皆依此天數篩選。",
    )

    st.markdown("### 📬 收件設定")
    default_recipients = get_secret("DEFAULT_RECIPIENTS", "")
    if "recipients_text" not in st.session_state:
        st.session_state["recipients_text"] = default_recipients

    recipient_input = st.text_area(
        "收件信箱（每行一個）",
        key="recipients_text",
        placeholder="pe9875@gov.taipei\n10983@gov.taipei",
        height=90,
    )
    st.caption(
        "💡 **新增收件人**：直接在上方輸入框換行追加即可。"
    )

    st.markdown("### 📅 排程說明")
    st.markdown("""
- ⏰ **每週一 08:00**（台灣時間）自動執行
- ☁️ 由 **GitHub Actions** 雲端排程
- 💤 **不需要開電腦**
- 📧 自動寄送至公務信箱
    """)
    if not (api_key and gmail_user and gmail_pass):
        st.warning("金鑰或 Gmail 設定尚未完整，排程寄送可能失敗。")
    with st.expander("🔑 系統狀態", expanded=False):
        st.markdown(f"Gemini API Key：{'✅ 已設定' if api_key else '❌ 未設定'}")
        st.markdown(f"Gmail 帳號：{'✅ 已設定' if gmail_user else '❌ 未設定'}")
        st.markdown(f"Gmail 密碼：{'✅ 已設定' if gmail_pass else '❌ 未設定'}")
    st.markdown("---")
    st.caption("🏛️ 台北市政府捷運工程局\nAI 競賽展示系統 v4.1")

week_start = today - datetime.timedelta(days=int(lookback_days))
date_range = f"{week_start.strftime('%Y年%m月%d日')} 至 {today.strftime('%Y年%m月%d日')}"
report_title = f"【{today.strftime('%Y/%m/%d')}】國際捷運技術新知、重大事件週報"

# ── 主畫面 ──────────────────────────────────────────
st.markdown('<div class="main-title">🚇 國際捷運技術週報 AI 自動產生系統</div>',
            unsafe_allow_html=True)
st.markdown(
    f'<div class="subtitle">資料涵蓋期間：{week_start.strftime("%Y/%m/%d")} – '
    f'{today.strftime("%Y/%m/%d")} ｜ 使用模型：{model_choice}</div>',
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns(3)
for col, num, label in [
    (c1, "3",   "主題領域"),
    (c2, "全球", "涵蓋範圍"),
    (c3, f"{lookback_days}", "新聞搜尋天數"),
]:
    col.markdown(
        f'<div class="stat-card"><div class="stat-num">{num}</div>'
        f'<div class="stat-label">{label}</div></div>',
        unsafe_allow_html=True,
    )

with st.expander("主題領域說明"):
    st.markdown("""
**主題領域**
- 技術新知
- 重大事故
- 營運爭議

涵蓋範圍：全球國際捷運／鐵道系統，不限定特定國家。
    """)



# ═══════════════════════════════════════════════════════
#  新聞來源（透過 Google News RSS 代理；聚焦捷運/輕軌媒體，避開來源網站封鎖）
# ═══════════════════════════════════════════════════════
GNEWS_SOURCES = [
    # ── 技術新知優先（更新頻率高、技術報導扎實的媒體）──
    ("Railway Gazette International", "railwaygazette.com"),
    ("Metro Report International", "metro-report.com"),
    ("IRJ (International Railway Journal)", "railjournal.com"),
    ("Railway Technology", "railway-technology.com"),
    ("Railway-News", "railway-news.com"),
    ("SmartRail World", "smartrailworld.com"),
    ("Global Mass Transit", "globalmasstransit.net"),
    # ── 加分來源（產業協會/學會，更新頻率較低，能抓到算賺到）──
    ("UITP", "uitp.org"),
    ("IRSE", "irse.org"),
    ("Transit Jam", "transit-jam.com"),
]
METRO_SCOPE_FILTER = '(metro OR subway OR "light rail" OR LRT OR MRT OR tram)'

# ── 中國大陸新聞過濾（保留香港）─────────────────────────
# 程式碼層先過濾一輪，Gemini 端的查核原則再做第二道把關。
_MAINLAND_CHINA_TERMS = [
    "中国大陆", "中國大陸", "中国铁路", "中國鐵路", "China Railway",
    "北京", "Beijing", "上海", "Shanghai", "广州", "廣州", "Guangzhou",
    "深圳", "Shenzhen", "南京", "Nanjing", "武汉", "武漢", "Wuhan",
    "成都", "Chengdu", "西安", "Xi'an", "重庆", "重慶", "Chongqing",
    "天津", "Tianjin", "苏州", "蘇州", "Suzhou", "杭州", "Hangzhou",
    "郑州", "鄭州", "Zhengzhou", "长沙", "長沙", "Changsha",
    "青岛", "青島", "Qingdao", "大连", "大連", "Dalian",
    "沈阳", "瀋陽", "Shenyang", "哈尔滨", "哈爾濱", "Harbin",
    "昆明", "Kunming", "福州", "Fuzhou", "厦门", "廈門", "Xiamen",
    "无锡", "無錫", "Wuxi", "宁波", "寧波", "Ningbo", "合肥", "Hefei",
    "济南", "濟南", "Jinan", "东莞", "東莞", "Dongguan", "佛山", "Foshan",
    "长春", "長春", "Changchun", "石家庄", "石家莊", "Shijiazhuang",
    "兰州", "蘭州", "Lanzhou", "乌鲁木齐", "烏魯木齊", "Urumqi",
    "南宁", "南寧", "Nanning", "贵阳", "貴陽", "Guiyang", "太原", "Taiyuan",
    "南昌", "Nanchang", "呼和浩特", "Hohhot", "银川", "銀川", "Yinchuan",
    "西宁", "西寧", "Xining",
]
_HONGKONG_TERMS = ["香港", "Hong Kong", "MTR", "HKSAR"]


def _is_mainland_china_item(text: str) -> bool:
    """判斷文章是否屬於中國大陸（不含香港）地鐵新聞，供過濾使用。"""
    if not text:
        return False
    if any(term in text for term in _HONGKONG_TERMS):
        return False
    return any(term in text for term in _MAINLAND_CHINA_TERMS)


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

_GNEWS_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MetroWeeklyBot/4.2)"}


def _fetch_one_gnews(source_name: str, domain: str, cutoff: datetime.datetime) -> str:
    """抓取單一 Google News 代理來源（供平行呼叫使用）。"""
    query = f"site:{domain} {METRO_SCOPE_FILTER} when:{int(lookback_days)}d"
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )
    try:
        req = urllib.request.Request(url, headers=_GNEWS_HEADERS)
        with urllib.request.urlopen(req, timeout=8) as f:
            raw = f.read()
        root = ET.fromstring(raw)
        items_found: list[tuple[str, str, str, str]] = []

        for item in root.findall(".//item"):
            raw_title = (item.findtext("title") or "").strip()
            title = re.sub(r"\s*-\s*[^-]+$", "", raw_title).strip() or raw_title
            link = (item.findtext("link") or "").strip()
            desc = re.sub(r"<[^>]+>", "", item.findtext("description") or "")[:300].strip()
            pub_str = (item.findtext("pubDate") or "").strip()
            if (
                title
                and _is_recent(pub_str, cutoff)
                and not _is_mainland_china_item(f"{title} {desc}")
            ):
                items_found.append((title, link, desc, _parse_pub_date(pub_str)))

        if items_found:
            lines = [f"【新聞來源：{source_name}（共 {len(items_found)} 篇）】"]
            for t, l, d, dt in items_found[:12]:
                lines.append(f"  日期：{dt}\n  標題：{t}\n  摘要：{d}\n  連結：{l}")
            return "\n".join(lines)
        return f"【新聞來源：{source_name}】（近 {lookback_days} 天無符合範疇之新文章）"
    except Exception as exc:
        return f"【新聞來源：{source_name}】⚠️ 失敗：{exc}"


# ═══════════════════════════════════════════════════════
#  搜尋關鍵字（ddgs 多後端，補充用）
# ═══════════════════════════════════════════════════════
BASE_SEARCH_QUERIES = [
    # 技術新知（2 組，廣義關鍵字覆蓋信號/智慧化/硬體/標準）
    f"metro railway technology CBTC GoA4 AI digital twin announcement {today:%Y}",
    f"metro railway FRMCS 5G signalling battery energy rolling stock trial {today:%Y}",
    # 重大事故（3 組，含官方運安調查機構報告，不適合走 Google News site: 代理）
    f"metro subway derailment signal failure fire evacuation incident {today:%B %Y}",
    f"metro subway accident collision track intrusion service disruption {today:%B %Y}",
    f"metro subway investigation report site:ntsb.gov OR site:gov.uk/raib OR TTSB {today:%Y}",
    # 營運爭議（2 組）
    f"metro subway strike fare increase construction delay controversy {today:%B %Y}",
    f"metro transit safety crime complaints operations controversy {today:%B %Y}",
]

# ── ddgs 結果網域白名單（只保留下列媒體／機構，過濾掉地方新聞、Yahoo 等雜訊來源）──
TRUSTED_MEDIA_DOMAINS = [d for _, d in GNEWS_SOURCES]  # 與 GNEWS_SOURCES 同步，10 個專業媒體
INVESTIGATION_DOMAINS = [
    "ntsb.gov",        # 美國 NTSB
    "raib.gov.uk",     # 英國 RAIB
    "orr.gov.uk",      # 英國 ORR
    "ttsb.gov.tw",     # 台灣運安會
    "atsb.gov.au",     # 澳洲 ATSB
    "bea-tt.developpement-durable.gouv.fr",  # 法國 BEA-TT
]


def _domain_allowed(href: str, allowed_domains: list[str]) -> bool:
    """檢查連結網域是否落在白名單內（含子網域）。"""
    if not href:
        return False
    try:
        netloc = urllib.parse.urlparse(href).netloc.lower()
    except Exception:
        return False
    netloc = netloc.removeprefix("www.")
    return any(netloc == d or netloc.endswith("." + d) for d in allowed_domains)


def build_search_queries() -> tuple[list[str], set[int]]:
    queries = list(BASE_SEARCH_QUERIES)
    base_len = len(queries)
    # 第 3~7 組（事故／爭議）用新聞型搜尋，較貼近時效性
    news_indices = set(range(3, base_len + 1))
    return queries, news_indices


def _allowed_domains_for(i: int) -> list[str]:
    """第 5 組（投資調查報告）用運安機構白名單，其餘一律限定 10 個專業媒體網域。"""
    if i == 5:
        return INVESTIGATION_DOMAINS
    return TRUSTED_MEDIA_DOMAINS


def _fetch_one_ddg(i: int, query: str, use_news: bool) -> str:
    """執行單一 ddgs 查詢（供平行呼叫使用）。不重試、不睡眠，失敗就略過。"""
    news_timelimit = "w" if int(lookback_days) <= 7 else "m"
    allowed_domains = _allowed_domains_for(i)
    try:
        with DDGS() as ddgs:
            if use_news:
                results = ddgs.news(
                    query, max_results=8, timelimit=news_timelimit, backend="auto"
                )
            else:
                results = ddgs.text(
                    query, max_results=10, timelimit="m", backend="auto"
                )
        if results:
            results = [
                r for r in results
                if not _is_mainland_china_item(
                    f"{r.get('title','')} "
                    f"{r.get('body') or r.get('excerpt') or r.get('description') or ''}"
                )
                and _domain_allowed(r.get("href") or r.get("url") or "", allowed_domains)
            ]
        if results:
            lines = [f"【DDG {i}】{query}"]
            for r in results:
                body = (
                    r.get("body") or r.get("excerpt") or r.get("description") or ""
                )[:300]
                href = r.get("href") or r.get("url") or ""
                lines.append(
                    f"  標題：{r.get('title','')}\n"
                    f"  日期：{r.get('date','')}\n"
                    f"  摘要：{body}\n"
                    f"  連結：{href}"
                )
            return "\n".join(lines)
        return f"【DDG {i}】{query}\n  （無結果）"
    except Exception as exc:
        return f"【DDG {i}】{query}\n  ⚠️ {type(exc).__name__}：{str(exc)[:120]}"


def fetch_all_sources_parallel(progress_bar=None, status_text=None) -> tuple[str, str]:
    """
    平行抓取 Google News 代理 + ddgs 關鍵字搜尋（展示版）。
    所有來源同時發出請求，整體耗時取決於最慢的單一查詢，
    而非逐一序列等待，目標在 20–30 秒內完成。
    """
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=int(lookback_days))
    )
    search_queries, news_query_indices = build_search_queries()

    gnews_jobs = list(GNEWS_SOURCES)
    ddg_jobs = [(i, q, i in news_query_indices) for i, q in enumerate(search_queries, 1)]
    total = len(gnews_jobs) + len(ddg_jobs)
    done = 0

    gnews_blocks: list[str] = []
    ddg_blocks: list[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(16, max(total, 1))) as executor:
        future_map = {}
        for source_name, domain in gnews_jobs:
            fut = executor.submit(_fetch_one_gnews, source_name, domain, cutoff)
            future_map[fut] = "gnews"
        for i, query, use_news in ddg_jobs:
            fut = executor.submit(_fetch_one_ddg, i, query, use_news)
            future_map[fut] = "ddg"

        try:
            for future in concurrent.futures.as_completed(future_map, timeout=25):
                kind = future_map[future]
                try:
                    text = future.result()
                except Exception as exc:
                    text = f"⚠️ 查詢失敗：{exc}"
                (gnews_blocks if kind == "gnews" else ddg_blocks).append(text)
                done += 1
                if status_text:
                    status_text.text(f"📡 平行抓取資料中... {done}/{total} 完成")
                if progress_bar:
                    progress_bar.progress(done / total)
        except concurrent.futures.TimeoutError:
            if status_text:
                status_text.text(f"⏱️ 部分查詢逾時，已採用目前取得的 {done}/{total} 筆資料...")

    return "\n\n".join(gnews_blocks), "\n\n".join(ddg_blocks)


# ── Prompt 建立 ───────────────────────────────────────
def build_prompt(rss_results: str, ddg_results: str) -> str:
    weekday = ['一','二','三','四','五','六','日'][today.weekday()]
    search_count = len(build_search_queries()[0])
    return f"""
# 角色
你是專業捷運機電技術分析師，服務對象為台北市政府捷運工程局處長及技術同仁。

# 任務
以下是透過「Google News 代理（聚焦捷運/輕軌媒體）」與「ddgs 多後端搜尋」蒐集到的國際都市軌道交通原始資料（嚴格涵蓋近 {lookback_days} 天）。
請嚴格依照三大領域與查核原則，整理出週報（目標期間：{date_range}）。
請先合併重複來源，再保留具公共運輸安全、工程技術、營運管理參考價值的事件；不要因為來源摘要較短就直接排除。

## ━━ 第一部分：Google News 代理（Metro Report / Railway Gazette / IRJ 等捷運輕軌專業媒體）━━
{rss_results}

## ━━ 第二部分：關鍵字搜尋結果（ddgs 多後端）━━
{ddg_results}

## ⚠️ 最高查核原則（零容忍，違反即捨棄該則）
1. **只使用上方原始資料中出現的資訊**，禁止自行編造
2. **範疇限制**：本報告僅涵蓋「都市軌道交通」（捷運／輕軌／MRT／LRT／地鐵／電車），**不納入**重型鐵路、高鐵、貨運鐵路等非都市軌道系統之新聞，全球範圍皆可納入（不限定國家）
2.5 **來源限制**：下方原始資料已透過程式碼限定只抓取指定的國際專業鐵道媒體與官方運安調查機構，**不會出現地方新聞、八卦媒體等雜訊來源**；若仍看到非專業來源的內容，直接捨棄
3. **地區排除（零容忍）**：**不納入中國大陸地區**（北京、上海、廣州、深圳、南京、武漢、成都等）之地鐵／輕軌新聞；**香港、台灣及其餘國際地區皆正常納入**，不在此限
4. **日期判斷（統一嚴格標準，不分類別）**：「新聞發布日」與「事件/技術發表日」皆須在 {date_range} 內（過去 {lookback_days} 天），**超出一律捨棄，技術新知亦不例外**
5. **禁止舊聞充數**：超過上述天數限制的歷史案例一律捨棄
6. **無付費牆**：確保 URL 可公開存取，付費牆來源捨棄
7. **寧缺勿濫**：確實無符合條件者，直接回報「本週無符合條件之重大異動」
8. **數量原則（目標固定 10 則）**：請以「輸出 10 則」為目標。若第一輪嚴格篩選後不足 10 則，可在不違反上述查核原則（地區排除、時間範圍、不納入高鐵/貨運鐵路）的前提下，放寬「次要相關性」標準（例如同類別中關聯度較低、但仍屬都市軌道交通範疇的事件）來補足；**但絕對不可捏造、虛構或挪用非本週時間範圍的新聞來湊數**。若放寬後仍不足 10 則，請如實輸出實際則數即可，**結尾統計處不需說明原因，只需列出實際則數**。

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

## 範疇說明
- 全球國際捷運／輕軌／MRT／LRT 系統，不限定特定國家
- 不納入重型鐵路、高鐵、貨運鐵路等非都市軌道系統
- 不納入中國大陸地區地鐵新聞；香港、台灣及其餘國際地區正常納入

## 輸出格式（每則獨立區塊，目標固定 10 則，詳見上方數量原則）

# {report_title}
> 資料涵蓋期間：{date_range}（都市軌道交通範疇，嚴格依 {lookback_days} 天篩選）

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
⏰ **報告產出時間**：{today.strftime('%Y年%m月%d日')} 週{weekday}
"""


def extract_text(response) -> str:
    if response.text:
        return response.text
    candidates = response.candidates or []
    if candidates and candidates[0].content and candidates[0].content.parts:
        texts = [p.text for p in candidates[0].content.parts if getattr(p, "text", None)]
        if texts:
            return "\n".join(texts)
    raise ValueError("Gemini 回應無文字內容")


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
    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">
<style>
  body{{font-family:'Noto Sans TC',Arial,sans-serif;line-height:1.8;
       max-width:820px;margin:0 auto;padding:24px;color:#333}}
  h1{{color:#1a3a5c;border-bottom:3px solid #1a3a5c;padding-bottom:8px}}
  h2{{color:#2c5f8a}} h3{{color:#1a6e4a;background:#f0f8f4;padding:8px 12px;
      border-left:4px solid #1a6e4a;border-radius:0 4px 4px 0}}
  blockquote{{background:#f5f5f5;border-left:4px solid #ccc;margin:0;padding:8px 16px;color:#666}}
  li{{margin:4px 0}} a{{color:#2c5f8a}}
  hr{{border:none;border-top:1px solid #ddd;margin:24px 0}}
  strong{{color:#1a3a5c}}
  .footer{{background:#f5f8fc;padding:12px;border-radius:6px;margin-top:24px;font-size:.9em;color:#666}}
</style></head><body><p>{h}</p>
<div class="footer">📧 AI 自動產生 | Gemini + RSS + ddgs | 僅供參考，請交叉驗證原始來源</div>
</body></html>"""


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
        return None


def send_email_func(text: str, recipients: list, gmail_user: str, gmail_pass: str) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = report_title
    msg["From"]    = gmail_user
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
            s.login(gmail_user, gmail_pass)
            s.sendmail(gmail_user, recipients, msg.as_string())
        return True
    except Exception as e:
        st.error(f"寄信失敗：{e}")
        return False


# ── 立即產生報告 ──────────────────────────────────────
st.markdown("### 🚀 立即產生報告")
col_b1, col_b2, _ = st.columns([2, 2, 4])
generate_btn = col_b1.button("🤖 立即產生週報", type="primary", use_container_width=True)
send_btn     = col_b2.button("📧 產生並寄送",   use_container_width=True)

if generate_btn or send_btn:
    if not api_key:
        st.error("❌ Gemini API Key 未設定，請至 Streamlit Cloud App Settings → Secrets 填入")
    else:
        progress_bar = st.progress(0)
        status_text  = st.empty()

        try:
            # Step 1：平行抓取 Google News 代理 + ddgs 關鍵字搜尋
            status_text.text("📡 平行抓取 Google News 代理 + ddgs 關鍵字搜尋中...")
            rss_results, ddg_results = fetch_all_sources_parallel(progress_bar, status_text)

            # Step 2：Gemini 分析
            progress_bar.progress(1.0)
            status_text.text(f"🤖 {model_choice} 正在分析整理...")
            client   = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model_choice,
                contents=build_prompt(rss_results, ddg_results),
                config=types.GenerateContentConfig(temperature=0.2),
            )
            report_text = extract_text(response)

            os.makedirs("reports", exist_ok=True)
            with open("reports/latest.md", "w", encoding="utf-8") as f:
                f.write(report_text)
            with open(f"reports/report_{today.strftime('%Y%m%d')}.md", "w", encoding="utf-8") as f:
                f.write(report_text)

            st.session_state["latest_report"] = report_text
            progress_bar.empty()
            status_text.empty()
            st.success("✅ 報告產生完成！")

            if send_btn:
                recipients = [r.strip() for r in recipient_input.splitlines() if r.strip()]
                if not recipients:
                    st.warning("⚠️ 請在左側填入收件信箱")
                elif not gmail_user or not gmail_pass:
                    st.warning("⚠️ GMAIL_USER 或 GMAIL_APP_PASS 未在 Secrets 中設定")
                else:
                    ok = send_email_func(report_text, recipients, gmail_user, gmail_pass)
                    if ok:
                        st.success(f"📧 已成功寄送至：{', '.join(recipients)}")

        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"❌ 發生錯誤：{e}")
            st.info("請確認 Gemini API Key 正確，且帳號配額未超限")

# ── 報告顯示區 ──────────────────────────────────────
st.markdown("---")
st.markdown("### 📄 最新報告內容")

report_to_show = st.session_state.get("latest_report", "")
if not report_to_show:
    try:
        with open("reports/latest.md", "r", encoding="utf-8") as f:
            report_to_show = f.read()
    except FileNotFoundError:
        pass

if report_to_show:
    tab1, tab2 = st.tabs(["📋 排版預覽", "📝 原始文字"])
    with tab1:
        st.markdown(report_to_show)
        pdf_bytes = try_markdown_to_pdf_bytes(report_to_show)
        if pdf_bytes:
            st.download_button(
                "⬇️ 下載報告 PDF",
                data=pdf_bytes,
                file_name=f"metro_report_{today.strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.info("PDF 套件尚未安裝；部署後會依 requirements.txt 自動啟用 PDF 下載。")
    with tab2:
        st.text_area("原始 Markdown", report_to_show, height=600)
        st.download_button(
            "⬇️ 下載報告 (.md)",
            data=report_to_show,
            file_name=f"metro_report_{today.strftime('%Y%m%d')}.md",
            mime="text/markdown",
        )
else:
    st.markdown("""
    <div class="warn-box">
    📭 尚無報告資料。請點擊上方「立即產生週報」按鈕產生第一份報告。
    </div>""", unsafe_allow_html=True)
