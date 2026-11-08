'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {validateReport} = require('../bridge/offline-paper-report-validator.cjs');
const NOW = Date.parse('2026-11-08T12:00:00Z');
function sample() {
  return {
    schema_version: 'jubao-report-v1',
    generated_at_utc: '2026-11-08T11:00:00Z',
    brand: 'Synthetic test data ONLY',
    live_trading: false, paper_only: true,
    engines: [
      {id: 'spot', source: 'DRY_RUN_SQLITE_READ_ONLY', connected: true,
        closed_trades: 2, open_trades: 1, realized_pnl_usdt: '12.34', notice: 'Synthetic'},
      {id: 'futures', source: 'NOT_CONNECTED', connected: false,
        closed_trades: null, open_trades: null, realized_pnl_usdt: null},
      {id: 'solana', source: 'SOLANA_MONITOR_SNAPSHOT', connected: false,
        closed_trades: null, open_trades: null, realized_pnl_usdt: null}
    ]
  };
}
function invalid(mutator, expected) {
  const x = sample();
  mutator(x);
  assert.throws(() => validateReport(x, NOW), expected);
}
test('valid paper report remains unverified; no VPS/earnings claims', () => {
  const result = validateReport(sample(), NOW);
  assert.equal(result.accepted, true);
  assert.equal(result.origin, 'LOCAL_FILE_UNVERIFIED');
  assert.equal(result.runtime_verified, false);
  assert.equal(result.profit_verified, false);
  assert.equal(result.freshness, 'WITHIN_24H_NOT_LIVE');
  assert.equal(result.engines.find(x => x.id === 'spot').imported_connection_claim, true);
});
test('48h older report is historical, never live', () => {
  const x = sample(); x.generated_at_utc = '2026-11-06T11:00:00Z';
  assert.equal(validateReport(x, NOW).freshness, 'HISTORICAL_OVER_24H');
});
test('reject actual trading flag', () => invalid(x => {x.live_trading = true;}, /paper-only/));
test('reject missing engine', () => invalid(x => {x.engines.pop();}, /three engines/));
test('reject duplicate engine', () => invalid(x => {x.engines[2].id = 'spot';}, /duplicate/));
test('reject cross-engine SQLite source', () => invalid(x => {x.engines[1].source = 'SOLANA_MONITOR_SQLITE_READ_ONLY';}, /Invalid source/));
test('reject prototype-looking source', () => invalid(x => {x.engines[0].source = 'toString';}, /Invalid source/));
test('reject disconnected fake profit', () => invalid(x => {x.engines[1].realized_pnl_usdt = '9999';}, /cannot carry/));
test('reject synthetic data masquerading as connected', () => invalid(x => {
  x.engines[0].source = 'SYNTHETIC_FIXTURE_ONLY'; x.engines[0].connected = true;
}, /read-only SQLite/));
test('reject future report', () => invalid(x => {x.generated_at_utc = '2026-11-08T13:00:00Z';}, /Future/));
test('reject malformed timestamp', () => invalid(x => {x.generated_at_utc = 'yesterday';}, /timestamp/));
test('reject impossible UTC date', () => invalid(x => {x.generated_at_utc = '2026-02-30T11:00:00Z';}, /Invalid report timestamp/));
test('reject dangerous secret field even when nested', () => invalid(x => {
  x.engines[1].api_key = 'DO-NOT-ECHO';
}, /Sensitive credential/));
test('reject B historical snapshot trade metrics', () => invalid(x => {
  x.engines[2].closed_trades = 40;
}, /cannot carry/));
test('reject negative counts', () => invalid(x => {x.engines[0].closed_trades = -1;}, /Invalid trade count/));
test('reject non-finite realized pnl', () => invalid(x => {
  x.engines[0].realized_pnl_usdt = 'Infinity';
}, /Invalid PnL/));
