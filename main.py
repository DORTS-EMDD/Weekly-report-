"""
國際捷運技術週報 自動產生器 v3
- SDK  : google-genai (新版，非 google-generativeai)
- 搜尋 : Google Search Grounding（內建於 Gemini）
- 寄信 : Gmail SMTP
- 排程 : GitHub Actions 每週一 08:00 台灣時間
"""

import os
import re
import sys
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google import genai
from google.genai import types

# ── 環境變數（由 GitHub Secrets 注入）────────────────
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GMAIL_USER     = os.environ["GMAIL_USER"]
GMAIL_APP_PASS = os.environ["GMAIL_APP_PASS"]
RECIPIENTS     = os.environ["RECIPIENTS"]        # 逗號分隔

# ── 模型設定 ──────────────────────────────────────────
MODEL_NORMAL   = "gemini-3.1-flash-lite"   # 預設：輕量省配額
MODEL_POWERFUL = "gemini-3.5-flash"        # 強化：細節更完整

# ── 日期 ──────────────────────────────────────────────
today      = datetime.date.today()
week_start = today - datetime.timedelta(days=7)
date_range = (
    f"{week_start.strftime('%Y年%m月%d日')} 至 {today.strftime('%Y年%m月%d日')}"
)
report_title = f"【{today.strftime('%Y/%m/%d')}】國際捷運技術新知、重大事件週報"


# ─────────────────────────────────────────────────────
def build_prompt() -> str:
    return f"""
# 任務
你是專業捷運機電技術分析師。請使用內建的 Google Search 工具，
在今日（{today.strftime('%Y年%m月%d日')}）針對下列 12 組關鍵字各執行一次獨立搜尋，
產出涵蓋過去 7 天（{date_range}）的國際軌道交通重大資訊週報。

## 強制執行的 12 次搜尋（每次主題不同，必須全部執行）
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
1. **雙重日期查核**：每則新聞「新聞發布日」與「事件實際發生日」皆須在 {date_range} 內
2. **禁止舊聞充數**：舊案調查報告、歷史回顧一律捨棄
3. **免費公開原則**：禁止引用付費牆網站；優先使用官方新聞稿
4. **寧缺勿濫**：無符合條件者直接回報「系統監測正常，本週無符合條件之重大異動」

## 核心監控領域
1. **技術新知**：GoA4、CBTC、FRMCS/5G/6G、虛擬聯結、AI維修、數位雙生、邊緣運算、SiC牽引、超級電容、氫能、EULYNX
2. **事故分析**：出軌、號誌故障、機電異常、延誤（分析根因：人為/系統/環境/機電介面）
3. **營運爭議**：勞資罷工、票價政策、系統轉換延宕

## 優先監控區域
日本、韓國、美國、歐洲、新加坡、香港、澳洲

## 輸出格式（每則新聞一個區塊，數量不限，符合條件幾則就寫幾則）

# {report_title}
> 資料涵蓋期間：{date_range}

---

### 🔹 [類別] 國家/地區：（一句有力的主標題）
* **發布/事件日期**：（原文發布年月日）
* **事件摘要**：
  - （列點精要說明）
* **技術關鍵字**：（英漢對照，例：FRMCS / 未來鐵道行動通訊系統）
* **資料來源**：[來源名稱](完整 https:// 網址)
* **【臺北捷運啟示】**：（對北捷系統防護或營運管理的具體參考；若無關聯請寫「暫無直接關聯」）

---
（以上區塊重複，直到所有符合條件的新聞都列完）

## 結尾（必填）
---
📊 **本週統計**：共 N 則符合條件之國際資訊
🔍 **執行搜尋次數**：本次共執行 N 次搜尋
⏰ **報告產出時間**：{today.strftime('%Y年%m月%d日')} 週{['一','二','三','四','五','六','日'][today.weekday()]}
"""


# ─────────────────────────────────────────────────────
def generate_report(use_powerful: bool = False) -> str:
    client     = genai.Client(api_key=GEMINI_API_KEY)
    model_name = MODEL_POWERFUL if use_powerful else MODEL_NORMAL

    print(f"[INFO] 模型：{model_name}")
    print(f"[INFO] 期間：{date_range}")

    response = client.models.generate_content(
        model=model_name,
        contents=build_prompt(),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2,
        ),
    )

    # 新版 SDK：grounding 時 response.text 可能為 None，需從 parts 取出
    if response.text:
        return response.text

    candidates = response.candidates or []
    if candidates and candidates[0].content and candidates[0].content.parts:
        texts = [p.text for p in candidates[0].content.parts if getattr(p, "text", None)]
        if texts:
            return "\n".join(texts)

    finish = candidates[0].finish_reason if candidates else "unknown"
    raise ValueError(f"Gemini 回應無文字內容，finish_reason={finish}")


# ─────────────────────────────────────────────────────
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
    return f"""<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<style>
  body{{font-family:'Noto Sans TC',Arial,sans-serif;line-height:1.8;
       max-width:820px;margin:0 auto;padding:24px;color:#333}}
  h1{{color:#1a3a5c;border-bottom:3px solid #1a3a5c;padding-bottom:8px}}
  h2{{color:#2c5f8a}}
  h3{{color:#1a6e4a;background:#f0f8f4;padding:8px 12px;
      border-left:4px solid #1a6e4a;border-radius:0 4px 4px 0}}
  blockquote{{background:#f5f5f5;border-left:4px solid #ccc;
              margin:0;padding:8px 16px;color:#666}}
  li{{margin:4px 0}} a{{color:#2c5f8a}}
  hr{{border:none;border-top:1px solid #ddd;margin:24px 0}}
  strong{{color:#1a3a5c}}
  .footer{{background:#f5f8fc;padding:12px;border-radius:6px;
           margin-top:24px;font-size:.9em;color:#666}}
</style></head><body>
<p>{h}</p>
<div class="footer">
  📧 此報告由 AI 自動產生 | Gemini + Google Search | 僅供參考，請交叉驗證原始來源
</div></body></html>"""


# ─────────────────────────────────────────────────────
def save_report(text: str) -> str:
    os.makedirs("reports", exist_ok=True)
    path = f"reports/report_{today.strftime('%Y%m%d')}.md"
    for p in [path, "reports/latest.md"]:
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"[INFO] 已儲存：{path}")
    return path


def send_email(text: str, recipients: list) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = report_title
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(markdown_to_html(text), "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_APP_PASS)
            s.sendmail(GMAIL_USER, recipients, msg.as_string())
        print(f"[INFO] ✅ 已寄送至：{', '.join(recipients)}")
        return True
    except Exception as e:
        print(f"[ERROR] 寄信失敗：{e}")
        return False


# ─────────────────────────────────────────────────────
def main():
    use_powerful = "--powerful" in sys.argv
    print("=" * 50)
    print("  國際捷運技術週報 自動產生器 v3")
    print(f"  日期：{today.strftime('%Y年%m月%d日')}")
    print(f"  模式：{'強化版' if use_powerful else '標準版'}")
    print("=" * 50)

    report = generate_report(use_powerful)
    save_report(report)
    recipients = [r.strip() for r in RECIPIENTS.split(",") if r.strip()]
    send_email(report, recipients)
    print("\n✅ 完成！")


if __name__ == "__main__":
    main()
