"""
國際捷運技術週報自動產生器
- 使用 duckduckgo-search 抓取即時新聞（免費、無需 API Key）
- 將搜尋結果餵給 Gemini 撰寫報告（不使用 Google Search Grounding，零配額消耗）
- 每週一自動執行，寄送報告至指定信箱
"""

import os
import time
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai
from google.genai import types
from duckduckgo_search import DDGS

# ── 設定 ──────────────────────────────────────────────
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GMAIL_USER     = os.environ["GMAIL_USER"]
GMAIL_APP_PASS = os.environ["GMAIL_APP_PASS"]
RECIPIENTS     = os.environ["RECIPIENTS"]

MODEL_NORMAL   = "gemini-3.1-flash-lite"  # 預設：輕量版，速度快、省配額
MODEL_POWERFUL = "gemini-3.5-flash"       # 強化版：接近 Pro 等級智能

# ── 動態日期 ──────────────────────────────────────────
today      = datetime.date.today()
week_start = today - datetime.timedelta(days=7)
date_range = f"{week_start.strftime('%Y年%m月%d日')} 至 {today.strftime('%Y年%m月%d日')}"
report_title = f"【{today.strftime('%Y/%m/%d')}】國際捷運技術新知、重大事件週報"

# ── 搜尋關鍵字清單 ────────────────────────────────────
SEARCH_QUERIES = [
    f"metro rail accident incident {today.strftime('%B %Y')}",
    f"CBTC FRMCS 5G railway {today.strftime('%B %Y')}",
    f"metro strike fare hike {today.strftime('%B %Y')}",
    f"digital twin AI maintenance railway {today.strftime('%B %Y')}",
    f"SiC traction supercapacitor train {today.strftime('%B %Y')}",
    f"鉄道 事故 遅延 {today.strftime('%Y年%m月')}",
    f"지하철 사고 파업 {today.strftime('%Y')}",
    f"metro derailment signal failure {today.strftime('%B %Y')}",
    f"EULYNX train virtual coupling {today.strftime('%Y')}",
    f"MRT incident Singapore Hong Kong MTR {today.strftime('%B %Y')}",
    f"subway labor dispute strike {today.strftime('%B %Y')}",
    f"hydrogen train green rail {today.strftime('%B %Y')}",
]


def fetch_news() -> str:
    """使用 DuckDuckGo 抓取最新新聞，回傳彙整後的文字供 Gemini 分析。"""
    all_results = []
    ddgs = DDGS()

    for i, query in enumerate(SEARCH_QUERIES, 1):
        print(f"[搜尋 {i:02d}/{len(SEARCH_QUERIES)}] {query}")
        try:
            results = ddgs.news(query, max_results=5, timelimit="w")  # timelimit="w" = 過去一週
            for r in results:
                all_results.append(
                    f"標題：{r.get('title', '')}\n"
                    f"來源：{r.get('source', '')}  日期：{r.get('date', '')}\n"
                    f"摘要：{r.get('body', '')}\n"
                    f"網址：{r.get('url', '')}\n"
                )
            time.sleep(1)  # 避免對 DuckDuckGo 請求過快
        except Exception as e:
            print(f"  ⚠️ 搜尋失敗，跳過：{e}")

    if not all_results:
        return "（本週未搜尋到任何相關新聞）"

    combined = "\n---\n".join(all_results)
    print(f"[INFO] 共取得 {len(all_results)} 筆搜尋結果")
    return combined


def build_prompt(news_context: str) -> str:
    return f"""你是專業的捷運機電技術分析師。以下是透過網路搜尋取得的過去 7 天（{date_range}）國際軌道交通相關新聞原始資料，請依格式產出繁體中文週報。

## 搜尋結果原始資料
{news_context}

## ⚠️ 查核原則（防幻覺零容忍）
1. **只能使用上方提供的資料**，禁止自行捏造任何事件或來源
2. **雙重日期查核**：每則新聞發布日必須在 {date_range} 內，不符合者略去
3. **寧缺勿濫**：若無符合條件新聞，直接回報「系統監測正常，本週無符合條件之重大異動」
4. 每則來源必須附上原始網址

## 核心內容（三大領域）
1. **技術新知與政策**：GoA4、CBTC、FRMCS/5G/6G鐵道通訊、列車虛擬聯結、AI預防性維修、數位雙生、SiC半導體牽引、超級電容、氫能、EULYNX標準化
2. **事故分析**：重大營運異常、延誤、出軌、機電設備故障
3. **營運爭議**：勞資爭議罷工、票價政策、大型系統轉換

## 輸出格式（每則新聞一個區塊）

# 【{today.strftime('%Y/%m/%d')}】國際捷運技術新知、重大事件週報
> 資料涵蓋期間：{date_range}

---

### 🔹 [類別] 國家/地區：（簡短有力的主標題）
* **發布/事件日期**：
* **事件摘要**：
  - （列點說明）
* **技術關鍵字**：（英漢對照）
* **資料來源**：[來源名稱](完整 https:// 網址)
* **【臺北捷運啟示】**：（具體參考價值；若無關聯請寫「暫無直接關聯」）

---

## 結尾固定格式
---
📊 **本週統計**：共 N 則符合條件之國際資訊
🔍 **資料來源**：DuckDuckGo News（{len(SEARCH_QUERIES)} 組關鍵字搜尋）
⏰ **報告產出時間**：{today.strftime('%Y年%m月%d日')}
"""


