"""
國際捷運技術週報 — Streamlit 展示介面 v4.1
- 搜尋一：RSS 訂閱源（主要；六大媒體，無限速）
- 搜尋二：ddgs 多後端（次要；DuckDuckGo + Bing + Yahoo，帶重試）
- 收件人欄位使用 session_state 保留編輯狀態
- 下拉選單文字顯示修正（黑字）
"""

import os
import re
import time
import random
import datetime
import smtplib
from io import BytesIO
from html import escape
import urllib.request
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

ADVANCED_REGIONS = [
    "日本", "韓國", "新加坡", "香港",
    "澳洲", "英國", "法國", "德國", "荷蘭",
    "瑞士", "美國", "加拿大",
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
        help="事故與營運爭議依此期間篩選；技術新知可納入 2 倍天數（最多 30 天）。",
    )

    st.markdown("### 🌏 重點國家")

    default_regions = ["日本", "韓國", "新加坡", "香港"]

    if "selected_regions_state" not in st.session_state:
        st.session_state["selected_regions_state"] = default_regions.copy()

    col_all, col_clear = st.columns(2)

    if col_all.button("全選", use_container_width=True):
        st.session_state["selected_regions_state"] = ADVANCED_REGIONS.copy()
        for region in ADVANCED_REGIONS:
            st.session_state[f"region_{region}"] = True
        st.rerun()

    if col_clear.button("清除", use_container_width=True):
        st.session_state["selected_regions_state"] = []
        for region in ADVANCED_REGIONS:
            st.session_state[f"region_{region}"] = False
        st.rerun()

    selected_regions = []

    with st.expander("選擇國家", expanded=False):
        for region in ADVANCED_REGIONS:
            checked = region in st.session_state["selected_regions_state"]
            if st.checkbox(region, value=checked, key=f"region_{region}"):
                selected_regions.append(region)

    st.session_state["selected_regions_state"] = selected_regions

    if selected_regions:
        st.caption("已選：" + "、".join(selected_regions))
    else:
        st.warning("請至少選擇一個國家/地區。")

    with st.expander("🔍 搜尋後端設定", expanded=False):
        st.caption("ddgs 補充搜尋使用的後端（至少選一個）")
        use_ddg   = st.checkbox("DuckDuckGo（預設首選）", value=True)
        use_bing  = st.checkbox("Bing（限速時備援）",      value=True)
        use_yahoo = st.checkbox("Yahoo（最終備援）",        value=True)
    selected_backends = (
        (["auto"]  if use_ddg   else []) +
        (["bing"]  if use_bing  else []) +
        (["yahoo"] if use_yahoo else [])
    )
    if not selected_backends:
        st.warning("⚠️ 請至少選一個搜尋後端。")
        selected_backends = ["auto"]

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
    (c2, str(len(selected_regions)), "重點國家/地區"),
    (c3, f"{lookback_days}", "新聞搜尋天數"),
]:
    col.markdown(
        f'<div class="stat-card"><div class="stat-num">{num}</div>'
        f'<div class="stat-label">{label}</div></div>',
        unsafe_allow_html=True,
    )

with st.expander("主題領域與重點地區"):
    col_area, col_region = st.columns(2)
    with col_area:
        st.markdown("""
**主題領域**
- 技術新知
- 重大事故
- 營運爭議
        """)
    with col_region:
        st.markdown("""
**重點國家/地區**
- 日本、韓國、新加坡、香港、澳洲
- 英國、法國、德國、荷蘭、瑞士
- 美國、加拿大
        """)


# ═══════════════════════════════════════════════════════
#  RSS 訂閱源（主要；無配額限制）
# ═══════════════════════════════════════════════════════
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

