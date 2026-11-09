"""JUBAO R14 synthetic WAL safety and paper report tests. No VPS, keys or network."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bridge'))
import r14_live_wal_aggregate as r14

class LiveWalAggregateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jubao-r14-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.conns = []
    def tearDown(self):
        for con in self.conns:
            con.close()
    def db(self, directory='spot', trades=(), name='tradesv3.dryrun.sqlite'):
        p = self.root / directory / name
        p.parent.mkdir(exist_ok=True)
        c = sqlite3.connect(p)
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA wal_autocheckpoint=0')
        c.execute('CREATE TABLE trades (id INTEGER PRIMARY KEY, is_open INTEGER, close_profit_abs REAL, pair TEXT, secret_note TEXT)')
        c.executemany('INSERT INTO trades (is_open, close_profit_abs, pair, secret_note) VALUES (?,?,?,?)',
                      [(status, profit, 'BTC/USDT', 'SENSITIVE_TEST_ONLY') for status, profit in trades])
        c.commit()
        self.conns.append(c)
        self.assertTrue(Path(str(p)+'-wal').exists())
        self.assertTrue(Path(str(p)+'-shm').exists())
        return p
    def fingerprint(self, p):
        return [(q.stat().st_size, q.stat().st_mtime_ns) for q in (p, Path(str(p)+'-wal'), Path(str(p)+'-shm'))]
    def test_aggregate_from_live_wal_without_file_changes(self):
        spot=self.db('spot', [(0,10.5),(0,.75),(1,None)])
        future=self.db('futures', [(0,-4.5),(0,1.0)])
        before=self.fingerprint(spot),self.fingerprint(future)
        report=r14.generate(spot,future)
        self.assertEqual(before,(self.fingerprint(spot),self.fingerprint(future)))
        self.assertEqual(report['engines'][0]['realized_pnl_usdt'],'11.25')
        self.assertEqual(report['engines'][1]['realized_pnl_usdt'],'-3.5')
        self.assertEqual(report['engines'][0]['closed_trades'],2)
        self.assertEqual(report['engines'][0]['open_trades'],1)
        self.assertFalse(report['provenance']['runtime_verified'])
        self.assertFalse(report['provenance']['profit_verified'])
    def test_empty_database_does_not_fabricate_wallet_equity(self):
        report=r14.generate(self.db(trades=[]))
        self.assertEqual(report['engines'][0]['closed_trades'],0)
        self.assertEqual(report['engines'][1]['source'],'NOT_CONNECTED')
        self.assertNotIn('equity',json.dumps(report).lower())
    def test_missing_closed_profit_becomes_null(self):
        self.assertIsNone(r14.generate(self.db(trades=[(0,None),(0,2.5)]))['engines'][0]['realized_pnl_usdt'])
    def test_reject_live_named_database(self):
        with self.assertRaises(r14.Rejected):r14.generate(self.db(name='tradesv3.sqlite'))
    def test_reject_same_database_both_engines(self):
        db=self.db()
        with self.assertRaises(r14.Rejected):r14.generate(db,db)
    def test_reject_incomplete_wal_shm(self):
        db=self.db()
        os.unlink(str(db)+'-shm')
        with self.assertRaises(r14.Rejected):r14.generate(db)
    def test_reject_bad_schema(self):
        p=self.root/'tradesv3.dryrun.sqlite'
        with sqlite3.connect(p) as c:c.execute('CREATE TABLE unrelated (id INTEGER)')
        with self.assertRaises(r14.Rejected):r14.generate(p)
    def test_reject_nonfinite_profit(self):
        with self.assertRaises(r14.Rejected):r14.generate(self.db(trades=[(0,'nan')]))
    def test_reject_symlink_path(self):
        p=self.db()
        d=self.root/'link';d.mkdir()
        l=d/p.name;l.symlink_to(p)
        with self.assertRaises(r14.Rejected):r14.generate(l)
    def test_cli_uses_stdout_sanitized_contract(self):
        p=self.db(trades=[(0,4.0)])
        result=subprocess.run([sys.executable,str(ROOT/'bridge/r14_live_wal_aggregate.py'),'--spot-db',str(p)],
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout)
        self.assertEqual(value['schema_version'],'jubao-report-v1')
        self.assertEqual([e['id'] for e in value['engines']],['spot','futures','solana'])
        self.assertEqual(value['engines'][0]['source'],'DRY_RUN_SQLITE_READ_ONLY')
        self.assertNotIn('SENSITIVE_TEST_ONLY',result.stdout)
        self.assertNotIn('BTC/USDT',result.stdout)
        self.assertNotIn(str(p),result.stdout)
    def test_cli_fail_closed_without_path_leak(self):
        p=str(self.root/'SecretPath/tradesv3.dryrun.sqlite')
        result=subprocess.run([sys.executable,str(ROOT/'bridge/r14_live_wal_aggregate.py'),'--spot-db',p],
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertEqual(result.stdout,'')
        self.assertNotIn(p,result.stderr)
    def test_report_explicitly_unverified_and_b_null(self):
        out=r14.generate(self.db(trades=[(0,1.5)]),paper_attested=True)
        self.assertTrue(out['paper_only'])
        self.assertFalse(out['live_trading'])
        self.assertTrue(out['provenance']['dry_run_operator_attested'])
        for flag in ('heartbeat_verified','profit_verified','runtime_verified','source_identity_verified'):
            self.assertFalse(out['provenance'][flag])
        self.assertIsNone(out['engines'][2]['realized_pnl_usdt'])

if __name__=='__main__':unittest.main()
