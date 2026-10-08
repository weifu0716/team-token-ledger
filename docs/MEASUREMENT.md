# 量測方法與歸屬限制

## 來源

讀 `$CODEX_HOME/sessions/**/*.jsonl` 與 `archived_sessions/**/*.jsonl`；預設 `~/.codex`。目前解析：
- `session_meta`：session ID、cwd 的最後一層資料夾名稱；不傳完整路徑。
- `turn_context`：模型名稱；未知則顯示 `unknown`，不猜價格。
- `response_item` user：僅在 opt-in 時取最近請求片段，跳過已知環境／AGENTS 注入格式。
- `event_msg` / `token_count`：`info.total_token_usage` 與 `info.last_token_usage`。

這些本機檔案格式可能隨 Codex 版本更動，並非穩定公共介面。OpenAI 原始碼也提供 [ThreadTokenUsageUpdatedNotification 結構](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/json/v2/ThreadTokenUsageUpdatedNotification.json)；不要把即時 API 的駝峰欄位名稱與 JSONL 格式混用。

## 計數規則

1. 同一檔案累計值相減；相同快照跳過。
2. 新檔第一個快照只採 `last_token_usage`，不把未知繼承總量全灌到今天；缺少 last 時警示並跳過該區間。這是保守值，可能少算未觀測前綴。
3. `total = input_tokens + output_tokens`。`cached_input_tokens` 已含在 input；`reasoning_output_tokens` 已含在 output，不再相加。不個別呈現 cache-write 計數，但它若含在 input 仍納入總量。
4. 任一計數倒退／子集不合理／資料格式無法解析時，保留警示，不推估。倒退後建立新基準再算後續增量。
5. 安裝時對既有檔案建立基準，不上傳其既有內容；新增事件時間還必須晚於安裝起算時間。
6. 半行 JSON 先不讀，等下一次完整換行再處理。檔案替換／截斷時重新建立基準，不重播歷史。
7. 事件指紋使用 UTC 時間＋累計計數；不放 session ID，避免複製／fork 更名導致重複。極少數真實獨立事件若剛好相同，會保守視為重複。
8. 同台重傳只寫一次；不同裝置同指紋全部列為爭議並排除合計。這可能使先前報表數字在另一台補傳後下修，屬於撤除重複的修正。

## 無法證明的事情

- 裝置配對只證明回報憑證來自哪個安裝，不證明那份工作在那台執行。
- 本機同步／匯入／fork 紀錄，如果只有一台回報，未必能偵測來源不屬於該台。兩台皆回報相同紀錄時才有足夠資料偵測跨裝置重複。
- 原始紀錄可被刪改，員工也能停用排程；沒有防竄改簽章、作業系統稽核代理或官方使用者歸屬。
- 未產生本機日誌的雲端任務、其他電腦、收集器裝錯目錄、格式改版都可能漏算。
- 工作片段是「曾請 AI 做什麼」的線索，沒有成果驗證、工時或人員績效資訊。

**用途：試行期的用量觀察與改善對話。用途不包含：精確分帳、員工處分證據、實際 API 帳單、訂閱額度換算。**
