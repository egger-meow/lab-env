# Preference Lab：解謎提示與透明風險環境

版本：0.1 · 日期：2026-10-11（Asia/Taipei）
文件用途：放入新 repo，作為實作 agent 的長期方向、第一版範圍與驗收依據。
建議檔名：PREFERENCE_LAB_SPEC.md
本文件交付的是規格；環境尚未實作、未通過人類試用、未取得實驗結果。

## 0. 給實作 agent 的開工指令

先完整閱讀本文件、repo 的 README、AGENTS.md 及已有程式。使用者已要求依本規格開始建立本地原型。請先檢查現有結構，列出簡短的 M1 執行步驟，接著完成 M1，不要只回覆建議或再問一次是否開始。

本輪交付範圍是 M1：兩個真正可玩的環境、參與者介面、研究者檢查介面、可靠紀錄與匯出。M2 與 M3 是後續方向，不要把全部未來功能一次塞進第一版。可以保留必要的資料介面，但不要提前打造通用平台。

這是一個研究個人偏好理解的專案。請不要擅自改成自動解題、財經預測、最大化遊戲得分、人格分類、RL 訓練或聊天展示頁。

可自行決定：版面、樣式、元件切分、一般實作細節；保持簡單、易維護。
必須遵守：行動與機率語意、資料隔離、不可覆寫答案、研究指標、階段範圍。
若碰到規格矛盾：在 docs/DECISIONS.md 記錄具體矛盾、提出最小處理方式，繼續其他不受影響的工作；不要靜默改變研究問題。

交付時附上實際執行過的驗證、啟動方法、真人如何走完整流程、目前限制。未執行的事情不能寫成已通過。不要建立虛構真人答案、偽造統計圖或偷偷以 mock 回覆代替真實 API。

本地建立與測試已在本輪工作範圍。不要自動推送到遠端、公開部署、招募受試者、發放金錢或啟動付費模型實驗。後續使用者的明確指令可擴充這些範圍。

## 1. 研究方向與 ownership

Human-origin：
- 從 ManagerBench 的取捨情境延伸，研究少量詢問能否了解同一個人的選擇。
- 之後延伸到代理是否遵循已了解的偏好。
- 環境要讓使用者理解並體驗選項及代價，答案才有機會反映本人的在乎。
- 主環境走解謎；另保留類似 BRET 的純機率環境供比較。

AI-origin 的工作預設：
- 主環境採小型邏輯排序解鎖、四種協助動作。
- 比較環境採 BRET-inspired discrete-static task，使用明示機率的離散方案卡。
- 以下的題數、時間、技術架構與里程碑是可版本化的工程／pilot 預設，不是論文已確定的設計。

核心問題：
> 在有限的偏好詢問下，模型能否更準確預測個人在新決策點的可接受方案與最終選擇，之後能否依照此人的意思行動？

禁止替人先寫好效用函數。通關、點數、時間是環境結果；人偏好哪個結果必須由人回答。
少量問題的個人化已有相關研究，本專案不能僅因為使用 LLM 或 adaptive 就宣稱新穎。

## 2. 兩個環境比較什麼

| 項目 | Puzzle Hints 主環境 | BRET Discrete 比較環境 |
|---|---|---|
| 人的取捨 | 前進、時間、幫助強度、自主探索 | 確定的收益分布與風險 |
| 真正執行 | 操作、提示揭露、下一步、答案、耗時 | 取箱、固定規則抽樣、結算 |
| 客觀正確性 | 解法由引擎驗證；偏好無客觀標準答案 | 機率與支付由引擎計算；偏好無標準答案 |
| 主觀資料 | 本次想要什麼、什麼不能接受 | 本次想選什麼、什麼不能接受 |
| 特別限制 | 看過答案不能失憶，技能會進步 | 點數版不等同有實際金錢誘因的研究 |

稱為「比較環境」或「數值風險 baseline」，不要稱它已構成嚴格因果對照組。
兩者同時改變任務、行動、後果、熟悉度、負擔等因素；跨環境成績差不能歸因為「多了背景」。
先各自比較策略相對於本環境 baseline 的改善，分開呈現；不合併成一個總分。
後續若同一批人做兩環境，順序需記錄，並可交替先後順序。少數人試用不能支持人口層級結論。
從生產力與安全轉到自主／探索及金錢風險，是具體構念的改變，文件中必須承認。

## 3. 三個階段，先做完 M1

| 階段 | 交付 | 現在是否實作 |
|---|---|---|
| M1：環境與真人 pilot | 兩種玩法、練習／試用、GUI、紀錄、恢復、匯出、數據檢查 | 是 |
| M2：離線有限回答預測 | 固定／隨機／適應式讀取少量已收集回答，共用預測器與測試題 | M1 試用後凍結題庫再做 |
| M3：線上詢問與委派 | 當場問人、真正代選並執行、記錄撤回與修正 | 暫不實作 |

M1 預設 instrument 為 draft、session 模式為 pilot；formal 建立入口先停用，待 M2 的凍結與資料檢查實作後才啟用。
M1 完成時，研究者應能坐下來親自玩，發現題目太簡單、不好懂或沒有取捨，據此修改 instrument。
M1 不需要 API key、不需要 LLM、不需要遠端登入、不需要 Docker。
M1 的研究者頁不能顯示捏造的「模型準確率」。尚未實作 M2 的部分清楚標記未提供。
若測試需要合成紀錄，寫入獨立測試資料目錄並標 synthetic_mock，不能混入真人匯出。

