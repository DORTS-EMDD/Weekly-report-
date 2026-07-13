"""
國際捷運技術週報 — Streamlit 展示介面
- 搜尋一：RSS 訂閱源（RSS_SOURCES 清單，每項來源皆已個別查證是否有可訂閱 RSS）
- 搜尋二：ddgs 多後端（動態精簡關鍵字以加速）
- 依左側勾選事件篩選各自的新聞 (新增「營運政策」並改為下拉收合選單)
- 嚴格排除傳統火車/高鐵，優先聚焦捷運、中運量與LRRT系統
"""

import os
import re
import json
import hashlib
import time
import random
import difflib
import datetime
import smtplib
import concurrent.futures
from io import BytesIO
from html import escape, unescape
from pathlib import Path
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
    --dorts-blue: #005bac;
    --dorts-cyan: #00a3d9;
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
    margin: .45rem 0 .55rem !important;
  }
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
    font-size: 1rem !important;
    margin: .35rem 0 .15rem !important;
  }
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    margin-bottom: .25rem !important;
  }
  [data-testid="stSidebar"] .stRadio,
  [data-testid="stSidebar"] .stSelectbox,
  [data-testid="stSidebar"] .stNumberInput,
  [data-testid="stSidebar"] .stTextArea {
    margin-bottom: .35rem !important;
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
  [data-testid="InputInstructions"] {
    display: none !important;
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
  .report-summary-card {
    background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 12px 14px; margin: 10px 0 16px;
  }
  .report-summary-card .report-card-body { line-height: 1.45; }
  .type-badge {
    display: inline-block; border-radius: 999px; padding: 4px 10px;
    font-size: .78rem; font-weight: 800; margin-right: 6px;
  }
  .badge-tech { background: #dbeafe; color: #1e40af; }
  .badge-incident { background: #fee2e2; color: #b91c1c; }
  .badge-policy { background: #dcfce7; color: #166534; }
  .badge-dispute { background: #ffedd5; color: #c2410c; }
  .badge-standard { background: #ede9fe; color: #6d28d9; }
  .badge-neutral { background: #e2e8f0; color: #334155; }
  div.stButton > button[kind="primary"] {
    background: #12385b !important; border-color: #12385b !important;
    color: #ffffff !important; font-weight: 800 !important;
    min-height: 3rem; box-shadow: 0 8px 18px rgba(18,56,91,.18);
  }
  div.stButton > button[kind="primary"]:hover {
    background: #1d5f8f !important; border-color: #1d5f8f !important;
  }
  .primary-action { margin-top: 4px; }

  /* Minimal presentation layer */
  html, body, [class*="css"] {
    font-family: Inter, "Noto Sans TC", "Microsoft JhengHei", Arial, sans-serif;
    color: #111827;
  }
  .block-container { max-width: 1180px; padding-top: 1.8rem; }
  [data-testid="stSidebar"] {
    background: #f8fafc !important;
    border-right: 1px solid #e5e7eb !important;
  }

/* 左側 sidebar 整體內容往上拉 */
[data-testid="stSidebar"] > div:first-child {
    padding-top: 0 !important;
}

[data-testid="stSidebar"] > div:first-child > div:first-child {
    padding-top: 0 !important;
}
  [data-testid="stSidebar"], [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] p, [data-testid="stSidebar"] span,
  [data-testid="stSidebar"] div, [data-testid="stSidebar"] .stMarkdown {
    color: #111827 !important;
  }
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3 {
    color: #111827 !important;
    font-size: .9rem !important;
    font-weight: 800 !important;
    letter-spacing: 0 !important;
    margin: .65rem 0 .25rem !important;
  }
  [data-testid="stSidebar"] hr {
    border-color: #e5e7eb !important;
    margin: .55rem 0 !important;
  }
  [data-testid="stSidebar"] [data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 8px !important;
    box-shadow: none !important;
  }
  [data-testid="stSidebar"] [data-testid="stExpander"] summary,
  [data-testid="stSidebar"] [data-testid="stExpander"] summary * {
    color: #111827 !important;
  }
  [data-testid="stSidebar"] .stButton button,
  [data-testid="stSidebar"] .stButton button * {
    background: #ffffff !important;
    border-color: #d1d5db !important;
    color: #111827 !important;
    box-shadow: none !important;
  }
  [data-testid="stSidebar"] .stButton button:hover,
  [data-testid="stSidebar"] .stButton button:hover * {
    background: #eef2ff !important;
    border-color: #315f8a !important;
  }
  .hero-card {
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    border-left: 5px solid var(--dorts-blue) !important;
    border-radius: 8px !important;
    box-shadow: none !important;
    padding: 32px 34px !important;
  }
  .hero-eyebrow { color: var(--dorts-blue) !important; font-weight: 800; }
  .hero-title { color: #111827 !important; font-size: 2.35rem !important; line-height: 1.18 !important; }
  .hero-subtitle { color: #4b5563 !important; max-width: 860px !important; }
  .hero-pill {
    background: #f9fafb !important;
    border: 1px solid #e5e7eb !important;
    color: #374151 !important;
    border-radius: 999px !important;
  }
  .section-title {
    color: #111827 !important;
    font-size: 1.05rem !important;
    margin: 28px 0 10px !important;
  }
  .report-card {
    border: 1px solid #e5e7eb !important;
    box-shadow: none !important;
    margin: 8px 0 !important;
    padding: 14px 16px !important;
  }
  .report-card h4 {
    margin: 6px 0 8px !important;
    line-height: 1.35 !important;
    font-size: 1.02rem !important;
  }
  .report-card-body {
    color: #374151 !important;
    font-size: .92rem !important;
    line-height: 1.42 !important;
  }
  .report-line { margin: 3px 0; }
  .report-line.list { padding-left: 1rem; text-indent: -0.72rem; }
  .report-line.meta { color: #4b5563; }
  .report-spacer { height: 4px; }
  .type-badge {
    border-radius: 999px !important;
    padding: 3px 8px !important;
    font-size: .72rem !important;
  }
  .notice-success, .warn-box {
    box-shadow: none !important;
    border-radius: 8px !important;
  }
  [data-testid="stSidebar"] {
    min-width: 324px !important;
    max-width: 324px !important;
  }
  [data-testid="stSidebar"] > div:first-child {
    min-width: 324px !important;
    max-width: 324px !important;
  }
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] span {
    font-size: .9rem !important;
  }
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
    font-size: .98rem !important;
  }
  .sidebar-title {
    font-size: 1.12rem;
    font-weight: 800;
    line-height: 1.35;
    color: #111827;
    margin: 0 0 .04rem;
  }
  .sidebar-subtitle {
    font-size: .78rem;
    line-height: 1.45;
    color: #6b7280;
    margin: 0 0 .38rem;
  }
  [data-testid="stSidebar"] hr {
    margin: .18rem 0 !important;
  }
  [data-testid="stSidebar"] h3 {
    margin: .28rem 0 .08rem !important;
  }
  [data-testid="stSidebar"] [data-testid="stExpander"] {
    margin-bottom: .22rem !important;
  }
  [data-testid="stSidebar"] .stCheckbox,
  [data-testid="stSidebar"] .stRadio,
  [data-testid="stSidebar"] .stSelectbox,
  [data-testid="stSidebar"] .stTextArea {
    margin-bottom: .18rem !important;
  }
  [data-testid="stSidebar"] .stButton button {
    min-height: 2.2rem !important;
    padding: .25rem .55rem !important;
  }
  [data-testid="stSidebar"] textarea {
    min-height: 52px !important;
  }

  @media (max-width: 760px) {
    .hero-card { padding: 22px !important; background: #ffffff !important; }
    .hero-title { font-size: 1.65rem !important; }
    .hero-meta { margin-top: 20px; }
  }
</style>
""", unsafe_allow_html=True)


def get_app_source_hash() -> str:
    try:
        return hashlib.sha1(Path(__file__).read_bytes()).hexdigest()
    except Exception:
        return "unknown"


def clear_old_report_state() -> None:
    keys_to_clear = [
        "latest_report_md", "latest_report_html", "latest_pdf",
        "latest_debug_payload", "latest_run_config",
        "report_generated", "email_sent", "last_run_result",
        "latest_report", "latest_report_summary", "latest_report_stats",
        "latest_debug_info", "latest_source_statuses",
    ]
    for key in keys_to_clear:
        st.session_state.pop(key, None)


current_app_hash = get_app_source_hash()
previous_app_hash = st.session_state.get("_app_source_hash")
st.session_state["_app_source_hash"] = current_app_hash

# ── 日期與常數 ──────────────────────────────────────────────
today = datetime.date.today()
APP_DIR = Path(__file__).resolve().parent
REPORTS_DIR = APP_DIR / "reports"

ADVANCED_TYPES = ["技術新知", "重大事故", "營運政策", "營運爭議", "規範更新"]
DEFAULT_SELECTED_TYPES = ["技術新知", "重大事故", "營運政策", "營運爭議"]
SECTION_NUMBER_BY_TYPE = {
    "技術新知": "一",
    "重大事故": "二",
    "營運政策": "三",
    "營運爭議": "四",
    "規範更新": "五",
}
EMPTY_TEXT_BY_TYPE = {
    "技術新知": "本期未發現符合條件之技術新知案例。",
    "重大事故": "本期未發現符合條件之重大事故案例。",
    "營運政策": "本期未發現符合條件之營運政策案例。",
    "營運爭議": "本期未發現符合條件之營運爭議事件。",
    "規範更新": "本期未發現符合條件之規範版本更新、修訂草案、公告或徵詢事件。",
}
MIN_REPORT_ITEMS = 15
MAX_ITEMS_PER_SOURCE = 25
DDGS_MAX_RESULTS = 25
RESEARCH_SUPPLEMENT_LOOKBACK_DAYS = 90
NORMAL_LOOKBACK_OPTIONS = [7, 14, 30]
ADVANCED_LOOKBACK_OPTIONS = [90, 180, 365]
REPORT_TARGET_BY_DAYS = {
    7: 8,
    14: 10,
    30: 10,
    90: 10,
    180: 12,
    365: 12,
}
LONG_TERM_TARGET_LABELS = {
    90: "趨勢回顧",
    180: "半年報",
    365: "年度回顧",
}
REPORT_PERIOD_LABELS = {
    7: "週報",
    14: "雙週報",
    30: "月報",
    90: "季報",
    180: "半年報",
    365: "年度回顧",
}


def get_research_supplement_lookback_days(days: int) -> int:
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 90
    if days >= 365:
        return 365
    if days >= 180:
        return 180
    return 90

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
    "日本": "Japan Tokyo Metro Osaka Metro subway new transit system",
    "韓國": "Korea Seoul Metro subway urban rail light rail",
    "新加坡": "Singapore MRT LTA SMRT",
    "香港": "Hong Kong MTR light rail metro",
    "美國": "United States New York subway Washington Metro Chicago CTA",
    "加拿大": "Canada Toronto TTC Vancouver SkyTrain Montreal REM",
    "英國": "United Kingdom London Underground DLR tram Transport for London",
    "法國": "France Paris Metro RATP Grand Paris Express",
    "德國": "Germany Berlin U-Bahn Munich U-Bahn Hamburg U-Bahn",
    "西班牙": "Spain Madrid Metro Barcelona Metro tranvia light rail metro project",
    "荷蘭": "Netherlands Amsterdam metro Rotterdam metro",
    "瑞士": "Switzerland Zurich tram Lausanne metro",
    "澳洲": "Australia Sydney Metro Melbourne Metro Brisbane Metro light rail",
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

LOW_VALUE_EXCLUDED_HOSTS = {
    "buseta.wmata.com",
    "estore.mtr.com.hk",
    "portal.mtr.com.hk",
    "link.mtrmb.mtr.com.hk",
    "art.tfl.gov.uk",
}

ALLOWED_NEWS_DOMAINS: set[str] = set()

DOMESTIC_EXCLUDED_DOMAINS = {
    ".tw",
}

DOMESTIC_EXCLUDED_TERMS = [
    "台灣", "臺灣", "Taiwan",
    "台北", "臺北", "Taipei", "Taipei MRT", "北捷",
    "新北", "New Taipei",
    "桃園", "Taoyuan", "Taoyuan Metro", "桃捷",
    "台中", "臺中", "Taichung",
    "台南", "臺南", "Tainan",
    "高雄", "Kaohsiung", "Kaohsiung MRT", "高捷",
    "基隆", "Keelung", "新竹", "Hsinchu", "苗栗", "Miaoli",
    "宜蘭", "Yilan", "花蓮", "Hualien", "台東", "臺東", "Taitung",
    "屏東", "Pingtung",
]

TRANSIT_NEWS_TERMS = (
    '("urban rail" OR metro OR subway OR underground OR "mass rapid transit" OR MRT OR '
    '"light rail" OR tram OR tramway OR streetcar OR LRRT OR LRT OR AGT OR '
    '"automated guideway transit" OR "people mover") '
    '-"high-speed rail" -"high speed rail" -HSR -Shinkansen -"bullet train" '
    '-intercity -"regional rail" -freight -locomotive -bus -coach -highway'
)

URBAN_RAIL_MODE_TERMS = [
    "metro", "subway", "underground", "tube", "metrorail", "mass rapid transit", "mrt",
    "light rail", "tram", "tramway", "streetcar", "lrrt", "lrt",
    "urban rail", "urban metro", "rapid transit", "people mover", "automated guideway transit",
    "agt", "monorail", "u-bahn", "stadtbahn", "skytrain", "dlr", "mover",
    "地下鉄", "メトロ", "新交通システム", "都市鉄道", "路面電車", "トラム",
    "지하철", "도시철도", "경전철",
    "地鐵", "港鐵", "輕軌", "轻轨", "都市軌道", "捷運",
]

URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS = [
    term for term in URBAN_RAIL_MODE_TERMS
    if term not in {"metro"}
]

URBAN_RAIL_OPERATOR_TERMS = [
    "tokyo metro", "seoul metro", "mtr", "lta", "smrt", "tfl", "transport for london",
    "ratp", "wmata", "ttc", "translink", "mta", "nyct", "cta", "bart",
    "metro de madrid", "madrid metro", "barcelona metro", "wiener linien",
    "stockholm metro", "sporveien", "copenhagen metro", "rta dubai",
    "東京メトロ", "서울교통공사", "港鐵", "巴黎地鐵",
]

CIVIC_METRO_NAME_ONLY_TERMS = [
    "metro vancouver", "metro council", "metro mayor", "metro government",
    "metro area", "metro region", "metropolitan council", "metropolitan government",
    "metropolitan planning organization",
]

SOURCE_NAME_NOISE_TERMS = [
    "metro magazine", "metro report international", "urban transport magazine",
    "mass transit", "railway gazette international", "international railway journal",
    "railway age", "railway-news", "railway news", "railway technology",
    "global railway review", "intelligent transport",
]

NON_URBAN_TRANSPORT_TERMS = [
    "high-speed rail", "high speed rail", "high-speed train", "high speed train",
    "hsr", "shinkansen", "bullet train", "tgv", "ice train", "renfe high speed",
    "intercity", "inter-city", "long-distance", "long distance", "regional rail",
    "commuter rail", "national rail", "mainline", "main line", "heavy haul",
    "freight", "locomotive", "rail freight", "passenger rail", "railway contract",
    "railway contracts", "railway procurement", "lirr", "long island rail road",
    "amtrak", "korail", "network rail", "east midlands railway", "regiojet",
    "battery train", "hybrid train", "diesel-hybrid", "gsm-r outage",
    "bus", "coach", "highway", "intercity bus", "long-distance coach", "brt",
    "airport", "aviation", "lax", "airport people mover", "terminal people mover",
    "airport transit", "airport shuttle", "terminal shuttle",
    "road maintenance", "road works", "road construction", "road closure",
    "pothole", "highway works", "traffic advisory",
    "高速鐵路", "高速铁路", "高鐵", "高铁", "新幹線", "新干线",
    "台鐵", "臺鐵", "台湾鉄路", "台灣鐵路", "在来線", "特急",
    "貨運", "貨物列車", "客運鐵路", "城際鐵路", "區域鐵路", "通勤鐵路",
    "公路", "高速公路", "道路維護", "道路施工", "道路封閉", "道路坑洞",
    "交通提醒", "長途巴士", "客運", "機場", "航空", "航廈", "航站",
    "高速鉄道", "高速バス", "バス", "貨物鉄道", "在来線",
]

NON_URBAN_HARD_EXCLUDE_TERMS = [
    term for term in NON_URBAN_TRANSPORT_TERMS
    if term not in {"passenger rail", "railway contract", "railway contracts", "railway procurement"}
]

NON_URBAN_QUERY_EXCLUSIONS = (
    '-"high-speed rail" -"high speed rail" -HSR -Shinkansen -"bullet train" '
    '-intercity -"regional rail" -"commuter rail" -freight -locomotive '
    '-Amtrak -Korail -RegioJet -bus -coach -highway'
)

AIRPORT_PEOPLE_MOVER_EXCLUDE_TERMS = [
    "airport", "aviation", "lax", "airport people mover", "terminal people mover",
    "airport transit", "airport shuttle", "terminal shuttle",
    "機場", "航空", "航廈", "航站",
]

TECH_NEWS_REQUIRED_TERMS = [
    "cbtc", "goa4", "driverless", "unattended train operation", "automatic train operation",
    "automation", "automated", "train control", "signalling", "signaling", "signal system",
    "rolling stock", "fleet", "new train", "trainset", "vehicle", "platform screen door",
    "platform doors", "psd", "power supply", "traction power", "substation", "third rail",
    "overhead line", "communications", "telecom", "4g", "5g", "lte", "radio", "cybersecurity",
    "data", "monitoring", "condition monitoring", "real-time", "digital", "asset management",
    "depot", "maintenance", "workshop", "afc", "fare gate", "ticketing", "elevator",
    "escalator", "system integration", "testing", "commissioning", "trial run",
    "api", "data governance", "ai image analysis", "video analytics", "system verification",
    "自動運転", "無人運転", "ワンマン運転", "信号", "ホームドア", "車両", "電力",
    "変電所", "通信", "保守", "検査", "試験", "システム",
    "自動駕駛", "無人駕駛", "單人駕駛", "號誌", "信號", "月臺門", "月台門",
    "車輛", "列車", "供電", "牽引", "變電站", "通訊", "資安", "即時監控",
    "維修", "機廠", "測試", "試運轉", "系統整合", "列控", "資料治理",
    "AI 影像分析", "影像分析", "測試驗證",
]

TECH_NEWS_SOFT_EXCLUDE_TERMS = [
    "accident", "derailment", "collision", "fire", "arson", "incident", "strike",
    "wage", "salary", "union", "fare dispute", "budget overrun", "lawsuit",
    "ceo", "resignation", "appoints", "appointment", "preview", "ceremony",
    "anniversary", "mascot", "branding", "pest", "hygiene", "route planning",
    "network expansion", "line extension", "funding", "procurement scandal",
    "bus procurement", "electric bus", "policy", "ban",
    "事故", "脱線", "火災", "放火", "スト", "労組", "賃金", "社長", "退任",
    "就任", "記念", "ラッピング", "ドラゴンズ", "害虫", "禁止", "バス",
    "事故", "出軌", "脫軌", "火災", "縱火", "罷工", "工會", "薪資", "票價",
    "爭議", "執行長", "離職", "任命", "預覽", "開幕", "紀念", "彩繪",
    "行銷", "害蟲", "禁帶", "禁令", "公車", "電動巴士",
]

MAX_SELECTION_CANDIDATES = 150
SELECTION_MIN_ITEMS = 8
SELECTION_MAX_ITEMS = 20
CANDIDATE_SNIPPET_CHARS = 140
REPORT_SNIPPET_CHARS = 420
JOURNAL_MAX_RESULTS_PER_QUERY = 3
JOURNAL_MAX_ITEMS = 8
JOURNAL_ARTICLE_FETCH_LIMIT = 18

SOURCE_QUALITY_A_DOMAINS = {
    "tfl.gov.uk", "mta.info", "wmata.com", "ttc.ca", "translink.ca",
    "ratp.fr", "lta.gov.sg", "smrt.com.sg", "mtr.com.hk",
    "seoulmetro.co.kr", "tokyometro.jp", "metro.tokyo.lg.jp",
    "metro-madrid.es", "tmb.cat", "wienerlinien.at", "sl.se",
    "cph.dk", "rta.ae", "railwaygazette.com", "railjournal.com",
    "railway-technology.com", "railway-news.com",
    "urban-transport-magazine.com", "masstransitmag.com",
    "intelligenttransport.com", "metro-magazine.com",
}

SOURCE_TIER_OFFICIAL_DOMAINS = {
    "tfl.gov.uk", "mta.info", "wmata.com", "ttc.ca", "translink.ca",
    "ratp.fr", "lta.gov.sg", "smrt.com.sg", "mtr.com.hk",
    "seoulmetro.co.kr", "tokyometro.jp", "metro.tokyo.lg.jp",
    "metro-madrid.es", "tmb.cat", "wienerlinien.at", "sl.se",
    "cph.dk", "rta.ae", "uitp.org", "societedesgrandsprojets.fr",
}

SOURCE_TIER_PROFESSIONAL_DOMAINS = {
    "railwaygazette.com", "railjournal.com", "railway-technology.com",
    "railway-news.com", "urban-transport-magazine.com", "masstransitmag.com",
    "intelligenttransport.com", "metro-magazine.com", "railwayage.com",
    "globalmasstransit.net", "globalmasstransit.com",
}

SOURCE_DISPLAY_BY_DOMAIN = {
    "mta.info": "MTA 官方公告",
    "tokyometro.jp": "Tokyo Metro 官方公告",
    "mtr.com.hk": "港鐵官方資料",
    "ttc.ca": "TTC 官方公告",
    "tfl.gov.uk": "TfL 官方公告",
    "wmata.com": "WMATA 官方公告",
    "translink.ca": "TransLink 官方公告",
    "ratp.fr": "RATP 官方資料",
    "lta.gov.sg": "LTA 官方公告",
    "smrt.com.sg": "SMRT 官方公告",
    "seoulmetro.co.kr": "Seoul Metro 官方公告",
    "railway-news.com": "Railway-News",
    "railwaygazette.com": "Railway Gazette",
    "railjournal.com": "International Railway Journal",
    "urban-transport-magazine.com": "Urban Transport Magazine",
    "globalmasstransit.net": "Global Mass Transit",
    "globalmasstransit.com": "Global Mass Transit",
    "masstransitmag.com": "Mass Transit Magazine",
    "metro-magazine.com": "METRO Magazine",
    "railwayage.com": "Railway Age",
}

SOURCE_DOMAIN_HINT_BY_LABEL = {
    "mta": "mta.info",
    "tokyo metro": "tokyometro.jp",
    "mtr": "mtr.com.hk",
    "ttc": "ttc.ca",
    "tfl": "tfl.gov.uk",
    "wmata": "wmata.com",
    "translink": "translink.ca",
    "ratp": "ratp.fr",
    "lta": "lta.gov.sg",
    "smrt": "smrt.com.sg",
    "seoul metro": "seoulmetro.co.kr",
    "railway-news": "railway-news.com",
    "railway news": "railway-news.com",
    "railway gazette": "railwaygazette.com",
    "international railway journal": "railjournal.com",
    "irj": "railjournal.com",
    "urban transport magazine": "urban-transport-magazine.com",
    "global mass transit": "globalmasstransit.net",
    "mass transit magazine": "masstransitmag.com",
    "metro magazine": "metro-magazine.com",
    "railway age": "railwayage.com",
}

SOURCE_QUALITY_C_DOMAINS = {
    "msn.com", "yahoo.com", "aol.com", "tripadvisor.com", "timeout.com",
    "lonelyplanet.com", "booking.com", "expedia.com", "trip.com",
    "wikipedia.org", "wikivoyage.org",
}

LOW_QUALITY_CONTENT_TERMS = [
    "wikipedia", "travel guide", "tourist", "hotel", "airport parking",
    "things to do", "itinerary", "visitor guide", "travel tips", "travel reminder",
    "tourism information", "weekend travel", "seo", "sponsored",
    "minor delay", "detour", "service alert", "service advisory",
    "customer notice", "take transit", "temporary stop closure",
    "hiring", "jobs", "careers", "conference registration", "event page",
    "product page", "mtr e-store", "passenger praised", "passenger review",
    "traveler review", "viral video", "social media", "列車模型", "吊牌掛飾",
    "一般旅遊", "旅遊攻略", "景點", "飯店", "酒店", "旅客心得",
    "社群影片", "旅遊資訊", "週末搭乘提醒",
]

LOW_INFORMATION_PAGE_TERMS = [
    "home", "homepage", "topic page", "archive", "category", "service page",
    "portal", "入口", "首頁", "分類頁", "服務頁", "旅客資訊", "活動資訊",
    "archive page", "route page", "trip result", "journey planner", "route map",
    "route number", "RouteNumber", "trip planner", "travel information",
    "trip results", "rider tools", "service alerts", "service advisory",
    "mtr e-store", "untitled", "pdf map", "plan-metro", "plan-de-ligne",
    "archives", "event page", "conference registration", "product page",
    "jobs", "hiring", "vacancy", "career", "careers",
    "主頁", "列車模型", "吊牌掛飾",
]

LOW_INFORMATION_PATH_MARKERS = [
    "/topic", "/topics", "/archive", "/archives", "/category", "/categories",
    "/tag/", "/tags/", "/services", "/service", "/customer", "/passenger",
    "/mobile", "/app", "/apps", "/route", "/routes", "/trip", "/trips",
    "/journey", "/journey-planner", "/trip-planner", "/travel-information",
    "/rider-tools", "/service-alert", "/service-advisory", "/map", "/maps",
    "/search", "/store", "/estore", "/e-store", "/shop", "/product",
    "/event", "/events", "/registration", "/register", "/jobs", "/hiring",
    "/careers", "plan-metro", "plan-de-ligne", ".pdf",
]

HARD_LOW_VALUE_CANDIDATE_TERMS = [
    "trip results", "trip result", "service alerts", "service alert",
    "service advisory", "rider tools", "careers", "career", "hiring",
    "jobs", "plan-metro", "plan-de-ligne", "route page", "route map",
    "pdf map", "mtr e-store", "product page", "conference registration",
    "event page", "untitled", "lost property", "delay certificate",
    "contract documents holders list", "passenger praised", "passenger review",
    "traveler review", "viral video", "social media", "mascot", "stamp rally",
    "theme train", "themed train", "tbm farewell", "tbm demobilization",
    "tbm removal", "tunnel boring machine farewell", "pothole",
    "失物招領", "延誤證明", "標案文件持有人", "旅客心得", "社群影片",
    "吉祥物", "集章活動", "主題列車", "潛盾機告別", "潛盾機撤場", "道路坑洞",
]

JOURNAL_PRECISION_QUERIES = [
    '"urban rail transit" "predictive maintenance" "condition monitoring"',
    '"metro system" "fault diagnosis" "machine learning"',
    '"urban rail transit" "digital twin" maintenance',
    '"metro system" "digital twin" operation maintenance',
    '"CBTC" "urban rail transit" safety',
    '"communication based train control" "metro" reliability',
    '"driverless metro" "system assurance"',
    '"urban rail transit" "regenerative braking" energy storage',
    '"metro" "wayside energy storage" supercapacitor',
    '"platform screen door" "metro" fault diagnosis',
    '"platform screen doors" "urban rail transit" reliability',
    '"urban rail transit" cybersecurity',
    '"CBTC" cybersecurity',
    '"railway operational technology" cybersecurity',
]

JOURNAL_EXPLORATORY_QUERIES = [
    '"urban rail transit" emerging technology',
    '"metro system" innovation',
    '"smart metro" system integration',
    '"urban rail" advanced monitoring',
    '"driverless metro" technology',
    '"rail transit" intelligent maintenance',
    '"urban rail transit" intelligent operation maintenance',
]

JOURNAL_SOURCE_PAGES = [
    ("Springer Urban Rail Transit articles", "https://link.springer.com/journal/40864/articles"),
]

JOURNAL_EXCLUDE_TERMS = [
    "high-speed rail", "freight railway", "intercity rail", "road traffic",
    "bus", "autonomous vehicle", "air traffic", "pure algorithm",
    "高速鐵路", "貨運鐵路", "城際鐵路", "公車", "自駕車", "航空",
]

JOURNAL_RAIL_CONTEXT_TERMS = [
    "railway", "rail transit", "urban rail", "urban rail transit", "metro",
    "metro system", "subway", "mass rapid transit", "mrt", "light rail",
    "tram", "tramway", "cbtc", "rolling stock", "railway signalling",
    "railway signaling", "platform screen door", "traction power",
    "都市軌道", "捷運", "地鐵", "地下鉄", "都市鉄道", "軌道",
]

JOURNAL_ALLOWED_SOURCE_DOMAINS = {
    "mdpi.com", "nature.com", "springer.com", "link.springer.com",
    "sciencedirect.com", "doi.org", "tandfonline.com", "ieee.org",
    "ieeexplore.ieee.org", "elsevier.com", "frontiersin.org",
    "ascelibrary.org", "sagepub.com", "emerald.com",
}

JOURNAL_PREFERRED_SOURCE_TERMS = [
    "mdpi", "sciencedirect", "ieee", "springer", "taylor & francis",
    "tandfonline", "elsevier", "transportation research",
    "railway engineering science",
]

JOURNAL_SYSTEM_TERMS = [
    "cbtc", "signalling", "signaling", "train control", "rolling stock",
    "traction power", "power supply", "maintenance", "condition monitoring",
    "predictive maintenance", "artificial intelligence", "machine learning",
    "digital twin", "cybersecurity", "energy efficiency", "data governance",
    "passenger flow", "system integration", "platform screen door",
    "號誌", "列控", "車輛", "牽引供電", "維修", "AI", "數位分身",
    "資安", "能源效率", "資料治理", "旅客流量", "系統整合", "月臺門",
]

JOURNAL_INSIGHT_TERMS = [
    "maintenance", "energy", "safety", "risk", "cyber", "data", "system",
    "integration", "planning", "operations", "condition monitoring",
    "維修", "能源", "安全", "風險", "資安", "資料", "系統", "整合", "規劃",
]

JOURNAL_CORE_SYSTEM_TERMS = [
    "rolling stock", "vehicle system", "trainset", "signalling", "signaling",
    "train control", "cbtc", "ato", "atp", "ats", "operations control",
    "operation control", "traction power", "regenerative braking", "energy storage",
    "power supply", "communications", "wireless", "data transmission",
    "platform screen door", "platform door", "automatic fare collection", "afc",
    "depot equipment", "maintenance equipment", "condition monitoring",
    "fault diagnosis", "predictive maintenance", "image recognition",
    "video analytics", "system integration", "system assurance", "rams",
    "safety verification", "cybersecurity", "hvac", "ventilation", "fire safety",
    "environmental control", "energy management", "digital twin",
    "電聯車", "車輛系統", "號誌", "信號", "列車控制", "列控", "行車監控",
    "行控中心", "牽引供電", "再生煞車", "儲能", "供電", "通訊", "無線通訊",
    "月臺門", "月台門", "自動收費", "票務系統", "機廠設備", "維修設備",
    "狀態監測", "故障診斷", "預測性維護", "影像辨識", "系統整合", "系統保證",
    "安全驗證", "RAMS", "資安", "空調", "通風", "消防", "環控", "能源管理",
    "數位孿生", "數位分身",
]

JOURNAL_SECONDARY_SYSTEM_TERMS = [
    "track monitoring", "tunnel monitoring", "construction interface",
    "equipment layout", "installation interface", "metro construction interface",
    "軌道監測", "隧道監測", "施工介面", "設備配置", "安裝介面", "機電安裝",
]

JOURNAL_LOW_PRIORITY_TERMS = [
    "crew scheduling", "crew rostering", "staff scheduling", "workforce scheduling",
    "manpower scheduling", "passenger behavior", "passenger behaviour", "mode choice",
    "passenger choice", "commuter behavior", "pure operation management",
    "construction site layout", "civil construction", "civil engineering",
    "tunnel excavation", "excavation optimization", "general railway",
    "commuter rail", "人力排班", "人員排班", "乘務排班", "旅客行為",
    "旅客運具選擇", "通勤行為", "純營運管理", "施工場地配置", "土建施工",
    "隧道開挖", "一般鐵路", "通勤鐵路",
]

# ── 金鑰狀態 ──────────────────────────────────────────
# AI 報告產製改用 MaiAgent 雲端 API。
# 請在 Streamlit Cloud Secrets 或環境變數設定：
# MAIAGENT_API_KEY、MAIAGENT_CHATBOT_ID、MAIAGENT_API_BASE
maiagent_api_key = get_secret("MAIAGENT_API_KEY")
maiagent_chatbot_id = get_secret("MAIAGENT_CHATBOT_ID")
maiagent_api_base = get_secret("MAIAGENT_API_BASE", "https://api.maiagent.ai")
model_choice = "MaiAgent 雲端 API"

gmail_user = get_secret("GMAIL_USER")
gmail_pass = get_secret("GMAIL_APP_PASS")

if not st.session_state.get("_demo_cache_default_off_applied"):
    st.session_state["demo_cache_mode"] = False
    st.session_state["_demo_cache_default_off_applied"] = True

if not st.session_state.get("_fast_mode_removed_applied"):
    st.session_state["fast_mode"] = False
    st.session_state["_fast_mode_removed_applied"] = True


def select_all_report_types() -> None:
    st.session_state["selected_types_state"] = ADVANCED_TYPES.copy()
    for report_type in ADVANCED_TYPES:
        st.session_state[f"type_{report_type}"] = True


def clear_selected_report_types() -> None:
    st.session_state["selected_types_state"] = []
    for report_type in ADVANCED_TYPES:
        st.session_state[f"type_{report_type}"] = False


# ── 側邊欄 ──────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-title">🚇 國際捷運 AI 週報</div>
        <div class="sidebar-subtitle">臺北市政府捷運工程局｜機電系統設計處</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 📬 收件設定")
    default_recipients = get_secret("DEFAULT_RECIPIENTS", "")
    if "recipients_text" not in st.session_state:
        st.session_state["recipients_text"] = default_recipients

    recipient_input = st.text_area(
        "收件信箱",
        key="recipients_text",
        placeholder="每行一個 Email",
        height=52,
        help="需要新增收件人時，直接換行輸入。",
    )

    st.markdown("### 📋 報告設定")
    if "selected_types_state" not in st.session_state:
        st.session_state["selected_types_state"] = DEFAULT_SELECTED_TYPES.copy()
    if (
        not st.session_state.get("_default_types_without_standards_applied")
        and st.session_state.get("selected_types_state") == ADVANCED_TYPES
    ):
        st.session_state["selected_types_state"] = DEFAULT_SELECTED_TYPES.copy()
        st.session_state["type_規範更新"] = False
    st.session_state["_default_types_without_standards_applied"] = True
    if "long_term_mode" not in st.session_state:
        st.session_state["long_term_mode"] = False
    if "lookback_days_state" not in st.session_state:
        st.session_state["lookback_days_state"] = NORMAL_LOOKBACK_OPTIONS[0]

    available_lookback_options = NORMAL_LOOKBACK_OPTIONS + (
        ADVANCED_LOOKBACK_OPTIONS if st.session_state["long_term_mode"] else []
    )
    if st.session_state["lookback_days_state"] not in available_lookback_options:
        st.session_state["lookback_days_state"] = NORMAL_LOOKBACK_OPTIONS[0]

    lookback_days = st.selectbox(
        "報告期間",
        available_lookback_options,
        key="lookback_days_state",
        format_func=lambda d: f"{d} 天（{REPORT_PERIOD_LABELS.get(int(d), '報告')}）",
    )
    if int(lookback_days) in ADVANCED_LOOKBACK_OPTIONS:
        st.info("長期回顧適合趨勢分析、事故彙整與規範更新追蹤；不建議作為一般新聞週報使用，系統將提高重複內容排除與來源審查標準。")

    selected_types = []
    period_summary = LONG_TERM_TARGET_LABELS.get(int(lookback_days), REPORT_PERIOD_LABELS.get(int(lookback_days), "報告"))
    selected_type_count = sum(
        1 for t in ADVANCED_TYPES
        if st.session_state.get(f"type_{t}", t in st.session_state["selected_types_state"])
    )
    st.markdown("**📰 新聞類型**")
    st.caption(f"已選 {selected_type_count} 種類型｜{period_summary}")
    with st.expander("展開選擇新聞類型", expanded=False):
        col_t_all, col_t_clear = st.columns(2)
        col_t_all.button(
            "全選類型",
            use_container_width=True,
            on_click=select_all_report_types,
        )

        col_t_clear.button(
            "清除類型",
            use_container_width=True,
            on_click=clear_selected_report_types,
        )

        for t in ADVANCED_TYPES:
            checked = t in st.session_state["selected_types_state"]
            if st.checkbox(t, value=checked, key=f"type_{t}"):
                selected_types.append(t)

    st.session_state["selected_types_state"] = selected_types
    if not selected_types:
        st.warning("⚠️ 請至少選擇一種新聞類型。")

    standards_enabled = "規範更新" in selected_types
    standard_count = sum(len(v) for v in STANDARDS_WATCHLIST.values())

    st.markdown("### 🌏 追蹤範圍")
    scope_mode = st.radio(
        "報導範圍",
        ["指定先進國家/地區", "全球（安全白名單來源）"],
        index=0,
        horizontal=False,
        help="全球模式不以國家刪除新聞；指定模式才套用下方先進國家/地區清單。",
    )
    if "selected_regions_state" not in st.session_state:
        st.session_state["selected_regions_state"] = DEFAULT_REGIONS.copy()
    st.session_state["selected_regions_state"] = [
        region
        for region in dict.fromkeys(st.session_state["selected_regions_state"])
        if region in ADVANCED_REGIONS
    ]

    stored_selected_regions = list(st.session_state["selected_regions_state"])
    selected_regions = stored_selected_regions.copy()
    global_scope_selected = scope_mode == "全球（安全白名單來源）"
    if scope_mode == "全球（安全白名單來源）":
        st.caption("報導範圍：全球模式")
    else:
        st.caption(f"已選 {len(stored_selected_regions)} / {len(ADVANCED_REGIONS)} 個國家")

    with st.expander("展開選擇國家", expanded=False):
        col_all, col_clear = st.columns(2)
        if col_all.button("全選國家", use_container_width=True, key="select_all_regions", disabled=global_scope_selected):
            st.session_state["selected_regions_state"] = ADVANCED_REGIONS.copy()
            for region in ADVANCED_REGIONS:
                st.session_state[f"region_{region}"] = True
            st.rerun()

        if col_clear.button("清除全選", use_container_width=True, key="clear_all_regions", disabled=global_scope_selected):
            st.session_state["selected_regions_state"] = []
            for region in ADVANCED_REGIONS:
                st.session_state[f"region_{region}"] = False
            st.rerun()

        next_selected_regions = []
        region_cols = st.columns(2)
        for idx, region in enumerate(ADVANCED_REGIONS):
            checked = region in stored_selected_regions
            if region_cols[idx % 2].checkbox(region, value=checked, key=f"region_{region}", disabled=global_scope_selected):
                next_selected_regions.append(region)

    if not global_scope_selected:
        selected_regions = list(dict.fromkeys(next_selected_regions))
        st.session_state["selected_regions_state"] = selected_regions
    else:
        selected_regions = stored_selected_regions
    if scope_mode != "全球（安全白名單來源）" and not selected_regions:
        st.warning("請至少選擇一個國家/地區。")

    if standards_enabled:
        st.markdown("### 📚 規範追蹤")
        st.caption(f"已啟用，{standard_count} 項標準")
        with st.expander("查看規範追蹤清單", expanded=False):
            for category, standards in STANDARDS_WATCHLIST.items():
                st.markdown(f"**{category}**：{', '.join(standards)}")
        st.caption("規範追蹤僅作為更新監測清單；若未查得明確修訂、公告、草案、徵詢或新版發布，不會列入正式週報。")

    with st.expander("⚙️ 進階設定", expanded=False):
        st.markdown("**長期趨勢 / 規範追蹤模式**")
        long_term_mode = st.checkbox(
            "啟用長期趨勢 / 規範追蹤模式",
            key="long_term_mode",
            help="啟用後，報告期間可選 90、180、365 天。",
        )
        include_research_supplement = st.checkbox(
            f"納入近 {get_research_supplement_lookback_days(int(lookback_days))} 天國際學術期刊補充",
            value=False,
            key="include_research_supplement",
            help="7、14、30、90 天報告查近 90 天；180 天半年報查近 180 天；365 天年度回顧查近 365 天。只在正式報告最後新增「國際學術期刊」，不計入新聞統計。",
        )

        st.markdown("**排程說明**")
        st.caption("由 GitHub Actions 自動寄送週報；預設每周一早上8時30分寄出報告。")

        st.markdown("**AI 模型設定**")
        st.caption("目前使用：MaiAgent 雲端 API")

        show_developer_info = st.checkbox(
            "開發者資訊顯示",
            value=False,
            key="show_developer_info",
            help="啟用後只顯示 AI 校正資料 JSON 下載按鈕，供排錯使用。",
        )

        st.markdown("**展覽快速版**")
        demo_cache_mode = st.checkbox(
            "展覽快速版（10 秒內顯示預產報告）",
            value=False,
            key="demo_cache_mode",
            help="啟用後按下產生報告會直接載入 repo 內預產展示報告，不即時搜尋、不呼叫 MaiAgent。",
        )
        if demo_cache_mode:
            st.caption("目前會顯示預先產製展示報告，不是即時搜尋結果。")

    st.caption("🏛️ 台北市政府捷運工程局\nAI 競賽展示系統")

week_start = today - datetime.timedelta(days=int(lookback_days))
date_range = f"{week_start.strftime('%Y年%m月%d日')} 至 {today.strftime('%Y年%m月%d日')}"
lookback_int = int(lookback_days)
include_research_supplement = bool(
    include_research_supplement
)
fast_mode_enabled = False
demo_cache_mode_enabled = bool(st.session_state.get("demo_cache_mode", False))
report_period_label = REPORT_PERIOD_LABELS.get(lookback_int, "週報")
research_supplement_lookback_days = get_research_supplement_lookback_days(lookback_int)
research_supplement_start_date = today - datetime.timedelta(days=research_supplement_lookback_days)
research_supplement_period_label = f"近 {research_supplement_lookback_days} 天"
target_is_enforced = lookback_int in REPORT_TARGET_BY_DAYS
min_report_items = REPORT_TARGET_BY_DAYS.get(lookback_int, 0)
report_target_display = f"至少 {min_report_items} 則" if target_is_enforced else LONG_TERM_TARGET_LABELS.get(lookback_int, "趨勢回顧")
report_output_requirement = f"正式報告至少 {min_report_items} 則" if target_is_enforced else f"{report_target_display}，不強制篇數"
report_quantity_instruction = (
    f"本期為 {report_period_label}，正式報告建議下限為 {min_report_items} 則。"
    f"請不要在達到 {min_report_items} 則以前提早停止；若高信度新聞不足，"
    f"請優先納入中信度但來源、日期、都市軌道關聯明確的候選；"
    f"不要因摘要較短或連結為 Google News 轉址而過度剔除。"
    f"若最後正式新聞仍不足 {min_report_items} 則，必須在結尾列明不足原因，"
    f"例如：都市軌道來源不足、日期不明、非捷運/非輕軌、來源不合格。"
    f"**品質優先於數量；不得為了湊滿數量，把高鐵、一般鐵路、公車、長途運輸、"
    f"事故、政策、爭議或一般專案消息升格為技術新知。"
    f"規範追蹤清單、持續追蹤中、無單一新聞連結的標準項目，"
    f"不得列入正式規範更新，也不得計入正式新聞數。**"
    if target_is_enforced
    else f"本期為 {report_period_label}，屬長期趨勢 / 規範追蹤模式，不強制篇數。"
         f"請以趨勢分析、事故彙整、真正規範更新、來源品質與重複內容排除為優先；"
         f"不得為了增加篇數納入低關聯、重複、非都市軌道或來源不合格新聞。"
         f"規範追蹤清單、持續追蹤中、無單一新聞連結的標準項目，"
         f"不得列入正式規範更新，也不得計入正式新聞數。"
         f"若有效候選有限，請在報告摘要說明原因。"
)
report_shortfall_summary_line = (
    f"**不足 {min_report_items} 則原因**：（僅正式新聞少於 {min_report_items} 則時輸出；若達標，整行不要出現）"
    if target_is_enforced
    else "**長期回顧說明**：（簡述本期趨勢、重複內容排除後有效候選品質與來源限制）"
)
selected_report_topic = "、".join(selected_types) if selected_types else "技術趨勢"
report_title = f"【{today.strftime('%Y/%m/%d')}】國際捷運{selected_report_topic}{report_period_label}"
is_global_scope = scope_mode == "全球（安全白名單來源）"
active_regions = [] if is_global_scope else selected_regions
report_scope_label = "全球" if is_global_scope else "、".join(active_regions)


def build_current_run_config() -> dict:
    return {
        "report_date": today.isoformat(),
        "report_date_label": today.strftime("%Y/%m/%d"),
        "start_date": week_start.isoformat(),
        "end_date": today.isoformat(),
        "lookback_days": lookback_int,
        "date_range": date_range,
        "report_label": report_period_label,
        "report_title": report_title,
        "selected_types": selected_types.copy(),
        "scope_mode": scope_mode,
        "selected_regions": ["全球"] if is_global_scope else active_regions.copy(),
        "report_scope_label": report_scope_label,
        "include_standards": standards_enabled,
        "include_research_supplement": include_research_supplement,
        "research_supplement_period": {
            "lookback_days": research_supplement_lookback_days,
            "start_date": research_supplement_start_date.isoformat(),
            "end_date": today.isoformat(),
        },
        "fast_mode": fast_mode_enabled,
        "demo_cache_mode": demo_cache_mode_enabled,
        "app_source_hash": current_app_hash,
    }


current_run_config = build_current_run_config()


def get_report_type_code(report_label: str, lookback_days: int) -> str:
    label = (report_label or "").strip()
    try:
        days = int(lookback_days)
    except (TypeError, ValueError):
        days = 0
    if days == 7 or label == "週報":
        return "weekly"
    if days == 30 or label == "月報":
        return "monthly"
    if days == 90 or label == "季報":
        return "quarterly"
    if days == 180 or label in {"半年報", "半年度報告"}:
        return "halfyear"
    if days == 365 or label in {"年報", "年度回顧"}:
        return "annual"
    return f"{days}days" if days else "report"


def _compact_date(value, fallback: datetime.date | None = None) -> str:
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, datetime.date):
        return value.strftime("%Y%m%d")
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.datetime.strptime(text, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    match = re.search(r"(20\d{2})\D?(\d{1,2})\D?(\d{1,2})", text)
    if match:
        return f"{int(match.group(1)):04d}{int(match.group(2)):02d}{int(match.group(3)):02d}"
    return (fallback or today).strftime("%Y%m%d")


def build_report_download_filename(prefix: str, extension: str, run_config: dict | None = None) -> str:
    config = run_config or current_run_config
    days = int(config.get("lookback_days") or lookback_int)
    report_date_obj = today
    try:
        report_date_obj = datetime.date.fromisoformat(str(config.get("report_date") or today.isoformat()))
    except ValueError:
        pass
    report_type_code = get_report_type_code(config.get("report_label", report_period_label), days)
    report_date = _compact_date(config.get("report_date"), report_date_obj)
    clean_prefix = re.sub(r"[^A-Za-z0-9_]+", "_", str(prefix or "report")).strip("_")
    clean_extension = re.sub(r"[^A-Za-z0-9]+", "", str(extension or "")).lower()
    return f"{clean_prefix}_{report_type_code}_{report_date}.{clean_extension}"


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
    query = f"site:{domain} {keywords} when:{max(1, min(int(days), 365))}d"
    return google_news_search_url(query, hl=hl, gl=gl, ceid_lang=ceid_lang)


# ═══════════════════════════════════════════════════════
#  RSS 訂閱源（官方 RSS 優先；必要時由抓取函式 fallback 至 Google News site: 代理）
# ═══════════════════════════════════════════════════════
RSS_SOURCES = [
    ("Railway Gazette International（已併入 Metro Report International 都市軌道報導）",
     "https://www.railwaygazette.com/149.rss"),
    ("Railway Gazette Urban rail（Google News代理）",
     google_news_site_proxy_url("railwaygazette.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
    ("International Railway Journal (IRJ)", "https://www.railjournal.com/feed/"),
    ("IRJ metro / light rail（Google News代理）",
     google_news_site_proxy_url("railjournal.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
    ("Railway Technology", "https://www.railway-technology.com/feed/"),
    ("Railway-News", "https://railway-news.com/feed/"),
    ("Global Railway Review", "https://www.globalrailwayreview.com/feed/"),
    ("Intelligent Transport", "https://www.intelligenttransport.com/feed/"),
    ("Urban Transport Magazine（Google News代理）",
     google_news_site_proxy_url("urban-transport-magazine.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
    ("Mass Transit Magazine", "https://www.masstransitmag.com/rss"),
    ("METRO Magazine Rail（Google News代理）",
     google_news_site_proxy_url("metro-magazine.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
    ("Smart Cities Dive Transportation（Google News代理）",
     google_news_site_proxy_url("smartcitiesdive.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
    ("Railway Age urban rail / light rail（Google News代理）",
     google_news_site_proxy_url("railwayage.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
    ("UITP（無官方RSS，改用Google News代理）",
     google_news_site_proxy_url("uitp.org", int(lookback_days), TRANSIT_NEWS_TERMS)),
    # 2026-07 查證：masstransit.network 的 RSS 端點實際回傳的是「會員名錄」頁面
    # （人名列表），不是新聞內容，已移除，改依賴下方已驗證有效的 Global Mass Transit。
    ("Global Mass Transit", "https://www.globalmasstransit.net/feed"),
    # 東洋經濟原本用全站 RSS，抓到的 20 篇裡沒有一篇是鐵道新聞（全是投資理財/職場/美食）。
    # 改用 Google News 代理鎖定 site:toyokeizai.net + 鐵道關鍵字，才會是真的鐵道新聞。
    ("東洋經濟 Online 鐵道（Google News代理，鎖定 site:toyokeizai.net + 鐵道）",
     google_news_site_proxy_url("toyokeizai.net", int(lookback_days), '(地下鉄 OR メトロ OR 新交通システム OR 都市鉄道 OR 路面電車) -新幹線 -JR -在来線 -バス', "ja", "JP", "ja")),
    ("乗りものニュース", "https://trafficnews.jp/feed"),
    ("鉄道総合技術研究所 RTRI（無官方RSS，改用Google News代理）",
     google_news_site_proxy_url("rtri.or.jp", int(lookback_days), '(地下鉄 OR メトロ OR 新交通システム OR 都市鉄道 OR 軌道) -新幹線 -在来線 -貨物鉄道', "ja", "JP", "ja")),
    ("Transit Jam", "https://transitjam.com/feed/"),
    ("TfL 官方新聞（Google News代理）",
     google_news_site_proxy_url("tfl.gov.uk", int(lookback_days), '(Tube OR Underground OR tram OR DLR OR "London Overground") -bus -coach', "en-GB", "GB", "en")),
    ("MTA 官方新聞（Google News代理）",
     google_news_site_proxy_url("mta.info", int(lookback_days), '(subway OR metro OR signal OR accessibility OR safety)')),
    ("WMATA 官方新聞（Google News代理）",
     google_news_site_proxy_url("wmata.com", int(lookback_days), '(Metro OR Metrorail OR subway OR station OR railcar) -bus')),
    ("TTC 官方新聞（Google News代理）",
     google_news_site_proxy_url("ttc.ca", int(lookback_days), '(subway OR streetcar OR signal OR fleet OR safety)', "en-CA", "CA", "en")),
    ("TransLink 官方新聞（Google News代理）",
     google_news_site_proxy_url("translink.ca", int(lookback_days), '(SkyTrain OR "Canada Line" OR rail transit OR station) -bus', "en-CA", "CA", "en")),
    ("RATP 官方新聞（Google News代理）",
     google_news_site_proxy_url("ratp.fr", int(lookback_days), '(metro OR tramway OR automatisation OR securite) -bus -RER', "fr", "FR", "fr")),
    ("Société des grands projets 官方新聞（Google News代理）",
     google_news_site_proxy_url("societedesgrandsprojets.fr", int(lookback_days), '("Grand Paris Express" OR metro OR gare)', "fr", "FR", "fr")),
    ("LTA 官方新聞（Google News代理）",
     google_news_site_proxy_url("lta.gov.sg", int(lookback_days), '(MRT OR LRT OR "Thomson-East Coast Line" OR "rail transit") -bus', "en-SG", "SG", "en")),
    ("MTR 官方新聞（Google News代理）",
     google_news_site_proxy_url("mtr.com.hk", int(lookback_days), '(MTR OR 港鐵 OR 地鐵 OR 輕鐵 OR signalling) -bus', "zh-HK", "HK", "zh-Hant")),
    ("Seoul Metro 官方新聞（Google News代理）",
     google_news_site_proxy_url("seoulmetro.co.kr", int(lookback_days), '(지하철 OR 도시철도 OR 안전 OR 열차)', "ko", "KR", "kr")),
    ("Tokyo Metro 官方新聞（Google News代理）",
     google_news_site_proxy_url("tokyometro.jp", int(lookback_days), '(東京メトロ OR 地下鉄 OR 安全 OR 車両)', "ja", "JP", "ja")),
]

KNOWN_BAD_OFFICIAL_RSS_HOSTS = {
    "railwaygazette.com",
    "railjournal.com",
    "globalrailwayreview.com",
    "intelligenttransport.com",
    "masstransitmag.com",
    "trafficnews.jp",
}

KNOWN_BAD_OFFICIAL_RSS_LABELS = [
    "Railway Gazette International",
    "International Railway Journal",
    "Global Railway Review",
    "Intelligent Transport",
    "Mass Transit Magazine",
    "乗りものニュース",
]


def _source_skip_record(
    source_name: str,
    url: str,
    status: str,
    reason: str,
    item_count: int = 0,
) -> dict:
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    return {
        "source_name": source_name,
        "method": "Google News 代理" if "news.google.com" in host else "官方 RSS",
        "status": status,
        "item_count": item_count,
        "error_message": reason,
        "fallback_used": False,
    }


def _source_identity(source: tuple[str, str]) -> tuple[str, str]:
    source_name, url = source
    return source_name.casefold(), url.casefold()


def _is_known_bad_official_rss(source_name: str, url: str) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().removeprefix("www.")
    if "news.google.com" in host:
        return False
    if host in KNOWN_BAD_OFFICIAL_RSS_HOSTS:
        return True
    source_lower = (source_name or "").casefold()
    return any(label.casefold() in source_lower for label in KNOWN_BAD_OFFICIAL_RSS_LABELS)


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


FORMAL_SOURCE_PROXY_LABELS = {
    "日本地下鉄/メトロ", "韓國地下鐵", "Singapore MRT", "香港港鐵",
    "Australia Metro", "UK Underground", "France Metro", "Germany U-Bahn",
    "Spain Metro/Light Rail", "Netherlands Metro", "Switzerland Metro/Tram",
    "US Subway/Metro", "Canada Metro", "Italy Metro/Tram", "Sweden Metro/Tram",
    "Austria U-Bahn/Tram", "Denmark Metro/Light Rail", "Norway Metro/Tram",
}


def _is_query_proxy_source_label(source_name: str) -> bool:
    raw = str(source_name or "").strip()
    cleaned = clean_source_name_for_ui(raw).strip()
    raw_lower = raw.casefold()
    cleaned_lower = cleaned.casefold()
    if "google news" in raw_lower or "代理" in raw_lower:
        return True
    return any(cleaned_lower == label.casefold() for label in FORMAL_SOURCE_PROXY_LABELS)


def _clean_formal_source_proxy_label(label: str) -> str:
    cleaned = str(label or "").strip()
    cleaned = re.sub(r"Google\s*News\s*地區代理\s*[－\-:：]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Google\s*News\s*代理", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"地區代理\s*[－\-:：]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" －-_/|：:")
    if _is_query_proxy_source_label(cleaned):
        return ""
    return cleaned


def _conditional_news_sources(fast_mode: bool) -> tuple[list[tuple[str, str]], list[dict]]:
    sources: list[tuple[str, str]] = []
    skipped: list[dict] = []
    days = int(lookback_days)
    apta_source = (
        "APTA rail transit（Google News代理）",
        google_news_site_proxy_url("apta.com", days, TRANSIT_NEWS_TERMS),
    )
    smartcitiesworld_source = (
        "SmartCitiesWorld rail transit（Google News代理）",
        google_news_site_proxy_url(
            "smartcitiesworld.net",
            days,
            '("urban rail" OR metro OR subway OR "light rail" OR tram OR MRT OR "rail transit") -bus -parking -road -MaaS',
        ),
    )

    if lookback_int in ADVANCED_LOOKBACK_OPTIONS or standards_enabled:
        sources.append(apta_source)
    else:
        skipped.append(_source_skip_record(
            apta_source[0],
            apta_source[1],
            "long_term_only_source",
            "APTA 僅於長期報告或規範更新啟用",
        ))

    if fast_mode:
        skipped.append(_source_skip_record(
            smartcitiesworld_source[0],
            smartcitiesworld_source[1],
            "low_priority_source",
            "SmartCitiesWorld 低頻來源，快速模式跳過",
        ))
    else:
        sources.append(smartcitiesworld_source)

    return sources, skipped

# ═══════════════════════════════════════════════════════
#  依勾選國家動態產生的 Google News 地區代理來源
# ═══════════════════════════════════════════════════════
# 背景：上方 RSS_SOURCES 幾乎都是歐美鐵道媒體，對日韓星港等亞洲市場的
# 捷運新聞覆蓋率實測為 0（見程式修訂紀錄）。這裡針對使用者勾選的國家，
# 用當地語言關鍵字動態組出 Google News RSS 代理，補上這塊缺口。
# 每個 tuple：(顯示名稱, 查詢關鍵字, hl 語系, gl 國別, ceid 語言代碼)
REGION_NEWS_QUERIES: dict[str, list[tuple[str, str, str, str, str]]] = {
    "日本": [("Google News地區代理－日本地下鉄/メトロ",
             "(地下鉄 OR メトロ OR 新交通システム OR 都市鉄道 OR 路面電車) -新幹線 -JR -在来線 -高速バス -ゲーム -Steam -スタンプラリー -アニメ", "ja", "JP", "ja")],
    "韓國": [("Google News地區代理－韓國地下鐵",
             "(지하철 OR 도시철도 OR 경전철)", "ko", "KR", "kr")],
    "新加坡": [("Google News地區代理－Singapore MRT",
              "(MRT OR LTA OR SMRT Singapore)", "en-SG", "SG", "en")],
    "香港": [("Google News地區代理－香港港鐵",
             "(港鐵 OR MTR 香港)", "zh-HK", "HK", "zh-Hant")],
    "澳洲": [("Google News地區代理－Australia Metro",
             "(Sydney Metro OR Melbourne Metro OR Brisbane Metro OR light rail) -bus -coach -highway", "en-AU", "AU", "en")],
    "英國": [("Google News地區代理－UK Underground",
             "(London Underground OR TfL Tube OR DLR OR tram) -bus -coach -highway -National Rail", "en-GB", "GB", "en")],
    "法國": [("Google News地區代理－France Metro",
             "(Metro Paris OR RATP OR Grand Paris Express)", "fr", "FR", "fr")],
    "德國": [("Google News地區代理－Germany U-Bahn",
             "(U-Bahn OR Stadtbahn OR tram OR Straßenbahn) -ICE -DB -Fernverkehr -Spiel -Kinofilm -Videospiel", "de", "DE", "de")],
    "西班牙": [("Google News地區代理－Spain Metro/Light Rail",
              "(Madrid Metro OR Barcelona Metro OR Metro de Madrid OR tranvia OR tranvía OR light rail) -AVE -alta velocidad -autobus", "es", "ES", "es")],
    "荷蘭": [("Google News地區代理－Netherlands Metro",
             "(Amsterdam metro OR Rotterdam metro)", "nl", "NL", "nl")],
    "瑞士": [("Google News地區代理－Switzerland Metro/Tram",
             "(Zurich tram OR Lausanne metro)", "de-CH", "CH", "de")],
    "美國": [("Google News地區代理－US Subway/Metro",
             "(subway OR Metrorail OR light rail OR streetcar OR people mover) United States -Amtrak -intercity -bus -coach -highway", "en-US", "US", "en")],
    "加拿大": [("Google News地區代理－Canada Metro",
              "(TTC subway OR SkyTrain Vancouver OR REM Montreal OR light rail) -bus -coach -highway", "en-CA", "CA", "en")],
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


def build_region_news_sources(regions: list[str], days: int, fast_mode: bool = False) -> list[tuple[str, str]]:
    """依勾選國家動態組出 Google News 地區代理 RSS 來源清單。"""
    sources: list[tuple[str, str]] = []
    days = max(1, min(int(days), 365))
    for region in regions:
        region_queries = REGION_NEWS_QUERIES.get(region, [])
        if fast_mode:
            region_queries = region_queries[:1]
        for label, keyword, hl, gl, lang in region_queries:
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
    days = max(1, min(int(days), 365))
    update_terms = " OR ".join(f'"{term}"' for term in STANDARD_UPDATE_TERMS)
    for category, standards in STANDARDS_WATCHLIST.items():
        for standard in standards:
            query = f'"{standard}" ({update_terms}) when:{days}d'
            sources.append((f"規範更新代理－{category}－{standard}", google_news_search_url(query)))
    return sources


FAST_SOURCE_KEYWORDS = (
    "railway-news",
    "railway gazette",
    "urban transport magazine",
    "mass transit magazine",
    "metro magazine",
    "mta",
    "tfl",
    "lta",
    "mtr",
    "tokyo metro",
    "ttc",
    "wmata",
    "translink",
)


def select_fast_rss_sources(sources: list[tuple[str, str]]) -> list[tuple[str, str]]:
    selected: list[tuple[str, str]] = []
    seen_keys: set[str] = set()
    for source_name, url in sources:
        haystack = f"{source_name} {url}".casefold()
        if not any(keyword in haystack for keyword in FAST_SOURCE_KEYWORDS):
            continue
        netloc = urlparse(url).netloc.lower().removeprefix("www.")
        dedupe_key = source_name.casefold() if netloc == "news.google.com" else (netloc or source_name.casefold())
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        selected.append((source_name, url))
    return selected or sources[: min(12, len(sources))]


def build_run_news_sources(
    region_sources: list[tuple[str, str]],
    standards_sources: list[tuple[str, str]],
    fast_mode: bool,
    return_skipped: bool = False,
) -> list[tuple[str, str]] | tuple[list[tuple[str, str]], list[dict]]:
    skipped_statuses: list[dict] = []
    usable_sources: list[tuple[str, str]] = []
    for source_name, url in RSS_SOURCES:
        if _is_known_bad_official_rss(source_name, url):
            skipped_statuses.append(_source_skip_record(
                source_name,
                url,
                "skipped_known_bad",
                "已知官方 RSS 長期失效，保留代理或未來自訂 RSS 可能性",
            ))
            continue
        usable_sources.append((source_name, url))

    conditional_sources, conditional_skips = _conditional_news_sources(fast_mode)
    usable_sources.extend(conditional_sources)
    skipped_statuses.extend(conditional_skips)

    if fast_mode:
        selected_base = select_fast_rss_sources(usable_sources)
        selected_keys = {_source_identity(source) for source in selected_base}
        for source_name, url in usable_sources:
            if _source_identity((source_name, url)) not in selected_keys:
                skipped_statuses.append(_source_skip_record(
                    source_name,
                    url,
                    "skipped_fast_mode",
                    "快速模式跳過低優先來源",
                ))
        base_sources = selected_base
    else:
        base_sources = usable_sources

    combined = base_sources + region_sources + standards_sources
    if return_skipped:
        return combined, skipped_statuses
    return combined


def render_main_dashboard(source_count: int, standards_count: int):
    selected_regions_note = "全球" if is_global_scope else f"{len(selected_regions)} 個國家"
    st.markdown(
        f"""
        <div class="hero-card">
          <div class="hero-eyebrow">臺北市政府捷運工程局｜機電系統設計處</div>
          <div class="hero-title">國際捷運技術{report_period_label} AI 自動產生系統</div>
          <div class="hero-subtitle">國際技術新知、重大事故、營運政策、營運爭議與規範更新之自動化監測</div>
            <div class="hero-meta">
            <span class="hero-pill">今日日期：{today.strftime('%Y/%m/%d')}</span>
            <span class="hero-pill">資料涵蓋：{week_start.strftime('%Y/%m/%d')} - {today.strftime('%Y/%m/%d')}</span>
            <span class="hero-pill">範圍：{scope_mode}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">報告產出</div>', unsafe_allow_html=True)
    generate_clicked = st.button(f"🚀 產生國際捷運 AI {report_period_label}", type="primary", use_container_width=True)
    if demo_cache_mode_enabled:
        st.info("展覽快速版已啟用：按下產生報告會顯示預先產製展示報告，不是即時搜尋結果。")
    send_after_generate = st.checkbox(
        "產生後寄送 Email",
        value=False,
        key="send_after_generate",
        help="預設只產生並顯示報告；勾選後會在報告成功產生後才寄送。",
    )
    progress_placeholder = st.empty()
    status_placeholder = st.empty()

    return generate_clicked, send_after_generate, progress_placeholder, status_placeholder


initial_region_sources = build_region_news_sources(active_regions, int(lookback_days), fast_mode=fast_mode_enabled)
initial_standard_sources = build_standards_news_sources(int(lookback_days)) if standards_enabled else []
initial_combined_sources = build_run_news_sources(initial_region_sources, initial_standard_sources, fast_mode_enabled)
generate_btn, send_after_generate, progress_placeholder, status_placeholder = render_main_dashboard(
    source_count=len(initial_combined_sources),
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


def _is_domestic_taiwan_host(host: str) -> bool:
    host = host.lower().strip(".")
    if not host:
        return False
    return any(host.endswith(suffix) for suffix in DOMESTIC_EXCLUDED_DOMAINS)


def _contains_taiwan_reference(text: str) -> bool:
    text_lower = (text or "").casefold()
    return any(term.casefold() in text_lower for term in DOMESTIC_EXCLUDED_TERMS)


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
        host = _domain_from_url(value)
        if host and host != "news.google.com":
            return host
    for value in (url, source_href, query):
        domain = _extract_site_domain_from_google_news(value)
        if domain and domain != "news.google.com":
            return domain
    return _domain_hint_from_source_label(f"{source} {query}")


def _has_high_value_operational_detail(text: str) -> bool:
    return (
        _contains_any_term(text, HIGH_VALUE_POLICY_TERMS)
        or _contains_any_term(text, TECH_NEWS_REQUIRED_TERMS)
        or _contains_any_term(text, ACCIDENT_SIGNAL_TERMS)
        or _is_standard_update_candidate(text, require_url=True)
    )


def _is_low_value_service_notice_text(text: str) -> bool:
    return _contains_any_term(text, LOW_VALUE_POLICY_TERMS + LOW_INFORMATION_PAGE_TERMS)


def hard_low_value_candidate_reason(candidate: dict) -> str:
    title = candidate.get("title", "")
    snippet = candidate.get("snippet", "")
    source = candidate.get("source", "")
    url = candidate.get("url", "")
    source_href = candidate.get("source_href", "")
    text = f"{title} {snippet} {source} {candidate.get('query', '')} {url} {source_href}"
    text_lower = text.casefold()
    host_candidates = [
        _domain_from_url(source_href),
        _domain_from_url(url),
        candidate.get("source_domain", ""),
    ]
    if any(
        host and _host_matches(host, domain)
        for host in host_candidates
        for domain in LOW_VALUE_EXCLUDED_HOSTS
    ):
        return "硬性低價值來源或子網域"
    if _contains_any_term(text, FINANCIAL_MARKET_TERMS):
        return "股票行情或企業財經分析"

    has_high_value = _has_high_value_operational_detail(text)
    if has_high_value:
        return ""

    if any(term.casefold() in text_lower for term in HARD_LOW_VALUE_CANDIDATE_TERMS):
        return "硬性低價值頁面"

    path_text = " ".join(urlparse(value or "").path.casefold() for value in (url, source_href))
    if any(marker in path_text for marker in LOW_INFORMATION_PATH_MARKERS):
        return "硬性低價值路徑"

    return ""


def _wordish_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", text or ""))


def _information_quality_issue(candidate: dict) -> str:
    title = candidate.get("title", "")
    snippet = candidate.get("snippet", "")
    source = candidate.get("source", "")
    text = f"{title} {snippet} {source} {candidate.get('query', '')} {candidate.get('url', '')} {candidate.get('source_href', '')}"
    title_count = _wordish_count(title)
    snippet_count = _wordish_count(snippet)
    is_official = candidate.get("source_tier") == "A_official"
    has_high_value = _has_high_value_operational_detail(text)

    if _is_low_value_service_notice_text(text) and not has_high_value:
        if _contains_any_term(text, ["route page", "route number", "RouteNumber", "trip planner"]):
            return "低價值路線公告"
        return "日常服務推播"
    if title_count < 4 and snippet_count < 10 and not (is_official and has_high_value):
        return "摘要資訊不足"
    if snippet_count < 8 and not has_high_value:
        return "摘要資訊不足"
    return ""


def _strip_source_name_noise(text: str) -> str:
    cleaned = text or ""
    for term in SOURCE_NAME_NOISE_TERMS:
        cleaned = re.sub(re.escape(term), " ", cleaned, flags=re.IGNORECASE)
    return cleaned


def _is_standards_source(source_name: str) -> bool:
    return (source_name or "").startswith("規範更新代理")


def _is_standard_update_query(query: str) -> bool:
    query_lower = (query or "").casefold()
    return any(
        standard.casefold() in query_lower
        for standards in STANDARDS_WATCHLIST.values()
        for standard in standards
    )
def _is_standard_update_candidate(text: str, require_url: bool = True) -> bool:
    """
    判斷是否為真正的規範更新。
    只有「標準編號 + 明確更新動作 + 可查證來源」才算規範更新。
    單純標準清單、官方首頁、持續追蹤中，不可列入正式週報。
    """
    text_raw = text or ""
    text_lower = text_raw.casefold()

    has_standard = any(
        standard.casefold() in text_lower
        for standards in STANDARDS_WATCHLIST.values()
        for standard in standards
    )

    update_action_terms = [
        "new edition", "revision", "amendment", "corrigendum",
        "draft", "public comment", "published", "withdrawn",
        "superseded", "revised", "updated",
        "新版", "新版本", "修訂", "修正", "增補", "勘誤",
        "草案", "徵詢", "公告", "發布", "撤回", "取代",
    ]

    tracking_only_terms = [
        "持續追蹤中", "持續追蹤", "追蹤清單",
        "標準體系公告", "無單一新聞連結",
        "standard watchlist", "tracking only",
        "catalogue", "catalog", "webstore",
    ]

    has_update_action = any(term.casefold() in text_lower for term in update_action_terms)
    is_tracking_only = any(term.casefold() in text_lower for term in tracking_only_terms)
    has_url = re.search(r"https?://", text_raw) is not None

    if is_tracking_only:
        return False
    if require_url and not has_url:
        return False

    return has_standard and has_update_action


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
    path_text = " ".join(
        urlparse(candidate.get(key, "") or "").path.replace("/", " ")
        for key in ("url", "source_href")
    )
    event_text = " ".join(str(candidate.get(key, "") or "") for key in (
        "title", "snippet"
    ))
    priority_guess = _event_region_hint_from_text(f"{event_text} {path_text}")
    if priority_guess:
        return priority_guess
    primary_guess = guess_region_from_text(f"{event_text} {path_text}")
    if primary_guess != "未判定":
        return primary_guess
    domain_guess = _region_from_domain_hints(candidate)
    if domain_guess:
        return domain_guess
    query_guess = guess_region_from_text(candidate.get("query", ""))
    return query_guess if query_guess != "未判定" else "未判定"


def _canonical_candidate_region(candidate: dict) -> str:
    region = str(candidate.get("region", "") or "").strip()
    guessed = _region_guess_from_candidate(candidate)
    if guessed == "巴西":
        region = "巴西"
    elif guessed != "未判定" and (not region or region in {"未判定", "國際", "國際研究"} or region != guessed):
        region = guessed
    if region in {"Brazil", "Brasil", "São Paulo", "Sao Paulo", "聖保羅", "圣保罗"}:
        region = "巴西"
    if not region:
        region = "未判定"
    candidate["region"] = region
    return region


def _is_allowed_international_candidate(candidate: dict, text: str, looks_like_standard: bool) -> bool:
    source = candidate.get("source", "")
    host = _original_source_domain(
        source,
        candidate.get("url", ""),
        candidate.get("source_href", ""),
        candidate.get("query", ""),
    )
    if looks_like_standard or _is_standards_source(source):
        return True
    if host and _host_matches(host, "uitp.org"):
        return True
    international_terms = [
        "international report", "global report", "cross-national", "multinational",
        "global survey", "benchmark report", "technical report",
        "國際報告", "全球報告", "跨國", "多國", "技術報告",
    ]
    return _contains_any_term(text, international_terms) and _contains_any_term(text, URBAN_RAIL_MODE_TERMS)


def _is_urban_rail_candidate(text: str, source_name: str = "") -> bool:
    """正式新聞候選須直接連到都會軌道；標準更新另由規範規則處理。"""
    if _is_standards_source(source_name):
        return True

    topic_text = _strip_source_name_noise(text)
    has_mode = _contains_any_term(topic_text, URBAN_RAIL_MODE_TERMS)
    has_unambiguous_mode = _contains_any_term(topic_text, URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS)
    has_operator = _contains_any_term(f"{source_name} {topic_text}", URBAN_RAIL_OPERATOR_TERMS)
    has_non_urban = _contains_any_term(topic_text, NON_URBAN_TRANSPORT_TERMS)
    has_hard_non_urban = _contains_any_term(topic_text, NON_URBAN_HARD_EXCLUDE_TERMS)
    has_civic_metro_name_only = _contains_any_term(topic_text, CIVIC_METRO_NAME_ONLY_TERMS)

    if has_civic_metro_name_only and not (has_unambiguous_mode or has_operator):
        return False
    if has_hard_non_urban and not has_unambiguous_mode:
        return False
    if has_non_urban and not has_mode:
        return False
    return has_mode or has_operator


def _is_tech_news_only_mode() -> bool:
    return bool(selected_types) and set(selected_types) == {"技術新知"}


def _is_technical_news_candidate(text: str, source_name: str = "") -> bool:
    """只勾技術新知時，排除純事故、政策、人事、行銷或一般工程進度。"""
    if _is_standards_source(source_name):
        return True

    topic_text = _strip_source_name_noise(f"{source_name} {text}")
    has_technical_term = _contains_any_term(topic_text, TECH_NEWS_REQUIRED_TERMS)
    has_soft_exclude = _contains_any_term(topic_text, TECH_NEWS_SOFT_EXCLUDE_TERMS)

    if has_soft_exclude and not has_technical_term:
        return False
    return has_technical_term


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
    url_host = _domain_from_url(url)
    if any(
        candidate_host and _host_matches(candidate_host, domain)
        for candidate_host in (host, url_host)
        for domain in LOW_VALUE_EXCLUDED_HOSTS
    ):
        return False, "低價值來源或子網域"
    if _is_blocked_host(host):
        return False, "被安全規則排除"
    if _is_domestic_taiwan_host(host):
        return False, "範圍排除"
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
    if response.status_code in (404, 405):
        raise FeedFetchError(str(response.status_code), f"HTTP {response.status_code}")
    if response.status_code >= 400:
        raise FeedFetchError("parse error", f"HTTP {response.status_code}")

    parsed = feedparser.parse(response.content)
    if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
        raise FeedFetchError("parse error", str(getattr(parsed, "bozo_exception", "RSS/Atom parse error")))
    return parsed


def _items_from_parsed_feed(
    parsed_feed,
    cutoff: datetime.datetime,
    seen_titles: set[str],
    seen_urls: set[str],
    source_name: str = "",
) -> tuple[list[dict], int, int, int, int]:
    items: list[dict] = []
    invalid_count = 0
    blocked_count = 0
    duplicate_count = 0
    topic_filtered_count = 0

    for entry in getattr(parsed_feed, "entries", []):
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        desc = (entry.get("summary") or entry.get("description") or "").strip()
        pub_str = _entry_pub_str(entry)
        source_href = _entry_source_href(entry)

        if not title or not _is_recent(pub_str, cutoff):
            continue

        candidate_text = f"{title} {desc} {link} {source_href} {pub_str}"

        if _contains_taiwan_reference(candidate_text):
            blocked_count += 1
            continue

        # 規範更新來源必須是「真正更新」，不能只是標準首頁或追蹤清單
        if _is_standards_source(source_name):
            if not pub_str or not _is_standard_update_candidate(candidate_text):
                topic_filtered_count += 1
                continue

        if not _is_urban_rail_candidate(candidate_text, source_name):
            topic_filtered_count += 1
            continue

        if _is_tech_news_only_mode() and not _is_technical_news_candidate(f"{title} {desc} {link} {source_href}", source_name):
            topic_filtered_count += 1
            continue

        is_valid, reason = _is_valid_news_url(link, source_href=source_href)
        if not is_valid:
            if reason in ("被安全規則排除", "範圍排除"):
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
        - datetime.timedelta(days=max(1, min(int(lookback_days), 365)))
    )
    all_blocks: list[str] = []
    source_statuses: list[dict] = []
    seen_titles: set[str] = set()
    seen_urls: set[str] = set()
    session = create_requests_session()

    for idx, (source_name, url) in enumerate(sources, 1):
        if status_text:
            status_text.text(f"📡 RSS {idx}/{len(sources)}：{clean_source_name_for_ui(source_name)}...")

        method = _method_for_url(url)
        if _is_known_bad_official_rss(source_name, url):
            source_statuses.append(_status_record(
                source_name,
                method,
                "skipped_known_bad",
                0,
                "已知官方 RSS 長期失效，保留代理或未來自訂 RSS 可能性",
            ))
            all_blocks.append(f"【RSS來源：{source_name}】（skipped_known_bad）")
            continue
        valid_source, source_reason = _is_valid_news_url(url)
        if not valid_source and source_reason in ("被安全規則排除", "範圍排除"):
            source_statuses.append(_status_record(source_name, method, source_reason, 0, source_reason))
            all_blocks.append(f"【RSS來源：{source_name}】（{source_reason}）")
            continue

        try:
            parsed_feed = _fetch_feed(session, url)
            items_found, invalid_count, blocked_count, duplicate_count, topic_filtered_count = _items_from_parsed_feed(
                parsed_feed, cutoff, seen_titles, seen_urls, source_name
            )
            if items_found:
                all_blocks.append(_format_items_block(source_name, items_found))
                source_statuses.append(_status_record(source_name, method, "成功", min(len(items_found), MAX_ITEMS_PER_SOURCE)))
            else:
                status = "非都市軌道" if topic_filtered_count and not (invalid_count or blocked_count) else "被安全規則排除" if blocked_count and not invalid_count else "無文章"
                message = f"無有效候選；非都市軌道 {topic_filtered_count}、無效連結 {invalid_count}、安全排除 {blocked_count}、重複 {duplicate_count}"
                all_blocks.append(f"【RSS來源：{source_name}】（{status}）")
                source_statuses.append(_status_record(source_name, method, status, 0, message))
        except FeedFetchError as exc:
            fallback_url = _fallback_google_news_url(url)
            if fallback_url:
                try:
                    parsed_feed = _fetch_feed(session, fallback_url)
                    items_found, invalid_count, blocked_count, duplicate_count, topic_filtered_count = _items_from_parsed_feed(
                        parsed_feed, cutoff, seen_titles, seen_urls, f"{source_name}（fallback Google News）"
                    )
                    if items_found:
                        all_blocks.append(_format_items_block(f"{source_name}（fallback Google News）", items_found))
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

    raw_text = "\n\n".join(all_blocks)
    if return_status:
        return raw_text, source_statuses
    return raw_text


# ═══════════════════════════════════════════════════════
#  精簡化 DDGS 關鍵字搜尋 (加速優化版)
# ═══════════════════════════════════════════════════════
def _fast_query_bucket(query: str) -> str:
    q = (query or "").casefold()
    if any(standard.casefold() in q for standards in STANDARDS_WATCHLIST.values() for standard in standards):
        return "standards"
    if any(term in q for term in ("derailment", "collision", "incident", "fire", "suspended", "accident")):
        return "incident"
    if any(term in q for term in ("strike", "controversy", "dispute", "protest", "budget overrun")):
        return "controversy"
    if any(term in q for term in ("policy", "fare", "accessibility", "ridership", "frequency", "regulation")):
        return "policy"
    if any(term in q for term in ("cbtc", "signalling", "signaling", "rolling stock", "driverless", "power", "depot", "automation")):
        return "technology"
    return "general"


def limit_fast_search_queries(queries: list[str], news_query_indices: set[int]) -> tuple[list[str], set[int]]:
    max_queries = 10 if not is_global_scope else 8
    selected_pairs: list[tuple[int, str]] = []
    seen_buckets: set[str] = set()

    for original_idx, query in enumerate(queries, 1):
        bucket = _fast_query_bucket(query)
        if bucket in seen_buckets:
            continue
        seen_buckets.add(bucket)
        selected_pairs.append((original_idx, query))
        if len(selected_pairs) >= max_queries:
            break

    if not is_global_scope and len(selected_pairs) < max_queries:
        selected_original_indices = {idx for idx, _ in selected_pairs}
        for original_idx, query in reversed(list(enumerate(queries, 1))):
            if original_idx in selected_original_indices:
                continue
            selected_pairs.append((original_idx, query))
            selected_original_indices.add(original_idx)
            if len(selected_pairs) >= max_queries:
                break
        selected_pairs.sort(key=lambda item: item[0])

    limited_queries = [query for _, query in selected_pairs]
    remapped_news_indices = {
        new_idx
        for new_idx, (old_idx, _) in enumerate(selected_pairs, 1)
        if old_idx in news_query_indices
    }
    return limited_queries, remapped_news_indices


def build_search_queries() -> tuple[list[str], set[int]]:
    """依據勾選的選項動態合併搜尋字，大幅減少發送次數"""
    queries = []
    news_indices = set()

    # 1. 核心通用關鍵字（只查有勾的）
    if "技術新知" in selected_types:
        queries.extend([
            f"metro subway MRT LRRT LRT light rail automated guideway transit signalling rolling stock power depot technology {today:%Y} {NON_URBAN_QUERY_EXCLUSIONS}",
            f"metro subway CBTC GoA4 driverless platform screen doors communications power supply depot maintenance {today:%Y} {NON_URBAN_QUERY_EXCLUSIONS}",
            f"地下鉄 メトロ 新交通システム 都市鉄道 自動運転 信号 車両 ホームドア 電力 通信 保守 {today:%Y} -新幹線 -JR -在来線 -高速バス"
        ])
    if "重大事故" in selected_types:
        queries.extend([
            f"metro subway light rail LRT tram derailment collision incident {today:%B %Y} {NON_URBAN_QUERY_EXCLUSIONS}",
            f"地下鉄 メトロ 新交通システム 路面電車 事故 脱線 運休 {today:%Y年%m月} -新幹線 -JR -在来線 -高速バス"
        ])
    if "營運政策" in selected_types:
        queries.extend([
            f"metro subway MRT light rail passenger safety fare accessibility regulation {today:%B %Y} {NON_URBAN_QUERY_EXCLUSIONS}",
            f"地下鉄 メトロ 新交通システム 規則 安全対策 {today:%Y年%m月} -新幹線 -JR -在来線 -高速バス"
        ])
    if "營運爭議" in selected_types:
        queries.extend([
            f"metro subway light rail LRT tram strike delay controversy fare dispute {today:%B %Y} {NON_URBAN_QUERY_EXCLUSIONS}",
            f"地下鉄 メトロ 新交通システム 路面電車 遅延 争議 {today:%Y年%m月} -新幹線 -JR -在来線 -高速バス"
        ])

    if is_global_scope:
        if "技術新知" in selected_types:
            queries.extend([
                f"urban rail metro subway light rail rolling stock signalling power supply CBTC automation depot {today:%Y} {NON_URBAN_QUERY_EXCLUSIONS}",
                f"metro subway MRT platform screen doors CBTC communications cybersecurity upgrade {today:%Y} {NON_URBAN_QUERY_EXCLUSIONS}",
                f"tram LRT LRRT automated depot maintenance system integration {today:%Y} {NON_URBAN_QUERY_EXCLUSIONS}",
            ])
        if "重大事故" in selected_types:
            queries.extend([
                f"metro subway LRT light rail derailment collision fire service suspended investigation {today:%Y} {NON_URBAN_QUERY_EXCLUSIONS}",
                f"urban rail tram light rail accident signalling power outage passengers evacuated {today:%Y} {NON_URBAN_QUERY_EXCLUSIONS}",
            ])
        if "營運政策" in selected_types:
            queries.extend([
                f"metro subway MRT transit safety policy fare accessibility regulation {today:%Y} {NON_URBAN_QUERY_EXCLUSIONS}",
                f"urban rail light rail tram operator policy ridership service frequency procurement {today:%Y} {NON_URBAN_QUERY_EXCLUSIONS}",
            ])
        if "營運爭議" in selected_types:
            queries.extend([
                f"metro subway light rail tram strike delay dispute budget overrun contract dispute {today:%Y} {NON_URBAN_QUERY_EXCLUSIONS}",
                f"urban rail metro light rail public controversy service disruption fare protest {today:%Y} {NON_URBAN_QUERY_EXCLUSIONS}",
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
            queries.append(f"{term} metro subway MRT LRRT LRT light rail tram CBTC driverless signalling rolling stock power depot maintenance system integration {today:%B %Y} {NON_URBAN_QUERY_EXCLUSIONS}")

        # 將事故、政策、爭議合併為一個查詢字串，精簡發送數量
        if any(t in selected_types for t in ["重大事故", "營運政策", "營運爭議"]):
            idx = len(queries) + 1
            queries.append(f"{term} metro subway light rail incident strike policy controversy {today:%B %Y} {NON_URBAN_QUERY_EXCLUSIONS}")
            news_indices.add(idx)

    if fast_mode_enabled:
        return limit_fast_search_queries(queries, news_indices)
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
                        results = ddgs.news(query, max_results=DDGS_MAX_RESULTS, timelimit=news_timelimit, backend=backend)
                    else:
                        results = ddgs.text(query, max_results=DDGS_MAX_RESULTS, timelimit=news_timelimit, backend=backend)
                if results:
                    for r in results:
                        body = (r.get("body") or r.get("excerpt") or r.get("description") or "")[:250]
                        href = r.get("href") or r.get("url") or ""
                        title = (r.get("title") or "").strip()
                        if not title:
                            continue
                        item_date = r.get("date") or r.get("published") or ""
                        candidate_text = f"{title} {body} {href} {item_date}"

                        if _contains_taiwan_reference(candidate_text):
                            continue

                        # 規範更新查詢必須符合「標準編號 + 更新動作 + 來源 URL」
                        if _is_standard_update_query(query):
                            if not item_date or not _is_standard_update_candidate(candidate_text):
                                continue
                        else:
                            if not _is_urban_rail_candidate(candidate_text):
                                continue

                        if (
                            _is_tech_news_only_mode()
                            and not _is_standard_update_query(query)
                            and not _is_technical_news_candidate(candidate_text)
                        ):
                            continue
                        is_valid, reason = _is_valid_news_url(href)
                        if not is_valid:
                            continue
                        result_items.append({
                            "title": title,
                            "summary": body,
                            "link": href,
                            "date": item_date or "日期未知",
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
    news_query_indices = set(range(1, len(search_queries) + 1))
    total = len(search_queries)
    days = int(lookback_days)
    news_timelimit = "w" if days <= 7 else "m" if days <= 31 else "y"
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


def _effective_source_url(candidate: dict) -> str:
    source_href = candidate.get("source_href") or ""
    url = candidate.get("url") or ""
    source_domain = (candidate.get("source_domain") or "").strip().lower()
    raw_url = source_href or url
    if "news.google.com" in _domain_from_url(raw_url):
        domain = source_domain or _original_source_domain(
            candidate.get("source", ""),
            url,
            source_href,
            candidate.get("query", ""),
        )
        if domain and domain != "news.google.com":
            return f"https://{domain}"
    return _clean_candidate_url(raw_url)


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
    host = _original_source_domain(source, url, source_href)
    text = f"{source} {url} {source_href}".casefold()

    if host and any(_host_matches(host, domain) for domain in SOURCE_QUALITY_A_DOMAINS):
        return "A", "官方/營運機構/政府交通機關/專業鐵道媒體"
    if any(term.casefold() in text for term in ("official", "government", "transport authority", "metro operator")):
        return "A", "官方或交通機關線索"
    if host and any(_host_matches(host, domain) for domain in SOURCE_QUALITY_C_DOMAINS):
        return "C", "轉載、旅遊或低信度網站"
    if any(term.casefold() in text for term in LOW_QUALITY_CONTENT_TERMS):
        return "C", "旅遊、SEO 或內容農場線索"
    return "B", "一般新聞媒體或未分級來源"


def classify_source_tier(source: str, url: str, source_href: str = "") -> tuple[str, str]:
    host = _original_source_domain(source, url, source_href)
    text = f"{source} {url} {source_href}".casefold()
    path_lower = urlparse(url or "").path.casefold()

    if host and any(_host_matches(host, domain) for domain in LOW_VALUE_EXCLUDED_HOSTS):
        return "D_proxy_low_value", "低價值來源或子網域"
    if any(marker in path_lower for marker in LOW_INFORMATION_PATH_MARKERS):
        return "D_proxy_low_value", "入口頁、查詢頁、路線頁、PDF 或低資訊頁"
    if any(term.casefold() in text for term in LOW_INFORMATION_PAGE_TERMS):
        return "D_proxy_low_value", "入口頁、分類頁或低資訊內容"
    if host and any(_host_matches(host, domain) for domain in SOURCE_TIER_OFFICIAL_DOMAINS):
        return "A_official", "官方公告、政府交通主管機關或營運機構"
    if any(term in text for term in ("官方", "政府", "transport authority", "metro operator", "official")):
        return "A_official", "官方或交通機關線索"
    if host and any(_host_matches(host, domain) for domain in SOURCE_TIER_PROFESSIONAL_DOMAINS):
        return "B_professional", "專業鐵道或大眾運輸媒體"
    if host and any(_host_matches(host, domain) for domain in SOURCE_QUALITY_C_DOMAINS):
        return "C_media", "一般媒體、轉載或入口媒體"
    if "news.google.com" in _domain_from_url(url) and not host:
        return "D_proxy_low_value", "Google News 代理且原始來源未明確辨識"
    return "C_media", "一般新聞媒體或未分級來源"


def source_label_for_report(source: str, url: str, source_href: str = "", tier: str = "") -> str:
    host = _original_source_domain(source, url, source_href)
    for domain, label in SOURCE_DISPLAY_BY_DOMAIN.items():
        if host and _host_matches(host, domain):
            return label

    source_clean = clean_source_name_for_ui(source)
    if _is_query_proxy_source_label(source):
        if host and host != "news.google.com":
            return host
        return "資料來源未明確辨識"

    if source_clean and source_clean not in {"RSS", "ddgs", "Google News"}:
        if tier == "A_official" and "官方" not in source_clean:
            return f"{source_clean} 官方公告"
        return source_clean
    if host and host != "news.google.com":
        return host
    if "news.google.com" in _domain_from_url(url):
        return "資料來源未明確辨識"
    return "資料來源未明確辨識"


def source_verb_for_report(tier: str, label: str) -> str:
    if tier == "A_official" or "官方" in (label or ""):
        return "公告"
    if tier == "B_professional":
        return "報導"
    return "報導"


EVENT_REGION_PRIORITY_HINTS: list[tuple[str, list[str]]] = [
    ("瑞士", ["basel", "basel tram", "bvb", "zürich", "zurich", "lausanne", "瑞士", "巴塞爾", "蘇黎世", "洛桑"]),
    ("美國", ["houston", "metrorail", "houston metrorail", "metro rail houston", "休士頓", "休斯頓"]),
    ("加拿大", ["vancouver", "broadway subway", "toronto", "finch west", "finch west lrt", "metrolinx", "ttc", "skytrain", "溫哥華", "多倫多"]),
    ("英國", ["northern ireland", "belfast", "translink ni", "translink northern ireland", "北愛爾蘭", "貝爾法斯特"]),
    ("德國", ["berlin", "adlershof", "leipzig", "munich", "hamburg", "u-bahn", "柏林", "萊比錫", "慕尼黑", "漢堡"]),
]


def _event_region_hint_from_text(text: str) -> str:
    text_lower = (text or "").casefold()
    for region, terms in EVENT_REGION_PRIORITY_HINTS:
        if any(term.casefold() in text_lower for term in terms):
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
        "澳洲": ["australia", "sydney", "melbourne", "brisbane", "澳洲"],
        "英國": ["united kingdom", "uk", "london", "tfl", "underground", "英國", "英国", "倫敦"],
        "法國": ["france", "paris", "ratp", "法國", "法国", "巴黎"],
        "德國": ["germany", "berlin", "munich", "hamburg", "u-bahn", "德國", "德国"],
        "美國": [
            "united states", "new york", "nyc", "manhattan", "washington", "chicago",
            "seattle", "federal way", "star lake", "sound transit", "link light rail",
            "wmata", "cta", "mta.info", "soundtransit.org", "美國", "美国",
        ],
        "加拿大": [
            "canada", "toronto", "vancouver", "translink", "yaletown-roundhouse",
            "yaletown–roundhouse", "ttc", "skytrain", "加拿大",
        ],
        "西班牙": ["spain", "madrid", "barcelona", "西班牙"],
        "巴西": ["brazil", "brasil", "são paulo", "sao paulo", "sao-paulo", "saopaulo", "巴西", "聖保羅", "圣保罗"],
        "印度": ["india", "mumbai", "delhi metro", "印度", "孟買", "孟买"],
        "荷蘭": ["netherlands", "amsterdam", "rotterdam", "荷蘭", "荷兰"],
        "瑞士": ["switzerland", "zurich", "lausanne", "瑞士"],
        "義大利": ["italy", "milan", "rome", "turin", "義大利", "意大利"],
        "瑞典": ["sweden", "stockholm", "gothenburg", "瑞典"],
        "奧地利": ["austria", "vienna", "wien", "奧地利", "奥地利"],
        "丹麥": ["denmark", "copenhagen", "丹麥", "丹麦"],
        "挪威": ["norway", "oslo", "挪威"],
    }
    for region, terms in aliases.items():
        if any(term.casefold() in text_lower for term in terms):
            return region
    return "未判定"


def _candidate_date_obj(date_text: str) -> datetime.date | None:
    text = (date_text or "").strip()
    if not text or "未知" in text:
        return None
    try:
        return parsedate_to_datetime(text).date()
    except Exception:
        pass
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        pass
    for pattern in (r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", r"(\d{4})年(\d{1,2})月(\d{1,2})日"):
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
) -> dict:
    original_domain = _original_source_domain(source, url, source_href, query)
    quality, quality_reason = classify_source_quality(source, url, source_href)
    source_tier, source_tier_reason = classify_source_tier(source, url, source_href)
    source_display = source_label_for_report(source, url, source_href, source_tier)
    source_verb = source_verb_for_report(source_tier, source_display)
    region_value = region if region and region != "未判定" else guess_region_from_text(
        f"{title} {snippet} {source} {query} {url} {source_href}"
    )
    return {
        "title": _clean_text(title),
        "date": _clean_text(date) or "日期未知",
        "source": _clean_text(source) or (_domain_from_url(source_href or url) or "未判定來源"),
        "url": (url or "").strip(),
        "snippet": _shorten(snippet, REPORT_SNIPPET_CHARS),
        "query": _clean_text(query),
        "region": region_value,
        "source_type": source_type,
        "source_href": (source_href or "").strip(),
        "source_quality": quality,
        "source_quality_reason": quality_reason,
        "source_tier": source_tier,
        "source_tier_reason": source_tier_reason,
        "source_display": source_display,
        "source_verb": source_verb,
        "source_domain": original_domain or _domain_from_url(source_href or url),
    }


def parse_rss_candidates(raw_rss: str) -> list[dict]:
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
                candidates.append(_make_news_candidate(
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


def parse_ddg_candidates(raw_ddg: str) -> list[dict]:
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
                candidates.append(_make_news_candidate(
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


def dedupe_candidates(candidates: list[dict]) -> tuple[list[dict], dict[str, int]]:
    stats = {"URL 重複": 0, "標題正規化重複": 0, "標題相似重複": 0}
    seen_urls: set[str] = set()
    seen_title_keys: set[str] = set()
    title_keys: list[str] = []
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
            stats["URL 重複"] += 1
            continue
        if title_key and title_key in seen_title_keys:
            stats["標題正規化重複"] += 1
            continue
        if title_key and any(difflib.SequenceMatcher(None, title_key, existing).ratio() >= similarity_threshold for existing in title_keys):
            stats["標題相似重複"] += 1
            continue
        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_title_keys.add(title_key)
            title_keys.append(title_key)
        deduped.append(candidate)
    return deduped, stats


def preliminary_filter_candidate(candidate: dict) -> tuple[bool, str]:
    url = candidate.get("url", "")
    source_href = candidate.get("source_href", "")
    source = candidate.get("source", "")
    title = candidate.get("title", "")
    snippet = candidate.get("snippet", "")
    text = f"{title} {snippet} {source} {url} {source_href} {candidate.get('query', '')}"
    text_lower = text.casefold()
    candidate_region = _canonical_candidate_region(candidate)

    if not url:
        return False, "沒有 URL"

    is_valid, reason = _is_valid_news_url(url, source_href=source_href)
    if not is_valid:
        return False, reason

    date_obj = _candidate_date_obj(candidate.get("date", ""))
    if not date_obj:
        return False, "日期不明或無法判斷"
    cutoff_date = today - datetime.timedelta(days=max(1, min(int(lookback_days), 365)) + 3)
    if date_obj < cutoff_date:
        return False, "日期不符搜尋期間"
    if date_obj > today + datetime.timedelta(days=1):
        return False, "未來日期不合理"

    if _contains_taiwan_reference(text):
        return False, "國內新聞排除"

    if _contains_any_term(text, AIRPORT_PEOPLE_MOVER_EXCLUDE_TERMS):
        return False, "機場/航空 people mover 排除"

    if any(term.casefold() in text_lower for term in LOW_QUALITY_CONTENT_TERMS):
        return False, "旅遊/SEO/內容農場"

    information_issue = _information_quality_issue(candidate)
    if information_issue:
        return False, information_issue
    if _is_low_value_long_term_candidate(candidate):
        return False, "長期回顧低價值或錯分類候選"

    parsed_url = urlparse(url)
    path_lower = (parsed_url.path or "").casefold()
    has_entry_path = any(marker in path_lower for marker in LOW_INFORMATION_PATH_MARKERS)
    has_entry_terms = any(term.casefold() in text_lower for term in LOW_INFORMATION_PAGE_TERMS)
    has_technical_detail = _contains_any_term(text, TECH_NEWS_REQUIRED_TERMS)
    has_dispute_detail = _contains_any_term(text, [
        "strike", "fare dispute", "contract dispute", "lawsuit", "delay compensation",
        "cost overrun", "budget overrun", "service disruption", "public backlash",
        "罷工", "勞資爭議", "票價爭議", "合約糾紛", "工程延宕", "成本增加", "服務中斷", "民怨",
    ])
    has_policy_value = _contains_any_term(text, HIGH_VALUE_POLICY_TERMS) if "HIGH_VALUE_POLICY_TERMS" in globals() else False
    is_low_value_tier = candidate.get("source_tier") == "D_proxy_low_value"
    if (has_entry_path or has_entry_terms or is_low_value_tier) and not (
        has_technical_detail
        or has_dispute_detail
        or has_policy_value
        or _is_standard_update_candidate(text, require_url=True)
    ):
        return False, "入口頁/服務頁/分類頁且缺少明確事件"

    looks_like_standard = _is_standards_source(source) or any(
        standard.casefold() in text_lower
        for standards in STANDARDS_WATCHLIST.values()
        for standard in standards
    )
    if looks_like_standard:
        if "規範更新" not in selected_types:
            return False, "規範更新未勾選"
        if not _is_standard_update_candidate(f"{text} {candidate.get('date', '')}", require_url=True):
            return False, "規範更新條件不足"
        return True, ""

    if not is_global_scope:
        if candidate_region not in active_regions:
            if candidate_region in {"國際", "國際研究", "未判定"} and _is_allowed_international_candidate(candidate, text, looks_like_standard):
                candidate["region"] = "國際"
            else:
                return False, "國家/地區不在指定範圍"
    elif candidate_region in {"國際", "國際研究"} and not _is_allowed_international_candidate(candidate, text, looks_like_standard):
        candidate["region"] = "未判定"

    if not _is_urban_rail_candidate(text, source):
        return False, "非捷運/都市軌道"

    if _is_tech_news_only_mode() and not _is_technical_news_candidate(text, source):
        return False, "非技術新知"

    if candidate.get("source_quality") == "C" and not _contains_any_term(text, URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS):
        return False, "C級來源且主題關聯不足"

    return True, ""


def prepare_candidate_pool(raw_rss: str, raw_ddg: str) -> dict:
    parsed_candidates = parse_rss_candidates(raw_rss) + parse_ddg_candidates(raw_ddg)
    raw_candidates: list[dict] = []
    hard_excluded_candidates: list[dict] = []
    hard_exclusion_stats: dict[str, int] = {}
    for candidate in parsed_candidates:
        hard_reason = hard_low_value_candidate_reason(candidate)
        if hard_reason:
            hard_excluded_candidates.append(annotate_candidate_for_scheme_d(candidate, hard_reason))
            hard_exclusion_stats[hard_reason] = hard_exclusion_stats.get(hard_reason, 0) + 1
        else:
            raw_candidates.append(annotate_candidate_for_scheme_d(candidate))

    deduped_candidates, dedupe_stats = dedupe_candidates(raw_candidates)
    filtered_candidates: list[dict] = []
    excluded_candidates: list[dict] = hard_excluded_candidates.copy()
    exclusion_stats: dict[str, int] = hard_exclusion_stats.copy()

    for candidate in deduped_candidates:
        keep, reason = preliminary_filter_candidate(candidate)
        if keep:
            filtered_candidates.append(annotate_candidate_for_scheme_d(candidate))
        else:
            excluded_candidates.append(annotate_candidate_for_scheme_d(candidate, reason))
            exclusion_stats[reason] = exclusion_stats.get(reason, 0) + 1

    filtered_candidates = sorted(
        filtered_candidates,
        key=lambda item: (
            -int(item.get("python_score", 0) or 0),
            _source_tier_rank(item.get("source_tier", "C_media")),
            _quality_rank(item.get("source_quality", "B")),
            0 if item.get("source_type") in {"官方 RSS", "Google News 代理"} else 1,
            -_date_sort_key(item),
        ),
    )
    candidate_limit = min(get_selection_candidate_limit(lookback_int, fast_mode=fast_mode_enabled), MAX_SELECTION_CANDIDATES)
    model_candidates = [dict(item, id=idx) for idx, item in enumerate(filtered_candidates[:candidate_limit], 1)]
    candidate_cards = [build_candidate_card(candidate) for candidate in model_candidates]
    return {
        "raw_candidates": raw_candidates,
        "deduped_candidates": deduped_candidates,
        "filtered_candidates": filtered_candidates,
        "excluded_candidates": excluded_candidates,
        "model_candidates": model_candidates,
        "candidate_cards": candidate_cards,
        "candidate_card_limit": candidate_limit,
        "dedupe_stats": dedupe_stats,
        "exclusion_stats": exclusion_stats,
        "raw_count": len(raw_candidates),
        "deduped_count": len(deduped_candidates),
        "filtered_count": len(filtered_candidates),
    }


def build_long_term_coverage_warning(candidates: list[dict]) -> dict:
    if lookback_int not in ADVANCED_LOOKBACK_OPTIONS:
        return {"long_term_coverage_warning": False, "reason": ""}
    date_objs = [
        date_obj for date_obj in (_candidate_date_obj(candidate.get("date", "")) for candidate in candidates or [])
        if date_obj
    ]
    if not date_objs:
        return {
            "long_term_coverage_warning": True,
            "reason": "長期回顧候選資料缺少可解析日期，無法確認是否完整涵蓋本期。",
        }
    earliest = min(date_objs)
    expected_start = today - datetime.timedelta(days=lookback_int)
    recent_cutoff = today - datetime.timedelta(days=min(60, max(30, lookback_int // 5)))
    if earliest > recent_cutoff:
        return {
            "long_term_coverage_warning": True,
            "reason": "來源回傳資料多集中於近期，年度回顧可能無法完整代表全年。" if lookback_int == 365 else "來源回傳資料多集中於近期，長期回顧可能無法完整代表整個期間。",
            "earliest_candidate_date": earliest.isoformat(),
            "expected_start": expected_start.isoformat(),
        }
    return {
        "long_term_coverage_warning": False,
        "reason": "",
        "earliest_candidate_date": earliest.isoformat(),
        "expected_start": expected_start.isoformat(),
    }


def _unique_limited(values: list[str], limit: int = 5) -> list[str]:
    output: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in output:
            output.append(cleaned)
        if len(output) >= limit:
            break
    return output


def _annual_observation_dates_are_recent(candidates: list[dict]) -> bool:
    date_objs = [
        date_obj for date_obj in (_candidate_date_obj(candidate.get("date", "")) for candidate in candidates or [])
        if date_obj
    ]
    if not date_objs:
        return False
    return min(date_objs) > today - datetime.timedelta(days=60)


def _annual_observation_themes(candidates: list[dict]) -> list[str]:
    theme_terms = [
        ("號誌與列車控制", ["cbtc", "signalling", "signaling", "signal", "train control", "號誌", "信號"]),
        ("自動化與無人駕駛", ["driverless", "automation", "automated", "unattended train", "自動", "無人"]),
        ("車輛與車隊更新", ["rolling stock", "fleet", "trainset", "new train", "車輛", "列車"]),
        ("月臺門與車站設備", ["platform screen door", "platform doors", "psd", "elevator", "escalator", "月臺門", "月台門", "電梯", "電扶梯"]),
        ("供電與能源管理", ["power supply", "traction power", "substation", "third rail", "energy", "供電", "牽引", "變電", "能源"]),
        ("通訊、資安與資料治理", ["communications", "telecom", "radio", "5g", "lte", "cyber", "data", "通訊", "資安", "資料"]),
        ("維修監測與影像分析", ["maintenance", "monitoring", "condition monitoring", "video", "camera", "ai", "維修", "監測", "影像", "AI"]),
        ("AFC 與票務系統", ["afc", "ticketing", "fare gate", "fare", "票務", "票閘", "票價"]),
    ]
    combined = " ".join(
        f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('query', '')}"
        for candidate in candidates or []
    )
    return [label for label, terms in theme_terms if _contains_any_term(combined, terms)]


def build_annual_observation_section(selected_candidates: list[dict]) -> str:
    if lookback_int != 365:
        return ""
    candidates = selected_candidates or []
    if not candidates:
        return "## 年度觀察重點\n本年度回顧未取得可供歸納的已入選新聞，正式報告以下列已輸出章節為準。"

    candidate_regions = [_canonical_candidate_region(dict(candidate)) for candidate in candidates]
    regions = _unique_limited([
        region for region in candidate_regions if region not in {"未判定", "國際研究"}
    ])
    categories = [
        category for category in ADVANCED_TYPES
        if any((candidate.get("classification") or candidate.get("preliminary_type")) == category for candidate in candidates)
    ]
    themes = _unique_limited(_annual_observation_themes(candidates), 4)

    region_text = "、".join(regions) if regions else "已入選新聞所載地區"
    category_text = "、".join(categories) if categories else "已入選新聞類型"
    sentences = [
        f"本年度回顧依已入選新聞整理，案例主要分布於{region_text}，新聞類型以{category_text}為主。"
    ]
    if themes:
        sentences.append(f"從入選標題與摘要可見，觀察重點集中在{'、'.join(themes)}等都市軌道議題。")
    if _annual_observation_dates_are_recent(candidates):
        sentences.append("本年度回顧係依系統取得之候選資料整理，部分來源回傳資料集中於近期，故本報告以具明確日期與都市軌道關聯之案例為主。")
    return "## 年度觀察重點\n" + "".join(sentences)


def insert_annual_observation_section(report_md: str, selected_candidates: list[dict]) -> str:
    if lookback_int != 365 or "年度觀察重點" in (report_md or ""):
        return report_md
    section = build_annual_observation_section(selected_candidates)
    if not section:
        return report_md
    lines = (report_md or "").splitlines()
    insert_idx = 1 if lines and lines[0].lstrip().startswith("#") else 0
    while insert_idx < len(lines) and (not lines[insert_idx].strip() or lines[insert_idx].lstrip().startswith(">")):
        insert_idx += 1
    before = "\n".join(lines[:insert_idx]).rstrip()
    after = "\n".join(lines[insert_idx:]).lstrip()
    return f"{before}\n\n{section}\n\n{after}".strip()


def format_selection_candidate(candidate: dict) -> str:
    source_url = _effective_source_url(candidate)
    prompt_card = {
        "id": candidate.get("id", ""),
        "title": candidate.get("title", ""),
        "date": candidate.get("date", ""),
        "source_display": candidate.get("source_display", candidate.get("source", "")),
        "source_domain": candidate.get("source_domain") or _domain_from_url(source_url) or _extract_domain_hint(source_url),
        "region": candidate.get("region", "未判定"),
        "preliminary_type": candidate.get("preliminary_type", infer_preliminary_type(candidate)),
        "python_score": candidate.get("python_score", 0),
        "short_snippet": candidate.get("short_snippet", _shorten(candidate.get("snippet", ""), CANDIDATE_SNIPPET_CHARS)),
        "url": source_url,
    }
    return json.dumps(prompt_card, ensure_ascii=False)


def _selected_report_sections() -> str:
    lines = [
        f"{SECTION_NUMBER_BY_TYPE[category]}、{category}"
        for category in ADVANCED_TYPES
        if category in selected_types
    ]
    return "\n".join(lines) if lines else "無"


def _section_number_for_index(index: int) -> str:
    numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    if 1 <= index <= len(numerals):
        return numerals[index - 1]
    return str(index)


def research_section_heading(markdown: bool = False) -> str:
    selected_main_count = sum(1 for category in ADVANCED_TYPES if category in selected_types)
    heading = f"{_section_number_for_index(selected_main_count + 1)}、國際學術期刊"
    return f"## {heading}" if markdown else heading


def _selected_empty_section_rules() -> str:
    lines = [
        f"- {category}若無符合資料，請寫：「{EMPTY_TEXT_BY_TYPE[category]}」"
        for category in ADVANCED_TYPES
        if category in selected_types
    ]
    return "\n".join(lines) if lines else "- 未勾選新聞類型時，不得自行新增章節。"


def _selected_stats_template() -> str:
    parts = [f"{category} N 則" for category in ADVANCED_TYPES if category in selected_types]
    return " / ".join(parts) if parts else "無"


def _policy_selection_rule() -> str:
    if "營運政策" not in selected_types:
        return ""
    weekly_limit = "7 天週報中，營運政策原則最多 4～5 則。" if lookback_int == 7 else "營運政策需保留具制度、系統或治理價值者。"
    return f"""
- {weekly_limit}
- 營運政策優先：票價政策且涉及 AFC/票務系統、大型活動疏運且含班距/加班車/人流或車站管制、新線通車/試營運/系統轉換、建設治理/資產更新、維修窗口且有明確工程或系統影響。
- 營運政策降權或排除：單純假日提醒、活動搭乘資訊、週末服務公告、路線查詢/trip result/route page，或沒有班距、加班車、車站管制、人流管理、設備或系統資訊者。
- 同一週多則大型活動、假日或週末服務公告，請合併為 1 則綜合案例，不要逐則拆列；不得為了湊數納入低價值營運公告。
""".strip()


LOW_VALUE_POLICY_TERMS = [
    "holiday service", "weekend service", "weekender", "service advisory",
    "travel information", "trip result", "route page", "take transit",
    "RouteNumber", "route number", "minor delay", "detour", "service alert",
    "trip planner", "schedule change", "planned service change",
    "bus replacement", "shuttle bus", "customer notice", "service update",
    "temporary stop closure", "take the ttc", "route information", "public preview",
    "fare table", "game day", "event traffic", "escalator guide", "escalator information",
    "station entrance", "station access information", "accessibility policy",
    "accessibility service", "barrier-free", "construction work",
    "搭乘資訊", "假日服務", "週末服務", "服務提醒", "旅客資訊更新",
    "活動搭乘", "旅客資訊", "路線資訊", "票價表", "球賽", "活動交通",
    "電扶梯導引", "電扶梯資訊", "出入口資訊", "車站出入口",
    "無障礙政策", "無障礙服務", "施工通知", "工程通知",
]
HIGH_VALUE_POLICY_TERMS = [
    "fare", "afc", "ticketing", "headway", "special train", "extra train",
    "crowd control", "station control", "passenger information system",
    "trial operation", "system conversion", "asset renewal", "maintenance",
    "engineering works", "track renewal", "rail replacement", "signal testing",
    "system testing", "station equipment", "equipment upgrade",
    "fare adjustment", "major event", "event service", "station access control",
    "platform crowding", "passenger flow control",
    "票價", "票務", "班距", "加班車", "人流管制", "車站管制", "試營運",
    "系統轉換", "資產更新", "維修", "工程",
]


ACCIDENT_SIGNAL_TERMS = [
    "derailment", "collision", "fire", "smoke", "power outage", "signal failure",
    "service suspension", "disruption", "platform screen door", "train door",
    "death", "fatal", "killed", "injury", "injured", "crash", "hit", "rammed",
    "suspended", "heat damage", "damage", "barrier", "platform barrier",
    "entgleist", "Verletzte", "Unfall", "Zusammenstoß",
    "出軌", "脫軌", "追撞", "火災", "冒煙", "停駛", "供電異常", "號誌異常",
    "通訊異常", "月臺門", "車門異常", "死亡", "受傷", "撞擊", "營運中斷",
    "月臺屏障", "設備損壞",
]

SAFETY_INCIDENT_DETAIL_TERMS = [
    "derailment", "collision", "death", "fatal", "killed", "injury", "injured",
    "crash", "hit", "rammed", "disruption", "suspended", "heat damage",
    "damage", "platform barrier", "entgleist", "Verletzte", "Unfall",
    "Zusammenstoß", "死亡", "受傷", "撞擊", "出軌", "脫軌", "營運中斷",
    "停駛", "月臺屏障", "設備損壞",
]

LOW_VALUE_OFFICIAL_NOTICE_TERMS = [
    "construction notice", "contract documents holders list", "bid number",
    "open date", "take the ttc", "match", "stadium", "fireworks",
    "event service", "public preview", "route information", "travel information",
    "service advisory", "platform ilaa", "symbol character", "mascot",
    "character", "fare table", "game day", "event traffic", "escalator guide",
    "escalator information", "station entrance", "station access information",
    "accessibility policy", "accessibility service", "barrier-free", "construction work",
    "活動搭乘", "花火大會", "加開列車", "觀賽", "吉祥物", "角色",
    "標案文件持有人", "施工通知", "旅客資訊", "路線資訊", "票價表",
    "球賽", "活動交通", "電扶梯導引", "電扶梯資訊", "出入口資訊", "車站出入口",
    "無障礙政策", "無障礙服務", "工程通知",
]

NON_TECH_NEWS_EXCLUDE_TERMS = [
    "extra train", "special train", "theme train", "themed train",
    "character train", "stamp rally", "digital stamp", "passenger event",
    "road maintenance", "road works", "road construction", "road accident", "pothole", "bus",
    "autonomous bus", "self-driving bus", "tunnel boring machine farewell",
    "tbm farewell", "tbm removal", "tbm demobilization", "mascot", "character",
    "加開列車", "主題列車", "角色列車", "數位集章", "集章活動",
    "一般旅客活動", "旅客活動", "道路維護", "道路施工", "道路坑洞", "道路事故",
    "巴士", "公車", "自動駕駛巴士", "吉祥物", "角色",
    "隧道鑽掘機告別", "潛盾機告別", "潛盾機撤場",
]

NON_ACCIDENT_CONTEXT_TERMS = [
    "tunnel boring machine farewell", "tbm farewell", "road maintenance",
    "tbm removal", "tbm demobilization", "road works", "road construction",
    "road accident", "traffic accident", "pothole", "strike date",
    "roadblock", "police roadblock", "law enforcement", "enforcement case",
    "planned weekend closure", "weekend closure", "maintenance closure",
    "routine maintenance", "testing progress", "engineering milestone",
    "strike dates", "strike notice", "罷工日期", "罷工日期公告",
    "道路維護", "道路施工", "道路坑洞", "道路事故", "一般道路事故",
    "道路路障", "執法案件", "預定週末封閉", "週末封閉", "例行維修",
    "一般測試進度", "工程里程碑", "隧道鑽掘機告別", "潛盾機告別", "潛盾機撤場",
]

URBAN_RAIL_INCIDENT_CONTEXT_TERMS = [
    "metro", "subway", "underground", "tram", "light rail", "lrt", "mrt",
    "urban rail", "station", "platform", "train", "track", "railcar",
    "metro train", "subway train", "捷運", "地鐵", "都市軌道", "輕軌",
    "車站", "月臺", "月台", "列車", "軌道", "軌道車輛",
]

GENERAL_RAIL_EXCLUDE_TERMS = [
    "lirr", "long island rail road", "commuter rail", "regional rail",
    "intercity rail", "amtrak", "national rail",
]

PROCUREMENT_LIST_NOTICE_TERMS = [
    "contract documents holders list", "bid number", "open date", "標案文件持有人",
]

SUBSTANTIVE_POLICY_DETAIL_TERMS = [
    "headway", "capacity", "crowd control", "station control",
    "passenger flow control", "afc", "ticketing", "fare gate",
    "system conversion", "asset renewal", "engineering works",
    "signal testing", "system testing", "station equipment", "equipment upgrade",
    "班距", "容量", "人流管制", "車站管制", "旅客流量", "AFC", "票務系統",
    "票閘", "系統轉換", "資產更新", "號誌測試", "系統測試", "車站設備",
    "設備更新", "營運規劃",
]

STRONG_TECHNICAL_DETAIL_TERMS = [
    "cbtc", "train control", "signalling", "signaling", "signal system",
    "rolling stock", "trainset", "power supply", "traction power", "substation",
    "communications", "telecom", "cybersecurity", "api", "data governance",
    "platform screen door", "platform doors", "psd", "afc", "depot",
    "maintenance", "condition monitoring", "monitoring equipment",
    "video analytics", "ai image analysis", "system integration", "testing",
    "commissioning", "system verification",
    "號誌", "信號", "列控", "車輛", "供電", "牽引", "變電站", "通訊",
    "資安", "資料治理", "月臺門", "月台門", "票務系統", "機廠", "維修監測",
    "AI 影像分析", "影像分析", "系統整合", "測試驗證",
]

MEDIUM_TECHNICAL_DETAIL_TERMS = [
    "station equipment", "passenger information", "operations control",
    "operational control", "control centre", "control center", "maintenance facility",
    "vehicle introduction", "fleet introduction", "system upgrade", "equipment improvement",
    "safety management", "asset management", "station systems", "platform equipment",
    "escalator", "elevator", "air conditioning", "hvac", "passenger information system",
    "ai", "image analysis", "video analytics", "monitoring center", "safety center",
    "control room", "operations control center", "maintenance depot",
    "車站設備", "旅客資訊", "營運監控", "行控", "控制中心", "維修設施",
    "車輛導入", "系統更新", "設備改善", "營運安全管理", "資產管理",
    "電扶梯", "電梯", "空調", "月臺設備", "月台設備", "旅客資訊系統",
    "影像分析", "監控中心", "安全中心", "行控中心", "維修機廠",
]

WEEKLY_BACKFILL_ALLOWED_TERMS = [
    "station equipment", "escalator", "elevator", "air conditioning", "hvac",
    "platform equipment", "passenger information system", "ai", "image analysis",
    "video analytics", "data", "monitoring", "maintenance support",
    "operations control center", "control centre", "control center", "safety center",
    "monitoring center", "maintenance facility", "maintenance depot",
    "vehicle introduction", "fleet introduction", "rolling stock introduction",
    "safety management", "operations safety", "operational safety",
    "車站設備", "電扶梯", "電梯", "空調", "月臺設備", "月台設備",
    "旅客資訊系統", "AI", "影像", "資料", "監控", "維修輔助",
    "營運安全", "控制中心", "安全中心", "監控中心", "維修設施",
    "維修機廠", "車輛導入",
]

LOW_REPORT_VALUE_TERMS = [
    "passenger praised", "passenger praises", "traveller praised", "traveler praised",
    "clean and safe", "low fare", "cheap fare", "social media", "viral video",
    "youtube", "tiktok", "instagram", "personal experience", "first-time rider",
    "reviewed the metro", "lost property", "delay certificate", "mascot",
    "stamp rally", "theme train", "themed train", "road maintenance",
    "road works", "road construction", "pothole", "travel information",
    "weekend service", "weekend travel", "tourism information", "tbm farewell",
    "tbm removal", "tbm demobilization", "contract documents holders list",
    "旅客稱讚", "乘客稱讚", "乾淨安全", "低票價", "票價便宜", "社群影片",
    "個人經驗", "旅客心得", "失物招領", "延誤證明", "吉祥物", "數位集章",
    "主題列車", "道路維護", "道路施工", "道路坑洞", "旅遊資訊",
    "週末搭乘提醒", "潛盾機告別", "潛盾機撤場", "標案文件持有人",
]

FINANCIAL_MARKET_TERMS = [
    "yahoo finance", "finance.yahoo.com", "stock price", "share price",
    "stock market", "market cap", "trading", "ticker", "nasdaq", "nyse",
    "earnings", "quarterly results", "financial results", "investor",
    "investment analysis", "analyst rating", "price target",
    "股價", "股票", "股市", "財報", "營收", "投資分析", "投資人",
    "目標價", "券商", "分析師評級",
]

PROPERTY_OR_CAMPUS_DEVELOPMENT_TERMS = [
    "property development", "real estate", "land development", "campus development",
    "university campus", "commercial development", "shopping mall", "housing development",
    "white shek kok", "pak shek kok", "station-area development",
    "土地開發", "物業開發", "車站周邊開發", "校園發展", "校園開發",
    "白石角", "大學校園", "商場", "住宅開發",
]

GENERIC_TEST_WITHOUT_TECH_TERMS = [
    "resume weekend testing", "weekend testing resumes", "testing resumes",
    "restore weekend testing", "restored weekend testing", "trial runs resume",
    "恢復週末測試", "週末測試恢復", "恢復測試", "測試恢復", "試運轉恢復",
]

EQUIPMENT_FAILURE_TERMS = [
    "signal failure", "signalling failure", "signaling failure", "signal fault",
    "power failure", "power outage", "communications failure", "communication fault",
    "platform screen door failure", "platform door fault", "train door failure",
    "switch failure", "points failure", "afc failure", "ticketing system failure",
    "equipment failure", "equipment fault",
    "號誌故障", "號誌異常", "信號故障", "信號異常", "供電故障", "供電異常",
    "通訊故障", "通訊異常", "月臺門故障", "月台門故障", "車門故障",
    "轉轍器故障", "道岔故障", "票務系統故障", "自動收費故障", "設備故障",
]

ENGINEERING_MILESTONE_ONLY_TERMS = [
    "tunnel boring machine", "tbm", "tbm removal", "tbm demobilization",
    "tbm breakthrough", "construction milestone", "civil works complete",
    "construction progress", "site handover", "boring machine leaves",
    "隧道鑽掘機", "潛盾機", "潛盾機撤場", "潛盾機離場", "隧道鑽掘機離場",
    "工程里程碑", "施工進度", "土建完工", "工地移交",
]

SECURITY_OR_CRIME_TERMS = [
    "knife", "stabbing", "fight", "assault", "pepper spray", "tear gas",
    "irritant gas", "security incident", "police incident", "fare evasion",
    "roadblock", "law enforcement", "刀具", "持刀", "刺傷", "鬥毆", "打架",
    "刺激性氣體", "催淚氣體", "治安事件", "警方事件", "逃票", "道路路障", "執法案件",
]

MAJOR_SECURITY_RAIL_IMPACT_TERMS = [
    "fatal", "killed", "death", "multiple injuries", "serious injuries",
    "service suspended", "service suspension", "major disruption", "station evacuated",
    "train evacuated", "emergency response", "security lockdown",
    "死亡", "多人受傷", "重傷", "停駛", "營運中斷", "重大中斷",
    "車站疏散", "列車疏散", "緊急應變", "封鎖車站",
]

CORE_METRO_TECHNICAL_TERMS = [
    "rolling stock", "railcar", "trainset", "vehicle equipment", "depot equipment",
    "maintenance equipment", "signalling", "signaling", "signal system", "train control",
    "cbtc", "ato", "atp", "ats", "operations control", "operation control",
    "control centre", "control center", "occ", "traction power", "power supply",
    "substation", "regenerative braking", "energy storage", "energy management",
    "communications", "telecom", "radio", "wireless", "data transmission",
    "platform screen door", "platform door", "psd", "afc", "fare gate",
    "station equipment", "hvac", "air conditioning", "ventilation", "fire system",
    "environmental control", "escalator", "elevator", "condition monitoring",
    "fault diagnosis", "predictive maintenance", "video analytics", "image recognition",
    "ai image", "system integration", "system assurance", "rams", "safety verification",
    "interface management", "ot security", "ics security", "cybersecurity",
    "commissioning", "system testing", "technical verification",
    "電聯車", "車輛設備", "機廠設備", "維修設備", "號誌", "信號", "列車控制",
    "列控", "行車監控", "行控中心", "牽引供電", "一般電力", "變電站", "再生煞車",
    "儲能", "能源管理", "通訊系統", "無線通訊", "資料傳輸", "月臺門", "月台門",
    "自動收費", "票務系統", "票閘", "車站機電", "空調", "通風", "消防",
    "環境控制", "電扶梯", "電梯", "無障礙機電", "狀態監測", "故障診斷",
    "預測性維護", "影像辨識", "系統整合", "系統保證", "安全驗證", "介面管理",
    "資安", "工控資安", "系統測試", "技術驗證", "投入營運",
]

TECHNICAL_IMPLEMENTATION_TERMS = [
    "introduce", "introduced", "deploy", "deployed", "roll out", "upgrade",
    "renewal", "replace", "replacement", "retrofit", "modernisation", "modernization",
    "commission", "commissioning", "enter service", "entered service", "launch",
    "trial", "pilot", "test", "testing", "verification", "validated", "validation",
    "installation", "integrated", "integration", "improvement", "new system",
    "new equipment", "導入", "啟用", "部署", "升級", "更新", "汰換",
    "改造", "現代化", "試辦", "試行", "測試", "驗證", "改善", "新系統",
    "新設備", "安裝", "整合", "投入營運", "正式營運",
]

LOW_IMPACT_ACCIDENT_TERMS = [
    "animal on tracks", "dog on tracks", "cat on tracks", "bird on tracks",
    "passenger dispute", "minor altercation", "trespasser", "small animal",
    "動物落軌", "犬隻落軌", "貓落軌", "小動物", "旅客糾紛", "輕微衝突",
]

HIGH_IMPACT_ACCIDENT_TERMS = [
    "third rail", "power rail", "platform screen door", "platform barrier",
    "service suspension", "major disruption", "investigation", "safety review",
    "brake failure", "switch failure", "points failure", "power outage",
    "第三軌", "供電軌", "月臺門", "月臺屏障", "停駛", "重大中斷",
    "制度檢討", "安全檢討", "煞車失效", "轉轍器", "供電異常",
]

REGION_DOMAIN_HINTS = {
    "translink.ca": "加拿大",
    "ttc.ca": "加拿大",
    "mta.info": "美國",
    "wmata.com": "美國",
    "soundtransit.org": "美國",
    "tokyometro.jp": "日本",
    "mtr.com.hk": "香港",
    "lta.gov.sg": "新加坡",
    "smrt.com.sg": "新加坡",
    "ratp.fr": "法國",
    "tfl.gov.uk": "英國",
}

REPORT_SELECTION_DEBUG_DEFAULT = {
    "strict_selected_count": 0,
    "borderline_added_count": 0,
    "borderline_candidates": [],
    "shortfall_before_backfill": 0,
    "shortfall_after_backfill": 0,
    "backfill_reason": "",
    "duplicate_event_records": [],
}

WORK_ZONE_MONITORING_TERMS = [
    "work zone", "speed enforcement", "construction zone", "maintenance safety",
    "工區", "施工區", "速限執法", "維修作業安全", "施工安全", "安全監測",
]

WORK_ZONE_TECH_DETAIL_TERMS = [
    "sensor", "camera", "video", "monitoring equipment", "automated monitoring",
    "backend platform", "communication", "network", "感測", "攝影", "影像",
    "監測設備", "自動化監測", "後端平台", "通訊", "網路",
]


def _candidate_selection_text(candidate: dict) -> str:
    paths = " ".join(
        urlparse(candidate.get(key, "") or "").path.replace("/", " ")
        for key in ("url", "source_href")
    )
    return (
        f"{candidate.get('title', '')} {candidate.get('snippet', '')} "
        f"{candidate.get('source', '')} "
        f"{candidate.get('url', '')} {candidate.get('source_href', '')} {paths}"
    )


def _is_accident_signal_text(text: str) -> bool:
    if _contains_any_term(text, NON_ACCIDENT_CONTEXT_TERMS):
        return False
    if _contains_any_term(text, SECURITY_OR_CRIME_TERMS) and not _contains_any_term(text, MAJOR_SECURITY_RAIL_IMPACT_TERMS):
        return False
    if not _contains_any_term(text, URBAN_RAIL_INCIDENT_CONTEXT_TERMS):
        return False
    if _contains_any_term(text, SAFETY_INCIDENT_DETAIL_TERMS):
        return True
    equipment_terms = [
        "platform screen door", "platform doors", "train door", "barrier",
        "platform barrier", "月臺門", "月台門", "車門", "月臺屏障",
    ]
    issue_terms = [
        "failure", "fault", "damage", "incident", "accident", "review",
        "safety", "stuck", "broken", "異常", "故障", "損壞", "事故", "檢討", "安全",
    ]
    return _contains_any_term(text, equipment_terms) and _contains_any_term(text, issue_terms)


def _has_strong_technical_detail_text(text: str) -> bool:
    return _contains_any_term(text, STRONG_TECHNICAL_DETAIL_TERMS)


def _has_explicit_technical_system_detail(candidate: dict) -> bool:
    flags = set(candidate.get("candidate_flags", []) or [])
    if "technical_or_system_detail" in flags:
        return True
    return _has_strong_technical_detail_text(_candidate_selection_text(candidate))


def _has_good_report_signal(candidate: dict) -> bool:
    flags = set(candidate.get("candidate_flags", []) or [])
    if flags.intersection({"technical_or_system_detail", "incident_or_safety_signal", "high_value_policy"}):
        return True
    text = _candidate_selection_text(candidate)
    return (
        _has_strong_technical_detail_text(text)
        or _is_accident_signal_text(text)
        or _contains_any_term(text, HIGH_VALUE_POLICY_TERMS)
    )


def _has_low_value_official_notice(candidate: dict) -> bool:
    return _contains_any_term(_candidate_selection_text(candidate), LOW_VALUE_OFFICIAL_NOTICE_TERMS)


def _has_procurement_list_notice(candidate: dict) -> bool:
    return _contains_any_term(_candidate_selection_text(candidate), PROCUREMENT_LIST_NOTICE_TERMS)


def _is_financial_market_candidate(candidate: dict) -> bool:
    text = _candidate_selection_text(candidate)
    return _contains_any_term(text, FINANCIAL_MARKET_TERMS)


def _is_security_or_crime_candidate(candidate: dict) -> bool:
    return _contains_any_term(_candidate_selection_text(candidate), SECURITY_OR_CRIME_TERMS)


def _has_major_security_rail_impact(candidate: dict) -> bool:
    text = _candidate_selection_text(candidate)
    return _contains_any_term(text, MAJOR_SECURITY_RAIL_IMPACT_TERMS)


def _has_core_metro_technical_content(candidate: dict) -> bool:
    text = _candidate_selection_text(candidate)
    if _is_financial_market_candidate(candidate):
        return False
    if _is_security_or_crime_candidate(candidate):
        return False
    if _contains_any_term(text, EQUIPMENT_FAILURE_TERMS):
        return False
    if _contains_any_term(text, PROPERTY_OR_CAMPUS_DEVELOPMENT_TERMS) and not _contains_any_term(text, CORE_METRO_TECHNICAL_TERMS):
        return False
    if _contains_any_term(text, ENGINEERING_MILESTONE_ONLY_TERMS) and not _contains_any_term(text, CORE_METRO_TECHNICAL_TERMS):
        return False
    if _contains_any_term(text, GENERIC_TEST_WITHOUT_TECH_TERMS) and not _contains_any_term(text, CORE_METRO_TECHNICAL_TERMS):
        return False

    has_core_system = _contains_any_term(text, CORE_METRO_TECHNICAL_TERMS)
    has_implementation = _contains_any_term(text, TECHNICAL_IMPLEMENTATION_TERMS)
    has_ai_or_data = _contains_any_term(text, ["ai", "artificial intelligence", "data analytics", "machine learning", "影像辨識", "資料分析", "人工智慧"])
    has_ai_application_context = _contains_any_term(
        text,
        [
            "maintenance", "monitoring", "condition monitoring", "fault diagnosis",
            "predictive maintenance", "operations control", "safety", "equipment",
            "signal", "power", "platform door", "維修", "監測", "故障診斷",
            "預測性維護", "行控", "營運安全", "設備", "號誌", "供電", "月臺門", "月台門",
        ],
    )
    if not has_core_system:
        return False
    return has_implementation or (has_ai_or_data and has_ai_application_context)


def _has_general_rail_exclusion(candidate: dict) -> bool:
    return _contains_any_term(_candidate_selection_text(candidate), GENERAL_RAIL_EXCLUDE_TERMS)


def _has_substantive_detail_for_low_value_notice(candidate: dict) -> bool:
    text = _candidate_selection_text(candidate)
    return (
        _contains_any_term(text, STRONG_TECHNICAL_DETAIL_TERMS)
        or _contains_any_term(text, SAFETY_INCIDENT_DETAIL_TERMS)
        or _contains_any_term(text, SUBSTANTIVE_POLICY_DETAIL_TERMS)
        or _contains_any_term(text, WEEKLY_BACKFILL_ALLOWED_TERMS)
    )


def _has_long_term_report_value(candidate: dict) -> bool:
    text = _candidate_selection_text(candidate)
    return (
        _has_good_report_signal(candidate)
        or _contains_any_term(text, STRONG_TECHNICAL_DETAIL_TERMS)
        or _contains_any_term(text, SAFETY_INCIDENT_DETAIL_TERMS)
        or _contains_any_term(text, SUBSTANTIVE_POLICY_DETAIL_TERMS)
        or _contains_any_term(text, HIGH_IMPACT_ACCIDENT_TERMS)
    )


def _is_low_value_long_term_candidate(candidate: dict) -> bool:
    if int(lookback_int) not in ADVANCED_LOOKBACK_OPTIONS:
        return False
    text = _candidate_selection_text(candidate)
    classification = candidate.get("classification") or candidate.get("preliminary_type") or infer_preliminary_type(candidate)
    if _contains_any_term(text, LOW_REPORT_VALUE_TERMS) and not _has_long_term_report_value(candidate):
        return True
    if _contains_any_term(text, NON_TECH_NEWS_EXCLUDE_TERMS) and not _has_long_term_report_value(candidate):
        return True
    if _contains_any_term(text, CIVIC_METRO_NAME_ONLY_TERMS) and not _contains_any_term(text, URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS):
        return True
    if classification == "重大事故" and not _is_accident_signal_text(text):
        return True
    return False


def _is_technical_news_selection_candidate(candidate: dict) -> bool:
    if candidate.get("classification") != "技術新知":
        return False
    text = _candidate_selection_text(candidate)
    if _is_financial_market_candidate(candidate):
        return False
    if _contains_any_term(text, NON_TECH_NEWS_EXCLUDE_TERMS):
        return False
    if _is_accident_signal_text(text):
        return False
    if not _has_core_metro_technical_content(candidate):
        return False
    if not _has_explicit_technical_system_detail(candidate):
        return False
    if _has_low_value_official_notice(candidate):
        return False
    return True


def get_selection_candidate_limit(days: int, fast_mode: bool = False) -> int:
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 7
    if fast_mode:
        if days >= 90:
            return 100
        if days >= 30:
            return 80
        if days >= 14:
            return 70
        return 60
    if days >= 90:
        return 150
    if days >= 30:
        return 120
    return 100


def get_selection_output_range(days: int) -> str:
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 7
    if days >= 365:
        return "12～20"
    if days >= 180:
        return "12～18"
    if days >= 90:
        return "10～15"
    if days >= 30:
        return "10～15"
    if days >= 14:
        return "10～14"
    return "8～12"


def infer_preliminary_type(candidate: dict) -> str:
    text = _candidate_selection_text(candidate)
    if _is_standard_update_candidate(f"{text} {candidate.get('date', '')}", require_url=True):
        return "規範更新"
    if _contains_any_term(text, EQUIPMENT_FAILURE_TERMS):
        if _contains_any_term(text, HIGH_IMPACT_ACCIDENT_TERMS + ["service suspension", "service suspended", "major disruption", "營運中斷", "停駛", "重大中斷"]):
            return "重大事故"
        return "營運政策"
    if _contains_any_term(text, ENGINEERING_MILESTONE_ONLY_TERMS) and not _has_core_metro_technical_content(candidate):
        return "營運政策"
    if _is_security_or_crime_candidate(candidate) and not _has_major_security_rail_impact(candidate):
        return "營運政策"
    if _is_accident_signal_text(text):
        return "重大事故"
    if _contains_any_term(text, ["strike", "contract dispute", "lawsuit", "fare dispute", "budget overrun", "罷工", "合約糾紛", "票價爭議", "預算超支", "民怨"]):
        return "營運爭議"
    if _contains_any_term(text, WORK_ZONE_MONITORING_TERMS) and not _contains_any_term(text, WORK_ZONE_TECH_DETAIL_TERMS):
        return "營運政策"
    if _contains_any_term(text, LOW_VALUE_OFFICIAL_NOTICE_TERMS):
        return "營運政策"
    if _contains_any_term(text, HIGH_VALUE_POLICY_TERMS + LOW_VALUE_POLICY_TERMS):
        return "營運政策"
    return "技術新知"


def build_candidate_flags(candidate: dict) -> list[str]:
    text = _candidate_selection_text(candidate)
    flags: list[str] = []
    information_issue = _information_quality_issue(candidate)
    if candidate.get("source_tier") == "A_official":
        flags.append("official_source")
    if candidate.get("source_tier") == "B_professional":
        flags.append("professional_source")
    if candidate.get("source_tier") == "D_proxy_low_value":
        flags.append("low_value_proxy_or_page")
    if _domain_from_url(_effective_source_url(candidate)):
        flags.append("source_domain_detected")
    if "news.google.com" in _domain_from_url(candidate.get("url", "")):
        flags.append("google_news_proxy")
        if not (candidate.get("source_domain") or _original_source_domain(
            candidate.get("source", ""),
            candidate.get("url", ""),
            candidate.get("source_href", ""),
            candidate.get("query", ""),
        )):
            flags.append("source_domain_unresolved")
    if _candidate_date_obj(candidate.get("date", "")):
        flags.append("date_detected")

    if _is_urban_rail_candidate(text, candidate.get("source", "")):
        flags.append("urban_rail")
    if _has_strong_technical_detail_text(text):
        flags.append("technical_or_system_detail")
    if _has_core_metro_technical_content(candidate):
        flags.append("core_metro_technical_content")
    if _is_accident_signal_text(text):
        flags.append("incident_or_safety_signal")
    if _contains_any_term(text, HIGH_VALUE_POLICY_TERMS):
        flags.append("high_value_policy")
    if _contains_any_term(text, LOW_VALUE_POLICY_TERMS) or information_issue in {"日常服務推播", "低價值路線公告"}:
        flags.append("low_value_service_notice")
    if _has_low_value_official_notice(candidate):
        flags.append("low_value_official_notice")
    if _has_procurement_list_notice(candidate):
        flags.append("procurement_list_notice")
    if _is_financial_market_candidate(candidate):
        flags.append("financial_market_content")
    if _contains_any_term(text, EQUIPMENT_FAILURE_TERMS):
        flags.append("equipment_failure_not_tech")
    if _is_security_or_crime_candidate(candidate):
        flags.append("security_or_crime_context")
    if _contains_any_term(text, PROPERTY_OR_CAMPUS_DEVELOPMENT_TERMS):
        flags.append("property_or_campus_development")
    if _contains_any_term(text, GENERIC_TEST_WITHOUT_TECH_TERMS):
        flags.append("generic_testing_notice")
    if _has_general_rail_exclusion(candidate):
        flags.append("general_rail_exclusion")
    if information_issue == "摘要資訊不足":
        flags.append("insufficient_information")
    if len(candidate.get("title", "")) < 20:
        flags.append("short_title")
    if len(candidate.get("snippet", "")) < 80:
        flags.append("short_snippet")
    return flags


def score_news_candidate(candidate: dict) -> dict:
    text = _candidate_selection_text(candidate)
    score = 50
    reasons: list[str] = []
    tier = candidate.get("source_tier", "C_media")
    if tier == "A_official":
        score += 20
        reasons.append("官方來源 +20")
    elif tier == "B_professional":
        score += 14
        reasons.append("專業鐵道媒體 +14")
    elif tier == "C_media":
        score -= 4
        reasons.append("一般媒體 -4")
    elif tier == "D_proxy_low_value":
        score -= 25
        reasons.append("低價值頁面/代理來源 -25")

    if _candidate_date_obj(candidate.get("date", "")):
        score += 10
        reasons.append("明確日期 +10")
    else:
        score -= 20
        reasons.append("日期不明 -20")

    source_url = _effective_source_url(candidate)
    unresolved_google_proxy = (
        "news.google.com" in _domain_from_url(candidate.get("url", ""))
        and "news.google.com" in _domain_from_url(source_url)
    )
    if _extract_complete_url(source_url):
        score += 8
        reasons.append("完整 URL +8")
    elif _extract_domain_hint(source_url):
        score += 4
        reasons.append("可辨識 domain +4")
    else:
        score -= 15
        reasons.append("URL 不完整 -15")

    if unresolved_google_proxy:
        score -= 10
        reasons.append("Google News proxy unresolved original source -10")

    if _is_urban_rail_candidate(text, candidate.get("source", "")):
        score += 15
        reasons.append("都市軌道明確 +15")
    else:
        score -= 30
        reasons.append("都市軌道關聯不足 -30")

    if _has_strong_technical_detail_text(text):
        score += 15
        reasons.append("機電/系統技術訊號 +15")
    if _is_accident_signal_text(text):
        score += 10
        reasons.append("事故/安全訊號 +10")
    if _contains_any_term(text, HIGH_VALUE_POLICY_TERMS):
        score += 8
        reasons.append("高價值營運政策訊號 +8")
    if _contains_any_term(text, LOW_VALUE_POLICY_TERMS):
        score -= 12
        reasons.append("低價值服務提醒 -12")
    if _has_low_value_official_notice(candidate) and not _has_explicit_technical_system_detail(candidate):
        score -= 35
        reasons.append("低價值官方公告且缺少機電細節 -35")
    if _has_general_rail_exclusion(candidate):
        score -= 40
        reasons.append("一般鐵路/通勤鐵路排除訊號 -40")
    if _is_financial_market_candidate(candidate):
        score -= 45
        reasons.append("股票行情或企業財經分析 -45")
    if any(marker in urlparse(candidate.get("url", "")).path.casefold() for marker in LOW_INFORMATION_PATH_MARKERS):
        score -= 18
        reasons.append("入口/路線/查詢頁路徑 -18")
    if any(term.casefold() in text.casefold() for term in LOW_QUALITY_CONTENT_TERMS):
        score -= 15
        reasons.append("旅遊/SEO/低價值內容 -15")
    if len(candidate.get("title", "")) < 20:
        score -= 5
        reasons.append("標題過短 -5")
    if len(candidate.get("snippet", "")) < 80:
        score -= 8
        reasons.append("摘要過短 -8")

    information_issue = _information_quality_issue(candidate)
    if information_issue == "日常服務推播":
        score -= 25
        reasons.append("日常服務推播 -25")
    elif information_issue == "低價值路線公告":
        score -= 30
        reasons.append("低價值路線公告 -30")
    elif information_issue == "摘要資訊不足":
        score -= 18
        reasons.append("摘要資訊不足 -18")

    flags = build_candidate_flags(candidate)
    good_flags = {"technical_or_system_detail", "incident_or_safety_signal", "high_value_policy"}
    has_good_flag = bool(set(flags).intersection(good_flags))
    if not has_good_flag:
        score_cap = 55 if "short_snippet" in flags else 65
        if score > score_cap:
            score = score_cap
            reasons.append(f"缺少技術/事故/高價值政策旗標，分數上限 {score_cap}")
    if (tier == "D_proxy_low_value" or "low_value_service_notice" in flags) and not _has_explicit_technical_system_detail(candidate):
        if score > 50:
            score = 50
            reasons.append("低價值來源或服務提醒且無技術細節，分數上限 50")
    preliminary_type = infer_preliminary_type(candidate)
    return {
        "python_score": max(0, min(100, score)),
        "score_reason": "；".join(reasons),
        "candidate_flags": flags,
        "preliminary_type": preliminary_type,
        "short_snippet": _shorten(candidate.get("snippet", ""), CANDIDATE_SNIPPET_CHARS),
        "source_domain": candidate.get("source_domain") or _domain_from_url(_effective_source_url(candidate)),
    }


def annotate_candidate_for_scheme_d(candidate: dict, exclude_reason: str = "") -> dict:
    enriched = dict(candidate)
    enriched.update(score_news_candidate(enriched))
    enriched["exclude_reason"] = exclude_reason
    return enriched


def build_candidate_card(candidate: dict) -> dict:
    source_url = _effective_source_url(candidate)
    return {
        "id": candidate.get("id", ""),
        "date": candidate.get("date", ""),
        "title": candidate.get("title", ""),
        "source_display": candidate.get("source_display", candidate.get("source", "")),
        "source_domain": candidate.get("source_domain") or _domain_from_url(source_url),
        "source_tier": candidate.get("source_tier", ""),
        "source_type": candidate.get("source_type", ""),
        "source_verb": candidate.get("source_verb", ""),
        "region": candidate.get("region", "未判定"),
        "preliminary_type": candidate.get("preliminary_type", infer_preliminary_type(candidate)),
        "short_snippet": candidate.get("short_snippet", _shorten(candidate.get("snippet", ""), CANDIDATE_SNIPPET_CHARS)),
        "url": source_url,
        "python_score": candidate.get("python_score", 0),
        "score_reason": candidate.get("score_reason", ""),
        "candidate_flags": candidate.get("candidate_flags", []),
    }


def _is_low_value_policy_candidate(candidate: dict) -> bool:
    text = f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('query', '')}"
    has_low = _contains_any_term(text, LOW_VALUE_POLICY_TERMS)
    has_high = _contains_any_term(text, HIGH_VALUE_POLICY_TERMS)
    return has_low and not has_high


def rebalance_selected_candidates(selected: list[dict]) -> list[dict]:
    if lookback_int != 7 or "營運政策" not in selected_types:
        return selected
    balanced: list[dict] = []
    policy_count = 0
    for candidate in selected:
        if candidate.get("classification") != "營運政策":
            balanced.append(candidate)
            continue
        if _is_low_value_policy_candidate(candidate):
            candidate = dict(candidate)
            candidate["selected_reason"] = (
                f"{candidate.get('selected_reason', '')}；因屬一般服務公告，週報中降權。"
            ).strip("；")
            if policy_count >= 3:
                continue
        if policy_count >= 5:
            continue
        policy_count += 1
        balanced.append(candidate)
    return balanced


def _selection_target_range(days: int) -> tuple[int, int]:
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 7
    if days >= 365:
        return 12, 20
    if days >= 180:
        return 12, 18
    if days >= 90:
        return 10, 15
    if days >= 30:
        return 10, 15
    if days >= 14:
        return 10, 14
    return 8, 12


def _selection_classification(candidate: dict) -> str:
    preliminary_type = candidate.get("preliminary_type")
    if preliminary_type in ADVANCED_TYPES:
        return preliminary_type
    return infer_preliminary_type(candidate)


def _has_source_reference(candidate: dict) -> bool:
    source_url = _effective_source_url(candidate)
    return bool(_extract_complete_url(source_url) or candidate.get("source_domain") or _extract_domain_hint(source_url))


def _selection_good_flag_count(candidate: dict) -> int:
    flags = set(candidate.get("candidate_flags", []) or [])
    return sum(1 for flag in ("technical_or_system_detail", "incident_or_safety_signal", "high_value_policy") if flag in flags)


def _selection_bad_flag_count(candidate: dict) -> int:
    flags = set(candidate.get("candidate_flags", []) or [])
    return sum(1 for flag in (
        "low_value_service_notice", "insufficient_information", "short_snippet",
        "low_value_official_notice", "procurement_list_notice", "general_rail_exclusion",
    ) if flag in flags)


def _candidate_month_key(candidate: dict) -> str:
    date_obj = _candidate_date_obj(candidate.get("date", ""))
    return date_obj.strftime("%Y-%m") if date_obj else "日期未知"


def _candidate_system_theme(candidate: dict) -> str:
    text = f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('query', '')}"
    theme_terms = [
        ("號誌與列車控制", ["cbtc", "signalling", "signaling", "signal", "train control", "號誌", "信號"]),
        ("自動化與無人駕駛", ["driverless", "automation", "automated", "unattended train", "自動", "無人"]),
        ("車輛與車隊更新", ["rolling stock", "fleet", "trainset", "new train", "車輛", "列車"]),
        ("月臺門與車站設備", ["platform screen door", "platform doors", "psd", "elevator", "escalator", "月臺門", "月台門", "電梯", "電扶梯"]),
        ("供電與能源管理", ["power supply", "traction power", "substation", "third rail", "energy", "供電", "牽引", "變電", "能源"]),
        ("通訊、資安與資料治理", ["communications", "telecom", "radio", "5g", "lte", "cyber", "data", "通訊", "資安", "資料"]),
        ("維修監測與影像分析", ["maintenance", "monitoring", "condition monitoring", "video", "camera", "ai", "維修", "監測", "影像", "AI"]),
        ("AFC 與票務系統", ["afc", "ticketing", "fare gate", "fare", "票務", "票閘", "票價"]),
    ]
    for label, terms in theme_terms:
        if _contains_any_term(text, terms):
            return label
    return candidate.get("classification") or candidate.get("preliminary_type") or "未分類"


def _candidate_incident_type(candidate: dict) -> str:
    text = _candidate_selection_text(candidate)
    incident_terms = [
        ("tram_collision", ["tram", "streetcar", "collision", "crash", "hit", "rammed", "電車", "路面電車", "撞擊", "碰撞"]),
        ("derailment", ["derailment", "derailed", "entgleist", "出軌", "脫軌"]),
        ("power_supply", ["power outage", "power failure", "traction power", "third rail", "供電", "牽引", "第三軌"]),
        ("signal_or_switch", ["signal failure", "signalling", "signaling", "switch failure", "points failure", "號誌", "信號", "轉轍器", "道岔"]),
        ("platform_door", ["platform screen door", "platform door", "psd", "月臺門", "月台門"]),
        ("service_disruption", ["service suspension", "disruption", "suspended", "停駛", "營運中斷", "重大中斷"]),
        ("security", SECURITY_OR_CRIME_TERMS),
    ]
    for label, terms in incident_terms:
        if _contains_any_term(text, terms):
            return label
    return _candidate_system_theme(candidate)


EVENT_LOCATION_TERMS = [
    "tokyo", "osaka", "seoul", "singapore", "hong kong", "sydney", "melbourne",
    "london", "paris", "berlin", "munich", "new york", "washington", "chicago",
    "toronto", "vancouver", "houston", "madrid", "barcelona", "amsterdam", "rotterdam",
    "basel", "zurich", "leipzig", "adlershof", "milan", "rome", "stockholm",
    "vienna", "copenhagen", "oslo", "northern ireland", "belfast",
    "東京", "大阪", "首爾", "新加坡", "香港", "雪梨", "悉尼", "墨爾本",
    "倫敦", "巴黎", "柏林", "慕尼黑", "紐約", "華盛頓", "芝加哥",
    "多倫多", "溫哥華", "休士頓", "馬德里", "巴塞隆納", "阿姆斯特丹", "鹿特丹",
    "巴塞爾", "蘇黎世", "萊比錫", "米蘭", "羅馬", "斯德哥爾摩",
    "維也納", "哥本哈根", "奧斯陸", "北愛爾蘭", "貝爾法斯特",
]


PROJECT_SERIES_TERMS = [
    "project", "programme", "program", "extension", "line", "station", "construction",
    "contract", "upgrade", "rollout", "renewal", "trial", "testing", "commissioning",
    "opening", "launch", "fleet", "trainset", "cbtc", "signalling", "signaling",
    "platform screen door", "depot", "maintenance facility",
    "計畫", "專案", "延伸線", "路線", "車站", "工程", "合約", "升級", "更新",
    "試運轉", "測試", "通車", "啟用", "車隊", "列車", "號誌", "月臺門", "機廠",
]

PROJECT_STAGE_GROUPS = {
    "procurement": [
        "contract", "award", "tender", "bid", "procurement", "合約", "得標", "招標", "採購",
    ],
    "construction": [
        "construction", "works", "tunnel", "tbm", "civil works", "工程", "施工", "隧道", "潛盾",
    ],
    "testing": [
        "testing", "trial", "commissioning", "test run", "試運轉", "測試", "試車", "調試",
    ],
    "opening": [
        "opening", "opens", "launch", "service begins", "starts service", "通車", "啟用", "營運",
    ],
    "vehicle": [
        "trainset", "rolling stock", "fleet", "vehicle", "train arrival", "車輛", "列車", "車隊",
    ],
    "systems": [
        "cbtc", "signalling", "signaling", "platform screen door", "power supply",
        "號誌", "信號", "月臺門", "月台門", "供電",
    ],
}


def _candidate_specific_event_location(candidate: dict) -> str:
    text = _candidate_selection_text(candidate).casefold()
    priority_locations = [
        ("berlin-adlershof", ["adlershof"]),
        ("basel", ["basel", "巴塞爾"]),
        ("leipzig", ["leipzig", "萊比錫"]),
        ("houston", ["houston", "休士頓", "休斯頓"]),
        ("vancouver", ["vancouver", "broadway subway", "溫哥華"]),
        ("toronto", ["toronto", "finch west", "多倫多"]),
        ("northern-ireland", ["northern ireland", "belfast", "北愛爾蘭", "貝爾法斯特"]),
        ("berlin", ["berlin", "柏林"]),
    ]
    for canonical, terms in priority_locations:
        if any(term.casefold() in text for term in terms):
            return canonical
    for term in EVENT_LOCATION_TERMS:
        if term.casefold() in text:
            return term.casefold()
    return ""


def _candidate_event_location(candidate: dict) -> str:
    specific = _candidate_specific_event_location(candidate)
    if specific:
        return specific
    return str(candidate.get("region", "") or "").casefold()


def _event_date_close(left: dict, right: dict, days: int = 3) -> bool:
    left_date = _candidate_date_obj(left.get("date", ""))
    right_date = _candidate_date_obj(right.get("date", ""))
    if not left_date or not right_date:
        return True
    return abs((left_date - right_date).days) <= days


def _event_similarity_text(candidate: dict) -> str:
    text = _candidate_selection_text(candidate)
    text = _strip_source_name_noise(text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\b(20\d{2})[-/]\d{1,2}[-/]\d{1,2}\b", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.casefold().strip()


def _is_project_series_candidate(candidate: dict) -> bool:
    return _contains_any_term(_candidate_selection_text(candidate), PROJECT_SERIES_TERMS)


def _candidate_project_stage(candidate: dict) -> str:
    text = _candidate_selection_text(candidate)
    for stage, terms in PROJECT_STAGE_GROUPS.items():
        if _contains_any_term(text, terms):
            return stage
    return ""


def _same_project_stage_or_unspecified(left: dict, right: dict) -> bool:
    left_stage = _candidate_project_stage(left)
    right_stage = _candidate_project_stage(right)
    return not left_stage or not right_stage or left_stage == right_stage


def _duplicate_event_reason(candidate: dict, selected_item: dict) -> str:
    if int(lookback_int) in ADVANCED_LOOKBACK_OPTIONS and _is_project_series_candidate(candidate) and _is_project_series_candidate(selected_item):
        return "同一城市/地點、相同系統主題與相近專案階段，長期回顧視為同一專案系列。"
    if candidate.get("classification") == "重大事故":
        return "同一城市/地點、相近日期與相同事故/安全主題，事件級重複排除。"
    return "相同城市/地點、相近日期與相同系統主題，事件級重複排除。"


def _is_same_report_event(candidate: dict, selected_item: dict) -> bool:
    if candidate.get("classification") != selected_item.get("classification"):
        return False
    if candidate.get("region") and selected_item.get("region") and candidate.get("region") != selected_item.get("region"):
        return False
    if _candidate_system_theme(candidate) != _candidate_system_theme(selected_item):
        return False
    candidate_location = _candidate_event_location(candidate)
    selected_location = _candidate_event_location(selected_item)
    similarity = difflib.SequenceMatcher(
        None,
        _event_similarity_text(candidate),
        _event_similarity_text(selected_item),
    ).ratio()
    date_close = _event_date_close(candidate, selected_item, days=7 if candidate.get("classification") == "重大事故" else 3)
    candidate_specific_location = _candidate_specific_event_location(candidate)
    selected_specific_location = _candidate_specific_event_location(selected_item)
    same_specific_location = bool(candidate_specific_location and selected_specific_location and candidate_specific_location == selected_specific_location)
    if candidate_specific_location and selected_specific_location and candidate_specific_location != selected_specific_location:
        return False
    if int(lookback_int) in ADVANCED_LOOKBACK_OPTIONS and same_specific_location:
        if candidate.get("classification") == "重大事故" and (date_close or similarity >= 0.70):
            return True
        if _is_project_series_candidate(candidate) and _is_project_series_candidate(selected_item) and _same_project_stage_or_unspecified(candidate, selected_item):
            return True
        if similarity >= 0.76:
            return True
    if not date_close:
        return False
    if same_specific_location:
        return True
    return similarity >= 0.62


def _is_duplicate_selected_event(candidate: dict, selected: list[dict]) -> bool:
    return any(_is_same_report_event(candidate, item) for item in selected)


def _python_selection_sort_key(candidate: dict) -> tuple:
    return (
        -int(candidate.get("python_score", 0) or 0),
        _source_tier_rank(candidate.get("source_tier", "C_media")),
        -_date_sort_key(candidate),
        -int(_has_source_reference(candidate)),
        -_selection_good_flag_count(candidate),
        _selection_bad_flag_count(candidate),
        int(candidate.get("id", 0) or 0),
    )


def _python_selection_dynamic_key(candidate: dict, selected: list[dict]) -> tuple:
    base_key = _python_selection_sort_key(candidate)
    if int(lookback_int) not in ADVANCED_LOOKBACK_OPTIONS:
        return base_key
    selected_locations = [_candidate_specific_event_location(item) or _candidate_event_location(item) for item in selected]
    selected_regions = [item.get("region", "") for item in selected]
    selected_months = [_candidate_month_key(item) for item in selected]
    selected_themes = [_candidate_system_theme(item) for item in selected]
    selected_incidents = [_candidate_incident_type(item) for item in selected]
    candidate_location = _candidate_specific_event_location(candidate) or _candidate_event_location(candidate)
    diversity_penalty = (
        selected_locations.count(candidate_location),
        selected_regions.count(candidate.get("region", "")),
        selected_incidents.count(_candidate_incident_type(candidate)),
        selected_months.count(_candidate_month_key(candidate)),
        selected_themes.count(_candidate_system_theme(candidate)),
    )
    return base_key[:2] + diversity_penalty + base_key[2:]


def _long_term_diversity_skip_reason(candidate: dict, selected: list[dict]) -> str:
    if int(lookback_int) not in ADVANCED_LOOKBACK_OPTIONS or len(selected) < 6:
        return ""
    classification = _selection_classification(candidate)
    location = _candidate_specific_event_location(candidate) or _candidate_event_location(candidate)
    region = candidate.get("region", "")
    theme = _candidate_system_theme(candidate)
    incident_type = _candidate_incident_type(candidate)
    same_location_count = sum(
        1 for item in selected
        if (_candidate_specific_event_location(item) or _candidate_event_location(item)) == location
        and _selection_classification(item) == classification
    )
    same_region_incident_count = sum(
        1 for item in selected
        if item.get("region", "") == region
        and _candidate_incident_type(item) == incident_type
        and _selection_classification(item) == classification
    )
    same_theme_count = sum(
        1 for item in selected
        if _candidate_system_theme(item) == theme
        and _selection_classification(item) == classification
    )
    if classification == "重大事故":
        if location and same_location_count >= 2:
            return "長期代表性限制：同一城市/地點重大事故已達 2 則，避免年度回顧過度集中。"
        if region and incident_type and same_region_incident_count >= 2:
            return "長期代表性限制：同一國家/地區相同事故型態已達 2 則，避免單一事故類型過度占用篇幅。"
        if theme and same_theme_count >= 4:
            return "長期代表性限制：相同系統主題重大事故已達 4 則，候選不足時可少列。"
    if _is_project_series_candidate(candidate) and location and theme:
        same_project_theme_count = sum(
            1 for item in selected
            if (_candidate_specific_event_location(item) or _candidate_event_location(item)) == location
            and _candidate_system_theme(item) == theme
            and _is_project_series_candidate(item)
        )
        if same_project_theme_count >= 2:
            return "長期代表性限制：同一城市/系統專案系列已達 2 則，避免宣傳稿或相近里程碑重複占用篇幅。"
    return ""


def _python_candidate_allowed_for_scope(candidate: dict) -> bool:
    if is_global_scope:
        return True
    region = _canonical_candidate_region(candidate)
    if region in active_regions:
        return True
    text = f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('source', '')} {candidate.get('query', '')} {candidate.get('url', '')} {candidate.get('source_href', '')}"
    looks_like_standard = candidate.get("classification") == "規範更新" or _is_standard_update_candidate(f"{text} {candidate.get('date', '')}", require_url=True)
    if region in {"國際", "國際研究", "未判定"} and _is_allowed_international_candidate(candidate, text, looks_like_standard):
        candidate["region"] = "國際"
        return True
    return False


def _is_low_value_python_selection_candidate(candidate: dict) -> bool:
    flags = set(candidate.get("candidate_flags", []) or [])
    score = int(candidate.get("python_score", 0) or 0)
    has_good_signal = _has_good_report_signal(candidate)
    has_technical_detail = _has_explicit_technical_system_detail(candidate)
    text = _candidate_selection_text(candidate)
    if _is_financial_market_candidate(candidate):
        return True
    if _selection_classification(candidate) == "技術新知" and not _has_core_metro_technical_content(dict(candidate, classification="技術新知")):
        return True
    if _is_security_or_crime_candidate(candidate) and not _has_major_security_rail_impact(candidate):
        return True
    if _contains_any_term(text, EQUIPMENT_FAILURE_TERMS) and _selection_classification(candidate) == "技術新知":
        return True
    if _is_low_value_long_term_candidate(candidate):
        return True
    if "general_rail_exclusion" in flags or _has_general_rail_exclusion(candidate):
        return True
    if _contains_any_term(text, NON_TECH_NEWS_EXCLUDE_TERMS) and not _has_substantive_detail_for_low_value_notice(candidate):
        return True
    if _has_procurement_list_notice(candidate):
        return True
    if _has_low_value_official_notice(candidate) and not _has_substantive_detail_for_low_value_notice(candidate):
        return True
    if "low_value_service_notice" in flags and not has_good_signal:
        return True
    if "low_value_proxy_or_page" in flags and not has_technical_detail:
        return True
    if candidate.get("source_tier") == "D_proxy_low_value" and not has_technical_detail:
        return True
    if "insufficient_information" in flags and not has_good_signal:
        return True
    return score < 45


def _is_strict_technical_candidate(candidate: dict) -> bool:
    return _is_technical_news_selection_candidate(candidate)


def _take_next_python_candidate(pool: list[dict], selected: list[dict]) -> dict | None:
    while pool:
        candidate = min(pool, key=lambda item: _python_selection_dynamic_key(item, selected))
        pool.remove(candidate)
        duplicate_of = next((item for item in selected if _is_same_report_event(candidate, item)), None)
        if duplicate_of:
            try:
                LAST_PYTHON_SELECTION_DEBUG.setdefault("duplicate_event_records", []).append({
                    "candidate_id": candidate.get("id", ""),
                    "candidate_title": candidate.get("title", ""),
                    "duplicate_of_id": duplicate_of.get("id", ""),
                    "duplicate_of_title": duplicate_of.get("title", ""),
                    "duplicate_event_reason": _duplicate_event_reason(candidate, duplicate_of),
                    "candidate_location": _candidate_specific_event_location(candidate) or _candidate_event_location(candidate),
                    "duplicate_of_location": _candidate_specific_event_location(duplicate_of) or _candidate_event_location(duplicate_of),
                    "candidate_date": candidate.get("date", ""),
                    "duplicate_of_date": duplicate_of.get("date", ""),
                    "candidate_theme": _candidate_system_theme(candidate),
                    "duplicate_of_theme": _candidate_system_theme(duplicate_of),
                })
            except Exception:
                pass
            continue
        diversity_reason = _long_term_diversity_skip_reason(candidate, selected)
        if diversity_reason:
            try:
                LAST_PYTHON_SELECTION_DEBUG.setdefault("duplicate_event_records", []).append({
                    "candidate_id": candidate.get("id", ""),
                    "candidate_title": candidate.get("title", ""),
                    "duplicate_of_id": "",
                    "duplicate_of_title": "",
                    "duplicate_event_reason": diversity_reason,
                    "candidate_location": _candidate_specific_event_location(candidate) or _candidate_event_location(candidate),
                    "duplicate_of_location": "",
                    "candidate_date": candidate.get("date", ""),
                    "duplicate_of_date": "",
                    "candidate_theme": _candidate_system_theme(candidate),
                    "duplicate_of_theme": "",
                    "candidate_incident_type": _candidate_incident_type(candidate),
                })
            except Exception:
                pass
            continue
        return candidate
    return None




LAST_PYTHON_SELECTION_DEBUG: dict = dict(REPORT_SELECTION_DEBUG_DEFAULT)


def _is_hard_excluded_for_borderline(candidate: dict) -> bool:
    text = _candidate_selection_text(candidate)
    if _is_financial_market_candidate(candidate):
        return True
    if _selection_classification(candidate) == "技術新知" and not _has_core_metro_technical_content(dict(candidate, classification="技術新知")):
        return True
    if _is_security_or_crime_candidate(candidate) and not _has_major_security_rail_impact(candidate):
        return True
    if _is_low_value_long_term_candidate(candidate):
        return True
    if _has_general_rail_exclusion(candidate):
        return True
    if _has_procurement_list_notice(candidate):
        return True
    if _contains_any_term(text, AIRPORT_PEOPLE_MOVER_EXCLUDE_TERMS):
        return True
    if _contains_any_term(text, GENERAL_RAIL_EXCLUDE_TERMS):
        return True
    if _contains_any_term(text, LOW_REPORT_VALUE_TERMS):
        return True
    if _contains_any_term(text, NON_URBAN_HARD_EXCLUDE_TERMS) and not _contains_any_term(text, URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS):
        return True
    if _contains_any_term(text, [
        "lost property", "delay certificate", "route page", "trip result",
        "contract documents holders list", "mtr e-store", "product page",
        "失物招領", "延誤證明", "標案文件持有人", "商品", "旅遊攻略",
    ]):
        return True
    return False


def _is_b_level_technical_candidate(candidate: dict) -> bool:
    text = _candidate_selection_text(candidate)
    if candidate.get("classification") != "技術新知":
        return False
    if _is_hard_excluded_for_borderline(candidate):
        return False
    if _contains_any_term(text, NON_TECH_NEWS_EXCLUDE_TERMS):
        return False
    if _is_accident_signal_text(text):
        return False
    if not _candidate_date_obj(candidate.get("date", "")):
        return False
    if not _has_source_reference(candidate):
        return False
    if not _is_urban_rail_candidate(text, candidate.get("source", "")):
        return False
    return _contains_any_term(text, MEDIUM_TECHNICAL_DETAIL_TERMS + WEEKLY_BACKFILL_ALLOWED_TERMS)


def _is_borderline_report_candidate(candidate: dict) -> tuple[bool, str]:
    classification = candidate.get("classification") or _selection_classification(candidate)
    candidate["classification"] = classification
    if classification not in selected_types:
        return False, "類型未勾選"
    if not _python_candidate_allowed_for_scope(candidate):
        return False, "國家/地區不在指定範圍"
    if _is_hard_excluded_for_borderline(candidate):
        return False, "硬排除項"
    flags = set(candidate.get("candidate_flags", []) or [])
    text = _candidate_selection_text(candidate)
    if not _candidate_date_obj(candidate.get("date", "")):
        return False, "日期不明"
    if not _has_source_reference(candidate):
        return False, "來源/URL 不明"
    if classification == "技術新知":
        if _is_strict_technical_candidate(candidate):
            return True, "A級技術新知"
        if _is_b_level_technical_candidate(candidate):
            return True, "B級技術新知候補"
        return False, "技術門檻不足"
    if classification == "重大事故":
        if _is_accident_signal_text(text) and not _contains_any_term(text, LOW_IMPACT_ACCIDENT_TERMS):
            return True, "事故/安全訊號明確"
        if _contains_any_term(text, LOW_IMPACT_ACCIDENT_TERMS) and _contains_any_term(text, HIGH_IMPACT_ACCIDENT_TERMS):
            return True, "低影響事故但涉及系統安全議題"
        return False, "事故價值不足"
    if classification == "營運政策":
        if "high_value_policy" in flags or _contains_any_term(text, SUBSTANTIVE_POLICY_DETAIL_TERMS + HIGH_VALUE_POLICY_TERMS + WEEKLY_BACKFILL_ALLOWED_TERMS):
            return True, "具營運管理或系統規劃價值"
        return False, "營運政策價值不足"
    if classification == "營運爭議":
        if _contains_any_term(text, GENERAL_RAIL_EXCLUDE_TERMS):
            return False, "一般鐵路/通勤鐵路爭議"
        if _contains_any_term(text, URBAN_RAIL_MODE_TERMS):
            return True, "都市軌道營運爭議"
        return False, "都市軌道爭議關聯不足"
    if classification == "規範更新":
        if _is_standard_update_candidate(f"{text} {candidate.get('date', '')}", require_url=True):
            return True, "規範更新條件完整"
        return False, "規範更新條件不足"
    return False, "未符合候補條件"


def _selection_lower_bound(days: int) -> int:
    lower, _ = _selection_target_range(days)
    return lower


def _selection_debug_reset() -> dict:
    debug = dict(REPORT_SELECTION_DEBUG_DEFAULT)
    debug["duplicate_event_records"] = []
    debug["borderline_candidates"] = []
    debug["backfill_reason"] = ""
    return debug


def _select_from_grouped_pools(grouped: dict[str, list[dict]], max_items: int) -> list[dict]:
    selected: list[dict] = []
    if len(selected_types) <= 1:
        only_type = selected_types[0] if selected_types else ""
        while len(selected) < max_items:
            candidate = _take_next_python_candidate(grouped.get(only_type, []), selected)
            if not candidate:
                break
            selected.append(candidate)
        return selected

    for category in selected_types:
        if len(selected) >= max_items:
            break
        candidate = _take_next_python_candidate(grouped.get(category, []), selected)
        if candidate:
            selected.append(candidate)

    while len(selected) < max_items:
        added = False
        for category in selected_types:
            if len(selected) >= max_items:
                break
            candidate = _take_next_python_candidate(grouped.get(category, []), selected)
            if candidate:
                selected.append(candidate)
                added = True
        if not added:
            break
    return selected


def _backfill_borderline_candidates(
    selected: list[dict],
    model_candidates: list[dict],
    min_items: int,
    max_items: int,
    debug: dict,
) -> list[dict]:
    selected_ids = {int(item.get("id", 0) or 0) for item in selected}
    shortfall_before = max(0, min_items - len(selected))
    debug["shortfall_before_backfill"] = shortfall_before
    if shortfall_before <= 0:
        debug["shortfall_after_backfill"] = 0
        debug["backfill_reason"] = "嚴格入選已達目標下限，無需候補。"
        return selected

    borderline_pool: list[dict] = []
    for raw_candidate in model_candidates or []:
        candidate_id = int(raw_candidate.get("id", 0) or 0)
        if candidate_id in selected_ids:
            continue
        candidate = dict(raw_candidate)
        classification = _selection_classification(candidate)
        candidate["classification"] = classification
        allowed, reason = _is_borderline_report_candidate(candidate)
        if not allowed:
            continue
        candidate["selected_reason"] = (
            f"Python 合格候補：{reason}；score={candidate.get('python_score', 0)}；"
            f"tier={candidate.get('source_tier', '')}；flags={','.join(candidate.get('candidate_flags', []) or [])}"
        )
        candidate["include_in_report"] = True
        candidate["borderline_reason"] = reason
        borderline_pool.append(candidate)

    borderline_pool = sorted(borderline_pool, key=_python_selection_sort_key)
    while borderline_pool and len(selected) < min_items and len(selected) < max_items:
        candidate = _take_next_python_candidate(borderline_pool, selected)
        if not candidate:
            break
        selected.append(candidate)
        selected_ids.add(int(candidate.get("id", 0) or 0))
        if len(debug["borderline_candidates"]) < 20:
            debug["borderline_candidates"].append(build_candidate_card(candidate) | {"borderline_reason": candidate.get("borderline_reason", "")})

    debug["borderline_added_count"] = len(debug["borderline_candidates"])
    debug["shortfall_after_backfill"] = max(0, min_items - len(selected))
    if debug["borderline_added_count"]:
        debug["backfill_reason"] = f"嚴格入選不足 {shortfall_before} 則，已補入合格候補 {debug['borderline_added_count']} 則。"
    elif debug["shortfall_after_backfill"]:
        debug["backfill_reason"] = "嚴格入選不足，且未找到符合日期、來源、都市軌道與報告價值門檻之合格候補。"
    else:
        debug["backfill_reason"] = "候補後已達目標下限。"
    return selected

def select_candidates_by_python(model_candidates: list[dict]) -> list[dict]:
    global LAST_PYTHON_SELECTION_DEBUG
    LAST_PYTHON_SELECTION_DEBUG = _selection_debug_reset()
    min_items, max_items = _selection_target_range(lookback_int)
    grouped: dict[str, list[dict]] = {category: [] for category in selected_types}
    for raw_candidate in model_candidates or []:
        candidate = dict(raw_candidate)
        classification = _selection_classification(candidate)
        candidate["classification"] = classification
        if classification not in selected_types:
            continue
        if classification == "技術新知" and not _is_strict_technical_candidate(candidate):
            continue
        if not _python_candidate_allowed_for_scope(candidate):
            continue
        if _is_low_value_python_selection_candidate(candidate):
            continue
        candidate["selected_reason"] = (
            f"Python 嚴格規則選題：score={candidate.get('python_score', 0)}；"
            f"tier={candidate.get('source_tier', '')}；flags={','.join(candidate.get('candidate_flags', []) or [])}"
        )
        candidate["include_in_report"] = True
        grouped.setdefault(classification, []).append(candidate)

    for category in grouped:
        grouped[category] = sorted(grouped[category], key=_python_selection_sort_key)

    selected = _select_from_grouped_pools(grouped, max_items)
    LAST_PYTHON_SELECTION_DEBUG["strict_selected_count"] = len(selected)
    selected = _backfill_borderline_candidates(selected, model_candidates or [], min_items, max_items, LAST_PYTHON_SELECTION_DEBUG)
    LAST_PYTHON_SELECTION_DEBUG["final_selected_count"] = len(selected)
    return rebalance_selected_candidates(selected)


def build_selection_prompt(candidates: list[dict]) -> str:
    candidate_block = "\n\n".join(format_selection_candidate(candidate) for candidate in candidates)
    if not candidate_block:
        candidate_block = "本期 Python 初篩後沒有候選新聞。請回傳空的 selected_ids 清單。"
    selected_types_str = "、".join(selected_types) if selected_types else "無"
    example_type = selected_types[0] if selected_types else "技術新知"
    output_range = get_selection_output_range(lookback_int)
    return f"""
請依照你在 MaiAgent 後台設定的國際捷運技術週報角色指令，根據以下候選資料執行第一階段選題。不得自行搜尋或補充候選資料以外的新聞、日期、供應商、技術細節或統計數據。

本次是第一階段選題任務；請只判斷候選資料是否適合納入正式報告，不要撰寫正式新聞段落。
報告期間：{date_range}
使用者勾選的新聞類型：{selected_types_str}
需要選出的數量：{output_range} 則；高品質候選不足時可少於目標，但不要用低價值資料湊數。

請只使用候選資料中的 id 進行選題；category 必須從使用者勾選的新聞類型中選擇。不得輸出 Markdown 說明。

輸出 JSON 格式：
{{
  "selected_ids": [
    {{
      "id": 1,
      "category": "{example_type}",
      "reason": "入選理由",
      "priority": 1,
      "merge_group": "",
      "include_in_report": true
    }}
  ],
  "exclude_ids": [
    {{
      "id": 2,
      "exclude_reason": "排除理由"
    }}
  ]
}}

## 精簡候選資料
{candidate_block}
""".strip()


def _json_loads_loose(text: str):
    candidates = []
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text or "", flags=re.DOTALL | re.IGNORECASE)
    candidates.extend(fenced)
    candidates.append(text or "")
    for raw in candidates:
        raw = raw.strip()
        if not raw:
            continue
        for start_char, end_char in (("{", "}"), ("[", "]")):
            start = raw.find(start_char)
            end = raw.rfind(end_char)
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start:end + 1])
                except Exception:
                    continue
    return None


def _truthy_report_flag(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    text = str(value).strip().casefold()
    return text not in {"false", "no", "否", "不納入", "不建議", "0"}


def parse_selection_response(response_text: str, candidates: list[dict]) -> list[dict]:
    candidate_map = {int(candidate["id"]): candidate for candidate in candidates}
    selected: list[dict] = []
    seen_ids: set[int] = set()

    parsed = _json_loads_loose(response_text)
    items = []
    if isinstance(parsed, dict):
        if isinstance(parsed.get("selected_ids"), list):
            for raw_item in parsed["selected_ids"]:
                if isinstance(raw_item, dict):
                    items.append(raw_item)
                else:
                    items.append({"id": raw_item})
        for key in ("selected", "items", "入選", "selections"):
            if isinstance(parsed.get(key), list):
                items.extend(parsed[key])
                break
    elif isinstance(parsed, list):
        items = parsed

    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id") or item.get("編號") or item.get("number") or item.get("candidate_id")
        try:
            candidate_id = int(raw_id)
        except Exception:
            continue
        if candidate_id not in candidate_map or candidate_id in seen_ids:
            continue
        if not _truthy_report_flag(item.get("include_in_report", item.get("是否建議納入正式週報"))):
            continue
        classification = (
            item.get("classification")
            or item.get("category")
            or item.get("分類")
            or item.get("topic_type")
            or item.get("類型")
            or item.get("preliminary_type")
            or "技術新知"
        )
        if classification not in ADVANCED_TYPES:
            classification = next((category for category in ADVANCED_TYPES if category in str(item)), "技術新知")
        if classification not in selected_types:
            continue
        candidate = dict(candidate_map[candidate_id])
        candidate["classification"] = classification
        candidate["selected_reason"] = item.get("selected_reason") or item.get("入選理由") or item.get("reason") or "MaiAgent 第一階段選題入選。"
        candidate["selection_priority"] = item.get("priority", "")
        candidate["merge_group"] = item.get("merge_group", "")
        candidate["include_in_report"] = True
        selected.append(candidate)
        seen_ids.add(candidate_id)
        if len(selected) >= SELECTION_MAX_ITEMS:
            return selected

    if selected:
        return selected

    fallback_ids: list[int] = []
    for match in re.finditer(r"(?:編號|候選|ID|id|#)\s*[:：]?\s*(\d{1,3})", response_text or ""):
        candidate_id = int(match.group(1))
        if candidate_id in candidate_map and candidate_id not in fallback_ids:
            fallback_ids.append(candidate_id)
    if not fallback_ids:
        for line in (response_text or "").splitlines():
            match = re.match(r"^\s*(\d{1,3})[\.、\)]", line)
            if match:
                candidate_id = int(match.group(1))
                if candidate_id in candidate_map and candidate_id not in fallback_ids:
                    fallback_ids.append(candidate_id)

    for candidate_id in fallback_ids[:SELECTION_MAX_ITEMS]:
        candidate = dict(candidate_map[candidate_id])
        candidate["classification"] = next((category for category in selected_types if category in response_text), selected_types[0] if selected_types else "技術新知")
        candidate["selected_reason"] = "MaiAgent 第一階段回應未完全符合 JSON，已依回應中的候選編號納入。"
        candidate["include_in_report"] = True
        selected.append(candidate)

    if selected:
        return selected

    fallback_count = min(SELECTION_MIN_ITEMS, len(candidates), SELECTION_MAX_ITEMS)
    for candidate in candidates[:fallback_count]:
        backup = dict(candidate)
        if "規範更新" in selected_types and _is_standard_update_candidate(f"{backup.get('title')} {backup.get('snippet')} {backup.get('url')}", True):
            backup["classification"] = "規範更新"
        else:
            backup["classification"] = selected_types[0] if selected_types else "技術新知"
        backup["selected_reason"] = "MaiAgent 第一階段回應格式無法解析；依 Python 初篩排序備援納入。"
        backup["include_in_report"] = True
        selected.append(backup)
    return selected



def build_python_unselected_stats(model_candidates: list[dict], selected_candidates: list[dict]) -> dict:
    selected_ids = {int(item.get("id", 0) or 0) for item in selected_candidates}
    stats: dict[str, int] = {}
    examples: list[dict] = []
    for candidate in model_candidates or []:
        candidate_id = int(candidate.get("id", 0) or 0)
        if candidate_id in selected_ids:
            continue
        classification = _selection_classification(candidate)
        flags = set(candidate.get("candidate_flags", []) or [])
        if classification not in selected_types:
            reason = "類型未勾選"
        elif classification == "技術新知" and not _is_strict_technical_candidate(dict(candidate, classification=classification)):
            reason = "技術新知缺少明確機電/系統細節或屬低價值公告"
        elif not _python_candidate_allowed_for_scope(dict(candidate, classification=classification)):
            reason = "國家/地區不在指定範圍"
        elif _is_low_value_python_selection_candidate(candidate):
            reason = "Python 規則排除低價值或資訊不足候選"
        elif flags.intersection({"low_value_service_notice", "insufficient_information", "short_snippet", "low_value_official_notice", "procurement_list_notice", "general_rail_exclusion"}):
            reason = "低價值或摘要不足旗標降權後未入選"
        else:
            reason = "Python 規則排序、候補機制與類別平衡後未入選"
        stats[reason] = stats.get(reason, 0) + 1
        if len(examples) < 20:
            examples.append({
                "id": candidate_id,
                "title": candidate.get("title", ""),
                "classification": classification,
                "python_score": candidate.get("python_score", 0),
                "source_tier": candidate.get("source_tier", ""),
                "candidate_flags": candidate.get("candidate_flags", []),
                "reason": reason,
            })
    return {"summary": stats, "examples": examples}

def build_ai_unselected_stats(model_candidates: list[dict], selected_candidates: list[dict]) -> dict:
    selected_ids = {int(item.get("id", 0) or 0) for item in selected_candidates}
    stats: dict[str, int] = {}
    examples: list[dict] = []
    for candidate in model_candidates or []:
        candidate_id = int(candidate.get("id", 0) or 0)
        if candidate_id in selected_ids:
            continue
        text = f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('query', '')}"
        quality = candidate.get("source_quality", "B")
        if quality == "C":
            reason = "C級來源降權或未被第一階段選題納入"
        elif _contains_any_term(text, TECH_NEWS_SOFT_EXCLUDE_TERMS):
            reason = "可能偏事故、政策、爭議或缺少技術細節"
        elif not _contains_any_term(text, TECH_NEWS_REQUIRED_TERMS) and candidate.get("classification") == "技術新知":
            reason = "技術關鍵字不足"
        else:
            reason = "MaiAgent 第一階段未回傳該候選編號"
        stats[reason] = stats.get(reason, 0) + 1
        if len(examples) < 20:
            examples.append({
                "id": candidate_id,
                "title": candidate.get("title", ""),
                "quality": quality,
                "source": candidate.get("source", ""),
                "reason": reason,
            })
    return {"summary": stats, "examples": examples}


def format_report_candidate(candidate: dict) -> str:
    source_url = _effective_source_url(candidate)
    source_display = candidate.get("source_display") or source_label_for_report(
        candidate.get("source", ""), candidate.get("url", ""), candidate.get("source_href", ""), candidate.get("source_tier", "")
    )
    prompt_item = {
        "id": candidate.get("id", ""),
        "title": candidate.get("title", ""),
        "date": candidate.get("date", ""),
        "source_display": source_display,
        "source_verb": candidate.get("source_verb", source_verb_for_report(candidate.get("source_tier", ""), source_display)),
        "region": candidate.get("region", "未判定"),
        "preliminary_type": candidate.get("classification") or candidate.get("preliminary_type", infer_preliminary_type(candidate)),
        "url": source_url,
        "snippet": _shorten(candidate.get("snippet", ""), REPORT_SNIPPET_CHARS),
        "source_domain": candidate.get("source_domain") or _domain_from_url(source_url) or _extract_domain_hint(source_url),
    }
    return json.dumps(prompt_item, ensure_ascii=False)


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


def _journal_priority(date_text: str) -> tuple[int, str]:
    cutoff_date = today - datetime.timedelta(days=research_supplement_lookback_days)
    date_obj = _candidate_date_obj(date_text)
    has_full_date = _has_explicit_full_date(date_text)
    if has_full_date and date_obj and cutoff_date <= date_obj <= today + datetime.timedelta(days=1):
        return 0, f"明確日期且符合{research_supplement_period_label}研究補充期間"
    if has_full_date and date_obj:
        return 99, f"明確日期不在{research_supplement_period_label}研究補充期間"
    if date_obj and date_obj.year >= cutoff_date.year:
        return 1, "僅年份或日期不完整，降低優先度"
    return 2, "無明確發表日期，降低優先度"


def _parse_full_research_date(date_text: str) -> datetime.date | None:
    text = (date_text or "").strip()
    if not text or not _has_explicit_full_date(text):
        return None
    date_obj = _candidate_date_obj(text)
    return date_obj


def _research_date_info(result: dict, title: str, snippet: str) -> dict:
    date_fields = [
        "published_date", "publication_date", "online_publication_date",
        "article_date", "release_date", "published", "date",
    ]
    for key in date_fields:
        value = result.get(key) or result.get(key.replace("_", ""))
        date_obj = _parse_full_research_date(str(value or ""))
        if date_obj:
            cutoff_date = today - datetime.timedelta(days=research_supplement_lookback_days)
            return {
                "published_date": date_obj.isoformat(),
                "date_confidence": "high",
                "date_reason": f"{key} 提供完整日期",
                "is_within_research_period": cutoff_date <= date_obj <= today,
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
            cutoff_date = today - datetime.timedelta(days=research_supplement_lookback_days)
            return {
                "published_date": date_obj.isoformat(),
                "date_confidence": "high",
                "date_reason": "摘要提供明確發表/出版/發布日期",
                "is_within_research_period": cutoff_date <= date_obj <= today,
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


def _journal_safe_get(url: str, timeout: int = 8) -> str:
    if not url or not str(url).startswith(("http://", "https://")):
        return ""
    try:
        session = create_requests_session()
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


def fetch_journal_page_metadata(url: str) -> dict:
    html = _journal_safe_get(url)
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
        cutoff_date = today - datetime.timedelta(days=research_supplement_lookback_days)
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
        "is_within_research_period": bool(published_date) and (today - datetime.timedelta(days=research_supplement_lookback_days) <= _candidate_date_obj(published_date) <= today),
        "doi": doi,
        "journal_name": journal_name,
    }


def _journal_source_page_results(status_text=None) -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    statuses: list[dict] = []
    fetched = 0
    seen_links: set[str] = set()
    for source_name, page_url in JOURNAL_SOURCE_PAGES:
        if status_text:
            status_text.text(f"📚 解析學術來源頁：{source_name}...")
        html = _journal_safe_get(page_url)
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
            meta = fetch_journal_page_metadata(link)
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


def collect_journal_candidates(status_text=None) -> tuple[list[dict], list[dict], list[dict]]:
    if not include_research_supplement:
        return [], [], []
    if DDGS is None:
        return [], [{"query": "國際學術期刊補充", "status": "ddgs 套件未安裝", "count": 0}], []

    target_min, target_max = get_journal_target_count(research_supplement_lookback_days)
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

        date_info = _research_date_info(result, title, snippet)
        if (date_info["date_confidence"] != "high" or not date_info["is_within_research_period"]) and metadata_fetch_count < JOURNAL_ARTICLE_FETCH_LIMIT:
            fetched = fetch_journal_page_metadata(url)
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
        if not _is_urban_rail_candidate(text) and not _contains_any_term(text, ["metro system", "urban rail transit", "rail transit", "urban metro"]):
            _exclude(query, title, url, "都市軌道關聯不足", snippet, metadata)
            return False
        if date_info["date_confidence"] != "high" or not date_info["is_within_research_period"]:
            if date_info["date_confidence"] == "high" and not date_info["is_within_research_period"]:
                exclude_reason = f"明確發表日期不在{research_supplement_period_label}研究補充期間"
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
        candidate = _make_news_candidate(
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

    source_results, source_statuses = _journal_source_page_results(status_text)
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
        if status_text:
            status_text.text(f"📚 國際學術與技術研究補充搜尋 {idx}/{len(queries)}...")
        query_text = f'{query} journal OR research OR paper OR IEEE OR "Transportation Research"'
        try:
            with DDGS() as ddgs:
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
    selected = sorted(high_score, key=lambda item: (-int(item.get("journal_score", 0) or 0), item.get("published_date", "")))
    if len(selected) < target_min:
        selected.extend(sorted(borderline, key=lambda item: (-int(item.get("journal_score", 0) or 0), item.get("published_date", "")))[: target_min - len(selected)])
    selected = sorted(selected, key=lambda item: (-int(item.get("journal_score", 0) or 0), item.get("published_date", "")))[:target_max]
    for item in selected:
        item["journal_target_count"] = target_min
        item["journal_selected_count"] = len(selected)
        item["journal_shortfall_reason"] = _journal_shortfall_reason(len(selected), target_min, excluded)
    return selected, statuses, excluded


def build_report_prompt(selected_candidates: list[dict], journal_candidates: list[dict], search_count: int) -> str:
    weekday = ['一','二','三','四','五','六','日'][today.weekday()]
    selected_types_str = "、".join(selected_types) if selected_types else "無"
    selected_sections = _selected_report_sections()
    selected_empty_rules = _selected_empty_section_rules()
    selected_stats = _selected_stats_template()
    research_heading = research_section_heading(markdown=False)
    candidate_block = "\n\n".join(format_report_candidate(candidate) for candidate in selected_candidates)
    if not candidate_block:
        candidate_block = "第一階段沒有入選新聞。請只依已勾選章節輸出沒有符合資料的文字，不得自行補新聞。"

    journal_input_section = ""
    if include_research_supplement:
        if journal_candidates:
            journal_block = "\n".join(
                json.dumps({
                    "title": item.get("title", ""),
                    "date": item.get("published_date", "") or item.get("date", ""),
                    "journal_name": item.get("journal_name", item.get("source", "")),
                    "doi": item.get("doi", ""),
                    "journal_score": item.get("journal_score", ""),
                    "journal_score_reason": item.get("journal_score_reason", ""),
                    "url": item.get("url", ""),
                    "snippet": _shorten(item.get("snippet", ""), REPORT_SNIPPET_CHARS),
                }, ensure_ascii=False)
                for item in journal_candidates
            )
        else:
            journal_block = "無符合期間條件且具明確發表日期之研究候選。"
        journal_input_section = f"""
## 國際學術與技術研究補充候選
研究補充已啟用；本次研究補充期間為{research_supplement_period_label}（{research_supplement_start_date.isoformat()} 至 {today.isoformat()}）。如有下方候選，請於最後輸出「{research_heading}」。每篇期刊標題請用「1、標題」「2、標題」連續編號，不得加上「[技術研究補充]」。每篇使用固定欄位：發表日期、期刊/來源、研究主題、研究摘要、臺北捷運局啟示、資料來源。若有候選，章節最後必須新增「學術期刊綜合結論」，至少 300 字、建議 300～500 字，僅根據候選研究綜整趨勢與對臺北捷運局之啟示。若沒有候選，請寫：「本期未發現符合期間條件且具明確發表日期之國際學術或技術研究資料。」
{journal_block}
""".strip()
    journal_input_text = f"\n\n{journal_input_section}" if journal_input_section else ""

    return f"""
請依照你在 MaiAgent 後台設定的國際捷運技術週報角色指令，根據以下已入選新聞撰寫正式報告。不得自行搜尋，不得補充候選資料以外的新聞、日期、國家、城市、路線、供應商、技術細節、事故原因、統計數據或金額。

本次是第二階段正式報告撰寫任務。
報告標題：{report_title}
資料涵蓋期間：{date_range}
報導範圍：{report_scope_label}
勾選類型：{selected_types_str}
正式報告章節：
{selected_sections}
空章節文字：
{selected_empty_rules}

正式報告開頭固定：
# {report_title}
> 資料涵蓋期間：{date_range}
> 報導範圍：{report_scope_label}

正式報告每則新聞請使用以下固定格式，不得改成表格、簡報式卡片或多層條列，不得自行增減欄位，不得新增「技術關鍵字」欄位，不得把「臺北捷運局啟示」拆成子欄位：
🔹 [新聞類型] 繁體中文新聞標題

• 發布/事件日期：

• 國家/地區：

• 相關機電系統：

• 事件摘要：

• 臺北捷運局啟示：

• 資料來源：

每則新聞之間使用：
---

必要寫作提醒：
- 只根據下方已入選新聞資料撰寫；正式報告只輸出已勾選章節，不得輸出未勾選類型。
- 以下新聞已由 Python 規則完成選題，共 {len(selected_candidates)} 則；請勿再自行刪減、改選或新增新聞，正式報告新聞數必須與已入選新聞資料一致。
- 每則新聞標題必須翻成繁體中文正式標題；機構、車型或系統縮寫可保留。
- 「事件摘要：」與「臺北捷運局啟示：」後方必須換行，不要把正文接在同一行；摘要與啟示不要條列。
- 事件摘要請根據 title、snippet、source_display、date、region、preliminary_type 與 url 自行判斷撰寫。摘要重點為事件本身、都市軌道場景、涉及的機電系統或營運管理意義。若原始資料未提供細節，請採保守摘要，不得自行補述；除非該缺漏會影響工程判讀，否則不必特別寫「未提供」。不要每則都套用「資料來源未載明」或「原始資料未提供」。不得自行補原文沒有的數字、供應商、金額、GoA 等級、測試項目、車輛規格、事故原因或導入時程。
- 臺北捷運局啟示請從機電系統規劃、系統整合、維修管理、營運安全、資料治理、資安、能源效率或風險控管角度撰寫。不得寫成政策宣傳、空泛口號或與新聞無關的一般性建議。不得暗示臺北捷運局已有相同計畫、設備或問題，除非候選資料明確提供。
- 資料來源請使用 source_display、date、url 與 source_domain；若候選資料提供完整 URL，資料來源列應保留該 URL 或系統指定之來源連結；若只有 domain，顯示 domain；若沒有完整 URL，寫：「原始候選資料未提供完整 URL。」不得自行編造 URL，不得把來源首頁、分類頁或媒體名稱自行改寫成新聞頁 URL。
- 不得在正式報告正文使用 MaiAgent、Python 初篩、developer debug、python_score、入選原因、候選資料等模型處理語氣。

報告最後保留：
📊 本期統計：正式新聞共 N 則（{selected_stats}）
⏰ 報告產出時間：{today.strftime('%Y年%m月%d日')} 週{weekday}

## 已入選新聞資料
{candidate_block}
{journal_input_text}
""".strip()


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

        # 常見巢狀結果欄位 fallback
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


def call_maiagent_cloud(prompt: str) -> str:
    """呼叫 MaiAgent 雲端 Chatbot completions API 產生報告。"""
    if not maiagent_api_key:
        raise RuntimeError("未設定 MAIAGENT_API_KEY")
    if not maiagent_chatbot_id:
        raise RuntimeError("未設定 MAIAGENT_CHATBOT_ID")

    base_url = maiagent_api_base.rstrip("/")
    endpoint = f"{base_url}/api/chatbots/{maiagent_chatbot_id}/completions"
    v1_endpoint = f"{base_url}/api/v1/chatbots/{maiagent_chatbot_id}/completions"
    headers = {
        "Authorization": f"Api-Key {maiagent_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payloads = [
        {"message": {"content": prompt}, "isStreaming": False},
        {"message": {"content": prompt}, "is_streaming": False},
    ]
    endpoints = [endpoint + "/", endpoint, v1_endpoint + "/", v1_endpoint]
    last_error = None

    for url in endpoints:
        for payload in payloads:
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=240)
                if response.status_code in (400, 404, 422):
                    last_error = RuntimeError(f"MaiAgent API 回應 {response.status_code}: {response.text[:500]}")
                    continue
                response.raise_for_status()
                try:
                    data = response.json()
                except ValueError:
                    return response.text.strip()
                return _extract_maiagent_text(data)
            except Exception as exc:
                last_error = exc
                continue

    raise RuntimeError(f"MaiAgent API 呼叫失敗：{last_error}")


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
    md = compact_report_urls(md)

    def _inline(line: str) -> str:
        h = escape(line)
        h = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", h)
        h = re.sub(r"\[(.+?)\]\((https?://[^\s\)]+)\)", r'<a href="\2" target="_blank">\1</a>', h)
        return h

    rows = []
    for raw_line in md.splitlines():
        line = raw_line.strip()
        if not line or line == "---":
            rows.append('<div class="report-spacer"></div>')
            continue
        if line.startswith(("- ", "* ")):
            rows.append(f'<div class="report-line list">• {_inline(line[2:].strip())}</div>')
        elif line.startswith("> "):
            rows.append(f'<div class="report-line meta">{_inline(line[2:].strip())}</div>')
        else:
            rows.append(f'<div class="report-line">{_inline(line)}</div>')
    return "".join(rows)


def short_url_label(url: str) -> str:
    host = _domain_from_url(url) or "來源"
    if "news.google.com" in host:
        return "來源連結"
    return f"來源連結（{host}）"


def _extract_complete_url(text: str) -> str:
    match = re.search(r"https?://[^\s\)\]）＞>，,；;。]+", text or "")
    if not match:
        return ""
    return match.group(0).rstrip("。；;,，)")


def _extract_domain_hint(text: str) -> str:
    text = text or ""
    url = _extract_complete_url(text)
    if url:
        return _domain_from_url(url)
    match = re.search(r"\b(?:[a-z0-9-]+\.)+(?:com|org|net|gov|edu|info|co|jp|kr|sg|hk|uk|fr|de|au|ca|tw)\b", text, flags=re.IGNORECASE)
    return match.group(0).lower() if match else ""


def _normalize_report_date_text(text: str) -> str:
    text = text or ""
    match = re.search(
        r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?:[T\s]\d{1,2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?",
        text,
    )
    if not match:
        match = re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return "日期未知"


def _domain_to_url(domain: str) -> str:
    domain = (domain or "").strip().strip("/").lower()
    if not domain:
        return ""
    if domain.startswith(("http://", "https://")):
        return domain
    return f"https://{domain}"


def _clean_source_label(content: str, url: str, domain: str) -> str:
    label = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", content or "")
    label = re.sub(r"https?://[^\s\)\]）＞>，,；;。]+", "", label)
    if domain:
        label = re.sub(re.escape(domain), "", label, flags=re.IGNORECASE)
    label = re.sub(
        r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}(?:[T\s]\d{1,2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?",
        "",
        label,
    )
    label = re.sub(r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日", "", label)
    label = re.sub(r"(資料來源未明確辨識|日期未知)", "", label)
    label = re.sub(r"來源連結\s*[（(][^）)]*[）)]", "", label)
    label = re.sub(r"原始候選資料未提供完整\s*URL", "", label, flags=re.IGNORECASE)
    label = re.sub(r"未提供完整\s*URL", "", label, flags=re.IGNORECASE)
    label = re.sub(r"Google\s*News.*?(?:代理|proxy|來源)?", "", label, flags=re.IGNORECASE)
    label = _clean_formal_source_proxy_label(label)
    label = label.replace("，。", "，").replace("。 ", " ")
    label = re.sub(r"[（(]\s*[）)]", "", label)
    label = re.sub(r"[，,。；;：:]+\s*", " ", label)
    label = re.sub(r"\s+", " ", label)
    label = label.strip(" ：:;；,，。-（）()[]【】")
    label = _clean_formal_source_proxy_label(label)
    if label.casefold() in {"http", "https", "google news", "news", "article", "report", "source", url.casefold(), domain.casefold()}:
        label = ""
    if re.sub(r"\s+", "", label) in {"報導", "新聞", "公告", "來源", "資料來源"}:
        label = ""
    if not label and domain:
        label = domain
    return label or "資料來源未明確辨識"


def normalize_source_line(line: str) -> str:
    if "資料來源" not in (line or ""):
        return line
    match = re.match(
        r"^\s*(?:[-*]\s*)?(?:•\s*)?(?:\*\*)?資料來源(?:\*\*)?\s*[：:]\s*(.*)$",
        line or "",
    )
    if not match:
        return line
    content = match.group(1).strip()
    date_text = _normalize_report_date_text(content)
    url = _extract_complete_url(content)
    host = _domain_from_url(url)

    if url and "news.google.com" in host:
        url = ""
        host = ""

    domain = _extract_domain_hint(content.replace(url, "")) if not url else host
    if domain == "news.google.com":
        domain = ""
    source_ref = url or domain
    source_label = _clean_source_label(content, source_ref, domain or host)
    url_text = source_ref or "原始候選資料未提供完整 URL。"
    return f"• 資料來源：{source_label}，{date_text}，{url_text}"


def normalize_report_source_lines(text: str) -> str:
    return "\n".join(normalize_source_line(line) for line in (text or "").splitlines())


def compact_report_urls(text: str) -> str:
    """Keep formal source URLs complete while compacting incidental long URLs elsewhere."""
    text = normalize_report_source_lines(text)

    def _compact_line(line: str) -> str:
        if "資料來源" in line:
            return line
        placeholders: list[str] = []

        def _replace_markdown_link(match: re.Match) -> str:
            label, url = match.group(1), match.group(2)
            if len(url) < 72 and "news.google.com" not in url:
                replacement = match.group(0)
            else:
                replacement = f"[{label or short_url_label(url)}]({url})"
            placeholders.append(replacement)
            return f"__REPORT_LINK_{len(placeholders) - 1}__"

        line = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", _replace_markdown_link, line)

        def _replace_plain_url(match: re.Match) -> str:
            url = match.group(0).rstrip("。；;,，)")
            suffix = match.group(0)[len(url):]
            return f"{short_url_label(url)}{suffix}"

        line = re.sub(r"https?://[^\s\)\]]+", _replace_plain_url, line)
        for idx, original in enumerate(placeholders):
            line = line.replace(f"__REPORT_LINK_{idx}__", original)
        return line

    return "\n".join(_compact_line(line) for line in text.splitlines())


def strip_internal_report_fields(text: str) -> str:
    """正式報告隱藏模型稽核欄位；raw debug 仍保留原始候選資料。"""
    if not text:
        return text

    lines = text.splitlines()
    cleaned: list[str] = []
    skip_candidate_section = False
    internal_field_pattern = re.compile(
        r"^\s*[*-]?\s*(?:\*\*)?"
        r"(信心水準|納入理由|技術/政策關鍵字|技術關鍵字|入選原因|初步分類|python_score)"
        r"(?:\*\*)?\s*[：:].*$"
    )
    internal_system_pattern = re.compile(
        r"^\s*(?:>\s*)?(?:[*-]\s*)?"
        r"(篩選類型|本次\s*ddgs\s*搜尋次數|ddgs\s*搜尋次數|系統內部搜尋次數|"
        r"prompt\s*字數|Prompt\s*字數|MaiAgent\s*呼叫次數|MaiAgent\s*呼叫|"
        r"來源健康|原始蒐集|重複排除後|初篩後|developer\s*debug|模型)"
        r"\s*[：:].*$",
        flags=re.IGNORECASE,
    )
    search_count_pattern = re.compile(r"^\s*(?:🔍\s*)?(?:\*\*)?執行搜尋次數")
    achieved_shortfall_pattern = re.compile(r"^\s*(?:⚠️\s*)?(?:\*\*)?不足\s*\d+\s*則原因(?:\*\*)?\s*[：:]\s*(?:已達標|無|無。)\s*$")

    for raw_line in lines:
        line = raw_line.strip()
        section_title = re.sub(r"^[#\s]+", "", line).strip()

        if re.match(r"^(候補觀察(?:（.*?）)?|第一階段入選新聞|國際學術與技術研究補充候選)$", section_title):
            skip_candidate_section = True
            continue

        if skip_candidate_section:
            if section_title.startswith(("報告摘要", "結尾")) or re.match(r"^[一二三四五六]、", section_title) or line.startswith(("📊", "⚠️", "⏰", "**本週統計", "本週統計", "**本期統計", "本期統計", "**不足", "不足", "**報告產出時間", "報告產出時間")):
                skip_candidate_section = False
            else:
                continue

        if internal_field_pattern.match(line):
            continue
        if internal_system_pattern.match(line):
            continue
        if search_count_pattern.match(line):
            continue
        if achieved_shortfall_pattern.match(line):
            continue
        if section_title in {"結尾", "結尾（必填）"}:
            continue

        cleaned.append(raw_line)

    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_unselected_report_sections(text: str) -> str:
    if not text or not selected_types:
        return text
    cleaned = text
    for category in ADVANCED_TYPES:
        if category in selected_types:
            continue
        number = SECTION_NUMBER_BY_TYPE.get(category, "")
        if number:
            cleaned = re.sub(
                rf"(?ms)^\s*#{{0,6}}\s*{re.escape(number)}\s*、\s*{re.escape(category)}\s*$.*?(?=^\s*#{{0,6}}\s*[一二三四五六]\s*、|^\s*📊|^\s*⏰|\Z)",
                "",
                cleaned,
            )
        cleaned = cleaned.replace(EMPTY_TEXT_BY_TYPE.get(category, ""), "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def strip_unselected_types_from_title(text: str) -> str:
    if not text or not selected_types:
        return text
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not line.lstrip().startswith("#"):
            continue
        title = line
        for category in ADVANCED_TYPES:
            if category in selected_types:
                continue
            title = title.replace(f"、{category}", "").replace(f"{category}、", "").replace(category, "")
        title = re.sub(r"、{2,}", "、", title).replace("：、", "：").replace("、｜", "｜")
        title = re.sub(r"[、\s]+$", "", title)
        lines[idx] = title
        break
    return "\n".join(lines)


def normalize_report_statistics_line(text: str) -> str:
    if not text:
        return text
    selected_parts = [category for category in ADVANCED_TYPES if category in selected_types]
    if not selected_parts:
        return text
    counts = count_report_items_by_category(text)
    total = sum(counts.get(category, 0) for category in selected_parts)
    stats_detail = " / ".join(f"{category} {counts.get(category, 0)} 則" for category in selected_parts)
    stats_line = f"📊 本期統計：共 {total} 則（{stats_detail}）"
    if re.search(r"(?m)^\s*📊\s*(?:本週|本期)統計.*$", text):
        return re.sub(r"(?m)^\s*📊\s*(?:本週|本期)統計.*$", stats_line, text, count=1)
    if re.search(r"(?m)^\s*(?:本週|本期)統計.*$", text):
        return re.sub(r"(?m)^\s*(?:本週|本期)統計.*$", stats_line, text, count=1)
    match = re.search(r"(?m)^\s*⏰", text)
    if match:
        return text[:match.start()].rstrip() + "\n" + stats_line + "\n" + text[match.start():].lstrip()
    return text.rstrip() + "\n\n" + stats_line


def strip_report_footer_lines(text: str) -> str:
    lines = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if re.match(r"^📊\s*(?:本週|本期)統計", line):
            continue
        if re.match(r"^(?:本週|本期)統計", line):
            continue
        if re.match(r"^⏰\s*報告產出時間", line):
            continue
        if re.match(r"^報告產出時間", line):
            continue
        lines.append(raw_line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def final_report_statistics_line(report_md: str, journal_candidates: list[dict] | None = None) -> str:
    selected_parts = [category for category in ADVANCED_TYPES if category in selected_types]
    counts = count_report_items_by_category(report_md)
    formal_total = sum(counts.get(category, 0) for category in selected_parts) if selected_parts else count_report_items(report_md)
    stats_detail = "／".join(f"{category} {counts.get(category, 0)} 則" for category in selected_parts)
    if stats_detail:
        line = f"📊 本期統計：正式新聞共 {formal_total} 則（{stats_detail}）"
    else:
        line = f"📊 本期統計：正式新聞共 {formal_total} 則"
    if include_research_supplement:
        line += f"；國際學術期刊共 {len(journal_candidates or [])} 篇"
    return line + "。"


def apply_final_report_footer(report_md: str, journal_candidates: list[dict] | None = None) -> str:
    body = strip_report_footer_lines(report_md)
    weekday = ['一', '二', '三', '四', '五', '六', '日'][today.weekday()]
    stats_line = final_report_statistics_line(body, journal_candidates)
    time_line = f"⏰ 報告產出時間：{today.strftime('%Y年%m月%d日')} 週{weekday}"
    return f"{body.rstrip()}\n\n{stats_line}\n\n{time_line}".strip()


def normalize_research_section_heading(text: str) -> str:
    if not text or not include_research_supplement:
        return text
    heading = research_section_heading(markdown=True)
    return re.sub(
        r"(?m)^\s*#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:技術研究補充|國際學術期刊)\s*$",
        heading,
        text,
        count=1,
    )


INTERNAL_REPORT_REPLACEMENTS = {
    "模型：MaiAgent 雲端 API": "",
    "候選資料指出": "資料顯示",
    "候選摘要指出": "摘要資料顯示",
    "入選資料指出": "資料顯示",
    "初篩資料指出": "資料顯示",
    "資料欄位顯示": "資料顯示",
    "本次候選資料": "本次資料",
    "原始候選資料": "資料來源",
    "raw data": "原始資料",
    "Raw data": "原始資料",
    "本次送入模型": "本次整理",
    "AI 入選": "本期納入",
    "模型判斷": "本週報歸類",
    "Python 初篩": "初步整理",
    "MaiAgent 判斷": "本週報整理",
    "developer debug": "",
    "Developer debug": "",
    "python_score": "",
    "入選原因": "",
    "初步分類": "",
    "來源健康": "來源狀態",
    "原始資料僅提供": "資料來源僅載明",
    "原始資料未提供": "資料來源未載明",
    "故不補述。": "",
    "故不補述": "",
    "原始資料未提供，故不補述。": "資料來源未載明更細部技術資料。",
    "原始資料未提供，故不補述": "資料來源未載明更細部技術資料",
}


def clean_internal_report_language(text: str) -> str:
    if not text:
        return text
    cleaned = text
    for old, new in INTERNAL_REPORT_REPLACEMENTS.items():
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"候選資料(?:指出|顯示|記載|提及)?", "資料", cleaned)
    cleaned = re.sub(r"候選摘要(?:指出|顯示|記載|提及)?", "摘要資料", cleaned)
    cleaned = re.sub(r"入選資料(?:指出|顯示|記載|提及)?", "資料", cleaned)
    cleaned = re.sub(r"初篩資料(?:指出|顯示|記載|提及)?", "資料", cleaned)
    cleaned = re.sub(r"(?im)^.*(?:模型：MaiAgent\s*雲端\s*API|來源健康|prompt\s*字數|MaiAgent\s*呼叫|本次送入模型|developer\s*debug|python_score|入選原因|初步分類).*$", "", cleaned)
    cleaned = re.sub(r"(?i)\braw data\b", "原始資料", cleaned)
    cleaned = re.sub(r"(?i)\bcandidates?\b", "資料", cleaned)
    cleaned = re.sub(r"來源連結[（(]\s*Google\s*News\s*[）)]", "來源連結", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[（(]\s*Google\s*News\s*proxy\s*[）)]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"由\s*Google\s*News\s*代理", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Google\s*News\s*地區代理\s*[－\-:：]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Google\s*News\s*代理", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"地區代理\s*[－\-:：]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfallback\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"資料來源未提供完整 URL（[^）]*）", "資料來源未提供完整 URL", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


SERVICE_OR_CIVIL_SYSTEM_TERMS = [
    "無障礙設施", "無障礙服務", "車站人流管理", "旅客服務", "活動疏運",
    "營運政策", "土建工程", "站體改善", "道路交通", "一般客服",
]

ICT_SECURITY_CONTEXT_TERMS = [
    "通訊網路", "通訊系統", "無線通訊", "網路安全", "資安", "資訊安全",
    "營運科技", "系統入侵", "駭客", "弱點", "漏洞", "資料安全",
    "OT", "IT", "CBTC", "SCADA", "OCC", "AFC", "cyber", "cybersecurity",
    "network", "communication", "communications", "telecom", "radio", "5G", "LTE",
    "intrusion", "hacker", "vulnerability", "data security",
]


def normalize_electromechanical_system_line(line: str) -> str:
    if "相關機電系統" not in line:
        return line
    prefix = line.split("相關機電系統", 1)[0] + "相關機電系統："
    value = line.split("相關機電系統", 1)[1].lstrip("：:").strip()
    value = normalize_electromechanical_system_value(value, line)
    return f"{prefix}{value}"


def normalize_electromechanical_system_value(value: str, context: str = "") -> str:
    value = (value or "").strip()
    context_without_value = (context or "").replace(value, "")
    if "未明確載明機電系統" in value:
        concrete_value = value.replace("未明確載明機電系統", "")
        concrete_value = re.sub(r"[、,\s]+", "、", concrete_value).strip("、 ，,")
        if concrete_value:
            value = concrete_value
    if "資通訊與資安" in value and not _contains_any_term(context_without_value, ICT_SECURITY_CONTEXT_TERMS):
        if _contains_any_term(context_without_value, WORK_ZONE_MONITORING_TERMS):
            value = value.replace("資通訊與資安", "維修安全監測設備")
        elif value.strip("、 ，,") == "資通訊與資安":
            value = "維修安全監測設備"
        else:
            value = value.replace("資通訊與資安", "")
    if "電梯" in value or "升降機" in value:
        value = value.replace("無障礙設施", "車站電梯").replace("無障礙服務", "車站電梯")
    if "票閘" in value or "閘門" in value:
        value = value.replace("旅客服務", "AFC 自動收費系統")
    for term in SERVICE_OR_CIVIL_SYSTEM_TERMS:
        value = value.replace(term, "")
    value = re.sub(r"[、,\s]+", "、", value).strip("、 ，,")
    if not value:
        value = "未明確載明機電系統"
    return value


def _short_formal_sentence(text: str, limit: int = 180) -> str:
    text = re.sub(r"^\s*[-•]\s*", "", text or "").strip()
    text = re.sub(r"^(可能影響系統|可參考作法|後續追蹤建議)\s*[：:]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ；;，,")
    if len(text) > limit:
        window = text[:limit]
        cut_at = max(window.rfind(mark) for mark in ("。", "；", ";", "，", ","))
        if cut_at >= max(60, limit // 2):
            text = window[:cut_at + 1].rstrip("，,；; ")
        else:
            overflow_window = text[: min(len(text), limit + 80)]
            next_sentence = min(
                [idx for idx in (overflow_window.find(mark, limit) for mark in ("。", "；", ";")) if idx >= 0],
                default=-1,
            )
            if next_sentence >= 0:
                text = overflow_window[:next_sentence + 1].rstrip()
            else:
                text = window.rstrip("，,；;。 ") + "。"
    return text


def simplify_taipei_insight(text: str) -> str:
    lines = (text or "").splitlines()
    output: list[str] = []
    idx = 0
    while idx < len(lines):
        raw_line = lines[idx]
        line = raw_line.strip()
        if "【臺北捷運局啟示】" not in line:
            output.append(raw_line)
            idx += 1
            continue

        prefix = raw_line.split("【臺北捷運局啟示】", 1)[0]
        header = f"{prefix}【臺北捷運局啟示】："
        inline_text = line.split("【臺北捷運局啟示】", 1)[1].lstrip("：:").strip()
        idx += 1
        collected: list[str] = []
        while idx < len(lines):
            next_line = lines[idx].strip()
            if (
                next_line.startswith("• 資料來源")
                or next_line.startswith("• 發布/事件日期")
                or next_line.startswith("🔹")
                or next_line.startswith("________________________________________")
                or re.match(r"^[一二三四五六]、", next_line)
                or next_line.startswith("📊")
                or next_line.startswith("⏰")
            ):
                break
            if next_line:
                collected.append(next_line)
            idx += 1
        insight = _short_formal_sentence("；".join([inline_text] + collected))
        output.append(header)
        if insight:
            output.append(insight)
        continue
    return "\n".join(output)


def remove_legacy_report_fields(text: str) -> str:
    lines = []
    skip_legacy_insight_bullets = False
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if re.match(r"^•\s*(技術關鍵字|技術/政策關鍵字|入選原因|初步分類|python_score)\s*[：:]", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^[-•]\s*(可能影響系統|可參考作法|後續追蹤建議)\s*[：:]", line):
            continue
        if "相關機電系統" in raw_line:
            raw_line = normalize_electromechanical_system_line(raw_line)
        lines.append(raw_line)
    return "\n".join(lines)


def reduce_repeated_source_subjects(text: str) -> str:
    output: list[str] = []
    seen_subjects: set[str] = set()
    for raw_line in (text or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("🔹") or stripped.startswith("________________________________________"):
            seen_subjects = set()
        match = re.match(r"^(\s*-\s*)(依\s*[^，。；;]{2,40}(?:公告|報導|官方資料|發布))(?:，|指出，|顯示，)?\s*(.*)$", raw_line)
        if match:
            subject = re.sub(r"\s+", "", match.group(2))
            if subject in seen_subjects and match.group(3):
                raw_line = f"{match.group(1)}{match.group(3)}"
            else:
                seen_subjects.add(subject)
        output.append(raw_line)
    return "\n".join(output)


def simplify_formal_report_format(text: str) -> str:
    text = remove_legacy_report_fields(text)
    text = simplify_taipei_insight(text)
    text = reduce_repeated_source_subjects(text)
    return text


REPORT_FIELD_ALIASES = {
    "發布/事件日期": "發布/事件日期",
    "國家/地區": "國家/地區",
    "相關機電系統": "相關機電系統",
    "事件摘要": "事件摘要",
    "臺北捷運局啟示": "臺北捷運局啟示",
    "資料來源": "資料來源",
}


def _match_report_field_line(line: str) -> tuple[str, str] | None:
    match = re.match(
        r"^\s*(?:[-*]\s*)?(?:•\s*)?(?:\*\*)?(?:【)?"
        r"(發布/事件日期|國家/地區|相關機電系統|事件摘要|臺北捷運局啟示|資料來源)"
        r"(?:】)?(?:\*\*)?\s*[：:]\s*(.*)$",
        line or "",
    )
    if not match:
        return None
    return REPORT_FIELD_ALIASES[match.group(1)], match.group(2).strip()


def _is_report_block_boundary(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if _match_report_field_line(stripped):
        return True
    if stripped == "---" or stripped.startswith(("🔹", "📊", "⏰", "#", ">", "________________________________________")):
        return True
    return bool(re.match(r"^[一二三四五六]\s*、", stripped))


def _strip_nested_bullet_text(text: str) -> str:
    text = re.sub(r"^\s*[-*•]\s*", "", text or "")
    text = re.sub(r"^\s*(?:重點\s*\d+|[-*•])\s*[：:]?\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ；;，,")


def _join_field_parts(parts: list[str]) -> str:
    cleaned = [_strip_nested_bullet_text(part) for part in parts if _strip_nested_bullet_text(part)]
    text = " ".join(cleaned)
    text = re.sub(r"\s*[-*•]\s+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _dedupe_source_mentions_in_paragraph(text: str) -> str:
    seen: set[str] = set()

    def _replace(match: re.Match) -> str:
        subject = re.sub(r"\s+", "", match.group(1))
        if subject in seen:
            return ""
        seen.add(subject)
        return match.group(0)

    text = re.sub(
        r"(依\s*[^，。；;]{2,40}(?:公告|報導|官方資料|發布)(?:指出|顯示)?[，,]?)",
        _replace,
        text or "",
    )
    return re.sub(r"\s+", " ", text).strip()


def strip_event_summary_source_lead_in(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return cleaned
    lead_in_pattern = (
        r"^(?:依|根據)\s*"
        r"[^，。,；;：:\n]{2,80}?"
        r"(?:官方公告|官方資料|報導|公告)"
        r"(?:指出|表示|說明)?"
        r"\s*[，,：:]\s*"
    )
    return re.sub(lead_in_pattern, "", cleaned, count=1).strip()


def _looks_like_english_title(title: str) -> bool:
    compact = re.sub(r"[\s\W_]+", "", title or "")
    if not compact:
        return False
    ascii_chars = sum(1 for char in compact if ord(char) < 128)
    cjk_chars = len(re.findall(r"[\u3400-\u9fff]", compact))
    return ascii_chars >= 8 and ascii_chars > cjk_chars * 2


def chinese_fallback_title(category: str, title: str) -> str:
    lower = (title or "").casefold()
    if "automated work zone speed enforcement" in lower:
        return "MTA 推動工區自動速限執法計畫"
    if "r211" in lower and "d line" in lower:
        return "MTA R211A 新型列車導入紐約地鐵 D 線"
    if "driverless train" in lower and "western sydney airport" in lower:
        return "雪梨西部機場捷運線首列無人駕駛列車抵達"
    if "cbtc" in lower:
        return "CBTC 列車控制系統更新案"
    if "signalling" in lower or "signaling" in lower:
        return "捷運號誌系統更新案"
    if "platform screen door" in lower:
        return "月臺門系統更新案"
    if "afc" in lower or "ticketing" in lower or "fare" in lower:
        return "AFC 票務系統更新案"
    if "power" in lower or "substation" in lower or "traction" in lower:
        return "捷運供電系統更新案"
    if "cyber" in lower or "security" in lower:
        return "捷運資安防護更新案"
    if "driverless" in lower or "automated train" in lower:
        return "無人駕駛捷運列車導入案"
    if "train" in lower or "fleet" in lower:
        return "捷運列車更新案"
    if "metro" in lower or "subway" in lower or "light rail" in lower or "tram" in lower:
        if category == "重大事故":
            return "都市軌道重大事故事件"
        if category == "營運政策":
            return "都市軌道營運政策更新"
        if category == "營運爭議":
            return "都市軌道營運爭議事件"
        return "都市軌道系統更新案"
    return {
        "技術新知": "國際捷運技術更新案",
        "重大事故": "國際捷運重大事故事件",
        "營運政策": "國際捷運營運政策更新",
        "營運爭議": "國際捷運營運爭議事件",
        "規範更新": "國際捷運規範更新案",
    }.get(category, "國際捷運案例")


def normalize_report_title_line(line: str) -> str:
    match = re.match(r"^\s*🔹\s*\[([^\]]+)\]\s*(.+?)\s*$", line or "")
    if not match:
        return line
    category = match.group(1).strip()
    title = match.group(2).strip()
    if _looks_like_english_title(title):
        title = chinese_fallback_title(category, title)
    return f"🔹 [{category}] {title}"


def normalize_final_report_md(md: str) -> str:
    text = md or ""
    text = re.sub(r"(?m)^\s*[-*]\s*\*\*(發布/事件日期|國家/地區|相關機電系統|事件摘要|臺北捷運局啟示|資料來源)\*\*\s*[：:]", r"• \1：", text)
    text = re.sub(r"(?m)^\s*[-*]\s*\*\*【臺北捷運局啟示】\*\*\s*[：:]", "• 臺北捷運局啟示：", text)
    text = re.sub(r"(?m)^\s*•\s*【臺北捷運局啟示】\s*[：:]", "• 臺北捷運局啟示：", text)
    text = re.sub(r"(?m)^#{3,6}\s+\[([^\]]+)\]\s*(.+)$", r"🔹 [\1] \2", text)

    lines = text.splitlines()
    output: list[str] = []
    idx = 0
    while idx < len(lines):
        raw_line = lines[idx]
        stripped = raw_line.strip()
        if not stripped:
            output.append(raw_line)
            idx += 1
            continue
        if stripped in {"•", "-", "*"}:
            idx += 1
            continue

        field = _match_report_field_line(raw_line)
        if not field:
            output.append(normalize_report_title_line(raw_line) if stripped.startswith("🔹") else raw_line)
            idx += 1
            continue

        label, value = field
        context_window = "\n".join(lines[max(0, idx - 8): min(len(lines), idx + 10)])
        idx += 1
        collected = [value]
        while idx < len(lines):
            next_line = lines[idx].strip()
            if not next_line:
                idx += 1
                continue
            if _is_report_block_boundary(next_line):
                break
            collected.append(next_line)
            idx += 1

        field_text = _join_field_parts(collected)
        if label == "事件摘要":
            field_text = strip_event_summary_source_lead_in(field_text)
            field_text = _dedupe_source_mentions_in_paragraph(field_text)
            if field_text:
                output.extend(["• 事件摘要：", field_text, ""])
        elif label == "臺北捷運局啟示":
            insight = _short_formal_sentence(field_text, 180)
            if insight:
                output.extend(["• 臺北捷運局啟示：", insight, ""])
        elif label == "資料來源":
            output.extend([normalize_source_line(f"• 資料來源：{field_text}"), ""])
        elif label == "相關機電系統":
            system_value = normalize_electromechanical_system_value(field_text, context_window)
            if system_value:
                output.extend([f"• 相關機電系統：{system_value}", ""])
        else:
            if field_text:
                output.extend([f"• {label}：{field_text}", ""])

    text = "\n".join(output)
    text = normalize_report_source_lines(text)
    text = re.sub(r"(?m)^\s*(?:[-*]\s*)?•\s*$", "", text)
    text = re.sub(r"(?m)^•\s*事件摘要：\s*[-*•]\s*", "• 事件摘要：", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sanitize_report_text(text: str) -> str:
    text = (
        text.replace("全球（排除台灣）", "全球（安全白名單來源）")
        .replace("全球(排除台灣)", "全球（安全白名單來源）")
        .replace("（排除台灣）", "")
        .replace("(排除台灣)", "")
    )
    text = clean_internal_report_language(text)
    text = simplify_formal_report_format(text)
    if not include_research_supplement:
        text = re.sub(r"(?ms)^#{0,6}\s*(?:[一二三四五六七八九十]、)?(?:技術研究補充|國際學術期刊).*?(?=^#{0,6}\s*[一二三四五六七八九十]\s*、|^📊|^⏰|\Z)", "", text)
        text = re.sub(r"(?m)^.*(?:技術研究補充|國際學術期刊).*$", "", text)
    text = strip_unselected_types_from_title(text)
    text = strip_unselected_report_sections(text)
    text = normalize_report_source_lines(text)
    text = strip_internal_report_fields(text)
    text = normalize_final_report_md(text)
    text = normalize_research_section_heading(text)
    text = strip_internal_report_fields(text)
    return normalize_report_statistics_line(text)




def _journal_theme_summary(journal_candidates: list[dict]) -> list[str]:
    theme_terms = [
        ("列車控制與號誌安全", ["cbtc", "signalling", "signaling", "train control", "ato", "atp", "號誌", "列控"]),
        ("車輛與維修管理", ["rolling stock", "vehicle", "maintenance", "condition monitoring", "車輛", "維修", "監測"]),
        ("牽引供電與能源效率", ["traction power", "regenerative", "energy", "power supply", "牽引", "供電", "能源"]),
        ("資料治理、AI 與數位分身", ["data", "ai", "machine learning", "digital twin", "資料", "數位分身", "人工智慧"]),
        ("旅客流量與營運韌性", ["passenger flow", "resilience", "operation", "capacity", "旅客流量", "韌性", "運能"]),
        ("資安與系統整合", ["cyber", "system integration", "security", "資安", "系統整合"]),
    ]
    text = " ".join(f"{item.get('title','')} {item.get('snippet','')}" for item in journal_candidates or [])
    themes = [label for label, terms in theme_terms if _contains_any_term(text, terms)]
    return themes or ["都市軌道機電系統資料化、智慧化與維運管理"]


def build_journal_summary_conclusion(journal_candidates: list[dict]) -> str:
    themes = _unique_limited(_journal_theme_summary(journal_candidates), 4)
    theme_text = "、".join(themes)
    source_names = _unique_limited([
        item.get("journal_name") or item.get("source") or _domain_from_url(item.get("url", ""))
        for item in journal_candidates or []
    ], 4)
    source_text = "、".join(source_names) if source_names else "本期入選研究來源"
    return (
        f"本期國際學術期刊補充依系統取得之正式期刊或可信研究頁面整理，入選研究主要來自{source_text}，"
        f"觀察主題集中於{theme_text}等方向。整體而言，近期都市軌道研究已由單一設備改善，逐步轉向以資料、模型與系統整合支撐營運安全、維修決策及能源效率管理。"
        f"相關研究對臺北捷運局之啟示，在於新線規劃與既有系統更新時，應及早界定資料來源、欄位格式、系統介面、模型驗證、維修流程與營運安全邊界；"
        f"導入 AI、數位分身或預測維護等工具時，也應避免僅著重演算法展示，而需同步建立資料品質、資安權限、異常處置與跨系統驗證機制。"
        f"後續可將此類研究作為機電系統需求規劃、維修管理制度、能源效率策略及風險控管之參考來源，並以可追溯、可驗證、可維運為技術導入原則。"
    )


def ensure_journal_summary_conclusion(report_md: str, journal_candidates: list[dict]) -> str:
    if not include_research_supplement or not journal_candidates:
        return report_md
    if "學術期刊綜合結論" in (report_md or ""):
        return report_md
    conclusion = "【學術期刊綜合結論】\n" + build_journal_summary_conclusion(journal_candidates)
    match = re.search(r"(?m)^📊", report_md or "")
    if match:
        return (report_md[:match.start()].rstrip() + "\n\n" + conclusion + "\n\n" + report_md[match.start():].lstrip()).strip()
    return (report_md or "").rstrip() + "\n\n" + conclusion


def _journal_candidate_full_date(item: dict) -> str:
    for key in ("published_date", "date"):
        date_obj = _parse_full_research_date(str(item.get(key, "") or ""))
        if date_obj:
            return date_obj.isoformat()
    return ""


def _journal_candidate_date_for_text(text: str, journal_candidates: list[dict]) -> str:
    haystack = text or ""
    for item in journal_candidates or []:
        date_text = _journal_candidate_full_date(item)
        if not date_text:
            continue
        for value in (item.get("url", ""), item.get("doi", "")):
            value = str(value or "").strip()
            if value and value in haystack:
                return date_text
        title_tokens = [
            token for token in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{5,}", item.get("title", "") or "")
            if len(token) >= 5
        ]
        if title_tokens and sum(1 for token in title_tokens[:6] if token in haystack) >= 2:
            return date_text
    return ""


def repair_journal_dates_in_report(report_md: str, journal_candidates: list[dict]) -> str:
    if not include_research_supplement or not journal_candidates or not report_md:
        return report_md
    heading_match = re.search(
        r"(?m)^#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:技術研究補充|國際學術期刊)\s*$",
        report_md,
    )
    if not heading_match:
        return report_md
    end_match = re.search(r"(?m)^(?:📊|⏰)", report_md[heading_match.end():])
    section_end = heading_match.end() + end_match.start() if end_match else len(report_md)
    before = report_md[:heading_match.start()]
    section = report_md[heading_match.start():section_end]
    after = report_md[section_end:]

    candidate_dates = [date for date in (_journal_candidate_full_date(item) for item in journal_candidates) if date]
    date_index = 0
    active_date = ""

    def _next_candidate_date() -> str:
        nonlocal date_index
        if date_index >= len(candidate_dates):
            return ""
        date_text = candidate_dates[date_index]
        date_index += 1
        return date_text

    def _mark_candidate_date_used(date_text: str) -> None:
        nonlocal date_index
        while date_text and date_index < len(candidate_dates):
            current = candidate_dates[date_index]
            date_index += 1
            if current == date_text:
                break

    def _replace_line_date(line_text: str, date_text: str) -> str:
        if not date_text:
            return line_text
        if "發表日期" in line_text:
            return re.sub(
                r"^\s*(?:\d+[\.\、]\s*)?(?:[-*]\s*)?(?:•\s*)?發表日期.*$",
                f"• 發表日期：{date_text}",
                line_text,
                count=1,
            )
        if "日期未知" in line_text:
            return line_text.replace("日期未知", date_text, 1)
        if re.search(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", line_text):
            line_text = re.sub(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", date_text, line_text, count=1)
            return re.sub(rf"({re.escape(date_text)})[，,\s]*(?:{re.escape(date_text)})", r"\1", line_text)
        if re.search(r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日", line_text):
            line_text = re.sub(r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日", date_text, line_text, count=1)
            return re.sub(rf"({re.escape(date_text)})[，,\s]*(?:{re.escape(date_text)})", r"\1", line_text)
        if re.match(r"^\s*(?:[-*]\s*)?(?:•\s*)?發表日期\s*[：:]\s*$", line_text):
            return re.sub(r"([：:])\s*$", rf"\1{date_text}", line_text)
        return line_text

    repaired_lines: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped == "---" or stripped.startswith(("###", "🔹")):
            active_date = ""

        matched_date = _journal_candidate_date_for_text(line, journal_candidates)
        if matched_date:
            active_date = matched_date
            _mark_candidate_date_used(matched_date)

        if "發表日期" in line:
            replacement_date = matched_date or active_date or _next_candidate_date()
            if replacement_date:
                line = _replace_line_date(line, replacement_date)
                active_date = replacement_date
        elif "資料來源" in line:
            replacement_date = matched_date or active_date
            if replacement_date and ("日期未知" in line or re.search(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", line)):
                line = _replace_line_date(line, replacement_date)
                active_date = replacement_date

        repaired_lines.append(line)

    return before + "\n".join(repaired_lines) + after


def normalize_journal_section_format(report_md: str, journal_candidates: list[dict]) -> str:
    if not include_research_supplement or not journal_candidates or not report_md:
        return report_md
    heading_match = re.search(
        r"(?m)^#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:技術研究補充|國際學術期刊)\s*$",
        report_md,
    )
    if not heading_match:
        return report_md
    end_match = re.search(r"(?m)^(?:📊|⏰)", report_md[heading_match.end():])
    section_end = heading_match.end() + end_match.start() if end_match else len(report_md)
    before = report_md[:heading_match.start()]
    section = report_md[heading_match.start():section_end]
    after = report_md[section_end:]

    lines = section.splitlines()
    if not lines:
        return report_md
    output: list[str] = [lines[0]]
    item_index = 0
    in_conclusion = False
    field_names = ("發表日期", "期刊/來源", "期刊／來源", "研究主題", "研究摘要", "臺北捷運局啟示", "資料來源")
    seen_fields_by_item: dict[int, set[str]] = {}

    def _candidate_for_item(index: int) -> dict:
        if 1 <= index <= len(journal_candidates):
            return journal_candidates[index - 1] or {}
        return {}

    def _candidate_display_title(index: int) -> str:
        item = _candidate_for_item(index)
        title = _clean_text(str(item.get("title", "") or ""))
        title = re.sub(r"\[[^\]]*(?:技術研究補充|國際學術期刊)[^\]]*\]\s*", "", title).strip()
        return title or f"國際學術期刊研究 {index}"

    def _candidate_source_name(index: int) -> str:
        item = _candidate_for_item(index)
        source = (
            item.get("journal_name")
            or item.get("source")
            or item.get("source_display")
            or _domain_from_url(item.get("url", ""))
        )
        source = _clean_source_label(str(source or ""), item.get("url", ""), _domain_from_url(item.get("url", "")))
        if source == "資料來源未明確辨識":
            return ""
        return source

    def _repair_truncated_value(value: str, expected: str) -> str:
        value = (value or "").strip()
        expected = (expected or "").strip()
        if not value or not expected:
            return value
        if expected.casefold() == value.casefold():
            return expected
        if expected.casefold().endswith(value.casefold()) and 0 < len(expected) - len(value) <= 3:
            return expected
        return value

    def _field_match(raw_line: str) -> tuple[str, str] | None:
        stripped = raw_line.strip()
        match = re.match(
            r"^\s*(?:\d+[\.\、]\s*)?(?:[-*]\s*)?(?:•\s*)?"
            r"(發表日期|期刊[/／]來源|研究主題|研究摘要|臺北捷運局啟示|資料來源)"
            r"\s*[：:]\s*(.*)$",
            stripped,
        )
        if match:
            field = "期刊／來源" if match.group(1) in {"期刊/來源", "期刊／來源"} else match.group(1)
            return field, match.group(2).strip()
        match = re.match(
            r"^\s*(?:\d+[\.\、]\s*)?(?:[-*]\s*)?(?:•\s*)?發表日期\s*[Pp]\s*(.*)$",
            stripped,
        )
        if match:
            return "發表日期", match.group(1).strip()
        return None

    def _clean_journal_title_line(raw_line: str) -> str:
        title = raw_line.strip()
        title = re.sub(r"^\s*#{3,6}\s*", "", title)
        title = re.sub(r"^\s*🔹\s*", "", title)
        title = re.sub(r"\[[^\]]*(?:技術研究補充|國際學術期刊)[^\]]*\]\s*", "", title)
        title = re.sub(r"^\s*(?:\d+[\.\、]|[（(]?\d+[）)])\s*", "", title)
        title = title.strip(" ：:　")
        return title

    def _matches_candidate_title(candidate_title: str, candidate: dict) -> bool:
        original = str(candidate.get("title", "") or "")
        if not original or not candidate_title:
            return False
        if candidate_title.casefold() in original.casefold() or original.casefold() in candidate_title.casefold():
            return True
        original_tokens = [
            token.casefold()
            for token in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{5,}", original)
            if len(token) >= 5
        ]
        title_lower = candidate_title.casefold()
        return bool(original_tokens) and sum(1 for token in original_tokens[:8] if token in title_lower) >= 2

    def _looks_like_title_line(raw_line: str, title: str) -> bool:
        stripped = raw_line.strip()
        if not title or any(title.startswith(name) for name in field_names):
            return False
        if "學術期刊綜合結論" in title:
            return False
        if re.match(r"^\s*(?:#{3,6}|🔹|\d+[\.\、]|[（(]?\d+[）)])", stripped):
            return True
        if re.search(r"\[[^\]]*(?:技術研究補充|國際學術期刊)[^\]]*\]", stripped):
            return True
        if any(_matches_candidate_title(title, item) for item in journal_candidates or []):
            return True
        if item_index < len(journal_candidates) and "：" not in title and ":" not in title:
            if len(title) <= 120 and not title.endswith(("。", "；", ";")) and not title.startswith(("以下", "本期", "研究補充", "國際學術期刊")):
                return True
        return False

    def _repair_date_value(value: str, index: int) -> str:
        candidate_date = _journal_candidate_full_date(_candidate_for_item(index))
        if candidate_date:
            return candidate_date
        value = (value or "").strip()
        match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", value)
        if match:
            return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        if re.fullmatch(r"(?:0?\d{2}|\d{3})[-/]\d{1,2}[-/]\d{1,2}", value):
            return "日期未明"
        year_match = re.fullmatch(r"(20\d{2}|19\d{2})\s*年?", value)
        if year_match:
            return f"{year_match.group(1)}年"
        if not value or value in {"日期未知", "日期未明", "未知"}:
            return "日期未明"
        return value

    def _repair_field_value(field: str, value: str, index: int) -> str:
        value = _clean_text(value)
        if field == "發表日期":
            return _repair_date_value(value, index)
        if field == "期刊／來源":
            expected = _candidate_source_name(index)
            value = _repair_truncated_value(value, expected)
            if not value or value in {"資料來源未明確辨識", "報導"}:
                value = expected
            return value or "期刊來源未明"
        return value or "資料未載明"

    def _append_blank_if_needed() -> None:
        if output and output[-1].strip():
            output.append("")

    def _append_title(title: str) -> None:
        nonlocal item_index
        item_index += 1
        _append_blank_if_needed()
        output.append(f"{item_index}、{title}")
        seen_fields_by_item.setdefault(item_index, set())

    def _ensure_item_started() -> None:
        if item_index <= 0:
            _append_title(_candidate_display_title(1))

    def _append_field(field: str, value: str) -> None:
        _ensure_item_started()
        seen_fields = seen_fields_by_item.setdefault(item_index, set())
        if field in seen_fields:
            return
        output.append(f"• {field}：{_repair_field_value(field, value, item_index)}")
        seen_fields.add(field)

    def _process_body_line(raw_line: str) -> None:
        stripped = raw_line.strip()
        if not stripped:
            _append_blank_if_needed()
            return
        if stripped == "---":
            return
        field_match = _field_match(raw_line)
        if field_match:
            _append_field(field_match[0], field_match[1])
            return
        explicit_title_marker = bool(
            re.match(r"^\s*(?:#{3,6}|🔹|\d+[\.\、]|[（(]?\d+[）)])", stripped)
            or re.search(r"\[[^\]]*(?:技術研究補充|國際學術期刊)[^\]]*\]", stripped)
        )
        if output and output[-1].startswith("• ") and not explicit_title_marker:
            output[-1] = output[-1].rstrip() + " " + stripped
            return
        title = _clean_journal_title_line(raw_line)
        if _looks_like_title_line(raw_line, title):
            _append_title(title)
            return
        if item_index == 0:
            output.append(stripped)
        elif output and output[-1].startswith("• "):
            output[-1] = output[-1].rstrip() + " " + stripped
        else:
            output.append(stripped)

    for raw_line in lines[1:]:
        stripped = raw_line.strip()
        if in_conclusion:
            output.append(raw_line)
            continue
        if "學術期刊綜合結論" in stripped:
            prefix, _, suffix = raw_line.partition("學術期刊綜合結論")
            if prefix.strip():
                _process_body_line(prefix)
            _append_blank_if_needed()
            output.append("學術期刊綜合結論")
            suffix = suffix.strip(" ：:】]「」")
            if suffix:
                output.append(suffix)
            in_conclusion = True
            continue
        _process_body_line(raw_line)

    normalized = re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()
    return before + normalized + after


def count_journal_summary_conclusion_chars(report_md: str) -> int:
    match = re.search(r"學術期刊綜合結論[】\]]?\s*\n?(.+?)(?=^📊|^⏰|\Z)", report_md or "", flags=re.DOTALL | re.MULTILINE)
    if not match:
        return 0
    return len(re.sub(r"\s+", "", match.group(1)))


def enforce_research_section(report_md: str, journal_candidates: list[dict]) -> str:
    if not include_research_supplement:
        return report_md
    if journal_candidates:
        return report_md
    heading = research_section_heading(markdown=True)
    fallback = f"{heading}\n本期未發現符合期間條件且具明確發表日期之國際學術或技術研究資料。"
    if re.search(r"(?m)^#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:技術研究補充|國際學術期刊)\s*$", report_md or ""):
        return re.sub(
            r"(?ms)^#{0,6}\s*[一二三四五六七八九十]\s*、\s*(?:技術研究補充|國際學術期刊)\s*.*?(?=^📊|^⏰|\Z)",
            fallback + "\n\n",
            report_md,
            count=1,
        ).strip()
    match = re.search(r"(?m)^📊", report_md or "")
    if match:
        return (report_md[:match.start()].rstrip() + "\n\n" + fallback + "\n\n" + report_md[match.start():].lstrip()).strip()
    return (report_md.rstrip() + "\n\n" + fallback).strip()


def _candidate_report_presence_keys(candidate: dict) -> list[str]:
    source_url = _effective_source_url(candidate)
    values = []
    complete_source_url = _extract_complete_url(source_url)
    if complete_source_url:
        values.append(complete_source_url)
    raw_url = candidate.get("url", "")
    complete_raw_url = _extract_complete_url(raw_url)
    if complete_raw_url and complete_raw_url not in values:
        values.append(complete_raw_url)
    values.append(candidate.get("title", ""))
    return [str(value).strip() for value in values if str(value or "").strip()]


def _report_block_matches_candidate(block: str, candidate: dict) -> bool:
    keys = _candidate_report_presence_keys(candidate)
    if any(key and key in (block or "") for key in keys):
        return True
    title_tokens = [
        token for token in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{4,}", candidate.get("title", "") or "")
        if len(token) >= 4
    ]
    return bool(title_tokens) and sum(1 for token in title_tokens[:6] if token in (block or "")) >= 2


def _candidate_region_display(candidate: dict) -> str:
    text = _candidate_selection_text(candidate)
    region = _canonical_candidate_region(dict(candidate))
    city_map = [
        ("北愛爾蘭", ["northern ireland", "belfast", "北愛爾蘭", "貝爾法斯特"], "英國（北愛爾蘭）"),
        ("巴塞爾", ["basel", "巴塞爾"], "瑞士（巴塞爾）"),
        ("休士頓", ["houston", "休士頓", "休斯頓"], "美國（休士頓）"),
        ("溫哥華", ["vancouver", "broadway subway", "溫哥華"], "加拿大（溫哥華）"),
        ("多倫多", ["toronto", "finch west", "多倫多"], "加拿大（多倫多）"),
        ("柏林", ["berlin", "adlershof", "柏林"], "德國（柏林）"),
        ("萊比錫", ["leipzig", "萊比錫"], "德國（萊比錫）"),
    ]
    for _, terms, label in city_map:
        if _contains_any_term(text, terms):
            return label
    return region or "未判定"


def repair_report_region_lines(report_md: str, selected_candidates: list[dict]) -> str:
    if not report_md or not selected_candidates:
        return report_md
    parts = re.split(r"(?m)^(🔹\s*\[[^\]]+\].*)$", report_md)
    if len(parts) <= 1:
        return report_md
    output = [parts[0]]
    for idx in range(1, len(parts), 2):
        heading = parts[idx]
        body = parts[idx + 1] if idx + 1 < len(parts) else ""
        block = heading + body
        matched = next((candidate for candidate in selected_candidates if _report_block_matches_candidate(block, candidate)), None)
        if matched:
            region_display = _candidate_region_display(matched)
            if re.search(r"(?m)^•\s*國家/地區\s*[：:].*$", body):
                body = re.sub(r"(?m)^•\s*國家/地區\s*[：:].*$", f"• 國家/地區：{region_display}", body, count=1)
        output.extend([heading, body])
    return "".join(output)


GENERIC_FORMAL_TITLES = {
    "國際捷運技術更新案",
    "都市軌道系統更新案",
    "國際捷運營運政策更新",
    "國際捷運重大事故事件",
    "都市軌道重大事故事件",
    "國際捷運營運爭議事件",
    "國際捷運案例",
}


def _is_generic_formal_title(title: str) -> bool:
    cleaned = re.sub(r"\s+", "", title or "")
    return any(re.sub(r"\s+", "", item) in cleaned for item in GENERIC_FORMAL_TITLES)


def formal_title_from_candidate(candidate: dict) -> str:
    category = candidate.get("classification") or candidate.get("preliminary_type") or infer_preliminary_type(candidate)
    text = _candidate_selection_text(candidate)
    original_title = _clean_text(candidate.get("title", ""))
    if _contains_any_term(text, ["finch west", "hitachi"]):
        return "多倫多 Finch West LRT 啟用 Hitachi Rail 號誌系統"
    if _contains_any_term(text, ["broadway subway"]):
        return "溫哥華 Broadway Subway 都市軌道專案進展"
    if _contains_any_term(text, ["houston", "metrorail"]):
        return "休士頓 METRORail 都市軌道事件"
    if _contains_any_term(text, ["adlershof"]):
        return "柏林 Adlershof 電車撞擊事故"
    if _contains_any_term(text, ["basel"]) and category == "重大事故":
        return "巴塞爾電車碰撞事故"
    if _contains_any_term(text, ["leipzig"]) and category == "重大事故":
        return "萊比錫路面電車營運安全事件"

    region = _candidate_region_display(candidate)
    region = re.sub(r"^(.+?)（(.+?)）$", r"\2", region)
    theme = _candidate_system_theme(candidate)
    if original_title and not _is_generic_formal_title(original_title):
        if _looks_like_english_title(original_title):
            return f"{region} {theme}：{_shorten(original_title, 72)}"
        return original_title
    if category == "重大事故":
        return f"{region}都市軌道營運安全事件"
    if category == "營運政策":
        return f"{region}{theme}營運政策更新"
    if category == "營運爭議":
        return f"{region}都市軌道營運爭議事件"
    if category == "規範更新":
        return f"{region}都市軌道規範更新"
    return f"{region}{theme}更新"


def repair_generic_report_titles(report_md: str, selected_candidates: list[dict]) -> str:
    if not report_md or not selected_candidates:
        return report_md
    parts = re.split(r"(?m)^(🔹\s*\[[^\]]+\]\s*.*)$", report_md)
    if len(parts) <= 1:
        return report_md
    output = [parts[0]]
    for idx in range(1, len(parts), 2):
        heading = parts[idx]
        body = parts[idx + 1] if idx + 1 < len(parts) else ""
        match = re.match(r"^(🔹\s*\[([^\]]+)\]\s*)(.*)$", heading.strip())
        if match and _is_generic_formal_title(match.group(3)):
            block = heading + body
            matched = next((candidate for candidate in selected_candidates if _report_block_matches_candidate(block, candidate)), None)
            if matched:
                heading = f"{match.group(1)}{formal_title_from_candidate(matched)}"
        output.extend([heading, body])
    return "".join(output)


def identify_dropped_selected_candidates(report_md: str, selected_candidates: list[dict]) -> list[dict]:
    report_text = report_md or ""
    dropped: list[dict] = []
    for candidate in selected_candidates or []:
        keys = _candidate_report_presence_keys(candidate)
        title = candidate.get("title", "")
        title_tokens = [
            token for token in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{4,}", title or "")
            if len(token) >= 4
        ]
        present = any(key and key in report_text for key in keys)
        if not present and title_tokens:
            present = sum(1 for token in title_tokens[:5] if token in report_text) >= 2
        if not present:
            dropped.append(candidate)
    return dropped


def _fallback_system_value_for_candidate(candidate: dict) -> str:
    theme = _candidate_system_theme(candidate)
    if theme and theme != "未分類":
        return theme
    classification = candidate.get("classification") or candidate.get("preliminary_type", "")
    if classification == "重大事故":
        return "營運安全、設備監測與應變管理"
    if classification == "營運政策":
        return "營運管理、旅客資訊與車站設備"
    if classification == "營運爭議":
        return "營運管理與風險溝通"
    if classification == "規範更新":
        return "規範、系統安全與驗證"
    return "未明確載明機電系統"


def _fallback_report_item_for_candidate(candidate: dict) -> str:
    category = candidate.get("classification") or candidate.get("preliminary_type") or "技術新知"
    title = formal_title_from_candidate(candidate)
    date_text = _normalize_report_date_text(candidate.get("date", "")) if candidate.get("date") else "日期未知"
    region = _candidate_region_display(candidate)
    source_url = _effective_source_url(candidate)
    source_display = candidate.get("source_display") or source_label_for_report(
        candidate.get("source", ""), candidate.get("url", ""), candidate.get("source_href", ""), candidate.get("source_tier", "")
    )
    snippet = _short_formal_sentence(candidate.get("snippet", "") or candidate.get("title", ""), 260)
    insight = _short_formal_sentence(
        "本案由 Python 規則選題保守補回；後續可追蹤原始來源，確認其對系統整合、維修管理、營運安全或資料治理之具體影響。",
        220,
    )
    return "\n".join([
        f"🔹 [{category}] {title}",
        "",
        f"• 發布/事件日期：{date_text}",
        "",
        f"• 國家/地區：{region}",
        "",
        f"• 相關機電系統：{_fallback_system_value_for_candidate(candidate)}",
        "",
        "• 事件摘要：",
        snippet,
        "",
        "• 臺北捷運局啟示：",
        insight,
        "",
        normalize_source_line(f"• 資料來源：{source_display}，{date_text}，{source_url or candidate.get('source_domain', '')}"),
        "",
        "---",
    ])


def restore_missing_selected_report_items(report_md: str, selected_candidates: list[dict]) -> tuple[str, list[dict]]:
    dropped = identify_dropped_selected_candidates(report_md, selected_candidates)
    if not dropped:
        return report_md, []
    additions = "\n\n".join(_fallback_report_item_for_candidate(candidate) for candidate in dropped)
    match = re.search(r"(?m)^📊", report_md or "")
    if match:
        restored = report_md[:match.start()].rstrip() + "\n\n" + additions + "\n\n" + report_md[match.start():].lstrip()
    else:
        restored = (report_md or "").rstrip() + "\n\n" + additions
    return normalize_report_statistics_line(normalize_final_report_md(restored)), dropped


def compact_report_line_for_pdf(line: str) -> str:
    line = normalize_source_line(line)
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    line = re.sub(
        r"\[(.+?)\]\((https?://[^\)]+)\)",
        lambda m: f"{m.group(1)}（{m.group(2)}）",
        line,
    )
    line = re.sub(r"https?://[^\s\)\]]+", lambda m: _extract_complete_url(m.group(0)) or m.group(0), line)
    return line


def display_report_markdown(md: str) -> str:
    display_md = compact_report_urls(md)
    return re.sub(r"(?m)^#\s+(.+)$", r"### \1", display_md, count=1)


def register_pdf_fonts() -> tuple[str, str]:
    """Register an embeddable CJK font first; fall back to ReportLab CID fonts only if needed."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    def _is_registered(font_name: str) -> bool:
        try:
            pdfmetrics.getFont(font_name)
            return True
        except Exception:
            return False

    def _register_ttf(font_name: str, paths: list[str]) -> str | None:
        if _is_registered(font_name):
            return font_name
        for path in paths:
            if not os.path.exists(path):
                continue
            try:
                pdfmetrics.registerFont(TTFont(font_name, path, subfontIndex=0))
                return font_name
            except Exception:
                try:
                    pdfmetrics.registerFont(TTFont(font_name, path))
                    return font_name
                except Exception:
                    continue
        return None

    def _register_cid_fallback() -> str:
        for font_name in ("MSung-Light", "STSong-Light", "HeiseiMin-W3"):
            try:
                if not _is_registered(font_name):
                    pdfmetrics.registerFont(UnicodeCIDFont(font_name))
                return font_name
            except Exception:
                continue
        return "Helvetica"

    cjk_font = _register_ttf("MetroReportCJK", [
        r"C:\Windows\Fonts\msjh.ttc",
        r"C:\Windows\Fonts\msjh.ttf",
        r"C:\Windows\Fonts\msjhl.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\mingliu.ttc",
        r"C:\Windows\Fonts\ArialUni.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansTC-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJKtc-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
    ])
    if not cjk_font:
        cjk_font = _register_cid_fallback()

    latin_font = _register_ttf("MetroReportLatin", [
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\timesbd.ttf",
        r"C:\Windows\Fonts\timesi.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ]) or cjk_font

    return cjk_font, latin_font


def pdf_rich_text(text: str, cjk_font: str, latin_font: str) -> str:
    safe = (
        (text or "")
        .replace("🔹", "◆")
        .replace("📊", "【統計】")
        .replace("⏰", "【時間】")
        .replace("🔍", "【搜尋】")
        .replace("🚇", "")
        .replace("📧", "")
    )
    return f'<font name="{cjk_font}">{escape(safe, quote=False)}</font>'


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
    bullet_count = len(re.findall(r"(?m)^🔹\s*\[(?:技術新知|重大事故|營運政策|營運爭議|規範更新)\]", report_md or ""))
    if bullet_count:
        return bullet_count
    count = 0
    for match in re.finditer(r"^###\s+(.+)$", report_md or "", flags=re.MULTILINE):
        heading = match.group(1)
        if any(category in heading for category in ADVANCED_TYPES):
            count += 1
    return count


def count_report_items_by_category(report_md: str) -> dict[str, int]:
    counts = {category: 0 for category in ADVANCED_TYPES}
    for match in re.finditer(r"(?m)^🔹\s*\[([^\]]+)\]", report_md or ""):
        category = match.group(1).strip()
        if category in counts:
            counts[category] += 1
    if any(counts.values()):
        return counts
    for match in re.finditer(r"^###\s+(.+)$", report_md or "", flags=re.MULTILINE):
        heading = match.group(1)
        for category in ADVANCED_TYPES:
            if category in heading:
                counts[category] += 1
                break
    return counts


def report_has_unselected_types(report_md: str) -> bool:
    unselected = [category for category in ADVANCED_TYPES if category not in selected_types]
    for category in unselected:
        if re.search(rf"(?m)^(##|###)\s+.*{re.escape(category)}", report_md):
            return True
    return False


def report_has_non_urban_formal_items(report_md: str) -> bool:
    formal_area = report_md.split("## 候補觀察", 1)[0]
    for block in re.split(r"(?m)^###\s+", formal_area)[1:]:
        if "[規範更新]" in block:
            continue
        if not _is_urban_rail_candidate(block):
            return True
    return False


def has_candidate_observations(report_md: str) -> bool:
    return "候補觀察" in report_md and not re.search(r"候補觀察[^\n]*\n\s*(?:無|本期無)", report_md)


def split_report_summary(report_md: str) -> tuple[str, str]:
    match = re.search(r"(?m)^##\s*報告摘要.*$", report_md)
    if not match:
        return report_md.strip(), ""
    main_report = report_md[:match.start()].strip()
    summary = report_md[match.end():].strip()
    summary = re.sub(r"(?m)^---\s*$", "", summary).strip()
    return main_report, summary


def trim_report_card_body(body: str) -> str:
    body = re.split(r"(?m)^##\s+", body, maxsplit=1)[0]
    body = re.sub(r"(?m)^---\s*$", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def render_report_cards(report_md: str) -> None:
    main_report, summary = split_report_summary(report_md)
    parts = re.split(r"(?m)^###\s+", main_report)
    if len(parts) <= 1:
        st.markdown(compact_report_urls(main_report))
        if summary:
            st.markdown(
                f"""
                <div class="section-title">報告摘要</div>
                <div class="report-summary-card">
                  <div class="report-card-body">{markdown_fragment_to_html(summary)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        return

    intro = parts[0].strip()
    if intro:
        st.markdown(compact_report_urls(intro))

    for part in parts[1:]:
        if not part.strip():
            continue
        lines = part.splitlines()
        heading = lines[0].strip()
        if re.sub(r"^[#\s]+", "", heading).strip().startswith(("報告摘要", "候補觀察")):
            continue
        body = trim_report_card_body("\n".join(lines[1:]).strip())
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

    if summary:
        st.markdown(
            f"""
            <div class="section-title">報告摘要</div>
            <div class="report-summary-card">
              <div class="report-card-body">{markdown_fragment_to_html(summary)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def markdown_to_pdf_bytes(md: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    cjk_font, latin_font = register_pdf_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    for style_name in ("Title", "Heading1", "Heading2", "Heading3", "BodyText"):
        styles[style_name].fontName = cjk_font
        styles[style_name].leading = max(styles[style_name].leading, 14)
        styles[style_name].wordWrap = "CJK"
        styles[style_name].splitLongWords = 1
    styles["BodyText"].fontSize = 10.2
    styles["BodyText"].leading = 15
    styles["Title"].fontSize = 15
    styles["Title"].leading = 20
    styles["Heading2"].fontSize = 12.5
    styles["Heading2"].leading = 17
    styles["Heading3"].fontSize = 11.2
    styles["Heading3"].leading = 16
    styles.add(ParagraphStyle(
        name="ReportBullet",
        parent=styles["BodyText"],
        leftIndent=14,
        firstLineIndent=-8,
        spaceBefore=1,
        spaceAfter=1,
        wordWrap="CJK",
        splitLongWords=1,
    ))

    story = []
    for raw_line in md.splitlines():
        line = raw_line.strip()
        if not line or line == "---":
            story.append(Spacer(1, 4))
            continue
        if line.startswith("# "):
            story.append(Paragraph(pdf_rich_text(line[2:], cjk_font, latin_font), styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(pdf_rich_text(line[3:], cjk_font, latin_font), styles["Heading2"]))
        elif line.startswith("### "):
            story.append(Paragraph(pdf_rich_text(line[4:], cjk_font, latin_font), styles["Heading3"]))
        elif line.startswith(("- ", "• ")):
            line = compact_report_line_for_pdf(line)
            story.append(Paragraph(pdf_rich_text(_soft_wrap_long_tokens(line, 48), cjk_font, latin_font), styles["ReportBullet"]))
        else:
            line = compact_report_line_for_pdf(line)
            story.append(Paragraph(pdf_rich_text(_soft_wrap_long_tokens(line, 56), cjk_font, latin_font), styles["BodyText"]))
    doc.build(story)
    return buffer.getvalue()


def _soft_wrap_long_tokens(text: str, chunk: int = 45) -> str:
    """在超長無空白字串（如 Google News 長網址）中每隔 chunk 字元插入零寬空白，
    讓 reportlab 能夠換行、不會爆出版面；零寬空白不影響複製貼上後的文字內容。"""
    words = text.split(" ")
    out = []
    for w in words:
        has_cjk = re.search(r"[\u3400-\u9fff]", w) is not None
        looks_like_url_or_ascii_token = re.search(r"https?://|[A-Za-z0-9]{24,}", w) is not None
        if len(w) > chunk and looks_like_url_or_ascii_token and not has_cjk:
            w = "\u200b".join(w[i:i + chunk] for i in range(0, len(w), chunk))
        out.append(w)
    return " ".join(out)


def try_markdown_to_pdf_bytes(md: str) -> bytes | None:
    try:
        return markdown_to_pdf_bytes(md)
    except Exception:
        return None


def _read_demo_debug_payload(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _builtin_demo_report_text() -> str:
    sections: list[str] = [
        f"# {report_title}",
        f"> 資料涵蓋期間：{date_range}",
        f"> 報導範圍：{report_scope_label}",
        "",
        "一、技術新知",
        "",
        "🔹 [技術新知] 展示用捷運機電監測案例",
        "",
        "• 發布/事件日期：日期未知",
        "",
        "• 國家/地區：展示資料",
        "",
        "• 相關機電系統：號誌、通訊、車輛、供電與維修監測",
        "",
        "• 事件摘要：",
        "本段為展覽快速版內建展示文字，用於現場快速呈現週報格式、PDF 下載與 Email 寄送流程。內容不代表即時搜尋結果，也未連線查詢新聞來源或呼叫 AI 服務。",
        "",
        "• 臺北捷運局啟示：",
        "展示模式可先確認輸出流程與畫面穩定性，正式測試時請取消展覽快速版。",
        "",
        "• 資料來源：展覽快速版預產展示資料，日期未知，未提供完整 URL",
        "",
        "________________________________________",
    ]
    if "規範更新" in selected_types:
        sections.extend([
            "",
            "五、規範更新",
            "本期未發現符合條件資料。",
        ])
    if include_research_supplement:
        sections.extend([
            "",
            research_section_heading(markdown=True),
            "本期未發現符合期間條件且具明確發表日期之國際學術或技術研究資料。",
        ])
    sections.extend([
        "",
        "📊 本期統計：共 1 則（技術新知 1 則）",
        f"⏰ 報告產出時間：{today.strftime('%Y年%m月%d日')}",
    ])
    return "\n".join(sections)


def load_demo_report_cache() -> tuple[str, bytes | None, dict]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    demo_md_path = REPORTS_DIR / "demo_report.md"
    demo_pdf_path = REPORTS_DIR / "demo_report.pdf"
    demo_debug_path = REPORTS_DIR / "demo_debug.json"
    debug_payload = _read_demo_debug_payload(demo_debug_path)
    source = "內建展示文字"

    if demo_md_path.exists():
        report_text = demo_md_path.read_text(encoding="utf-8")
        source = str(demo_md_path)
    else:
        report_text = str(debug_payload.get("final_report_md") or "").strip()
        if report_text:
            source = str(demo_debug_path)
        else:
            report_text = _builtin_demo_report_text()

    report_text = sanitize_report_text(report_text)
    report_text = enforce_research_section(report_text, [])
    report_text = normalize_final_report_md(report_text)
    report_text = apply_final_report_footer(report_text, [])

    if demo_pdf_path.exists():
        pdf_bytes = demo_pdf_path.read_bytes()
    else:
        pdf_bytes = try_markdown_to_pdf_bytes(report_text)

    return report_text, pdf_bytes, {
        "demo_source": source,
        "demo_markdown_path": str(demo_md_path),
        "demo_pdf_path": str(demo_pdf_path) if demo_pdf_path.exists() else "",
        "demo_debug_path": str(demo_debug_path) if demo_debug_path.exists() else "",
        "demo_debug_payload_found": bool(debug_payload),
    }


def send_email_func(text: str, recipients: list, gmail_user: str, gmail_pass: str) -> bool:
    msg = MIMEMultipart("alternative")
    email_run_config = st.session_state.get("latest_run_config", current_run_config)
    msg["Subject"] = email_run_config.get("report_title", report_title)
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
            filename=build_report_download_filename("metro_report", "pdf", email_run_config),
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


def send_current_report_email(report_md: str, status_target=None, progress_target=None) -> bool:
    recipients = [r.strip() for r in recipient_input.splitlines() if r.strip()]
    if not report_md:
        if status_target:
            status_target.warning("⚠️ 請先產生報告，再寄送 Email。")
        return False
    if not recipients:
        if status_target:
            status_target.warning("⚠️ 請在左側填入收件信箱")
        return False
    if not gmail_user or not gmail_pass:
        if status_target:
            status_target.warning("⚠️ GMAIL_USER 或 GMAIL_APP_PASS 未在 Secrets 中設定")
        return False
    if progress_target:
        progress_target.progress(0.95)
    if status_target:
        status_target.text("📧 正在寄送 Email 至公務信箱……")
    ok = send_email_func(report_md, recipients, gmail_user, gmail_pass)
    if ok:
        if progress_target:
            progress_target.progress(1.0)
        if status_target:
            status_target.success("✅ Email 已寄送完成。")
        st.success(f"📧 已成功寄送至：{', '.join(recipients)}")
    return ok


if generate_btn:
    if demo_cache_mode_enabled:
        run_config = current_run_config.copy()
        clear_old_report_state()
        st.session_state["latest_run_config"] = run_config
        st.session_state["report_generated"] = False
        st.session_state["email_sent"] = False
        progress_bar = progress_placeholder.progress(0.15)
        status_text = status_placeholder

        try:
            run_start = time.perf_counter()
            status_text.text("⚡ 展覽快速版載入預先產製展示報告……")
            report_text, pdf_bytes, demo_meta = load_demo_report_cache()
            progress_bar.progress(0.70)

            formal_count = count_report_items(report_text)
            category_counts = count_report_items_by_category(report_text)
            has_standard_updates = category_counts.get("規範更新", 0) > 0 or bool(
                re.search(r"(?m)^🔹\s*\[規範更新\]", report_text)
            )
            elapsed_total = round(time.perf_counter() - run_start, 2)
            source_statuses = [{
                "source_name": "展覽快速版預產報告",
                "method": "預產報告",
                "status": "skipped_demo_cache_mode",
                "item_count": 0,
                "error_message": "展覽快速版啟用，未執行 RSS、Google News、DDGS、MaiAgent、規範查詢或學術查詢",
                "fallback_used": False,
            }]
            source_health_summary = build_source_health_summary(source_statuses)
            report_stats = {
                "raw_count": 0,
                "deduped_count": 0,
                "filtered_count": 0,
                "ai_selected_count": 0,
                "formal_count": formal_count,
                "prompt_chars": 0,
                "raw_chars": len(report_text),
                "maiagent_call_count": 0,
                "category_counts": category_counts,
                "journal_count": 0,
                "model_candidate_count": 0,
                "source_count": 0,
                "ddgs_query_count": 0,
                "candidate_card_limit": 0,
                "candidate_card_count": 0,
                "elapsed_seconds_total": elapsed_total,
                "elapsed_seconds_rss": 0.0,
                "elapsed_seconds_ddgs": 0.0,
                "elapsed_seconds_candidate_pool": 0.0,
                "elapsed_seconds_journal": 0.0,
                "elapsed_seconds_selection": 0.0,
                "elapsed_seconds_python_selection": 0.0,
                "elapsed_seconds_report": 0.0,
                "elapsed_seconds_pdf": 0.0,
                "source_health_summary": source_health_summary,
                "selection_method": "demo_cache",
                "demo_cache_mode": True,
                "include_research_supplement": include_research_supplement,
                "research_supplement_period": run_config.get("research_supplement_period", {}),
                "run_config": run_config,
            }
            debug_info = {
                "run_config": run_config,
                "raw_candidates": [],
                "deduped_candidates": [],
                "filtered_candidates": [],
                "excluded_candidates": [],
                "model_candidates": [],
                "candidate_cards": [],
                "selected_candidates": [],
                "selected_ids": [],
                "enriched_selected_candidates": [],
                "journal_candidates": [],
                "journal_statuses": [],
                "journal_excluded_candidates": [],
                "selection_prompt": "",
                "selection_response": "",
                "selection_method": "demo_cache",
                "ai_selection_response": "",
                "python_unselected_stats": {},
                "report_prompt": "",
                "report_response": "",
                "latest_report_md": report_text,
                "ai_unselected_stats": {},
                "dedupe_stats": {},
                "exclusion_stats": {},
                "source_statuses": source_statuses,
                "source_health_summary": source_health_summary,
                "report_stats": report_stats,
                "long_term_coverage": {"long_term_coverage_warning": False, "reason": ""},
                "demo_meta": demo_meta,
            }
            st.session_state["latest_report_md"] = report_text
            st.session_state["latest_report"] = report_text
            st.session_state["latest_pdf"] = pdf_bytes
            st.session_state["latest_report_summary"] = {
                "formal_count": formal_count,
                "has_standards": has_standard_updates,
                "category_counts": category_counts,
            }
            st.session_state["latest_report_stats"] = report_stats
            st.session_state["latest_run_config"] = run_config
            st.session_state["report_generated"] = True
            st.session_state["latest_debug_info"] = debug_info
            st.session_state["latest_source_statuses"] = source_statuses
            st.session_state["latest_debug_payload"] = {
                "run_info": {
                    "demo_cache_mode": True,
                    "include_research_supplement": include_research_supplement,
                    "research_supplement_period": run_config.get("research_supplement_period", {}),
                },
                "stats": report_stats,
                "source_health": source_statuses,
                "source_health_summary": source_health_summary,
                "final_report_md": report_text,
            }

            email_note = "未自動寄送 Email"
            if send_after_generate:
                email_ok = send_current_report_email(
                    st.session_state["latest_report_md"],
                    status_target=status_text,
                    progress_target=progress_bar,
                )
                email_note = "Email 已寄送" if email_ok else "Email 未寄出，請檢查收件設定或 Secrets"
                st.session_state["email_sent"] = bool(email_ok)
            else:
                progress_bar.progress(0.95)

            progress_bar.progress(1.0)
            status_text.markdown(
                f"""
                <div class="notice-success">
                  <strong>✅ 展覽快速版報告已載入</strong><br>
                  此為預先產製展示報告，不是即時搜尋結果；本次未呼叫 MaiAgent。<br>
                  正式新聞：{formal_count} 則｜{email_note}。
                </div>
                """,
                unsafe_allow_html=True,
            )
        except Exception as e:
            progress_placeholder.empty()
            status_text.error(f"❌ 展覽快速版載入失敗：{e}")
    elif not maiagent_api_key:
        status_placeholder.error("❌ MaiAgent API Key 未設定，請至 Streamlit Cloud App Settings → Secrets 填入 MAIAGENT_API_KEY")
    elif not maiagent_chatbot_id:
        status_placeholder.error("❌ MaiAgent Chatbot ID 未設定，請至 Streamlit Cloud App Settings → Secrets 填入 MAIAGENT_CHATBOT_ID")
    elif not selected_types:
        status_placeholder.error("❌ 尚未勾選新聞類型，請至左側選單勾選想要搜尋的主題。")
    elif not is_global_scope and not active_regions:
        status_placeholder.error("❌ 指定先進國家/地區模式下，請至少勾選一個國家/地區。")
    else:
        run_config = current_run_config.copy()
        clear_old_report_state()
        st.session_state["latest_run_config"] = run_config
        st.session_state["report_generated"] = False
        st.session_state["email_sent"] = False
        progress_bar = progress_placeholder.progress(0.10)
        status_text = status_placeholder

        class ProgressRange:
            def __init__(self, progress_bar_obj, start: float, end: float):
                self.progress_bar_obj = progress_bar_obj
                self.start = start
                self.end = end

            def progress(self, value: float):
                value = max(0.0, min(1.0, float(value)))
                self.progress_bar_obj.progress(self.start + (self.end - self.start) * value)

        try:
            maiagent_call_count = 0
            run_start = time.perf_counter()
            timings = {
                "elapsed_seconds_total": 0.0,
                "elapsed_seconds_rss": 0.0,
                "elapsed_seconds_ddgs": 0.0,
                "elapsed_seconds_candidate_pool": 0.0,
                "elapsed_seconds_journal": 0.0,
                "elapsed_seconds_selection": 0.0,
                "elapsed_seconds_python_selection": 0.0,
                "elapsed_seconds_report": 0.0,
                "elapsed_seconds_pdf": 0.0,
            }

            # Step 1：RSS 訂閱源 + 指定模式地區代理 + 規範更新代理
            region_sources = build_region_news_sources(active_regions, int(lookback_days), fast_mode=fast_mode_enabled)
            standards_sources = build_standards_news_sources(int(lookback_days)) if standards_enabled else []
            combined_sources, skipped_source_statuses = build_run_news_sources(
                region_sources,
                standards_sources,
                fast_mode_enabled,
                return_skipped=True,
            )
            status_text.text(
                f"🔎 蒐集國際新聞來源……（共 {len(combined_sources)} 個來源）"
            )
            stage_start = time.perf_counter()
            rss_results, fetched_source_statuses = fetch_rss_feeds(
                combined_sources, status_text=status_text, return_status=True
            )
            source_statuses = skipped_source_statuses + fetched_source_statuses
            source_health_summary = build_source_health_summary(source_statuses)
            timings["elapsed_seconds_rss"] = round(time.perf_counter() - stage_start, 2)
            progress_bar.progress(0.25)
            st.session_state["latest_source_statuses"] = source_statuses

            status_text.text("🔍 蒐集國際新聞來源……（ddgs 多後端搜尋）")
            ddg_progress = ProgressRange(progress_bar, 0.25, 0.40)
            search_count = len(build_search_queries()[0])
            stage_start = time.perf_counter()
            ddg_results = run_duckduckgo_searches(ddg_progress, status_text)
            timings["elapsed_seconds_ddgs"] = round(time.perf_counter() - stage_start, 2)
            progress_bar.progress(0.42)

            status_text.text("🧹 整理候選資料，排除重複與不相關新聞……")
            stage_start = time.perf_counter()
            candidate_pool = prepare_candidate_pool(rss_results, ddg_results)
            timings["elapsed_seconds_candidate_pool"] = round(time.perf_counter() - stage_start, 2)
            model_candidates = candidate_pool["model_candidates"]
            long_term_coverage = build_long_term_coverage_warning(candidate_pool["filtered_candidates"])
            progress_bar.progress(0.52)

            status_text.text("🛡️ 排除舊聞與低品質來源……")
            time.sleep(0.1)
            progress_bar.progress(0.58)

            # Step 2：Python 規則選題
            status_text.text("🧮 Python 規則選題……")
            selection_prompt = ""
            selection_response = ""
            stage_start = time.perf_counter()
            selected_candidates = select_candidates_by_python(model_candidates)
            timings["elapsed_seconds_python_selection"] = round(time.perf_counter() - stage_start, 2)
            timings["elapsed_seconds_selection"] = timings["elapsed_seconds_python_selection"]
            selected_ids = [int(item.get("id", 0) or 0) for item in selected_candidates]
            python_unselected_stats = build_python_unselected_stats(model_candidates, selected_candidates)
            ai_unselected_stats = python_unselected_stats
            selected_long_term_coverage = build_long_term_coverage_warning(selected_candidates)
            if selected_long_term_coverage.get("long_term_coverage_warning"):
                long_term_coverage = selected_long_term_coverage
            progress_bar.progress(0.70)

            journal_candidates: list[dict] = []
            journal_statuses: list[dict] = []
            journal_excluded_candidates: list[dict] = []
            stage_start = time.perf_counter()
            if include_research_supplement:
                journal_candidates, journal_statuses, journal_excluded_candidates = collect_journal_candidates(status_text)
            timings["elapsed_seconds_journal"] = round(time.perf_counter() - stage_start, 2)
            progress_bar.progress(0.76)

            # Step 3：MaiAgent 第二階段正式報告
            status_text.text(f"📝 MaiAgent 產生正式{report_period_label}……")
            report_prompt = build_report_prompt(selected_candidates, journal_candidates, search_count)
            stage_start = time.perf_counter()
            report_response = call_maiagent_cloud(report_prompt)
            timings["elapsed_seconds_report"] = round(time.perf_counter() - stage_start, 2)
            maiagent_call_count += 1
            progress_bar.progress(0.88)

            status_text.text("📄 完成 PDF / Email 輸出準備……")
            pdf_stage_start = time.perf_counter()
            report_text = report_response
            report_text = sanitize_report_text(report_text)
            report_text = enforce_research_section(report_text, journal_candidates)
            report_text = ensure_journal_summary_conclusion(report_text, journal_candidates)
            report_text = normalize_final_report_md(report_text)
            report_text = repair_journal_dates_in_report(report_text, journal_candidates)
            report_text = normalize_journal_section_format(report_text, journal_candidates)
            report_text = insert_annual_observation_section(report_text, selected_candidates)
            report_text, dropped_selected_candidates = restore_missing_selected_report_items(report_text, selected_candidates)
            report_text = repair_report_region_lines(report_text, selected_candidates)
            report_text = repair_generic_report_titles(report_text, selected_candidates)
            report_text = normalize_journal_section_format(report_text, journal_candidates)
            report_text = apply_final_report_footer(report_text, journal_candidates)
            pdf_bytes = try_markdown_to_pdf_bytes(report_text)
            dropped_selected_ids = [int(item.get("id", 0) or 0) for item in dropped_selected_candidates]
            dropped_selected_titles = [item.get("title", "") for item in dropped_selected_candidates]
            dropped_selected_reasons = ["MaiAgent 未輸出該 Python 入選候選，已由後處理補回。" for _ in dropped_selected_candidates]
            formal_count = count_report_items(report_text)
            category_counts = count_report_items_by_category(report_text)
            has_standard_updates = category_counts.get("規範更新", 0) > 0 or bool(
                re.search(r"(?m)^🔹\s*\[規範更新\]", report_text)
            )
            prompt_chars = len(report_prompt)
            raw_chars = len(rss_results) + len(ddg_results)

            os.makedirs("reports", exist_ok=True)
            with open("reports/latest.md", "w", encoding="utf-8") as f:
                f.write(report_text)
            with open(f"reports/report_{today.strftime('%Y%m%d')}.md", "w", encoding="utf-8") as f:
                f.write(report_text)

            report_stats = {
                "raw_count": candidate_pool["raw_count"],
                "deduped_count": candidate_pool["deduped_count"],
                "filtered_count": candidate_pool["filtered_count"],
                "ai_selected_count": len(selected_candidates),
                "formal_count": formal_count,
                "prompt_chars": prompt_chars,
                "raw_chars": raw_chars,
                "maiagent_call_count": maiagent_call_count,
                "category_counts": category_counts,
                "journal_count": len(journal_candidates),
                "model_candidate_count": len(model_candidates),
                "source_count": len(combined_sources),
                "ddgs_query_count": search_count,
                "candidate_card_limit": candidate_pool.get("candidate_card_limit", len(candidate_pool["candidate_cards"])),
                "candidate_card_count": len(candidate_pool["candidate_cards"]),
                "elapsed_seconds_total": timings["elapsed_seconds_total"],
                "elapsed_seconds_rss": timings["elapsed_seconds_rss"],
                "elapsed_seconds_ddgs": timings["elapsed_seconds_ddgs"],
                "elapsed_seconds_candidate_pool": timings["elapsed_seconds_candidate_pool"],
                "elapsed_seconds_journal": timings["elapsed_seconds_journal"],
                "elapsed_seconds_selection": timings["elapsed_seconds_selection"],
                "elapsed_seconds_python_selection": timings["elapsed_seconds_python_selection"],
                "elapsed_seconds_report": timings["elapsed_seconds_report"],
                "elapsed_seconds_pdf": timings["elapsed_seconds_pdf"],
                "source_health_summary": source_health_summary,
                "dropped_selected_ids": dropped_selected_ids,
                "dropped_selected_titles": dropped_selected_titles,
                "dropped_selected_reasons": dropped_selected_reasons,
                "strict_selected_count": LAST_PYTHON_SELECTION_DEBUG.get("strict_selected_count", 0),
                "borderline_added_count": LAST_PYTHON_SELECTION_DEBUG.get("borderline_added_count", 0),
                "shortfall_before_backfill": LAST_PYTHON_SELECTION_DEBUG.get("shortfall_before_backfill", 0),
                "shortfall_after_backfill": LAST_PYTHON_SELECTION_DEBUG.get("shortfall_after_backfill", 0),
                "backfill_reason": LAST_PYTHON_SELECTION_DEBUG.get("backfill_reason", ""),
                "journal_target_count": get_journal_target_count(research_supplement_lookback_days)[0] if include_research_supplement else 0,
                "journal_selected_count": len(journal_candidates),
                "journal_exclusion_stats": _journal_exclusion_stats(journal_excluded_candidates),
                "journal_shortfall_reason": _journal_shortfall_reason(len(journal_candidates), get_journal_target_count(research_supplement_lookback_days)[0], journal_excluded_candidates) if include_research_supplement else "",
                "journal_summary_conclusion_chars": count_journal_summary_conclusion_chars(report_text),
                "selection_method": "python_score_rules",
                "long_term_coverage": long_term_coverage,
                "demo_cache_mode": False,
                "include_research_supplement": include_research_supplement,
                "research_supplement_period": run_config.get("research_supplement_period", {}),
                "run_config": run_config,
            }
            st.session_state["latest_report_md"] = report_text
            st.session_state["latest_report"] = report_text
            st.session_state["latest_pdf"] = pdf_bytes
            st.session_state["latest_report_summary"] = {
                "formal_count": formal_count,
                "has_standards": has_standard_updates,
                "category_counts": category_counts,
            }
            st.session_state["latest_report_stats"] = report_stats
            st.session_state["latest_run_config"] = run_config
            st.session_state["report_generated"] = True
            st.session_state["latest_debug_info"] = {
                "run_config": run_config,
                "raw_candidates": candidate_pool["raw_candidates"],
                "deduped_candidates": candidate_pool["deduped_candidates"],
                "filtered_candidates": candidate_pool["filtered_candidates"],
                "excluded_candidates": candidate_pool["excluded_candidates"],
                "model_candidates": model_candidates,
                "candidate_cards": candidate_pool["candidate_cards"],
                "selected_candidates": selected_candidates,
                "selected_ids": selected_ids,
                "enriched_selected_candidates": selected_candidates,
                "journal_candidates": journal_candidates,
                "journal_statuses": journal_statuses,
                "journal_excluded_candidates": journal_excluded_candidates,
                "journal_selected_candidates": journal_candidates,
                "journal_exclusion_stats": _journal_exclusion_stats(journal_excluded_candidates),
                "journal_source_statuses": journal_statuses,
                "journal_target_count": get_journal_target_count(research_supplement_lookback_days)[0] if include_research_supplement else 0,
                "journal_selected_count": len(journal_candidates),
                "journal_shortfall_reason": _journal_shortfall_reason(len(journal_candidates), get_journal_target_count(research_supplement_lookback_days)[0], journal_excluded_candidates) if include_research_supplement else "",
                "journal_summary_conclusion_chars": count_journal_summary_conclusion_chars(report_text),
                "selection_debug": LAST_PYTHON_SELECTION_DEBUG,
                "borderline_candidates": LAST_PYTHON_SELECTION_DEBUG.get("borderline_candidates", []),
                "duplicate_event_records": LAST_PYTHON_SELECTION_DEBUG.get("duplicate_event_records", []),
                "selection_prompt": selection_prompt,
                "selection_response": selection_response,
                "selection_method": "python_score_rules",
                "ai_selection_response": "",
                "python_unselected_stats": python_unselected_stats,
                "report_prompt": report_prompt,
                "report_response": report_response,
                "latest_report_md": report_text,
                "ai_unselected_stats": ai_unselected_stats,
                "dedupe_stats": candidate_pool["dedupe_stats"],
                "exclusion_stats": candidate_pool["exclusion_stats"],
                "source_statuses": source_statuses,
                "source_health_summary": source_health_summary,
                "dropped_selected_ids": dropped_selected_ids,
                "dropped_selected_titles": dropped_selected_titles,
                "dropped_selected_reasons": dropped_selected_reasons,
                "report_stats": report_stats,
                "long_term_coverage": long_term_coverage,
            }

            email_note = "未自動寄送 Email"
            if send_after_generate:
                email_ok = send_current_report_email(
                    st.session_state["latest_report_md"],
                    status_target=status_text,
                    progress_target=progress_bar,
                )
                email_note = "Email 已寄送" if email_ok else "Email 未寄出，請檢查收件設定或 Secrets"
                st.session_state["email_sent"] = bool(email_ok)
            else:
                progress_bar.progress(0.95)

            timings["elapsed_seconds_pdf"] = round(time.perf_counter() - pdf_stage_start, 2)
            timings["elapsed_seconds_total"] = round(time.perf_counter() - run_start, 2)
            report_stats.update(timings)
            st.session_state["latest_report_stats"] = report_stats
            st.session_state["latest_debug_info"]["report_stats"] = report_stats

            summary = st.session_state["latest_report_summary"]
            standards_note = (
                f"｜規範更新：{'包含' if summary['has_standards'] else '未包含'}"
                if standards_enabled
                else ""
            )
            progress_bar.progress(1.0)
            status_text.markdown(
                f"""
                <div class="notice-success">
                  <strong>✅ 報告已完成</strong><br>
                  可於下方查看正式{report_period_label}、下載 PDF 或手動寄送 Email。<br>
                  正式新聞：{formal_count} 則{standards_note}｜
                  {email_note}。
                </div>
                """,
                unsafe_allow_html=True,
            )

        except Exception as e:
            progress_placeholder.empty()
            status_text.error(f"❌ 發生錯誤：{e}")
            st.info("請確認 MaiAgent API Key、Chatbot ID 與 API Base 正確，且該雲端 API 可由目前執行環境連線。")

# ── 報告顯示區 ──────────────────────────────────────
st.markdown("---")
source_statuses = st.session_state.get("latest_source_statuses", [])
display_run_config = st.session_state.get("latest_run_config", current_run_config)
display_report_label = display_run_config.get("report_label", report_period_label)
report_matches_current_app = (
    not display_run_config.get("app_source_hash")
    or display_run_config.get("app_source_hash") == current_app_hash
)

st.markdown(f'<div class="section-title">正式{display_report_label}</div>', unsafe_allow_html=True)

report_stats = st.session_state.get("latest_report_stats", {})
latest_report_md = st.session_state.get("latest_report_md", "")
report_to_show = (latest_report_md or st.session_state.get("latest_report", "")) if report_matches_current_app else ""
if report_to_show and not latest_report_md:
    report_to_show = normalize_final_report_md(report_to_show)
    st.session_state["latest_report_md"] = report_to_show
    latest_report_md = report_to_show

if report_to_show:
    st.markdown(display_report_markdown(report_to_show))

    st.markdown('<div class="section-title">輸出與寄送</div>', unsafe_allow_html=True)
    pdf_source_md = st.session_state.get("latest_report_md", "")
    pdf_bytes = st.session_state.get("latest_pdf") or (try_markdown_to_pdf_bytes(pdf_source_md) if pdf_source_md else None)
    output_cols = st.columns(2)
    out1 = output_cols[0]
    out2 = output_cols[1]
    with out1:
        if pdf_bytes:
            st.download_button(
                f"📄 下載正式{display_report_label} PDF",
                data=pdf_bytes,
                file_name=build_report_download_filename("metro_report", "pdf", display_run_config),
                mime="application/octet-stream",
                use_container_width=True,
            )
        else:
            st.button(f"📄 下載正式{display_report_label} PDF", disabled=True, use_container_width=True)
            st.caption("請先產生本次報告；PDF 會使用 latest_report_md。")
    with out2:
        if latest_report_md:
            send_latest_btn = st.button("📧 寄送目前報告", use_container_width=True)
            if send_latest_btn:
                email_progress = progress_placeholder.progress(0.95)
                st.session_state["email_sent"] = bool(send_current_report_email(
                    st.session_state["latest_report_md"],
                    status_target=status_placeholder,
                    progress_target=email_progress,
                ))
        else:
            st.button("📧 寄送目前報告", disabled=True, use_container_width=True)
            st.caption("請先產生報告。")
else:
    if not report_matches_current_app and st.session_state.get("latest_report_md"):
        st.caption("程式已更新，上一版本報告已隱藏；請重新產生報告。")
    st.markdown(f"""
    <div class="warn-box">
    📭 尚無報告資料。請點擊上方「產生國際捷運 AI {report_period_label}」按鈕產生第一份報告。
    </div>""", unsafe_allow_html=True)

# ── 開發者除錯資訊 ───────────────────────────────────
def _debug_candidate_rows(items: list[dict]) -> list[dict]:
    rows = []
    for item in items or []:
        rows.append({
            "id": item.get("id", ""),
            "date": item.get("date", ""),
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "source_display": item.get("source_display", ""),
            "quality": item.get("source_quality", ""),
            "source_tier": item.get("source_tier", ""),
            "region": item.get("region", ""),
            "type": item.get("source_type", ""),
            "preliminary_type": item.get("preliminary_type", ""),
            "python_score": item.get("python_score", ""),
            "score_reason": item.get("score_reason", ""),
            "candidate_flags": ", ".join(item.get("candidate_flags", []) or []),
            "exclude_reason": item.get("exclude_reason", ""),
            "url": item.get("url", ""),
            "classification": item.get("classification", ""),
            "reason": item.get("selected_reason", ""),
        })
    return rows


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_developer_debug_payload(debug_info: dict, report_stats: dict, source_statuses: list[dict]) -> dict:
    latest_stats = debug_info.get("report_stats", report_stats or {}) if debug_info else (report_stats or {})
    run_config = (
        debug_info.get("run_config")
        or latest_stats.get("run_config")
        or st.session_state.get("latest_run_config")
        or current_run_config
    )
    long_term_coverage = debug_info.get("long_term_coverage") or latest_stats.get("long_term_coverage") or {}
    source_health = debug_info.get("source_statuses", source_statuses) if debug_info else (source_statuses or [])
    source_health_summary = (
        debug_info.get("source_health_summary")
        or latest_stats.get("source_health_summary")
        or build_source_health_summary(source_health)
    )
    return _json_safe({
        "run_info": {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "report_date": run_config.get("report_date"),
            "start_date": run_config.get("start_date"),
            "end_date": run_config.get("end_date"),
            "lookback_days": run_config.get("lookback_days"),
            "date_range": run_config.get("date_range"),
            "report_label": run_config.get("report_label"),
            "report_title": run_config.get("report_title"),
            "selected_types": run_config.get("selected_types", []),
            "selected_regions": run_config.get("selected_regions", []),
            "scope_mode": run_config.get("scope_mode"),
            "include_standards": run_config.get("include_standards"),
            "include_research_supplement": run_config.get("include_research_supplement"),
            "research_supplement_period": run_config.get("research_supplement_period", {}),
            "research_lookback_days": (run_config.get("research_supplement_period", {}) or {}).get("lookback_days"),
            "fast_mode": run_config.get("fast_mode", True),
            "demo_cache_mode": run_config.get("demo_cache_mode", False),
            "app_source_hash": st.session_state.get("_app_source_hash", ""),
            "selection_method": latest_stats.get("selection_method", debug_info.get("selection_method", "")),
            "long_term_coverage_warning": long_term_coverage.get("long_term_coverage_warning", False),
            "long_term_coverage_reason": long_term_coverage.get("reason", ""),
        },
        "stats": {
            "raw_count": latest_stats.get("raw_count", 0),
            "dedup_count": latest_stats.get("deduped_count", 0),
            "filtered_count": latest_stats.get("filtered_count", 0),
            "selected_count": latest_stats.get("ai_selected_count", 0),
            "final_report_count": latest_stats.get("formal_count", 0),
            "prompt_chars": latest_stats.get("prompt_chars", 0),
            "raw_chars": latest_stats.get("raw_chars", 0),
            "maiagent_calls": latest_stats.get("maiagent_call_count", 0),
            "category_counts": latest_stats.get("category_counts", {}),
            "journal_count": latest_stats.get("journal_count", 0),
            "source_count": latest_stats.get("source_count", 0),
            "ddgs_query_count": latest_stats.get("ddgs_query_count", 0),
            "candidate_card_limit": latest_stats.get("candidate_card_limit", 0),
            "candidate_card_count": latest_stats.get("candidate_card_count", 0),
            "elapsed_seconds_total": latest_stats.get("elapsed_seconds_total", 0),
            "elapsed_seconds_rss": latest_stats.get("elapsed_seconds_rss", 0),
            "elapsed_seconds_ddgs": latest_stats.get("elapsed_seconds_ddgs", 0),
            "elapsed_seconds_candidate_pool": latest_stats.get("elapsed_seconds_candidate_pool", 0),
            "elapsed_seconds_journal": latest_stats.get("elapsed_seconds_journal", 0),
            "elapsed_seconds_selection": latest_stats.get("elapsed_seconds_selection", 0),
            "elapsed_seconds_python_selection": latest_stats.get("elapsed_seconds_python_selection", 0),
            "elapsed_seconds_report": latest_stats.get("elapsed_seconds_report", 0),
            "elapsed_seconds_pdf": latest_stats.get("elapsed_seconds_pdf", 0),
            "source_health_summary": source_health_summary,
            "dropped_selected_ids": latest_stats.get("dropped_selected_ids", debug_info.get("dropped_selected_ids", [])),
            "dropped_selected_titles": latest_stats.get("dropped_selected_titles", debug_info.get("dropped_selected_titles", [])),
            "dropped_selected_reasons": latest_stats.get("dropped_selected_reasons", debug_info.get("dropped_selected_reasons", [])),
            "strict_selected_count": latest_stats.get("strict_selected_count", debug_info.get("selection_debug", {}).get("strict_selected_count", 0)),
            "borderline_added_count": latest_stats.get("borderline_added_count", debug_info.get("selection_debug", {}).get("borderline_added_count", 0)),
            "shortfall_before_backfill": latest_stats.get("shortfall_before_backfill", debug_info.get("selection_debug", {}).get("shortfall_before_backfill", 0)),
            "shortfall_after_backfill": latest_stats.get("shortfall_after_backfill", debug_info.get("selection_debug", {}).get("shortfall_after_backfill", 0)),
            "backfill_reason": latest_stats.get("backfill_reason", debug_info.get("selection_debug", {}).get("backfill_reason", "")),
            "journal_target_count": latest_stats.get("journal_target_count", debug_info.get("journal_target_count", 0)),
            "journal_selected_count": latest_stats.get("journal_selected_count", debug_info.get("journal_selected_count", 0)),
            "journal_shortfall_reason": latest_stats.get("journal_shortfall_reason", debug_info.get("journal_shortfall_reason", "")),
            "journal_summary_conclusion_chars": latest_stats.get("journal_summary_conclusion_chars", debug_info.get("journal_summary_conclusion_chars", 0)),
            "journal_exclusion_stats": latest_stats.get("journal_exclusion_stats", debug_info.get("journal_exclusion_stats", {})),
            "selection_method": latest_stats.get("selection_method", debug_info.get("selection_method", "")),
            "demo_cache_mode": latest_stats.get("demo_cache_mode", run_config.get("demo_cache_mode", False)),
            "include_research_supplement": latest_stats.get("include_research_supplement", run_config.get("include_research_supplement", False)),
            "research_supplement_period": latest_stats.get("research_supplement_period", run_config.get("research_supplement_period", {})),
            "research_lookback_days": (latest_stats.get("research_supplement_period", run_config.get("research_supplement_period", {})) or {}).get("lookback_days"),
        },
        "selection_method": latest_stats.get("selection_method", debug_info.get("selection_method", "")),
        "source_health_summary": source_health_summary,
        "source_health": source_health,
        "raw_candidates": debug_info.get("raw_candidates", []) if debug_info else [],
        "deduped_candidates": debug_info.get("deduped_candidates", []) if debug_info else [],
        "filtered_candidates": debug_info.get("filtered_candidates", []) if debug_info else [],
        "candidate_cards": debug_info.get("candidate_cards", []) if debug_info else [],
        "selected_candidates": debug_info.get("selected_candidates", []) if debug_info else [],
        "selected_ids": debug_info.get("selected_ids", []) if debug_info else [],
        "dropped_selected_ids": latest_stats.get("dropped_selected_ids", debug_info.get("dropped_selected_ids", [])),
        "dropped_selected_titles": latest_stats.get("dropped_selected_titles", debug_info.get("dropped_selected_titles", [])),
        "dropped_selected_reasons": latest_stats.get("dropped_selected_reasons", debug_info.get("dropped_selected_reasons", [])),
        "selection_debug": debug_info.get("selection_debug", {}) if debug_info else {},
        "borderline_candidates": debug_info.get("borderline_candidates", []) if debug_info else [],
        "duplicate_event_records": debug_info.get("duplicate_event_records", []) if debug_info else [],
        "enriched_selected_candidates": debug_info.get("enriched_selected_candidates", debug_info.get("selected_candidates", [])) if debug_info else [],
        "excluded_candidates": debug_info.get("excluded_candidates", []) if debug_info else [],
        "exclusion_stats": debug_info.get("exclusion_stats", {}) if debug_info else {},
        "dedupe_stats": debug_info.get("dedupe_stats", {}) if debug_info else {},
        "ai_unselected_stats": debug_info.get("ai_unselected_stats", {}) if debug_info else {},
        "python_unselected_stats": debug_info.get("python_unselected_stats", {}) if debug_info else {},
        "research_lookback_days": (run_config.get("research_supplement_period", {}) or {}).get("lookback_days"),
        "journal_candidates": debug_info.get("journal_candidates", []) if debug_info else [],
        "journal_selected_candidates": debug_info.get("journal_selected_candidates", debug_info.get("journal_candidates", [])) if debug_info else [],
        "journal_statuses": debug_info.get("journal_statuses", []) if debug_info else [],
        "journal_source_statuses": debug_info.get("journal_source_statuses", debug_info.get("journal_statuses", [])) if debug_info else [],
        "journal_excluded_candidates": debug_info.get("journal_excluded_candidates", []) if debug_info else [],
        "journal_exclusion_stats": debug_info.get("journal_exclusion_stats", {}) if debug_info else {},
        "journal_target_count": debug_info.get("journal_target_count", 0) if debug_info else 0,
        "journal_selected_count": debug_info.get("journal_selected_count", 0) if debug_info else 0,
        "journal_shortfall_reason": debug_info.get("journal_shortfall_reason", "") if debug_info else "",
        "journal_summary_conclusion_chars": debug_info.get("journal_summary_conclusion_chars", 0) if debug_info else 0,
        "maiagent": {
            "selection_prompt": debug_info.get("selection_prompt", "") if debug_info else "",
            "selection_response": debug_info.get("selection_response", "") if debug_info else "",
            "ai_selection_response": debug_info.get("ai_selection_response", "") if debug_info else "",
            "report_prompt": debug_info.get("report_prompt", "") if debug_info else "",
            "report_response": debug_info.get("report_response", "") if debug_info else "",
        },
        "selection_response": debug_info.get("selection_response", "") if debug_info else "",
        "ai_selection_response": debug_info.get("ai_selection_response", "") if debug_info else "",
        "report_prompt": debug_info.get("report_prompt", "") if debug_info else "",
        "report_response": debug_info.get("report_response", "") if debug_info else "",
        "final_report_md": debug_info.get("latest_report_md", st.session_state.get("latest_report_md", "")) if debug_info else st.session_state.get("latest_report_md", ""),
    })


debug_info = st.session_state.get("latest_debug_info", {})
if show_developer_info:
    if debug_info:
        debug_payload = build_developer_debug_payload(debug_info, report_stats, source_statuses)
        st.session_state["latest_debug_payload"] = debug_payload
    else:
        debug_payload = st.session_state.get("latest_debug_payload")

    if debug_payload:
        debug_json = json.dumps(debug_payload, ensure_ascii=False, indent=2)
        st.download_button(
            "下載 AI 校正資料 JSON",
            data=debug_json.encode("utf-8"),
            file_name=build_report_download_filename("developer_debug", "json", display_run_config),
            mime="application/json",
            use_container_width=True,
        )
    else:
        st.caption("請先產生報告，開發者 JSON 會在報告完成後提供下載。")
