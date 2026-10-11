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

---

## 2026-10-11: Part B 後端 API 與 SQLite 儲存層實作 (Storage & API Layer)

- **日期**：2026-10-11
- **修改內容**：
  1. SQLite 儲存架構實作（`Storage`）：
     - 建立 `sessions`, `trials`, `trials_private`, `decisions`, `events`, `outcomes`, `instruments_cache` 資料表。
     - 啟用 WAL 模式與 Foreign Key 約束；針對 `:memory:` 提供單一連線持久化以支援單元測試。
     - 實作原子狀態版本遞增（`state_version`）與單調遞增事件序號（`sequence_no`）。
     - 決策提交嚴格實作冪等性保護（`idempotency_key` 唯一約束，重複提交返回原結果而不重複執行）。
     - 匯出規格符合第 10.4 節，打包包含 `manifest.json`, `instruments.json`, `decisions.json`, `events.jsonl`, `outcomes.json`, `private_replay.json` 之 ZIP 封裝。
  2. 實驗業務服務（`LabService`）：
     - 依據 `protocols/pilot_v001.json` 建立試驗 Session，載入並正式驗證題庫素材。
     - 嚴格實作參與者視角資料隔離（`get_participant_trial_view`），剔除 `expected_solution`, `hint_text`, `bomb_index`, `random_seed`。
     - 動作執行器：Puzzle 正確處理 `continue`, `hint`, `next_step`, `solution`；BRET 正確結算點數與立即揭露結果。
  3. FastAPI REST 端點（`app.py`）：
     - 參與者端點：`/api/sessions/join`, `/api/trials/{id}`, `/api/trials/{id}/board`, `/api/trials/{id}/open-decision`, `/api/trials/{id}/decision`, `/api/trials/{id}/next`。
     - 研究者端點（`X-Operator-Token` 保護）：`/api/operator/sessions`, `/api/operator/sessions/{id}`, `/api/operator/sessions/{id}/export`。
- **來源**：Human-origin（規格要求）+ AI-origin（工程實作）
- **影響版本**：
  - schema: `v001`
  - storage: `sqlite_v001`
  - api: `v0.1.0`
- **舊資料可比較性**：初次實作，向前相容。

---

## 2026-10-11: Part B 程式審查修正 (Review Fixes: Auth, Atomicity, Idempotency, Tutorial Isolation)

- **日期**：2026-10-11
- **修改內容**：
  1. 參與者端點身分驗證與 Session Token (P1)：
     - `Session` 增加 `session_token` 欄位；`/api/sessions/join` 正式回傳 `session_token`。
     - 參與者端點實作 `verify_participant_trial` 依賴注入，檢查 `X-Session-Token` Header，嚴格驗證 Token 有效性並阻擋跨 Session 存取 (401 / 403)。
  2. 決策狀態檢查與唯一性限制 (P1)：
     - 僅允許 `status == "decision_open"` 提交決策；非此狀態直接拒絕 (400)。
     - 資料庫加上 `UNIQUE(trial_id, decision_index)` 約束；記錄 `request_payload_hash`。
     - 相同 key 且相同內容視為合法冪等重送；相同 key 但不同內容拋出衝突錯誤 (400)；不同 key 嘗試二次提交受 UNIQUE 約束阻擋。
  3. 決策與後果執行之單一交易原子性 (P1)：
     - 實作 `commit_decision_atomic`，將決策寫入、試驗狀態更新、後果寫入、事件記錄全部包裝在單一 SQLite 交易中。
     - 測試證明若中途任何步驟失敗，所有變更自動 rollback，零殘留孤立記錄或破損狀態。
  4. 題目切換合法性守門與冪等性 (P1)：
     - `/next` 端點強制檢查當前題目必須處於合法終態 (`completed`, `completed_without_decision`, `skipped`, `aborted`)，否則拒絕 (400)。
     - 重複呼叫 `/next` 具備冪等性，安全返回下一題 ID，絕不覆寫或重置下一題已累積的 `active_play_ms` 與狀態。
  5. BRET 教學與示範題隔離 (P1)：
     - 教學題（`is_tutorial=True`）不進行隨機炸彈抽樣，且嚴格禁止主要偏好提交 `/decision` (400)。
     - 接入固定展示步進端點 `/demonstration` 與理解確認端點 `/comprehension`，完成固定教學流程。
  6. 題目不可變快照（按 Hash 鎖定） (P1)：
     - `instruments_cache` 表以 `canonical_hash` 為主鍵，不可變快照保存。試驗運行、資料檢視與 Session ZIP 匯出全部依 `trial.instrument_hash` 讀取，徹底杜絕新版本覆蓋舊試驗題目的問題。
  7. 獨立公開觀察快照與解謎完成標記修正：
     - `public_observation_snapshot` 擴充納入原始線索 `public_stimulus`（包含 puzzle clues/items 或 BRET options）、完整 `action_specs`、`display_order` 與目前狀態。
     - 解謎完成判斷：依據試驗是否曾提交主要決策區分標記為 `completed` 或 `completed_without_decision`。
  8. 完整流程端點擴充：
     - 補齊 `pause`, `resume`, `skip`, `abort`, `feedback`, `solution-followup` 端點與對應事件發射；`Trial.status` 補齊 `paused`。
     - Pydantic 模型及 BRET 欄位採用 `StrictInt`，嚴格阻絕 `bool` 與 `float` 繞過。
