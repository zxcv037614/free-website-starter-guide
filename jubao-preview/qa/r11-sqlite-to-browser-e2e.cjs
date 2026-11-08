'use strict';
// JUBAO R11: synthetic SQLite -> Python exporter -> Node gate -> R8 browser import.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const {spawnSync} = require('node:child_process');
const project = path.resolve(__dirname, '..');
const exporter = path.join(project, 'bridge', 'export-offline-paper-report.py');
const validator = path.join(project, 'bridge', 'offline-paper-report-validator.cjs');
const pageFile = path.join(project, 'index.html');
const FIXTURE_PY = [
  'import json,sqlite3,sys',
  'from pathlib import Path',
  'root=Path(sys.argv[1])',
  "for key,mode,records in [('spot','spot',[(0,10.5),(0,0.75),(1,None)]),('futures','futures',[(0,-4.5),(0,1.0)])]:",
  " db=root/(key+'.sqlite')",
  ' with sqlite3.connect(db) as c:',
  "  c.execute('CREATE TABLE trades (id INTEGER PRIMARY KEY,is_open INTEGER,close_profit_abs REAL)')",
  "  c.executemany('INSERT INTO trades (is_open,close_profit_abs) VALUES (?,?)',records)",
  '  c.commit()',
  " (root/(key+'.json')).write_text(json.dumps({'dry_run':True,'trading_mode':mode,'stake_currency':'USDT'}))"
].join('\n');
let passed=0;
function check(name, condition) {
  assert.ok(condition, name);
  passed++;
  console.log('PASS', String(passed).padStart(2,'0'), name);
}
function run(cmd, args, cwd) {
  const result = spawnSync(cmd, args, {cwd, encoding:'utf8', timeout:20000, maxBuffer:1024*1024});
  if(result.error) throw result.error;
  if(result.status !== 0) throw new Error(cmd+' failed: '+(result.stderr||result.stdout).slice(0,1000));
  return result.stdout.trim();
}
async function main() {
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'jubao-r11-'));
  let server,browser;
  try {
    run('python3',['-c',FIXTURE_PY,temp],temp);
    check('synthetic SQLite fixtures created', ['spot.sqlite','futures.sqlite'].every(x=>fs.existsSync(path.join(temp,x))));
    const oneHourAgo=new Date(Date.now()-3600000);
    for(const x of ['spot.sqlite','futures.sqlite']) fs.utimesSync(path.join(temp,x),oneHourAgo,oneHourAgo);
    const out=path.join(temp,'paper-review.json');
    run('python3',[exporter,'--spot-db',path.join(temp,'spot.sqlite'),'--spot-config',path.join(temp,'spot.json'),
      '--futures-db',path.join(temp,'futures.sqlite'),'--futures-config',path.join(temp,'futures.json'),'--out',out],temp);
    const paper=JSON.parse(fs.readFileSync(out,'utf8'));
    check('V1 paper-only report', paper.schema_version==='jubao-report-v1' && paper.live_trading===false && paper.paper_only===true);
    check('A1 synthetic closed and open trades',paper.engines[0].realized_pnl_usdt==='11.25' && paper.engines[0].closed_trades===2 && paper.engines[0].open_trades===1);
    check('A2 synthetic futures trades',paper.engines[1].realized_pnl_usdt==='-3.5' && paper.engines[1].closed_trades===2 && paper.engines[1].open_trades===0);
    check('B historical with no fake trades',paper.engines[2].source==='SOLANA_MONITOR_SNAPSHOT' && !paper.engines[2].connected && paper.engines[2].closed_trades===null && paper.engines[2].realized_pnl_usdt===null);
    check('unverified provenance flags',!paper.provenance.heartbeat_verified && !paper.provenance.runtime_verified && !paper.provenance.profit_verified);
    const reviewed=JSON.parse(run('node',[validator,out],temp));
    check('R9 validator accepts R10 as unverified',reviewed.accepted && reviewed.origin==='LOCAL_FILE_UNVERIFIED' && !reviewed.profit_verified && !reviewed.runtime_verified && reviewed.freshness==='WITHIN_24H_NOT_LIVE');
    check('no secrets and under 1MB',fs.statSync(out).size<1048576 && !('api_key' in paper) && !('secret' in paper));
    const again=spawnSync('python3',[exporter,'--out',out],{encoding:'utf8',timeout:10000});
    check('JSON file cannot be overwritten',again.status!==0 && String(again.stderr).includes('Output exists'));
    const original=fs.readFileSync(pageFile);
    server=http.createServer((req,res)=>{
      if(req.url==='/'||req.url==='/index.html') {
        res.writeHead(200,{'content-type':'text/html; charset=utf-8','cache-control':'no-store'});res.end(original);
      }else{res.writeHead(404);res.end('Not Found');}
    });
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    browser=await chromium.launch({headless:true,args:['--no-sandbox']});
    for(const [name,viewport] of [['mobile',{width:390,height:844}],['tablet',{width:900,height:600}]]) {
      const context=await browser.newContext({viewport,deviceScaleFactor:1});
      const page=await context.newPage();
      const errors=[];let unexpected=0, reportCalls=0, tradeCalls=0;
      page.on('pageerror',e=>errors.push(String(e)));
      await page.route('**/*',async route=>{
        const url=route.request().url();
        if(url.startsWith('https://data-api.binance.vision/'))return route.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify([{symbol:'BTCUSDT',price:'80000'},{symbol:'ETHUSDT',price:'3000'},{symbol:'SOLUSDT',price:'200'}])});
        if(url.includes('/api/report')){reportCalls++;return route.abort();}
        if(/\/(order|withdraw|transfer)(\/|\?|$)/i.test(url)){tradeCalls++;return route.abort();}
        if(url.startsWith('http://127.0.0.1:'))return route.continue();
        unexpected++;return route.abort();
      });
      await page.goto('http://127.0.0.1:'+server.address().port+'/',{waitUntil:'domcontentloaded'});
      check(name+' initial PnL unknown',(await page.locator('#netPnl').textContent()).includes('—'));
      check(name+' initially no imported report',(await page.locator('#r8Origin').textContent()).includes('尚未匯入'));
      await page.locator('[data-nav="reports"]').click();
      await page.locator('#importFile').setInputFiles({name:'r11-fixture.json',mimeType:'application/json',buffer:fs.readFileSync(out)});
      await page.waitForFunction(()=>document.querySelector('#importStatus')?.textContent?.includes('已在手機本機讀取'),null,{timeout:8000});
      check(name+' actual R10 JSON imported',(await page.locator('#importStatus').textContent()).includes('已在手機本機讀取'));
      check(name+' origin unverified',(await page.locator('#r8ReportOrigin').textContent()).includes('未驗來源'));
      check(name+' recent report not live',(await page.locator('#r8ReportFreshness').textContent()).includes('仍非在線證據'));
      check(name+' both Freqtrade sources visible',(await page.locator('#sourceSpot').textContent()).includes('Dry-run')&&(await page.locator('#sourceFutures').textContent()).includes('Dry-run'));
      await page.locator('[data-nav="home"]').click();
      check(name+' synthetic net PnL adds to 7.75',(await page.locator('#netPnl').textContent()).includes('7.75'));
      check(name+' VPS heartbeat still not verified',(await page.locator('#r8Runtime').textContent()).includes('尚未核實'));
      await page.locator('[data-nav="trade"]').click();
      await page.locator('[data-trade="spot"]').click();
      check(name+' spot detail correct',(await page.locator('#tradePnl').textContent()).includes('11.25')&&(await page.locator('#tradeClosed').textContent()).includes('2'));
      check(name+' spot label unverified',(await page.locator('#tradeState').textContent()).includes('未驗來源'));
      await page.locator('[data-trade="futures"]').click();
      check(name+' futures detail correct',(await page.locator('#tradePnl').textContent()).includes('-3.50')&&(await page.locator('#tradeOpen').textContent()).includes('0'));
      check(name+' trading disabled',await page.getByRole('button',{name:/啟動自動交易/}).isDisabled()&&await page.getByRole('button',{name:/停止引擎/}).isDisabled());
      await page.locator('[data-nav="whale"]').click();
      check(name+' B profit stays unknown',(await page.locator('#whalePnl').textContent()).includes('—'));
      await page.locator('[data-nav="reports"]').click();
      await page.locator('#resetReport').click();
      check(name+' reset clears import',(await page.locator('#r8ReportOrigin').textContent()).includes('尚未匯入')&&(await page.locator('#globalStatus').textContent()).includes('未連線'));
      check(name+' no private endpoints or unexpected network',reportCalls===0 && tradeCalls===0 && unexpected===0);
      check(name+' no browser JS error',errors.length===0);
      await context.close();
    }
    console.log('JUBAO R11 E2E PASS',passed,'synthetic assertions; NO VPS, LIVE TRADES OR DEPLOY');
  } finally {
    if(browser)await browser.close();
    if(server)await new Promise(resolve=>server.close(resolve));
    fs.rmSync(temp,{recursive:true,force:true});
  }
}
main().catch(error=>{console.error('JUBAO R11 E2E FAIL:',error.stack||error);process.exitCode=1;});
