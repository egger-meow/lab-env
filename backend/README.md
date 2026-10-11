# Preference Lab Backend

FastAPI／Pydantic／SQLite 後端，提供 Puzzle 與 BRET 引擎、狀態管理、事件紀錄與 ZIP 匯出。

完整安裝、啟動、Token 與測試命令請見 [根目錄 README](../README.md)；研究者操作見 [PILOT_GUIDE](../PILOT_GUIDE.md)，驗收證據見 [M1_ACCEPTANCE](../docs/M1_ACCEPTANCE.md)。

本目錄執行 `uv sync --locked --cache-dir ../runs/uv-cache` 安裝。`scripts/verify_export.py` 提供唯讀離線 ZIP 檢查與已提交動作重播；命令與限制見根目錄 README。
