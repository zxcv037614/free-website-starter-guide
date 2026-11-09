# 聚寶鯨 R15｜Owner 私有 Dry-run 報表端點（Sandbox）

**狀態：SANDBOX ONLY，未部署到 DigitalOcean／Render，未打開交易所實盤，不會自動出現在公開黑金五頁後台。**

## 商業目的
讓 A1 現貨、A2 合約的**真實行情驅動、虛擬資金執行的 Freqtrade Dry-run** 帳本，未來經安全授權後可以由 Owner 後台按需讀取，不再只能手動匯入 JSON。R15 是私有報表介面基礎，不是成品後台；R6 Render 的原五頁與黑金鯨魚 Logo 仍保持不變。

## 新增功能
- `jubao-preview/bridge/r15_private_paper_endpoint.py`：Python 3.11 標準函式庫 HTTP 服務，**只能綁在 127.0.0.1**。唯一路由 `GET /api/v1/paper-report`，要求 `Authorization: Bearer ...` 且 token 至少 32 字元，由環境變數 `JUBAO_R15_OWNER_TOKEN` 提供；不將 token 寫入程式、網址、日誌、GitHub 或 Google Drive。切勿用交易所 API Key 作為此憑證。
- Owner 通過授權後才使用 R14 的本機唯讀 WAL 讀取器 `generate()`。每一次 GET 都從指定的本機合成／未來受授權的 Dry-run DB 重新讀取，沒有背景排程、沒有寫入 DB、沒有上傳外部服務。
- 所有輸出先經**嚴格白名單投影**，只允許 A1/A2 的 closed_trades、open_trades、realized_pnl_usdt、時間和來源標記。B 仍保留 NULL 可信 Swap/損益，不會把監控事件當成交，也不會輸出單筆交易、完整 argv、API keys、私鑰、原始 SQLite、敏感路徑或任意來源欄位。
- 固定 `paper_only=true`、`live_trading=false`，`runtime_verified=false`、`heartbeat_verified=false`、`profit_verified=false`、`source_identity_verified=false`；不允許未經證實的來源將狀態標記為真實盈利。異常會回傳不含檔案路徑與錯誤堆疊的 `503 REPORT_UNAVAILABLE`。
- 缺少或錯誤 token 回傳 401；錯誤 Host 回傳 403，其他路徑 404；POST/PUT/DELETE/OPTIONS 全部 405。拒絕 CORS 預檢，不提供 `Access-Control-Allow-Origin`，並使用 `Cache-Control: no-store`、`nosniff`、`X-Frame-Options: DENY`。不公開網路監聽，不支援跨來源瀏覽器直接存取。

## 隔離測試
- `jubao-preview/qa/test_r15_private_paper_endpoint.py` 使用合成 Dry-run SQLite/WAL 測試 Owner 驗證、跨網站限制、無交易寫入、拒絕未授權請求、每次 GET 重新取得聚合結果、惡意字段過濾、錯誤 fail-closed、WAL size/mtime 不變、無背景讀取，以及 B 不冒充成交。
- GitHub 一次性 CI 使用免費標準 runner Ubuntu 24.04、Python 3.11、Node 22，在 **R15 隔離分支**運行；絕不跑在 DigitalOcean，也沒有交易所 API key。CI PASS 只證明合成資料流程，不代表真實交易帳本、成交、虛擬金額及盈虧已驗證。

## 不能直接上線的原因
1. **Loopback-only 不能被 Render 靜態後台跨網路直接存取。** 這是刻意的安全隔離；即使 R15 在 VPS 啟動，公開網站也無法直接讀取 `127.0.0.1`。不能為了省事而將服務改為 `0.0.0.0`，或把 token 放到公開 HTML／localStorage。
2. 未來需要 Owner 身分驗證、反向代理／受保護的同源路由、HTTPS、來源與權限控管，再將經驗證的匿名化數據接進原黑金五頁後台。正式部署/域名/費用仍需另行 Owner Gate。R15 不會新增自動監測或新雲端服務。
3. R14 對 WAL 的唯讀讀取在一般系統上可能需 SHM 檔鎖定協調，無法在所有環境保證零檔案層面副作用，需先審查實機檔案權限與真正的 Dry-run 有效配置。R13 只批准限定 READ ONLY 查核，**不包括把 R14/R15 上傳 VPS、執行服務、修改防火牆或正式部署**。
4. 尚未實際取得 A1/A2 模擬成交或虛擬金額的真實數值，不能說後台已經看到真實損益。R15 只處理已實現損益和筆數；未提供虛擬帳戶 Equity、未實現損益、手續費、資金費率或真實鏈上 Swap。

## 後續正確推進順序
1. 在 R15 隔離 CI 驗證私有 API + R14 WAL 彙總，不動現有 VPS。
2. 認證有效的現有 Freqtrade dry_run、trading_mode、stake_currency/虛擬資金與資料庫來源；經額外 Owner 批准後取得匿名化實際報表，先由 R8 原五頁既有 JSON 手動匯入驗證數字。
3. 為原五頁實作受保護的同源自動更新接線和 Owner 授權，再在手機驗收；此階段不能公開資料或 credentials。
4. 完成安全與手機驗收後另外申請正式 VPS/Render 部署批准。保留既有 R6 LIVE，不合併 main、不新建付費資源。

## 測試操作（僅隔離測試）
在安全測試主機，以人工產生的**測試 token** 設定 JUBAO_R15_OWNER_TOKEN，並提供**合成** Freqtrade Dry-run SQLite 路徑啟動服務。GET 必須帶 Bearer token。禁止傳送 token、真實 SQLite、原始 config、SSH/交易所私鑰到 ChatGPT、GitHub 或 Google Drive。

### 永久備份規則
有真正開發／驗收更新，就同步 Google Drive 00_CURRENT 和 99_HISTORY，實際讀回一致後回報 GitHub SHA／CI 連結。純聊天不重複備份、不新增定時監測。