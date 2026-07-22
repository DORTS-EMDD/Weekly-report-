# 國際捷運技術週報專案規則

## 專案入口
- streamlit_app.py：Streamlit 手動操作入口
- main.py：GitHub Actions 自動產生及寄送入口
- 兩者必須共用相同的搜尋、選題、MaiAgent、PDF 與 Email 模組

## 修改限制
- 不得直接修改 main 分支
- 不得改變現有選題規則
- 不得修改 MaiAgent Prompt 內容
- 不得變更 GitHub Secrets 名稱
- 不得變更 GitHub Actions 排程時間
- 不得變更 Streamlit session_state key
- 不得改變 PDF、Email、JSON 與下載檔名格式
- 不得把 streamlit_app.py 與 main.py 合併
- 程式分割前後報告結果必須一致

## 執行方式
- Streamlit：streamlit run streamlit_app.py
- 自動寄送：python main.py

## 修改流程
1. 先盤點函式與依賴
2. 建立獨立工作分支
3. 每次只拆一個功能模組
4. 每次搬移後執行 import 與語法檢查
5. 完成後比較分割前後輸出
6. 以 Pull Request 提交，不得直接合併至 main