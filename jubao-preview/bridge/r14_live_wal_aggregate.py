#!/usr/bin/env python3
"""JUBAO R14: local read-only aggregate from existing Freqtrade SQLite/WAL.

Sandbox ONLY. No SSH, HTTP, exchange API, trade actions, config reads or
database writes. JSON stdout contains aggregates, never raw rows or secrets.
Runtime dry-run, currency, origin and profit authenticity remain UNVERIFIED.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3
import sys

ALLOWED_NAMES = frozenset({'tradesv3.dryrun.sqlite', 'tradesv3.dry_run.sqlite'})
MAX_TRADES = 500_000
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_REPORT_BYTES = 1024 * 1024

class Rejected(ValueError):
    pass

def _timestamp(sec):
    return datetime.fromtimestamp(sec, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def _check_path(raw):
    p = Path(raw).expanduser()
    if p.name not in ALLOWED_NAMES or p.is_symlink() or not p.is_file():
        raise Rejected('Unsupported or missing local paper database file')
    if not (16 <= p.stat().st_size <= MAX_FILE_BYTES):
        raise Rejected('SQLite file size outside review limit')
    with p.open('rb') as f:
        if f.read(16) != b'SQLite format 3\x00':
            raise Rejected('Invalid SQLite file header')
    p = p.resolve(strict=True)
    wal, shm = Path(str(p) + '-wal'), Path(str(p) + '-shm')
    # Do not manufacture missing WAL/SHM on an active bot.
    if wal.exists() != shm.exists():
        raise Rejected('Incomplete WAL/SHM sidecars')
    if any(f.is_symlink() or not f.is_file() for f in (wal, shm) if f.exists()):
        raise Rejected('Invalid WAL/SHM sidecar type')
    updated = max([p.stat().st_mtime] + [f.stat().st_mtime for f in (wal, shm) if f.exists()])
    if updated > datetime.now(timezone.utc).timestamp() + 300:
        raise Rejected('Future-dated source file')
    return p, updated

def _select_only(op, arg1, arg2, db_name, trigger):
    return sqlite3.SQLITE_OK if op in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION) else sqlite3.SQLITE_DENY

def summarize(path):
    p, updated = _check_path(path)
    opened = closed = 0
    pnl = Decimal('0')
    incomplete = False
    # mode=ro reads existing WAL under SQLite locking. Never use immutable=1.
    uri = p.as_uri() + '?mode=ro&cache=private'
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=0.35)) as conn:
            conn.execute('PRAGMA query_only=ON')
            conn.execute('PRAGMA trusted_schema=OFF')
            conn.execute('PRAGMA temp_store=MEMORY')
            conn.execute('PRAGMA busy_timeout=350')
            columns = {r[1] for r in conn.execute('PRAGMA table_info(trades)')}
            if not {'is_open', 'close_profit_abs'} <= columns:
                raise Rejected('Incompatible trades schema')
            conn.set_authorizer(_select_only)
            with closing(conn.execute('SELECT is_open, close_profit_abs FROM trades')) as rows:
                for is_open, absolute in rows:
                    if opened + closed >= MAX_TRADES:
                        raise Rejected('Trade row cap reached')
                    if type(is_open) is not int or is_open not in (0, 1):
                        raise Rejected('Invalid is_open value')
                    if is_open == 1:
                        opened += 1
                    else:
                        closed += 1
                        if absolute is None:
                            incomplete = True
                        else:
                            try:
                                val = Decimal(str(absolute))
                            except (InvalidOperation, ValueError):
                                raise Rejected('Non-numeric closed PnL') from None
                            if not val.is_finite():
                                raise Rejected('Nonfinite closed PnL')
                            pnl += val
    except sqlite3.DatabaseError:
        raise Rejected('Read-only schema or WAL query failed') from None
    return {'open_trades': opened, 'closed_trades': closed,
            'realized_pnl_usdt': None if incomplete else format(pnl, 'f'),
            'source_mtime_utc': _timestamp(updated)}

def generate(spot_db=None, futures_db=None, *, paper_attested=False):
    if not (spot_db or futures_db):
        raise Rejected('At least one existing local paper database is required')
    if spot_db and futures_db and Path(spot_db).resolve() == Path(futures_db).resolve():
        raise Rejected('One database cannot masquerade as two engines')
    engines, source_times = [], []
    for kind, path in (('spot', spot_db), ('futures', futures_db)):
        if not path:
            engines.append({'id': kind, 'source': 'NOT_CONNECTED', 'connected': False,
                            'open_trades': None, 'closed_trades': None, 'realized_pnl_usdt': None,
                            'notice': 'Not supplied; runtime and trades unknown'})
            continue
        m = summarize(path)
        source_times.append(datetime.fromisoformat(m.pop('source_mtime_utc').replace('Z', '+00:00')).timestamp())
        engines.append({'id': kind, 'source': 'DRY_RUN_SQLITE_READ_ONLY', 'connected': True,
                        'open_trades': m['open_trades'], 'closed_trades': m['closed_trades'],
                        'realized_pnl_usdt': m['realized_pnl_usdt'],
                        'notice': 'LOCAL WAL read-only aggregate ONLY; origin, virtual stake currency, active dry-run setting and profit NOT independently verified'})
    engines.append({'id': 'solana', 'source': 'SOLANA_MONITOR_SNAPSHOT', 'connected': False,
                    'open_trades': None, 'closed_trades': None, 'realized_pnl_usdt': None,
                    'notice': 'B monitor-only; do not claim verified swaps or profit'})
    return {'schema_version': 'jubao-report-v1',
            'generated_at_utc': _timestamp(min(source_times)),
            'brand': 'JUBAO local read-only WAL; UNVERIFIED origin & paper results',
            'live_trading': False, 'paper_only': True,
            'provenance': {'mode': 'LOCAL_ACTIVE_WAL_RO',
                           'dry_run_operator_attested': bool(paper_attested),
                           'heartbeat_verified': False, 'runtime_verified': False,
                           'profit_verified': False, 'source_identity_verified': False},
            'engines': engines}

def main(argv=None):
    parser = argparse.ArgumentParser(description='Local read-only Freqtrade WAL aggregate, no raw trade rows')
    parser.add_argument('--spot-db')
    parser.add_argument('--futures-db')
    parser.add_argument('--paper-attested', action='store_true', help='Operator attests to dry-run config (not proof)')
    args = parser.parse_args(argv)
    try:
        report = generate(args.spot_db, args.futures_db, paper_attested=args.paper_attested)
        payload = json.dumps(report, ensure_ascii=False, separators=(',', ':'))
        if len(payload.encode('utf-8')) > MAX_REPORT_BYTES:
            raise Rejected('Report exceeds 1MB')
        print(payload)
        return 0
    except (Rejected, OSError, OverflowError):
        print('JUBAO_R14_REJECTED: read-only review unavailable or incompatible', file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
