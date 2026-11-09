# 聚寶鯨 R20｜A1/A2 程序 ↔ Dry-run 帳本檔案識別（Sandbox）

日期：2026-11-09（Asia/Taipei）
狀態：SANDBOX / READ-ONLY PROBE PREPARED，尚未在 DigitalOcean 執行，不是正式 Owner 身分驗證、實際 Dry-run 配置、真實帳本／獲利驗收。
沿用 R19 獨立分支：sandbox/jubao-v10-r19-paper-source-identity-20261109，SHA fd91a529697d5d6b8474db01df193c1a1652d7d3。

## 為何需要這個檢查
Freqtrade 官方文件指出：CLI 參數優先於環境變數；環境變數優先於後載入配置；多份設定檔後者可覆蓋先前值。因此之前看到 config.json 的 dry_run=true 不足以確定真正有效執行模式。
官方來源：
- https://docs.freqtrade.io/en/latest/configuration/
- https://docs.freqtrade.io/en/latest/bot-usage/
- https://docs.freqtrade.io/en/stable/advanced-setup/

## 程式新增
jubao-preview/bridge/r20_readonly_fd_binding_probe.py
- 只讀容器本機 /proc/PID/comm（是否名為 freqtrade）和 /proc/PID/fd 的檔案 metadata（st_dev/st_ino）。不讀 PID cmdline、environ，完全不讀取 SQLite 主檔內容、WAL、SHM、原始 logs、策略設定、API/SSH 金鑰。
- 僅查看四個既定目錄下名字固定的 dry-run SQLite 候選檔案。用檔案 device/inode 與進程持有的 FD metadata 比對，僅以單次觀測證明「有 Freqtrade 程序持有該檔案的 FD」或回報未觀察到／未知。
- 輸出匿名化 JSON：引擎類型、程序數、候選數、FD binding enum 和短雜湊檔案識別提示（不是資料來源真實證明），不列路徑、程序 ID、啟動指令或真正交易筆數。
- 最終 effective_dry_run_verified、db_runtime_config_verified、exchange_market_data_verified、paper_profit_verified、strategy_24h_verified 永遠 false。
- Linux /proc FD 不一定常開：NOT_OBSERVED 不能推論 Freqtrade 停機或沒有使用資料庫。兩容器相同 inode hint 不足以跨 mount namespace 證明同一檔案。
- 專為公開合成 Sandbox 寫入程式碼，禁止直接讓未經審核來源腳本從網路進入 VPS 並執行。沒有對 DigitalOcean 執行任何命令。

## 本輪測試
jubao-preview/qa/test_r20_readonly_fd_binding_probe.py 使用人工 /proc 目錄、fd symlink 和假資料庫檔案，驗證 OBSERVED、NOT_OBSERVED、UNKNOWN、檔案 symlink、同 inode、只輸出匿名化欄位以及缺少訪問時 fail-closed。全部是合成資料；需以實際 GitHub Actions SUCCESS 及日誌證據認定 PASS。

## 不改的內容
原 R8 2.5 MB 黑金鯨魚 Logo、五頁導航，R14/R15/R16/R17/R18/R19 已完成 Sandbox 程式均保留。不得碰 Render R6、DigitalOcean 主機配置、GitHub main、實盤金鑰、交易、SQLite WAL 主檔，不能新增付費資源、排程或新部署。

## R20 真正現場驗收條件
1. Owner 在已登入的 DigitalOcean Web Console 依既有 R13 READ ONLY Gate 自行驗證三引擎是否仍存在，確認先前容器/程式快照的時效；助手不會從 Github Runner 自動登入 VPS。
2. 必須另行審查「effective runtime config」的安全查核方法。**尚未允許**讀取完整 /proc/PID/environ、完整命令列、原始 config、SQLite/WAL／實盤私鑰；若只能查白名單，不可輸出完整來源或憑證。
3. 單純 Docker Up、Freqtrade 心跳、候選 SQLite 存在、單次 FD binding、人工聲稱 dry_run 都不足以證明真實 Paper PnL。
4. 真正 R14 WAL/SQLite 聚合若需要在 VPS 讀取運作中資料庫，必須先做獨立 Owner Gate 授權、文件化一致性/鎖定/來源安全，禁止先上傳 R14/R15 或改動當前服務。
5. 最終仍需 Owner 正式 HTTPS IdP 身分／Samsung 手機實機驗收；無真實資料前所有收益維持「未驗證」。

## 永久交接
R20 任何實際程式更新，同步 00_CURRENT 和 99_HISTORY 全文快照，讀回一致。只在成功測試後回報 CI 項數與 SHA。純聊天不重複備份。
