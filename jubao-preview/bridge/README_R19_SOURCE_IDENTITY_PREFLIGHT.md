# 聚寶鯨 R19｜A1/A2 帳本來源安全預檢（隔離開發）

版本：2026-11-09，Asia/Taipei。
狀態：SANDBOX ONLY｜正式 DigitalOcean／Render 皆 HOLD｜尚無已核實的遠端帳本來源｜無實盤。

## 不重複做的部分
以 R18 原 2.5MB 黑金鯨魚 Logo 五頁 UI、R14 WAL、R15 私有報表 API、R16 前端、R17 Owner Session、R18 HTTPS 瀏覽器回歸作為已完成基線。**這次只修真實來源判定問題，不重做 UI 或登入。**

## 新增的實際程式與防呆
1. 修復 R14 對 A1/A2 SQLite 別名的識別：先前僅比較 resolve() 路徑；若兩個不同檔名是同一資料庫的 hardlink，可能被當成兩個不同帳本。現在使用 filesystem device+inode 再判斷，重複來源直接 REJECT，不聚合重複模擬績效。新增合成硬連結測試。
2. r19_offline_source_preflight.py：純離線、最多 16KiB、嚴格僅允許預定欄位的匿名化 JSON 輸入，拒絕未知欄位／憑證／收益／數據明細／重複 JSON keys／不正確時間、錯誤引擎、伪造 VERIFIED 身分、檔案 symlink。完全不連線 DigitalOcean、Docker、SQLite、交易所或第三方。
3. R19 嚴格區分「指定 config.json 靜態 dry_run」與「執行中 effective dry_run」、「資料庫候選存在」與「正在運行進程使用這份 DB」、「心跳聚合」與「完整 24 小時策略持續健康」。輸入即使所有聲稱都 true，也只能取得 READY_FOR_INDEPENDENT_OPERATOR_REVIEW_ONLY，絕不可自動標為 authentic_paper_ledger_verified 或 source_identity_verified；這些驗證旗標永遠 false。
4. 如果輸入任何引擎的 dry_run=false，輸出 HOLD_POSSIBLE_LIVE_TRADING；A1/A2 資料庫被聲稱非獨立則 HOLD_POSSIBLE_DUPLICATE_LEDGER。不啟動、停止、修改任何服務。

## 驗收測試
- qa/test_r14_live_wal_aggregate.py 既有 12 項 + 新 1 項 hardlink 避免雙重計數回歸。
- qa/test_r19_offline_source_preflight.py 共 30 項：來源拒絕、交易模式、來源身分、重複帳本、過期心跳、假 PnL 欄位、失效資料、程式執行結果不洩密。
- 一次性 CI 工作流程：.github/workflows/jubao-r19-one-shot-source-preflight-qa.yml。實際結果以 GitHub Actions Completed/Success 與 log 為準，未完成前不得宣稱 PASS。

## 需要遠端真正證據的項目
目前原 R13 截圖已證實過：2026-11-09 09:14（台灣）A1/A2 各有最近 15 分鐘 RUNNING 心跳、先前 Docker/程序存活及静態 dry_run=true；但仍沒有進程 effective runtime 配置、真實 DB 綁定、真實交易所行情與可信盈虧。B systemd 曾 active，不代表可信 Swap。

若 Owner 願意在已登入、已授權的 DigitalOcean Web Console 接續既有 R13 READ ONLY 查核，可在**不安裝檔案、不更改服務**下使用單一限定的白名單檢查。只回傳靜態狀態與 stake 貨幣分類，不會回傳 config、secret、完整 argv、env、原始日誌或交易紀錄；但它**不是 effective runtime 驗證**：

    for c in jubao-quant-spot-1 jubao-quant-futures-1; do
      echo "$c"
      docker exec "$c" python3 -B -c 'import json; p="/freqtrade/user_data/config.json"; x=json.load(open(p)); d=x.get("dry_run"); m=x.get("trading_mode"); s=x.get("stake_currency"); print("static_dry_run="+("true" if d is True else "false" if d is False else "unknown")); print("static_mode="+(m if m in ("spot","futures") else "unknown")); print("stake_class="+("USDT" if s=="USDT" else "unknown"))'
    done

這個命令讀取指定既有設定檔並在容器本機只投影欄位；即使顯示 USDT、dry_run=true，仍不能判定 effective runtime 未被其他配置／環境覆蓋。若 Web Console 或容器回應錯誤應停止，不透過聊天傳送私鑰、原始 config 或 SQLite。不得將任何真實來源報表／證據寫到此**公開** GitHub Repo。

## Owner Gate
既有 R13 限定 READ ONLY 可用於低風險查核，不涵蓋新增系統、修改主機、安裝讀取器、部署服務、改防火牆/SSH、啟動或重啟、合併 main、金流或實盤。安全的 R14/R15 實際 VPS 部署與 Android 可用的正式 Owner HTTPS 閘道，待獨立 Owner 批准；正式 Render R6 不變。

## 跨聊天室備份
若此輪有實際 Github 開發或驗收變更，須在 Google Drive 00_CURRENT 更新，99_HISTORY 另存不可覆蓋快照，讀回核對完全相同。回報新 SHA、Actions CI、CURRENT/HISTORY 連結；不要重做原五頁／Logo，也不開定時背景監測。
