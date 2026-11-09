# 聚寶鯨 R16｜原黑金五頁後台 Owner 同源模擬報表自動同步（Sandbox）

狀態：**SANDBOX ONLY，尚未部署、尚未接真實 VPS 帳本、沒有正式 Owner 登入或可公開使用的安全閘道**。不得把合成資料視為實際交易績效。

## 實際新增
- `jubao-preview/bridge/r16_owner_dashboard_sync.js`：可附加到**原始 R8 index.html** 的瀏覽器端 Owner 報表更新模組。原本 2.5MB 黑金鯨魚五頁 HTML/LOGO 完全不修改；實機仍部署 Render R6，R16 此時只供 Sandbox 注入/測試。
- 固定同源 `GET /api/v1/owner/paper-report`、`credentials: same-origin`、`Cache-Control: no-store`；**不含任何 Bearer token、交易所金鑰、API secret 或 localStorage**。此路由由未來 Owner Session/HTTPS 私有閘道實作，**R15 localhost Bearer API 不能直接從公網瀏覽器訪問**。不把 R15 token 塞到 HTML 或 JS。
- 在 Dashboard 首頁、A1/A2 交易、報表三頁添加小型 Owner 連線狀態條，保留原五頁選單、深海黑金定位和原始 LOGO。這是獨立外掛，並非替換介面。
- 每次有可用 Owner Session 且頁面可見時，執行同源安全 GET。成功時逐項檢驗 `jubao-report-v1` 的 paper_only、live_trading=false、未驗證 provenance、A1/A2 允許資料來源、B 強制 unknown、UTC 時效、筆數與有限 decimal 字串。**只有合格資料**才使用 R8 現有 FileReader/本地 JSON 匯入介面重新計算五頁數字。沒有改寫 R8 的既有風控、交易按鈕與報表驗證邏輯。
- 60 秒僅在**打開且可見的瀏覽器頁面**嘗試讀取；切到背景則不發送請求，回到前景才重新取；按「手動重新讀取」可即時更新。這不是伺服器定時監測，不會建立持久背景 Agent 或新增付費排程。
- 401/403 未授權、503、回應過大、跨來源重新導向、錯誤／未來時間、live trading JSON、冒充 VERIFIED、B 可信 Swap 造假、無法驗證的欄位都 Fail Closed；若之前顯示的是 R16 自動資料則清除，避免留下舊盈虧當作最新資料。用戶手動選擇本機 JSON 時，停止自動覆蓋直到重新啟用。
- 畫面明示：『Owner 模擬帳本、未獨立驗證、僅已實現盈虧彙總』。尚無 Equity、即時未實現盈虧、真實報價來源驗證、成交明細或鏈上 B 可信 Swap。不能把 `runtime_verified=false` 顯示為 LIVE 盈利。

## R16 瀏覽器驗收
- `jubao-preview/qa/r16-owner-dashboard-sync-e2e.cjs`：Playwright Chromium 在手機 390×844 與平板 900×600 上，以**原 R8 HTML 原樣檔案**配一個 Sandbox 測試伺服器（在回應時附加 R16 JS，不修改 GitHub 既有 `index.html`）。伺服器只綁 127.0.0.1，使用純合成 Freqtrade 風格數據及 HttpOnly 模擬 Owner Session cookie，絕不連線 DigitalOcean 或真實交易所。
- 先驗證未登入拒絕、登入後安全同步 A1/A2 模擬損益、B 保持未知、同源來源與更新時間顯示、舊資料/斷線清除、不冒充已驗收益、原五頁選單/LOGO/禁用的交易按鈕保留、無手機溢出及無 JS 例外。
- 舊 R8/R11、R9/R10/R12/R14/R15 安全測試必須保留；只使用免費標準 GitHub runner 一次性 CI，無 Cron、不部署、不重啟。

## 部署前 Owner Gate（目前未批准）
1. 現有 DigitalOcean A1/A2 的 Freqtrade 實際有效 Dry-run 設定、各自私有 DB URL、USDT stake、交易所行情、開倉與成交來源須先安全核實，並允許限定唯讀聚合；R13 限定 READ ONLY 授權**不等於**批准安裝任何新服務。
2. 需要 Owner 正式身份系統（HttpOnly Secure session cookie、CSRF/Origin 控制、短時效、撤銷、權限）、具 TLS 的同源私有報表閘道。只可把經白名單投影的聚合結果送回瀏覽器，絕不能公開 SQLite、服務私鑰或 R15 bearer token。
3. 公網 Render R6 目前仍為舊預覽，R8/R14/R15/R16 尚未部署。R16 JavaScript 只是經原 HTML 沙盒注入驗收，**不是**正式前端已上線；正式整合需將附加 JS 以審核方式載入後台，禁止把本機 127.0.0.1 當公網地址。
4. 未完成單筆交易歷史、浮動 PnL、虛擬錢包 Equity、B 可信 Swap 與全時心跳的完整實證；缺資料顯示未知，絕不放合成績效。完成手機實測及安全審查，再另外請 Owner 批准正式部署。

## 固定工作規則
本輪只在 GitHub 隔離 R16 分支提交，保留原黑金鯨魚 LOGO、五頁、不合併 main、不改 DigitalOcean/Render、不使用實盤 API、不增加收費資源、不新增定時監測。任何實際開發進度同步 Google Drive 00_CURRENT + 99_HISTORY，讀回核實並回報 GitHub SHA 和 CI 結果。