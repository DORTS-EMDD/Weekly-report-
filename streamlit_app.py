"""
國際捷運技術週報 — Streamlit 競賽展示介面
功能：
  1. 立即產生本週報告（展示用）
  2. 顯示最新報告內容
  3. 寄送測試信件
"""

import os
import datetime
import streamlit as st
from google import genai
from google.genai import types

# ── 頁面設定 ──────────────────────────────────────────
st.set_page_config(
    page_title="國際捷運技術週報 AI 系統",
    page_icon="🚇",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS 樣式 ──────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stSidebar"] { background-color: #1a3a5c; }
  [data-testid="stSidebar"] * { color: white !important; }
  [data-testid="stSidebar"] .stSelectbox label { color: white !important; }
  .main-title {
    font-size: 2rem; font-weight: 700; color: #1a3a5c;
    border-bottom: 3px solid #1a3a5c; padding-bottom: 8px; margin-bottom: 4px;
  }
  .subtitle { color: #666; font-size: 0.95rem; margin-bottom: 24px; }
  .info-box {
    background: #f0f8f4; border-left: 4px solid #1a6e4a;
    padding: 12px 16px; border-radius: 0 6px 6px 0; margin: 12px 0;
  }
  .warn-box {
    background: #fff8e6; border-left: 4px solid #f59e0b;
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
            "gemini-3.1-flash-lite：Gemini 3 最新輕量版，速度快、省配額，適合大量章節改寫。\n"
            "gemini-3.5-flash：接近 Pro 等級智能，細節與表格保留更完整，建議用於關鍵章節。"
        ),
    )

    st.markdown("### 📬 收件設定")
    recipient_input = st.text_area(
        "收件信箱（每行一個）",
        placeholder="pe9875@gov.taipei\n10983@gov.taipei",
        height=90,
    )

    st.markdown("---")
    st.markdown("### 📅 排程說明")
    st.markdown("""
- ⏰ **每週一 08:00**（台灣時間）自動執行
- ☁️ 由 GitHub Actions 雲端排程
- 💤 **不需要開電腦**
- 📧 自動寄送至公務信箱
    """)

    st.markdown("---")
    st.caption("🏛️ 臺北大眾捷運股份有限公司\nAI 競賽展示系統 v1.0")

# ── 主畫面 ──────────────────────────────────────────
st.markdown('<div class="main-title">🚇 國際捷運技術週報 AI 自動產生系統</div>', unsafe_allow_html=True)

today = datetime.date.today()
week_start = today - datetime.timedelta(days=7)
st.markdown(
    f'<div class="subtitle">資料涵蓋期間：{week_start.strftime("%Y/%m/%d")} – {today.strftime("%Y/%m/%d")} ｜ '
    f'使用模型：{model_choice}</div>',
    unsafe_allow_html=True,
)

# 統計卡片
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown('<div class="stat-card"><div class="stat-num">3</div><div class="stat-label">監控領域</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown('<div class="stat-card"><div class="stat-num">7</div><div class="stat-label">監控國家/地區</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown('<div class="stat-card"><div class="stat-num">12+</div><div class="stat-label">每次搜尋次數</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown('<div class="stat-card"><div class="stat-num">週一</div><div class="stat-label">自動寄送週期</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── API Key 輸入 ──────────────────────────────────────
with st.expander("🔑 API 設定（展示模式）", expanded=False):
    api_key_input = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="貼上你的 Gemini API Key（AIza...）",
        help="僅用於此次展示，不會儲存。正式排程請設定於 GitHub Secrets。",
    )
    gmail_user_input = st.text_input("Gmail 帳號", placeholder="your@gmail.com")
    gmail_pass_input = st.text_input("Gmail 應用程式密碼", type="password", placeholder="xxxx xxxx xxxx xxxx")

# 取得 API Key（優先用輸入，其次環境變數）
api_key = api_key_input or os.environ.get("GEMINI_API_KEY", "")

# ── 立即產生報告 ──────────────────────────────────────
st.markdown("### 🚀 立即產生報告")

col_btn1, col_btn2, col_space = st.columns([2, 2, 4])
with col_btn1:
    generate_btn = st.button("🤖 立即產生週報", type="primary", use_container_width=True)
with col_btn2:
    send_btn = st.button("📧 產生並寄送", use_container_width=True)

if generate_btn or send_btn:
    if not api_key:
        st.error("❌ 請先在上方輸入 Gemini API Key")
    else:
        with st.spinner(f"🔍 正在使用 {model_choice} 搜尋國際捷運資訊（約需 30–90 秒）..."):
            try:
                from main import build_prompt, markdown_to_html, save_report, send_email
                import smtplib

                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model_choice,
                    contents=build_prompt(),
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        temperature=0.2,
                    ),
                )
                report_text = response.text

                # 儲存報告
                save_report(report_text)
                st.session_state["latest_report"] = report_text
                st.session_state["report_generated"] = True

                st.success("✅ 報告產生完成！")

                # 如果按的是寄送按鈕
                if send_btn:
                    recipients = [r.strip() for r in recipient_input.splitlines() if r.strip()]
                    if not recipients:
                        st.warning("⚠️ 請在左側填入收件信箱")
                    elif not gmail_user_input or not gmail_pass_input:
                        st.warning("⚠️ 請填入 Gmail 帳號與應用程式密碼")
                    else:
                        os.environ["GMAIL_USER"]    = gmail_user_input
                        os.environ["GMAIL_APP_PASS"] = gmail_pass_input
                        success = send_email(report_text, recipients)
                        if success:
                            st.success(f"📧 已成功寄送至：{', '.join(recipients)}")
                        else:
                            st.error("❌ 寄信失敗，請確認 Gmail 應用程式密碼是否正確")

            except Exception as e:
                st.error(f"❌ 發生錯誤：{e}")
                st.info("💡 提示：請確認 API Key 正確，且帳號有啟用 Google Search grounding 權限")

# ── 報告顯示區 ──────────────────────────────────────
st.markdown("---")
st.markdown("### 📄 最新報告內容")

# 嘗試讀取已儲存的報告
report_to_show = st.session_state.get("latest_report", "")

if not report_to_show:
    try:
        with open("reports/latest.md", "r", encoding="utf-8") as f:
            report_to_show = f.read()
    except FileNotFoundError:
        pass

if report_to_show:
    # 標籤頁：Markdown 預覽 / 原始文字
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
    </div>
    """, unsafe_allow_html=True)

# ── 系統架構說明 ──────────────────────────────────────
with st.expander("📐 系統架構說明"):
    st.markdown("""
```
GitHub Actions（每週一 08:00 台灣時間，雲端自動執行）
        ↓
    main.py
        ├── Gemini API（gemini-3.1-flash-lite / gemini-3.5-flash）
        │       └── Google Search Grounding（內建搜尋工具）
        │               ├── 搜尋國際捷運技術新知
        │               ├── 搜尋重大事故與異常
        │               └── 搜尋規範與政策更新
        ├── 整理成繁體中文週報（Markdown 格式）
        └── Gmail SMTP → 寄送至公務信箱
```
    """)
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("""
**✅ 免費元件**
- GitHub Actions（2,000 分鐘/月免費）
- Gemini API（Flash 模型有免費額度）
- Google Search Grounding（每月 5,000 次免費）
- Gmail SMTP（免費）
- Streamlit Cloud（免費部署）
        """)
    with col_b:
        st.markdown("""
**🔒 安全設計**
- API Key 存於 GitHub Secrets，不會外洩
- Gmail 使用應用程式密碼，非帳號密碼
- 報告僅寄送至指定信箱
- 原始碼開源，可自行審閱
        """)