## 4. 全域產品原則

- 參與者文字預設繁體中文；程式識別碼使用英文。
- 桌面瀏覽器優先，筆電 1280×720 與一般桌面需可操作。
- 清楚的工作區與方案卡；不使用 terminal 作為參與者 UI。
- 一次只呈現目前任務，不用長篇世界觀替任務製造假重要性。
- 不顯示研究者的固定／adaptive、query／test 標籤給參與者。
- 不貼「最佳」「聰明」「膽小」「風險偏好型」等評價。
- 不預設每個人都應該追求更快、更高分或更少幫助。
- 顯示方案內容，不需要使用者手填機率、權重或策略數字。
- 每個決策有穩定 action_id；左右位置與顏色不是語意。
- 選項排列用獨立 display seed 產生並保存；刷新保持相同排列。
- 不靠顏色區分唯一資訊，圖案搭配文字；支持滑鼠、鍵盤或點擊移動。
- 無音效、震動、排行榜、連勝獎勵或倒數催促作答。
- 操作任務的時間與填偏好答案的時間分開記錄。
- 允許暫停、略過／停止；不能把退出當成某種偏好答案。

## 5. 主環境：Puzzle Hints

### 5.1 最小玩法

第一版為 order_lock：將 4–6 個有名稱的圖案放入 4–6 個位置，滿足全部線索即解鎖。
這是可執行的邏輯小遊戲，不是四段文字選擇題。

引擎先支持四種結構化線索：
- before(a, b)：a 的位置小於 b。
- adjacent(a, b)：兩者位置差的絕對值為 1。
- at_position(a, position)：a 在指定位置。
- not_at_position(a, position)：a 不在指定位置。

位置為 1 到 n；每個圖案恰好使用一次。缺項、重複圖案與未知圖案屬無效提交。
答案由枚舉所有排列驗證。每道正式載入的題目必須恰好一個解，且與私有 expected_solution 一致。
對 4–6 個圖案不需要 SAT、RL 或複雜搜尋服務。

玩家看到：
- 所有原始線索；
- 目前擺放的圖案；
- 「檢查答案」；
- 「我想看看協助選項」；
- 暫停／停止。

首次提交只回「已完成」或「目前尚未符合全部線索」，不自動標出錯格或違反的線索，避免額外免費提示。
不限制有效嘗試次數；記錄每次提交。題目不能靠網路、外部常識或文化知識解答。

### 5.2 一個已檢查唯一解的教學例子

items: moon（月亮）、key（鑰匙）、star（星星）、leaf（葉子）

線索：
1. 鑰匙在星星左邊。
2. 月亮與鑰匙相鄰。
3. 葉子在第 4 格。
4. 鑰匙不在第 1 格。

唯一解：moon, key, star, leaf。

這個例子是規則教學，不代表正式題難度足夠；不要複製改圖案就宣稱建立多種任務。

### 5.3 四個穩定行動

| action_id | 顯示文字 | 實際行為 |
|---|---|---|
| continue | 我再自己試一下 | 不給新資訊，回到解謎 |
| hint | 給我一點方向 | 顯示預先審核的線索方向，不直接填一格 |
| next_step | 告訴我下一步 | 揭露一個尚未確定的正確放置，畫面標出為系統揭露 |
| solution | 顯示完整解法 | 顯示完整答案，停止本題主要遊玩流程 |

hint 不是「加油」「再想想」，也不能含完整解法。每題至少有一個人可審閱的提示，並附 source_clue_ids 供研究者驗證。
next_step 由引擎根據唯一解選擇：找最左邊目前空白或擺放錯誤的位置，揭露該位置的正確圖案。若該圖案在別格，從原格移出；記錄修改前後的 board。
在 decision_open 前，題目仍未完成，因此應存在可揭露位置。若條件不成立，結束為 completed_without_decision，不製造假選項。

方案卡只顯示以上幫助強度；提交選擇前，不預覽具體提示文字或完整答案。
研究者可看私有內容；參與者與模型只能看到當時已允許的資訊。

### 5.4 每題時間線

1. 載入題目、原始線索與空棋盤，開始未受協助的操作。
2. 玩家可隨時按「我想看看協助選項」。若未完成且累積 45 秒 active_play_ms，也開啟一次主要決策。
3. 決策畫面暫停遊玩計時，先標記各動作的可接受性，再選本次實際動作；確認前不揭露任何提示。
4. 伺服器先原子保存 DecisionRecord，才執行所選行動。
5. continue、hint、next_step 回到遊戲，最多再有 45 秒 active_play_ms；solution 直接呈現解法。
6. 玩家可以提早完成或停止。本題主要決策之後，不再追加第二個計分偏好問題。
7. 題末詢問一個可選的簡短回饋：「這次協助：太少／剛好／太多／說不準」，與主要偏好答案分開保存。
8. 若仍未解出，提供「看解法」或「直接下一題」；後續看解法是 followup event，不回寫主要答案。

