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
    margin-bottom: 8px !important;
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

# ── 日期與常數 ──────────────────────────────────────────────
today = datetime.date.today()

ADVANCED_TYPES = ["技術新知", "重大事故", "營運爭議", "營運政策"]

ADVANCED_REGIONS = [
    "日本", "韓國", "新加坡", "香港",
    "澳洲", "英國", "法國", "德國", "荷蘭",
    "瑞士", "美國", "加拿大",
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
    )
    lookback_days = st.number_input(
        "新聞搜尋天數", min_value=3, max_value=30, value=7, step=1,
    )

    # ── 新聞類型篩選 (下拉式收合) ──
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

    # ── 國家地區篩選 (下拉式收合) ──
    st.markdown("### 🌏 重點國家/地區")
    default_regions = ["日本", "韓國", "新加坡", "香港"]
    if "selected_regions_state" not in st.session_state:
        st.session_state["selected_regions_state"] = default_regions.copy()

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
    if selected_regions:
        st.caption("已選：" + "、".join(selected_regions))
    else:
        st.warning("請至少選擇一個國家/地區。")

    # ── 收件設定 ──
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

    st.markdown("### 📅 排程說明")
    st.markdown("""
- ⏰ **每週一 08:00** 自動執行
- ☁️ 由 **GitHub Actions** 雲端排程
- 📧 自動寄送至公務信箱
    """)
    with st.expander("🔑 系統狀態", expanded=False):
        st.markdown(f"Gemini API Key：{'✅' if api_key else '❌'}")
        st.markdown(f"Gmail 帳號：{'✅' if gmail_user else '❌'}")
        st.markdown(f"Gmail 密碼：{'✅' if gmail_pass else '❌'}")
        
    st.markdown("---")
    st.caption("🏛️ 台北市政府捷運工程局\nAI 競賽展示系統")

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
    (c1, str(len(selected_types)), "追蹤主題數"),
    (c2, str(len(selected_regions)), "重點國家"),
    (c3, f"{lookback_days}", "新聞搜尋天數"),
]:
    col.markdown(
        f'<div class="stat-card"><div class="stat-num">{num}</div>'
        f'<div class="stat-label">{label}</div></div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════
#  RSS 訂閱源（權威媒體清單，逐一查證是否有可用 RSS）
# ═══════════════════════════════════════════════════════
# 註：每一列皆已個別查證是否存在可訂閱的 RSS（2026-07 查證）。
# 找不到官方 RSS 端點的來源（UITP、RTRI）改用 Google News 的
# site: 搜尋做為代理 RSS，仍會標明真實來源網域，供 Gemini／人工複查連結是否有效。
RSS_SOURCES = [
    ("Railway Gazette International（已併入 Metro Report International 都市軌道報導）",
     "https://www.railwaygazette.com/149.rss"),
    ("International Railway Journal (IRJ)", "https://www.railjournal.com/feed/"),
    ("Railway Technology", "https://www.railway-technology.com/feed/"),
    ("Railway-News", "https://railway-news.com/feed/"),
    ("Global Railway Review", "https://www.globalrailwayreview.com/feed/"),
    ("Intelligent Transport", "https://www.intelligenttransport.com/feed/"),
    ("UITP（無官方RSS，改用Google News代理）",
     "https://news.google.com/rss/search?q=site:uitp.org&hl=en-US&gl=US&ceid=US:en"),
    ("Mass Transit Network", "https://masstransit.network/index.rss"),
    ("Global Mass Transit", "https://www.globalmasstransit.net/feed"),
    ("東洋經濟 Online（鐵道最前線，全站RSS需自行篩選）", "https://toyokeizai.net/list/feed/rss"),
    ("乗りものニュース", "https://trafficnews.jp/feed"),
    ("鉄道総合技術研究所 RTRI（無官方RSS，改用Google News代理）",
     "https://news.google.com/rss/search?q=site:rtri.or.jp&hl=ja&gl=JP&ceid=JP:ja"),
    ("Transit Jam", "https://transitjam.com/feed/"),
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
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=min(int(lookback_days) * 2, 60))
    )
    all_blocks: list[str] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MetroWeeklyBot/4.2)"}
    ATOM = "http://www.w3.org/2005/Atom"

    for idx, (source_name, url) in enumerate(RSS_SOURCES, 1):
        if status_text:
            status_text.text(f"📡 RSS {idx}/{len(RSS_SOURCES)}：{source_name}...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as f:
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
                    lines.append(f"  日期：{dt}\n  標題：{t}\n  摘要：{d}\n  連結：{l}")
                all_blocks.append("\n".join(lines))
            else:
                all_blocks.append(f"【RSS來源：{source_name}】（近30天無新文章）")
        except Exception as exc:
            all_blocks.append(f"【RSS來源：{source_name}】（略過：無有效訂閱點或超時）")

    return "\n\n".join(all_blocks)


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
    if "營運爭議" in selected_types:
        queries.extend([
            f"metro subway transit strike delay controversy {today:%B %Y}",
            f"鉄道 地下鉄 遅延 争議 {today:%Y年%m月}"
        ])
    if "營運政策" in selected_types:
        queries.extend([
            f"metro subway policy passenger safety regulation {today:%B %Y}",
            f"鉄道 地下鉄 規則 安全対策 {today:%Y年%m月}"
        ])

    # 2. 地區合併關鍵字（改為涵蓋所有已勾選國家，不再只取前 5 個）
    for i, region in enumerate(selected_regions):
        term = REGION_SEARCH_TERMS.get(region, region)
        if "技術新知" in selected_types:
            queries.append(f"{term} metro LRRT subway upgrade press release {today:%B %Y}")

        # 將事故、爭議、政策合併為一個查詢字串，精簡發送數量
        if any(t in selected_types for t in ["重大事故", "營運爭議", "營運政策"]):
            idx = len(queries)
            queries.append(f"{term} metro subway incident strike policy controversy {today:%B %Y}")
            news_indices.add(idx)

    # 上限控制：從固定 16 條放寬為依實際勾選數動態調整（搭配下方平行化執行，維持速度）
    return queries[:32], news_indices


def _run_single_query(i: int, query: str, use_news: bool, news_timelimit: str) -> tuple[int, str]:
    """執行單一查詢（純運算/網路請求，不觸碰 Streamlit API，可安全在背景執行緒執行）"""
    # 隨機抖動起跑時間，避免多執行緒同時擊中 DDGS 造成瞬間流量觸發限流
    time.sleep(random.uniform(0.1, 0.6))
    result_block = None

    for backend in ["auto", "bing"]:
        for attempt in range(1, 3):
            try:
                with DDGS() as ddgs:
                    if use_news:
                        results = ddgs.news(query, max_results=10, timelimit=news_timelimit, backend=backend)
                    else:
                        results = ddgs.text(query, max_results=10, timelimit="m", backend=backend)
                if results:
                    lines = [f"【搜尋 {i}（{backend}）】{query}"]
                    for r in results:
                        body = (r.get("body") or r.get("excerpt") or r.get("description") or "")[:250]
                        href = r.get("href") or r.get("url") or ""
                        lines.append(f"  標題：{r.get('title','')}\n  摘要：{body}\n  連結：{href}")
                    result_block = "\n".join(lines)
                else:
                    result_block = f"【搜尋 {i}】無結果"
                break
            except Exception as exc:
                wait = attempt * 1.0 + random.uniform(0.5, 1.5)
                time.sleep(wait)
                if not any(k in str(exc) for k in ("Ratelimit", "429", "403")):
                    break

        if result_block and "無結果" not in result_block:
            break

    return i, (result_block or f"【搜尋 {i}】略過")


def run_duckduckgo_searches(progress_bar=None, status_text=None) -> str:
    """執行 DDGS 多後端搜尋（平行化版本：查詢數變多但改為併發執行，速度不會被拖慢）"""
    if not selected_types:
        return "未勾選任何新聞類型，略過搜尋。"

    search_queries, news_query_indices = build_search_queries()
    total = len(search_queries)
    news_timelimit = "w" if int(lookback_days) <= 7 else "m"
    results_map: dict[int, str] = {}
    done_count = 0

    # 同時最多 6 條併發，兼顧速度與避免被 DDGS 判定為濫用流量
    max_workers = max(1, min(6, total))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_single_query, i, query, i in news_query_indices, news_timelimit): i
            for i, query in enumerate(search_queries, 1)
        }
        for future in concurrent.futures.as_completed(futures):
            i, block = future.result()
            results_map[i] = block
            done_count += 1
            if status_text:
                status_text.text(f"🔍 已完成搜尋 {done_count:02d}/{total}...")
            if progress_bar:
                progress_bar.progress(done_count / total)

    return "\n\n".join(results_map[i] for i in sorted(results_map))


