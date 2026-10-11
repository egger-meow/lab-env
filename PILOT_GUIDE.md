# PILOT_GUIDE：研究者操作與真人試跑

版本：2026-10-12（Asia/Taipei）。本指南是 M1 可用性探索流程；**尚未執行真人 pilot，未產生真人觀察或研究結論**。工程驗證見 [18 項驗收](docs/M1_ACCEPTANCE.md)，啟動見 [README](README.md)。

## 試跑安排

先由研究者本人完整走一次，再由研究者安排 3–5 位自願參與者逐一操作。這是 AI-origin 的小規模工作預設，並非確定的實驗設計或有效樣本數；本交付不招募、不代簽同意、不發放金錢。每人預留 30–40 分鐘：說明 3–5 分鐘、兩環境約 15–25 分鐘、訪談 5–10 分鐘，實際時間由真人量測。參與者可隨時停止，時間目標不是催答限制。

第一位研究者先玩也屬真人可用性觀察，但已讀私有答案的題目須記為已看過，不能作新題偏好資料。若沒有未見過題目的志願者，這輪只報操作檢查。受試者數、完成數、資料來源均照實填寫，不預先填結果。

## 研究者建立 session

1. 按 README 在同一台電腦啟動 API 與前端。真人使用獨立 DB（如 `backend/data/pilot.sqlite3`），`PREFERENCE_LAB_DECISION_SOURCE=human_gui`；不要使用 E2E 產生的 DB。
2. 研究者專用 profile 開 `http://127.0.0.1:5173/?view=operator`，輸入後端同一個 Operator Token，刷新 session 清單。
3. Mode 選 Pilot。受試者代號留白由系統隨機產生，或用不含姓名的研究代號。選環境順序並記在觀察表：可交替 Puzzle→BRET、BRET→Puzzle。相同參與者不為比較順序重做已見題。
4. 按「建立 Session 並初始化試驗」，確認成功、題數 12、代號與環境順序。記錄 session_id、session code、code commit、`pilot_v001`／protocol 0.1.0、題庫版本及是否已見過題目。不要把加入碼放入公開紀錄。
5. 用另一個 profile／私人視窗開 `?view=participant`，只輸入 session code。確認畫面是受試者視角，不含研究者私有題庫、seed 或其他 session。兩視窗共用 profile 會共享 localStorage，不適合研究者與受試者隔離。
6. 複製 [空白觀察表](docs/PILOT_OBSERVATION_TEMPLATE.md) 到 `runs/human-pilot/` 受控保存；不要將真人填答、訪談或 ZIP 提交 Git。另行取得適用的參與同意；系統沒有內建同意書紀錄功能。

## 對參與者讀的說明

> 這是兩種小遊戲的試用，我們想知道操作與選項是否清楚。請選當下你自己想採用的方式，沒有研究者期待的最佳答案。每個方案先分別回答「可接受／不可接受／不確定」，再選這次實際要執行的一個；可接受不代表一定要選。你可以略過單題、暫停休息或停止整場，不必解釋。Puzzle 的協助在確認後才揭露；BRET 是沒有現金兌換的實驗點數，命中只讓本輪變成 0，不扣之前的點數。

不要說「愛挑戰的人不用提示」「正常人都不想賭」或建議最大期望值。研究者可協助找按鈕、重讀規則，但不替受試者選答案。口頭協助需記錄時間與內容；正式選擇階段避免持續要求放聲思考，以免把訪談時間混入作答負擔。

## 帶完兩個環境