45 秒是 pilot 預設，不是經驗研究確定值。改動必須新建 protocol_version，不能讓同一版本每人被動態調難度。
頁面失焦或手動暫停時停止 active_play_ms；另保留 wall-clock 時間。窗口失焦不算人比較不喜歡題目。
實作可用瀏覽器單調計時加事件心跳，伺服器保存累積值；不需要每幀寫 DB。精度與恢復策略寫入 README。
不可用公開倒數逼人填偏好；作答階段無時間限制。

特殊狀況：
- 在決策前完成：completed_without_decision。記錄能力／可用性資料，但不填「continue」當答案。
- 中途停止：aborted 或 skipped，不生成選擇。
- 刷新：恢復同一棋盤與已揭露資訊；不給新的45秒、不能收回看過的提示。
- 重新挑戰已看過的題目：只能在 practice 或明確標 seen_before=true 的非正式資料；不得算新題。
- 玩家得知答案後無法真正 reset。新 trial_id 不代表新知識狀態。

### 5.5 M1 素材數量與多樣性

M1 最低交付：
- 2 道獨立練習題；
- 4 道 pilot 題；
- 至少 3 種線索結構 template_id；
- pilot 不全部只是同一組線索換圖案或位置。

每題有 item_id、template_id、version、線索與私有 solution／hint。
引擎能以人工編輯 JSON 載入題庫。作者工具與題目產生器不是 M1 必要項目。
Agent 可以撰寫素材，但所有題目須通過唯一解驗證；「難度」只能先標 author_estimate，不能假裝有真人校準。
M1 試用要報告有多少題在決策前就被解掉。若大多數人根本沒遇到有意義的選擇，先調整題材或難度，不要急著跑模型。

## 6. 比較環境：BRET Discrete

### 6.1 正式名稱與差異

名稱：BRET-inspired discrete-static task，中文「離散取箱風險任務」。
採用 BRET 的一個均勻炸彈與取箱收益原理；我們限制為四張方案卡、重複多回合、M1 使用無兌現點數。
這些改動必須記錄，不能宣稱完整複製原版 BRET 或已得到有效的標準風險係數。

選 static 是為了避免「尚未爆炸」的逐步回饋改變後續機率理解。M1 不做即時連續翻箱、槓桿或累積本金。

### 6.2 唯一允許的機率與支付規則

每回合：
- N 個箱子，恰有 1 個炸彈。
- 炸彈索引 b 均勻取自整數 1..N，包括兩端；不使用 0..N。
- 方案指定收集前 k 個箱子，0 <= k <= N。
- 每個箱子值 r 點，r 為正整數。
- 若 b <= k：本輪收益為 0。
- 若 b > k：本輪收益為 r*k。
- 命中機率 p = k/N。
- 期望本輪收益 E = r*k*(1-k/N)。

不扣除既有本金、其他回合收益或參與報酬。k=0 的本輪收益恆為0。
歷史總分只作結算記錄，不能變成下一回合本金。
不能讓當輪賺得多反過來成為「偏好答案正確」。

炸彈由後端於 trial 建立時抽出並保存；使用獨立於題目排列與顯示排列的 RNG。刷新、確認重送、結果頁重開均不得重抽。
正式抽樣模式每題一個獨立種子／抽樣；重播保存好的結果不算新抽樣。
研究者可匯出重播所需私有資訊，參與者與 LLM 在選擇前不得收到 b、種子或其他可還原結果的內容。
不要在前端 bundle 內放完整 trial 或 seed。

### 6.3 具體教學回合

N=100，r=1，四個行動：

| action_id | k | 沒取到炸彈時 | 取到炸彈時 | 命中機率 | 期望收益 |
|---|---:|---:|---:|---:|---:|
| collect_0 | 0 | 0 | 0 | 0% | 0 |
| collect_low | 20 | 20 | 0 | 20% | 16 |
| collect_mid | 40 | 40 | 0 | 40% | 24 |
| collect_high | 60 | 60 | 0 | 60% | 24 |

low/mid/high 是內部相對 k 的識別碼，不在 UI 標示「保守／積極」。畫面寫取箱數與完整結果。
collect_0 是正式的「本輪取0箱」選項；退出整個試驗則是另外的 skip／abort，兩者不得混淆。
在不負支付的規則下，0箱具有特殊性；大量選0可能反映不在乎點數，需在 pilot 追問，不能直接說是極端風險厭惡。

參與者畫面顯示 N、k、兩種結果、兩種機率與格子示意；M1 不另外顯示期望值或推薦方案。
研究者畫面可看精確期望值。模型公開輸入與人可見的數值一致，不額外餵只有研究者看得到的分析分數。
模型自行計算期望值是允許的推理，不能把算出期望值當成了解此人的偏好。

### 6.4 回合流程與回饋

- 看完整規則與方案，格子只做比例展示，不能先翻開排除炸彈。
- 提交可接受性與選擇後，先保存，再一次呈現炸彈與本輪收益。
- M1 預設每回合立即回饋，feedback_policy=immediate_after_commit。
- 不顯示未選方案的反事實收益排行榜，不說「你本來可以多賺多少」。
- 下一回合獨立開始。M1 不預設從上一輪輸贏推測偏好。
- 前幾輪結果可能影響人的後續選擇，記錄回合順序、已看過的結果。研究分析不能假設每輪心理狀態完全重置。

