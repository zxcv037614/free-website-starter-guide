# 聚寶鯨 R12｜離線三引擎運作證據審核（Sandbox Only）

**狀態：SANDBOX ONLY／僅用合成資料／沒有登入 DigitalOcean／沒有真實交易／沒有部署。**

R11 已完成合成 SQLite → R10 Python 離線匯出 → R9 JSON 驗證 → R8 手機與平板 Chromium 匯入的端到端測試。R11 成功不代表 DigitalOcean A1/A2/B 已持續在線，也不代表任何真實收益。

## R12 新增項目

- 檢查器：jubao-preview/bridge/r12-offline-runtime-evidence.cjs
- 測試：jubao-preview/qa/r12-offline-runtime-evidence.test.cjs
- 僅接受本機去識別化的三引擎 JSON，最多 256KB；不得加入原始 config、SQL、SSH、API key 或其他欄位。
- 欄位：schema_version、captured_at_utc、source、engines。三個引擎 ID 必須為 spot / futures / solana。
- 每個引擎欄位：id、container_state（running/stopped/unknown）、dry_run（true/false/null）、heartbeat_at_utc（UTC 或 null）、uptime_seconds（非負整數或 null）、ledger_snapshot_at_utc（UTC 或 null）。
- source 僅允許 SYNTHETIC_FIXTURE_ONLY 或 OPERATOR_REDACTED_UNATTESTED，禁止任何自稱 TRUSTED、VERIFIED 或 production 證明。
- 只讀本機檔案，不連線、不寫 DB、不啟動或停止機器人、不匯出憑證。
- 結果一律為 OFFLINE_INPUT_UNATTESTED；remote_identity_verified、continuous_24h_verified、authentic_paper_ledger_verified、real_profit_verified 永遠 false。
- A1/A2 出現 dry_run=false：HOLD_POSSIBLE_LIVE_TRADING；僅發出風險提示，不操作容器。聲稱 uptime >= 86400 秒仍不構成驗證。
- B 是聰明錢監控，不是 Freqtrade；不能把 B 監控事件視為成交、損益，不能攜帶 Freqtrade dry_run 或交易帳本時間。
- 本輪不修改既有五頁黑金鯨魚 UI，Render R6 保持原狀。

## 安全的合成測試格式

可建立一個僅供本機使用的 JSON，內容如下（日期僅示範，實際審核依 UTC 時間檢查）：

    {
      "schema_version": "jubao-r12-observation-v1",
      "captured_at_utc": "2026-11-08T10:00:00Z",
      "source": "SYNTHETIC_FIXTURE_ONLY",
      "engines": [
        {"id":"spot","container_state":"running","dry_run":true,"heartbeat_at_utc":"2026-11-08T09:58:00Z","uptime_seconds":90000,"ledger_snapshot_at_utc":"2026-11-08T09:55:00Z"},
        {"id":"futures","container_state":"unknown","dry_run":null,"heartbeat_at_utc":null,"uptime_seconds":null,"ledger_snapshot_at_utc":null},
        {"id":"solana","container_state":"unknown","dry_run":null,"heartbeat_at_utc":null,"uptime_seconds":null,"ledger_snapshot_at_utc":null}
      ]
    }

執行：node jubao-preview/bridge/r12-offline-runtime-evidence.cjs /safe/local/r12-synthetic.json

這個結果只是本機資料規格檢查，不證明遠端身份、服務在線、24 小時連續運作、SQLite 真實性或獲利。

## 下一個明確的 DigitalOcean Owner Gate

1. Owner 另行明確批准「既有 DO VPS／A1／A2／B 特定 READ ONLY 調查」後，才能查看容器狀態、命名、運作時間與匿名化心跳資料。
2. A1 現貨及 A2 合約須分別確認真正 dry_run=true、正確 trading_mode、無任何實盤金鑰誤連；禁止讀取或上傳完整 config。
3. 24 小時證明需多時間點可靠佐證與運作紀錄；單一 uptime 或 heartbeat 不夠。
4. SQLite schema 和模擬帳本只在經同意安全離線副本下核對；不可直接把活躍資料庫當 immutable 快照讀取。
5. B 要區分監測事件、OBSERVED 失敗、可信 Swap。既有 70 件、40 件失敗、0 可信 Swap 只屬歷史基線。
6. 任何要寫入、重啟容器、部署、產生新費用、接私人交易金鑰或實盤，都需要另外新的 Owner Gate。

## 備份與隔離

每次有真正的開發與驗收進展，同步 Google Drive 的 00_CURRENT 與 99_HISTORY，並讀回核實，再回報可開啟的備份連結及 GitHub SHA；僅聊天不重複備份。不得新增排程監測。

GitHub repo 目前仍是公開共用倉庫，不得上傳真實 SQLite、原始 VPS 日誌、任何 API/SSH 私鑰、完整設定檔及個人資料。保留原鯨魚 Logo、五頁 UI、不改 Render、不合併 main。
