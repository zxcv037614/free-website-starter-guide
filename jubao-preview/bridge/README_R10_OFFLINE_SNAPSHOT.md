# JUBAO R10｜離線模擬帳本橋接（Sandbox only）

**狀態：程式已提交；僅離線合成資料已測試。禁止將此流程當成 VPS 已在線、24 小時運轉或真實獲利證據。**

## 目前完成的部分

- A1 spot / A2 futures：從**完成複製的** Freqtrade SQLite 快照唯讀計算 closed_trades、open_trades、close_profit_abs (USDT)。
- 匯出符合既有 R8/R9 \`jubao-report-v1\` 的 JSON，供手機 R8 報表頁**手動匯入**。
- 必須提供本機的 \`dry_run=true\`、\`trading_mode=spot/futures\`、\`stake_currency=USDT\` 設定檔；**這不構成遠端機器身份證明**。
- 輸入資料庫唯讀模式 \`mode=ro&immutable=1\` + \`PRAGMA query_only=ON\`，拒絕仍有 WAL/SHM 的活躍資料庫；不連網、不讀取實際 VPS、不啟動交易。
- B 仍是歷史監測，可信成交／Swap 尚未核實，資料為 null，**不能以事件數冒充成交數**。
- 若有任何已平倉交易缺少 \`close_profit_abs\`，損益保持 null；不硬算 0。
- 報表來源始終標記 \`OFFLINE_SNAPSHOT_ONLY\`，心跳、引擎在線、損益身份證明皆 \`false\`。報表時間採離線快照檔案修改時間，**不是引擎心跳**。

## 操作範例（只供受控本機 Sandbox，勿上傳金鑰）

先確認資料庫為**停止寫入後製作的離線副本**；不可直接把執行中的 Freqtrade SQLite 當輸入。
可自行建立只含三個安全欄位的本機佐證 config，如：

\`\`\`json
{"dry_run": true, "trading_mode": "spot", "stake_currency": "USDT"}
\`\`\`

但這份小 config **無法證明原始機器真的在 dry-run**。實際環境佐證必須經 Owner 核准後另行取得並核實。不要把原始 Freqtrade config、SQLite 真實快照、API keys、VPS SSH 憑證放上此**公開 GitHub Repo**或 Google Drive。

\`\`\`bash
python3 jubao-preview/bridge/export-offline-paper-report.py \
  --spot-db /safe/offline/a1-paper-copy.sqlite \
  --spot-config /safe/offline/spot-sanitized.json \
  --out /safe/offline/a1-review-20261108.json
node jubao-preview/bridge/offline-paper-report-validator.cjs /safe/offline/a1-review-20261108.json
\`\`\`

合約 A2 如有乾淨的獨立離線副本，可再加 \`--futures-db\` 與 \`--futures-config\`。不可把同一個 DB 假裝成 A1 和 A2。未提供的引擎保持 NOT_CONNECTED。產生 JSON 後可使用**已有的** R8 本機 JSON 匯入入口，無需修改原五頁 UI。

## QA / Owner Gate

\`\`\`bash
node --test jubao-preview/qa/r9-offline-paper-report.test.cjs
python3 -W error::ResourceWarning -m unittest discover -s jubao-preview/qa -p 'test_r10_offline_export.py' -v
\`\`\`

- R8：86/86 Chromium 合成資料 PASS（歷史證據），不等於 R10。
- R9：16 項 Node 測試已建立，GitHub Actions 執行結果未核實。
- R10：16 項 Python 合成資料測試在本地執行 PASS；GitHub Actions 執行結果仍須核對。
- Render R6 官方預覽維持原設定；R7/R8/R9/R10 均未部署。
- 不新增付費服務、不部署 Production、不接入實盤金鑰、不登入 DigitalOcean、不合併 main。
- 下一步：經 Owner 個別授權核實 DigitalOcean A1/A2/B 容器、dry-run 設定、24 小時心跳、SQLite schema，再做受權的本機快照匯出；現階段不聲稱真實損益。