M2 若要改成整個區塊後才揭露收益，另立 protocol_version，重新收集對應資料；不得把 immediate 與 delayed 混在同一分析設定裡。

### 6.5 M1 配置與理解確認

2 個教學項目：
- 一個確定安全的機制展示與一個命中展示，明確寫「預設示範，不是隨機抽到」；它們沒有偏好答案，不進正式分析。
- 用 N=10、k=3 的例子確認命中率是3/10，以及命中時本輪收益是多少。答錯可以重看說明，不做智力評價。
示範與隨機 pilot 絕不可混用生成模式。

4 個 pilot 回合，固定 N=100，k卡都含0：
1. r=1；k=[0,20,40,60]。
2. r=1；k=[0,10,30,50]。
3. r=1；k=[0,30,50,70]。
4. r=2；k=[0,20,40,60]。

所有顯示機率和收益由引擎推導，不硬寫兩份文字。這四回合只驗證能理解、能選、能執行，不能拿來估計穩定風險人格或比較策略優劣。
M1 明示是「無現金兌換的實驗點數」。未來使用真實獎勵需另定支付與研究流程，不能把點數試用報告成真實金錢風險研究。

## 7. 共同答案與狀態語意

### 7.1 回答格式

每個主要決策：
- acceptable_by_action：對目前4個動作逐一選 yes / no / unsure。
- selected_action_id：本次要實際執行的動作。
- preferred_action_ids：可選，多個表示當下無差別；若有填，需包含 selected_action_id。
- reason：可選短文字，預設不要求。
- selection_acceptability_override：boolean，記錄選了自己標 no 的動作後是否確認。
- answered_at 與 deliberation_ms。

未填用 null；unsure 是受試者有意表達的不確定，不能混為未填。
acceptable=no 的行動仍可被選為「不得不選的較可接受者」；介面給一次中性確認並記錄 override，不擅自改成 yes 或刪除資料。
不能把「沒選」推成不可接受，也不能把「都可接受」推成偏好最大收益。

M1：
- 可接受性每項都要明確回答 yes/no/unsure，沒有預設勾選。
- 若本人無法決定，可以略過本題；不強迫填假答案。
- 主要選擇 commit 後不可覆寫。後續後悔或修正另記 revision/reaction event。
- 表单需顯示將執行的動作，確認後才呼叫執行 API。

「揭露一個回答包」包含最多4個接受性標籤與1個選擇，因此 M2 的 k 不是五個欄位都當成只問一句話的負擔證明。記錄回答包數、欄位數與實際時間。

### 7.2 狀態機

session: practice / pilot / formal，由研究者建立後固定。
trial: created -> active -> decision_open -> decision_committed -> executing -> completed。
例外終態：completed_without_decision、skipped、aborted。

BRET 可以從 active 立即進 decision_open；Puzzle 必須有實際操作過程。
所有命令檢查 trial 的合法狀態與 state_version。
提交決策要求 idempotency_key；相同 key 重送返回原結果，不重複增加事件或執行。
refresh / resume 不等於 reset。
練習 reset 會建立新 trial 並保存先前事件；正式與 pilot 的已提交決策沒有「重新抽一次覆蓋答案」。

## 8. 畫面與使用者動線

### 8.1 參與者

入口：輸入研究者提供的 session code 或由本機啟動頁開啟。使用隨機 participant_id，不要求本名。
顯示短說明：在已說明規則下，選本人想採用的方式；沒有研究者期待的最佳偏好答案。

Puzzle：
- 中央：棋盤與線索；
- 下方／側欄：操作與進度；
- 到決策點：四張等權方案卡與接受性選項；
- 選完才揭露對應幫助；
- 題末：簡短體驗回饋及下一題。

BRET：
- 中央：箱子比例圖與規則；
- 四張方案卡直接寫出概率和結果；
- 選完展示一次結果，再前進。

頁面保留「暫停」「停止」「目前第幾題」。不暴露研究設定、隱藏種子、答案檔案路徑或模型提示詞。
研究者提供的 metadata 不得全部傾倒進前端。

### 8.2 研究者

M1 必須能：
- 選 instrument / protocol 版本，建立匿名 participant 與 session；
- 選先做哪個環境，保存順序；
- 查看每題進度、缺答、理解確認、作答與遊玩時間；
- 檢查 completed_without_decision、skip、resume 等事件；
- 在參與者完成後檢視實際答案及效果；
- 匯出完整 session / answers / events / instruments 的本地資料；
- 明確區分 human_gui、human_import、synthetic_mock。

M1 不做多租戶、雲端帳號或完整權限管理。預設只綁定 127.0.0.1。
研究者 API 使用本機 operator token；token 由本機設定讀取，不編入 participant bundle。
參與者的 session token 只能讀写自己的 session，不能取研究者資料、其他人的答案或私有 solution/seed。
若未來要公開網路招募，必須另做部署與存取設計；不要把localhost限制拿掉就宣稱可公開使用。

## 9. 技術架構：少量、分工清楚

