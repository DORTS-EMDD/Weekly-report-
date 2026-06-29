"""
國際捷運技術週報 — Streamlit 競賽展示介面 v3
金鑰來源：Streamlit Secrets（不硬碼在程式中）
"""

import os
import re
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st
from google import genai
from google.genai import types

# ══════════════════════════════════════════════════════
#  金鑰讀取（順序：Streamlit Secrets → 環境變數）
#  ⚠️ 請勿在此處直接填入金鑰！
#  設定方式：Streamlit Cloud → App Settings → Secrets
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
  [data-testid="stSidebar"] .stSelectbox > div > div {
    color: #111 !important; background-color: #f5f5f5 !important;
  }
  .main-title {
    font-size: 2rem; font-weight: 700; color: #1a3a5c;
    border-bottom: 3px solid #1a3a5c; padding-bottom: 8px; margin-bottom: 4px;
  }
  .subtitle { color: #666; font-size: 0.95rem; margin-bottom: 24px; }
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
</style>
""", unsafe_allow_html=True)

# ── 日期 ──────────────────────────────────────────────
today      = datetime.date.today()
week_start = today - datetime.timedelta(days=7)
date_range = f"{week_start.strftime('%Y年%m月%d日')} 至 {today.strftime('%Y年%m月%d日')}"
report_title = f"【{today.strftime('%Y/%m/%d')}】國際捷運技術新知、重大事件週報"

# ── 側邊欄 ──────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚇 捷運週報系統")
    st.markdown("---")

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

    st.markdown("### 📬 收件設定")
    default_recipients = get_secret("DEFAULT_RECIPIENTS", "")
    recipient_input = st.text_area(
        "收件信箱（每行一個）",
        value=default_recipients,
        placeholder="pe9875@gov.taipei\n10983@gov.taipei",
        height=90,
    )

    st.markdown("---")
    st.markdown("### 📅 排程說明")
    st.markdown("""
- ⏰ **每週一 08:00**（台灣時間）自動執行
- ☁️ 由 **GitHub Actions** 雲端排程
- 💤 **不需要開電腦**
- 📧 自動寄送至公務信箱
    """)
    st.markdown("---")
    st.caption("🏛️ 台北市政府捷運工程局\nAI 競賽展示系統 v3")

# ── 主畫面 ──────────────────────────────────────────
st.markdown('<div class="main-title">🚇 國際捷運技術週報 AI 自動產生系統</div>',
            unsafe_allow_html=True)
st.markdown(
    f'<div class="subtitle">資料涵蓋期間：{week_start.strftime("%Y/%m/%d")} – '
    f'{today.strftime("%Y/%m/%d")} ｜ 使用模型：{model_choice}</div>',
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)
for col, num, label in [
    (c1, "3",  "監控領域"),
    (c2, "7",  "監控國家/地區"),
    (c3, "12+","每次搜尋次數"),
    (c4, "週一","自動寄送週期"),
]:
    col.markdown(
        f'<div class="stat-card"><div class="stat-num">{num}</div>'
        f'<div class="stat-label">{label}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── 金鑰狀態顯示 ──────────────────────────────────────
api_key    = get_secret("GEMINI_API_KEY")
gmail_user = get_secret("GMAIL_USER")
gmail_pass = get_secret("GMAIL_APP_PASS")

with st.expander("🔑 金鑰狀態", expanded=not bool(api_key)):
    col_k1, col_k2, col_k3 = st.columns(3)
    col_k1.markdown(f"**Gemini API Key**\n{'✅ 已設定' if api_key else '❌ 未設定'}")
    col_k2.markdown(f"**Gmail 帳號**\n{'✅ 已設定' if gmail_user else '❌ 未設定'}")
    col_k3.markdown(f"**Gmail 密碼**\n{'✅ 已設定' if gmail_pass else '❌ 未設定'}")

    if not api_key:
        st.markdown("""
        <div class="warn-box">
        金鑰未設定。請至 Streamlit Cloud → App Settings → Secrets 填入：<br><br>
        <code>GEMINI_API_KEY = "你的金鑰"</code><br>
        <code>GMAIL_USER = "yourname@gmail.com"</code><br>
        <code>GMAIL_APP_PASS = "xxxx xxxx xxxx xxxx"</code>
        </div>
        """, unsafe_allow_html=True)


# ── Prompt 建立 ───────────────────────────────────────
def build_prompt() -> str:
    weekday = ['一','二','三','四','五','六','日'][today.weekday()]
    return f"""
# 任務
你是專業捷運機電技術分析師。請使用內建的 Google Search 工具，
在今日（{today.strftime('%Y年%m月%d日')}）針對下列 12 組關鍵字各執行一次獨立搜尋，
產出涵蓋過去 7 天（{date_range}）的國際軌道交通重大資訊週報。

## 強制執行的 12 次搜尋
1. metro OR subway accident OR incident {today.strftime('%B %Y')}
2. CBTC OR FRMCS OR 5G railway {today.strftime('%B %Y')}
3. metro strike OR fare hike {today.strftime('%B %Y')}
4. digital twin OR AI predictive maintenance railway {today.strftime('%B %Y')}
5. SiC traction OR supercapacitor train {today.strftime('%B %Y')}
6. 鉄道 事故 OR 遅延 {today.strftime('%Y年%m月')}
7. 지하철 사고 OR 파업 {today.strftime('%Y년%m월')}
8. metro derailment OR signal failure {today.strftime('%B %Y')}
9. EULYNX OR virtual train coupling {today.strftime('%Y')}
10. MRT Singapore incident OR Hong Kong MTR {today.strftime('%B %Y')}
11. subway labor dispute OR strike {today.strftime('%B %Y')}
12. hydrogen train OR green rail energy {today.strftime('%B %Y')}

## ⚠️ 最高查核原則（防幻覺，違反整份作廢）
1. **雙重日期查核**：「新聞發布日」與「事件實際發生日」皆須在 {date_range} 內
2. **禁止舊聞充數**：舊案調查報告、歷史回顧一律捨棄
3. **免費公開原則**：禁止引用付費牆網站；優先使用官方新聞稿
4. **寧缺勿濫**：無符合條件者回報「系統監測正常，本週無符合條件之重大異動」

## 核心監控領域
1. **技術新知**：GoA4、CBTC、FRMCS/5G/6G、虛擬聯結、AI維修、數位雙生、SiC牽引、超級電容、氫能、EULYNX
2. **事故分析**：出軌、號誌故障、機電異常、延誤（分析根因：人為/系統/環境/機電介面）
3. **營運爭議**：勞資罷工、票價政策、系統轉換延宕

## 優先監控區域
日本、韓國、美國、歐洲、新加坡、香港、澳洲

## 輸出格式

# {report_title}
> 資料涵蓋期間：{date_range}

---

### 🔹 [類別] 國家/地區：（一句有力的主標題）
* **發布/事件日期**：（原文發布年月日）
* **事件摘要**：
  - （列點精要說明）
* **技術關鍵字**：（英漢對照）
* **資料來源**：[來源名稱](完整 https:// 網址)
* **【臺北捷運啟示】**：（具體參考；若無關聯請寫「暫無直接關聯」）

---

## 結尾（必填）
---
📊 **本週統計**：共 N 則
🔍 **執行搜尋次數**：N 次
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
<div class="footer">📧 AI 自動產生 | Gemini + Google Search | 僅供參考，請交叉驗證原始來源</div>
</body></html>"""


def send_email_func(text: str, recipients: list, gmail_user: str, gmail_pass: str) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = report_title
    msg["From"]    = gmail_user
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(markdown_to_html(text), "html", "utf-8"))
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
        with st.spinner(f"🔍 {model_choice} 正在搜尋國際捷運資訊（約 30–90 秒）..."):
            try:
                client   = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model_choice,
                    contents=build_prompt(),
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        temperature=0.2,
                    ),
                )
                report_text = extract_text(response)

                os.makedirs("reports", exist_ok=True)
                with open("reports/latest.md", "w", encoding="utf-8") as f:
                    f.write(report_text)
                with open(f"reports/report_{today.strftime('%Y%m%d')}.md", "w", encoding="utf-8") as f:
                    f.write(report_text)

                st.session_state["latest_report"] = report_text
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
GitHub Actions（每週一 08:00 台灣時間 / 00:00 UTC，雲端自動執行）
        ↓
    main.py
        ├── Gemini API（gemini-3.1-flash-lite / gemini-3.5-flash）
        │       └── Google Search Grounding（Gemini 內建，免費 5,000次/月）
        │               ├── 12 組關鍵字 × 英/日/韓語搜尋
        │               └── 整理成繁體中文週報
        └── Gmail SMTP → 自動寄送至公務信箱
```
    """)
    ca, cb = st.columns(2)
    with ca:
        st.markdown("""
**✅ 完全免費**
- GitHub Actions：2,000 分鐘/月
- Gemini Flash：免費配額每日足用
- Google Search Grounding：5,000 次/月
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
        """)
