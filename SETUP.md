# 部署與維護

## 1. 先在老闆電腦跑起來

下載 repo，安裝 Python 3.11+。在專案根目錄：

```sh
python -m unittest discover -s tests -v
python -m ledger server
```

Windows 可用 `pwsh -File boss/start-windows.ps1`；macOS 可用 `bash boss/start-macos.sh`。這是前景服務，關閉終端就停止。開 `http://127.0.0.1:8765`，管理金鑰在使用者目錄 `.team-token-ledger/boss/admin-key.txt`，由本機檔案讀取後貼到登入欄，不放在 URL。

預設只聽 localhost。SQLite 與金鑰在程式資料夾之外。檔案權限必須只讓老闆／服務帳號讀取；POSIX 目錄0700、秘密0600，Windows 另外檢查 ACL（Python chmod 無法代替 NTFS ACL）。不在所有人可讀的共用資料夾放資料。

## 2. 決定員工如何連線

### 同機試行

老闆與合成員工都在同一台電腦：配對網址填 `http://127.0.0.1:8765`。這個網址放到另一台電腦時會指向那台自己，不能用來連老闆。

### 同一局域網或遠端正式試行

建議將服務留在 localhost，前面使用你已有的 HTTPS 反向代理或公司 VPN／安全網路。員工填實際可連線的 HTTPS 網址。例如已有 Caddy 與已指到主機的網域，可使用：

```caddyfile
ledger.example.com {
    request_body {
        max_size 512KB
    }
    reverse_proxy 127.0.0.1:8765
}
```

`example.com` 是範例，不是可用服務。網域、TLS、主機、防火牆、代理的流量限制與備份都由部署者設定。不要直接將 Python 的開發型 HTTP 服務裸露在公網；內建驗證與請求大小限制不取代正式入口的防護。此版本沒有獨立的每員工配額／速率限制，僅適合受信任小團隊試行。

若只做明確批准的局域網 HTTP 測試，可命令列配對時明確傳 `allow_http: true`，員工安裝加 `--allow-http`／`-AllowHttp`。網頁配對介面預設不接受遠端 HTTP；正式試行應用 HTTPS。HTTP 會明文傳遞憑證與工作資料。

### 已有 Docker 主機

```sh
docker compose up -d --build
docker compose exec ledger cat /data/admin-key.txt
```

第二行會顯示**管理秘密**：只能老闆在自己終端看，不貼到聊天或 CI 日誌。volume 保存資料，容器重啟自動恢復；連線仍只綁 localhost，搭配 HTTPS 代理。容器設定限制 256 MB／1 CPU，不呼叫付費模型。主機／網路服務本身可能有費用，應由老闆選擇，不由此程式建立。Docker 路徑在本次環境未實跑。

## 3. 配對與驗收

登入網頁，按「配對員工」，每台電腦產生一份檔案。私下交給該員工，依 `employee/INSTALL.md` 安裝。首次同步後確認網頁的員工標籤、最近回報時間、內容模式與來源狀態。

程式不會在 GitHub 註冊任何員工身分。員工憑證只有自己的上傳權，不可讀取老闆報表／建立或撤銷其他裝置。管理金鑰須妥善保存。

正式使用前完成 `docs/ACCEPTANCE.md`。先分辨本機／雲端工作是否都有紀錄，尤其不同電腦共用帳號時。

## 4. 日常操作

- 預設台灣 UTC+8；可改固定 UTC 位移。夏令時間地區要自己選當日正確位移，這版不含 IANA 歷史時區資料庫。
- 日報按「使用紀錄時間」分日，不按補傳時間分日。若一次請求跨午夜，整筆在回報事件時間當日計入，無法拆分跨日中的計算。
- 網頁每分鐘抓一次自己後端，不用 AI。老闆按匯出才下載 Markdown／CSV，系統不自動傳給 Claude、LINE 或郵件。
- 排程和伺服器沒有雲端費用上限保證；自行部署應監控硬碟／網路。此版本不自動刪資料，請訂保留期限並定期備份、人工清理。

## 5. 更新、備份與撤銷

更新先停止收集排程／老闆服務，備份資料目錄，檢查 CHANGELOG，再更新程式。員工端重新用**原配對檔**安裝，可保留 cursor／outbox；若配對檔已遺失，不要從老闆端重產同名裝置當成更新，依既有 config 找回安全的本機設定或另行換機流程。

備份最簡單方式：停止服務，再複製整個資料目錄（含 SQLite、WAL 若有、管理金鑰）。備份也必須有相同存取控制。不要只複製正在寫入中的單一 `server.db`。

員工離職／換機，網頁撤銷裝置後，舊憑證無法再上傳，歷史報表仍保留。要清除已傳資料需先按公司保留規則備份，再由管理者維護資料庫；v0.1 沒有一鍵刪除工作內容。

管理金鑰輪替：停服務，將 `admin-key.txt` 換成用安全亂數產生的新金鑰（至少32 bytes），只給管理者，再重啟。舊瀏覽器登入失效；員工的個別憑證不受影響。

## API 摘要

所有 API 均以 `Authorization: Bearer …` 驗證，不接受 query token，不提供 CORS。

| 路徑 | 權限 | 行為 |
|---|---|---|
| GET `/health` | 無 | 服務存活，不含任何私人資料 |
| GET `/api/report?day=YYYY-MM-DD&offset=480` | 老闆 | 當日日報與裝置狀態 |
| GET `/api/export.md`、`/api/export.csv` | 老闆 | 同樣日期參數，下載檔案 |
| POST `/api/devices` | 老闆 | `{name, endpoint}` → 一次回傳專屬配對檔 |
| POST `/api/revoke` | 老闆 | `{id}` 撤銷裝置 |
| POST `/api/ingest` | 員工 | `{events: [...], status: {...}}`，一次最多100筆／512 KiB |

前端以純文字呈現員工資料，不執行回報 HTML；CSV 防止儲存格公式注入。員工端遇到 HTTP 重新導向會停止，不將憑證跟隨到另一個網域。
