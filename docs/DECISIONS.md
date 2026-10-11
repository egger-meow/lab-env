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

---

## 2026-10-11: Part A 程式審查修正 (Review Fixes)

- **日期**：2026-10-11
- **修改內容**：
  1. 提示語意分離 (P1)：修正解謎提示文字（包含 `pilot_03` 與 `pilot_04`），移除直接報出特定格數圖案的解答性文字，確保 `hint` 僅提供線索關注方向，嚴格與 `next_step` 的步驟揭露區隔。
  2. 決策驗證強化 (P1)：實作 `validate_decision_record`，強制檢驗接受性字典完整涵蓋題目的合法動作、`selected_action_id` 存在性、`preferred_action_ids` 包含選中動作、標記 `no` 時必須具備 `selection_acceptability_override=True`、以及思考時間非負數。
  3. 素材驗證流水線 (P1)：`Instrument` 預設狀態改為 `drafted`，實作 `validate_instrument` 統一入口，驗證動作規格唯一性、Puzzle 唯一解與合法動作，以及 BRET 4 個選項（含 $k=0$）。通過後正式晉升為 `engine_validated`。
  4. BRET 型別與邊界嚴格檢驗 (P2)：拒絕 `bool` 與 `float`，要求 $N, r, k$ 均為嚴格整數；確認 $k=0$ 與 $k=N$ 為合法邊界；`compute_bret_payoff` 同步強制檢查參數與邊界，杜絕負收益。
  5. BRET 教學結構化 (P2)：為 `tutorial_01` 與 `tutorial_02` 補上明確的 `demonstration`（固定安全與引爆展示）及 `comprehension`（理解確認題目與答案）結構，確保教學階段不走隨機抽取或產出偏好答案。
  6. 匯出規範：新增 `export_schemas` 模組，產出 Pydantic 模型之標準 JSON Schema 至 `schemas/`。
- **來源**：Human-origin（審查意見）+ AI-origin（反例測試與驗證模組實作）
- **影響版本**：
  - schema: `v001`
  - instrument: `puzzle_hints/v001`, `bret_discrete/v001`
  - protocol: `pilot_v001`
- **舊資料可比較性**：素材文字修正為語意保真對齊，不破壞舊資料解法或題型結構。

