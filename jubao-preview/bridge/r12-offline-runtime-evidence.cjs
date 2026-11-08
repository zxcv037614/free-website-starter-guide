'use strict';
// JUBAO R12: offline inspection *claim* reviewer. Does not connect to VPS.
// All user-supplied runtime/uptime/heartbeat values remain UNATTESTED.
const fs = require('node:fs');
const MAX_BYTES = 256 * 1024;
const IDS = ['spot', 'futures', 'solana'];
const SOURCES = ['SYNTHETIC_FIXTURE_ONLY', 'OPERATOR_REDACTED_UNATTESTED'];
const STATES = ['running', 'stopped', 'unknown'];
function reject(message) { throw new Error(message); }
function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function exactFields(value, keys, context) {
  if (!isObject(value)) reject(context + ' must be a plain object');
  if (Object.keys(value).length !== keys.length ||
      Object.keys(value).some(key => !keys.includes(key))) {
    reject(context + ' has missing or forbidden fields; raw configs/secrets are never allowed');
  }
}
function utcMilliseconds(value, label, allowNull = false) {
  if (allowNull && value === null) return null;
  if (typeof value !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value)) {
    reject(label + ' must be a seconds-precision UTC timestamp or null');
  }
  const ms = Date.parse(value);
  if (!Number.isFinite(ms) || new Date(ms).toISOString().replace('.000Z', 'Z') !== value) {
    reject(label + ' is not a valid UTC timestamp');
  }
  return ms;
}
function validateInspection(input, nowMs = Date.now()) {
  if (!Number.isFinite(nowMs)) reject('Invalid review clock');
  exactFields(input, ['schema_version', 'captured_at_utc', 'source', 'engines'], 'root');
  if (input.schema_version !== 'jubao-r12-observation-v1' ||
      !SOURCES.includes(input.source) || !Array.isArray(input.engines) ||
      input.engines.length !== 3) {
    reject('Expected three sanitized engines in jubao-r12-observation-v1');
  }
  const capturedMs = utcMilliseconds(input.captured_at_utc, 'captured_at_utc');
  if (capturedMs > nowMs + 300000) reject('Future-dated inspection rejected');
  const seen = new Set();
  const review = [];
  let liveRisk = false;
  for (const item of input.engines) {
    exactFields(item, ['id', 'container_state', 'dry_run', 'heartbeat_at_utc',
      'uptime_seconds', 'ledger_snapshot_at_utc'], 'engine');
    if (!IDS.includes(item.id) || seen.has(item.id)) reject('Invalid or duplicate engine id');
    seen.add(item.id);
    if (!STATES.includes(item.container_state) ||
        ![true, false, null].includes(item.dry_run)) reject('Invalid runtime or dry-run claim');
    if (item.uptime_seconds !== null &&
        !(Number.isSafeInteger(item.uptime_seconds) && item.uptime_seconds >= 0)) {
      reject('Invalid claimed uptime');
    }
    if (item.container_state !== 'running' && item.uptime_seconds !== null) {
      reject('Only running containers may state a current uptime');
    }
    const heartbeatMs = utcMilliseconds(item.heartbeat_at_utc, 'heartbeat_at_utc', true);
    const ledgerMs = utcMilliseconds(item.ledger_snapshot_at_utc, 'ledger_snapshot_at_utc', true);
    if ((heartbeatMs !== null && heartbeatMs > capturedMs + 300000) ||
        (ledgerMs !== null && ledgerMs > capturedMs + 300000)) {
      reject('Heartbeat or ledger timestamp newer than inspection capture');
    }
    if (item.id === 'solana' &&
        (item.dry_run !== null || item.ledger_snapshot_at_utc !== null)) {
      reject('B is a monitor: cannot claim Freqtrade dry-run or verified trade ledger');
    }
    const flags = [];
    if (item.container_state !== 'running') flags.push('RUNNING_NOT_CLAIMED');
    if (item.id !== 'solana' && item.dry_run !== true) {
      if (item.dry_run === false) {
        liveRisk = true;
        flags.push('POSSIBLE_LIVE_TRADING_STOP');
      } else {
        flags.push('DRY_RUN_NOT_ESTABLISHED');
      }
    }
    if (heartbeatMs === null) flags.push('NO_HEARTBEAT_TIMESTAMP');
    else if (nowMs - heartbeatMs > 24 * 3600000) flags.push('STALE_HEARTBEAT_OVER_24H');
    if (item.uptime_seconds !== null && item.uptime_seconds >= 86400) {
      flags.push('UPTIME_24H_IS_UNATTESTED_CLAIM');
    }
    if (ledgerMs !== null) flags.push('LEDGER_TIMESTAMP_IS_NOT_LEDGER_AUTHENTICATION');
    review.push({
      id: item.id,
      observed_state_claim: item.container_state,
      dry_run_claim: item.dry_run,
      reported_uptime_seconds: item.uptime_seconds,
      reported_heartbeat_at_utc: item.heartbeat_at_utc,
      flags,
      runtime_verified: false,
      dry_run_verified: false,
      continuous_24h_verified: false,
      ledger_verified: false,
      profit_verified: false,
      swaps_verified: false
    });
  }
  return {
    accepted_sanitized_shape: true,
    origin: 'OFFLINE_INPUT_UNATTESTED',
    source: input.source,
    review_status: liveRisk ? 'HOLD_POSSIBLE_LIVE_TRADING' : 'NEEDS_OWNER_VPS_EVIDENCE',
    captured_at_utc: input.captured_at_utc,
    remote_identity_verified: false,
    continuous_24h_verified: false,
    authentic_paper_ledger_verified: false,
    real_profit_verified: false,
    warning: 'A local observation cannot prove VPS identity, bot operation, 24h continuity, dry-run settings, ledger authenticity or profit.',
    engines: review
  };
}
function readAndReview(filePath, nowMs = Date.now()) {
  const stat = fs.statSync(filePath);
  if (!stat.isFile() || stat.size === 0 || stat.size > MAX_BYTES) {
    reject('Expected a nonempty local JSON file not exceeding 256KB');
  }
  return validateInspection(JSON.parse(fs.readFileSync(filePath, 'utf8')), nowMs);
}
if (require.main === module) {
  try {
    if (process.argv.length !== 3) reject('Usage: node r12-offline-runtime-evidence.cjs <sanitized-local.json>');
    process.stdout.write(JSON.stringify(readAndReview(process.argv[2]), null, 2) + '\n');
  } catch (_) {
    // Never echo untrusted file contents, paths, or exception messages to logs.
    process.stderr.write('JUBAO R12 REJECTED: unsafe, malformed or unsupported offline observation\n');
    process.exitCode = 1;
  }
}
module.exports = {validateInspection, readAndReview, MAX_BYTES};