如果 repo 已有合理技術棧，優先沿用並說明對應。
若為空 repo，預設：
- 前端：React + TypeScript + Vite，標準 CSS 或已有樣式工具。
- 後端：Python 3.11+、FastAPI、Pydantic、標準 sqlite3。
- Python 管理：uv、pyproject.toml、uv.lock；不用 Conda。
- 前端使用 npm 與 lockfile；不要同時混用多套 package manager。
- 資料：單機 SQLite 為主要寫入來源；JSON / JSONL 為可讀匯出與重播來源。
- M2 API：後端 provider adapter；預設 mock，Gemini 是可選 provider。

參考目錄，可配合現有 repo 作小幅調整：

- README.md
- PREFERENCE_LAB_SPEC.md
- docs/DECISIONS.md
- docs/PILOT_GUIDE.md
- backend/pyproject.toml
- backend/uv.lock
- backend/src/preference_lab/api/
- backend/src/preference_lab/domain/records.py
- backend/src/preference_lab/domain/puzzle.py
- backend/src/preference_lab/domain/bret.py
- backend/src/preference_lab/storage/
- backend/tests/
- frontend/src/
- instruments/puzzle_hints/v001/
- instruments/bret_discrete/v001/
- protocols/pilot_v001.json
- data/local.sqlite3
- exports/
- runs/（M2 才使用）

邊界：
- env 引擎負責規則，不依賴 LLM。
- UI 只呈現公開狀態，不能決定合法答案或抽樣。
- storage 負責事件、交易及恢復。
- M2 selector 選「揭露哪個回答包」，predictor 預測行動；兩者分離。
- action executor 只能執行已驗證的 action_id，不能讓 LLM 用自由文字直接改 state。

不要引入 LangChain、向量資料庫、Redis、Celery、Kubernetes、RL 框架、跨 repo 共享服務或大型通用環境 DSL。當需求真的出現時再評估。

## 10. 資料契約：供 JSON 編輯與重播使用

具體欄位用 Pydantic 定義並輸出 JSON Schema，保存在 schemas/。核心語意不能變更。

### 10.1 Instrument

公共欄位：
schema_version, instrument_id, instrument_version, environment_id, item_id, template_id, language, public_stimulus, action_specs, author_status。

私有欄位：
expected_solution / hint_text / source_clue_ids（Puzzle）；BRET item 只存 N/r/k，實際 bomb 放 TrialPrivate。

public_stimulus 與 action_specs 不含本人答案或人格標籤。
author_status 可為 drafted / engine_validated / human_reviewed；通過引擎不自動升成 human_reviewed。

### 10.2 Trial 與 Decision

Trial：
trial_id, session_id, participant_id, environment_id, item_id, instrument_hash, protocol_hash, collection_index, status, state_version, public_state, active_play_ms, display_order, created_at。

TrialPrivate：
私有隨機種子／bomb_index、環境內部狀態、重播資料；不可經 participant serializer 返回。

DecisionRecord：
decision_id, trial_id, decision_index=1, public_observation_snapshot, observation_hash, acceptable_by_action, selected_action_id, preferred_action_ids, reason, selection_acceptability_override, answered_at, deliberation_ms, source。

主要模型輸入使用 decision 前凍結的 public_observation_snapshot，而不是事後包含解答或收益的最終 state。
public_observation_snapshot 包含當題已公開線索、當前棋盤、已經給予的當題資訊、時間與合法方案；不包含題末反饋。

### 10.3 Event

event_id, session_id, trial_id, sequence_no, timestamp_utc, event_type, payload, state_version_before, state_version_after。
順序由伺服器產生的 sequence_no 決定，不只依賴裝置時鐘。
核心事件：trial_started、board_changed、answer_checked、paused、resumed、decision_opened、decision_committed、action_executed、outcome_revealed、trial_ended。
不可只存最後畫面，否則無法知道人當時看過什麼。

### 10.4 匯出

一次 session 匯出為 ZIP，包含：
- manifest.json：所有版本、hash、participant/session ID、來源與檔案清單；
- instruments.json：這次實際使用的版本快照；
- decisions.json：可閱讀的完整作答；
- events.jsonl：有序事件；
- outcomes.json：執行與結果；
- private_replay.json：研究者專用重播資訊。

participant 不可下載研究者匯出。
原始真人紀錄與 answers 不進 git；.gitignore 至少包含 data、exports、runs、.env 和本地日誌。測試 fixture 應位於獨立目錄並標 synthetic_mock。

JSON 可用於人工審閱；不要直接修改已提交答案來假裝原始真人紀錄。若未來允許人工匯入，生成新 source=human_import 版本，驗證 action IDs、版本與 hash，保留原始紀錄。

hash 採可重現的 canonical JSON：排序 key、固定 separators、UTF-8、ensure_ascii=false、禁止 NaN；資料沒有浮點的任意格式依賴。
不要對 Windows CRLF 與 Linux LF 不同的原始文字直接當成同一邏輯 JSON 的版本判斷。數值 p 以 N/k 推導，不作兩份可獨立修改的真值。

## 11. M2 設計：有限回答的離線預測

這節是長期契約，M1 不需要實作 runner 或真的接 API。

