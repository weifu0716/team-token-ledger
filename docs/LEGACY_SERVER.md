# 舊版 v0.1 伺服器流程（非預設）

v0.2主流程在根目錄README與SETUP：每日PDF存同步資料夾、老闆本機查收件。新安裝請用daily/install-windows.ps1。

舊版的ledger/server.py、collector.py網路上傳、employee/install-windows.ps1、install-macos.sh、Dockerfile及compose.yaml保留供已在用伺服器的人查歷史，不是新版安裝入口。

既有部署的完整文件以[v0.1.0儲存庫版本](https://github.com/weifu0716/team-token-ledger/tree/v0.1.0)為準；主程式核心回歸測試仍保留。

![舊版伺服器看板，合成資料](assets/dashboard.png)

換成每日PDF時先移除舊上傳排程、備份舊資料，不自行刪除或混用兩套。舊配對檔與管理金鑰不會用在新版。