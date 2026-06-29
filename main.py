"""
國際捷運技術週報 自動產生器 v4
- SDK  : google-genai (新版)
- 搜尋 : DuckDuckGo（免費、無配額限制）
- 寄信 : Gmail SMTP
- 排程 : GitHub Actions（時間請見 .github/workflows/weekly.yml）
"""

import os
import re
import sys
import time
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from duckduckgo_search import DDGS
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
# 20 組精準查詢詞（技術新知 / 事故分析 / 營運爭議 / 地區官方）
# timelimit="m" 近一個月廣撈，Gemini 再嚴格篩選 7 天內
SEARCH_QUERIES = [
    # A. 技術新知：次世代信號與通訊
    f"CBTC GoA4 autonomous train signalling deployment {today.strftime('%Y')}",
    f"FRMCS 5G railway communication migration trial {today.strftime('%Y')}",
    f"virtual coupling train platooning ETCS {today.strftime('%Y')}",
    f"EULYNX interlocking standard railway Europe {today.strftime('%Y')}",
    # B. 技術新知：智慧化與數位雙生
    f"digital twin railway metro predictive maintenance {today.strftime('%Y')}",
    f"edge AI artificial intelligence metro fault detection {today.strftime('%Y')}",
    f"big data cybersecurity railway operations {today.strftime('%Y')}",
    # C. 技術新知：硬體與能源
    f"SiC silicon carbide traction inverter metro train {today.strftime('%Y')}",
    f"supercapacitor regenerative braking energy storage metro {today.strftime('%Y')}",
    f"hydrogen fuel cell train test pilot route {today.strftime('%Y')}",
    f"new rolling stock EMU electric train first run {today.strftime('%Y')}",
    # D. 事故分析
    f"metro subway train derailment accident {today.strftime('%B %Y')}",
    f"metro subway signal failure power outage disruption {today.strftime('%B %Y')}",
    f"railway train door mechanical fault delay {today.strftime('%B %Y')}",
    f"鉄道 事故 脱線 信号障害 遅延 {today.strftime('%Y年%m月')}",
    f"지하철 사고 탈선 신호 장애 {today.strftime('%Y년 %m월')}",
    # E. 營運爭議
    f"metro subway transit workers strike labor dispute {today.strftime('%B %Y')}",
    f"subway fare increase transit authority policy {today.strftime('%B %Y')}",
    # F. 地區官方
    f"MTR Hong Kong MRT Singapore incident announcement {today.strftime('%B %Y')}",
    f"railway metro official press release news Japan Korea Europe {today.strftime('%B %Y')}",
]


def run_duckduckgo_searches() -> str:
    """執行 20 組 DuckDuckGo 搜尋，timelimit=m 廣撈近一個月，Gemini 篩 7 天"""
    total = len(SEARCH_QUERIES)
    all_blocks = []
    with DDGS() as ddgs:
        for i, query in enumerate(SEARCH_QUERIES, 1):
            print(f"[INFO] 搜尋 {i:02d}/{total}：{query}")
            try:
                results = list(ddgs.text(query, max_results=8, timelimit="m"))
                if results:
                    block_lines = [f"【搜尋 {i}】{query}"]
                    for r in results:
                        block_lines.append(
                            f"  標題：{r.get('title','')}\n"
                            f"  摘要：{r.get('body','')}\n"
                            f"  連結：{r.get('href','')}"
                        )
                    all_blocks.append("\n".join(block_lines))
                else:
                    all_blocks.append(f"【搜尋 {i}】{query}\n  （本次無結果）")
                time.sleep(1.2)
            except Exception as e:
                all_blocks.append(f"【搜尋 {i}】{query}\n  ⚠️ 搜尋失敗：{e}")
    return "\n\n".join(all_blocks)


# ─────────────────────────────────────────────────────
def build_prompt(search_results: str) -> str:
    return f"""
# 角色
你是專業捷運機電技術分析師，服務對象為台北市政府捷運工程局處長及技術同仁。

# 任務
以下是透過 DuckDuckGo 搜尋引擎（近一個月範圍）蒐集到的國際軌道交通原始資料。
請嚴格依照三大領域與查核原則，整理出週報（目標涵蓋期間：{date_range}）。

## 搜尋結果（原始資料，請分析整理，勿直接複製）
{search_results}

## ⚠️ 最高查核原則（零容忍，違反即捨棄該則）
1. **只使用搜尋結果中出現的資訊**，禁止自行編造
2. **日期判斷（依類別分級）**：
   - 事故類、爭議類：「新聞發布日」與「事件發生日」皆須在 {date_range} 內
   - 技術新知類：「新聞發布日」或「技術發表/測試日」在過去 30 天內即可納入
3. **禁止舊聞充數**：舊案調查報告、歷史事故回顧（超過 30 天）一律捨棄
4. **無付費牆**：確保來源 URL 可公開存取，付費牆來源捨棄
5. **寧缺勿濫**：確實無符合條件者，直接回報「本週無符合條件之重大異動」

## 三大核心監控領域

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

## 優先監控區域
日本、韓國、美國、歐洲（英德法）、新加坡、香港、澳洲

## 輸出格式（每則獨立區塊，目標 5–12 則）

# {report_title}
> 資料涵蓋期間：{date_range}（技術新知可納入近 30 天）

---

### 🔹 [A技術/B事故/C爭議] 國家/地區：（一句有力主標題）
* **發布/事件日期**：（原文發布年月日）
* **事件摘要**：
  - （列點精要說明，3–5 點）
* **技術關鍵字**：（英漢對照，例：FRMCS / 未來鐵道行動通訊系統）
* **資料來源**：[來源名稱](完整 https:// 網址)
* **【臺北捷運啟示】**：（對北捷系統的具體參考價值；無關聯請寫「暫無直接關聯」）

---

## 結尾（必填）
---
📊 **本週統計**：共 N 則（A技術 N 則 / B事故 N 則 / C爭議 N 則）
🔍 **執行搜尋次數**：本次共執行 {len(SEARCH_QUERIES)} 次（DuckDuckGo）
⏰ **報告產出時間**：{today.strftime('%Y年%m月%d日')} 週{["一","二","三","四","五","六","日"][today.weekday()]}
"""


# ─────────────────────────────────────────────────────
def generate_report(use_powerful: bool = False) -> str:
    model_name = MODEL_POWERFUL if use_powerful else MODEL_NORMAL
    print(f"[INFO] 模型：{model_name}")
    print(f"[INFO] 期間：{date_range}")

    # Step 1：DuckDuckGo 搜尋
    print("[INFO] 開始 DuckDuckGo 搜尋...")
    search_results = run_duckduckgo_searches()
    print(f"[INFO] 搜尋完成，字元數：{len(search_results)}")

    # Step 2：Gemini 分析整理
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=model_name,
        contents=build_prompt(search_results),
        config=types.GenerateContentConfig(temperature=0.2),
    )

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
  📧 此報告由 AI 自動產生 | Gemini + DuckDuckGo | 僅供參考，請交叉驗證原始來源
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
    print("  國際捷運技術週報 自動產生器 v4")
    print(f"  日期：{today.strftime('%Y年%m月%d日')}")
    print(f"  模式：{'強化版' if use_powerful else '標準版'}")
    print(f"  搜尋：DuckDuckGo（無配額限制）")
    print("=" * 50)

    report = generate_report(use_powerful)
    save_report(report)
    recipients = [r.strip() for r in RECIPIENTS.split(",") if r.strip()]
    send_email(report, recipients)
    print("\n✅ 完成！")


if __name__ == "__main__":
    main()
