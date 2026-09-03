# 國際捷運技術週報專案規則

## 專案入口

- `streamlit_app.py`：Streamlit 手動操作入口
- `main.py`：GitHub Actions 自動產生及寄送入口
- 兩者必須共用相同的搜尋、選題、MaiAgent、PDF 與 Email 模組

## 修改限制

- 預設以 `main` 分支作為正式修復與驗證基準。
- 使用者明確要求時，得直接在 `main` 分支進行 root-cause 修復、測試、commit 與 push。
- 使用者未指定工作分支時，預設使用 `main`。
- 不得因切換分支、同步或合併而覆蓋既有 dirty / untracked 工作。
- 不得改變現有選題規則。
- 不得任意修改正式週報內容生成用的 MaiAgent Prompt。
- 若為修復 semantic validator、schema、grounding 或其他資料驗證 contract 所必要之判定 Prompt，可進行最小必要修改，但不得因此降低驗證標準或改變既有 acceptance contract。
- 不得變更 GitHub Secrets 名稱。
- 不得變更 GitHub Actions 排程時間。
- 不得變更 Streamlit `session_state` key。
- 不得改變 PDF、Email、JSON 與下載檔名格式。
- 不得把 `streamlit_app.py` 與 `main.py` 合併。
- 程式分割前後報告結果必須一致。
- 修改 production code 前，必須先確認 root cause、影響範圍及既有 contract。
- 優先採用最小 root-cause fix。
- 不得為通過單一測試案例新增 production special case、fallback、重複邏輯或第二套 source of truth。
- Tests passing 是必要條件，但不是充分條件；仍須進行 architecture、scope、source-of-truth 與 regression audit。

## 執行方式

- Streamlit：`streamlit run streamlit_app.py`
- 自動寄送：`python main.py`

## 修改流程

1. 先確認目前 branch、HEAD、worktree 狀態及正式 baseline。
2. 盤點函式、依賴、資料流與既有 contract。
3. 確認 root cause、影響範圍後，採最小 root-cause fix。
4. 執行 import 與語法檢查。
5. 執行受影響的 focused tests。
6. 執行 RC regression 與必要的 full suite。
7. 比較修改前後輸出，確認沒有非預期行為變更。
8. 執行 `git diff`、`git diff --check`、scope 與 source-of-truth audit。
9. 若目前工作分支為 `main`，且使用者已明確要求直接在 `main` 工作，完成完整驗證後得直接 commit 並 push `main`。
10. 若目前工作分支不是 `main`，除非使用者明確要求直接在該分支工作，否則不得擅自切換、reset、clean 或 stash 既有工作；先回報目前狀態與切換風險。
11. 不得使用 `reset`、`clean`、`stash` 或其他方式消除與本次任務無關的既有 dirty / untracked 工作。

## Git 與版本治理

- `main` 為正式可執行版本及 release baseline。
- 使用者明確要求直接在 `main` 工作時，`main` 可作為修復、驗證、commit 與 push 的直接工作分支。
- 所有 production 修改仍必須遵守 root-cause-first、minimal-fix、regression 與 scope audit 原則。
- 不得以直接修改 `main` 為理由省略測試、驗證或 code review 性質的自我審查。
- 不得 force push。
- 不得覆蓋使用者既有未提交工作。
- 若發現目前 HEAD、remote `main` 或正式 baseline 不一致，先確認版本狀態，不得猜測或自行覆蓋。

## Semantic Validation 治理

- Semantic validator 的 schema、grounding 與 acceptance contract 屬正式品質門檻。
- 不得為提高報告通過率而放寬 validator。
- Semantic judge prompt 若因 schema / grounding contract 缺漏而需要修改，應採最小 root-cause fix。
- Semantic judge prompt 的修改不得改變既有 acceptance precedence、evidence source of truth 或 grounding 嚴格性。
- `candidate["evidence"]` 為 authoritative evidence source of truth。
- 不得使用 title、snippet、metadata 或其他非 authoritative evidence 取代 `candidate["evidence"]`。
- 不得新增第二個 semantic validator、fallback validator 或平行判定邏輯。
- `SUPPORTED`、`UNSUPPORTED`、`UNCERTAIN` 等既有 validation contract 不得因單一案例而放寬。

## Authoritative Data 治理

- `core_systems`、`canonical_event_id`、country / resolved_region、authoritative source metadata 等欄位必須維持既有 authoritative owner。
- 不得建立第二個 source of truth。
- Consumer 不得重新推導或覆寫 authoritative fields。
- Canonicalization 與 validation 必須維持既有正確順序。
- 不得使用 fuzzy matching、特殊 candidate ID 分支或 downstream workaround 取代 authoritative canonicalization。

## 報告品質治理

- 正式報告必須維持公務技術週報語氣。
- 「相關機電系統」必須指出具體機電系統，不得使用「依原始候選資料所示之都市軌道系統」等泛化描述。
- 「事件摘要」不得直接複製新聞標題。
- 事件摘要必須以候選資料及 authoritative evidence 為依據。
- 不得以標題改寫或無實質資訊增加的內容冒充技術摘要。
- 不得將廠商宣傳語氣直接視為已驗證技術成果。
- 技術新知應有具體技術、系統、設備、應用或工程變化作為依據。
- 國際週報既有來源、國家與交通系統範圍規則不得任意改變。

## 禁止的修復方式

除非能證明本身就是合法 domain rule，不得為了讓測試或單一案例通過而：

- 新增 fallback
- 新增 special case
- 新增第二套 validator
- 新增第二套 classifier
- 新增重複 canonicalization logic
- 修改正確的 test contract
- 放寬 schema / grounding validation
- 使用 fuzzy matching 掩蓋資料錯誤
- 靜默修改 authoritative data
- 改變既有 source of truth
- 透過 downstream rewrite 掩蓋 upstream root cause
- 無限增加 retry / fallback 層級

## 完成判定

修改完成後，不得只以 tests passing 判定成功。

必須同時確認：

- Root cause 已修復
- 修改範圍最小且合理
- Existing contract 未被偷偷改變
- Source of truth 未分散
- 沒有 duplicated logic
- 沒有新增不必要 fallback
- 沒有新增 special case
- RC regression 通過
- 受影響測試通過
- 必要時 full suite 通過
- `git diff --check` 通過
- production scope audit 通過
- dirty / untracked 狀態未被破壞

若需要大幅擴張修改範圍才能通過測試，應停止並回報 architecture / root-cause 問題，不得自行一路擴張修補。
