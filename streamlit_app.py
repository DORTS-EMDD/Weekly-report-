"""
國際捷運技術週報 — Streamlit 展示介面
- 搜尋一：RSS 訂閱源（RSS_SOURCES 清單，每項來源皆已個別查證是否有可訂閱 RSS）
- 搜尋二：ddgs 多後端（動態精簡關鍵字以加速）
- 依左側勾選事件篩選各自的新聞 (新增「營運政策」並改為下拉收合選單)
- 嚴格排除傳統火車/高鐵，優先聚焦捷運、中運量與LRRT系統
"""

import os
import re
import time
import random
import datetime
import smtplib
import concurrent.futures
from io import BytesIO
from html import escape
import urllib.parse
from urllib.parse import urlparse, urlunparse, parse_qs
from email.utils import parsedate_to_datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from ddgs import DDGS
except ModuleNotFoundError:
    DDGS = None

try:
    from google import genai
    from google.genai import types
except (ModuleNotFoundError, ImportError):
    genai = None
    types = None

try:
    import feedparser
except ModuleNotFoundError:
    feedparser = None


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
  :root {
    --metro-blue: #12385b;
    --metro-blue-2: #1d5f8f;
    --rail-gray: #475569;
    --paper: #ffffff;
    --soft-blue: #e8f3fb;
    --soft-gray: #f5f7fa;
    --gold: #c9972b;
  }

  .block-container { padding-top: 1.3rem; }
  [data-testid="stSidebar"] { background-color: #0f2d4a; }
  [data-testid="stSidebar"], [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] p, [data-testid="stSidebar"] span,
  [data-testid="stSidebar"] div, [data-testid="stSidebar"] .stMarkdown {
    color: #f8fafc !important;
  }
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3 {
    color: #ffffff !important;
    letter-spacing: 0 !important;
  }
  [data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.22) !important;
  }
  [data-testid="stSidebar"] input,
  [data-testid="stSidebar"] textarea {
    color: #0f172a !important;
    background-color: #ffffff !important;
    border-color: rgba(255,255,255,0.45) !important;
  }
  [data-testid="stSidebar"] [data-baseweb="select"],
  [data-testid="stSidebar"] [data-baseweb="select"] *,
  [data-testid="stSidebar"] [data-baseweb="select"] div,
  [data-testid="stSidebar"] [data-baseweb="select"] span,
  [data-testid="stSidebar"] [data-baseweb="select"] input {
    color: #0f172a !important;
    background-color: #ffffff !important;
  }
  [data-baseweb="option"], [data-baseweb="option"] *,
  [role="option"], [data-baseweb="menu"] li,
  [data-baseweb="popover"] [role="option"] {
    color: #0f172a !important;
    background-color: #ffffff !important;
  }
  [data-baseweb="option"]:hover,
  [data-baseweb="option"][aria-selected="true"],
  [role="option"]:hover {
    background-color: #dbeafe !important;
    color: #0f172a !important;
  }
  [data-testid="stSidebar"] .stButton button,
  [data-testid="stSidebar"] .stButton button * {
    color: #0f172a !important;
    background-color: #f8fafc !important;
    border-color: rgba(255,255,255,0.5) !important;
  }
  [data-testid="stSidebar"] .stButton button:hover,
  [data-testid="stSidebar"] .stButton button:hover * {
    background-color: #dbeafe !important;
    color: #0f172a !important;
  }
  [data-testid="stSidebar"] [data-testid="stExpander"] {
    border: 1px solid rgba(255,255,255,0.24) !important;
    border-radius: 8px !important;
    background-color: rgba(255,255,255,0.08) !important;
    margin-bottom: 10px !important;
  }
  [data-testid="stSidebar"] [data-testid="stExpander"] summary,
  [data-testid="stSidebar"] [data-testid="stExpander"] summary * {
    color: #ffffff !important;
    background-color: transparent !important;
  }
  [data-testid="stSidebar"] [data-testid="stNumberInputStepDown"],
  [data-testid="stSidebar"] [data-testid="stNumberInputStepUp"] {
    background-color: #1d5f8f !important;
    color: white !important;
    border-color: rgba(255,255,255,0.35) !important;
  }

  .hero-card {
    background: linear-gradient(135deg, #0f2d4a 0%, #16466f 58%, #eef6fb 58%, #ffffff 100%);
    border: 1px solid #d7e3ee;
    border-radius: 10px;
    padding: 28px 30px;
    box-shadow: 0 14px 32px rgba(15, 45, 74, .14);
    margin-bottom: 18px;
  }
  .hero-eyebrow { color: #d7b46a; font-size: .9rem; font-weight: 700; margin-bottom: 6px; }
  .hero-title { color: #ffffff; font-size: 2.15rem; font-weight: 800; line-height: 1.25; margin-bottom: 8px; }
  .hero-subtitle { color: #eaf4fb; font-size: 1rem; max-width: 780px; margin-bottom: 16px; }
  .hero-meta { display: flex; flex-wrap: wrap; gap: 8px 10px; color: #12385b; }
  .hero-pill {
    background: #ffffff; border: 1px solid #d7e3ee; border-radius: 999px;
    padding: 6px 12px; font-size: .86rem; font-weight: 700;
  }

  .section-title {
    color: var(--metro-blue); font-size: 1.25rem; font-weight: 800;
    margin: 22px 0 10px;
  }
  .kpi-card {
    background: var(--paper); border: 1px solid #dbe4ee; border-radius: 8px;
    padding: 16px; min-height: 118px; box-shadow: 0 6px 18px rgba(15, 45, 74, .08);
  }
  .kpi-icon { font-size: 1.25rem; color: var(--gold); margin-bottom: 8px; }
  .kpi-num { font-size: 1.9rem; font-weight: 800; color: var(--metro-blue); line-height: 1.1; }
  .kpi-label { color: #334155; font-size: .9rem; font-weight: 700; margin-top: 4px; }
  .kpi-note { color: #64748b; font-size: .78rem; margin-top: 4px; }

  .workflow-card {
    background: #f8fbfd; border: 1px solid #dbe4ee; border-left: 4px solid var(--metro-blue-2);
    border-radius: 8px; padding: 14px; min-height: 112px;
  }
  .workflow-step { color: var(--gold); font-weight: 800; font-size: .82rem; }
  .workflow-title { color: var(--metro-blue); font-weight: 800; margin-top: 4px; }
  .workflow-desc { color: #475569; font-size: .84rem; margin-top: 4px; }

  .notice-success {
    background: #eef8f1; border: 1px solid #b9dfc6; border-left: 5px solid #2f855a;
    border-radius: 8px; padding: 14px 16px; margin: 16px 0;
  }
  .warn-box {
    background: #fff8e6; border-left: 4px solid #c9972b;
    padding: 12px 16px; border-radius: 0 8px 8px 0; margin: 12px 0;
  }

  .report-card {
    background: #ffffff; border: 1px solid #dbe4ee; border-radius: 8px;
    padding: 18px 20px; margin: 14px 0; box-shadow: 0 6px 18px rgba(15, 45, 74, .07);
  }
  .report-card h4 { color: #102f4e; margin: 8px 0 10px; font-size: 1.08rem; line-height: 1.45; }
  .report-card-body { color: #334155; font-size: .94rem; line-height: 1.75; }
  .type-badge, .status-badge {
    display: inline-block; border-radius: 999px; padding: 4px 10px;
    font-size: .78rem; font-weight: 800; margin-right: 6px;
  }
  .badge-tech { background: #dbeafe; color: #1e40af; }
  .badge-incident { background: #fee2e2; color: #b91c1c; }
  .badge-policy { background: #dcfce7; color: #166534; }
  .badge-dispute { background: #ffedd5; color: #c2410c; }
  .badge-standard { background: #ede9fe; color: #6d28d9; }
  .badge-neutral { background: #e2e8f0; color: #334155; }
  .badge-success { background: #dcfce7; color: #166534; }
  .badge-fallback { background: #e0f2fe; color: #075985; }
  .badge-empty { background: #f1f5f9; color: #475569; }
  .badge-warning { background: #fef3c7; color: #92400e; }
  .badge-error { background: #fee2e2; color: #991b1b; }
  .badge-blocked { background: #e5e7eb; color: #111827; }

  .source-health-table {
    width: 100%; border-collapse: collapse; font-size: .88rem; background: #ffffff;
    border: 1px solid #dbe4ee; border-radius: 8px; overflow: hidden;
  }
  .source-health-table th {
    background: #12385b; color: #ffffff; text-align: left; padding: 10px;
  }
  .source-health-table td {
    border-top: 1px solid #e5edf5; padding: 9px 10px; vertical-align: top;
  }
  .source-health-table tr:nth-child(even) td { background: #f8fbfd; }

  div.stButton > button[kind="primary"] {
    background: #12385b !important; border-color: #12385b !important;
    color: #ffffff !important; font-weight: 800 !important;
    min-height: 3rem; box-shadow: 0 8px 18px rgba(18,56,91,.18);
  }
  div.stButton > button[kind="primary"]:hover {
    background: #1d5f8f !important; border-color: #1d5f8f !important;
  }
  .primary-action { margin-top: 4px; }

  @media (max-width: 760px) {
    .hero-card { padding: 20px; background: linear-gradient(180deg, #0f2d4a 0%, #16466f 68%, #ffffff 68%); }
    .hero-title { font-size: 1.55rem; }
    .hero-meta { margin-top: 20px; }
    .kpi-card, .workflow-card { min-height: auto; }
  }
</style>
""", unsafe_allow_html=True)

# ── 日期與常數 ──────────────────────────────────────────────
today = datetime.date.today()

ADVANCED_TYPES = ["技術新知", "重大事故", "營運政策", "營運爭議", "規範更新"]
MIN_REPORT_ITEMS = 15
MAX_ITEMS_PER_SOURCE = 25

ADVANCED_REGIONS = [
    "日本", "韓國", "新加坡", "香港", "澳洲", "英國", "法國", "德國",
    "美國", "加拿大", "西班牙", "荷蘭", "瑞士", "義大利", "瑞典",
    "奧地利", "丹麥", "挪威",
]

DEFAULT_REGIONS = [
    "日本", "韓國", "新加坡", "香港", "澳洲", "英國", "法國", "德國",
    "美國", "加拿大", "西班牙",
]

REGION_SEARCH_TERMS = {
    "日本": "Japan Tokyo Osaka subway metro operator",
    "韓國": "Korea Seoul metro subway operator",
    "新加坡": "Singapore MRT LTA SMRT",
    "香港": "Hong Kong MTR",
    "美國": "United States New York subway Washington Metro Chicago CTA",
    "加拿大": "Canada Toronto TTC Vancouver SkyTrain Montreal REM",
    "英國": "United Kingdom London Underground Transport for London",
    "法國": "France Paris Metro RATP Grand Paris Express",
    "德國": "Germany Berlin U-Bahn Munich U-Bahn Hamburg U-Bahn",
    "西班牙": "Spain Madrid Metro Barcelona Metro CAF SENER Ineco light rail",
    "荷蘭": "Netherlands Amsterdam metro Rotterdam metro",
    "瑞士": "Switzerland Zurich tram Lausanne metro",
    "澳洲": "Australia Sydney Metro Melbourne Metro Brisbane rail",
    "義大利": "Italy Milan Metro Rome Metro Turin tram light rail",
    "瑞典": "Sweden Stockholm metro Gothenburg tram light rail",
    "奧地利": "Austria Vienna U-Bahn Wiener Linien tram metro",
    "丹麥": "Denmark Copenhagen Metro light rail",
    "挪威": "Norway Oslo Metro tram light rail",
}

STANDARDS_WATCHLIST = {
    "碰撞/出軌類": ["EN 50126", "EN 50128", "EN 50129", "IEEE 1474.1", "EN 13674-1", "UIC 860-0", "IEC 61373"],
    "觸電/電弧爆炸類": ["EN 50122", "EN 50122-2", "EN 50327", "EN 50328", "EN 50329", "IEC 62271-100", "IEC 62271-102", "IEC 60947-1", "IEC 60850"],
    "火災/中毒類": ["NFPA 130", "ASTM E119", "IEC 60754-1", "IEC 60754-2", "IEC 60332-1", "ASTM E662", "NFPA 258", "NFPA 70"],
    "結構性/爆炸性設備失效類": ["IEC 60076", "IEC 60076-11", "IEC 62695"],
}

STANDARD_UPDATE_TERMS = [
    "new edition", "revision", "amendment", "corrigendum", "draft",
    "public comment", "published", "withdrawn", "superseded",
]

BLOCKED_DOMAINS = {
    ".cn", ".ru", ".kp", ".by", ".ir",
}

ALLOWED_NEWS_DOMAINS: set[str] = set()

TRANSIT_NEWS_TERMS = '(metro OR subway OR "light rail" OR tram OR LRRT OR LRT)'

# ── 金鑰狀態 ──────────────────────────────────────────
api_key    = get_secret("GEMINI_API_KEY")
gmail_user = get_secret("GMAIL_USER")
gmail_pass = get_secret("GMAIL_APP_PASS")

# ── 側邊欄 ──────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚇 國際捷運 AI 週報")
    st.caption("臺北市政府捷運工程局｜機電系統設計處")
    st.markdown("---")

    st.markdown("### ⚙️ 模型設定")
    model_choice = st.selectbox(
        "選擇 Gemini 模型",
        ["gemini-3.1-flash-lite", "gemini-3.5-flash"],
        index=0,
    )

    st.markdown("---")
    st.markdown("### 🗓️ 搜尋期間")
    lookback_days = st.number_input(
        "新聞搜尋天數", min_value=3, max_value=30, value=7, step=1,
    )

    st.markdown("---")
    st.markdown("### 📑 新聞類型篩選")
    if "selected_types_state" not in st.session_state:
        st.session_state["selected_types_state"] = ADVANCED_TYPES.copy()

    col_t_all, col_t_clear = st.columns(2)
    if col_t_all.button("全選類型", use_container_width=True):
        st.session_state["selected_types_state"] = ADVANCED_TYPES.copy()
        for t in ADVANCED_TYPES:
            st.session_state[f"type_{t}"] = True
        st.rerun()

    if col_t_clear.button("清除類型", use_container_width=True):
        st.session_state["selected_types_state"] = []
        for t in ADVANCED_TYPES:
            st.session_state[f"type_{t}"] = False
        st.rerun()

    selected_types = []
    with st.expander("選擇新聞類型", expanded=False):
        for t in ADVANCED_TYPES:
            checked = t in st.session_state["selected_types_state"]
            if st.checkbox(t, value=checked, key=f"type_{t}"):
                selected_types.append(t)

    st.session_state["selected_types_state"] = selected_types
    if selected_types:
        st.caption("已選：" + "、".join(selected_types))
    else:
        st.warning("⚠️ 請至少選擇一種新聞類型。")

    standards_enabled = "規範更新" in selected_types

    st.markdown("---")
    st.markdown("### 🌏 國家/地區篩選")
    scope_mode = st.radio(
        "報導範圍",
        ["指定先進國家/地區", "全球（安全白名單來源）"],
        index=0,
        help="全球模式不以國家刪除新聞；指定模式才套用下方先進國家/地區清單。",
    )
    if "selected_regions_state" not in st.session_state:
        st.session_state["selected_regions_state"] = DEFAULT_REGIONS.copy()

    col_all, col_clear = st.columns(2)
    if col_all.button("全選國家", use_container_width=True):
        st.session_state["selected_regions_state"] = ADVANCED_REGIONS.copy()
        for region in ADVANCED_REGIONS:
            st.session_state[f"region_{region}"] = True
        st.rerun()

    if col_clear.button("清除國家", use_container_width=True):
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
    if scope_mode == "全球（安全白名單來源）":
        st.caption("全球模式：不以國家/地區限制刪除新聞，仍套用來源安全規則。")
        st.caption("切回指定模式時會沿用目前勾選清單。")
    elif selected_regions:
        st.caption("已選：" + "、".join(selected_regions))
    else:
        st.warning("請至少選擇一個國家/地區。")

    st.markdown("---")
    st.markdown("### 📚 規範更新追蹤")
    standard_count = sum(len(v) for v in STANDARDS_WATCHLIST.values())
    if standards_enabled:
        st.success(f"已啟用規範更新追蹤：{standard_count} 項標準")
        with st.expander("追蹤清單", expanded=False):
            for category, standards in STANDARDS_WATCHLIST.items():
                st.markdown(f"**{category}**：{', '.join(standards)}")
    else:
        st.caption("勾選「規範更新」後，才會啟用 Google News RSS 與 ddgs 規範搜尋。")

    st.markdown("---")
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
    st.caption("💡 **新增收件人**：直接在上方輸入框換行追加即可。")

    st.markdown("---")
    st.markdown("### 📅 排程說明")
    st.markdown("""
- ⏰ **每週一 08:00** 自動執行
- ☁️ 由 **GitHub Actions** 雲端排程
- 📧 自動寄送至公務信箱
    """)

    st.markdown("---")
    st.markdown("### 🟢 系統狀態")
    with st.expander("🔑 系統狀態", expanded=False):
        st.markdown(f"Gemini API Key：{'✅' if api_key else '❌'}")
        st.markdown(f"Gmail 帳號：{'✅' if gmail_user else '❌'}")
        st.markdown(f"Gmail 密碼：{'✅' if gmail_pass else '❌'}")
        st.markdown(f"google-genai 套件：{'✅' if genai and types else '❌'}")
        st.markdown(f"ddgs 套件：{'✅' if DDGS else '❌'}")
        st.markdown(f"feedparser 套件：{'✅' if feedparser else '❌'}")

    st.markdown("---")
    st.markdown("### 🔧 除錯模式")
    show_raw_debug = st.checkbox(
        "顯示原始搜尋資料",
        value=False,
        help="開啟後，產生報告時會另外保留 RSS／ddgs 抓到的原始文字（Gemini 篩選前），"
             "方便判斷篇數過少是因為「原始資料本來就少」還是「Gemini 篩太嚴」。",
    )

    st.markdown("---")
    st.caption("🏛️ 台北市政府捷運工程局\nAI 競賽展示系統")

week_start = today - datetime.timedelta(days=int(lookback_days))
date_range = f"{week_start.strftime('%Y年%m月%d日')} 至 {today.strftime('%Y年%m月%d日')}"
report_title = f"【{today.strftime('%Y/%m/%d')}】國際捷運技術新知、重大事件週報"
is_global_scope = scope_mode == "全球（安全白名單來源）"
active_regions = [] if is_global_scope else selected_regions


def google_news_search_url(query: str, hl: str = "en-US", gl: str = "US", ceid_lang: str = "en") -> str:
    return (
        "https://news.google.com/rss/search?q="
        f"{urllib.parse.quote(query)}&hl={hl}&gl={gl}&ceid={gl}:{ceid_lang}"
    )


def google_news_site_proxy_url(
    domain: str,
    days: int,
    keywords: str = TRANSIT_NEWS_TERMS,
    hl: str = "en-US",
    gl: str = "US",
    ceid_lang: str = "en",
) -> str:
    query = f"site:{domain} {keywords} when:{max(1, min(int(days), 60))}d"
    return google_news_search_url(query, hl=hl, gl=gl, ceid_lang=ceid_lang)


# ═══════════════════════════════════════════════════════
#  RSS 訂閱源（官方 RSS 優先；必要時由抓取函式 fallback 至 Google News site: 代理）
# ═══════════════════════════════════════════════════════
RSS_SOURCES = [
    ("Railway Gazette International（已併入 Metro Report International 都市軌道報導）",
     "https://www.railwaygazette.com/149.rss"),
    ("Railway Gazette Urban rail（Google News代理）",
     google_news_site_proxy_url("railwaygazette.com", int(lookback_days), '("urban rail" OR metro OR tram OR "light rail")')),
    ("International Railway Journal (IRJ)", "https://www.railjournal.com/feed/"),
    ("IRJ metro / light rail（Google News代理）",
     google_news_site_proxy_url("railjournal.com", int(lookback_days), '(metro OR "light rail" OR tram OR LRRT)')),
    ("Railway Technology", "https://www.railway-technology.com/feed/"),
    ("Railway-News", "https://railway-news.com/feed/"),
    ("Global Railway Review", "https://www.globalrailwayreview.com/feed/"),
    ("Intelligent Transport", "https://www.intelligenttransport.com/feed/"),
    ("Urban Transport Magazine（Google News代理）",
     google_news_site_proxy_url("urban-transport-magazine.com", int(lookback_days))),
    ("Mass Transit Magazine", "https://www.masstransitmag.com/rss"),
    ("METRO Magazine Rail（Google News代理）",
     google_news_site_proxy_url("metro-magazine.com", int(lookback_days), '(rail OR metro OR "light rail" OR tram)')),
    ("Smart Cities Dive Transportation（Google News代理）",
     google_news_site_proxy_url("smartcitiesdive.com", int(lookback_days), '(transportation OR transit OR metro OR "light rail")')),
    ("Railway Age light rail / passenger rail（Google News代理）",
     google_news_site_proxy_url("railwayage.com", int(lookback_days), '("light rail" OR "passenger rail" OR metro OR transit)')),
    ("UITP（無官方RSS，改用Google News代理）",
     google_news_site_proxy_url("uitp.org", int(lookback_days))),
    # 2026-07 查證：masstransit.network 的 RSS 端點實際回傳的是「會員名錄」頁面
    # （人名列表），不是新聞內容，已移除，改依賴下方已驗證有效的 Global Mass Transit。
    ("Global Mass Transit", "https://www.globalmasstransit.net/feed"),
    # 東洋經濟原本用全站 RSS，抓到的 20 篇裡沒有一篇是鐵道新聞（全是投資理財/職場/美食）。
    # 改用 Google News 代理鎖定 site:toyokeizai.net + 鐵道關鍵字，才會是真的鐵道新聞。
    ("東洋經濟 Online 鐵道（Google News代理，鎖定 site:toyokeizai.net + 鐵道）",
     "https://news.google.com/rss/search?q=site:toyokeizai.net+%E9%90%B5%E9%81%93&hl=ja&gl=JP&ceid=JP:ja"),
    ("乗りものニュース", "https://trafficnews.jp/feed"),
    ("鉄道総合技術研究所 RTRI（無官方RSS，改用Google News代理）",
     google_news_site_proxy_url("rtri.or.jp", int(lookback_days), '(鉄道 OR 地下鉄 OR 新交通システム)', "ja", "JP", "ja")),
    ("Transit Jam", "https://transitjam.com/feed/"),
    ("TfL 官方新聞（Google News代理）",
     google_news_site_proxy_url("tfl.gov.uk", int(lookback_days), '(Tube OR Underground OR Elizabeth Line OR tram OR DLR)', "en-GB", "GB", "en")),
    ("MTA 官方新聞（Google News代理）",
     google_news_site_proxy_url("mta.info", int(lookback_days), '(subway OR metro OR signal OR accessibility OR safety)')),
    ("WMATA 官方新聞（Google News代理）",
     google_news_site_proxy_url("wmata.com", int(lookback_days), '(Metro OR Metrorail OR rail OR safety)')),
    ("TTC 官方新聞（Google News代理）",
     google_news_site_proxy_url("ttc.ca", int(lookback_days), '(subway OR streetcar OR signal OR fleet OR safety)', "en-CA", "CA", "en")),
    ("TransLink 官方新聞（Google News代理）",
     google_news_site_proxy_url("translink.ca", int(lookback_days), '(SkyTrain OR rail OR transit OR safety)', "en-CA", "CA", "en")),
    ("RATP 官方新聞（Google News代理）",
     google_news_site_proxy_url("ratp.fr", int(lookback_days), '(metro OR tramway OR RER OR automatisation OR securite)', "fr", "FR", "fr")),
    ("Société des grands projets 官方新聞（Google News代理）",
     google_news_site_proxy_url("societedesgrandsprojets.fr", int(lookback_days), '("Grand Paris Express" OR metro OR gare)', "fr", "FR", "fr")),
    ("LTA 官方新聞（Google News代理）",
     google_news_site_proxy_url("lta.gov.sg", int(lookback_days), '(MRT OR LRT OR rail OR Thomson-East Coast Line)', "en-SG", "SG", "en")),
    ("MTR 官方新聞（Google News代理）",
     google_news_site_proxy_url("mtr.com.hk", int(lookback_days), '(MTR OR railway OR metro OR signalling)', "zh-HK", "HK", "zh-Hant")),
    ("Seoul Metro 官方新聞（Google News代理）",
     google_news_site_proxy_url("seoulmetro.co.kr", int(lookback_days), '(지하철 OR 도시철도 OR 안전 OR 열차)', "ko", "KR", "kr")),
    ("Tokyo Metro 官方新聞（Google News代理）",
     google_news_site_proxy_url("tokyometro.jp", int(lookback_days), '(東京メトロ OR 地下鉄 OR 安全 OR 車両)', "ja", "JP", "ja")),
]

# ═══════════════════════════════════════════════════════
#  依勾選國家動態產生的 Google News 地區代理來源
# ═══════════════════════════════════════════════════════
# 背景：上方 RSS_SOURCES 幾乎都是歐美鐵道媒體，對日韓星港等亞洲市場的
# 捷運新聞覆蓋率實測為 0（見程式修訂紀錄）。這裡針對使用者勾選的國家，
# 用當地語言關鍵字動態組出 Google News RSS 代理，補上這塊缺口。
# 每個 tuple：(顯示名稱, 查詢關鍵字, hl 語系, gl 國別, ceid 語言代碼)
REGION_NEWS_QUERIES: dict[str, list[tuple[str, str, str, str, str]]] = {
    "日本": [("Google News地區代理－日本地下鉄/メトロ",
             "(地下鉄 OR メトロ OR 新交通システム) -ゲーム -Steam -スタンプラリー -アニメ", "ja", "JP", "ja")],
    "韓國": [("Google News地區代理－韓國地下鐵",
             "(지하철 OR 도시철도 OR 경전철)", "ko", "KR", "kr")],
    "新加坡": [("Google News地區代理－Singapore MRT",
              "(MRT OR LTA OR SMRT Singapore)", "en-SG", "SG", "en")],
    "香港": [("Google News地區代理－香港港鐵",
             "(港鐵 OR MTR 香港)", "zh-HK", "HK", "zh-Hant")],
    "澳洲": [("Google News地區代理－Australia Metro",
             "(Sydney Metro OR Melbourne Metro OR Brisbane Metro)", "en-AU", "AU", "en")],
    "英國": [("Google News地區代理－UK Underground",
             "(London Underground OR TfL Tube)", "en-GB", "GB", "en")],
    "法國": [("Google News地區代理－France Metro",
             "(Metro Paris OR RATP OR Grand Paris Express)", "fr", "FR", "fr")],
    "德國": [("Google News地區代理－Germany U-Bahn",
             "(U-Bahn OR S-Bahn Metro) -Spiel -Kinofilm -Videospiel", "de", "DE", "de")],
    "西班牙": [("Google News地區代理－Spain Metro/Light Rail",
              "(Madrid Metro OR Barcelona Metro OR CAF OR SENER OR Ineco OR tranvia)", "es", "ES", "es")],
    "荷蘭": [("Google News地區代理－Netherlands Metro",
             "(Amsterdam metro OR Rotterdam metro)", "nl", "NL", "nl")],
    "瑞士": [("Google News地區代理－Switzerland Metro/Tram",
             "(Zurich tram OR Lausanne metro)", "de-CH", "CH", "de")],
    "美國": [("Google News地區代理－US Subway/Metro",
             "(subway OR metro rail transit) United States", "en-US", "US", "en")],
    "加拿大": [("Google News地區代理－Canada Metro",
              "(TTC Toronto OR SkyTrain Vancouver OR REM Montreal)", "en-CA", "CA", "en")],
    "義大利": [("Google News地區代理－Italy Metro/Tram",
              "(Milan Metro OR Rome Metro OR tram OR metropolitana)", "it", "IT", "it")],
    "瑞典": [("Google News地區代理－Sweden Metro/Tram",
             "(Stockholm metro OR Gothenburg tram OR light rail)", "sv", "SE", "sv")],
    "奧地利": [("Google News地區代理－Austria U-Bahn/Tram",
              "(Vienna U-Bahn OR Wiener Linien OR tram)", "de-AT", "AT", "de")],
    "丹麥": [("Google News地區代理－Denmark Metro/Light Rail",
             "(Copenhagen Metro OR Odense Letbane OR light rail)", "da", "DK", "da")],
    "挪威": [("Google News地區代理－Norway Metro/Tram",
             "(Oslo Metro OR Sporveien OR tram OR light rail)", "no", "NO", "no")],
}


def build_region_news_sources(regions: list[str], days: int) -> list[tuple[str, str]]:
    """依勾選國家動態組出 Google News 地區代理 RSS 來源清單。"""
    sources: list[tuple[str, str]] = []
    days = max(1, min(int(days), 60))
    for region in regions:
        for label, keyword, hl, gl, lang in REGION_NEWS_QUERIES.get(region, []):
            query = f"{keyword} when:{days}d"
            url = (
                "https://news.google.com/rss/search?q="
                f"{urllib.parse.quote(query)}&hl={hl}&gl={gl}&ceid={gl}:{lang}"
            )
            sources.append((label, url))
    return sources


def build_standards_news_sources(days: int) -> list[tuple[str, str]]:
    """只有勾選規範更新時，才組出標準版本狀態的 Google News RSS 代理來源。"""
    sources: list[tuple[str, str]] = []
    days = max(1, min(int(days), 60))
    update_terms = " OR ".join(f'"{term}"' for term in STANDARD_UPDATE_TERMS)
    for category, standards in STANDARDS_WATCHLIST.items():
        for standard in standards:
            query = f'"{standard}" ({update_terms}) when:{days}d'
            sources.append((f"規範更新代理－{category}－{standard}", google_news_search_url(query)))
    return sources


def render_main_dashboard(source_count: int, standards_count: int) -> None:
    selected_regions_note = "全球模式" if is_global_scope else f"{len(selected_regions)} / {len(ADVANCED_REGIONS)}"
    st.markdown(
        f"""
        <div class="hero-card">
          <div class="hero-eyebrow">臺北市政府捷運工程局｜機電系統設計處</div>
          <div class="hero-title">國際捷運技術週報 AI 自動產生系統</div>
          <div class="hero-subtitle">國際技術新知、重大事故、營運政策、營運爭議與規範更新之自動化監測</div>
          <div class="hero-meta">
            <span class="hero-pill">今日日期：{today.strftime('%Y/%m/%d')}</span>
            <span class="hero-pill">資料涵蓋：{week_start.strftime('%Y/%m/%d')} - {today.strftime('%Y/%m/%d')}</span>
            <span class="hero-pill">模型：{model_choice}</span>
            <span class="hero-pill">範圍：{scope_mode}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">關鍵指標</div>', unsafe_allow_html=True)
    kpi_items = [
        ("📑", len(selected_types), "追蹤主題數", "固定依報告排序輸出"),
        ("🌏", selected_regions_note, "預設/選取國家數", "指定模式套用國家邊界"),
        ("🗓️", lookback_days, "新聞搜尋天數", date_range),
        ("📡", source_count, "RSS/代理來源數", "含官方與 Google News 代理"),
        ("🎯", f">= {MIN_REPORT_ITEMS}", "AI 報告目標篇數", "不足時列明原因"),
        ("📚", standards_count if standards_enabled else "未啟用", "規範追蹤數量", "勾選規範更新後啟用"),
    ]
    cols = st.columns(3)
    for idx, (icon, num, label, note) in enumerate(kpi_items):
        cols[idx % 3].markdown(
            f"""
            <div class="kpi-card">
              <div class="kpi-icon">{icon}</div>
              <div class="kpi-num">{escape(str(num))}</div>
              <div class="kpi-label">{escape(label)}</div>
              <div class="kpi-note">{escape(str(note))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-title">系統流程</div>', unsafe_allow_html=True)
    workflow_items = [
        ("01", "蒐集候選資料", "RSS / Google News / ddgs"),
        ("02", "安全與連結過濾", "排除高風險來源與無效 URL"),
        ("03", "AI 分類與摘要", "依固定類型排序與去重"),
        ("04", "形成機設處啟示", "可能影響系統、可參考作法、追蹤建議"),
        ("05", "輸出與寄送", "下載 PDF 或寄送公務信箱"),
    ]
    wcols = st.columns(5)
    for idx, (step, title, desc) in enumerate(workflow_items):
        wcols[idx].markdown(
            f"""
            <div class="workflow-card">
              <div class="workflow-step">STEP {step}</div>
              <div class="workflow-title">{escape(title)}</div>
              <div class="workflow-desc">{escape(desc)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


initial_region_sources = build_region_news_sources(active_regions, int(lookback_days))
initial_standard_sources = build_standards_news_sources(int(lookback_days)) if standards_enabled else []
render_main_dashboard(
    source_count=len(RSS_SOURCES) + len(initial_region_sources) + len(initial_standard_sources),
    standards_count=sum(len(v) for v in STANDARDS_WATCHLIST.values()),
)


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


class FeedFetchError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def create_requests_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; TaipeiMetroAIWeekly/5.0; +https://www.dorts.gov.taipei/)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    return session


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


def _extract_site_domain_from_google_news(url: str) -> str:
    try:
        query = parse_qs(urlparse(url).query).get("q", [""])[0]
    except Exception:
        return ""
    match = re.search(r"site:([^\s\)]+)", query)
    return match.group(1).lower().removeprefix("www.") if match else ""


def _fallback_google_news_url(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    if "news.google.com" in parsed.netloc:
        return None
    domain = parsed.netloc.lower().removeprefix("www.")
    if not domain:
        return None
    return google_news_site_proxy_url(domain, int(lookback_days))


def _is_blocked_host(host: str) -> bool:
    host = host.lower().strip(".")
    if not host:
        return False
    return any(host.endswith(suffix) for suffix in BLOCKED_DOMAINS)


def _is_allowed_host(host: str) -> bool:
    if not ALLOWED_NEWS_DOMAINS:
        return True
    return any(_host_matches(host, domain) for domain in ALLOWED_NEWS_DOMAINS)


def _is_valid_news_url(url: str, source_href: str = "") -> tuple[bool, str]:
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
    if _is_blocked_host(host):
        return False, "被安全規則排除"
    if not _is_allowed_host(host):
        return False, "不在來源白名單"
    return True, ""


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


def _fetch_feed(session: requests.Session, url: str):
    if feedparser is None:
        raise FeedFetchError("parse error", "feedparser 套件未安裝")
    try:
        response = session.get(url, timeout=15)
    except requests.exceptions.Timeout as exc:
        raise FeedFetchError("timeout", str(exc)) from exc
    except requests.exceptions.RequestException as exc:
        raise FeedFetchError("parse error", str(exc)) from exc

    if response.status_code == 403:
        raise FeedFetchError("403", "HTTP 403 Forbidden")
    if response.status_code >= 400:
        raise FeedFetchError("parse error", f"HTTP {response.status_code}")

    parsed = feedparser.parse(response.content)
    if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
        raise FeedFetchError("parse error", str(getattr(parsed, "bozo_exception", "RSS/Atom parse error")))
    return parsed


def _items_from_parsed_feed(parsed_feed, cutoff: datetime.datetime, seen_titles: set[str], seen_urls: set[str]) -> tuple[list[dict], int, int, int]:
    items: list[dict] = []
    invalid_count = 0
    blocked_count = 0
    duplicate_count = 0

    for entry in getattr(parsed_feed, "entries", []):
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        desc = (entry.get("summary") or entry.get("description") or "").strip()
        pub_str = _entry_pub_str(entry)
        source_href = _entry_source_href(entry)

        if not title or not _is_recent(pub_str, cutoff):
            continue

        is_valid, reason = _is_valid_news_url(link, source_href=source_href)
        if not is_valid:
            if reason == "被安全規則排除":
                blocked_count += 1
            else:
                invalid_count += 1
            continue

        title_key = _normalize_title(title)
        url_key = _dedupe_url(link)
        if title_key in seen_titles or url_key in seen_urls:
            duplicate_count += 1
            continue
        seen_titles.add(title_key)
        seen_urls.add(url_key)

        items.append({
            "title": title,
            "link": link,
            "summary": re.sub(r"<[^>]+>", " ", desc)[:500],
            "date": _parse_pub_date(pub_str),
            "source_href": source_href,
        })

    return items, invalid_count, blocked_count, duplicate_count


def _status_record(source_name: str, method: str, status: str, item_count: int, error_message: str = "") -> dict:
    return {
        "source_name": source_name,
        "method": method,
        "status": status,
        "item_count": item_count,
        "error_message": error_message,
    }


def _method_for_url(url: str) -> str:
    return "Google News 代理" if "news.google.com" in _domain_from_url(url) else "官方 RSS"


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
    sources: list[tuple[str, str]] | None = None,
    status_text=None,
    return_status: bool = False,
) -> str | tuple[str, list[dict]]:
    """通用 RSS/Atom 抓取函式，使用 feedparser + requests retry/backoff。"""
    if sources is None:
        sources = RSS_SOURCES

    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=min(int(lookback_days) * 2, 60))
    )
    all_blocks: list[str] = []
    source_statuses: list[dict] = []
    seen_titles: set[str] = set()
    seen_urls: set[str] = set()
    session = create_requests_session()

    for idx, (source_name, url) in enumerate(sources, 1):
        if status_text:
            status_text.text(f"📡 RSS {idx}/{len(sources)}：{source_name}...")

        method = _method_for_url(url)
        valid_source, source_reason = _is_valid_news_url(url)
        if not valid_source and source_reason == "被安全規則排除":
            source_statuses.append(_status_record(source_name, method, "被安全規則排除", 0, source_reason))
            all_blocks.append(f"【RSS來源：{source_name}】（被安全規則排除）")
            continue

        try:
            parsed_feed = _fetch_feed(session, url)
            items_found, invalid_count, blocked_count, duplicate_count = _items_from_parsed_feed(
                parsed_feed, cutoff, seen_titles, seen_urls
            )
            if items_found:
                all_blocks.append(_format_items_block(source_name, items_found))
                source_statuses.append(_status_record(source_name, method, "成功", min(len(items_found), MAX_ITEMS_PER_SOURCE)))
            else:
                status = "被安全規則排除" if blocked_count and not invalid_count else "無文章"
                message = f"無有效候選；無效連結 {invalid_count}、安全排除 {blocked_count}、重複 {duplicate_count}"
                all_blocks.append(f"【RSS來源：{source_name}】（{status}）")
                source_statuses.append(_status_record(source_name, method, status, 0, message))
        except FeedFetchError as exc:
            fallback_url = _fallback_google_news_url(url)
            if fallback_url:
                try:
                    parsed_feed = _fetch_feed(session, fallback_url)
                    items_found, invalid_count, blocked_count, duplicate_count = _items_from_parsed_feed(
                        parsed_feed, cutoff, seen_titles, seen_urls
                    )
                    if items_found:
                        all_blocks.append(_format_items_block(f"{source_name}（fallback Google News）", items_found))
                        source_statuses.append(
                            _status_record(source_name, "Google News fallback", "fallback 成功", min(len(items_found), MAX_ITEMS_PER_SOURCE), f"官方 RSS 失敗：{exc.message}")
                        )
                    else:
                        status = "被安全規則排除" if blocked_count and not invalid_count else "無文章"
                        message = f"官方 RSS 失敗：{exc.message}；fallback 無有效候選；無效連結 {invalid_count}、安全排除 {blocked_count}、重複 {duplicate_count}"
                        all_blocks.append(f"【RSS來源：{source_name}】（{status}）")
                        source_statuses.append(_status_record(source_name, "Google News fallback", status, 0, message))
                except FeedFetchError as fallback_exc:
                    all_blocks.append(f"【RSS來源：{source_name}】（{exc.status}）")
                    source_statuses.append(
                        _status_record(source_name, method, exc.status, 0, f"官方 RSS：{exc.message}；fallback：{fallback_exc.message}")
                    )
            else:
                all_blocks.append(f"【RSS來源：{source_name}】（{exc.status}）")
                source_statuses.append(_status_record(source_name, method, exc.status, 0, exc.message))

    raw_text = "\n\n".join(all_blocks)
    if return_status:
        return raw_text, source_statuses
    return raw_text


# ═══════════════════════════════════════════════════════
#  精簡化 DDGS 關鍵字搜尋 (加速優化版)
# ═══════════════════════════════════════════════════════
def build_search_queries() -> tuple[list[str], set[int]]:
    """依據勾選的選項動態合併搜尋字，大幅減少發送次數"""
    queries = []
    news_indices = set()

    # 1. 核心通用關鍵字（只查有勾的）
    if "技術新知" in selected_types:
        queries.extend([
            f"metro LRRT automated guideway transit technology {today:%Y}",
            f"metro subway CBTC GoA4 driverless {today:%Y}",
            f"鉄道 新交通システム 地下鉄 技術 {today:%Y}"
        ])
    if "重大事故" in selected_types:
        queries.extend([
            f"metro subway train derailment collision incident {today:%B %Y}",
            f"鉄道 地下鉄 事故 脱線 運休 {today:%Y年%m月}"
        ])
    if "營運政策" in selected_types:
        queries.extend([
            f"metro subway policy passenger safety regulation {today:%B %Y}",
            f"鉄道 地下鉄 規則 安全対策 {today:%Y年%m月}"
        ])
    if "營運爭議" in selected_types:
        queries.extend([
            f"metro subway transit strike delay controversy {today:%B %Y}",
            f"鉄道 地下鉄 遅延 争議 {today:%Y年%m月}"
        ])
    if "規範更新" in selected_types:
        update_terms = " OR ".join(f'"{term}"' for term in STANDARD_UPDATE_TERMS)
        for category, standards in STANDARDS_WATCHLIST.items():
            for standard in standards:
                idx = len(queries) + 1
                queries.append(f'"{standard}" ({update_terms}) metro rail standard update {today:%Y}')
                news_indices.add(idx)

    # 2. 地區合併關鍵字：指定模式才套用 ADVANCED_REGIONS；全球模式不以國家限制刪除新聞。
    for i, region in enumerate(active_regions):
        term = REGION_SEARCH_TERMS.get(region, region)
        if "技術新知" in selected_types:
            queries.append(f"{term} metro LRRT subway upgrade press release {today:%B %Y}")

        # 將事故、政策、爭議合併為一個查詢字串，精簡發送數量
        if any(t in selected_types for t in ["重大事故", "營運政策", "營運爭議"]):
            idx = len(queries) + 1
            queries.append(f"{term} metro subway incident strike policy controversy {today:%B %Y}")
            news_indices.add(idx)

    return queries, news_indices


def _run_single_query(i: int, query: str, use_news: bool, news_timelimit: str) -> tuple[int, str, str, list[dict], str]:
    """執行單一查詢（純運算/網路請求，不觸碰 Streamlit API，可安全在背景執行緒執行）"""
    # 隨機抖動起跑時間，避免多執行緒同時擊中 DDGS 造成瞬間流量觸發限流
    time.sleep(random.uniform(0.1, 0.6))
    result_items: list[dict] = []
    final_backend = ""
    final_status = "略過"

    for backend in ["auto", "bing"]:
        for attempt in range(1, 3):
            try:
                with DDGS() as ddgs:
                    if use_news:
                        results = ddgs.news(query, max_results=10, timelimit=news_timelimit, backend=backend)
                    else:
                        results = ddgs.text(query, max_results=10, timelimit="m", backend=backend)
                if results:
                    for r in results:
                        body = (r.get("body") or r.get("excerpt") or r.get("description") or "")[:250]
                        href = r.get("href") or r.get("url") or ""
                        title = (r.get("title") or "").strip()
                        if not title:
                            continue
                        is_valid, reason = _is_valid_news_url(href)
                        if not is_valid:
                            continue
                        result_items.append({
                            "title": title,
                            "summary": body,
                            "link": href,
                            "date": r.get("date") or r.get("published") or "日期未知",
                        })
                    final_backend = backend
                    final_status = "成功" if result_items else "無結果"
                else:
                    final_backend = backend
                    final_status = "無結果"
                break
            except Exception as exc:
                wait = attempt * 1.0 + random.uniform(0.5, 1.5)
                time.sleep(wait)
                if not any(k in str(exc) for k in ("Ratelimit", "429", "403")):
                    break

        if result_items:
            break

    return i, query, final_backend or "auto", result_items, final_status


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


def run_duckduckgo_searches(progress_bar=None, status_text=None) -> str:
    """執行 DDGS 多後端搜尋（平行化版本：查詢數變多但改為併發執行，速度不會被拖慢）"""
    if not selected_types:
        return "未勾選任何新聞類型，略過搜尋。"
    if DDGS is None:
        return "ddgs 套件未安裝，略過 ddgs 搜尋；請確認 requirements.txt 已包含 ddgs。"

    search_queries, news_query_indices = build_search_queries()
    total = len(search_queries)
    news_timelimit = "w" if int(lookback_days) <= 7 else "m"
    results_map: dict[int, str] = {}
    done_count = 0
    seen_titles: set[str] = set()
    seen_urls: set[str] = set()

    # 同時最多 6 條併發，兼顧速度與避免被 DDGS 判定為濫用流量
    max_workers = max(1, min(6, total))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_single_query, i, query, i in news_query_indices, news_timelimit): i
            for i, query in enumerate(search_queries, 1)
        }
        for future in concurrent.futures.as_completed(futures):
            i, query, backend, items, status = future.result()
            deduped_items: list[dict] = []
            for item in items:
                title_key = _normalize_title(item["title"])
                url_key = _dedupe_url(item["link"])
                if title_key in seen_titles or url_key in seen_urls:
                    continue
                seen_titles.add(title_key)
                seen_urls.add(url_key)
                deduped_items.append(item)
            results_map[i] = _format_ddg_block(i, backend, query, deduped_items, status)
            done_count += 1
            if status_text:
                status_text.text(f"🔍 已完成搜尋 {done_count:02d}/{total}...")
            if progress_bar:
                progress_bar.progress(done_count / total)

    return "\n\n".join(results_map[i] for i in sorted(results_map))


# ── Prompt 建立 ───────────────────────────────────────
def build_prompt(rss_results: str, ddg_results: str, rss_sources: list[tuple[str, str]] | None = None) -> str:
    if rss_sources is None:
        rss_sources = RSS_SOURCES
    weekday = ['一','二','三','四','五','六','日'][today.weekday()]
    search_count = len(build_search_queries()[0])
    selected_types_str = "、".join(selected_types) if selected_types else "無"
    report_order = "、".join(ADVANCED_TYPES)
    source_names = "\n".join("   - " + name for name, _ in rss_sources)
    if is_global_scope:
        scope_instruction = (
            "本次採全球模式：不得用國家/地區清單刪除新聞。仍須套用來源安全規則、有效 URL 規則，"
            "並聚焦都市捷運、地下鐵、中運量、輕軌、AGT、LRRT/LRT。"
        )
        scope_list = "全球（安全白名單來源）；不套用 ADVANCED_REGIONS 國家邊界。"
    else:
        scope_instruction = (
            "本次採指定先進國家/地區模式：完成主題判斷後，必須再確認事件發生地或標準公告主體"
            "落在指定清單內；不在清單內者不得納入正式新聞。"
        )
        scope_list = "\n".join("- " + r for r in active_regions)

    standards_instruction = ""
    if "規範更新" in selected_types:
        standards_instruction = f"""
## 規範更新特別規則
1. 只有原始資料中明確出現下列標準編號與公開公告/新聞，才可列入規範更新；不得依模型記憶補寫。
2. 不可重製、翻譯或摘要標準全文，只能整理公開的版本狀態、公告、摘要與可能影響。
3. 關鍵字範圍包含：{", ".join(STANDARD_UPDATE_TERMS)}。
4. 每則規範更新請使用固定格式：
### [規範更新] 標準編號：主題
- **更新狀態**：
- **涉及風險類別**：
- **可能影響機電系統**：
- **對捷運機電規劃/規範之啟示**：
- **資料來源**：[來源名稱](完整 https:// URL)

規範追蹤清單：
{chr(10).join("- " + category + "：" + "、".join(standards) for category, standards in STANDARDS_WATCHLIST.items())}
"""

    return f"""
# 角色
你是專業捷運機電技術分析師，服務對象為台北市政府捷運工程局處長及技術同仁。

# 任務
以下是透過「RSS 訂閱源」與「ddgs 多後端搜尋」蒐集到的原始資料。
請依照使用者勾選的類型，整理出具參考價值的週報（目標期間：{date_range}）。
你只能根據下方 raw RSS/ddgs 候選資料輸出；不得使用模型記憶、常識推測或外部未提供資訊補寫。

## ━━ 第一部分：RSS 訂閱源（涵蓋 {len(rss_sources)} 個媒體/地區代理，見下方權重清單）━━
{rss_results}

## ━━ 第二部分：關鍵字搜尋結果━━
{ddg_results}

## 篩選與優先級指示
1. **新聞類型過濾**：本次報告**只能**包含以下使用者勾選的新聞類型：【{selected_types_str}】。若不屬於這些類型，請直接忽略。
   - **技術新知**：機電、號誌、車輛、土木等工程技術。
   - **重大事故**：出軌、追撞、火災、嚴重系統當機。
   - **營運政策**：捷運站內安檢新規、乘車規則變動（如禁帶大型鋰電池/滑板車）、安全管理政策。
   - **營運爭議**：罷工、預算超支、票價爭議、合約糾紛、服務品質爭議。
   - **規範更新**：標準版本、修訂、勘誤、草案、徵詢、公告、撤回、取代等公開狀態。
2. **最高優先級（專注捷運與LRRT，排除一般鐵路/高鐵）**：本報告是提供給北市府捷運局的國際週報，請**嚴格過濾並排除**傳統客運/貨運鐵路（火車、城際列車）與高速鐵路（HSR）的新聞。請**絕對優先保留並聚焦**於國際上的**「都市捷運系統（Metro / Subway / Underground）」**以及**「中運量 / 輕軌 / 膠輪系統（LRRT / AGT / LRT）」**的新聞，並給予最大篇幅。
3. **來源權重**：請優先採納「第一部分：RSS 訂閱源」中實際出現的來源（本次共 {len(rss_sources)} 個，清單如下），這些是本次真正抓取到的媒體，**不要**引用或想像清單以外的媒體名稱：
{source_names}
4. **報告排序固定**：正式報告必須依序輸出：{report_order}。未勾選的類型不要出現；已勾選但無合格資料者，該類別寫「本期無合格資料」。
5. **【絕對禁止腦補、嚴格日期查核與來源查核】（違反本條視為報告失敗）**：
   - 每一則新聞的「發布/事件日期」**必須**直接取自原始資料中該則內容本身標註的日期字串（RSS 的「日期：」欄位，或關鍵字搜尋結果摘要中出現的日期）。**禁止**依你自己知識庫中對該事件、公司或專案的既有印象去推測、換算或臆造日期。
   - 若某則原始資料**沒有**明確可辨識的日期，或日期含糊到無法判斷是哪一天，**直接捨棄該則**，不要用「近期」「今年」等模糊字眼帶過，也不要自行補上一個日期。
   - 判斷「未來日期」時，**只看該則報導本身的發布/刊登日期**是否晚於今天（{today.strftime('%Y-%m-%d')}）；若是，才視為不合理並剔除。**但**如果報導本身發布日期是合理的過去/現在日期，只是內文「引述」了某項政策的未來生效日（例如報導於 6 月底刊出，內容提到「規定將於 7 月 1 日起實施」），這屬於政策內容的一部分，**不可**僅因內文出現未來日期就整則剔除——請保留該則，並在內容中如實寫出「即將於某日起生效」。
   - 若同一事件在原始資料中找不到，但你「記得」曾經發生過類似新聞，**一律視為未提供資料**，不要用記憶內容補寫。你只能整理「第一部分」與「第二部分」中實際出現的文字，不能新增任何未出現於原始資料的事實、數字或日期。
   - **來源必須是該則事件本身的具體新聞文章連結**：「資料來源」欄位填入的網址，**必須**是原始資料中該則內容自己標註的「連結：」網址，且該網址指向的必須是報導這件事本身的新聞文章頁面。**嚴禁**引用網站首頁、路網圖、票務頁面、會員名錄、活動總覽頁等非新聞頁面來充當來源，也**嚴禁**在原始資料中找不到對應連結時，挪用同一媒體其他頁面的網址頂替。若某則事件在原始資料中沒有對應的具體文章連結，即使內容看起來合理，也必須**整則捨棄**。
    - 不得為了湊數引用無具體新聞頁、首頁、社群頁、會員頁、活動首頁或模型記憶。
6. **數量要求**：正式報告目標至少 {MIN_REPORT_ITEMS} 則。若高信度新聞不足，請另設「候補觀察」區，只收錄原始資料中存在但信心較低或日期/範圍需追蹤的候選，不得捏造。若最後正式新聞仍不足 {MIN_REPORT_ITEMS} 則，必須在結尾列明不足原因，例如：來源不足、日期不明、非捷運、來源不合格。
7. **國家/地區規則**：{scope_instruction}

## 國家/地區範圍
{scope_list}

{standards_instruction}

## 輸出格式（每則獨立區塊，正式報告至少 {MIN_REPORT_ITEMS} 則）

# {report_title}
> 資料涵蓋期間：{date_range} 
> 篩選類型：{selected_types_str}
> 報導範圍：{scope_mode}

---

## 技術新知
## 重大事故
## 營運政策
## 營運爭議
## 規範更新

### [填入該則所屬之分類：技術新知/重大事故/營運政策/營運爭議/規範更新] 國家/地區或標準編號：（一句有力主標題）
* **發布/事件日期**：（原文發布年月日）
* **國家/地區**：（全球模式仍需標示；規範更新可填公告機構/標準體系）
* **相關機電系統**：車輛/號誌/通訊/供電/月臺門/機廠設備/系統整合/資安/土建界面
* **信心水準**：高/中/低
* **納入理由**：（說明為何對捷運機電系統或機設處有參考價值）
* **事件摘要**：
  - （列點精要說明，3–5 點）
* **技術/政策關鍵字**：（英漢對照）
* **資料來源**：[來源名稱](完整 https:// 網址)
* **【臺北捷運局啟示】**
  - **可能影響系統**：
  - **可參考作法**：
  - **後續追蹤建議**：

---

## 候補觀察（必要時）
- 僅可列入原始資料中存在、但信心水準較低或仍需查證的候選；必須標示不足原因。

## 結尾（必填）
---
📊 **本週統計**：共 N 則 
⚠️ **不足 {MIN_REPORT_ITEMS} 則原因**：（若正式新聞少於 {MIN_REPORT_ITEMS} 則必填；若達標可寫「已達標」）
🔍 **執行搜尋次數**：RSS/地區代理 {len(rss_sources)} 源 + ddgs {search_count} 次精簡搜尋
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
<div class="footer">📧 AI 自動產生 | 僅供參考，請交叉驗證原始來源</div>
</body></html>"""


def markdown_fragment_to_html(md: str) -> str:
    h = escape(md)
    h = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", h)
    h = re.sub(r"\[(.+?)\]\((https?://[^\s\)]+)\)", r'<a href="\2" target="_blank">\1</a>', h)
    lines = []
    for line in h.splitlines():
        if line.startswith("- ") or line.startswith("* "):
            lines.append(f"<li>{line[2:]}</li>")
        elif not line.strip():
            lines.append("<br>")
        else:
            lines.append(line)
    return "<br>".join(lines)


def category_badge_class(category: str) -> str:
    return {
        "技術新知": "badge-tech",
        "重大事故": "badge-incident",
        "營運政策": "badge-policy",
        "營運爭議": "badge-dispute",
        "規範更新": "badge-standard",
    }.get(category, "badge-neutral")


def detect_category(text: str) -> str:
    for category in ADVANCED_TYPES:
        if category in text:
            return category
    return "其他"


def count_report_items(report_md: str) -> int:
    count = 0
    for match in re.finditer(r"^###\s+(.+)$", report_md, flags=re.MULTILINE):
        heading = match.group(1)
        if any(category in heading for category in ADVANCED_TYPES):
            count += 1
    return count


def has_candidate_observations(report_md: str) -> bool:
    return "候補觀察" in report_md and not re.search(r"候補觀察[^\n]*\n\s*(?:無|本期無)", report_md)


def render_report_cards(report_md: str) -> None:
    parts = re.split(r"(?m)^###\s+", report_md)
    if len(parts) <= 1:
        st.markdown(report_md)
        return

    intro = parts[0].strip()
    if intro:
        st.markdown(intro)

    for part in parts[1:]:
        if not part.strip():
            continue
        lines = part.splitlines()
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        category = detect_category(heading)
        st.markdown(
            f"""
            <div class="report-card">
              <span class="type-badge {category_badge_class(category)}">{escape(category)}</span>
              <h4>{escape(heading)}</h4>
              <div class="report-card-body">{markdown_fragment_to_html(body)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def status_badge(status: str) -> str:
    class_name = {
        "成功": "badge-success",
        "fallback 成功": "badge-fallback",
        "無文章": "badge-empty",
        "timeout": "badge-warning",
        "403": "badge-error",
        "parse error": "badge-error",
        "被安全規則排除": "badge-blocked",
    }.get(status, "badge-neutral")
    label = {
        "成功": "✅ 成功",
        "fallback 成功": "↪ fallback 成功",
        "無文章": "○ 無文章",
        "timeout": "⏱ timeout",
        "403": "403",
        "parse error": "parse error",
        "被安全規則排除": "安全排除",
    }.get(status, status)
    return f'<span class="status-badge {class_name}">{escape(label)}</span>'


def render_source_health_dashboard(statuses: list[dict]) -> None:
    if not statuses:
        st.info("尚無來源健康資料；產生報告後會在此顯示各來源狀態。")
        return

    st.markdown('<div class="section-title">來源健康儀表板</div>', unsafe_allow_html=True)
    status_order = ["成功", "fallback 成功", "無文章", "timeout", "403", "parse error", "被安全規則排除"]
    counts = {status: sum(1 for row in statuses if row.get("status") == status) for status in status_order}
    metric_cols = st.columns(7)
    for idx, status in enumerate(status_order):
        metric_cols[idx].metric(status, counts[status])

    rows = []
    for row in statuses:
        rows.append(
            "<tr>"
            f"<td>{escape(row.get('source_name', ''))}</td>"
            f"<td>{escape(row.get('method', ''))}</td>"
            f"<td>{status_badge(row.get('status', ''))}</td>"
            f"<td>{escape(str(row.get('item_count', 0)))}</td>"
            f"<td>{escape(row.get('error_message', ''))}</td>"
            "</tr>"
        )
    table = (
        '<table class="source-health-table">'
        "<thead><tr><th>來源</th><th>方法</th><th>狀態</th><th>候選數</th><th>訊息</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    st.markdown(table, unsafe_allow_html=True)


def markdown_to_pdf_bytes(md: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
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


def _soft_wrap_long_tokens(text: str, chunk: int = 45) -> str:
    """在超長無空白字串（如 Google News 長網址）中每隔 chunk 字元插入零寬空白，
    讓 reportlab 能夠換行、不會爆出版面；零寬空白不影響複製貼上後的文字內容。"""
    words = text.split(" ")
    out = []
    for w in words:
        if len(w) > chunk:
            w = "\u200b".join(w[i:i + chunk] for i in range(0, len(w), chunk))
        out.append(w)
    return " ".join(out)


def raw_debug_to_pdf_bytes(raw_rss: str, raw_ddg: str) -> bytes:
    """把「原始搜尋資料（Gemini 篩選前）」的純文字內容轉成 PDF，
    方便使用者下載保存，不用再從網頁手動複製。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    for style_name in ("Title", "Heading2", "BodyText"):
        styles[style_name].fontName = "MSung-Light"
        styles[style_name].leading = max(styles[style_name].leading, 13)
    styles["BodyText"].fontSize = 8.5
    styles["BodyText"].leading = 12

    def _section(title: str, content: str, story: list):
        story.append(Paragraph(escape(title), styles["Title"]))
        story.append(Spacer(1, 10))
        if not content.strip():
            story.append(Paragraph("（無資料）", styles["BodyText"]))
            return
        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if not line:
                story.append(Spacer(1, 4))
                continue
            wrapped = _soft_wrap_long_tokens(line)
            if line.startswith("【"):
                story.append(Spacer(1, 6))
                story.append(Paragraph(escape(wrapped), styles["Heading2"]))
            else:
                story.append(Paragraph(escape(wrapped), styles["BodyText"]))

    story: list = []
    _section(f"📡 RSS 原始資料（{today.strftime('%Y-%m-%d')}）", raw_rss, story)
    story.append(PageBreak())
    _section(f"🔍 ddgs 原始資料（{today.strftime('%Y-%m-%d')}）", raw_ddg, story)

    doc.build(story)
    return buffer.getvalue()


def try_raw_debug_to_pdf_bytes(raw_rss: str, raw_ddg: str) -> bytes | None:
    try:
        return raw_debug_to_pdf_bytes(raw_rss, raw_ddg)
    except ModuleNotFoundError:
        return None


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
        pdf_part.add_header("Content-Disposition", "attachment", filename=f"metro_report_{today.strftime('%Y%m%d')}.pdf")
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
st.markdown('<div class="section-title">報告產出</div>', unsafe_allow_html=True)
st.markdown('<div class="primary-action"></div>', unsafe_allow_html=True)
col_b1, _ = st.columns([3, 5])
generate_btn = col_b1.button("🚀 產生國際捷運 AI 週報", type="primary", use_container_width=True)
send_btn = False

if generate_btn or send_btn:
    if not api_key:
        st.error("❌ Gemini API Key 未設定，請至 Streamlit Cloud App Settings → Secrets 填入")
    elif genai is None or types is None:
        st.error("❌ google-genai 套件未安裝，請確認 requirements.txt 已包含 google-genai。")
    elif not selected_types:
        st.error("❌ 尚未勾選新聞類型，請至左側選單勾選想要搜尋的主題。")
    elif not is_global_scope and not active_regions:
        st.error("❌ 指定先進國家/地區模式下，請至少勾選一個國家/地區。")
    else:
        progress_bar = st.progress(0)
        status_text  = st.empty()

        try:
            # Step 1：RSS 訂閱源 + 指定模式地區代理 + 規範更新代理
            region_sources = build_region_news_sources(active_regions, int(lookback_days))
            standards_sources = build_standards_news_sources(int(lookback_days)) if standards_enabled else []
            combined_sources = RSS_SOURCES + region_sources + standards_sources
            status_text.text(
                f"📡 抓取 {len(combined_sources)} 個 RSS / Google News 代理來源..."
            )
            rss_results, source_statuses = fetch_rss_feeds(
                combined_sources, status_text=status_text, return_status=True
            )
            st.session_state["latest_rss_raw"] = rss_results
            st.session_state["latest_source_statuses"] = source_statuses

            # Step 2：加速版 ddgs 搜尋
            status_text.text("🔍 開始執行加速版關鍵字搜尋...")
            ddg_results = run_duckduckgo_searches(progress_bar, status_text)
            st.session_state["latest_ddg_raw"] = ddg_results

            if show_raw_debug:
                os.makedirs("reports", exist_ok=True)
                with open(f"reports/raw_rss_{today.strftime('%Y%m%d')}.txt", "w", encoding="utf-8") as f:
                    f.write(rss_results)
                with open(f"reports/raw_ddg_{today.strftime('%Y%m%d')}.txt", "w", encoding="utf-8") as f:
                    f.write(ddg_results)

            # Step 3：Gemini 分析
            progress_bar.progress(1.0)
            status_text.text(f"🤖 {model_choice} 正在進行智慧過濾整理（約 15–40 秒）...")
            client   = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model_choice,
                contents=build_prompt(rss_results, ddg_results, combined_sources),
                config=types.GenerateContentConfig(temperature=0.2),
            )
            report_text = extract_text(response)

            os.makedirs("reports", exist_ok=True)
            with open("reports/latest.md", "w", encoding="utf-8") as f:
                f.write(report_text)
            with open(f"reports/report_{today.strftime('%Y%m%d')}.md", "w", encoding="utf-8") as f:
                f.write(report_text)

            st.session_state["latest_report"] = report_text
            formal_count = count_report_items(report_text)
            st.session_state["latest_report_summary"] = {
                "formal_count": formal_count,
                "has_candidate_observations": has_candidate_observations(report_text),
                "has_standards": "規範更新" in report_text,
            }
            progress_bar.empty()
            status_text.empty()
            summary = st.session_state["latest_report_summary"]
            st.markdown(
                f"""
                <div class="notice-success">
                  <strong>✅ 報告已完成</strong><br>
                  正式新聞：{formal_count} 則｜
                  候補觀察：{'有' if summary['has_candidate_observations'] else '無'}｜
                  規範更新：{'包含' if summary['has_standards'] else '未包含'}｜
                  可下載 PDF，也可寄送 Email。
                </div>
                """,
                unsafe_allow_html=True,
            )

        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"❌ 發生錯誤：{e}")
            st.info("請確認 Gemini API Key 正確，且帳號配額未超限")

# ── 報告顯示區 ──────────────────────────────────────
st.markdown("---")
raw_rss = st.session_state.get("latest_rss_raw", "")
raw_ddg = st.session_state.get("latest_ddg_raw", "")
source_statuses = st.session_state.get("latest_source_statuses", [])

if source_statuses:
    render_source_health_dashboard(source_statuses)

st.markdown('<div class="section-title">分類結果呈現</div>', unsafe_allow_html=True)

report_to_show = st.session_state.get("latest_report", "")
if not report_to_show:
    try:
        with open("reports/latest.md", "r", encoding="utf-8") as f:
            report_to_show = f.read()
    except FileNotFoundError:
        pass

if report_to_show:
    tab1, tab2 = st.tabs(["📋 分類卡片", "📝 原始文字"])
    with tab1:
        render_report_cards(report_to_show)
    with tab2:
        st.text_area("原始 Markdown", report_to_show, height=600)

    st.markdown('<div class="section-title">輸出與寄送</div>', unsafe_allow_html=True)
    pdf_bytes = try_markdown_to_pdf_bytes(report_to_show)
    raw_pdf_bytes = try_raw_debug_to_pdf_bytes(raw_rss, raw_ddg) if (raw_rss or raw_ddg) else None
    out1, out2, out3 = st.columns(3)
    with out1:
        if pdf_bytes:
            st.download_button(
                "📄 下載正式週報 PDF",
                data=pdf_bytes,
                file_name=f"metro_report_{today.strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.info("PDF 套件尚未安裝；部署後會依 requirements.txt 自動啟用 PDF 下載。")
    with out2:
        if raw_pdf_bytes:
            st.download_button(
                "🧾 下載原始資料 PDF",
                data=raw_pdf_bytes,
                file_name=f"raw_search_data_{today.strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.button("🧾 下載原始資料 PDF", disabled=True, use_container_width=True)
            st.caption("產生報告後會提供原始資料 PDF。")
    with out3:
        send_latest_btn = st.button("📧 寄送至公務信箱", use_container_width=True)
        if send_latest_btn:
            recipients = [r.strip() for r in recipient_input.splitlines() if r.strip()]
            if not recipients:
                st.warning("⚠️ 請在左側填入收件信箱")
            elif not gmail_user or not gmail_pass:
                st.warning("⚠️ GMAIL_USER 或 GMAIL_APP_PASS 未在 Secrets 中設定")
            else:
                ok = send_email_func(report_to_show, recipients, gmail_user, gmail_pass)
                if ok:
                    st.success(f"📧 已成功寄送至：{', '.join(recipients)}")
else:
    st.markdown("""
    <div class="warn-box">
    📭 尚無報告資料。請點擊上方「產生國際捷運 AI 週報」按鈕產生第一份報告。
    </div>""", unsafe_allow_html=True)

# ── 原始搜尋資料（除錯用）────────────────────────────
if show_raw_debug and (raw_rss or raw_ddg):
    with st.expander("🔎 原始資料與 AI 篩選前候選池（除錯用）", expanded=False):
        st.caption(
            "這裡是 RSS／ddgs 實際抓到、丟給 Gemini 的原始文字。"
            "如果這裡本來就沒什麼內容，代表是搜尋源撈得不夠廣；"
            "如果這裡內容很多但最終報告篇數很少，代表是日期、來源或 prompt 篩選規則較嚴。"
        )

        rss_blocks = raw_rss.count("【RSS來源：")
        rss_with_data = raw_rss.count("有效候選")
        rss_no_article = raw_rss.count("（無文章）")
        rss_blocked = raw_rss.count("（被安全規則排除）")
        ddg_blocks = raw_ddg.count("【搜尋 ")
        ddg_no_result = raw_ddg.count("無結果")

        c_d1, c_d2, c_d3, c_d4 = st.columns(4)
        c_d1.metric("RSS 有效來源", f"{rss_with_data}/{rss_blocks}")
        c_d2.metric("RSS 無文章/安全排除", rss_no_article + rss_blocked)
        c_d3.metric("ddgs 查詢總數", ddg_blocks)
        c_d4.metric("ddgs 無結果", ddg_no_result)

        with st.expander("📡 RSS 原始資料全文", expanded=False):
            st.text_area("RSS raw", raw_rss, height=400, label_visibility="collapsed")
        with st.expander("🔍 ddgs 原始資料全文", expanded=False):
            st.text_area("ddgs raw", raw_ddg, height=400, label_visibility="collapsed")
