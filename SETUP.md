# v0.2 技術安裝與維護（給協助安裝的AI）

主流程：Windows作業系統排程＋公司Google Drive／OneDrive同步資料夾。不建AI automation、伺服器或新付費服務。

## 前置

- 完整下載專案，在repo根目錄執行。核對來源版本，先讀README與SECURITY。
- 需要PowerShell 7（pwsh）與Python 3.11以上，用Get-Command及版本指令查實際路徑；缺少時協助安裝官方執行環境並遵循操作者權限。
- 收件位置是已同步的本機路徑，不是網頁URL；兩端必須指向同一個雲端資料夾，設為可在本機取得。程式不代辦登入或分享授權。
- 安裝目錄與收件夾分開。私人電腦指定公司專案白名單；未指定會掃描CODEX_HOME內全部專案。
- 兩端時區一致。安裝器記錄固定UTC偏移，目前不自動處理夏令時間。
- 換自v0.1時先移除舊上傳排程，保留歷史資料；不要同時安裝兩套，不自動遷移舊資料。

## 1. 老闆先安裝

準備UTF-8名單，每行一個姓名，#行可註解。同名加部門，如王小明（設計）。

```powershell
pwsh -File .\daily\install-windows.ps1 -Mode boss -SharedFolder "D:\公司同步\AI日報" -Roster "D:\準備資料\names.txt" -PythonPath "C:\Python312\python.exe"
```

路徑只是範例，換成真實位置。預設安裝到 ~/.team-token-daily-boss。日後維護這裡的 names.txt；原匯入名單修改不會自動同步。

收件根目錄自動建立.team-daily-folder.json；所有員工要能看到同一檔案，不用交換配對憑證。每日17:15、登入及每30分鐘執行收件檢查。有昨日資料夾時同時更新昨日結果。

輸出在 results/YYYY-MM-DD-收件檢查.html 及JSON。按「立即檢查收件.lnk」再開results內HTML；這是靜態本機網頁，重跑後需重新整理，不對外提供服務。

## 2. 員工安裝

```powershell
pwsh -File .\daily\install-windows.ps1 -Mode employee -Name "王小明" -SharedFolder "G:\公司同步\AI日報" -PythonPath "C:\Python312\python.exe" -Project "D:\公司工作"
```

預設 ~/.team-token-daily-employee。明確同意分享請求片段才加 -ContentMode excerpts，否則只分享專案短名。非預設紀錄位置用 -CodexHome。

安裝器建立venv並下載ReportLab依賴；之後產報告不需API。-UseExistingPython僅供已備妥依賴的受控環境。17:00產報告，加登入與每30分鐘重試；不喚醒模型。停機多日最多每次補31個未結算日。

## 3. 真實驗收

安裝器真觸發Start-ScheduledTask，確認新的LastRunTime及LastTaskResult=0，再看data/last-run.log末行Completed exit=0。17點前自動執行可能idle，不代表已試過交件；需按「立即補交今天.lnk」完整測試。

驗證链：本機PDF/JSON→員工同步路徑→老闆真的看見→老闆逐筆核對。只看到saved_to_shared_path不是雲端同步成功證明。

## 補交

```powershell
pwsh -File "$HOME\.team-token-daily-employee\runtime\manual.ps1"
pwsh -File "$HOME\.team-token-daily-employee\runtime\manual.ps1" -Day "2026-10-08"
```

當日更新同名檔，隔日補成昨日整日版，仍存昨日資料夾。更早安裝前日期不能回報；**安裝當日從00:00起計，可能包含安裝前當天用量**。已結算日後來才補入日誌，需手動指定日期重產。

老闆核對指定歷史日期：在repo根目錄用已有ReportLab的Python執行：
```powershell
python -m ledger.daily check --shared "D:\公司同步\AI日報" --roster "$HOME\.team-token-daily-boss\names.txt" --day "2026-10-08" --output "$HOME\.team-token-daily-boss\results"
```
一般每日檢查用已安裝快捷方式，會先核對程式指紋。

## 維護與失敗

- 修改MD不會改變日報。安裝程式、設定和啟動器唯讀，執行前比對指紋；更新時重跑同目錄安裝器，先停止該安裝排程再封存新版指紋。
- 同目錄重裝保留姓名、裝置識別及起算日。變更姓名／範圍／時間／路徑需由協助者核對，不要直接刪資料重裝，否則可能產生同名換機衝突。
- 共用位置失聯或根目錄識別不同，先留本機outbox，恢復後補交。不在錯誤路徑新建假收件夾。
- 同名不同裝置拒絕覆蓋。雲端同步沒有跨電腦原子鎖，仍可能產生衝突副本；查收件表extra檔案和同步平台版本歷史。
- 殘留.delivery-lock先確認無交件執行，備份PDF/JSON後再由管理者移除重試。
- bootstrap-status.json是最近一次程式驗證失敗，可能過時，需搭配最新last-run.log及daily-status.json。
- outbox、共用日報、receipt-history.json目前不自動清除；公司自訂保存期限並備份。不要刪老闆history來消除警示。
- 無假勤整合；假日或請假缺件人工判讀。

移除排程：pwsh -File daily/uninstall-windows.ps1 -Mode employee（或boss），報告仍保留。此版只驗證Windows，新版macOS/Linux安裝尚未提供。