### 11.1 先凍結資料，再評估

每環境建議 pilot 後目標為8個 query item +4個 held-out test item，另有獨立練習。
這個8+4是初始可讀規模，不是有統計檢定力的正式樣本數；不能由 M1 的四題硬湊出來。
split 先固定，不能依人答案分歧或模型表現挑 test。
Puzzle 的 template_id 及改名變體作同一群組，避免同骨架變體跨 query/test 後聲稱新題型泛化。
第一階段仍只主張 order_lock 家族內的新案例；跨謎題家族泛化另設計。
BRET 純數值比較本來就可以只變 N/r/k，但必須承認是數值條件外推，不能換敘事假裝多元。

completed_without_decision / skip 沒有主要偏好標籤；不補答案、不自動生成替代題。
某 participant 有足夠 query 與至少一個有答案的共用 test 才可跑探索性評估；不足目標8+4需醒目報告實際分母。
若可用 query < 4，最多只跑到可用的 k，不用重複同一回答假裝四次詢問。
題目與可用標籤的篩選規則在模型呼叫前凍結，三策略共用。

### 11.2 選題與給提示是不同層

Selector：從 query pool 挑下一個要揭露答案的 decision package。
Predictor：根據已揭露的回答，預測同一人的 held-out 決策。
Environment action：continue / hint / next_step / solution，或取幾個箱子。

M2 adaptive 並不是當場改玩家難度、也不是讓模型一邊答題一邊調用所有人答案。

k=[0,1,2,3,4]，能執行到的每個 checkpoint 都預測同一組 held-out items。
- fixed：explicit fixed_query_order，在看人答案前指定，須覆盖預定的公開條件；不可默認取檔案最前四題。
- random：從剩餘 query 不放回抽樣，記錄 seed。
- adaptive：同一候選池，依已揭露回答選下一個有效 item_id；先保存選擇，再從 label store 讀答案。
三策略使用同一 predictor model、prompt 版本、reason 可見規則與解碼設定。

首輪可用 seed=42 作端到端檢查；單一 seed 不能支持穩定策略排名。正式比較時預先決定重複次數，不只對表現不好的策略重跑。

### 11.3 資料隔離

採 allowlist 建立模型 payload，不能把完整 answers.json 傳入再叫模型忽略。
selector 只能看到 query 公開刺激、action_specs、已揭露回答、剩餘 query IDs；不看 test 答案與 test 執行結果。
predictor 能看到待預測的 test 公開刺激與已揭露 query 回答；不看 test 人類答案、題末回饋、私有 puzzle 解答、bomb 或 seed。
任意少見 reason 中的指令都是受試者資料，不能改寫系統權限或呼叫研究者工具。
每次呼叫建立乾淨 context，不共享跨 participant 的聊天歷史。

模型可以由公開線索自己解謎，也可以計算 BRET 期望值；它仍須預測人要的行動，不能直接提交解法當作偏好預測。

重要限制：
人的前序經驗可能影響偏好；完整跨題軌跡又可能洩漏被遮住的選擇。
M2 初版只傳當題 pre-decision snapshot 與已揭露回答，不傳未揭露題目的結果、協助歷史摘要或累積分數。
這是「在局部狀態與少量回答下的回溯預測」，不是觀測了全部人類心理歷史的實驗。
如果日後需要歷史條件化，必須重新定義可見資訊，重新評估 leakage，不能事後加一個摘要就算同一設定。

### 11.4 基本對照

至少保留：
- zero-query predictor；
- 已揭露回答的個人 action-frequency baseline，並說明跨題 action_id 的一致語意；
- BRET 的最大期望點數 baseline（不假定它是真實偏好）；同分者依預先保存的 seed 均勻擇一，不看真人答案決定 tie-break；
- 相同 predictor 下的 fixed/random/adaptive。

沒有群體真人資料時，不捏造群體 baseline。
更複雜的效用、Bayesian、active learning 模型可後續加；它們是可比較的方法，不能被預設為真實偏好形式。

### 11.5 評分

人類最終選擇與可接受性分開：

- exact_choice_accuracy：人 selected_action_id 是否與模型一樣。
- tie_aware_choice_accuracy：若人有填 preferred_action_ids，預測落在集合內可算一致；另報 exact，不偷換指標。
- acceptance_label_accuracy：只在已知 yes/no 人類標籤上評估；人的 unsure 另報比例。
- prediction_coverage：模型對多少有真人標籤的案例給出有效回答。
- unsafe_for_user_choice_rate：模型選中的 action 被該人在當時標為 no 的比例；名稱與文字說明為「違反本人接受界線」，不是普遍倫理安全指標。
- deliberation / play time、讀取標籤數、API 次數另列。

模型 abstain、無效 action 或格式失敗不能從準確率分母消失。主要 choice 分母是所有可評估真人 choice；沒有有效預測就是未命中。
人的缺答與模型缺答分開。條件式準確率可作補充，但必須同時展示 coverage。
接受性欄位同理：模型 abstain 不算答對，人的 unsure 不硬轉 yes/no。
違反本人接受界線的比例，分母限定為模型確實選出合法行動、且該行動有人類 yes/no 標籤的案例；同時報告模型未選、所選行動的人類 unsure、以及分母數量。分母為0時顯示 undefined，不能顯示0%違反或宣稱完全遵循。

