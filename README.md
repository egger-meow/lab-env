# Preference Lab

本地 M1 研究原型：可操作的 Puzzle Hints 與 BRET-inspired 離散取箱任務，包含研究者建立 session、參與者作答、SQLite 紀錄與 ZIP 匯出。參與者不需要 API key；目前沒有 LLM 呼叫、現金兌換或模型準確率分析。formal／M2／M3 尚未提供。

- [研究者與真人試跑指南](PILOT_GUIDE.md)
- [18 項規格驗收與待辦](docs/M1_ACCEPTANCE.md)
- [完整規格](PREFERENCE_LAB_SPEC.md)、[研究設計決策](docs/DECISIONS.md)

## 安裝（Windows PowerShell）

準備 Git、Python 3.11 以上、uv、Node.js（本次驗證為 24.13.1）與 npm。瀏覽器自動測試另需本機 Chrome。Python 可由 uv 管理。尚未安裝 uv 時，使用 [uv 官方安裝方式](https://docs.astral.sh/uv/getting-started/installation/)；下列驗證使用既有工具，未重裝工具本身。

```powershell
git clone https://github.com/egger-meow/lab-env.git
cd lab-env
cd backend
uv sync --locked --cache-dir ..\runs\uv-cache
cd ..\frontend
npm ci --no-audit --no-fund
cd ..
```

保留 `backend/uv.lock` 與 `frontend/package-lock.json`，不要為排查安裝問題先刪 lockfile。`uv sync` 會安裝預設 dev 測試依賴。第一次安裝需要連線下載依賴。

## 啟動與 Token

開兩個 PowerShell 視窗，均從 repo 根目錄開始。後端視窗：

```powershell
cd backend
$env:PREFERENCE_LAB_OPERATOR_TOKEN = [guid]::NewGuid().ToString('N')
$env:PREFERENCE_LAB_DB = 'data/pilot.sqlite3'
$env:PREFERENCE_LAB_DECISION_SOURCE = 'human_gui'
# 在自己螢幕讀取此值，貼到研究者頁；不要分享給受試者或提交 Git。
$env:PREFERENCE_LAB_OPERATOR_TOKEN
uv run --locked --cache-dir ..\runs\uv-cache uvicorn preference_lab.api.app:app --host 127.0.0.1 --port 8000
```

前端視窗：

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

第三個視窗可檢查 API：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

應回傳 `status=ok`。開啟 [研究者頁](http://127.0.0.1:5173/?view=operator)，在 Operator Token 欄貼入後端同一個值。建立 Pilot session 後，把 `PL-…` session code 交給參與者，於 [參與者頁](http://127.0.0.1:5173/?view=participant) 輸入。完整雙環境 Pilot 共 12 題：6 題 Puzzle（2 練習＋4 pilot）、2 個 BRET 教學項目＋4 個 BRET pilot 回合。

Token 分三種：Operator Token 是研究者管理密鑰；session code 是加入碼；`X-Session-Token` 是加入後自動取得的參與者憑證。參與者不用輸入 Operator Token。未設定研究者環境變數時，程式使用公開的開發預設 `dev-operator-token-local`，只適合本機合成測試。更改環境變數後需重啟後端；程式不自動讀取 `.env`。

| 設定 | 用途與預設 |
| --- | --- |
| `PREFERENCE_LAB_DB` | SQLite 路徑，預設 `data/local.sqlite3`；相對於後端工作目錄 |
| `PREFERENCE_LAB_OPERATOR_TOKEN` | 後端啟動時讀取，研究者頁需填相同值 |
| `PREFERENCE_LAB_DECISION_SOURCE` | 伺服器設定來源；真人 `human_gui`，測試 `synthetic_mock`，不可由參與者選擇 |
| `PREFERENCE_LAB_API_URL` | Vite 開發 proxy 目標，預設 `http://127.0.0.1:8000`；設在啟動前端的視窗 |

目前是同機、受研究者監督的本地原型。Token 與草稿會留在瀏覽器 localStorage；研究者與受試者請用不同瀏覽器 profile／私人視窗，勿讓受試者使用曾登入研究者的 profile。session code 持有人可重新加入該 session，勿公開加入碼。不要直接把開發服務暴露到公網。

## 測試與匯出驗證

另開乾淨 PowerShell 視窗，從 repo 根目錄執行；測試使用開發預設 Token，勿繼承真人伺服器的自訂 Token。

```powershell
Remove-Item Env:PREFERENCE_LAB_OPERATOR_TOKEN -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force runs\verification | Out-Null
cd backend
uv run --locked --cache-dir ..\runs\uv-cache python -m pytest -q --basetemp ../runs/verification/pytest
cd ..\frontend
npm run build
npm run lint
npm run test:e2e
```

E2E 自啟隔離 API/Vite（18732/18731）、Chrome profile 與 SQLite；測試決策標為 `synthetic_mock`，不寫真人 DB。預設 Chrome 位於 `C:\Program Files\Google\Chrome\Application\chrome.exe`；不同安裝位置先設 `$env:CHROME_PATH`。要改測試連接埠，先設 `$env:APP_URL='http://127.0.0.1:18741'` 和 `$env:API_URL='http://127.0.0.1:18742'`。兩埠需空閒，測試失敗會非零退出。報告、截圖、測試 DB 在 `runs/part-c/browser/`；路徑名稱沿用既有 runner，不代表真人資料。

研究者檢視 session 後按「匯出完整 Session ZIP」。保存在根目錄 `exports/`（Git 忽略）後，可離線檢查六個檔案、數量、instrument／observation hash、事件序號，以及每個已提交動作的執行結果：

```powershell
cd backend
# 將檔名替換成剛下載的 ZIP。
uv run --locked --cache-dir ..\runs\uv-cache python scripts/verify_export.py ..\exports\session_YOUR_ID_export.zip --expected-source human_gui
```

成功輸出 `action_replay: passed`；失敗非零退出。這檢查已提交動作的重播，並非整個 session 狀態機的逐事件重建，也不證明資料確由真人填寫。中止或提前解出可沒有 decision；不要要求每場一定有 12 筆答案。ZIP 含私有答案、炸彈位置與 seed，僅交研究者保管。

## 計時、恢復與備份

Puzzle 在 active 狀態以 200ms interval 累加遊玩時間，約每累積 5 秒同步伺服器；棋盤操作、開決策、暫停也攜帶時間。這是瀏覽器計時近似值，並非經校準的毫秒精度或完整單調 wall-clock 測量；排程延遲可能低估。決策畫面凍結遊玩時間，`deliberation_ms` 另記。45 秒開主要決策；選 continue／hint／next_step 後最多再玩 45 秒，不追加主要偏好題。

手動暫停、失焦或隱藏分頁會暫停。刷新恢復相同 trial、棋盤、已揭露資訊與排列，不重新抽炸彈。未同步時間與草稿依賴原 profile 的 localStorage；清除儲存、換裝置／profile 不保證恢復，斷線時也不能保證暫停請求已保存。提交結果不明時使用畫面的「重試原提交」，不要換答案或清除 storage。若收到版本衝突，讀取同步後狀態再確認。

停止兩個服務用各視窗 `Ctrl+C`。備份前先停止後端，再複製實際 SQLite 檔（含若仍存在的 journal）與每場 ZIP 到受控位置；不要在運作中只複製主 DB。保留同次 code commit、protocol 與題庫版本。恢復時讓 `PREFERENCE_LAB_DB` 指向備份再啟動；本次未演練災難恢復。

## 排查問題與驗證範圍

| 現象 | 處理 |
| --- | --- |
| `uv`／`node`／`npm` 找不到 | 確認工具已安裝並重開 PowerShell；先看 `uv --version`、`node --version`、`npm --version` |
| uv cache 存取被拒 | 使用文件中的 repo 內 `--cache-dir`；不要以為程式測試已失敗 |
| 安裝 DNS／下載失敗 | 確認套件來源連線與代理設定，重跑 lockfile 安裝；不能用既有環境冒充乾淨安裝成功 |
| `npm ci` 對 `.node` 檔報 EPERM | 停止自己啟動的 Vite／測試程序再重跑，或用全新 clone；勿終止無關程序或刪 lockfile |
| 前端開了但 API 失敗 | 先查 health，確認後端工作目錄、8000 埠與 Vite proxy 設定；build／preview 不等於配置好 API 的正式部署 |
| 研究者 401 | 確認前後端 Token 一致、後端已重啟；直接開 export URL 沒有認證 header，請用研究者下載按鈕 |
| session code 找不到 | 檢查 code 和後端 DB 路徑；不要另建 session 假裝恢復原資料 |
| 暫停後不知道如何繼續 | 按「繼續試驗」；中止與單題略過的差異見 PILOT_GUIDE |
| E2E server exited／Chrome 找不到 | 確認埠空閒、Chrome 路徑、`backend/.venv/Scripts/python.exe` 存在，並先跑 `uv sync` |
| 測試使用自訂 Operator Token 而失敗 | 在測試視窗清掉該環境變數，保留真人後端原有設定 |

本次實跑證據見驗收表。Windows／本地桌面 Chrome 是已驗證範圍；Linux/macOS、Firefox/Safari、手機、螢幕閱讀器與跨裝置恢復未驗證。真人是否理解選項、是否在乎點數與流程負擔仍待 pilot，不能以自動化測試取代。
