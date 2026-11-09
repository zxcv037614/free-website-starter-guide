/* JUBAO R18 isolated HTTPS Owner-session mobile controls.
 * NEVER deploy as production authentication. Only a synthetic localhost
 * fixture with a self-signed certificate and generated test-only secrets.
 * Preserves the original five pages and black-gold whale logo unchanged.
 */
(function () {
  'use strict';
  if (window.__JUBAO_R18__) return;
  const LOGIN = '/api/v1/owner/session';
  const LOGOUT = '/api/v1/owner/logout';
  const MAX_SECONDS = 8;
  const store = {busy: false, status: 'SIGNED_OUT'};
  const nodes = {};

  function node(tag, value) {
    const n = document.createElement(tag);
    if (value != null) n.textContent = value;
    return n;
  }
  function announce(status, message) {
    store.status = status;
    if(nodes.status)nodes.status.textContent = message;
    if(nodes.login)nodes.login.disabled = store.busy;
    if(nodes.logout)nodes.logout.disabled = store.busy;
  }
  async function post(path, payload) {
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), MAX_SECONDS * 1000);
    try {
      const res = await fetch(path, {
        method: 'POST', credentials: 'same-origin', redirect: 'error',
        cache: 'no-store',
        headers: {'Content-Type': 'application/json', Accept: 'application/json'},
        body: JSON.stringify(payload), signal: abort.signal
      });
      if (!res.ok) return false;
      if (!(res.headers.get('Content-Type') || '').toLowerCase().includes('application/json')) return false;
      const bytes = await res.arrayBuffer();
      if (bytes.byteLength < 1 || bytes.byteLength > 4096) return false;
      const obj = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
      return path === LOGIN ? obj?.authenticated === true && obj?.test_only === true
                            : obj?.authenticated === false;
    } catch (_) { return false; }
    finally { clearTimeout(timeout); }
  }

  async function login(value) {
    if(store.busy) return false;
    if(typeof value !== 'string' || value.length > 4096) return false;
    store.busy = true;
    announce('AUTHENTICATING','正在驗證本機測試用 Owner Session');
    try {
      const allowed = await post(LOGIN, {owner_secret: value});
      if (!allowed) {
        announce('SIGNED_OUT','未授權或登入失敗，未取得任何模擬損益');
        return false;
      }
      announce('AUTHENTICATED','本機測試 Session 已建立；資料仍為合成，不是 VPS 獲利');
      const synced = await window.__JUBAO_R16__?.refresh();
      announce(synced ? 'SYNCED_TEST' : 'AUTHENTICATED',
        synced ? '隔離合成 A1/A2 模擬資料已更新，非真實 VPS 帳本'
               : '測試登入成功，但模擬報表暫時不可用');
      return Boolean(synced);
    } finally {
      store.busy = false;
      announce(store.status,nodes.status?.textContent || '');
    }
  }

  async function logout() {
    if(store.busy) return false;
    store.busy = true;
    announce('SIGNING_OUT','正在撤銷本機 Owner Session');
    try {
      const ok = await post(LOGOUT, {});
      if (!ok) {
        announce('ERROR','登出未確認，請關閉測試瀏覽器並停止本機服務');
        return false;
      }
      window.__JUBAO_R16__?.clearSession();
      announce('SIGNED_OUT','Owner 已登出；先前自動顯示的損益已清除');
      return true;
    } finally {
      store.busy = false;
      announce(store.status,nodes.status?.textContent || '');
    }
  }

  function render() {
    const home = document.querySelector('.section[data-page="home"]');
    if(!home || !window.__JUBAO_R16__) return;
    const panel = node('section');
    panel.id = 'r18OwnerLogin';
    panel.style.cssText = 'box-sizing:border-box;max-width:100%;padding:14px;'+
      'margin:10px 0;border-radius:12px;border:1px solid rgba(223,181,86,.45);'+
      'background:rgba(8,20,38,.96);color:#eddcae;'+
      'font:13px/1.5 system-ui,sans-serif;';
    panel.setAttribute('aria-label','R18 Owner 本機測試登入');
    const head = node('strong','Owner 登入｜R18 隔離測試');
    const warn = node('p','只供 localhost HTTPS 合成測試。不是正式登入，也不連接實際交易帳本。');
    warn.style.cssText='margin:6px 0 12px;color:#b9c4d1;';
    const label = node('label','測試用 Owner 密語');
    label.htmlFor='r18OwnerSecret';
    label.style.cssText='display:block;margin-bottom:5px;';
    const input = node('input');
    input.id='r18OwnerSecret';
    input.type='password';
    input.autocomplete='off';
    input.placeholder='僅限合成測試密語';
    input.style.cssText='box-sizing:border-box;width:100%;max-width:100%;'+
      'background:#0d223d;color:white;border:1px solid #876c36;'+
      'border-radius:8px;padding:10px;font:inherit;';
    const actions=node('div');
    actions.style.cssText='display:flex;flex-wrap:wrap;gap:8px;margin-top:9px;';
    const enter=node('button','登入（測試）');
    enter.id='r18LoginButton';enter.type='button';
    const out=node('button','登出');
    out.id='r18LogoutButton';out.type='button';
    for(const button of [enter,out])button.style.cssText=
      'background:#142943;color:#f0dfb6;'+
      'border:1px solid #ad8d4d;padding:9px 12px;border-radius:9px;cursor:pointer;';
    const status=node('p','尚未登入；A1/A2 模擬帳本保持未知');
    status.id='r18LoginStatus';status.setAttribute('role','status');
    status.style.cssText='margin:10px 0 0;color:#e1c883;';
    enter.addEventListener('click', async () => {
      const value=input.value;
      input.value='';
      await login(value);
    });
    out.addEventListener('click', () => {input.value='';logout();});
    input.addEventListener('keydown', event => {if(event.key==='Enter')enter.click();});
    actions.append(enter,out);
    panel.append(head,warn,label,input,actions,status);
    home.prepend(panel);
    Object.assign(nodes,{status,login:enter,logout:out,input,panel});
  }
  window.__JUBAO_R18__={login,logout,getState:()=>({...store})};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render,{once:true});
  else render();
})();