- **來源**：Human-origin（審查意見與反例要求）+ AI-origin（工程實作與完整反例測試案例）
- **影響版本**：
  - schema: `v001`
  - storage: `sqlite_v001`
  - api: `v0.1.0`
- **舊資料可比較性**：向前相容，修正可靠性漏洞與狀態機邊界。

---

## 2026-10-11: Part B 第二輪程式審查修正 (Review Fixes 2: Next Step Idempotency, Rejoin Positioning, Tutorial Sequence, Board/Timer Validation, State Version, Atomic Trial Ended)

- **日期**：2026-10-11
- **修改內容**：
  1. `next_step` 冪等重送先於動作推導 (P1)：在任何動作推導或棋盤完成檢查前，優先檢查 `idempotency_key` 與比對請求 payload hash。合法冪等重送直接返回既有決策與結果，徹底解決棋盤已完成時重送報錯問題。
  2. 暫停與終態 Rejoin 正確定位 (P1)：重新 `join_session` 時，當前題目定位依序尋找 `active`, `decision_open`, `paused`；若無進行中題目但有已完成題且尚未前進，停留在該題供使用者查閱與前進；全數完成時標記 `session_completed = True`。
  3. 教學題嚴格狀態與依序步進 (P1)：示範題步進與理解確認操作嚴格要求試驗處於 `active` 狀態（拒絕 `created`, `paused` 及終態）；示範題必須依序執行步進 (`step_index == current_demonstration_index`)，禁止跳步或提前完成。
  4. 棋盤長度與計時器單調非負驗證 (P2)：`/board` 提交嚴格驗證棋盤長度必須符合 `num_positions`、圖案必須屬於題目合法項目且無重複；所有涉及 `active_play_ms` 之端點強制檢驗非負數且不得倒退（單調遞增）。
  5. 客戶端狀態版本校驗 (P2)：`CommitDecisionRequest` 接收客戶端畫面 `state_version`，首次提交時校驗與伺服器當前版本一致，防範使用者在過期舊畫面上作答；合法冪等重送則安全返回原決策。
  6. 冪等請求 Hash 涵蓋 `reason` (Gap A)：計算 `request_payload_hash` 時將 `record.reason` 納入 Canonical Hash，偵測同 key 竄改 reason 的衝突情形。
  7. 生命週期終態事件原子保存 (Gap B)：在 `commit_decision_atomic` 與 `update_trial_state_atomic` 中，將 `trial_ended` 事件與試驗狀態變更置於同一個 SQLite 交易內寫入，涵蓋決策完成、解謎完成、教學完成、理解確認、skip 與 abort，確保零殘留孤立紀錄。
- **來源**：Human-origin（審查反例要求）+ AI-origin（工程實作與全覆蓋測試）
- **影響版本**：
  - schema: `v001`
  - storage: `sqlite_v001`
  - api: `v0.1.0`
- **舊資料可比較性**：向前相容，全面固化真實受試者資料品質與操作可靠性。

---

## 2026-10-11: Part B 第三輪程式審查修正 (Review Fixes 3: Board Save vs Check Answer Separation, Decision Open Freeze, Single Trial Ended Emission)

- **日期**：2026-10-11
- **修改內容**：
  1. 保存棋盤與檢查答案職責分離 (P1)：`/board` 僅負責保存棋盤排布與記錄 `board_changed`，不再調用 `check_board`，不回覆正誤、不洩漏提示訊息、不累加嘗試次數，亦不判定完成。新增 `/api/trials/{id}/check-answer` 作為參與者明確檢查答案的唯一入口，嚴格驗證正誤、累加 `attempts`、記錄 `answer_checked` 並在正解時判定題目完成。
  2. 決策畫面嚴格凍結棋盤與遊玩時間 (P1)：`decision_open` 狀態下，禁止更新棋盤（`/board` 與 `/check-answer` 強制要求狀態必須為 `active`）；`/pause`、`/skip`、`/abort` 端點在 `decision_open` 時強制檢驗 `active_play_ms` 等於凍結值，杜絕決策期間遊玩時間膨脹。待主要決策提交並執行（如 `continue`/`hint`/`next_step`）恢復為 `active` 後，方可恢復遊玩操作與計時。
  3. 終態事件單次精確發射 (P2)：修正 `update_trial_state_atomic`，在寫入更新前先行讀取 `prev_status`，限定僅在「非終態 → 終態」轉換時發射 `trial_ended`。題目已完結後提交的題末回饋 (`/feedback`) 與後續解法揭露 (`/solution-followup`) 僅記錄各自事件，杜絕多筆 `trial_ended` 重複生成。
- **來源**：Human-origin（審查意見與反例要求）+ AI-origin（工程實作與全覆蓋測試）
- **影響版本**：
  - schema: `v001`
  - storage: `sqlite_v001`
  - api: `v0.1.0`
- **舊資料可比較性**：向前相容，完全保真真人操作行為邊界與事件語意。




