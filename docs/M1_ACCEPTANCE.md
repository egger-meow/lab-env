# M1：18 項規格驗收

驗收日期：2026-10-12（Asia/Taipei）。對照 [SPEC §15](../PREFERENCE_LAB_SPEC.md#15-m1-必過驗收)。應用程式基準 commit 為 `e7d8071`；本交付另加文件、離線匯出檢查與 10 個測試案例，未變更研究 protocol／題庫／參與者流程。以下「通過」限定於列出的本地工程證據，**不代表真人 pilot 已通過**。

狀態：13 項工程通過、4 項部分通過、1 項待跨 OS 驗證。未完成項目保留，不宣稱 M1 全部驗收結案。

## 本次實跑證據

環境：Windows PowerShell、Python 3.13.12、uv 0.10.2、Node 24.13.1、npm 11.8.0、lockfile Vite 8.3.4、桌面 Chrome headless 1280×720。Chrome 未在此報告固定完整版本號；其他 OS／瀏覽器未驗證。

- 在 `runs/part-d/clean/` 複製 Git 追蹤檔案、不複製 venv 或 node_modules：`uv sync --locked` 建立新 venv 並安裝 24 個套件；`npm ci --no-audit --no-fund` 安裝 128 個套件成功。使用 repo 內 cache 並允許套件來源連線。不是全新 OS，沒有重裝 Git、Node、uv 或 Chrome，也沒有另做遠端 git clone 驗證。
- 後端最終命令：`uv run --locked --cache-dir ../runs/uv-cache python -m pytest -q --basetemp ../runs/verification/pytest`：**79 passed，1 warning**（Starlette/httpx deprecation）。README 已包含先建立 basetemp 父目錄的步驟。原有 69 項＋本次離線 ZIP 驗證 10 項。
- 乾淨副本 `npm run build`：成功；`npm run lint`：exit 0，本次無診斷輸出。先前 Part C 的 warning 數量不挪作本次結果。
- 乾淨副本 `npm run test:e2e`：**110 個 logged checks 通過**，另含嚴格相等／順序 assertion；完成 12 題，瀏覽器 runtime errors 為空。從研究者表單建立 session、剛產生的 SQLite 紀錄、實際 ZIP 下載皆在同一次流程內核對。見 [browser-report.json](part-d-evidence/browser-report.json)。
- README 的 `uv run … uvicorn …`、`npm run dev …` 與 health 命令實際啟動驗證（測試埠改為 API 18752／Vite 18751，DB 改為獨立 synthetic DB）：自訂 Operator Token 有效、未帶 Token 為 401、前端 HTTP 200、proxy health=ok。PILOT_GUIDE 單題中止命令回傳 aborted。見 [startup-report.json](part-d-evidence/startup-report.json)。未在真人 session 上執行。
- 對瀏覽器實際下載的 ZIP 執行 `scripts/verify_export.py … --expected-source synthetic_mock`：12 trials、9 decisions、71 events，source 僅 synthetic_mock，action_replay=passed。另以測試確認修改 instrument、動作結果、事件數量與錯誤 source 會被拒絕。
- 本次檢視新截圖中的 Puzzle 棋盤／線索、決策彈窗與 BRET 四張方案卡；文字與點擊目標可讀，BRET 長頁需捲動。這是 agent 的視覺檢查，不是人類參與者可用性證據。

安裝時原工作目錄遇到原生 `.node` 檔占用，改在乾淨副本完成 npm ci；受限沙箱最初無法寫全域 uv cache／連線，改用 repo cache 與允許的下載執行。初次 README 測試命令缺 basetemp 父目錄、本次測試 fixture 的 BRET action ID 用錯，均修正後重跑為上列結果；失敗執行不算通過。原 node_modules 已用鎖定依賴離線安裝恢復，仍可能保留被占用的暫存原生檔，不影響 Git 交付。

## 逐項對照

測試名稱可在連結的檔案內搜尋；所有本次測試使用隔離資料，任何 source=human_gui 的測試也是合成 fixture，不能算真人。

| # | SPEC 驗收要求 | 狀態 | 通過證據與尚未完成項目 |
| --- | --- | --- | --- |
| 1 | 每個 puzzle fixture 恰好一解；非法／多解題不可啟動 | 通過 | [test_fixtures_validation.py](../backend/tests/test_fixtures_validation.py) 的六題載入；[test_puzzle_engine.py](../backend/tests/test_puzzle_engine.py) 的多解／無解拒絕；[test_instrument_validation.py](../backend/tests/test_instrument_validation.py) 非法素材驗證。素材數量與至少三 template 亦有檢查 |
| 2 | next_step／solution 與引擎解一致；hint 來源可審閱 | 部分 | `test_execute_next_step`、本次 [test_export_verifier.py](../backend/tests/test_export_verifier.py) 四個 Puzzle 分支重播；JSON 保留 hint_text／source_clue_ids。唯一解與來源結構已檢查，**提示品質與不直接洩漏完整解法仍待真人逐題審閱**，未升格 human_reviewed |
| 3 | 具體 board 更新與提示 trace 可重播到相同 state | 部分 | 本次 verifier 測試保存 `[null,moon,null,null]` 棋盤，再提交 hint／next_step，從 ZIP 的 observation snapshot 重算已執行 payload；E2E 核對實際 revealed_hint。尚無從完整事件串重建最後完整 public_state 的工具／證據，不以動作重播冒充整場 trace 重建 |
| 4 | 枚舉 b=1..N，有 k 個命中位置，收益公式與 UI 相同 | 通過 | [test_bret_engine.py](../backend/tests/test_bret_engine.py) exhaustive enumeration／教學數值；fixtures math 檢查；[BretView](../frontend/src/components/BretView.tsx) 使用後端 action stats，見本次 [方案卡截圖](part-d-evidence/bret-pilot.png) |
| 5 | k=0、k=N、非法 k／r 有明確處理，非法配置不進 trial | 通過 | BRET boundary／validation tests 拒絕越界、非正數、float、bool；instrument validation 檢查四卡與 k=0 |
| 6 | 重開 trial 不重抽；示範不混隨機 | 通過 | [test_api_flow.py](../backend/tests/test_api_flow.py) tutorial isolation／sequential stepping、decision idempotency；BRET browser reload/retry；private 存已抽炸彈。教學沒有偏好 decision |
| 7 | 先保存再執行，同 key 只執行一次 | 通過 | [test_storage.py](../backend/tests/test_storage.py) atomic commit／simulated failure rollback／unique decision；API 重送與 key collision；E2E 丟失成功 response 後逐 byte 重送，DB 與 ZIP 一筆決策 |
| 8 | public 不含未揭露答案、seed、hint 或他人資料 | 通過 | API participant_data_isolation、authentication_and_cross_session_protection、operator auth；未揭露與揭露後狀態分開。範圍是已測 API 契約，未做完整安全稽核；研究者與受試者共用 profile 的風險見 README |
| 9 | 暫停／失焦不加 active time；刷新保留答案與提示 | 通過 | API paused_trial_freezes_play_time、monotonic_timer；E2E blur／reload／pending payload／heartbeat。200ms interval 和約 5s checkpoint 的精度及 localStorage 限制見 README；跨裝置不保證 |
| 10 | completed_without_decision、unsure、null、skip 保持語意 | 通過 | API completion_without_decision、skip／abort；[test_decision_validation.py](../backend/tests/test_decision_validation.py) 接受性與 override；E2E keyboard skip 不生成答案、未詢問 preferred_action_ids 不送。GUI 未提供平手集合輸入，null 不可解讀成無平手 |
| 11 | 匯出可重播；版本改動不覆蓋舊 session | 部分 | storage instrument_hash_immutability／ZIP contents；本次離線 verifier 重新核對 hash 與每個已提交動作。**ZIP 尚缺完整 trial 終態、protocol 原文與 code commit，完整 session 重建未驗證**；指南要求另存 protocol／commit／觀察表 |
| 12 | Windows／Linux 相同邏輯 JSON 的 canonical hash 相同 | 待驗證 | [test_canonical.py](../backend/tests/test_canonical.py) 在 Windows 驗證排序、Unicode、LF/CRLF、hash 重複性與拒絕 NaN/Inf；**未實跑 Linux**，不能把換行模擬當跨 OS 通過 |
| 13 | 實際走通 puzzle hint 和 solution | 通過 | 本次 12 題 E2E 實際提交兩分支、查 DB／ZIP；hint 揭露檢查與動作離線重播通過。屬自動化操作，非真人偏好答案 |
| 14 | 固定測試 seed 走通 BRET 命中與未命中 | 通過 | 本次 `test_export_verifier_fixed_seed_bret`：N=100、k=20，seed=1 得 b=18（命中／0 點），seed=42 得 b=82（安全／20 點）；服務 commit→ZIP→離線結果重播。seed 控制僅測試，不修改 production；瀏覽器本身採獨立隨機回合，未固定兩種結果 |
| 15 | 參與者無 key 完成 M1，研究者看剛產生紀錄 | 通過 | 本次瀏覽器走完 12 題，參與者只持 session 憑證，無模型 key／Operator Token；研究者檢視當次 session、下載 ZIP 並核對 SQLite。真人第一次是否能獨立完成待 pilot |
| 16 | 研究者頁無假真人、假 API 成功、假模型成績 | 通過 | 本次研究者建立／詳細頁來自 API 實際紀錄；決策來源與 ZIP 核對 synthetic_mock，未產生模型準確率。見 [operator-detail](part-d-evidence/operator-detail.png)；不把合成 fixture 當真人 |
| 17 | 1280×720 可讀，鍵盤或點擊可操作 | 通過 | 本次 viewport 截圖視覺檢查＋點擊完整流程＋modal Tab/Shift-Tab loop／keyboard skip。見 [Puzzle](part-d-evidence/participant-puzzle.png)、[決策彈窗](part-d-evidence/decision-modal.png)、[BRET](part-d-evidence/bret-pilot.png)。不是完整無障礙稽核或真人理解證據 |
| 18 | README 命令實跑，未跑 OS／瀏覽器明說 | 部分 | 安裝、後端／前端啟動、health、Token、測試、ZIP verifier 實跑如上；README 明列未驗環境。**全新 OS 工具安裝、遠端 clone、真人 human_gui ZIP 路徑尚未實跑**；synthetic ZIP 使用同一驗證命令與 source=synthetic_mock，不冒充真人匯出 |

## 交給真人前與下一輪待辦

- 研究者逐題審閱 hint 及練習教學，記錄人類審閱；現有 fixture 仍是 draft／engine validation，尚無真人難度校準。
- 依 [PILOT_GUIDE](../PILOT_GUIDE.md) 研究者先跑、再安排 3–5 位自願者；填 [空白觀察表](PILOT_OBSERVATION_TEMPLATE.md)，量測理解、協助介入、決策前解出比例、時間與退出情況。本交付沒有招募或真人資料。
- 本輪若需中止，研究者用已驗證 API 中止當前 trial 並記錄整場停止；GUI 沒有整場 abort，session status 不是可靠的整場停止標記。需自助試跑前補上明確的整場停止流程與驗證。
- 視研究者需求補完整 trial／protocol／code 資訊的可攜匯出與逐事件重建；未完成前保存 DB、protocol、commit 與 ZIP，不只留 ZIP。
- 用同版本 fixtures／canonical tests 在 Linux 實跑並比對 hash；目前沒有 Linux runner 證據。
- 真人操作／題意／負擔可接受後才討論凍結題庫、formal 與 M2。上述缺口未解除，不宣稱完成全部 M1 驗收。