# ── Prompt 建立 ───────────────────────────────────────
def build_prompt(rss_results: str, ddg_results: str) -> str:
    weekday = ['一','二','三','四','五','六','日'][today.weekday()]
    search_count = len(build_search_queries()[0])
    
    selected_types_str = "、".join(selected_types) if selected_types else "無"
    
    return f"""
# 角色
你是專業捷運機電技術分析師，服務對象為台北市政府捷運工程局處長及技術同仁。

# 任務
以下是透過「RSS 訂閱源」與「ddgs 多後端搜尋」蒐集到的原始資料。
請依照使用者勾選的類型，整理出具參考價值的週報（目標期間：{date_range}）。

## ━━ 第一部分：RSS 訂閱源（涵蓋 {len(RSS_SOURCES)} 個媒體，見下方權重清單）━━
{rss_results}

## ━━ 第二部分：關鍵字搜尋結果━━
{ddg_results}

## 🎯 篩選與優先級指示（請保持彈性）
1. **新聞類型過濾**：本次報告**只能**包含以下使用者勾選的新聞類型：【{selected_types_str}】。若不屬於這些類型，請直接忽略。
   - **技術新知**：機電、號誌、車輛、土木等工程技術。
   - **重大事故**：出軌、追撞、火災、嚴重系統當機。
   - **營運爭議**：罷工、預算超支、票價爭議、合約糾紛。
   - **營運政策**：捷運站內安檢新規、乘車規則變動（如禁帶大型鋰電池/滑板車）、安全管理政策。
2. **最高優先級（專注捷運與LRRT，排除一般鐵路/高鐵）**：本報告是提供給北市府捷運局的國際週報，請**嚴格過濾並排除**傳統客運/貨運鐵路（火車、城際列車）與高速鐵路（HSR）的新聞。請**絕對優先保留並聚焦**於國際上的**「都市捷運系統（Metro / Subway / Underground）」**以及**「中運量 / 輕軌 / 膠輪系統（LRRT / AGT / LRT）」**的新聞，並給予最大篇幅。
3. **來源權重**：請優先採納「第一部分：RSS 訂閱源」中實際出現的來源（本次共 {len(RSS_SOURCES)} 個，清單如下），這些是本次真正抓取到的媒體，**不要**引用或想像清單以外的媒體名稱：
{chr(10).join('   - ' + name for name, _ in RSS_SOURCES)}
4. **放寬篩選**：只要事件對捷運局具備實務參考價值、或與使用者選擇的國家/地區有關聯，即使摘要較短，亦可納入。不需要過度嚴格剃除主題相關性；但日期真實性規則（見下方第 5 點）沒有彈性空間。
5. **【絕對禁止腦補、嚴格日期查核】（違反本條視為報告失敗）**：
   - 每一則新聞的「發布/事件日期」**必須**直接取自原始資料中該則內容本身標註的日期字串（RSS 的「日期：」欄位，或關鍵字搜尋結果摘要中出現的日期）。**禁止**依你自己知識庫中對該事件、公司或專案的既有印象去推測、換算或臆造日期。
   - 若某則原始資料**沒有**明確可辨識的日期，或日期含糊到無法判斷是哪一天，**直接捨棄該則**，不要用「近期」「今年」等模糊字眼帶過，也不要自行補上一個日期。
   - 若某則的日期**晚於今天（{today.strftime('%Y-%m-%d')}）**，即為不合理的未來日期，**直接剔除**，不得納入報告、不得嘗試「合理化」或改寫成合理日期。
   - 若同一事件在原始資料中找不到，但你「記得」曾經發生過類似新聞，**一律視為未提供資料**，不要用記憶內容補寫。你只能整理「第一部分」與「第二部分」中實際出現的文字，不能新增任何未出現於原始資料的事實、數字或日期。
   - 若某新聞類型或國家因日期查核後篩到剩下很少則、甚至 0 則，**寧可誠實回報「本期無相關新聞」**，也不要為了湊滿 8–15 則而放寬日期查核標準。

## 國家/地區限制清單
本報告限定報導以下國家/地區：
{chr(10).join('- ' + r for r in selected_regions)}

## 輸出格式（每則獨立區塊，目標 8–15 則）

# {report_title}
> 資料涵蓋期間：{date_range} 
> 篩選類型：{selected_types_str}

---

### 🔹 [填入該則所屬之分類：技術新知/重大事故/營運爭議/營運政策] 國家/地區：（一句有力主標題）
* **發布/事件日期**：（原文發布年月日）
* **事件摘要**：
  - （列點精要說明，3–5 點）
* **技術/政策關鍵字**：（英漢對照）
* **資料來源**：[來源名稱](完整 https:// 網址)
* **【臺北捷運局啟示】**：（對北捷系統/中運量的具體參考價值）

---

## 結尾（必填）
---
📊 **本週統計**：共 N 則 
🔍 **執行搜尋次數**：RSS {len(RSS_SOURCES)} 源 + ddgs {search_count} 次精簡搜尋
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
st.markdown("### 🚀 立即產生報告")
col_b1, col_b2, _ = st.columns([2, 2, 4])
generate_btn = col_b1.button("🤖 立即產生週報", type="primary", use_container_width=True)
send_btn     = col_b2.button("📧 產生並寄送",   use_container_width=True)

if generate_btn or send_btn:
    if not api_key:
        st.error("❌ Gemini API Key 未設定，請至 Streamlit Cloud App Settings → Secrets 填入")
    elif not selected_types:
        st.error("❌ 尚未勾選新聞類型，請至左側選單勾選想要搜尋的主題。")
    else:
        progress_bar = st.progress(0)
        status_text  = st.empty()

        try:
            # Step 1：RSS 訂閱源 (擴充至 12 個)
            status_text.text(f"📡 抓取 {len(RSS_SOURCES)} 個權威媒體 RSS 訂閱源...")
            rss_results = fetch_rss_feeds(status_text=status_text)

            # Step 2：加速版 ddgs 搜尋
            status_text.text("🔍 開始執行加速版關鍵字搜尋...")
            ddg_results = run_duckduckgo_searches(progress_bar, status_text)

            # Step 3：Gemini 分析
            progress_bar.progress(1.0)
            status_text.text(f"🤖 {model_choice} 正在進行智慧過濾整理（約 15–40 秒）...")
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