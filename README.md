# 🚇 國際捷運技術週報 AI 自動系統

每週一自動搜尋國際捷運技術新知、重大事故、規範更新，整理成繁體中文週報寄送至公務信箱。

**完全免費 · 不需開電腦 · 雲端自動執行**

---

## 📁 檔案說明

```
metro-weekly-report/
├── main.py                        # 主程式（產報告 + 寄信）
├── streamlit_app.py               # 競賽展示介面
├── requirements.txt               # 套件清單
├── .streamlit/config.toml         # Streamlit 主題設定
└── .github/workflows/weekly.yml   # GitHub Actions 排程
```

---

## 🚀 快速上手（3 步驟）

### 步驟一：上傳到 GitHub

1. 到 [github.com](https://github.com) 建立新 Repository（名稱任意，建議設為 **Private**）
2. 把所有檔案上傳到 Repository 根目錄

### 步驟二：設定 GitHub Secrets

到 Repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**，新增以下 4 個：

| Secret 名稱 | 說明 | 範例 |
|------------|------|------|
| `GEMINI_API_KEY` | 從 [aistudio.google.com](https://aistudio.google.com) 取得 | `AIzaSy...` |
| `GMAIL_USER` | 你的 Gmail 帳號 | `yourname@gmail.com` |
| `GMAIL_APP_PASS` | Gmail 應用程式密碼（見下方說明） | `abcd efgh ijkl mnop` |
| `RECIPIENTS` | 收件信箱，逗號分隔 | `pe9875@gov.taipei,10983@gov.taipei` |

#### 如何取得 Gmail 應用程式密碼？
1. 登入 Gmail → 右上角頭像 → 管理 Google 帳戶
2. 安全性 → 兩步驟驗證（必須先開啟）
3. 安全性 → 應用程式密碼 → 選擇「郵件」→ 產生
4. 複製 16 位密碼（格式：`xxxx xxxx xxxx xxxx`）

### 步驟三：手動觸發測試

1. 到 Repository → **Actions** → **每週捷運技術週報自動寄送**
2. 點擊 **Run workflow**
3. 確認信件寄出 ✅

之後每週一早上 08:00（台灣時間）自動執行，不需任何操作。

---

## 🖥️ Streamlit 展示部署

1. 到 [share.streamlit.io](https://share.streamlit.io) 登入（用 GitHub 帳號）
2. New app → 選擇你的 Repository → Main file: `streamlit_app.py`
3. 進階設定（Secrets）貼入：
```toml
GEMINI_API_KEY = "AIzaSy..."
```
4. Deploy → 取得公開展示網址 ✅

---

## 📊 監控內容

| 領域 | 重點追蹤項目 |
|------|------------|
| 技術新知 | FRMCS/5G鐵道通訊、CBTC、GoA4、數位雙生、SiC牽引、氫能 |
| 重大事故 | 出軌、號誌故障、機電異常、延誤分析 |
| 營運爭議 | 勞資罷工、票價政策、系統轉換延宕 |

**監控區域**：日本、韓國、美國、歐洲、新加坡、香港、澳洲

---

## 💰 費用說明（完全免費）

| 服務 | 免費額度 | 本系統用量 |
|------|---------|-----------|
| GitHub Actions | 2,000 分鐘/月 | 約 5 分鐘/週 |
| Gemini API（Flash） | 每天 1,500 次請求 | 約 15 次/週 |
| Google Search Grounding | 5,000 次/月 | 約 12 次/週 |
| Gmail SMTP | 無限制 | 1 封/週 |
| Streamlit Cloud | 免費公開部署 | — |

---

## ⚠️ 注意事項

- Gemini 免費版會用你的資料改善模型，若有資安疑慮請升級付費版
- Gmail 應用程式密碼請妥善保管，不要 commit 到 GitHub
- 公務信箱若有收信過濾，請將 Gmail 加入白名單
