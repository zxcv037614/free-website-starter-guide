"""R10 synthetic fixtures only: no VPS, network, private credentials, or live bot."""
import importlib.util
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timezone

SRC = Path(__file__).resolve().parents[1] / 'bridge' / 'export-offline-paper-report.py'
spec = importlib.util.spec_from_file_location('jubao_offline_export', SRC)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class OfflineExporterTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)
        self.db = self.root / 'paper.sqlite'
        self.cfg = self.root / 'dryrun.json'
        self.mkdb([(0, 2.50), (0, -0.75), (1, None)])
        self.mkcfg()
        self.now = 1794140000.0
        os.utime(self.db, (self.now - 3600, self.now - 3600))

    def mkdb(self, rows):
        if self.db.exists():
            self.db.unlink()
        with closing(sqlite3.connect(self.db)) as con:
            con.execute('CREATE TABLE trades (id INTEGER PRIMARY KEY, is_open INTEGER, close_profit_abs REAL)')
            con.executemany('INSERT INTO trades (is_open,close_profit_abs) VALUES (?,?)', rows)
            con.commit()

    def mkcfg(self, **updates):
        config = {'dry_run': True, 'trading_mode': 'spot', 'stake_currency': 'USDT',
                  'exchange': {'key': 'synthetic-demo-secret-must-not-be-output'}}
        config.update(updates)
        self.cfg.write_text(json.dumps(config), encoding='utf-8')

    def test_01_generates_spot_paper_report(self):
        d = app.generate_report(spot=(self.db,self.cfg),now=self.now)
        self.assertEqual(d['engines'][0]['realized_pnl_usdt'], '1.75')
        self.assertEqual(d['engines'][0]['open_trades'], 1)
        self.assertEqual(d['engines'][0]['closed_trades'], 2)
        self.assertFalse(d['provenance']['runtime_verified'])
        self.assertFalse(d['provenance']['profit_verified'])
        self.assertNotIn('synthetic-demo-secret',json.dumps(d))
        self.assertTrue(d['generated_at_utc'].endswith('Z'))

    def test_02_no_snapshot_does_not_fake_online_data(self):
        d = app.generate_report(now=self.now)
        self.assertEqual([x['connected'] for x in d['engines']], [False,False,False])
        self.assertIsNone(d['engines'][0]['realized_pnl_usdt'])

    def test_03_reject_live_trading_config(self):
        self.mkcfg(dry_run=False)
        with self.assertRaisesRegex(app.Reject,'dry_run=true'):
            app.generate_report(spot=(self.db,self.cfg),now=self.now)

    def test_04_reject_wrong_trading_mode(self):
        self.mkcfg(trading_mode='futures')
        with self.assertRaisesRegex(app.Reject,'trading_mode'):
            app.generate_report(spot=(self.db,self.cfg),now=self.now)

    def test_05_reject_non_usdt(self):
        self.mkcfg(stake_currency='BTC')
        with self.assertRaisesRegex(app.Reject,'USDT'):
            app.generate_report(spot=(self.db,self.cfg),now=self.now)

    def test_06_reject_active_wal_file(self):
        Path(str(self.db)+'-wal').write_bytes(b'test')
        with self.assertRaisesRegex(app.Reject,'WAL/SHM'):
            app.generate_report(spot=(self.db,self.cfg),now=self.now)

    def test_07_reject_bad_sqlite_header(self):
        self.db.write_text('not a database')
        with self.assertRaisesRegex(app.Reject,'header'):
            app.generate_report(spot=(self.db,self.cfg),now=self.now)

    def test_08_reject_invalid_trade_state(self):
        self.mkdb([(5,1.2)])
        with self.assertRaisesRegex(app.Reject,'is_open'):
            app.generate_report(spot=(self.db,self.cfg),now=self.now)

    def test_09_missing_profit_stays_unknown(self):
        self.mkdb([(0,None),(1,None)])
        d = app.generate_report(spot=(self.db,self.cfg),now=self.now)
        self.assertIsNone(d['engines'][0]['realized_pnl_usdt'])

    def test_10_reject_cross_engine_same_db(self):
        futures_cfg = self.root/'futures.json'
        futures_cfg.write_text(json.dumps({'dry_run':True,'trading_mode':'futures','stake_currency':'USDT'}))
        with self.assertRaisesRegex(app.Reject,'same SQLite'):
            app.generate_report(spot=(self.db,self.cfg),futures=(self.db,futures_cfg),now=self.now)

    def test_11_old_snapshot_uses_old_timestamp(self):
        os.utime(self.db,(self.now-72*3600,self.now-72*3600))
        d = app.generate_report(spot=(self.db,self.cfg),now=self.now)
        self.assertLess(datetime.fromisoformat(d['generated_at_utc'].replace('Z','+00:00')).timestamp(),self.now-24*3600)

    def test_12_b_historical_never_claims_trades(self):
        d=app.generate_report(spot=(self.db,self.cfg),now=self.now)
        b=d['engines'][2]
        self.assertEqual(b['source'],'SOLANA_MONITOR_SNAPSHOT')
        self.assertFalse(b['connected'])
        self.assertIsNone(b['realized_pnl_usdt'])
        self.assertIsNone(b['closed_trades'])

    def test_13_reject_future_file_time(self):
        os.utime(self.db,(self.now+3600,self.now+3600))
        with self.assertRaisesRegex(app.Reject,'future'):
            app.generate_report(spot=(self.db,self.cfg),now=self.now)

    def test_14_reject_invalid_config_json(self):
        self.cfg.write_text('{bad json')
        with self.assertRaisesRegex(app.Reject,'JSON'):
            app.generate_report(spot=(self.db,self.cfg),now=self.now)

    def test_15_reject_schema_without_pnl_field(self):
        with closing(sqlite3.connect(self.db)) as con:
            con.execute('ALTER TABLE trades RENAME TO legacy_trades')
            con.commit()
        with self.assertRaisesRegex(app.Reject,'schema'):
            app.generate_report(spot=(self.db,self.cfg),now=self.now)

    def test_16_r10_output_cli_is_never_overwritten(self):
        out=self.root/'report.json'
        os.utime(self.db,(time.time()-3600,time.time()-3600))
        args=['--spot-db',str(self.db),'--spot-config',str(self.cfg),'--out',str(out)]
        self.assertEqual(app.main(args),0)
        self.assertTrue(out.exists())
        self.assertEqual(app.main(args),1)
        self.assertFalse(json.loads(out.read_text())['live_trading'])

if __name__ == '__main__':
    unittest.main()
