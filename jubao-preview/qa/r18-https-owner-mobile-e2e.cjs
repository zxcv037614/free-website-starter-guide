'use strict';
/* JUBAO R18: actual Chromium -> synthetic HTTPS 5-page R8 UI
 * -> HttpOnly Secure Owner Session -> REAL R17 gateway -> REAL R15 API
 * -> SYNTHETIC fixtures. No DigitalOcean, no live assets, no real credentials.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const original = path.join(root, 'index.html');
const originalHash = crypto.createHash('sha256').update(fs.readFileSync(original)).digest('hex');
const TEST_SECRET = 'R18-TEST-ONLY-OWNER-NOT-FOR-DEPLOY-' + 'e'.repeat(40);
const CERT = process.env.R18_TLS_CERT;
const KEY = process.env.R18_TLS_KEY;
if (!CERT || !KEY) throw Error('Missing ephemeral TLS cert/key paths (CI-only)');
let count = 0;
function check(text, ok) {
  assert.ok(ok, text); count++;
  console.log('PASS', count, text);
}
function launchFixture() {
  return new Promise((resolve,reject)=>{
    const proc = spawn('python3', [
      path.join(__dirname,'r18_synthetic_https_fixture.py'),
      '--cert', CERT, '--key', KEY
    ], {cwd:root,stdio:['ignore','pipe','pipe']});
    let output='',err='';
    const deadline=setTimeout(()=>{
      proc.kill();reject(new Error('R18 local fixture startup timeout; '+err.slice(-250)));
    },10000);
    proc.stdout.setEncoding('utf8');
    proc.stderr.setEncoding('utf8');
    proc.stderr.on('data',chunk=>{err+=(chunk||'').slice(0,500);});
    proc.once('exit',code=>{
      clearTimeout(deadline);
      reject(new Error('R18 fixture exited code '+code+'; '+err.slice(-500)));
    });
    proc.stdout.on('data',chunk=>{
      output+=chunk;
      const match=output.match(/https:\/\/127\.0\.0\.1:(\d+)\r?\n/);
      if(match){
        clearTimeout(deadline);
        resolve({proc,origin:'https://127.0.0.1:'+match[1]});
      }
    });
  });
}
async function main(){
  const {proc,origin} = await launchFixture();
  let browser;
  try {
    browser=await chromium.launch({headless:true,args:['--no-sandbox']});
    check('Original whale UI source hash unchanged',
      crypto.createHash('sha256').update(fs.readFileSync(original)).digest('hex')===originalHash);
    for(const [device,viewport] of [['Samsung-size',{width:390,height:844}],
                                    ['tablet',{width:900,height:600}]]) {
      const context=await browser.newContext({viewport,ignoreHTTPSErrors:true,deviceScaleFactor:1});
      const page=await context.newPage();
      const jsErrors=[];let external=0,orders=0,secretLeaks=0;
      page.on('pageerror',e=>jsErrors.push(String(e)));
      page.on('request', req=>{
        if(req.url().includes('/api/v1/owner/paper-report')
          && req.headers()['authorization'])secretLeaks++;
      });
      await page.route('**/*',async route=>{
        const url=route.request().url();
        if(url.startsWith('https://data-api.binance.vision/')){
          return route.fulfill({
            status:200,contentType:'application/json',
            headers:{'access-control-allow-origin':'*'},
            body:JSON.stringify([{symbol:'BTCUSDT',price:'85000.12'},
              {symbol:'ETHUSDT',price:'3000.45'},{symbol:'SOLUSDT',price:'180.67'}])
          });
        }
        if(/\/(order|withdraw|transfer)(\/|\?|$)/i.test(url)){orders++;return route.abort();}
        if(url.startsWith(origin+'/'))return route.continue();
        external++;return route.abort();
      });
      await page.goto(origin+'/',{waitUntil:'domcontentloaded'});
      await page.waitForFunction(()=>window.__JUBAO_R16__?.getState().status==='AUTH',null,{timeout:8000});
      check(device+' original 5 tabs',await page.locator('.section[data-page]').count()===5);
      check(device+' original whale logo',await page.locator('#brandLogo').count()===1);
      check(device+' three R16 Owner panels',await page.locator('.r16-owner-panel').count()===3);
      check(device+' R18 login control exists',await page.locator('#r18OwnerLogin').count()===1);
      check(device+' initial simulated PnL UNKNOWN',(await page.locator('#netPnl').textContent()).includes('—'));
      check(device+' report endpoint blocked before login',
        await page.evaluate(async()=> (await fetch('/api/v1/owner/paper-report')).status)===401);
      await page.locator('#r18OwnerSecret').fill('invalid-fixture-secret');
      await page.locator('#r18LoginButton').click();
      await page.waitForFunction(()=>window.__JUBAO_R18__?.getState().status==='SIGNED_OUT');
      check(device+' failed login remains UNKNOWN',(await page.locator('#netPnl').textContent()).includes('—'));
      check(device+' login input cleared',await page.locator('#r18OwnerSecret').inputValue()==='');
      await page.locator('#r18OwnerSecret').fill(TEST_SECRET);
      await page.locator('#r18LoginButton').click();
      await page.waitForFunction(()=>window.__JUBAO_R18__?.getState().status==='SYNCED_TEST',null,{timeout:10000});
      check(device+' HTTPS Secure Cookie set',
        (await context.cookies(origin)).some(c=>c.name==='__Host-jubao_owner'&&c.secure&&c.httpOnly&&c.sameSite==='Strict'));
      check(device+' real R17->R15 synthetic aggregate sync to UI',
        (await page.locator('#netPnl').textContent()).includes('7.75'));
      check(device+' UI admits synthetic-only/unverified',
        (await page.locator('#r18LoginStatus').textContent()).includes('合成')
        && (await page.locator('#r16Panel-home').textContent()).includes('未驗證'));
      check(device+' R15 private endpoint not exposed',
        await page.evaluate(async()=> (await fetch('/api/v1/paper-report')).status)===404);
      const report=await page.evaluate(async()=> {
        const response=await fetch('/api/v1/owner/paper-report',{credentials:'same-origin',cache:'no-store'});
        return {status:response.status, data:await response.json()};
      });
      check(device+' R17 report provenance unverified',report.status===200
        &&report.data.paper_only===true&&report.data.live_trading===false
        &&report.data.provenance.profit_verified===false);
      await page.locator('[data-nav="trade"]').click();
      await page.locator('[data-trade="spot"]').click();
      check(device+' A1 spot 11.25 synthetic',(await page.locator('#tradePnl').textContent()).includes('11.25'));
      await page.locator('[data-trade="futures"]').click();
      check(device+' A2 futures -3.50 synthetic',(await page.locator('#tradePnl').textContent()).includes('-3.50'));
      await page.locator('[data-nav="whale"]').click();
      check(device+' B no invented Swap profit',(await page.locator('#whalePnl').textContent()).includes('—'));
      await page.locator('[data-nav="home"]').click();
      // A broken private upstream must clear the old aggregate.
      await page.route('**/api/v1/owner/paper-report',async route=>route.fulfill({
        status:503,contentType:'application/json',body:'{"error":"REPORT_UNAVAILABLE"}'
      }));
      check(device+' 503 fail closed',
        !(await page.evaluate(()=>window.__JUBAO_R16__.refresh())));
      check(device+' 503 clears stale PnL',(await page.locator('#netPnl').textContent()).includes('—'));
      await page.unroute('**/api/v1/owner/paper-report');
      check(device+' automatic report can recover',
        await page.evaluate(()=>window.__JUBAO_R16__.refresh())
        &&(await page.locator('#netPnl').textContent()).includes('7.75'));
      // A valid session must not accept falsified live-trading results.
      const unsafe=structuredClone(report.data);unsafe.live_trading=true;
      await page.route('**/api/v1/owner/paper-report',async route=>route.fulfill({
        status:200,contentType:'application/json',body:JSON.stringify(unsafe)
      }));
      check(device+' browser rejects live_trading=true',
        !(await page.evaluate(()=>window.__JUBAO_R16__.refresh())));
      check(device+' forged result leaves PnL unknown',(await page.locator('#netPnl').textContent()).includes('—'));
      await page.unroute('**/api/v1/owner/paper-report');
      check(device+' normal service restores aggregate',
        await page.evaluate(()=>window.__JUBAO_R16__.refresh()));
      await page.locator('#r18LogoutButton').click();
      await page.waitForFunction(()=>window.__JUBAO_R18__?.getState().status==='SIGNED_OUT');
      check(device+' logout removes aggregate immediately',(await page.locator('#netPnl').textContent()).includes('—'));
      check(device+' logout truly revokes R17 server Session',
        await page.evaluate(async()=> (await fetch('/api/v1/owner/paper-report')).status)===401);
      await page.reload({waitUntil:'domcontentloaded'});
      await page.waitForFunction(()=>window.__JUBAO_R16__?.getState().status==='AUTH');
      check(device+' reload cannot reintroduce signed-out profit',
        (await page.locator('#netPnl').textContent()).includes('—'));
      check(device+' no horizontal overflow',
        (await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))<=2);
      check(device+' no browser Bearer or unwanted order/external calls',
        secretLeaks===0&&orders===0&&external===0);
      check(device+' no uncaught browser exceptions '+jsErrors.join('; ').slice(0,100),
        jsErrors.length===0);
      await context.close();
    }
    console.log('JUBAO R18 HTTPS REAL-CHAIN SYNTHETIC MOBILE E2E PASS',count,
      'assertions; NO VPS, NO PRODUCTION, NO LIVE PNL');
  } finally {
    if(browser)await browser.close();
    proc.kill('SIGTERM');
  }
}
main().catch(error=>{console.error('R18 HTTPS CI failure:',error.stack||error);process.exitCode=1;});
