'use strict';
// JUBAO R16 SANDBOX Playwright: real unchanged R8 HTML + injected R16
// session-only same-origin synthetic paper response. NO VPS, NO TRADE KEYS.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const http=require('node:http');
const path=require('node:path');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const original=fs.readFileSync(path.join(root,'index.html'),'utf8');
const bridge=fs.readFileSync(path.join(root,'bridge','r16_owner_dashboard_sync.js'));
const prices=[{symbol:'BTCUSDT',price:'85000.12'},
              {symbol:'ETHUSDT',price:'3000.45'},
              {symbol:'SOLUSDT',price:'180.67'}];
const now=()=>new Date(Date.now()-2*60*1000).toISOString().slice(0,19)+'Z';
const clone=x=>JSON.parse(JSON.stringify(x));
function fixture(){
  return {
    schema_version:'jubao-report-v1',
    generated_at_utc:now(),paper_only:true,live_trading:false,
    brand:'R16 SYNTHETIC PRIVATE PAPER FIXTURE; NOT VPS',
    provenance:{mode:'LOCAL_ACTIVE_WAL_RO',heartbeat_verified:false,
                runtime_verified:false,profit_verified:false,source_identity_verified:false},
    engines:[
      {id:'spot',source:'DRY_RUN_SQLITE_READ_ONLY',connected:true,
       closed_trades:2,open_trades:1,realized_pnl_usdt:'11.25'},
      {id:'futures',source:'DRY_RUN_SQLITE_READ_ONLY',connected:true,
       closed_trades:2,open_trades:0,realized_pnl_usdt:'-3.50'},
      {id:'solana',source:'SOLANA_MONITOR_SNAPSHOT',connected:false,
       closed_trades:null,open_trades:null,realized_pnl_usdt:null}
    ]
  };
}
let passed=0;
function check(message,condition){assert.ok(condition,message);passed++;console.log('PASS',passed,message);}
async function main(){
  let mode='good',value=fixture(),calls=[],server,browser;
  const html=original.replace('</body>','<script defer src="/bridge/r16_owner_dashboard_sync.js"></script></body>');
  if(html===original)throw Error('Original black-gold R8 HTML missing closing body tag');
  const originHash=require('node:crypto').createHash('sha256').update(original).digest('hex');
  server=http.createServer((req,res)=>{
    if(req.url==='/api/v1/owner/paper-report'){
      calls.push({url:req.url,method:req.method,auth:req.headers.authorization??null});
      res.setHeader('Content-Type','application/json; charset=utf-8');
      res.setHeader('Cache-Control','no-store');
      if(!String(req.headers.cookie||'').includes('owner_session=synthetic-authorized')){
        res.statusCode=401;return res.end('{"error":"UNAUTHORIZED"}');
      }
      if(mode==='503'){res.statusCode=503;return res.end('{"error":"REPORT_UNAVAILABLE"}');}
      const body=mode==='oversize'?'x'.repeat(1024*1024+1):JSON.stringify(value);
      return res.end(body);
    }
    if(req.url==='/'||req.url==='/index.html'){
      res.setHeader('Content-Type','text/html; charset=utf-8');
      res.setHeader('Cache-Control','no-store');
      return res.end(html);
    }
    if(req.url==='/bridge/r16_owner_dashboard_sync.js'){
      res.setHeader('Content-Type','application/javascript; charset=utf-8');
      return res.end(bridge);
    }
    res.statusCode=404;return res.end('Not Found');
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin='http://127.0.0.1:'+server.address().port;
  try{
    browser=await chromium.launch({headless:true,args:['--no-sandbox']});
    check('R8 original HTML source hash remains unchanged',
      require('node:crypto').createHash('sha256')
        .update(fs.readFileSync(path.join(root,'index.html'))).digest('hex')===originHash);
    check('R16 script never embeds R15 Bearer token or uses localStorage',
      !/JUBAO_R15_OWNER_TOKEN|localStorage|Authorization\s*:|Bearer /.test(String(bridge)));
    for (const [label,viewport] of [['mobile',{width:390,height:844}],
                                   ['tablet',{width:900,height:600}]]){
      const context=await browser.newContext({viewport,deviceScaleFactor:1});
      const page=await context.newPage();
      let external=0,orders=0;const errors=[];
      page.on('pageerror',e=>errors.push(String(e)));
      await page.route('**/*',async route=>{
        const url=route.request().url();
        if(url.startsWith('https://data-api.binance.vision/')){
          return route.fulfill({status:200,contentType:'application/json',
              headers:{'access-control-allow-origin':'*'},body:JSON.stringify(prices)});
        }
        if(/\/(order|withdraw|transfer)(\/|\?|$)/i.test(url)){orders++;return route.abort();}
        if(url.startsWith(origin+'/'))return route.continue();
        external++;return route.abort();
      });
      mode='good';value=fixture();calls=[];
      await page.goto(origin+'/',{waitUntil:'domcontentloaded'});
      await page.waitForFunction(()=>window.__JUBAO_R16__?.getState().status==='AUTH');
      check(label+' initial unauthorized session refused', (await page.evaluate(()=>window.__JUBAO_R16__.getState())).status==='AUTH');
      check(label+' original five tabs unchanged',(await page.locator('.section[data-page]').count())===5
        &&(await page.locator('[data-nav]').count())===5);
      check(label+' original whale logo still present',(await page.locator('#brandLogo').count())===1);
      check(label+' trade action buttons still disabled',(await page.locator('button[disabled]').count())>=3);
      check(label+' three additive owner panels',await page.locator('.r16-owner-panel').count()===3);
      check(label+' no invented initial profit',(await page.locator('#netPnl').textContent()).includes('—'));
      check(label+' endpoint called without browser Bearer token',calls.length===1&&calls[0].auth===null);
      await context.addCookies([{name:'owner_session',value:'synthetic-authorized',url:origin,
                                 httpOnly:true,secure:false,sameSite:'Strict'}]);
      check(label+' authorized same-origin synthetic source can sync',
        await page.evaluate(()=>window.__JUBAO_R16__.refresh()));
      check(label+' status explicitly UNVERIFIED',(await page.locator('#r16Panel-reports').textContent()).includes('未驗證'));
      check(label+' source flag not false verified',(await page.locator('#r8ReportOrigin').textContent()).includes('未驗來源'));
      check(label+' A1 + A2 synthetic net PnL correctly 7.75',(await page.locator('#netPnl').textContent()).includes('7.75'));
      await page.locator('[data-nav="trade"]').click();
      await page.locator('[data-trade="spot"]').click();
      check(label+' A1 trade pane updated',(await page.locator('#tradePnl').textContent()).includes('11.25')
        &&(await page.locator('#tradeClosed').textContent()).includes('2'));
      await page.locator('[data-trade="futures"]').click();
      check(label+' A2 trade pane updated',(await page.locator('#tradePnl').textContent()).includes('-3.50'));
      await page.locator('[data-nav="whale"]').click();
      check(label+' B profit remains unknown',(await page.locator('#whalePnl').textContent()).includes('—'));
      await page.locator('[data-nav="reports"]').click();
      check(label+' source and fetch timestamps visible',
        (await page.locator('#r16Panel-reports').textContent()).includes('來源時間')
        &&(await page.locator('#r16Panel-reports').textContent()).includes('本次讀取'));
      value=fixture();value.engines[0].realized_pnl_usdt='15.25';
      check(label+' manual fetch re-reads new on-demand aggregate',
        await page.evaluate(()=>window.__JUBAO_R16__.refresh()));
      check(label+' updated synthetic net PnL rendered',
        (await page.locator('#netPnl').textContent()).includes('11.75'));
      await context.clearCookies();
      check(label+' revoked session cannot refresh',
        !(await page.evaluate(()=>window.__JUBAO_R16__.refresh())));
      check(label+' revoked session clears prior synced PnL',
        (await page.locator('#netPnl').textContent()).includes('—')
        &&(await page.evaluate(()=>window.__JUBAO_R16__.getState())).status==='AUTH');
      await context.addCookies([{name:'owner_session',value:'synthetic-authorized',
        url:origin,httpOnly:true,sameSite:'Strict'}]);
      value=fixture();value.live_trading=true;
      check(label+' live trading payload fails closed',
        !(await page.evaluate(()=>window.__JUBAO_R16__.refresh())));
      check(label+' unsafe report cannot populate PnL',(await page.locator('#netPnl').textContent()).includes('—'));
      value=fixture();value.engines[2].realized_pnl_usdt='999999';
      check(label+' fabricated B swap profit rejected',
        !(await page.evaluate(()=>window.__JUBAO_R16__.refresh())));
      value=fixture();value.generated_at_utc=new Date(Date.now()+3600000).toISOString().slice(0,19)+'Z';
      check(label+' future-dated paper source rejected',
        !(await page.evaluate(()=>window.__JUBAO_R16__.refresh())));
      value=fixture();value.engines[1].source='NOT_CONNECTED';value.engines[1].connected=false;
      check(label+' disconnected engine cannot show profit',
        !(await page.evaluate(()=>window.__JUBAO_R16__.refresh())));
      value=fixture();value.generated_at_utc=new Date(Date.now()-48*3600000).toISOString().slice(0,19)+'Z';
      check(label+' stale authenticated source is marked historical',
        await page.evaluate(()=>window.__JUBAO_R16__.refresh())
        &&(await page.evaluate(()=>window.__JUBAO_R16__.getState())).status==='STALE');
      mode='503';
      check(label+' server 503 clears stale aggregate',
        !(await page.evaluate(()=>window.__JUBAO_R16__.refresh())));
      check(label+' failure does not leave simulated PnL',
        (await page.locator('#netPnl').textContent()).includes('—'));
      mode='good';value=fixture();
      check(label+' manual refresh button functions',await page.locator('#r16ManualRefresh').count()===1);
      await page.locator('#r16ManualRefresh').click();
      await page.waitForFunction(()=>window.__JUBAO_R16__.getState().status==='SYNCED');
      check(label+' manual refresh restored read-only data',
        (await page.locator('#netPnl').textContent()).includes('7.75'));
      for(const name of ['home','trade','whale','risk','reports']){
        await page.locator('[data-nav="'+name+'"]').click();
        check(label+' original navigation preserved '+name,
          await page.locator('.section[data-page="'+name+'"]').evaluate(x=>x.classList.contains('active')));
      }
      check(label+' 390/900 viewport no horizontal overflow',
        (await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))<=2);
      check(label+' no order or unexpected external request',orders===0&&external===0);
      check(label+' no JS exceptions '+errors.join('; ').slice(0,80),errors.length===0);
      await context.close();
    }
    console.log('JUBAO R16 ORIGINAL UI SESSION SYNC SYNTHETIC PASS',passed,
      'assertions; NO REAL VPS, NO DEPLOY, NO LIVE PROFITS');
  } finally{
    if(browser)await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
}
main().catch(err=>{console.error('R16 SYNTHETIC QA FAILED:',err.stack||err);process.exitCode=1;});
