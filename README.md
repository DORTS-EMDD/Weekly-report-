# 🚇 國際捷運技術週報 AI 自動系統 v3

每週一自動搜尋國際捷運技術新知、重大事故、規範更新，整理成繁體中文週報寄送至公務信箱。

**完全免費 · 不需開電腦 · 雲端自動執行**

---

## 📁 檔案結構

```
Weekly-report/
├── main.py                        # 主程式（產報告 + 寄信）
├── streamlit_app.py               # 競賽展示介面
├── requirements.txt               # 套件：requests, ddgs, streamlit
├── .streamlit/
│   └── config.toml                # Streamlit 主題設定
└── .github/
    └── workflows/
        └── weekly.yml             # GitHub Actions 排程
```

---

## 🚀 設定步驟

### 步驟一：GitHub Secrets（讓自動寄信運作）

Repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret 名稱 | 說明 | 範例 |
|---|---|---|
| `MAIAGENT_API_KEY` | 本局 MaiAgent 雲端 API Key | `maia_...` |
| `MAIAGENT_CHATBOT_ID` | 本局 MaiAgent Chatbot ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `MAIAGENT_API_BASE` | MaiAgent API Base；未填時程式預設 `https://api.maiagent.ai` | `https://api.maiagent.ai` |
| `GMAIL_USER` | 用來寄信的 Gmail 帳號 | `name@gmail.com` |
| `GMAIL_APP_PASS` | Gmail 應用程式密碼（16碼） | `abcd efgh ijkl mnop` |
| `RECIPIENTS` | 收件人，逗號分隔 | `pe9875@gov.taipei,10983@gov.taipei` |

#### 如何取得 Gmail 應用程式密碼
1. 開啟 Gmail 兩步驟驗證
2. 前往 [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. 輸入名稱（如「捷運週報」）→ 建立
4. 複製 16 碼密碼

### 步驟二：手動測試

Repository → **Actions** → **每週捷運技術週報自動寄送** → **Run workflow** → **Run workflow**

> ⚠️ 注意：GitHub Actions 排程為每週一 **00:00 UTC（台灣時間 08:00）**觸發。
> 若 workflow 是在週一 08:00 後才建立，需等下週才會自動執行。
> **請用手動 Run workflow 立即測試！**

---

## 🖥️ Streamlit 展示部署

1. 前往 [share.streamlit.io](https://share.streamlit.io) 以 GitHub 帳號登入
2. **New app** → 選擇此 Repository → Main file: `streamlit_app.py`
3. **Advanced settings → Secrets** 填入：

```toml
MAIAGENT_API_KEY = "maia_..."
MAIAGENT_CHATBOT_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
MAIAGENT_API_BASE = "https://api.maiagent.ai"
GMAIL_USER = "name@gmail.com"
GMAIL_APP_PASS = "abcd efgh ijkl mnop"
DEFAULT_RECIPIENTS = "pe9875@gov.taipei\n10983@gov.taipei"
```

4. **Deploy** → 取得公開展示網址 ✅

> ⚠️ 金鑰請勿直接寫在程式碼中，務必使用 Streamlit Secrets。

---

## 📊 監控內容

| 領域 | 重點追蹤項目 |
|---|---|
| 技術新知 | FRMCS/5G鐵道通訊、CBTC、GoA4、數位雙生、SiC牽引、虛擬聯結、氫能、EULYNX |
| 重大事故 | 出軌、號誌故障、機電異常、延誤（含根因分析） |
| 營運爭議 | 勞資罷工、票價政策、系統轉換延宕 |

**優先監控**：日本、韓國、美國、歐洲、新加坡、香港、澳洲

---

## 💰 費用（完全免費）

| 服務 | 免費額度 | 本系統用量 |
|---|---|---|
| GitHub Actions | 2,000 分鐘/月 | 約 5–10 分鐘/週 |
| MaiAgent 雲端 API | 依本局雲端服務設定 | 約 1 次/週 |
| Gmail SMTP | 無限制 | 1 封/週 |
| Streamlit Cloud | 免費公開部署 | — |

---

## ⚠️ 常見問題

| 問題 | 解法 |
|---|---|
| Actions 今天沒自動執行 | 手動 Run workflow；排程在每週一 00:00 UTC 觸發，新建的 repo 會等下週 |
| 雲端 API 暫時失敗 | workflow 已內建重試（最多 3 次）；請確認 MaiAgent API Key、Chatbot ID 與 API Base |
| 信件未收到 | 確認 GMAIL_APP_PASS 是 16 碼應用程式密碼；公務信箱請將寄件 Gmail 加入白名單 |
| Streamlit MaiAgent 金鑰顯示未設定 | 至 Streamlit Cloud App Settings → Secrets 填入金鑰 |
