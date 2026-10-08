# 員工端：安裝一次，自動回報

## 給協助安裝的 AI

先讀本檔，再執行。不要替換成每五分鐘喚醒模型的自動化。安裝程式只用系統排程呼叫 Python。

必要資料：老闆提供的配對檔本機路徑、作業系統、Python 3.11+、實際 Codex 資料根目錄。若無 Python，請從官方安裝來源協助安裝；不要從不明網址下載可執行檔。Windows 還需要 PowerShell 7（`pwsh`）。

先向員工說明：上傳到配對檔指定的老闆伺服器；預設傳時間、模型、Token、專案資料夾名稱。不傳完整路徑與對話。可設定公司專案清單；只有明確選擇 `excerpts` 才傳工作請求片段（最多 180 字）。不要把 JSON 配對憑證貼在聊天、日誌、GitHub 或圖片裡。

## Windows

在已下載／clone 的專案目錄，用 PowerShell 7 執行：

```powershell
pwsh -NoProfile -File ./employee/install-windows.ps1 -Enrollment 'C:\path\enrollment-your-device.json'
```

若 `python` 不是有效 Python，可指定 `-PythonPath 'C:\path\python.exe'`。可選設定：

```powershell
# 以下都是替換用範例路徑；要分享文字時才選 excerpts。
./employee/install-windows.ps1 -Enrollment 'C:\path\enrollment-your-device.json' -ContentMode excerpts -Project 'C:\CompanyWork' -CodexHome 'C:\Users\YOUR_NAME\.codex'
```

預設安裝於使用者的 `.team-token-ledger`：
- `app/`：獨立程式副本，不依賴原下載資料夾。
- `employee-data/config.json`：配對憑證與設定（敏感）。
- `employee-data/collector.db`：讀取位置、去重紀錄、待上傳佇列。
- `employee-data/status.json`：最近執行結果，不含工作原文。
- `runtime/`：隱藏啟動與 PowerShell 7 執行腳本。

排程名稱 `TeamTokenLedger-Employee`，登入時與每 5 分鐘執行；以目前使用者的有限權限執行，不需要存 Windows 密碼，不彈終端視窗。Windows 登出時不執行。

安裝程式會真觸發排程並檢查新的 `LastRunTime`、`LastTaskResult=0`；還要到老闆頁面確認該員工最近回報更新。`phase=no_sources` 表示路徑下沒有可用紀錄，不代表 Token 為零。

## macOS

```sh
bash employee/install-macos.sh --enrollment /path/enrollment-your-device.json
# 可選：--content-mode excerpts --project /Users/YOUR_NAME/CompanyWork
# Python 不在 PATH 時：PYTHON_PATH=/absolute/path/python3 bash employee/install-macos.sh ...
```

建立 `~/Library/LaunchAgents/com.teamtokenledger.employee.plist`，登入後每 300 秒執行。程式放 `~/.team-token-ledger/app`；資料放 `employee-data`。**macOS 腳本提供但未在本次 Windows 開發環境實機驗證**，請用以下結果完成驗收：

```sh
launchctl print gui/$(id -u)/com.teamtokenledger.employee
cat ~/.team-token-ledger/employee-data/status.json
```

## 起算、更新與移除

- 初次配對把既有 JSONL 設成起算基準；不補傳歷史。安裝期間的歷史掃描也不呼叫模型。
- 相同配對檔重跑安裝會保留既有起算點、讀取位置與佇列；不要先刪除資料庫來「修復」。同時先停排程再更新程式。
- 第二台電腦需另一份配對檔；同一配對檔不得複製給不同員工。
- 若需更改文字分享範圍，停排程後在本機修改 `config.json` 的 `content_mode` 與 `projects`；重啟後適用於新收集資料，已排隊和已傳資料不會自動撤回。
- 移除：Windows 執行 `pwsh -File employee/uninstall-windows.ps1`；macOS 執行 `bash employee/uninstall-macos.sh`。它們停止排程、保留資料；再請老闆在頁面撤銷憑證。
- **換配對／離職／換機**：先撤銷舊裝置，再安裝新配對到新的資料目錄。舊佇列保留供處理，不能直接掛到新人名下。

## 排錯

| 狀況 | 下一步 |
|---|---|
| 無法連線 | 確認老闆服務開著、網址可由員工電腦存取；localhost 不是遠端老闆的電腦 |
| 401 | 請老闆檢查憑證是否撤銷；不要反覆重新配對掩蓋資料缺口 |
| 400 | 查裝置時間、版本與回報格式；資料留在佇列，不應強制刪掉 |
| `no_sources` | 查 `CODEX_HOME`；預設 `~/.codex`，讀 `sessions`、`archived_sessions` |
| `partial` | 有格式警示／計數重置；請保留本機紀錄診斷，不要把整份對話上傳 issue |
| 老闆看到「回報中斷」 | 檢查電腦睡眠、登入狀態、排程和網路，與是否有使用 Codex 是不同的問題 |
