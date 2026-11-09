# 聚寶鯨 R17｜Owner Session 本機安全閘道（SANDBOX ONLY）

日期：2026-11-09（台灣）  
R16 基準 SHA：2f9b6cb7bc85eff9b25f9f7ff7c794e1775c5c5b

## 新增功能
- bridge/r17_local_owner_session_gateway.py：只綁定 127.0.0.1，不可對公網提供服務。
- 使用合成測試密語、10 分鐘 RAM Session，隨機 __Host-jubao_owner Cookie，帶 HttpOnly／Secure／SameSite=Strict，登出可立即撤銷。
- 未登入無法讀報表，要求同源 POST Origin、Host 檢查，固定 GET /api/v1/owner/paper-report，不提供 CORS、不可 POST 下單或其他方法。
- 由閘道在伺服器端向 R15 本機 API 發送 Bearer 憑證，前端絕不持有 R15 token，固定 127.0.0.1 防止任意 URL 重導。
- R15 既有 public_report 白名單再投影，僅投影 A1/A2 Dry-run 彙總、B unknown。原五頁黑金鯨魚 LOGO、R16 外掛、R14/R15 均不改。

## 測試
qa/test_r17_owner_session_gateway.py 使用 unittest 合成資料涵蓋 Owner Session 401/403、cookie、登出、10 分鐘過期、方法限制、B 假 Swap/收益防護、實盤模式拒絕、資料錯誤後 Fail Closed，並通過本機合成 R15 loopback 整合。
命令：python3 -m unittest discover -s jubao-preview/qa -p 'test_r17_*.py' -v
另有 GitHub 一次性 R17 QA；是否通過須以實際 Actions 結果為準。

## 重要未完成事項
1. 此身分驗證是 LOCAL TEST 驗證密語，不是真實 Owner 身分或完整公開環境驗證。不得將本程式綁定 0.0.0.0、直接放公網或當成正式登入。也尚未提供使用者可操作的登入頁。
2. 真正對外同源 HTTPS 閘道需要可靠 IdP、MFA（如可用）、Proxy 信任界線、CSRF、防重放、撤銷、Session 生命週期與正式安全審查。這些仍未完成。
3. R16 原五頁只在合成 Playwright 成功；R17 尚未整合公網 Render，更沒有接實際 DigitalOcean A1/A2 SQLite 及有效執行時 Dry-run。B 真實 Swap/損益仍無可信證據。
4. R15/R14 本機讀取正在使用的 SQLite/WAL 可能涉及檔案協調；需審核真實 DB/讀取權限，不能在 R13 READ ONLY 限定下自行安裝、部署或改機。
5. GitHub main、Render R6、現有 DigitalOcean、交易所 API 與真實金流一律維持不變；禁止背景監測、增費或重做原 Logo/UI。

## 下一個 Owner Gate
先以最小安全 READ ONLY 檢查 A1/A2 有效 Dry-run 設定、實際使用的私有 DB 來源和匿名化聚合可行性。另行明確批准後，才評估正式 Owner HTTPS/IdP 閘道以及 R14/R15 限制部署，最後以 Samsung 真機驗收。不可把合成 PASS 當真實 Dry-run 績效或實盤收入。
