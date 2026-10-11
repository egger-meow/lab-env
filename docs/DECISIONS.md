# Preference Lab 研究與架構決策紀錄 (Decision Log)

本文件依據 [PREFERENCE_LAB_SPEC.md](file:///c:/IDEA/lab-env/PREFERENCE_LAB_SPEC.md) 第 19 節維護。
記錄所有研究性改動、架構選型、規格釐清與最小處理方式。

---

## 2026-10-11: M1 初始化與技術選型

- **日期**：2026-10-11
- **修改內容**：
  1. 技術棧選型確認：
     - 後端：Python 3.11+、FastAPI、Pydantic v2、SQLite3（標準函式庫）、套件管理使用 `uv`。
     - 前端：React 18/19 + TypeScript + Vite + Tailwind CSS，包裝為簡潔標準的單頁應用程式。
     - 資料存放：單機 SQLite 作為核心事件交易資料庫，匯出為符合規範的 JSON / JSONL / ZIP。
  2. 依據規格第 5、6 節，環境邏輯完全純規則運算，不依賴任何外部 LLM 或黑箱 API。
  3. 題目載入：以標準 Canonical JSON 檔案格式載入題庫，所有正式題目必須通過純規則引擎唯一解驗證。
- **來源**：Human-origin（規格要求）+ AI-origin（工程細節實作）
- **影響版本**：
  - schema: `v001`
  - instrument: `puzzle_hints/v001`, `bret_discrete/v001`
  - protocol: `pilot_v001`
- **舊資料可比較性**：初次建立，不影響既有資料。
