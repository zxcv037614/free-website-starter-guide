# 聚寶鯨 V1.0｜R7 唯讀報表安全校正（2026-11-08）
狀態：SANDBOX ONLY / NOT DEPLOYED / NOT LIVE
Owner Gate：未批准 main 合併、Render 部署、DigitalOcean 連線、私人 API 或實盤。

## 基線
- R6 正式預覽：Render https://jubao-quant-preview-v10.onrender.com
- R6 部署 commit：b941141c6ab76f73558b1e5b393ccb31ef8578c8 (2026-11-08 13:45 Asia/Taipei, LIVE)
- R7 隔離分支：sandbox/jubao-v10-r7-report-safety-20261108
- R7 程式提交：f5fad89dd59720c0b394ec0cb4ff0aaa0ff10521
- 原 logo 與五頁保留；未修改正式 Render branch；autoDeploy=off

## 本輪程式修改
1. 將 JSON 資料來源判定由 JS 原型鏈檢查改為 own-property 檢查。
2. 嚴格限制 spot/futures 與 solana 可接受的資料來源種類。
3. NOT_CONNECTED 不得包含非 null 損益或持倉數量。
4. 未經可信來源的 connected=true 不允許以一般來源宣稱連線。
5. 本機匯入報表標示「未驗來源」，避免誤認為後端已連線。
6. 未連線／合成測試的交易卡片不得顯示損益數字。

## 唯讀校正結果
- R7 GitHub blob 已重新讀取，檔案存在，五個 data-page / 五個導航項目仍保留。
- 三個交易相關預留按鈕仍保留 disabled。
- Binance Spot 公開報價 API、前景輪詢、失敗清空顯示仍保留。
- 不自動呼叫 /api/report；兩個風控滑桿仍只更新本機文字。
- 本機 JSON 匯入仍有 1MB 限制與報表格式檢查。
- 此為程式靜態檢查，未執行新版瀏覽器 E2E、CI 或 Samsung 真機 R7 驗證，不得稱整站 PASS。

## 使用者截圖驗收
- V1.0 R6 Samsung 平板橫向畫面：總覽／交易 A1／聰明錢／風控／報表 5 頁已顯示；BTC/ETH/SOL 三組公開價格顯示。
- A2 實際切換、停用按鈕點擊、風控互動和 JSON 匯入仍待操作測試。
- Render R6 的 LIVE 不代表 A1/A2/B VPS 真實連線。
- B 歷史 70 事件，40 OBSERVED 失敗，可信 Swap=0；禁止自動跟單。

## 後續 Owner Gate
取得 Owner 新的明確授權後，才進行 DigitalOcean READ ONLY A1/A2/B 運作、dry-run 帳本及權限核對；不得取得或暴露 API secret；不得下單或新增付費資源。若 R7 要部署，先補隔離環境瀏覽器／手機驗證與另一次部署批准。
