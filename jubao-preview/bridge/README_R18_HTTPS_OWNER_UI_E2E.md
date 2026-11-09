# 聚寶鯨｜R18 HTTPS Owner Session 黑金五頁整合驗證
日期：2026-11-09（Asia/Taipei）
狀態：SANDBOX ONLY；尚未部署 DigitalOcean / Render、沒有真實 A1/A2 帳本、沒有實盤、沒有真正的 Owner IdP。

## 不重做的部分
- 原 jubao-preview/index.html 2.5MB 黑金鯨魚 LOGO 與五頁完全不變。
- 既有 R14 WAL 聚合、R15 私有 API、R16 受保護同源前端同步與 R17 本機測試登入程式全部重用。
- 不替換既有正式 Render R6，不合併 main，不增加付費資源，不啟動交易 / 自動跟單 / 常駐監測。

## R18 實際新增
1. bridge/r18_local_owner_login.js：以加法方式注入原後台首頁「Owner 登入（測試）／登出」小面板，輸入僅在當次 HTTPS POST 傳送至同源 localhost，隨即清除欄位，不輸出至 Console、localStorage 或 URL。UI 將真實連線與合成測試資料清楚區隔，B 未驗證 Swap 不產生利潤。
2. bridge/r17_local_owner_session_gateway.py：修正 Origin 判斷，對 SSL/TLS 本機連線只接受完全相同 HTTPS Origin；維持 Secure / HttpOnly / SameSite=Strict Cookie、10 分鐘時效與登出撤銷。
3. bridge/r16_owner_dashboard_sync.js：新增 clearSession()；Owner 登出時清除之前自動匯入的模擬損益，避免舊數字殘留。
4. qa/r18_synthetic_https_fixture.py：自簽測試 TLS、127.0.0.1 綁定，在本機執行 R15 -> R17 的真正 HTTP 客戶端／伺服器轉接。資料全部是 Python 合成 fixture，不可能連到 VPS 或真實交易所。回應原 HTML 時才附加 R16／R18 JS，GitHub 原始 R8 index 不修改。
5. qa/r18-https-owner-mobile-e2e.cjs：Playwright Chromium 手機尺寸 390×844、平板 900×600 驗證頁面、Logo、Owner 401、錯誤與成功登入、Secure Cookie、R15→R17→UI 資料回填、A1/A2 顯示、B 保持 unknown、503 清除、偽造 live_trading fail-closed、登出撤銷 Session、重新整理不留盈虧、無意外外部或交易請求。

## 執行方式（僅 GitHub Actions 隔離 QA）
Workflow jubao-r18-one-shot-https-owner-ui-qa.yml 在 ubuntu-24.04 runner：
- Python 3.11、Node 22、Playwright Chromium 1.56.1。
- OpenSSL 產生臨時單日測試憑證，放在 GitHub runner 暫存目錄，絕不提交私鑰。
- 以 TLS/HTTPS 完整測試 R17 同源驗證。測試環境允許信任 CI 自簽憑證，這不是正式公網可信 TLS。
- 重跑 R14、R15、R17 安全單元測試與 R11、R16 黑金五頁回歸，最後跑 R18 行動視窗 E2E。
- 只有實際 Actions Completed / Success 才能標示 PASS；不能把合成交易測試聲稱為 VPS 真實損益驗證。

## 重要未完成
- R18 測試用 Owner 密語和 R15 token 只是公開的假資料、不能部署，沒有真正的 Owner 身分／多因子驗證／正式 TLS 憑證／正式公網閘道設計。
- R17/R18 伺服器只能在 localhost。不可直接對外綁定、丟上 Render 公網、複製測試憑證當正式私鑰或把 token 寫入 HTML。
- 尚未讀到真實 DigitalOcean A1/A2 Dry-run SQLite、有效進程配置、虛擬 stake 貨幣、成交明細，沒有真實收益可報告。B 沒有已驗證可信 Swap。
- 未在 Samsung Android 真機驗收，只有 Chromium 模擬手機/平板畫面。
- 對 DigitalOcean/Render 的任何操作仍需要另外 Owner Gate，R13 限定唯讀不等於允許部署或修改服務。

## R19 安全接續目標
1. 經獨立授權 READ ONLY 核實現有 VPS 上兩個 Freqtrade 的有效 dry_run 與交易所虛擬帳本來源，只回傳安全白名單證據，不傳憑證/DB/log。
2. 以正式可撤銷的 Owner 身分及 HTTPS Gateway 方案進行隔離安全審查，服務分層與 Network/Secrets Boundary 必須明確。
3. Owner 另外批准後才能佈署和接真實數據，並安排 Samsung 實機斷線、登出、數字來源與五頁手感驗收。

## 跨聊天室接手與備份
實際代碼/驗收有更新時同步 Drive 00_CURRENT + 99_HISTORY；讀回內容相同後回報兩連結、GitHub Sandbox SHA 和具體 Actions 結果，不因純聊天建立重複備份。