def generate_report(use_powerful_model: bool = False) -> str:
    model_name = MODEL_POWERFUL if use_powerful_model else MODEL_NORMAL
    print(f"[INFO] 使用模型：{model_name}")
    print(f"[INFO] 開始產生報告，日期範圍：{date_range}")

    # Step 1：用 DuckDuckGo 抓新聞（免費，不消耗 Gemini 配額）
    news_context = fetch_news()

    # Step 2：把搜尋結果餵給 Gemini 寫報告（不使用 grounding tool）
    print("[INFO] 正在呼叫 Gemini 產生報告...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=model_name,
        contents=build_prompt(news_context),
        config=types.GenerateContentConfig(temperature=0.2),
    )

    if response.text is not None:
        return response.text

    parts = (
        response.candidates[0].content.parts
        if response.candidates and response.candidates[0].content.parts
        else []
    )
    text_parts = [p.text for p in parts if hasattr(p, "text") and p.text]
    if text_parts:
        return "\n".join(text_parts)

    finish = response.candidates[0].finish_reason if response.candidates else "unknown"
    raise ValueError(f"Gemini 回應未包含任何文字內容。finish_reason={finish}")


def markdown_to_html(md_text: str) -> str:
    import re
    html = md_text
    html = re.sub(r'^# (.+)$',   r'<h1>\1</h1>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$',  r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\[(.+?)\]\((https?://[^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', html)
    html = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)
    html = re.sub(r'^\* (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'^- (.+)$',  r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'^---$', r'<hr>', html, flags=re.MULTILINE)
    html = html.replace('\n\n', '</p><p>').replace('\n', '<br>')
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'Noto Sans TC', Arial, sans-serif; line-height: 1.8;
           max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }}
    h1 {{ color: #1a3a5c; border-bottom: 3px solid #1a3a5c; padding-bottom: 8px; }}
    h2 {{ color: #2c5f8a; }}
    h3 {{ color: #1a6e4a; background: #f0f8f4; padding: 8px 12px;
          border-left: 4px solid #1a6e4a; border-radius: 0 4px 4px 0; }}
    blockquote {{ background: #f5f5f5; border-left: 4px solid #ccc;
                  margin: 0; padding: 8px 16px; color: #666; }}
    li {{ margin: 4px 0; }}
    a {{ color: #2c5f8a; }}
    hr {{ border: none; border-top: 1px solid #ddd; margin: 24px 0; }}
    strong {{ color: #1a3a5c; }}
    .footer {{ background: #f5f8fc; padding: 12px; border-radius: 6px;
               margin-top: 24px; font-size: 0.9em; color: #666; }}
  </style>
</head>
<body>
<p>{html}</p>
<div class="footer">
  📧 此報告由 AI 自動產生 | 搜尋：DuckDuckGo News | 撰寫：Gemini | 僅供參考，請交叉驗證原始來源
</div>
</body>
</html>"""


def send_email(report_text: str, recipients: list) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = report_title
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(report_text, "plain", "utf-8"))
    msg.attach(MIMEText(markdown_to_html(report_text), "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.sendmail(GMAIL_USER, recipients, msg.as_string())
        print(f"[INFO] ✅ 已成功寄送至：{', '.join(recipients)}")
        return True
    except Exception as e:
        print(f"[ERROR] 寄信失敗：{e}")
        return False


def save_report(report_text: str) -> str:
    os.makedirs("reports", exist_ok=True)
    filename = f"reports/report_{today.strftime('%Y%m%d')}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report_text)
    with open("reports/latest.md", "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"[INFO] 報告已儲存：{filename}")
    return filename


def main(use_powerful: bool = False):
    print("=" * 50)
    print("  國際捷運技術週報 自動產生器")
    print(f"  日期：{today.strftime('%Y年%m月%d日')}")
    print("=" * 50)
    report = generate_report(use_powerful_model=use_powerful)
    save_report(report)
    recipient_list = [r.strip() for r in RECIPIENTS.split(",") if r.strip()]
    send_email(report, recipient_list)
    print("\n✅ 全部完成！")
    return report


if __name__ == "__main__":
    import sys
    main(use_powerful="--powerful" in sys.argv)