def fetch_rss_feeds(status_text=None) -> str:
    """從六大國際鐵道 RSS 取得文章（依使用者設定的新聞搜尋天數過濾）。"""
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=min(int(lookback_days) * 2, 30))
    )
    all_blocks: list[str] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MetroWeeklyBot/4.1)"}
    ATOM = "http://www.w3.org/2005/Atom"

    for idx, (source_name, url) in enumerate(RSS_SOURCES, 1):
        if status_text:
            status_text.text(f"📡 RSS {idx}/{len(RSS_SOURCES)}：{source_name}...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as f:
                raw = f.read()
            root = ET.fromstring(raw)
            items_found: list[tuple[str, str, str, str]] = []

            for item in root.findall(".//item"):
                title   = (item.findtext("title") or "").strip()
                link    = (item.findtext("link")  or "").strip()
                desc    = (item.findtext("description") or "").strip()[:400]
                pub_str = (item.findtext("pubDate") or "").strip()
                if title and _is_recent(pub_str, cutoff):
                    items_found.append((title, link, desc, _parse_pub_date(pub_str)))

            if not items_found:
                for entry in root.findall(f".//{{{ATOM}}}entry"):
                    title   = (entry.findtext(f"{{{ATOM}}}title") or "").strip()
                    link_el = entry.find(f"{{{ATOM}}}link")
                    link    = link_el.get("href", "") if link_el is not None else ""
                    summ    = (entry.findtext(f"{{{ATOM}}}summary") or "").strip()[:400]
                    pub_str = (
                        entry.findtext(f"{{{ATOM}}}published")
                        or entry.findtext(f"{{{ATOM}}}updated") or ""
                    ).strip()
                    if title and _is_recent(pub_str, cutoff):
                        items_found.append((title, link, summ, _parse_pub_date(pub_str)))

            if items_found:
                lines = [f"【RSS來源：{source_name}（共 {len(items_found)} 篇）】"]
                for t, l, d, dt in items_found[:12]:
                    lines.append(
                        f"  日期：{dt}\n  標題：{t}\n  摘要：{d}\n  連結：{l}"
                    )
                all_blocks.append("\n".join(lines))
            else:
                all_blocks.append(f"【RSS來源：{source_name}】（近30天無新文章）")
        except Exception as exc:
            all_blocks.append(f"【RSS來源：{source_name}】⚠️ 失敗：{exc}")

    return "\n\n".join(all_blocks)


# ═══════════════════════════════════════════════════════
#  搜尋關鍵字（ddgs 多後端，補充用）
# ═══════════════════════════════════════════════════════
BASE_SEARCH_QUERIES = [
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
    # 地區查詢依使用者選擇動態生成，見 build_search_queries()
]
FALLBACK_BACKENDS = ["auto", "bing", "yahoo"]


def build_search_queries() -> tuple[list[str], set[int]]:
    queries = list(BASE_SEARCH_QUERIES)
    base_len = len(queries)
    news_indices = set(range(12, base_len))

    for region in selected_regions:
        term = REGION_SEARCH_TERMS.get(region, region)
        start = len(queries)
        queries.extend([
            f"{term} metro rail technology upgrade press release {today:%B %Y}",
            f"{term} metro subway incident disruption accident {today:%B %Y}",
            f"{term} metro transit fare strike construction delay controversy {today:%B %Y}",
        ])
        news_indices.update({start + 1, start + 2})

    return queries, news_indices


def run_duckduckgo_searches(progress_bar=None, status_text=None) -> str:
    """
    執行基礎關鍵字與使用者選定國家/地區的補充搜尋（ddgs v9 多後端）。
    限速時自動切換後備後端（bing / yahoo），最多重試3次。
    """
    search_queries, news_query_indices = build_search_queries()
    total = len(search_queries)
    all_blocks: list[str] = []
    news_timelimit = "w" if int(lookback_days) <= 7 else "m"

    for i, query in enumerate(search_queries, 1):
        if status_text:
            status_text.text(f"🔍 ddgs 搜尋 {i:02d}/{total}：{query[:50]}...")
        if progress_bar:
            progress_bar.progress(i / total)

        use_news = i in news_query_indices
        result_block = None

        for backend in selected_backends:
            for attempt in range(1, 3):
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
                                or r.get("description") or ""
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
                    break
                except Exception as exc:
                    err = str(exc)
                    is_rate = any(
                        k in err for k in
                        ("Ratelimit", "429", "403", "vqd", "No results")
                    )
                    wait = (2 ** attempt) * 3 + random.uniform(1, 4)
                    time.sleep(wait)
                    if not is_rate:
                        result_block = (
                            f"【DDG {i}】{query}\n"
                            f"  ⚠️ {type(exc).__name__}: {err[:120]}"
                        )
                        break

            if result_block and "無結果" not in result_block and "⚠️" not in result_block:
                break

        all_blocks.append(
            result_block
            or f"【DDG {i}】{query}\n  ⚠️ 三個後端均無法取得結果，已略過"
        )
        time.sleep(random.uniform(2.0, 5.0))

    return "\n\n".join(all_blocks)


# ── Prompt 建立 ───────────────────────────────────────
def build_prompt(rss_results: str, ddg_results: str) -> str:
    weekday = ['一','二','三','四','五','六','日'][today.weekday()]
    search_count = len(build_search_queries()[0])
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
2. **國家/地區限制（依領域分級，最高優先）**：
   - **領域 A 技術新知**：不限定國家，全球範圍皆可納入，**但一律排除「中國」（含中國大陸各城市，如北京、上海、廣州、深圳、廈門等）**
   - **領域 B 事故分析、領域 C 營運爭議**：**只能**納入以下使用者勾選之國家/地區：
     **{', '.join(selected_regions)}**
     其他國家（含中國、含未勾選國家）的事故或爭議新聞一律**完全忽略，不得納入**
3. **日期判斷（依類別分級）**：
   - 事故類、爭議類：「新聞發布日」與「事件發生日」皆須在 {date_range} 內（**嚴格執行，超出即捨棄**）
   - 技術新知類：「新聞發布日」或「技術發表/測試日」須在過去 {min(int(lookback_days) * 2, 30)} 天內
4. **禁止舊聞充數**：超過上述天數限制的歷史案例一律捨棄
5. **無付費牆**：確保 URL 可公開存取，付費牆來源捨棄
6. **寧缺勿濫**：確實無符合條件者，直接回報「本週無符合條件之重大異動」
7. **數量原則**：若原始資料足夠，至少輸出 8 則；若不足 8 則，說明是因來源或日期條件不足，而非自行補舊聞。

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

## 地區範圍說明
- 技術新知（領域 A）：全球皆可納入，唯獨排除中國
- 事故分析、營運爭議（領域 B、C）：僅限以下國家/地區
{chr(10).join('  - ' + r for r in selected_regions)}

## 輸出格式（每則獨立區塊，目標 8–15 則）

# {report_title}
> 資料涵蓋期間：{date_range}（技術新知可納入近 {min(int(lookback_days) * 2, 30)} 天，全球範圍，排除中國）

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
🔍 **執行搜尋次數**：RSS {len(RSS_SOURCES)} 源 + ddgs {search_count} 次關鍵字搜尋
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
            # Step 1：RSS 訂閱源（主要，穩定）
            status_text.text("📡 抓取 RSS 訂閱源（Railway Gazette / IRJ 等）...")
            rss_results = fetch_rss_feeds(status_text=status_text)

            # Step 2：ddgs 搜尋（補充）
            status_text.text("🔍 開始 ddgs 多後端關鍵字搜尋...")
            ddg_results = run_duckduckgo_searches(progress_bar, status_text)

            # Step 3：Gemini 分析
            progress_bar.progress(1.0)
            status_text.text(f"🤖 {model_choice} 正在分析整理（約 20–60 秒）...")
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

# ── 系統架構說明 ──────────────────────────────────────
with st.expander("📐 系統架構說明"):
    st.markdown("""
```
GitHub Actions（排程：每週一 08:00 台灣時間）
        ↓
    main.py
        ├── 【主要】RSS 訂閱源（6 大媒體；無 API 金鑰、無配額限制）
        │       Railway Gazette / IRJ / Railway Technology /
        │       Global Railway Review / Intelligent Transport / UITP
        ├── 【補充】ddgs 多後端搜尋（20 組關鍵字；DDG → Bing → Yahoo 自動切換）
        ├── Gemini API（分析整理為繁體中文週報）
        └── Gmail SMTP → 自動寄送至公務信箱
```
    """)
    ca, cb = st.columns(2)
    with ca:
        st.markdown("""
**✅ 完全免費**
- GitHub Actions：2,000 分鐘/月
- Gemini Flash：免費配額每日足用
- RSS 訂閱源：完全免費、無限速
- ddgs：開源多後端（DDG/Bing/Yahoo）
- Gmail SMTP：無限制
- Streamlit Cloud：免費部署
        """)
    with cb:
        st.markdown("""
**🔒 安全設計**
- 金鑰存於 GitHub Secrets / Streamlit Secrets
- 程式碼中無任何硬碼金鑰
- Gmail 使用應用程式密碼（非登入密碼）
- 報告僅寄送至指定信箱

**🔄 容錯設計**
- RSS 無限速，不受 GitHub Actions IP 限制
- ddgs 限速時自動切換 Bing / Yahoo 後端
- 每次查詢 2~5 秒隨機延遲，降低觸發限速機率
        """)
