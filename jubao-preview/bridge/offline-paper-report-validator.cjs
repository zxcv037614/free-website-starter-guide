'use strict';
// Jubao R9: offline, paper-only JSON gate. NO network, orders, credentials or runtime probing.
const fs = require('node:fs');
const MAX_BYTES = 1024 * 1024;
const IDS = ['spot', 'futures', 'solana'];
const SOURCES = Object.freeze({
  spot: ['NOT_CONNECTED', 'SYNTHETIC_FIXTURE_ONLY', 'DRY_RUN_SQLITE_READ_ONLY'],
  futures: ['NOT_CONNECTED', 'SYNTHETIC_FIXTURE_ONLY', 'DRY_RUN_SQLITE_READ_ONLY'],
  solana: ['NOT_CONNECTED', 'SYNTHETIC_FIXTURE_ONLY', 'SOLANA_MONITOR_SNAPSHOT', 'SOLANA_MONITOR_SQLITE_READ_ONLY']
});
const SECRET_KEY = /(api[_-]?key|private[_-]?key|secret|password|credential|access[_-]?token|refresh[_-]?token|mnemonic|seed[_-]?phrase)/i;
function fail(reason) { throw new Error(reason); }
function object(x) { return x !== null && typeof x === 'object' && !Array.isArray(x); }
function protectSecrets(root) {
  const nodes = [root];
  let examined = 0;
  while (nodes.length) {
    if (++examined > 10000) fail('Payload is too complex');
    const node = nodes.pop();
    if (!node || typeof node !== 'object') continue;
    for (const [key, value] of Object.entries(node)) {
      if (SECRET_KEY.test(key)) fail('Sensitive credential field is forbidden');
      if (value && typeof value === 'object') nodes.push(value);
    }
  }
}
function validateReport(report, nowMs = Date.now()) {
  if (!object(report)) fail('Report must be a JSON object');
  protectSecrets(report);
  if (report.schema_version !== 'jubao-report-v1' ||
      report.live_trading !== false || report.paper_only !== true ||
      !Array.isArray(report.engines) || report.engines.length !== 3) {
    fail('Expected a paper-only jubao-report-v1 with exactly three engines');
  }
  if (typeof report.generated_at_utc !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(report.generated_at_utc)) {
    fail('generated_at_utc must be an ISO 8601 UTC timestamp');
  }
  const generatedMs = Date.parse(report.generated_at_utc);
  if (!Number.isFinite(generatedMs) || new Date(generatedMs).toISOString().slice(0, 19) !== report.generated_at_utc.slice(0, 19)) {
    fail('Invalid report timestamp');
  }
  if (!Number.isFinite(nowMs) || generatedMs > nowMs + 5 * 60 * 1000) {
    fail('Future-dated report rejected');
  }
  const seen = new Set();
  const engines = [];
  for (const engine of report.engines) {
    if (!object(engine) || !IDS.includes(engine.id) || seen.has(engine.id)) fail('Invalid or duplicate engine id');
    seen.add(engine.id);
    if (typeof engine.source !== 'string' || !SOURCES[engine.id].includes(engine.source) ||
        typeof engine.connected !== 'boolean') fail('Invalid source or connected flag');
    const readOnlySource = ['DRY_RUN_SQLITE_READ_ONLY', 'SOLANA_MONITOR_SQLITE_READ_ONLY'].includes(engine.source);
    if (engine.connected && !readOnlySource) fail('Only a read-only SQLite source may claim an imported connection');
    if (engine.source === 'NOT_CONNECTED' && engine.connected) fail('Disconnected source may not claim a connection');
    for (const key of ['open_trades', 'closed_trades']) {
      const n = engine[key];
      if (n !== null && !(Number.isSafeInteger(n) && n >= 0)) fail('Invalid trade count');
    }
    const p = engine.realized_pnl_usdt;
    if (p !== null && !((typeof p === 'number' || typeof p === 'string') &&
        String(p).trim() !== '' && Number.isFinite(Number(p)))) fail('Invalid PnL field');
    if (['NOT_CONNECTED', 'SYNTHETIC_FIXTURE_ONLY', 'SOLANA_MONITOR_SNAPSHOT'].includes(engine.source) &&
        (engine.open_trades !== null || engine.closed_trades !== null || p !== null)) {
      fail('Disconnected, synthetic or historical source cannot carry trading metrics');
    }
    if (typeof engine.notice !== 'undefined' && (typeof engine.notice !== 'string' || engine.notice.length > 500)) {
      fail('Invalid notice');
    }
    engines.push({id: engine.id, source: engine.source, imported_connection_claim: engine.connected,
      closed_trades: engine.closed_trades, open_trades: engine.open_trades,
      realized_pnl_usdt: p});
  }
  const ageHours = Math.max(0, (nowMs - generatedMs) / 3600000);
  return {
    accepted: true,
    schema_version: 'jubao-report-v1',
    origin: 'LOCAL_FILE_UNVERIFIED',
    runtime_verified: false,
    profit_verified: false,
    generated_at_utc: report.generated_at_utc,
    age_hours: Math.round(ageHours * 100) / 100,
    freshness: ageHours > 24 ? 'HISTORICAL_OVER_24H' : 'WITHIN_24H_NOT_LIVE',
    warning: 'Offline import does NOT establish VPS heartbeat, 24h runtime, authentic ledger, or profit.',
    engines
  };
}
function readAndValidate(path, nowMs = Date.now()) {
  const stat = fs.statSync(path);
  if (!stat.isFile() || stat.size > MAX_BYTES) fail('File must be JSON and at most 1MB');
  const report = JSON.parse(fs.readFileSync(path, 'utf8'));
  return validateReport(report, nowMs);
}
if (require.main === module) {
  try {
    if (process.argv.length !== 3) fail('Usage: node offline-paper-report-validator.cjs <local-report.json>');
    const result = readAndValidate(process.argv[2]);
    // Only a fixed-field review summary is printed; never echo arbitrary input fields.
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  } catch (error) {
    process.stderr.write('JUBAO R9 REJECTED: ' + String(error.message) + '\n');
    process.exitCode = 1;
  }
}
module.exports = {validateReport, readAndValidate, MAX_BYTES};