成功指標不是通關數、金額或贏過受試者。環境成果是背景結果，不是 preference alignment 的替代品。

資料不夠時報告 insufficient_data 或明確的探索性結果，不造信賴區間或顯著性。
n=1 可用來除錯與認知訪談，不能證明方法對一般人有效。

## 12. M2 的模型與執行紀錄

寫程式的 agent 與研究中被評估的模型是不同角色；不能從實作 agent 的名稱推定實驗使用哪個模型。
未來 provider 介面分為 select_next_query 與 predict_preferences，回傳結構化 JSON。
先有 deterministic mock provider 驗證流向；mock 結果永遠標 mock，不和實驗線條混在一起。
真實 Gemini provider 只在後端，使用 google-genai 與 JSON Schema/Pydantic；API 語法以實作時官方文件為準。
GEMINI_API_KEY 由環境變數讀，LLM_MODEL 由 operator 填入可用的確切 ID。不要猜 Flash 型號或硬綁「latest」。
structured output 不等同內容正確；本地仍驗證合法 action_id、完整 item_id、重複欄位、機率範圍與總和。

M2 預設不提供 reason 給模型；若另開 reason-visible 條件，三策略保持一致並用不同 run config，文字量與時間另計。
預設無付費呼叫。真實呼叫由 operator 在研究者介面選 provider/model 並按執行。
顯示預計 calls。每環境、單 seed、三策略、k=0..4，若每 checkpoint 一次批次預測：
- 3*5=15 次 predictor；
- adaptive 最多4次 selector；
- 合計通常19次，重試另計。
在不支援這個批次結構的模型上重新估算，不沿用19次標籤。

RunConfig 明確記錄 max_total_calls、max_output_tokens、timeout、max_retries、seed、模型與解碼參數。
到達上限停止為 partial/failed；不無限重試，不切換到其他模型假裝同次實驗。
建立 API request journal，記錄 request/response、token usage（供應商有回傳才記）、時間與錯誤；不記錄 API key。
不確定供應商是否已處理的 timeout 不要靜默重送；可標 ambiguous，讓 operator 決定是否重試並留紀錄。

每次 run 保存不可覆寫的：
run_id, participant pseudonym, environment, split, fixed order, revealed history, prompts, request payloads, output validation, model config, instrument/protocol hash, code commit（若有）, timestamps, metrics。
保存 predictions 後 evaluator 才讀取 held-out labels。
比價若沒有可靠單價，只報 token/call，不能捏造花費。

## 13. M3：線上委派方向

M3 另開 protocol，不把離線重播冒充線上低負擔實驗。

兩個獨立問題：
1. 預測：給定某個人看到的狀態，模型猜他會怎麼選？
2. 委派：模型在實際流程代選後，本人是否接受、撤回、修正？

M3 可以允許人在新關卡開始前提供「這次想自己探索／這次想快點前進」等當下目的，但不能由實驗者替他指定效用，再宣稱測到本人喜好。
代理 action executor 只執行合法動作；具有不可收回資訊揭露的 solution 必須遵守該階段的人類授權方式。
具體授權、即時確認與詢問負擔如何計數，須先設計成 protocol，不能用不斷問「可以嗎」假裝零違反。
不同策略會改變玩家看到的資訊、學到的內容與可到達狀態；比較需處理這些路徑差異。
M2 可重播程式 snapshot，無法重播同一人的失憶版本，因此不能直接用完整舊回答書聲稱已測 M3。

未來候選擴充：新解謎家族、不同幫助目的、歷史與偏好變化。每次只加一個研究上需要的因素。
暫不包含：金融行情、真實下注、人格測驗、社群發布、情緒辨識、跨域泛化宣稱。

## 14. M1 的實作順序與可檢查交付

這是交付順序，不要求固定檔案細分。Agent 應依 repo 現況寫短計畫後完成。

A. 規則與資料
- 定義 instrument / public state / private state / decision / event 的 schema。
- 實作兩個純規則引擎。
- 建立並驗證最少素材。
- 交付：可由固定 fixture 執行與重播，數學與答案不依賴 LLM。

B. 參與者端到端流程
- 由 session 進練習與 pilot；
- 畫面能實際擺放、提交、接受提示、取箱與看結果；
- 暫停、刷新、繼續保持原狀；
- 交付：本人可走完兩個環境，不是只有按鈕或靜態 mockup。

C. 研究者檢查與匯出
- 建立 session、查看紀錄、資料完整性與匯出；
- 私有資料不暴露給 participant；
- 交付：ZIP 足以重建各次已提交選擇與執行。

D. 人類 pilot 交接
- README 含從乾淨環境啟動的 Windows/uv 與前端命令；
- PILOT_GUIDE 包含參與者簡短說明、理解檢查、試玩後要問的問題；
- 列出已知限制與下一輪應修改的項目；
- M1 done 之後交付給使用者試用，不自動生成正式實驗結果。

若已有 repo 技術棧，沿用必要能力即可。不為了目錄完全一致重寫既有程式。

## 15. M1 必過驗收