| 階段 | 操作 | 觀察與理解確認 |
| --- | --- | --- |
| Puzzle 練習 2 題 | 點選圖案和位置擺放，按「檢查答案」。未完成可按「我想看看協助選項」，或累積約 45 秒 active play 自動開決策 | 請本人用自己的話說明四個動作：自行再試、不直接填格的方向、揭露下一個正確放置、完整解法。是否分得清提示與下一步？ |
| Puzzle 決策 | 四張卡逐項明確回答 yes/no/unsure，再選本次動作並確認；reason 可不填 | 沒填與「不確定」不同；不可接受仍能選，但需中性再次確認。不要把沒選推成 no。介面目前未詢問平手集合，匯出 preferred_action_ids 為 null 是正常的 |
| Puzzle 後續 | continue／hint／next_step 回到遊戲，最多再玩約 45 秒；solution 結束本題。題末可回饋協助太少／剛好／太多／說不準，再前進 | 決策前解出不會硬塞 continue 答案；記錄 completed_without_decision 題數。後續看解法不改原主要選擇 |
| Puzzle pilot 4 題 | 自然操作，不為測分支要求受試者選 hint 或 solution | 觀察太簡單、太難、是否在乎提示代價，以及題材是否只像換圖案 |
| BRET 教學項目 1 | 看預設安全與命中展示 | 明確說這是預設示範，並非隨機抽到，沒有偏好答案 |
| BRET 教學項目 2 | 完成畫面理解確認；答錯可重讀 | N=10、取前 3 箱：命中率 3/10，命中本輪得 0。請說明下一回合是否獨立；取 0 箱與退出整場有何不同 |
| BRET pilot 4 回合 | 逐項接受性、選擇、確認後看結果，再下一回合 | N=100，r 與 k 由題目給定。兩種結果與機率是否理解？輸贏是否影響後續選擇？點數是否無意義？不要診斷風險人格 |
| 結束 | 畫面顯示「您已完成本次試驗」，研究者刷新並檢視同一 session | 對照剛發生的 trial 狀態、decision、outcome 與 event，接著匯出 |

理解檢查若誤解，先請本人重看規則並再用自己的話說明，記錄每次原話和協助。若兩次說明後仍有關鍵誤解，停止後續偏好收集並記錄原因；這是本輪可用性處置預設，不是智力評價。不要替答以通過檢查。

## 暫停、略過、中止與提交不明

- **暫停**：按「暫停」，或切走分頁自動暫停；確認「試驗已暫停」出現。回來按「繼續試驗」。刷新應回同一 trial；研究者記錄休息起訖與原因（本人可不說）。這不是偏好答案。
- **略過單題**：按略過並確認，trial 記 skipped，沒有主要選擇就不製造答案。已提交的主要答案不因略過而刪除。下一題依原流程前進。
- **停止整場**：立即停止操作，能暫停就先暫停；研究者記錄停止時間、目前 trial 與本人是否願意說明。現有 GUI 沒有獨立整場 abort 控制，「離開」只清掉加入狀態，不會把 session 標為 aborted。關閉視窗是有效退出，不要求本人為了留紀錄繼續答題。
- **研究者記錄中止**：對尚未終結的當前 trial，可用下列本機 API 將其標為 aborted。這只中止一題，**不會中止整個 session 或後面 created 的題目**；整場停止另記觀察表，不再前進。若已 completed，保留原狀，僅另記停止紀錄。不要直接改 DB。
- **提交結果不明**：先停止填答；畫面「重試原提交」會使用原 key／payload 核對。不要另開新 session、換答案或清除 localStorage。研究者若暫時不能確認結果，保留原始資料與錯誤，停止本場並標記待查；不必讓受試者留下等待。

以下由研究者在另一個 PowerShell 視窗執行，替換 session ID 並輸入自己的 Token；不給參與者操作。取得最新版本與時間後中止，衝突時重新檢視，不盲目重送。

```powershell
$pilotSessionId = 'REPLACE_WITH_SESSION_ID'
$pilotOperatorToken = Read-Host 'Operator Token'
$pilotHeaders = @{ 'X-Operator-Token' = $pilotOperatorToken }
$pilotDetail = Invoke-RestMethod "http://127.0.0.1:8000/api/operator/sessions/$pilotSessionId" -Headers $pilotHeaders
$pilotTrial = @($pilotDetail.trials | Where-Object { $_.status -in @('active','decision_open','paused') })
if ($pilotTrial.Count -ne 1) { throw '需要人工確認當前題目；未執行中止' }
$pilotParticipantHeaders = @{ 'X-Session-Token' = $pilotDetail.session.session_token }
$pilotAbortBody = @{ reason='participant_requested_stop'; active_play_ms=$pilotTrial[0].active_play_ms; state_version=$pilotTrial[0].state_version } | ConvertTo-Json
Invoke-RestMethod "http://127.0.0.1:8000/api/trials/$($pilotTrial[0].trial_id)/abort" -Method Post -Headers $pilotParticipantHeaders -ContentType 'application/json' -Body $pilotAbortBody
```

