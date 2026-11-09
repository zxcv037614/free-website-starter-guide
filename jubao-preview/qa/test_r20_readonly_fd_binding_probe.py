"""JUBAO R20 local mock /proc FD matching: no real VPS or SQLite data reads."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
import r20_readonly_fd_binding_probe as r20


class R20FDProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jubao-r20-synthetic-")
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.proc = base / "proc"
        self.proc.mkdir()
        self.dbdir = base / "user_data"
        self.dbdir.mkdir()
        self.now = datetime(2026, 11, 9, 11, 0, 0, tzinfo=timezone.utc)

    def create_candidate(self, name="tradesv3.dryrun.sqlite"):
        f = self.dbdir / name
        f.write_bytes(b"SYNTHETIC_TEST_NOT_A_DATABASE")
        return f

    def fake_process(self, pid="42", comm="freqtrade", file=None, accessible=True):
        d = self.proc / pid
        d.mkdir()
        (d / "comm").write_text(comm + "\n")
        if accessible:
            fds = d / "fd"
            fds.mkdir()
            if file is not None:
                (fds / "9").symlink_to(file)
        return d

    def observe(self):
        return r20.observe(engine="spot", proc_root=self.proc,
                           candidate_dirs=(self.dbdir,), now=self.now)

    def test_01_matching_open_db_stat_observed(self):
        db = self.create_candidate()
        self.fake_process(file=db)
        result = self.observe()
        self.assertEqual(result["db_fd_binding"], "OBSERVED_OPEN_AT_CAPTURE")
        self.assertEqual(result["paper_candidate_count"], 1)
        self.assertEqual(result["freqtrade_process_count"], 1)

    def test_02_no_fd_match_is_not_runtime_fail(self):
        self.create_candidate()
        self.fake_process()
        result = self.observe()
        self.assertEqual(result["db_fd_binding"], "NOT_OBSERVED")
        self.assertFalse(result["db_runtime_config_verified"])

    def test_03_no_process_same_not_observed(self):
        self.create_candidate()
        result = self.observe()
        self.assertEqual(result["freqtrade_process_count"], 0)
        self.assertEqual(result["db_fd_binding"], "NOT_OBSERVED")

    def test_04_missing_candidate_is_unknown(self):
        self.fake_process()
        result = self.observe()
        self.assertEqual(result["db_fd_binding"], "UNKNOWN_OR_AMBIGUOUS")
        self.assertEqual(result["paper_candidate_count"], 0)

    def test_05_multiple_dbs_ambiguous(self):
        self.create_candidate("tradesv3.dryrun.sqlite")
        self.create_candidate("tradesv3.dry_run.sqlite")
        self.fake_process()
        self.assertEqual(self.observe()["db_fd_binding"], "UNKNOWN_OR_AMBIGUOUS")

    def test_06_other_process_does_not_count(self):
        db = self.create_candidate()
        self.fake_process(comm="python3", file=db)
        result = self.observe()
        self.assertEqual(result["freqtrade_process_count"], 0)
        self.assertEqual(result["db_fd_binding"], "NOT_OBSERVED")

    def test_07_unreadable_fd_directory_is_unknown(self):
        self.create_candidate()
        self.fake_process(accessible=False)
        self.assertEqual(self.observe()["db_fd_binding"], "UNKNOWN_OR_AMBIGUOUS")

    def test_08_symlink_candidate_denied(self):
        outside = self.dbdir / "real.data"
        outside.write_bytes(b"TEST")
        link = self.dbdir / "tradesv3.dryrun.sqlite"
        link.symlink_to(outside)
        self.fake_process(file=outside)
        self.assertEqual(self.observe()["paper_candidate_count"], 0)

    def test_09_stable_digest_only_never_paths(self):
        db = self.create_candidate()
        self.fake_process(file=db)
        a, b = self.observe(), self.observe()
        self.assertEqual(a["candidate_identity_hint"], b["candidate_identity_hint"])
        self.assertEqual(len(a["candidate_identity_hint"]), 16)
        serialized = json.dumps(a)
        self.assertNotIn(str(db), serialized)
        self.assertNotIn(str(self.proc), serialized)
        self.assertNotIn("SYNTHETIC_TEST_NOT_A_DATABASE", serialized)

    def test_10_two_different_fds_count_once(self):
        db = self.create_candidate()
        d = self.fake_process(file=db)
        (d / "fd" / "10").symlink_to(db)
        self.assertEqual(self.observe()["db_fd_binding"], "OBSERVED_OPEN_AT_CAPTURE")

    def test_11_no_claims_of_runtime_verification(self):
        db = self.create_candidate()
        self.fake_process(file=db)
        out = self.observe()
        for key in ("effective_dry_run_verified", "db_runtime_config_verified",
                    "exchange_market_data_verified", "paper_profit_verified",
                    "strategy_24h_verified"):
            self.assertIs(out[key], False)

    def test_12_wrong_engine_rejected(self):
        with self.assertRaises(r20.ProbeError):
            r20.observe(engine="solana", proc_root=self.proc, candidate_dirs=(self.dbdir,))

    def test_13_process_scan_cap(self):
        self.create_candidate()
        for n in range(r20.MAX_PROC + 1):
            (self.proc / ("item_" + str(n))).touch()
        with self.assertRaises(r20.ProbeError):
            self.observe()

    def test_14_bad_proc_root_error_sanitized(self):
        with self.assertRaises(r20.ProbeError):
            r20.observe(engine="spot", proc_root=self.proc/"not-here",
                        candidate_dirs=(self.dbdir,))

    def test_15_no_argv_env_config_log_sqlite_access(self):
        source = (ROOT / "bridge" / "r20_readonly_fd_binding_probe.py").read_text()
        for term in (
            'Path("/proc/self/environ")', 'read_bytes(', 'cmdline").read_',
            'import sqlite3', 'subprocess.', 'import requests', 'import docker',
        ):
            self.assertNotIn(term, source)
        self.assertIn('/ "comm"', source)
        self.assertIn('/ "fd"', source)

    def test_16_same_inode_candidate_does_not_verify_live_trading(self):
        db = self.create_candidate()
        self.fake_process(file=db)
        out = self.observe()
        self.assertFalse(out["effective_dry_run_verified"])
        self.assertFalse(out["paper_profit_verified"])


if __name__ == "__main__":
    unittest.main()
