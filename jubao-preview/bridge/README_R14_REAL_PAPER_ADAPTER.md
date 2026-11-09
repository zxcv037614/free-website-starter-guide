# 聚寶鯨 R14｜真實 Dry-run SQLite/WAL 唯讀資料橋接（Sandbox）

狀態：SANDBOX ONLY｜未部署｜未讀取 DigitalOcean 真實 DB｜無實盤｜未接上正式後台。

## 已新增
- `jubao-preview/bridge/r14_live_wal_aggregate.py`：對已存在的 Freqtrade Dry-run 命名 SQLite 使用 mode=ro&cache=private，禁止 immutable=1，開啟 query_only、trusted_schema=OFF 且設定純 SELECT authorizer；只讀 A1/A2 trades.is_open、close_profit_abs，以白名單欄位彙總已平倉數、持倉數與已實現損益。
- 有 WAL/SHM 時採用 SQLite 正常唯讀協調；若缺一個邊檔便拒絕。不 checkpoint、不 ALTER/UPDATE/INSERT、不備份、不讀 config、環境變數、SSH/API key、原始交易明細。不連 SSH、交易所或外部 API。
- 輸出 jubao-report-v1 匿名化 JSON（stdout），與既有 R9 安全 validator 和 R8 本機匯入契約相容。B 只做未核實監控，成交及損益 null。沒有杜撰虛擬錢包餘額或開倉浮動損益。
- 報表必須顯示 LOCAL_ACTIVE_WAL_RO、heartbeat_verified=false、runtime_verified=false、profit_verified=false、source_identity_verified=false。--paper-attested 只是操作者聲明，並非獨立驗證。
- 合成資料測試：`jubao-preview/qa/test_r14_live_wal_aggregate.py`，確認 DB、WAL、SHM 檔案在讀取前後 size/mtime_ns 未改；檢查欄位計數、已平倉損益、NaN、缺邊檔、錯誤 schema、symlink、不同引擎不能共用 DB、隱私與無路徑洩漏。

## 真實數據使用的限制
- 2026-11-09 R13 已驗證 A1/A2 Freqtrade 程序超過24小時、最近15分鐘心跳，以及存在 Dry-run SQLite/WAL。這不證明實際載入設定沒有覆寫、交易紀錄可信或已產生模擬收益。
- 程式未獲准部署到 VPS。R13 Owner Gate 只有指定 READ ONLY 查核，沒有批准安裝程式、新建服務/排程或建立檔案。正式第一次唯讀讀取之前，必須確認實際進程的 dry_run=true、trading_mode、stake_currency=USDT 及 DB URL 與預期一致。
- mode=ro 讀取 WAL 可能需權限/鎖定及 SHM 協調；**不能保證所有系統上均不改動 SHM metadata**。如果實機唯讀限制無法滿足，停止，不調整權限或關閉引擎。
- 即使本程式有真實 SQLite 來源，來源身份、投入資金、真實行情來源、損益與完整策略循環仍須另外驗證，不能把讀到的數字當正式實盤或完整盈利證據。
- 目前**沒有自動同步到手機後台**。R8 HTML 已具手動匯入能力，但 R6 正式預覽未部署 R8/R14。要完成真實自動更新，仍須受保護、具身分驗證的私有報表橋接，驗收 Android 後另行 Owner Gate 批准正式部署。絕不能公開 SQLite、/api/report、私密 config 或金鑰到公開 GitHub/Render。

## 下一階段
1. 確認有效 Dry-run 與真實 DB URL（僅允許白名單/布林結果，不洩露完整 argv/config/key）。
2. 取得經 Owner 授權、最小權限的實際彙總報表並核對來源與時效。
3. 以原黑金鯨魚五頁後台顯示真實 Dry-run 成交、虛擬損益與更新時間；新增受保護鑑權與快取，不把私有資料暴露在網路上。
4. 先在 Sandbox/手機驗收，再另行批准 Render/VPS 部署；不改 main、不增費、不接實盤、不新增排程監測。

每有實際開發進度同步 Google Drive CURRENT 與 HISTORY，讀回確認，回報 GitHub commit 與 Actions 證據。