沒有 GUI 整場 abort 是已知缺口；本輪只適合研究者同機監督試跑，不宣稱完整自助撤回／刪除資料流程。若本人提出撤回資料，先記錄要求並由研究者依已說明的資料流程處理；停止不等於自動刪除。重玩已看答案題目只作練習，觀察表記 seen_before；目前 GUI 不自動提供跨 session 的已見題辨識。

## 匯出與核對

1. 在研究者清單刷新，檢視同一 session，核對題目狀態、最近事件與剛提交的選擇。session status 不能單獨作整場中止或完成證據；本輪以 trial 清單和觀察紀錄核對。
2. 按「匯出完整 Session ZIP」，確認實際下載成功，保存到受控 `exports/`。檔案含 `manifest.json`、`instruments.json`、`decisions.json`、`events.jsonl`、`outcomes.json`、`private_replay.json`；後兩份與 instrument 內可含答案／私有隨機資訊，不能交受試者或當公開模型輸入。
3. 按 README 執行 `verify_export.py --expected-source human_gui`。有答案的 trial 應有相應 outcome；教學、skipped、aborted、決策前解出可能沒有 decision。來源標籤由伺服器設定，仍需真人觀察紀錄才能確定是人填的。
4. 另存 code commit（`git rev-parse HEAD`）、當次 protocol 原始 JSON、觀察表及 ZIP 的 SHA256（`Get-FileHash -Algorithm SHA256`）。目前 ZIP 沒有完整 protocol JSON、完整 trial 終態快照或 code commit，不能單靠 ZIP 宣稱已完整重建整場狀態。變更題庫後舊 instrument snapshot 仍在 ZIP。
5. 測試檔一律在 runs 測試資料夾、source=synthetic_mock；不要把測試回合加到真人人數。真人 ZIP 與筆記不得進公開 docs 或 Git。

## 試後訪談與下一輪決策

用中性提問，允許不回答：「哪個操作最不清楚？」「你怎麼區分可接受和這次選擇？」「哪些協助真的影響你？」「有沒有太容易、太難或沒有取捨的題？」「BRET 的機率和輸贏你怎麼理解？」「點數有沒有影響你在不在乎？」「整體會不會太久？哪個步驟最費力？」不要把同一選擇強行解釋成人格。

每場分別記錄：總 wall time（含休息）、休息／研究者介入時間、遊玩 active_play_ms、回答 deliberation_ms、回答包數與實填接受性欄位數。用逐場值與範圍描述負擔；n 小不作人口推論、不報策略優劣或模型成效。

試跑後先彙整，再決定是否修改：

- 未解決的資料錯置、答案提前洩漏、重複執行或無法停止屬阻擋問題，先修復與重驗。
- 任一反覆出現的規則／接受性誤解，先改文字或教學；研究者協助才能完成的地方記錄為未獨立完成。
- 若多數人的 4 題 Puzzle pilot 有至少 3 題在決策前解出，先檢討難度／決策點；若多數人只因困難或無趣想退出，也需調整。這是探索性檢討觸發點，不是預先驗證的統計門檻。
- 若點數不被在乎，先記錄構念限制，不把取 0 箱或高取箱數解釋成固定風險偏好。
- 若流程超過預留時間或回答負擔明顯，先檢討題數／說明。不要在同一 protocol_version 下偷偷改 45 秒或動態調難度。

題意、提示資訊、支付、回饋時間或 protocol 改動，依 docs/DECISIONS.md 記錄來源、原因、版本與舊資料可比性。真人理解與可用性確認後再討論凍結題庫及 M2；目前不啟用 formal。
