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
  .compact-kpi-bar {
    background: #f8fafc;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 10px 14px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
    align-items: center;
    font-size: .9rem;
    margin: 12px 0 6px;
  }
  .compact-kpi-item {
    white-space: nowrap;
    color: #111827;
    font-weight: 700;
  }
  .compact-detail-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
  }
  .compact-detail-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 10px 12px;
  }
  .compact-detail-value {
    color: #111827;
    font-size: 1.08rem;
    font-weight: 800;
    line-height: 1.25;
  }
  .compact-detail-label {
    color: #334155;
    font-size: .84rem;
    font-weight: 700;
    margin-top: 3px;
  }
  .compact-detail-note {
    color: #64748b;
    font-size: .76rem;
    margin-top: 2px;
  }

  .workflow-card {
    background: #f8fbfd; border: 1px solid #dbe4ee; border-left: 4px solid var(--metro-blue-2);
    border-radius: 8px; padding: 14px; min-height: 112px;
  }
  .workflow-step { color: var(--gold); font-weight: 800; font-size: .82rem; }
  .workflow-title { color: var(--metro-blue); font-weight: 800; margin-top: 4px; }
  .workflow-desc { color: #475569; font-size: .84rem; margin-top: 4px; }
  .flow-summary {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-left: 4px solid var(--dorts-blue);
    border-radius: 8px;
    padding: 10px 14px;
    color: #374151;
    font-size: .9rem;
    font-weight: 700;
    margin: 8px 0 4px;
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
  .source-summary-card {
    background: #ffffff; border: 1px solid #dbe4ee; border-radius: 8px;
    padding: 13px 14px; min-height: 88px; box-shadow: 0 4px 14px rgba(15,45,74,.06);
  }
  .source-summary-num { font-size: 1.55rem; font-weight: 800; color: #12385b; line-height: 1.15; }
  .source-summary-label { font-size: .86rem; color: #334155; font-weight: 800; margin-top: 3px; }
  .source-summary-note { font-size: .76rem; color: #64748b; margin-top: 4px; }

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
  .kpi-card, .workflow-card, .source-summary-card {
    box-shadow: none !important;
    border: 1px solid #e5e7eb !important;
    background: #ffffff !important;
  }
  .kpi-card { padding: 14px !important; min-height: 102px !important; }
  .kpi-icon { color: var(--dorts-blue) !important; }
  .kpi-num { color: #111827 !important; font-size: 1.65rem !important; }
  .workflow-card { border-left: 2px solid var(--dorts-blue) !important; min-height: 96px !important; }
  .workflow-step { color: var(--dorts-blue) !important; }
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
  .type-badge, .status-badge {
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
    margin: .12rem 0 .08rem;
  }
  .sidebar-subtitle {
    font-size: .78rem;
    line-height: 1.45;
    color: #6b7280;
    margin: 0 0 .55rem;
  }
  [data-testid="stSidebar"] hr {
    margin: .28rem 0 !important;
  }
  [data-testid="stSidebar"] h3 {
    margin: .42rem 0 .12rem !important;
  }
  [data-testid="stSidebar"] [data-testid="stExpander"] {
    margin-bottom: .35rem !important;
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
    .kpi-card, .workflow-card { min-height: auto; }
  }
</style>
""", unsafe_allow_html=True)

# ── 日期與常數 ──────────────────────────────────────────────
today = datetime.date.today()

ADVANCED_TYPES = ["技術新知", "重大事故", "營運政策", "營運爭議", "規範更新"]
MIN_REPORT_ITEMS = 15
MAX_ITEMS_PER_SOURCE = 25
DDGS_MAX_RESULTS = 25
NORMAL_LOOKBACK_OPTIONS = [7, 14, 30]
ADVANCED_LOOKBACK_OPTIONS = [90, 180, 365]
REPORT_TARGET_BY_DAYS = {
    7: 15,
    14: 20,
    30: 25,
}
LONG_TERM_TARGET_LABELS = {
    90: "趨勢回顧",
    180: "半年回顧",
    365: "年度回顧",
}
REPORT_PERIOD_LABELS = {
    7: "週報",
    14: "雙周報",
    30: "月報",
    90: "季報",
    180: "半年回顧",
    365: "年度回顧",
}

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
    "高速鐵路", "高速铁路", "高鐵", "高铁", "新幹線", "新干线",
    "台鐵", "臺鐵", "台湾鉄路", "台灣鐵路", "在来線", "特急",
    "貨運", "貨物列車", "客運鐵路", "城際鐵路", "區域鐵路", "通勤鐵路",
    "公路", "高速公路", "長途巴士", "客運",
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

TECH_NEWS_REQUIRED_TERMS = [
    "cbtc", "goa4", "driverless", "unattended train operation", "automatic train operation",
    "automation", "automated", "train control", "signalling", "signaling", "signal system",
    "rolling stock", "fleet", "new train", "trainset", "vehicle", "platform screen door",
    "platform doors", "psd", "power supply", "traction power", "substation", "third rail",
    "overhead line", "communications", "telecom", "4g", "5g", "lte", "radio", "cybersecurity",
    "data", "monitoring", "condition monitoring", "real-time", "digital", "asset management",
    "depot", "maintenance", "workshop", "afc", "fare gate", "ticketing", "elevator",
    "escalator", "system integration", "testing", "commissioning", "trial run",
    "自動運転", "無人運転", "ワンマン運転", "信号", "ホームドア", "車両", "電力",
    "変電所", "通信", "保守", "検査", "試験", "システム",
    "自動駕駛", "無人駕駛", "單人駕駛", "號誌", "信號", "月臺門", "月台門",
    "車輛", "列車", "供電", "牽引", "變電站", "通訊", "資安", "即時監控",
    "維修", "機廠", "測試", "試運轉", "系統整合",
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
        st.session_state["selected_types_state"] = ADVANCED_TYPES.copy()
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
        st.info("長期回顧適合趨勢分析、事故彙整與規範更新追蹤；不建議作為一般新聞週報使用，系統將提高去重與來源審查標準。")

    selected_types = []
    selected_target = REPORT_TARGET_BY_DAYS.get(int(lookback_days))
    target_summary = f"目標至少 {selected_target} 則" if selected_target else LONG_TERM_TARGET_LABELS.get(int(lookback_days), "趨勢回顧")
    selected_type_count = sum(
        1 for t in ADVANCED_TYPES
        if st.session_state.get(f"type_{t}", t in st.session_state["selected_types_state"])
    )
    st.markdown("**新聞類型**")
    st.caption(f"已選 {selected_type_count} 種類型｜{target_summary}")
    with st.expander("展開選擇新聞類型", expanded=False):
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

        for t in ADVANCED_TYPES:
            checked = t in st.session_state["selected_types_state"]
            if st.checkbox(t, value=checked, key=f"type_{t}"):
                selected_types.append(t)

    st.session_state["selected_types_state"] = selected_types
    if not selected_types:
        st.warning("⚠️ 請至少選擇一種新聞類型。")

    standards_enabled = "規範更新" in selected_types
    standard_count = sum(len(v) for v in STANDARDS_WATCHLIST.values())
    if standards_enabled:
        st.caption(f"📚 規範追蹤：已啟用，{standard_count} 項標準")
        with st.expander("查看規範追蹤清單", expanded=False):
            for category, standards in STANDARDS_WATCHLIST.items():
                st.markdown(f"**{category}**：{', '.join(standards)}")

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

    selected_regions = []
    if scope_mode == "全球（安全白名單來源）":
        selected_regions = st.session_state["selected_regions_state"]
        st.caption("報導範圍：全球模式")
    else:
        st.caption(f"已選 {len(st.session_state['selected_regions_state'])} / {len(ADVANCED_REGIONS)} 個國家")

    with st.expander("展開選擇國家", expanded=False):
        col_all, col_clear = st.columns(2)
        if col_all.button("全選國家", use_container_width=True, key="select_all_regions"):
            st.session_state["selected_regions_state"] = ADVANCED_REGIONS.copy()
            for region in ADVANCED_REGIONS:
                st.session_state[f"region_{region}"] = True
            st.rerun()

        if col_clear.button("清除全選", use_container_width=True, key="clear_all_regions"):
            st.session_state["selected_regions_state"] = []
            for region in ADVANCED_REGIONS:
                st.session_state[f"region_{region}"] = False
            st.rerun()

        region_cols = st.columns(2)
        for idx, region in enumerate(ADVANCED_REGIONS):
            checked = region in st.session_state["selected_regions_state"]
            if region_cols[idx % 2].checkbox(region, value=checked, key=f"region_{region}"):
                selected_regions.append(region)

    st.session_state["selected_regions_state"] = selected_regions
    if scope_mode != "全球（安全白名單來源）" and not selected_regions:
        st.warning("請至少選擇一個國家/地區。")

    with st.expander("⚙️ 進階設定", expanded=False):
        st.markdown("**AI 模型設定**")
        st.caption("目前使用：MaiAgent 雲端 API")

        st.markdown("**長期趨勢 / 規範追蹤模式**")
        long_term_mode = st.checkbox(
            "啟用長期趨勢 / 規範追蹤模式",
            key="long_term_mode",
            help="啟用後，報告期間可選 90、180、365 天。",
        )
        if not standards_enabled:
            st.caption("規範更新未勾選；目前僅執行一般新聞追蹤。")

        st.markdown("**排程說明**")
        st.caption("每週一 08:00｜GitHub Actions｜自動寄送")

        st.markdown("**系統狀態**")
        st.markdown(f"MaiAgent API Key：{'✅' if maiagent_api_key else '❌'}")
        st.markdown(f"MaiAgent Chatbot ID：{'✅' if maiagent_chatbot_id else '❌'}")
        st.markdown(f"MaiAgent API Base：{maiagent_api_base}")
        st.markdown(f"Gmail 帳號：{'✅' if gmail_user else '❌'}")
        st.markdown(f"Gmail 密碼：{'✅' if gmail_pass else '❌'}")
        st.markdown(f"ddgs 套件：{'✅' if DDGS else '❌'}")
        st.markdown(f"feedparser 套件：{'✅' if feedparser else '❌'}")

        st.markdown("**原始資料除錯模式**")
        show_raw_debug = st.checkbox(
            "在網頁顯示原始資料",
            value=False,
            help="只控制網頁下方是否展開 raw 文字；原始資料 PDF 仍會在產生報告後提供下載。",
        )

    st.caption("🏛️ 台北市政府捷運工程局\nAI 競賽展示系統")

week_start = today - datetime.timedelta(days=int(lookback_days))
date_range = f"{week_start.strftime('%Y年%m月%d日')} 至 {today.strftime('%Y年%m月%d日')}"
lookback_int = int(lookback_days)
report_period_label = REPORT_PERIOD_LABELS.get(lookback_int, "週報")
target_is_enforced = lookback_int in REPORT_TARGET_BY_DAYS
min_report_items = REPORT_TARGET_BY_DAYS.get(lookback_int, 0)
report_target_display = f"至少 {min_report_items} 則" if target_is_enforced else LONG_TERM_TARGET_LABELS.get(lookback_int, "趨勢回顧")
report_output_requirement = f"正式報告至少 {min_report_items} 則" if target_is_enforced else f"{report_target_display}，不強制篇數"
report_quantity_instruction = (
    f"本期為 {report_period_label}，正式報告目標至少 {min_report_items} 則。"
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
         f"請以趨勢分析、事故彙整、真正規範更新、來源品質與去重為優先；"
         f"不得為了增加篇數納入低關聯、重複、非都市軌道或來源不合格新聞。"
         f"規範追蹤清單、持續追蹤中、無單一新聞連結的標準項目，"
         f"不得列入正式規範更新，也不得計入正式新聞數。"
         f"若有效候選有限，請在報告摘要說明原因。"
)
report_shortfall_summary_line = (
    f"**不足 {min_report_items} 則原因**：（僅正式新聞少於 {min_report_items} 則時輸出；若達標，整行不要出現）"
    if target_is_enforced
    else "**長期回顧說明**：（簡述本期趨勢、去重後有效候選品質與來源限制）"
)
selected_report_topic = "、".join(selected_types) if selected_types else "技術趨勢"
report_title = f"【{today.strftime('%Y/%m/%d')}】國際捷運{selected_report_topic}{report_period_label}"
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


def build_region_news_sources(regions: list[str], days: int) -> list[tuple[str, str]]:
    """依勾選國家動態組出 Google News 地區代理 RSS 來源清單。"""
    sources: list[tuple[str, str]] = []
    days = max(1, min(int(days), 365))
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
    days = max(1, min(int(days), 365))
    update_terms = " OR ".join(f'"{term}"' for term in STANDARD_UPDATE_TERMS)
    for category, standards in STANDARDS_WATCHLIST.items():
        for standard in standards:
            query = f'"{standard}" ({update_terms}) when:{days}d'
            sources.append((f"規範更新代理－{category}－{standard}", google_news_search_url(query)))
    return sources


def render_main_dashboard(source_count: int, standards_count: int):
    selected_regions_note = "全球模式" if is_global_scope else f"{len(selected_regions)} / {len(ADVANCED_REGIONS)}"
    st.markdown(
        f"""
        <div class="hero-card">
          <div class="hero-eyebrow">臺北市政府捷運工程局｜機電系統設計處</div>
          <div class="hero-title">國際捷運技術{report_period_label} AI 自動產生系統</div>
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

    st.markdown('<div class="section-title">報告產出</div>', unsafe_allow_html=True)
    generate_clicked = st.button(f"🚀 產生國際捷運 AI {report_period_label}", type="primary", use_container_width=True)
    progress_placeholder = st.empty()
    status_placeholder = st.empty()

    kpi_items = [
        ("📑", len(selected_types), "追蹤主題數", "固定依報告排序輸出"),
        ("🌏", selected_regions_note, "預設/選取國家數", "指定模式套用國家邊界"),
        ("🗓️", f"{lookback_days} 天", f"新聞搜尋期間（{report_period_label}）", date_range),
        ("📡", source_count, "RSS/代理來源數", "含官方與 Google News 代理"),
        ("🎯", report_target_display, "AI 報告目標", f"{report_period_label}輸出模式"),
        ("📚", standards_count if standards_enabled else "未啟用", "規範追蹤數量", "勾選規範更新後啟用"),
    ]
    compact_standards = f"規範 {standards_count} 項" if standards_enabled else "規範 未啟用"
    compact_kpi_items = [
        f"📑 追蹤 {len(selected_types)} 類型",
        f"🌏 {selected_regions_note} 國家" if not is_global_scope else "🌏 全球模式",
        f"🗓️ {lookback_days} 天{report_period_label}",
        f"📡 {source_count} 來源",
        f"🎯 {report_target_display}",
        f"📚 {compact_standards}",
    ]
    st.markdown(
        "<div class=\"compact-kpi-bar\">"
        + "".join(f"<span class=\"compact-kpi-item\">{escape(str(item))}</span>" for item in compact_kpi_items)
        + "</div>",
        unsafe_allow_html=True,
    )

    with st.expander("查看詳細關鍵指標", expanded=False):
        detail_cols = st.columns(3)
        for idx, (icon, num, label, note) in enumerate(kpi_items):
            detail_cols[idx % 3].markdown(
                f'<div class="compact-detail-card">'
                f'<div class="compact-detail-value">{escape(str(icon))} {escape(str(num))}</div>'
                f'<div class="compact-detail-label">{escape(str(label))}</div>'
                f'<div class="compact-detail-note">{escape(str(note))}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    workflow_items = [
        ("01", "蒐集候選資料", "RSS / Google News / ddgs"),
        ("02", "安全與連結過濾", "排除高風險來源與無效 URL"),
        ("03", "AI 分類與摘要", "依固定類型排序與去重"),
        ("04", "形成機設處啟示", "可能影響系統、可參考作法、追蹤建議"),
        ("05", "輸出與寄送", "下載 PDF 或寄送公務信箱"),
    ]
    st.markdown(
        '<div class="flow-summary">蒐集候選資料 → 安全與連結過濾 → AI 分類與摘要 → 形成機設處啟示 → 輸出與寄送</div>',
        unsafe_allow_html=True,
    )
    with st.expander("查看系統流程", expanded=False):
        wcols = st.columns(5)
        for idx, (step, title, desc) in enumerate(workflow_items):
            wcols[idx].markdown(
                f'<div class="workflow-card">'
                f'<div class="workflow-step">STEP {escape(step)}</div>'
                f'<div class="workflow-title">{escape(title)}</div>'
                f'<div class="workflow-desc">{escape(desc)}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    return generate_clicked, progress_placeholder, status_placeholder


initial_region_sources = build_region_news_sources(active_regions, int(lookback_days))
initial_standard_sources = build_standards_news_sources(int(lookback_days)) if standards_enabled else []
generate_btn, progress_placeholder, status_placeholder = render_main_dashboard(
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
        - datetime.timedelta(days=max(1, min(int(lookback_days), 365)))
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
                            _status_record(source_name, "Google News fallback", "fallback 成功", min(len(items_found), MAX_ITEMS_PER_SOURCE), f"官方 RSS 失敗：{exc.message}")
                        )
                    else:
                        status = "非都市軌道" if topic_filtered_count and not (invalid_count or blocked_count) else "被安全規則排除" if blocked_count and not invalid_count else "無文章"
                        message = f"官方 RSS 失敗：{exc.message}；fallback 無有效候選；非都市軌道 {topic_filtered_count}、無效連結 {invalid_count}、安全排除 {blocked_count}、重複 {duplicate_count}"
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


# ── Prompt 建立 ───────────────────────────────────────
def build_prompt(rss_results: str, ddg_results: str, rss_sources: list[tuple[str, str]] | None = None) -> str:
    if rss_sources is None:
        rss_sources = RSS_SOURCES
    weekday = ['一','二','三','四','五','六','日'][today.weekday()]
    search_count = len(build_search_queries()[0])
    selected_types_str = "、".join(selected_types) if selected_types else "無"
    report_order = "、".join(ADVANCED_TYPES)
    selected_section_headings = "\n".join(f"## {t}" for t in ADVANCED_TYPES if t in selected_types)
    allowed_heading_options = "/".join(t for t in ADVANCED_TYPES if t in selected_types)
    source_names = "\n".join("   - " + name for name, _ in rss_sources)
    if is_global_scope:
        scope_instruction = (
            "本次採全球模式：不得用國家/地區清單刪除新聞。仍須套用來源安全規則、有效 URL 規則，"
            "並嚴格聚焦都市捷運、地下鐵、中運量、輕軌、AGT、LRRT/LRT。"
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

1. 「規範更新」只可列入本期確實發生之標準版本、草案、修訂、勘誤、撤回、取代、公告或公開徵詢事件。
2. 每一則規範更新必須同時具備以下四項：
   - 明確標準編號，例如 EN 50126、NFPA 130、IEC 60076。
   - 明確更新動作，例如 new edition、revision、amendment、corrigendum、draft、public comment、published、withdrawn、superseded。
   - 明確日期，且日期必須落在本期搜尋期間內。
   - 可查證的完整來源 URL。
3. 不可重製、翻譯或摘要標準全文，只能整理公開的版本狀態、公告摘要與可能影響。
4. 僅出現標準編號、標準名稱、官方首頁、標準體系網站、catalog、webstore，或僅屬「持續追蹤中」者，不得列入正式規範更新。
5. 不得把 STANDARDS_WATCHLIST 追蹤清單改寫成規範更新新聞。
6. 不得輸出「持續追蹤中」作為正式規範更新。
7. 不得輸出「此為標準體系公告，無單一新聞連結」作為正式規範更新。
8. 規範追蹤清單只能作為系統監測範圍，不得列入正式新聞數量統計。
9. 若本期沒有符合條件的規範更新，請在「規範更新」章節只寫：
   「本期未發現符合條件之規範版本更新、修訂草案、公告或徵詢事件。」
10. 關鍵字範圍包含：{", ".join(STANDARD_UPDATE_TERMS)}。

每則真正規範更新請使用固定格式：
### [規範更新] 標準編號：主題
- **更新狀態**：
- **涉及風險類別**：
- **可能影響機電系統**：
- **對捷運機電規劃/規範之啟示**：
- **資料來源**：[來源名稱](完整 https:// URL)
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
   - **技術新知**：只收「新聞本身」明確描述都會軌道機電/系統技術、測試、導入或維修方法者，例如車輛、號誌/CBTC/GoA4、通訊、供電、月臺門、AFC/閘門、機廠設備、即時監控、資安、系統整合、試運轉與技術驗證。單純路線規劃、預算、人事、開幕預覽、服務調整、事故、罷工、行銷列車、禁止規定、害蟲防治、公車/電動巴士採購、一般工程進度或沒有技術細節的擴建消息，均不得列為技術新知。
   - **重大事故**：出軌、追撞、火災、嚴重系統當機。
   - **營運政策**：捷運站內安檢新規、乘車規則變動（如禁帶大型鋰電池/滑板車）、安全管理政策。
   - **營運爭議**：罷工、預算超支、票價爭議、合約糾紛、服務品質爭議。
   - **規範更新**：僅限本期確實發生且原始資料可查證的標準版本、修訂、勘誤、草案、徵詢、公告、撤回、取代等公開狀態；單純標準追蹤清單、官方首頁、catalog/webstore 或「持續追蹤中」不得列入。
2. **最高優先級（只收都會軌道，不以一般鐵路湊數）**：
   - 正式新聞必須直接屬於都市軌道系統：Metro / Subway / Underground / MRT / Metrorail、LRRT / LRT / Light Rail / Tram / Tramway / Streetcar、AGT / Automated Guideway Transit / People Mover、都市單軌或其他明確城市大眾捷運系統。
   - 只有「事件本身」發生於上述系統，或新聞明確寫出技術/設備將用於上述系統時，才可列為正式新聞。不能因為 ETCS、FRMCS、GSM-R、CBTC、車輛、供電、維修、AI、資產管理等技術「理論上可參考」就列入正式新聞。
   - 明確排除正式新聞：高速鐵路/HSR/Shinkansen/新幹線/高鐵、台鐵/臺鐵/TRA/JR一般鐵路、城際鐵路、區域鐵路、通勤鐵路、國鐵/主線鐵路、貨運鐵路、機車/客車、長途公路運輸、公車/客運/coach/highway/BRT，以及只談一般鐵路供應鏈或國家鐵路政策的新聞。
   - London Underground、Tokyo Metro、Seoul Metro、MTR、LTA MRT/LRT、WMATA Metrorail、TTC subway/streetcar、Vancouver SkyTrain、RATP metro/tram、Madrid/Barcelona Metro 等官方都市軌道系統可優先；但同一機構若新聞主體是公車、長途鐵路或一般通勤鐵路，仍不得列入正式新聞。
   - 高鐵、主線鐵路或公車新聞最多只能在「候補觀察」中一行點出，而且必須說明「非都市軌道，僅作背景追蹤」；不得計入正式新聞數。
3. **來源權重**：請優先採納「第一部分：RSS 訂閱源」中實際出現的來源（本次共 {len(rss_sources)} 個，清單如下），這些是本次真正抓取到的媒體，**不要**引用或想像清單以外的媒體名稱：
{source_names}
4. **報告排序固定**：正式報告必須依序輸出已勾選類型，順序參照：{report_order}。**未勾選的類型絕對不得出現在章節標題、每則標題、正式新聞、統計或結尾文字**。若只勾選「技術新知」，整份報告只能有「技術新知」類新聞；遇到事故、政策、爭議、勞資、人事、開幕活動、行銷、一般路線規劃或非都市軌道新聞，必須剔除，不得改寫成技術新知。
5. **【絕對禁止腦補、嚴格日期查核與來源查核】（違反本條視為報告失敗）**：
   - 每一則新聞的「發布/事件日期」**必須**直接取自原始資料中該則內容本身標註的日期字串（RSS 的「日期：」欄位，或關鍵字搜尋結果摘要中出現的日期）。**禁止**依你自己知識庫中對該事件、公司或專案的既有印象去推測、換算或臆造日期。
   - 若某則原始資料**沒有**明確可辨識的日期，或日期含糊到無法判斷是哪一天，**直接捨棄該則**，不要用「近期」「今年」等模糊字眼帶過，也不要自行補上一個日期。
   - 判斷「未來日期」時，**只看該則報導本身的發布/刊登日期**是否晚於今天（{today.strftime('%Y-%m-%d')}）；若是，才視為不合理並剔除。**但**如果報導本身發布日期是合理的過去/現在日期，只是內文「引述」了某項政策的未來生效日（例如報導於 6 月底刊出，內容提到「規定將於 7 月 1 日起實施」），這屬於政策內容的一部分，**不可**僅因內文出現未來日期就整則剔除——請保留該則，並在內容中如實寫出「即將於某日起生效」。
   - 若同一事件在原始資料中找不到，但你「記得」曾經發生過類似新聞，**一律視為未提供資料**，不要用記憶內容補寫。你只能整理「第一部分」與「第二部分」中實際出現的文字，不能新增任何未出現於原始資料的事實、數字或日期。
   - 若原始資料只有標題，事件摘要只能重述標題可確認的事實；不得自行補上「旨在提升效率、改善乘客體驗、提升容量、降低成本」等目的、成效、數字或技術細節。這類推論若必要，只能放在「臺北捷運局啟示」並明確寫成建議，不可當作新聞事實。
   - **來源必須是該則事件本身的具體新聞文章連結**：「資料來源」欄位填入的網址，**必須**是原始資料中該則內容自己標註的「連結：」網址，且該網址指向的必須是報導這件事本身的新聞文章頁面。**嚴禁**引用網站首頁、路網圖、票務頁面、會員名錄、活動總覽頁等非新聞頁面來充當來源，也**嚴禁**在原始資料中找不到對應連結時，挪用同一媒體其他頁面的網址頂替。若某則事件在原始資料中沒有對應的具體文章連結，即使內容看起來合理，也必須**整則捨棄**。
   - Google News RSS 的 `news.google.com/rss/articles/...` 連結若搭配原始資料中的「原始來源」或標題來源，可視為可追查來源連結；不要僅因其為 Google News 轉址而剔除。
    - 不得為了湊數引用無具體新聞頁、首頁、社群頁、會員頁、活動首頁或模型記憶。
6. **數量要求**：{report_quantity_instruction}
7. **國家/地區規則**：{scope_instruction}
8. **內部國際新聞邊界**：台灣、臺灣、Taiwan、Taipei、台北/臺北捷運、北捷、新北、桃園/桃捷、台中、台南、高雄/高捷等國內新聞或國內案例，不得列入正式新聞或候補觀察。這是內部篩選條件，報告中不得呈現本條內容或其原因。

## 國家/地區範圍
{scope_list}

{standards_instruction}

## 輸出格式（每則獨立區塊，{report_output_requirement}）

# {report_title}
> 資料涵蓋期間：{date_range} 
> 篩選類型：{selected_types_str}
> 報導範圍：{scope_mode}

---

{selected_section_headings}

### [填入該則所屬之分類：{allowed_heading_options}] 國家/地區或標準編號：（一句有力主標題）
* **發布/事件日期**：（原文發布年月日）
* **國家/地區**：（全球模式仍需標示；規範更新可填公告機構/標準體系）
* **相關機電系統**：車輛/號誌/通訊/供電/月臺門/機廠設備/系統整合/資安/土建界面
* **事件摘要**：
  - （列點精要說明，3–5 點）
* **資料來源**：[來源名稱](完整 https:// 網址)
* **【臺北捷運局啟示】**
  - **可能影響系統**：
  - **可參考作法**：
  - **後續追蹤建議**：

---

## 報告摘要（必填）
---
**本週統計**：共 N 則 
{report_shortfall_summary_line}
**報告產出時間**：{today.strftime('%Y年%m月%d日')} 週{weekday}
"""


def build_revision_prompt(
    rss_results: str,
    ddg_results: str,
    previous_report: str,
    previous_count: int,
    rss_sources: list[tuple[str, str]] | None = None,
) -> str:
    allowed_types = "、".join(selected_types)
    return f"""
{build_prompt(rss_results, ddg_results, rss_sources)}

# 上一版報告需要修正
上一版正式新聞只有 {previous_count} 則，或混入未勾選分類，未符合本期 {report_period_label} 目標。

## 必須修正
1. 請重寫「完整報告」，不是只補充差額。
2. 本次只允許下列分類：{allowed_types}。
3. 未勾選分類不得出現在章節、標題、正文與統計。
4. {report_quantity_instruction}
5. 僅能使用 raw RSS/ddgs 候選資料，不得補腦。
6. 正式新聞只允許都市捷運/MRT/metro/subway/LRRT/LRT/light rail/tram/AGT/people mover；高鐵、新幹線、台鐵/國鐵、城際/區域/通勤鐵路、貨運鐵路、公車/客運/長途公路運輸不得用來補足正式新聞數。
7. 若上一版曾納入 ETCS/FRMCS/GSM-R、電池列車、混合動力列車、一般鐵路資產管理、主線事故、bus strike 等非都市軌道題材，請移除正式新聞；除非 raw 明確寫出該事件發生在 metro/subway/light rail/tram 等都市軌道系統。
8. 若本次只允許「技術新知」，請移除事故、政策、爭議、勞資、人事、開幕活動、行銷、一般路線規劃、害蟲防治、公車/電動巴士採購，以及未具體描述機電/系統技術的工程進度。
9. 不要輸出「信心水準」「納入理由」「技術/政策關鍵字」「候補觀察」「執行搜尋次數」等內部稽核欄位。

## 上一版報告
{previous_report}
"""


def extract_text(response) -> str:
    # 保留原本 Gemini 解析函式，避免其他舊流程引用時發生錯誤。
    if response.text:
        return response.text
    candidates = response.candidates or []
    if candidates and candidates[0].content and candidates[0].content.parts:
        texts = [p.text for p in candidates[0].content.parts if getattr(p, "text", None)]
        if texts:
            return "\n".join(texts)
    raise ValueError("Gemini 回應無文字內容")


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
    endpoint = f"{base_url}/api/v1/chatbots/{maiagent_chatbot_id}/completions"
    headers = {
        "Authorization": f"Api-Key {maiagent_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payloads = [
        {"message": {"content": prompt}, "isStreaming": False},
        {"message": {"content": prompt}, "is_streaming": False},
    ]
    endpoints = [endpoint, endpoint + "/"]
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
        return "來源連結（Google News）"
    return f"來源連結（{host}）"


def compact_report_urls(text: str) -> str:
    """正式報告只顯示短連結文字；完整 URL 保留在 raw debug。"""
    placeholders: list[str] = []

    def _replace_markdown_link(match: re.Match) -> str:
        label, url = match.group(1), match.group(2)
        if len(url) < 72 and "news.google.com" not in url:
            replacement = match.group(0)
        else:
            replacement = f"[{label or short_url_label(url)}]({url})"
        placeholders.append(replacement)
        return f"__REPORT_LINK_{len(placeholders) - 1}__"

    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", _replace_markdown_link, text)

    def _replace_plain_url(match: re.Match) -> str:
        url = match.group(0).rstrip("。；;,，)")
        suffix = match.group(0)[len(url):]
        return f"{short_url_label(url)}{suffix}"

    text = re.sub(r"https?://[^\s\)\]]+", _replace_plain_url, text)
    for idx, original in enumerate(placeholders):
        text = text.replace(f"__REPORT_LINK_{idx}__", original)
    return text


def strip_internal_report_fields(text: str) -> str:
    """正式報告隱藏模型稽核欄位；raw debug 仍保留原始候選資料。"""
    if not text:
        return text

    lines = text.splitlines()
    cleaned: list[str] = []
    skip_candidate_section = False
    internal_field_pattern = re.compile(
        r"^\s*[*-]?\s*(?:\*\*)?"
        r"(信心水準|納入理由|技術/政策關鍵字)"
        r"(?:\*\*)?\s*[：:].*$"
    )
    search_count_pattern = re.compile(r"^\s*(?:🔍\s*)?(?:\*\*)?執行搜尋次數")
    achieved_shortfall_pattern = re.compile(r"^\s*(?:⚠️\s*)?(?:\*\*)?不足\s*\d+\s*則原因(?:\*\*)?\s*[：:]\s*(?:已達標|無|無。)\s*$")

    for raw_line in lines:
        line = raw_line.strip()
        section_title = re.sub(r"^[#\s]+", "", line).strip()

        if re.match(r"^候補觀察(?:（.*?）)?$", section_title):
            skip_candidate_section = True
            continue

        if skip_candidate_section:
            if section_title.startswith(("報告摘要", "結尾")) or line.startswith(("📊", "⚠️", "⏰", "**本週統計", "本週統計", "**不足", "不足", "**報告產出時間", "報告產出時間")):
                skip_candidate_section = False
            else:
                continue

        if internal_field_pattern.match(line):
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


def sanitize_report_text(text: str) -> str:
    text = (
        text.replace("全球（排除台灣）", "全球（安全白名單來源）")
        .replace("全球(排除台灣)", "全球（安全白名單來源）")
        .replace("（排除台灣）", "")
        .replace("(排除台灣)", "")
    )
    return strip_internal_report_fields(text)


def compact_report_line_for_pdf(line: str) -> str:
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    line = re.sub(
        r"\[(.+?)\]\((https?://[^\)]+)\)",
        lambda m: f"{m.group(1)}（{short_url_label(m.group(2))}）",
        line,
    )
    return compact_report_urls(line)


def register_pdf_fonts() -> tuple[str, str]:
    """Register Microsoft JhengHei for CJK and Times New Roman for Latin text when available."""
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

    cjk_font = _register_ttf("MicrosoftJhengHei", [
        r"C:\Windows\Fonts\msjh.ttc",
        r"C:\Windows\Fonts\msjh.ttf",
        r"C:\Windows\Fonts\msjhl.ttc",
        r"C:\Windows\Fonts\mingliu.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansTC-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJKtc-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
    ])
    if not cjk_font:
        if not _is_registered("MSung-Light"):
            pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
        cjk_font = "MSung-Light"

    latin_font = _register_ttf("TimesNewRoman", [
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\timesbd.ttf",
        r"C:\Windows\Fonts\timesi.ttf",
    ]) or "Times-Roman"

    return cjk_font, latin_font


def pdf_rich_text(text: str, cjk_font: str, latin_font: str) -> str:
    chunks: list[str] = []
    current: list[str] = []
    current_is_latin: bool | None = None

    for char in text:
        is_latin = ord(char) < 128
        if current and is_latin != current_is_latin:
            chunk = escape("".join(current), quote=False)
            font_name = latin_font if current_is_latin else cjk_font
            chunks.append(f'<font name="{font_name}">{chunk}</font>')
            current = []
        current.append(char)
        current_is_latin = is_latin

    if current:
        chunk = escape("".join(current), quote=False)
        font_name = latin_font if current_is_latin else cjk_font
        chunks.append(f'<font name="{font_name}">{chunk}</font>')

    return "".join(chunks)


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
        if any(category in heading for category in selected_types):
            count += 1
    return count


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


def status_badge(status: str) -> str:
    class_name = {
        "成功": "badge-success",
        "fallback 成功": "badge-fallback",
        "無文章": "badge-empty",
        "timeout": "badge-warning",
        "403": "badge-error",
        "parse error": "badge-error",
        "被安全規則排除": "badge-blocked",
        "範圍排除": "badge-blocked",
        "非都市軌道": "badge-neutral",
    }.get(status, "badge-neutral")
    label = {
        "成功": "✅ 成功",
        "fallback 成功": "↪ fallback 成功",
        "無文章": "○ 無文章",
        "timeout": "⏱ timeout",
        "403": "403",
        "parse error": "parse error",
        "被安全規則排除": "安全排除",
        "範圍排除": "範圍排除",
        "非都市軌道": "非都市軌道",
    }.get(status, status)
    return f'<span class="status-badge {class_name}">{escape(label)}</span>'


def render_source_health_dashboard(statuses: list[dict]) -> None:
    if not statuses:
        st.info("尚無來源健康資料；產生報告後會在此顯示各來源狀態。")
        return

    st.markdown('<div class="section-title">來源健康儀表板</div>', unsafe_allow_html=True)
    status_order = ["成功", "fallback 成功", "無文章", "非都市軌道", "timeout", "403", "parse error", "被安全規則排除", "範圍排除"]
    counts = {status: sum(1 for row in statuses if row.get("status") == status) for status in status_order}
    healthy_count = counts["成功"] + counts["fallback 成功"]
    issue_count = counts["timeout"] + counts["403"] + counts["parse error"]
    total_candidates = sum(int(row.get("item_count", 0) or 0) for row in statuses)
    summary_items = [
        ("可用來源", healthy_count, f"成功 {counts['成功']}｜fallback {counts['fallback 成功']}"),
        ("無文章來源", counts["無文章"], f"非都市軌道 {counts['非都市軌道']}｜本期無候選"),
        ("需注意來源", issue_count, f"timeout {counts['timeout']}｜403 {counts['403']}｜parse {counts['parse error']}"),
        ("候選資料", total_candidates, "已通過 URL 與安全規則"),
    ]
    cols = st.columns(4)
    for idx, (label, num, note) in enumerate(summary_items):
        cols[idx].markdown(
            f"""
            <div class="source-summary-card">
              <div class="source-summary-num">{escape(str(num))}</div>
              <div class="source-summary-label">{escape(label)}</div>
              <div class="source-summary-note">{escape(note)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
    with st.expander("查看每個來源詳細狀態", expanded=False):
        st.caption("這裡保留完整稽核資訊，展示時可收合，承辦檢查時再展開。")
        st.markdown(table, unsafe_allow_html=True)


def markdown_to_pdf_bytes(md: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
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
    styles["BodyText"].fontSize = 10.2
    styles["BodyText"].leading = 13.2
    styles["Heading3"].leading = 14.5

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
        else:
            line = compact_report_line_for_pdf(line)
            story.append(Paragraph(pdf_rich_text(line, cjk_font, latin_font), styles["BodyText"]))
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
    """把「原始搜尋資料（MaiAgent 篩選前）」的純文字內容轉成 PDF，
    方便使用者下載保存，不用再從網頁手動複製。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

    cjk_font, latin_font = register_pdf_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    for style_name in ("Title", "Heading2", "BodyText"):
        styles[style_name].fontName = cjk_font
        styles[style_name].leading = max(styles[style_name].leading, 13)
    styles["BodyText"].fontSize = 8.5
    styles["BodyText"].leading = 12

    def _section(title: str, content: str, story: list):
        story.append(Paragraph(pdf_rich_text(title, cjk_font, latin_font), styles["Title"]))
        story.append(Spacer(1, 10))
        if not content.strip():
            story.append(Paragraph(pdf_rich_text("（無資料）", cjk_font, latin_font), styles["BodyText"]))
            return
        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if not line:
                story.append(Spacer(1, 4))
                continue
            wrapped = _soft_wrap_long_tokens(line)
            if line.startswith("【"):
                story.append(Spacer(1, 6))
                story.append(Paragraph(pdf_rich_text(wrapped, cjk_font, latin_font), styles["Heading2"]))
            else:
                story.append(Paragraph(pdf_rich_text(wrapped, cjk_font, latin_font), styles["BodyText"]))

    story: list = []
    _section(f"RSS 原始資料（{today.strftime('%Y-%m-%d')}）", raw_rss, story)
    story.append(PageBreak())
    _section(f"ddgs 原始資料（{today.strftime('%Y-%m-%d')}）", raw_ddg, story)

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


send_btn = False

if generate_btn or send_btn:
    if not maiagent_api_key:
        status_placeholder.error("❌ MaiAgent API Key 未設定，請至 Streamlit Cloud App Settings → Secrets 填入 MAIAGENT_API_KEY")
    elif not maiagent_chatbot_id:
        status_placeholder.error("❌ MaiAgent Chatbot ID 未設定，請至 Streamlit Cloud App Settings → Secrets 填入 MAIAGENT_CHATBOT_ID")
    elif not selected_types:
        status_placeholder.error("❌ 尚未勾選新聞類型，請至左側選單勾選想要搜尋的主題。")
    elif not is_global_scope and not active_regions:
        status_placeholder.error("❌ 指定先進國家/地區模式下，請至少勾選一個國家/地區。")
    else:
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
            # Step 1：RSS 訂閱源 + 指定模式地區代理 + 規範更新代理
            region_sources = build_region_news_sources(active_regions, int(lookback_days))
            standards_sources = build_standards_news_sources(int(lookback_days)) if standards_enabled else []
            combined_sources = RSS_SOURCES + region_sources + standards_sources
            status_text.text(
                f"🔎 正在蒐集 RSS / Google News / ddgs 候選資料……（共 {len(combined_sources)} 個來源）"
            )
            rss_results, source_statuses = fetch_rss_feeds(
                combined_sources, status_text=status_text, return_status=True
            )
            progress_bar.progress(0.30)
            status_text.text("🛡️ 正在進行來源安全檢查與去重……")
            st.session_state["latest_rss_raw"] = rss_results
            st.session_state["latest_source_statuses"] = source_statuses

            # Step 2：加速版 ddgs 搜尋
            status_text.text("🔍 正在蒐集 ddgs 候選資料……")
            ddg_progress = ProgressRange(progress_bar, 0.30, 0.50)
            ddg_results = run_duckduckgo_searches(ddg_progress, status_text)
            progress_bar.progress(0.50)
            st.session_state["latest_ddg_raw"] = ddg_results
            status_text.text("🚇 正在篩選都會軌道相關新聞……")
            progress_bar.progress(0.65)

            if show_raw_debug:
                os.makedirs("reports", exist_ok=True)
                with open(f"reports/raw_rss_{today.strftime('%Y%m%d')}.txt", "w", encoding="utf-8") as f:
                    f.write(rss_results)
                with open(f"reports/raw_ddg_{today.strftime('%Y%m%d')}.txt", "w", encoding="utf-8") as f:
                    f.write(ddg_results)

            # Step 3：MaiAgent 雲端 API 分析
            status_text.text(f"🤖 正在交由 MaiAgent 雲端 API 產生{report_period_label}……")
            report_text = call_maiagent_cloud(
                build_prompt(rss_results, ddg_results, combined_sources)
            )
            formal_count = count_report_items(report_text)
            needs_revision = (
                (target_is_enforced and formal_count < min_report_items)
                or report_has_unselected_types(report_text)
                or report_has_non_urban_formal_items(report_text)
                or "排除台灣" in report_text
            )
            if needs_revision:
                status_text.text(
                    f"🤖 初稿 {formal_count} 則、分類或都市軌道範圍需修正，正在自動重寫……"
                )
                report_text = call_maiagent_cloud(
                    build_revision_prompt(
                        rss_results,
                        ddg_results,
                        report_text,
                        formal_count,
                        combined_sources,
                    )
                )
                formal_count = count_report_items(report_text)
            progress_bar.progress(0.85)
            status_text.text("📄 正在產製 PDF / Email 輸出準備……")
            report_text = sanitize_report_text(report_text)
            formal_count = count_report_items(report_text)

            os.makedirs("reports", exist_ok=True)
            with open("reports/latest.md", "w", encoding="utf-8") as f:
                f.write(report_text)
            with open(f"reports/report_{today.strftime('%Y%m%d')}.md", "w", encoding="utf-8") as f:
                f.write(report_text)

            st.session_state["latest_report"] = report_text
            st.session_state["latest_report_summary"] = {
                "formal_count": formal_count,
                "has_standards": "規範更新" in report_text,
            }
            progress_bar.progress(0.95)
            summary = st.session_state["latest_report_summary"]
            progress_bar.progress(1.0)
            status_text.markdown(
                f"""
                <div class="notice-success">
                  <strong>✅ 報告已完成</strong><br>
                  可於下方查看正式{report_period_label}、下載 PDF 或寄送 Email。<br>
                  正式新聞：{formal_count} 則｜
                  規範更新：{'包含' if summary['has_standards'] else '未包含'}｜
                  PDF / Email 已準備完成。
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
raw_rss = st.session_state.get("latest_rss_raw", "")
raw_ddg = st.session_state.get("latest_ddg_raw", "")
source_statuses = st.session_state.get("latest_source_statuses", [])

if source_statuses:
    render_source_health_dashboard(source_statuses)

st.markdown(f'<div class="section-title">正式{report_period_label}</div>', unsafe_allow_html=True)

report_to_show = st.session_state.get("latest_report", "")
if not report_to_show:
    try:
        with open("reports/latest.md", "r", encoding="utf-8") as f:
            report_to_show = f.read()
    except FileNotFoundError:
        pass
report_to_show = sanitize_report_text(report_to_show)

if report_to_show:
    tab1, tab2 = st.tabs(["正式版面", "Markdown"])
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
                f"📄 下載正式{report_period_label} PDF",
                data=pdf_bytes,
                file_name=f"metro_report_{today.strftime('%Y%m%d')}.pdf",
                mime="application/octet-stream",
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
                mime="application/octet-stream",
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
                status_placeholder.warning("⚠️ 請在左側填入收件信箱")
            elif not gmail_user or not gmail_pass:
                status_placeholder.warning("⚠️ GMAIL_USER 或 GMAIL_APP_PASS 未在 Secrets 中設定")
            else:
                email_progress = progress_placeholder.progress(0.95)
                status_placeholder.text("📧 正在寄送 Email 至公務信箱……")
                ok = send_email_func(report_to_show, recipients, gmail_user, gmail_pass)
                if ok:
                    email_progress.progress(1.0)
                    status_placeholder.success("✅ Email 已寄送完成。")
                    st.success(f"📧 已成功寄送至：{', '.join(recipients)}")
else:
    st.markdown(f"""
    <div class="warn-box">
    📭 尚無報告資料。請點擊上方「產生國際捷運 AI {report_period_label}」按鈕產生第一份報告。
    </div>""", unsafe_allow_html=True)

# ── 原始搜尋資料（除錯用）────────────────────────────
if show_raw_debug and (raw_rss or raw_ddg):
    with st.expander("🔎 原始資料與 AI 篩選前候選池（除錯用）", expanded=False):
        st.caption(
            "這裡是 RSS／ddgs 實際抓到、丟給 MaiAgent 的原始文字。"
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
