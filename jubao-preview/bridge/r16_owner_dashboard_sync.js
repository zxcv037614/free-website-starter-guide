/* JUBAO R16 | owner-session same-origin paper synchronization.
 * SANDBOX ONLY. Injected additively into unchanged R8 5-page dashboard.
 * The route below is a FUTURE authenticated same-origin gateway; R15 localhost
 * Bearer token must NEVER be embedded in this browser script.
 */
(function () {
  'use strict';
  if (window.__JUBAO_R16__) return;

  const ENDPOINT = '/api/v1/owner/paper-report';
  const REFRESH_MS = 60 * 1000;
  const MAX_BYTES = 1024 * 1024;
  const MAX_AGE_HOURS = 24;
  const ENGINES = ['spot', 'futures', 'solana'];
  const STORE = {busy: false, applied: false, manualOverride: false,
    status: 'WAITING', lastFetchUtc: null, reason: '等待受保護的 Owner 報表連線'};
  const view = {};
  let timeoutId = null;

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function makePanel(name) {
    const page = document.querySelector('.section[data-page="' + name + '"]');
    if (!page) return null;
    const panel = el('section', null, 'r16-owner-panel');
    panel.id = 'r16Panel-' + name;
    panel.setAttribute('aria-label', '聚寶鯨 Owner 真實模擬帳本連線狀態');
    panel.style.cssText = 'box-sizing:border-box;max-width:100%;margin:10px 0;padding:12px 14px;'+
      'border:1px solid rgba(210,174,80,.36);border-radius:12px;'+
      'background:rgba(7,20,39,.94);color:#f0dfb6;'+
      'font:13px/1.5 system-ui,sans-serif;overflow-wrap:anywhere;';
    const header=el('div');
    header.style.cssText='display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap;align-items:center;';
    const title=el('strong', '聚寶鯨｜Owner 模擬帳本');
    const badge=el('span', '未連線');
    badge.style.cssText='border:1px solid rgba(210,174,80,.5);border-radius:30px;padding:2px 9px;';
    header.append(title, badge);
    const detail=el('div','尚未連線實際 Dry-run 報表');
    detail.style.cssText='margin-top:6px;white-space:normal;';
    const fine=el('div','僅供虛擬交易審閱；來源、24h 策略與收益未獨立驗證');
    fine.style.cssText='margin-top:3px;color:#bdc5d1;font-size:12px;';
    panel.append(header,detail,fine);
    if (name==='reports') {
      const button=el('button','手動重新讀取');
      button.id='r16ManualRefresh';
      button.type='button';
      button.style.cssText='margin-top:8px;padding:6px 12px;border-radius:8px;'+
        'border:1px solid #af904c;background:#142943;color:#f0dfb6;cursor:pointer;';
      button.addEventListener('click', () => { STORE.manualOverride=false;refresh(); });
      panel.append(button);
      view.button=button;
    }
    page.prepend(panel);
    view[name]={panel,badge,detail,fine};
    return panel;
  }
  function show(state, detail) {
    STORE.status=state;
    STORE.reason=detail;
    const labels={
      WAITING:'未連線',LOADING:'查詢中',SYNCED:'已讀取（未驗證）',
      STALE:'歷史來源',AUTH:'需要 Owner 登入',
      FAILED:'來源不可用',MANUAL:'本機手動檔案'
    };
    for (const viewName of ['home','trade','reports']) {
      const p=view[viewName];if(!p)continue;
      p.badge.textContent=labels[state] || '未連線';
      p.detail.textContent=detail;
      p.fine.textContent='真實市場資料來源、虛擬資金、完整 24h 策略及損益均需獨立核實；禁止當作真實獲利';
    }
    if(view.button)view.button.disabled=STORE.busy;
  }
  function requireCondition(ok, reason) {
    if (!ok) throw new Error(reason);
  }
  function validate(data) {
    requireCondition(data && typeof data==='object' && !Array.isArray(data),'INVALID_OBJECT');
    requireCondition(data.schema_version==='jubao-report-v1' &&
      data.paper_only===true && data.live_trading===false,'UNSAFE_MODE');
    const p=data.provenance;
    requireCondition(p && p.mode==='LOCAL_ACTIVE_WAL_RO' &&
      p.profit_verified===false && p.runtime_verified===false &&
      p.heartbeat_verified===false && p.source_identity_verified===false,
      'UNTRUSTED_PROVENANCE');
    const stamp=data.generated_at_utc;
    requireCondition(typeof stamp==='string' &&
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(stamp),
      'INVALID_TIMESTAMP');
    const millis=Date.parse(stamp);
    requireCondition(Number.isFinite(millis) && new Date(millis).toISOString().slice(0,19)===stamp.slice(0,19) &&
      millis<=Date.now()+5*60*1000,'INVALID_OR_FUTURE_TIMESTAMP');
    requireCondition(Array.isArray(data.engines) && data.engines.length===3,'WRONG_ENGINES');
    const results=[];
    for(let i=0;i<3;i++){
      const v=data.engines[i];
      requireCondition(v && typeof v==='object' && v.id===ENGINES[i],'ENGINE_ORDER');
      if(i===2) {
        requireCondition(v.source==='SOLANA_MONITOR_SNAPSHOT' && v.connected===false &&
          v.open_trades===null && v.closed_trades===null &&
          v.realized_pnl_usdt===null,'B_MUST_REMAIN_UNKNOWN');
        results.push({id:v.id,source:v.source,connected:false,open_trades:null,
          closed_trades:null,realized_pnl_usdt:null,
          notice:'B：監控服務存在不等於可信 Swap；數據未驗證'});
        continue;
      }
      const connected=v.source==='DRY_RUN_SQLITE_READ_ONLY' && v.connected===true;
      const absent=v.source==='NOT_CONNECTED' && v.connected===false;
      requireCondition(connected||absent,'UNVERIFIED_ENGINE_SOURCE');
      const validCount=n=>Number.isSafeInteger(n)&&n>=0&&n<=500000;
      const validMoney=n=>n===null||(typeof n==='string' &&
         /^-?\d{1,40}(?:\.\d{1,20})?$/.test(n) &&
         Number.isFinite(Number(n)) && Math.abs(Number(n))<1e14);
      requireCondition(connected?
        (validCount(v.closed_trades)&&validCount(v.open_trades)&&validMoney(v.realized_pnl_usdt)):
        (v.closed_trades===null&&v.open_trades===null&&v.realized_pnl_usdt===null),
        'INVALID_AGGREGATE');
      results.push({id:v.id,source:v.source,connected,
        open_trades:connected?v.open_trades:null,
        closed_trades:connected?v.closed_trades:null,
        realized_pnl_usdt:connected?v.realized_pnl_usdt:null,
        notice:'受保護同源彙總（來源尚未獨立驗證；非實盤獲利）'});
    }
    const ageH=Math.max(0,(Date.now()-millis)/3600000);
    return {report:{schema_version:'jubao-report-v1',generated_at_utc:stamp,
      brand:'JUBAO Owner 同源模擬資料：未獨立驗證',
      live_trading:false,paper_only:true,
      provenance:{mode:'LOCAL_ACTIVE_WAL_RO',runtime_verified:false,
        profit_verified:false,heartbeat_verified:false,source_identity_verified:false},
      engines:results},ageH};
  }
  function resetBridgeData() {
    if(!STORE.applied)return;
    const reset=document.querySelector('#resetReport');
    if(reset)reset.click();
    STORE.applied=false;
  }
  function importThroughExistingR8(report) {
    return new Promise((resolve,reject)=>{
      const input=document.querySelector('#importFile');
      const status=document.querySelector('#importStatus');
      if(!input||!status||typeof DataTransfer!=='function')
        return reject(new Error('R8_IMPORT_NOT_AVAILABLE'));
      const raw=JSON.stringify(report);
      if(raw.length>MAX_BYTES)return reject(new Error('TOO_LARGE'));
      const dt=new DataTransfer();
      dt.items.add(new File([raw],'r16-owner-session-paper.json',{type:'application/json'}));
      let done=false;
      const finish=ok=>{
        if(done)return;
        done=true; observer.disconnect();clearTimeout(timer);
        if(ok)resolve(); else reject(new Error('R8_VALIDATION_REJECTED'));
      };
      const observer=new MutationObserver(()=>{
        const text=status.textContent||'';
        if(text.includes('已在手機本機讀取'))finish(true);
        else if(text.includes('匯入失敗')||text.includes('超過 1MB'))finish(false);
      });
      observer.observe(status,{childList:true,subtree:true,characterData:true});
      const timer=setTimeout(()=>finish(false),5000);
      status.textContent='R16 正在驗證同源資料';
      input.files=dt.files;
      input.dispatchEvent(new Event('change',{bubbles:true}));
    });
  }
  async function refresh() {
    if(STORE.busy||STORE.manualOverride||document.hidden)return false;
    STORE.busy=true;
    show('LOADING','正在檢查 Owner 同源報表；不會向交易所下單');
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),8000);
    try{
      const reply=await fetch(ENDPOINT,{
        method:'GET',credentials:'same-origin',cache:'no-store',
        headers:{Accept:'application/json'},redirect:'error',signal:controller.signal
      });
      if(reply.status===401||reply.status===403){
        resetBridgeData();show('AUTH','請先完成 Owner 登入；不使用前端金鑰或 Bearer token');
        return false;
      }
      if(!reply.ok)throw new Error('UNAVAILABLE');
      const type=reply.headers.get('content-type')||'';
      requireCondition(type.toLowerCase().includes('application/json'),'NOT_JSON');
      const bytes=await reply.arrayBuffer();
      requireCondition(bytes.byteLength>0&&bytes.byteLength<=MAX_BYTES,'PAYLOAD_SIZE');
      const raw=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
      const {report,ageH}=validate(raw);
      await importThroughExistingR8(report);
      STORE.applied=true;
      STORE.lastFetchUtc=new Date().toISOString();
      if(document.querySelector('#importStatus'))
        document.querySelector('#importStatus').textContent='R16：已由受保護同源連線讀取，數據未獨立驗證';
      const message='來源時間：'+report.generated_at_utc+
        ' UTC；本次讀取：'+STORE.lastFetchUtc+
        '；A1/A2 僅為虛擬交易已實現損益彙總，無錢包 Equity／浮動盈虧';
      show(ageH>MAX_AGE_HOURS?'STALE':'SYNCED',message);
      return true;
    }catch(_){
      resetBridgeData();
      show('FAILED','報表無效、過期授權或暫時無法取得；已清除先前自動顯示的損益');
      return false;
    }finally{
      clearTimeout(timeout);
      STORE.busy=false;
      if(view.button)view.button.disabled=false;
    }
  }
  function boot(){
    for(const name of ['home','trade','reports'])makePanel(name);
    const input=document.querySelector('#importFile');
    if(input)input.addEventListener('change',e=>{
      if(e.isTrusted){
        STORE.manualOverride=true;
        STORE.applied=false;
        show('MANUAL','使用者已切換成本機手動 JSON；暫停自動覆寫，可按手動重新讀取恢復');
      }
    });
    document.addEventListener('visibilitychange',()=>{
      if(!document.hidden&&!STORE.manualOverride)refresh();
    });
    const timerId=window.setInterval(()=>{if(!document.hidden)refresh();},REFRESH_MS);
    window.addEventListener('pagehide',()=>window.clearInterval(timerId),{once:true});
    refresh();
  }
  window.__JUBAO_R16__={refresh,validate,stop:()=>{STORE.manualOverride=true;resetBridgeData();show('MANUAL','已停止本頁自動讀取');},
    getState:()=>({status:STORE.status,lastFetchUtc:STORE.lastFetchUtc,
      applied:STORE.applied,manualOverride:STORE.manualOverride})};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
