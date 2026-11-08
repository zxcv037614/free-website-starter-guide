'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {validateInspection, readAndReview, MAX_BYTES} = require('../bridge/r12-offline-runtime-evidence.cjs');
const NOW = Date.parse('2026-11-08T10:15:00Z');
function fixture() {
  return {
    schema_version:'jubao-r12-observation-v1',
    captured_at_utc:'2026-11-08T10:00:00Z',
    source:'SYNTHETIC_FIXTURE_ONLY',
    engines:[
      {id:'spot', container_state:'running', dry_run:true,
       heartbeat_at_utc:'2026-11-08T09:58:00Z', uptime_seconds:88000,
       ledger_snapshot_at_utc:'2026-11-08T09:55:00Z'},
      {id:'futures', container_state:'running', dry_run:true,
       heartbeat_at_utc:'2026-11-08T09:58:00Z', uptime_seconds:400,
       ledger_snapshot_at_utc:null},
      {id:'solana', container_state:'unknown', dry_run:null,
       heartbeat_at_utc:null, uptime_seconds:null, ledger_snapshot_at_utc:null}
    ]
  };
}
test('accepts synthetic sanitized 3-engine observation', () => {
  const r=validateInspection(fixture(), NOW);
  assert.equal(r.engines.length,3);
  assert.equal(r.review_status,'NEEDS_OWNER_VPS_EVIDENCE');
  assert.equal(r.origin,'OFFLINE_INPUT_UNATTESTED');
});
test('24h claimed uptime never becomes 24h verified', () => {
  const r=validateInspection(fixture(), NOW);
  assert.equal(r.continuous_24h_verified,false);
  assert.equal(r.engines[0].continuous_24h_verified,false);
  assert.ok(r.engines[0].flags.includes('UPTIME_24H_IS_UNATTESTED_CLAIM'));
});
test('ledger timestamp does not authenticate ledger or profits', () => {
  const r=validateInspection(fixture(), NOW);
  assert.equal(r.authentic_paper_ledger_verified,false);
  assert.equal(r.engines[0].profit_verified,false);
  assert.ok(r.engines[0].flags.includes('LEDGER_TIMESTAMP_IS_NOT_LEDGER_AUTHENTICATION'));
});
test('no remote identities verified even with operator-labeled input', () => {
  const v=fixture();v.source='OPERATOR_REDACTED_UNATTESTED';
  const r=validateInspection(v,NOW);
  assert.equal(r.remote_identity_verified,false);
  assert.equal(r.engines[0].runtime_verified,false);
  assert.equal(r.engines[0].dry_run_verified,false);
});
test('live-trading false claim is flagged for hold', () => {
  const v=fixture();v.engines[1].dry_run=false;
  const r=validateInspection(v,NOW);
  assert.equal(r.review_status,'HOLD_POSSIBLE_LIVE_TRADING');
  assert.ok(r.engines[1].flags.includes('POSSIBLE_LIVE_TRADING_STOP'));
});
test('unknown dry_run is not treated as true', () => {
  const v=fixture();v.engines[0].dry_run=null;
  assert.ok(validateInspection(v,NOW).engines[0].flags.includes('DRY_RUN_NOT_ESTABLISHED'));
});
test('B monitor cannot claim Freqtrade dry run', () => {
  const v=fixture();v.engines[2].dry_run=true;
  assert.throws(()=>validateInspection(v,NOW),/B is a monitor/);
});
test('B monitor cannot claim authenticated trading ledger', () => {
  const v=fixture();v.engines[2].ledger_snapshot_at_utc='2026-11-08T09:00:00Z';
  assert.throws(()=>validateInspection(v,NOW),/B is a monitor/);
});
test('rejects extra secret-shaped fields', () => {
  const v=fixture();v.engines[0].api_key='DUMMY_ONLY';
  assert.throws(()=>validateInspection(v,NOW),/forbidden fields/);
});
test('rejects extra raw config at the root', () => {
  const v=fixture();v.config={dry_run:true};
  assert.throws(()=>validateInspection(v,NOW),/forbidden fields/);
});
test('rejects wrong schema and source', () => {
  const v=fixture();v.schema_version='jubao-report-v1';
  assert.throws(()=>validateInspection(v,NOW),/Expected three/);
  const w=fixture();w.source='TRUSTED_VPS';
  assert.throws(()=>validateInspection(w,NOW),/Expected three/);
});
test('rejects missing engine', () => {
  const v=fixture();v.engines.pop();
  assert.throws(()=>validateInspection(v,NOW),/Expected three/);
});
test('rejects duplicate engine', () => {
  const v=fixture();v.engines[1].id='spot';
  assert.throws(()=>validateInspection(v,NOW),/duplicate/);
});
test('rejects unexpected fourth engine', () => {
  const v=fixture();v.engines.push({...v.engines[0],id:'other'});
  assert.throws(()=>validateInspection(v,NOW),/Expected three/);
});
test('rejects future capture', () => {
  const v=fixture();v.captured_at_utc='2026-11-08T10:30:01Z';
  assert.throws(()=>validateInspection(v,NOW),/Future-dated/);
});
test('rejects impossible calendar date', () => {
  const v=fixture();v.captured_at_utc='2026-02-30T10:00:00Z';
  assert.throws(()=>validateInspection(v,NOW),/not a valid/);
});
test('rejects future heartbeat relative to capture', () => {
  const v=fixture();v.engines[0].heartbeat_at_utc='2026-11-08T10:06:00Z';
  assert.throws(()=>validateInspection(v,NOW),/newer than inspection/);
});
test('rejects future ledger snapshot relative to capture', () => {
  const v=fixture();v.engines[0].ledger_snapshot_at_utc='2026-11-08T10:06:00Z';
  assert.throws(()=>validateInspection(v,NOW),/newer than inspection/);
});
test('rejects negative or fractional uptime', () => {
  const v=fixture();v.engines[0].uptime_seconds=-1;
  assert.throws(()=>validateInspection(v,NOW),/Invalid claimed uptime/);
  const w=fixture();w.engines[0].uptime_seconds=0.5;
  assert.throws(()=>validateInspection(w,NOW),/Invalid claimed uptime/);
});
test('rejects uptime for stopped container', () => {
  const v=fixture();v.engines[0].container_state='stopped';
  assert.throws(()=>validateInspection(v,NOW),/Only running/);
});
test('marks stale 24h heartbeat without claiming continuity', () => {
  const v=fixture();v.engines[0].heartbeat_at_utc='2026-11-06T09:00:00Z';
  const r=validateInspection(v,NOW);
  assert.ok(r.engines[0].flags.includes('STALE_HEARTBEAT_OVER_24H'));
  assert.equal(r.continuous_24h_verified,false);
});
test('rejects invalid running state and timestamps', () => {
  const v=fixture();v.engines[0].container_state='passing';
  assert.throws(()=>validateInspection(v,NOW),/Invalid runtime/);
  const w=fixture();w.engines[1].heartbeat_at_utc='today';
  assert.throws(()=>validateInspection(w,NOW),/UTC timestamp/);
});
test('requires nonempty <=256KB local JSON only', () => {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jubao-r12-'));
  try {
    const file=path.join(dir,'fixture.json');
    fs.writeFileSync(file,JSON.stringify(fixture()));
    assert.equal(readAndReview(file,NOW).origin,'OFFLINE_INPUT_UNATTESTED');
    fs.writeFileSync(file,'x'.repeat(MAX_BYTES+1));
    assert.throws(()=>readAndReview(file,NOW),/256KB/);
    fs.writeFileSync(file,'');
    assert.throws(()=>readAndReview(file,NOW),/nonempty/);
  } finally { fs.rmSync(dir,{recursive:true,force:true}); }
});
