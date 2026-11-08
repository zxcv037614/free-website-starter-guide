'use strict';
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const file = path.join(__dirname, '..', 'index.html');
const raw = fs.readFileSync(file);
let done = 0;
function check(desc, cond) { assert.ok(cond, desc); done++; console.log('PASS', String(done).padStart(2,'0'), desc); }
const base = {
  schema_version:'jubao-report-v1',generated_at_utc:'2026-11-08T00:00:00Z',
  brand:'Jubao QA fixture ONLY',live_trading:false,paper_only:true,
  engines:[
    {id:'spot',source:'DRY_RUN_SQLITE_READ_ONLY',connected:true,closed_trades:2,open_trades:1,realized_pnl_usdt:'12.34',notice:'Synthetic QA input, not VPS'},
    {id:'futures',source:'NOT_CONNECTED',connected:false,closed_trades:null,open_trades:null,realized_pnl_usdt:null,notice:'Not connected'},
    {id:'solana',source:'SOLANA_MONITOR_SNAPSHOT',connected:false,closed_trades:null,open_trades:null,realized_pnl_usdt:null,notice:'Historical only'}
  ]
};
const clone = x => JSON.parse(JSON.stringify(x));
const fixture = [
  {symbol:'BTCUSDT',price:'85000.12'},
  {symbol:'ETHUSDT',price:'3000.45'},
  {symbol:'SOLUSDT',price:'180.67'}
];
async function main() {
  const server=http.createServer((req,res)=>{
    if(req.url==='/'||req.url==='/index.html'){
      res.writeHead(200,{'content-type':'text/html; charset=utf-8','cache-control':'no-store'});res.end(raw);
    } else { res.writeHead(404); res.end('Not Found');}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const root='http://127.0.0.1:'+server.address().port;
  let browser;
  try {
    browser=await chromium.launch({headless:true,args:['--no-sandbox']});
    for(const [label,viewport] of [['mobile',{width:390,height:844}],['tablet',{width:900,height:600}]]) {
      const page=await browser.newPage({viewport,deviceScaleFactor:1});
      let reportRequests=0, tradeRequests=0;
      const errors=[];
      page.on('pageerror', e=>errors.push(String(e)));
      await page.route('**/*',async route=>{
        const u=route.request().url();
        if(u.startsWith('https://data-api.binance.vision/')){
          return route.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify(fixture)});
        }
        if(u.includes('/api/report')){reportRequests++;return route.abort();}
        if(/\/(order|withdraw|transfer)(\/|\?|$)/i.test(u)){tradeRequests++;return route.abort();}
        return route.continue();
      });
      await page.goto(root+'/',{waitUntil:'domcontentloaded'});
      await page.waitForTimeout(250);
      check(label+': five pages',await page.locator('.section[data-page]').count()===5);
      check(label+': five navigation items',await page.locator('[data-nav]').count()===5);
      check(label+': original logo remains',await page.locator('#brandLogo').count()===1);
      check(label+': all three disabled control buttons',await page.locator('button[disabled]').count()>=3);
      check(label+': starting PnL is not invented',(await page.locator('#netPnl').textContent()).includes('—'));
      await page.waitForFunction(()=>document.querySelector('#priceBTC')?.textContent?.includes('85,000'),{timeout:6000});
      check(label+': synthetic public quotes shown',(await page.locator('#priceSOL').textContent()).includes('180.67'));
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
      check(label+': no horizontal overflow ('+overflow+'px)',overflow<=2);
      for(const p of ['home','trade','whale','risk','reports']){
        await page.locator('[data-nav="'+p+'"]').click();
        check(label+': navigation '+p,await page.locator('.section[data-page="'+p+'"]').evaluate(el=>el.classList.contains('active')));
      }
      await page.locator('[data-nav="trade"]').click();
      await page.locator('[data-trade="futures"]').click();
      check(label+': A2 switch',(await page.locator('#tradeTitle').textContent()).includes('A2'));
      check(label+': A2 missing PnL remains dash',(await page.locator('#tradePnl').textContent()).includes('—'));
      check(label+': start is disabled',await page.getByRole('button',{name:/啟動自動交易/}).isDisabled());
      check(label+': stop is disabled',await page.getByRole('button',{name:/停止引擎/}).isDisabled());
      await page.locator('[data-nav="risk"]').click();
      await page.locator('#riskSlider').evaluate(el=>{el.value='1.8';el.dispatchEvent(new Event('input',{bubbles:true}));});
      check(label+': risk slider preview',(await page.locator('#riskOut').textContent()).includes('1.8%'));
      await page.locator('#leverageSlider').evaluate(el=>{el.value='1';el.dispatchEvent(new Event('input',{bubbles:true}));});
      check(label+': leverage slider preview',(await page.locator('#leverageOut').textContent()).includes('1×'));
      await page.locator('[data-nav="reports"]').click();
      async function upload(data,name='test.json'){
        const buf=typeof data==='string'?Buffer.from(data):Buffer.from(JSON.stringify(data));
        await page.locator('#importFile').setInputFiles([]);
        await page.locator('#importStatus').evaluate(el=>{el.textContent='PENDING_QA';});
        await page.locator('#importFile').setInputFiles({name,mimeType:'application/json',buffer:buf});
        await page.waitForFunction(()=>document.querySelector('#importStatus').textContent!=='PENDING_QA',{timeout:8000});
        return await page.locator('#importStatus').textContent();
      }
      let st=await upload(base,'qa-valid.json');
      check(label+': valid JSON imported',st.includes('已在手機本機讀取'));
      check(label+': source explicitly unverified',(await page.locator('#globalStatus').textContent()).includes('部分報表已匯入'));
      await page.locator('[data-nav="trade"]').click();
      await page.locator('[data-trade="spot"]').click();
      check(label+': imported PnL shown as unverified', (await page.locator('#tradePnl').textContent()).includes('12.34')&&(await page.locator('#tradeState').textContent()).includes('未驗來源'));
      await page.locator('[data-nav="reports"]').click();
      const badSource=clone(base);badSource.engines[0].source='toString';
      st=await upload(badSource);check(label+': prototype source rejected',st.includes('匯入失敗'));
      const badUnconnected=clone(base);badUnconnected.engines[1].realized_pnl_usdt='999';
      st=await upload(badUnconnected);check(label+': fabricated disconnected PnL rejected',st.includes('匯入失敗'));
      const wrongEngine=clone(base);wrongEngine.engines[0].source='SOLANA_MONITOR_SQLITE_READ_ONLY';
      st=await upload(wrongEngine);check(label+': cross-engine source rejected',st.includes('匯入失敗'));
      const live=clone(base);live.live_trading=true;
      st=await upload(live);check(label+': live trading report rejected',st.includes('匯入失敗'));
      const syntheticConnected=clone(base);syntheticConnected.engines[0].source='SYNTHETIC_FIXTURE_ONLY';
      st=await upload(syntheticConnected);check(label+': synthetic connected status rejected',st.includes('匯入失敗'));
      st=await upload('{ invalid json');check(label+': invalid JSON rejected',st.includes('匯入失敗'));
      st=await upload('x'.repeat(1024*1024+1),'qa-too-large.json');
      check(label+': >1MB rejected',st.includes('超過 1MB'));
      await page.locator('#resetReport').click();
      check(label+': reset restores disconnected state',(await page.locator('#globalStatus').textContent()).includes('未連線'));
      check(label+': no report API was called',reportRequests===0);
      check(label+': no trade endpoint called',tradeRequests===0);
      check(label+': no JS page errors ('+errors.join('; ').slice(0,120)+')',errors.length===0);
      await page.locator('[data-nav="home"]').click();
      await fs.promises.mkdir(path.join(__dirname,'artifacts'),{recursive:true});
      await page.screenshot({path:path.join(__dirname,'artifacts','r7-'+label+'.png'),fullPage:true});
      await page.close();
    }
    console.log('R7 Browser QA total:',done,'PASS; no live trading, no real credentials, no DO and no deploy.');
  } finally {
    if(browser)await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
}
main().catch(err=>{console.error('R7 QA FAIL:',err.stack||err);process.exitCode=1;});
