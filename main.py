"""
國際捷運技術週報自動產生器
- 使用 google-genai SDK (新版)
- 每週一自動執行，寄送報告至指定信箱
"""

import os
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai
from google.genai import types

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


def build_prompt() -> str:
    return f"""
# 任務
你是專業的捷運機電技術分析師。請使用 Google Search 工具，在今日（{today.strftime('%Y年%m月%d日')}）執行至少 12 次獨立搜尋，產出過去 7 天（{date_range}）的國際軌道交通重大資訊週報。

## 強制搜尋指令（必須至少執行以下搜尋，每次搜尋主題不同）
請依序搜尋以下關鍵字組合（英文、日文、韓文各嘗試）：
1. "metro rail accident OR incident {week_start.strftime('%Y')}" site:railway-technology.com OR site:railjournal.com
2. "CBTC OR FRMCS OR 5G railway {today.strftime('%B %Y')}"
3. "metro strike OR fare hike {today.strftime('%B %Y')}"
4. "digital twin OR AI maintenance railway {today.strftime('%B %Y')}"
5. "SiC traction OR supercapacitor train {today.strftime('%B %Y')}"
6. "鉄道 事故 OR 遅延 {today.strftime('%Y年%m月')}" (日文搜尋)
7. "지하철 사고 OR 파업 {today.strftime('%Y년%m월')}" (韓文搜尋)
8. "metro derailment OR signal failure {today.strftime('%B %Y')}"
9. "EULYNX OR train virtual coupling {today.strftime('%Y')}"
10. "MRT incident Singapore OR Hong Kong MTR {today.strftime('%B %Y')}"
11. "subway labor dispute OR strike {today.strftime('%B %Y')}"
12. "hydrogen train OR green rail {today.strftime('%B %Y')}"

## ⚠️ 最高查核原則（防幻覺零容忍）
1. **雙重日期查核**：每則新聞必須同時確認「新聞發布日」與「事件實際發生日」皆在 {date_range} 內
2. **禁止舊聞充數**：禁止使用「舊案調查報告」、「歷史事故回顧」
3. **免費公開原則**：禁止引用付費牆網站，優先使用官方新聞稿
4. **寧缺勿濫**：若窮盡搜尋後無符合條件新聞，直接回報「系統監測正常，本週無符合條件之重大異動」

## 核心內容（三大領域）
1. **技術新知與政策**：GoA4、CBTC、FRMCS/5G/6G鐵道通訊、列車虛擬聯結、AI預防性維修、數位雙生、邊緣運算、SiC半導體牽引、超級電容、氫能、EULYNX標準化
2. **事故分析**：重大營運異常、延誤、出軌、機電設備故障（分析根因：人為/系統/環境/機電介面）
3. **營運爭議**：勞資爭議罷工、票價政策變動、大型系統轉換困難或延宕

## 優先關注區域
日本、韓國、美國、歐洲、新加坡、香港、澳洲

## 輸出格式（每則新聞一個區塊）

# {report_title}
> 資料涵蓋期間：{date_range}

---

### 🔹 [類別] 國家/地區：（簡短有力的主標題）
* **發布/事件日期**：（原文發布年月日，必須在 7 天內）
* **事件摘要**：
  - （列點精要說明）
* **技術關鍵字**：（英漢對照）
* **資料來源**：[來源名稱](完整 https:// 網址)
* **【臺北捷運啟示】**：（具體參考價值；若無關聯請寫「暫無直接關聯」）

---

## 結尾固定格式
---
📊 **本週統計**：共 N 則符合條件之國際資訊
🔍 **執行搜尋次數**：本次共執行 N 次搜尋
⏰ **報告產出時間**：{today.strftime('%Y年%m月%d日')}
"""


def generate_report(use_powerful_model: bool = False) -> str:
    client = genai.Client(api_key=GEMINI_API_KEY)
    model_name = MODEL_POWERFUL if use_powerful_model else MODEL_NORMAL

    print(f"[INFO] 使用模型：{model_name}")
    print(f"[INFO] 開始產生報告，日期範圍：{date_range}")

    response = client.models.generate_content(
        model=model_name,
        contents=build_prompt(),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2,
        ),
    )

    # 新版 SDK 使用 google_search grounding 時，response.text 可能為 None
    # 需從 candidates[0].content.parts 逐一提取文字部分
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
  📧 此報告由 AI 自動產生 | 模型：Gemini | 僅供參考，請交叉驗證原始來源
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
