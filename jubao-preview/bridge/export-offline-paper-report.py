#!/usr/bin/env python3
"""JUBAO R10 offline-only paper report export from COPIED Freqtrade SQLite DBs.

This program never connects to a VPS, exchange, or network. The database must be
an offline snapshot. A dry_run=true local config is necessary but NOT evidence
that a bot is currently running or that profits are authentic.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3
import sys

MAX_TRADES = 500_000
MAX_CONFIG_BYTES = 1024 * 1024

class Reject(ValueError):
    pass

def utc_iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def read_local_config(path, engine):
    p = Path(path).expanduser().resolve(strict=True)
    if not p.is_file() or p.stat().st_size > MAX_CONFIG_BYTES:
        raise Reject('Invalid local dry-run config file')
    try:
        with p.open(encoding='utf-8') as f:
            cfg = json.load(f)
    except (ValueError, UnicodeError):
        raise Reject('Invalid local dry-run config JSON') from None
    if not isinstance(cfg, dict) or cfg.get('dry_run') is not True:
        raise Reject('Config must explicitly set dry_run=true')
    if cfg.get('trading_mode') != engine:
        raise Reject('Config trading_mode does not match the requested engine')
    if cfg.get('stake_currency') != 'USDT':
        raise Reject('Only USDT stake currency is supported')
    # Never return or print the rest of the config; it may contain secrets.
    return True

def extract_trades(db_path):
    p = Path(db_path).expanduser().resolve(strict=True)
    if not p.is_file() or p.stat().st_size == 0:
        raise Reject('Offline snapshot is not a readable SQLite file')
    if Path(str(p) + '-wal').exists() or Path(str(p) + '-shm').exists():
        raise Reject('Active SQLite WAL/SHM detected: use a finished offline snapshot copy')
    with p.open('rb') as header_file:
        header = header_file.read(16)
    if header != b'SQLite format 3\x00':
        raise Reject('Invalid SQLite file header')
    closed = opened = 0
    total = Decimal('0')
    incomplete = False
    try:
        # immutable=1 prevents lock & WAL use, but also requires a finished copy.
        uri = p.as_uri() + '?mode=ro&immutable=1'
        with closing(sqlite3.connect(uri, uri=True, timeout=1.0)) as conn:
            conn.execute('PRAGMA query_only=ON')
            names = {row[1] for row in conn.execute('PRAGMA table_info(trades)')}
            if not {'is_open', 'close_profit_abs'}.issubset(names):
                raise Reject('Unknown Freqtrade trades schema: missing required columns')
            cursor = conn.execute('SELECT is_open, close_profit_abs FROM trades')
            for is_open, close_profit_abs in cursor:
                if closed + opened >= MAX_TRADES:
                    raise Reject('Offline snapshot exceeds row review cap')
                if type(is_open) is not int or is_open not in (0, 1):
                    raise Reject('Invalid is_open value in offline trades')
                if is_open:
                    opened += 1
                else:
                    closed += 1
                    if close_profit_abs is None:
                        incomplete = True
                    else:
                        try:
                            amount = Decimal(str(close_profit_abs))
                        except InvalidOperation:
                            raise Reject('Invalid realized PnL value') from None
                        if not amount.is_finite():
                            raise Reject('Nonfinite realized PnL in offline trades')
                        total += amount
    except sqlite3.DatabaseError:
        raise Reject('Unreadable or incompatible offline SQLite snapshot') from None
    return {
        'open_trades': opened,
        'closed_trades': closed,
        # Avoid fabricating zero profit if any closed trade is missing PnL.
        'realized_pnl_usdt': None if incomplete else format(total, 'f'),
        'snapshot_mtime': p.stat().st_mtime,
    }

def generate_report(spot=None, futures=None, now=None):
    """spot/futures are each (offline_db_path, dry_run_config_path) or None."""
    if now is None:
        now = datetime.now(timezone.utc).timestamp()
    engines, snapshot_times = [], []
    present = [x[0] for x in [spot, futures] if x is not None]
    if len(present) > 1 and Path(present[0]).resolve() == Path(present[1]).resolve():
        raise Reject('Cannot reuse the same SQLite snapshot for A1 and A2')
    for engine, pair in (('spot', spot), ('futures', futures)):
        if pair is None:
            engines.append({'id': engine, 'source': 'NOT_CONNECTED', 'connected': False,
                            'closed_trades': None, 'open_trades': None, 'realized_pnl_usdt': None,
                            'notice': 'No offline snapshot supplied; VPS status is unknown'})
            continue
        db_path, config_path = pair
        read_local_config(config_path, engine)
        metric = extract_trades(db_path)
        if metric['snapshot_mtime'] > now + 300:
            raise Reject('Snapshot file timestamp is in the future')
        snapshot_times.append(metric['snapshot_mtime'])
        engines.append({
            'id': engine, 'source': 'DRY_RUN_SQLITE_READ_ONLY', 'connected': True,
            'closed_trades': metric['closed_trades'], 'open_trades': metric['open_trades'],
            'realized_pnl_usdt': metric['realized_pnl_usdt'],
            'notice': 'Offline SQLite copy only; dry_run config checked; bot runtime and profit unverified',
        })
    engines.append({'id': 'solana', 'source': 'SOLANA_MONITOR_SNAPSHOT', 'connected': False,
                    'closed_trades': None, 'open_trades': None, 'realized_pnl_usdt': None,
                    'notice': 'B: historical monitor only; zero verified swaps, runtime unverified'})
    return {
        'schema_version': 'jubao-report-v1',
        # Conservatively use the oldest supplied file mtime, NEVER current export time
        # when reporting snapshots. File mtime is still not a bot heartbeat.
        'generated_at_utc': utc_iso(min(snapshot_times) if snapshot_times else now),
        'brand': 'JUBAO paper-only offline import; unverified',
        'live_trading': False, 'paper_only': True,
        'provenance': {'mode': 'OFFLINE_SNAPSHOT_ONLY', 'heartbeat_verified': False,
                       'runtime_verified': False, 'profit_verified': False},
        'engines': engines,
    }

def main(argv=None):
    p = argparse.ArgumentParser(description='Generate unverified JUBAO paper report from offline SQLite copies')
    for engine in ('spot', 'futures'):
        p.add_argument('--' + engine + '-db', help='Path to an OFFLINE SQLite copy')
        p.add_argument('--' + engine + '-config', help='Local dry_run=true Freqtrade config (never printed)')
    p.add_argument('--out', required=True, help='Path to local report JSON; never auto-uploaded')
    args = p.parse_args(argv)
    try:
        pairs = {}
        for engine in ('spot', 'futures'):
            db = getattr(args, engine + '_db')
            config = getattr(args, engine + '_config')
            if bool(db) != bool(config):
                raise Reject('Snapshot and dry-run config must both be supplied')
            pairs[engine] = (db, config) if db else None
        output = Path(args.out).expanduser().resolve()
        if any(pair and output in (Path(x).expanduser().resolve() for x in pair)
               for pair in pairs.values()):
            raise Reject('Output path must differ from input database and config')
        if output.exists():
            raise Reject('Output exists; use a new file name rather than overwrite')
        report = generate_report(**pairs)
        payload = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        # Fail closed: prevent accidentally exporting a >1MB report.
        if len(payload.encode('utf-8')) > 1024 * 1024:
            raise Reject('Report exceeds 1MB limit')
        with output.open('x', encoding='utf-8') as f:
            f.write(payload)
        print('Created local paper-only UNVERIFIED JSON report: ' + str(output))
    except (Reject, FileNotFoundError, PermissionError, IsADirectoryError) as e:
        print('JUBAO R10 REJECTED: ' + str(e), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