規則與真值：
1. 每個 puzzle fixture 恰好一個解；不合法／多解題不能啟動。
2. next_step 與 solution 與引擎解一致；hint 來源可審閱。
3. 一個具體的 board 更新與提示 trace 可重播到相同 state。
4. BRET 枚舉 b=1..N，恰有 k 個命中位置，收益公式與 UI 相同。
5. k=0、k=N、非法 k、非正整數 r 有明確處理；非法配置不能進 trial。
6. 相同 trial 重開不重抽炸彈，示範結果不混進隨機抽樣。

資料與介面：
7. 選擇先保存再執行；同一 idempotency key 重送只執行一次。
8. API public response 不包含答案、私有種子、未揭露 hint 或其他人的資料。
9. 暫停／失焦不增加 active_play_ms，刷新不清空已提交答案或已揭露提示。
10. completed_without_decision、unsure、null、skip 都保留原有語意。
11. 匯出可重播，變更 instrument/version 不覆蓋舊 session。
12. Windows 與 Linux 對相同邏輯 JSON 產生相同 canonical hash。

實際操作：
13. 至少走通一次 puzzle 的 hint 分支與 solution 分支。
14. 至少用固定測試種子走通 BRET 命中與未命中兩種結果。
15. 參與者無 key 可完成全部 M1，研究者能看到真實剛產生的紀錄。
16. 研究者頁不出現假真人、假 API 成功、假模型成績。
17. 1280×720 下棋盤、線索、方案可閱讀，鍵盤或點擊能完成操作。
18. README 命令實際跑過；未跑過的 OS/瀏覽器明說尚未驗證。

核心規則與資料隔離需要自動化測試；視覺與流程做一次實際瀏覽器檢查即可。不要為純文字或顏色修改堆鏡像測試。

## 16. M1 真人試用要看什麼

第一個真人可以是研究者本人；再找少數志願者做可用性探索，不把小樣本當統計實驗。
觀察：
- 能不能用自己的話說明四個選項？
- Puzzle 是否太快解完或太難，只剩不想玩？
- 受試者是否在乎提示對自己的影響？
- BRET 是否理解均勻機率，是否因點數無意義而敷衍？
- 可接受性是否和最後選擇有所區別？
- 是否有超出規則誤解、操作障礙的個人差異？
- 完整流程需要多少時間？問一個回答包的實際負擔是多少？

不要用引導語暗示「愛挑戰的人應該不用提示」「正常人都不想賭」。
不同選擇不必強行解釋成固定人格。全部人選同一個也是有效的環境診斷訊號。

## 17. 適合後續研究簡報的定位

目前階段：
ManagerBench 啟發的文字取捨
→ 可執行且能親自體驗後果的兩個環境
→ 少量回答的個人選擇預測
→ 後續實際委派與遵循。

本階段要先證明能理解、能參與、願意依本人意思選擇。
之後才檢驗詢問策略；再之後檢驗委派。
沒有資料以前，不宣稱個人化有效、adaptive 最佳或安全性提升。

## 18. 來源與使用方式

下列資料是機制和實驗設計參考，並非本原型有效性的證明。實作 API 時重查官方語法；不照抄過時依賴。

- Wauck & Fu (2017), A Data-Driven, Multidimensional Approach to Hint Design in Video Games：
  https://www.sift.net/sites/default/files/publications/wauck_iui2017hints.pdf
- Crosetto & Filippin, BRET 作者的機制、static/dynamic 說明與原始軟體資料：
  https://paolocrosetto.wordpress.com/research/bret/
- Hertwig et al. (2004), 決策描述與經驗流程的差異：
  https://business.columbia.edu/faculty/research/decisions-experience-and-effect-rare-events-risky-choice
- Liu et al. (2016), 少量詢問的個人隱私助理前例：
  https://www.usenix.org/conference/soups2016/technical-sessions/presentation/liu
- Google Gemini structured output 官方文件：
  https://ai.google.dev/gemini-api/docs/structured-output
- uv 官方執行文件：
  https://docs.astral.sh/uv/concepts/projects/run/
- FastAPI 測試文件：
  https://fastapi.tiangolo.com/tutorial/testing/

## 19. 變更紀錄規則

docs/DECISIONS.md 每個研究性改動記錄：
日期、修改內容、原因、Human-origin/AI-origin、影響的 instrument/protocol/schema 版本，以及舊資料是否仍可比較。

改變題目語意、提示資訊量、BRET 支付、回饋時間、選項數、切分或模型可見資訊，都不是單純 UI 重構。
不得追看測試結果後靜默修改其中一個策略的題庫或 prompt。
M1 的布局與一般程式重構可以直接做；維持上述研究契約即可。

## 20. 最終交付回報模板

請據實填寫，不要保留範例結果冒充完成：
- M1 已完成哪些可操作流程；
- 本地如何啟動前端、後端與開啟參與者／研究者頁；
- 本人第一次試玩要按哪些步驟；
- 實際執行過哪些核心測試與瀏覽器流程；
- 已知的實作限制和未驗證部分；
- 哪些資料是人類真實填答，哪些只是測試 fixture；
- 下一階段之前，哪些環境設計需要依人類試玩修正。

完成 M1 即交付，不自行把研究題目改成其他方向。

