"""JUBAO R19 offline source-proof boundaries; no VPS/network/credentials."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
import r19_offline_source_preflight as r19


def time_str(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class R19OfflineSourceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 9, 4, 0, 0, tzinfo=timezone.utc)
        self.temp = tempfile.TemporaryDirectory(prefix="jubao-r19-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def engine(self, kind):
        return {
            "id": kind, "container_running": True, "process_seen": True,
            "static_dry_run": True, "static_trading_mode": kind,
            "stake_currency_class": "USDT",
            "effective_dry_run_claim": True, "effective_trading_mode_claim": kind,
            "paper_db_candidate": True, "db_identity_distinct_claim": True,
            "process_db_binding_claim": True, "heartbeat_count_15m": 14,
            "last_heartbeat_utc": time_str(self.now - timedelta(minutes=1)),
        }

    def doc(self):
        return {
            "schema_version": r19.SCHEMA,
            "source": "OPERATOR_REDACTED_UNATTESTED",
            "captured_at_utc": time_str(self.now),
            "engines": [self.engine("spot"), self.engine("futures")]
        }

    def validate(self, payload):
        return r19.validate(payload, now=self.now)

    def test_01_full_operator_claims_still_unverified(self):
        out = self.validate(self.doc())
        self.assertEqual(out["gate_status"], "READY_FOR_INDEPENDENT_OPERATOR_REVIEW_ONLY")
        for k in ("source_identity_verified", "effective_runtime_verified",
                  "continuous_24h_strategy_verified", "authentic_paper_ledger_verified",
                  "real_profit_verified"):
            self.assertIs(out[k], False)

    def test_02_no_false_verified_fields_in_engines(self):
        out = self.validate(self.doc())
        self.assertTrue(all(e["remote_identity_verified"] is False and
                            e["authentic_paper_ledger_verified"] is False
                            for e in out["engines"]))

    def test_03_static_live_flag_forces_hold(self):
        d = self.doc()
        d["engines"][0]["static_dry_run"] = False
        self.assertEqual(self.validate(d)["gate_status"], "HOLD_POSSIBLE_LIVE_TRADING")

    def test_04_effective_live_flag_forces_hold(self):
        d = self.doc()
        d["engines"][1]["effective_dry_run_claim"] = False
        self.assertEqual(self.validate(d)["gate_status"], "HOLD_POSSIBLE_LIVE_TRADING")

    def test_05_same_db_claim_forces_hold(self):
        d = self.doc()
        d["engines"][0]["db_identity_distinct_claim"] = False
        self.assertEqual(self.validate(d)["gate_status"], "HOLD_POSSIBLE_DUPLICATE_LEDGER")

    def test_06_unknown_effective_mode_does_not_upgrade(self):
        d = self.doc()
        d["engines"][0]["effective_trading_mode_claim"] = None
        result = self.validate(d)
        self.assertEqual(result["gate_status"], "HOLD_INCOMPLETE_REMOTE_EVIDENCE")
        self.assertIn("SPOT_EFFECTIVE_RUNTIME_UNVERIFIED", result["reasons"])

    def test_07_unknown_effective_dry_run_does_not_upgrade(self):
        d = self.doc()
        d["engines"][1]["effective_dry_run_claim"] = None
        self.assertEqual(self.validate(d)["gate_status"], "HOLD_INCOMPLETE_REMOTE_EVIDENCE")

    def test_08_unknown_db_process_binding_blocks(self):
        d = self.doc()
        d["engines"][0]["process_db_binding_claim"] = None
        self.assertIn("SPOT_PROCESS_DB_BINDING_UNVERIFIED", self.validate(d)["reasons"])

    def test_09_process_missing_blocks(self):
        d = self.doc()
        d["engines"][1]["process_seen"] = False
        self.assertIn("FUTURES_PROCESS_NOT_ESTABLISHED", self.validate(d)["reasons"])

    def test_10_usdt_unknown_blocks(self):
        d = self.doc()
        d["engines"][1]["stake_currency_class"] = "UNKNOWN"
        self.assertIn("FUTURES_USDT_STAKE_UNCONFIRMED", self.validate(d)["reasons"])

    def test_11_stale_snapshot_marked(self):
        d = self.doc()
        d["captured_at_utc"] = time_str(self.now - timedelta(hours=1))
        self.assertIn("OBSERVATION_STALE_OVER_30M", self.validate(d)["reasons"])

    def test_12_future_snapshot_rejected(self):
        d = self.doc()
        d["captured_at_utc"] = time_str(self.now + timedelta(hours=1))
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_13_stale_heartbeat_not_fresh(self):
        d = self.doc()
        d["engines"][0]["last_heartbeat_utc"] = time_str(self.now - timedelta(minutes=25))
        result = self.validate(d)
        self.assertFalse(result["engines"][0]["heartbeat_within_15m_claim"])

    def test_14_future_heartbeat_rejected(self):
        d = self.doc()
        d["engines"][0]["last_heartbeat_utc"] = time_str(self.now + timedelta(hours=1))
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_15_positive_count_requires_timestamp(self):
        d = self.doc()
        d["engines"][1]["last_heartbeat_utc"] = None
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_16_zero_count_rejects_timestamp(self):
        d = self.doc()
        d["engines"][1]["heartbeat_count_15m"] = 0
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_17_reject_extra_secret_data(self):
        d = self.doc()
        d["engines"][0]["api_key"] = "NEVER_STORE_ME"
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_18_reject_extra_profit_data(self):
        d = self.doc()
        d["engines"][1]["realized_pnl_usdt"] = "1000"
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_19_reject_third_B_ledger(self):
        d = self.doc()
        d["engines"].append(self.engine("solana"))
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_20_reject_wrong_A1_A2_order(self):
        d = self.doc()
        d["engines"].reverse()
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_21_reject_unsupported_source(self):
        d = self.doc()
        d["source"] = "REMOTE_TRUSTED_VERIFIED"
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_22_reject_boolean_heartbeat_count(self):
        d = self.doc()
        d["engines"][0]["heartbeat_count_15m"] = True
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_23_reject_negative_heartbeat(self):
        d = self.doc()
        d["engines"][0]["heartbeat_count_15m"] = -1
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_24_reject_invalid_timestamp_format(self):
        d = self.doc()
        d["captured_at_utc"] = "2026-11-09T04:00:00+00:00"
        with self.assertRaises(r19.Rejected):
            self.validate(d)

    def test_25_duplicate_json_properties_rejected(self):
        with self.assertRaises(r19.Rejected):
            json.loads('{"id":"spot","id":"futures"}', object_pairs_hook=r19.strict_pairs)

    def test_26_cli_no_pnl_or_private_data(self):
        p = self.root / "safe.json"
        p.write_text(json.dumps(self.doc()), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(ROOT/"bridge/r19_offline_source_preflight.py"),str(p)],
                              capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertFalse(result["real_profit_verified"])
        self.assertNotIn("secret", proc.stdout.lower())
        self.assertNotIn(str(p), proc.stdout)
        self.assertNotIn("realized_pnl_usdt", proc.stdout)

    def test_27_cli_rejects_symlink(self):
        p = self.root / "source.json"
        p.write_text(json.dumps(self.doc()))
        alias = self.root / "linked.json"
        alias.symlink_to(p)
        proc = subprocess.run([sys.executable, str(ROOT/"bridge/r19_offline_source_preflight.py"),str(alias)],
                              capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertNotIn(str(p), proc.stderr)

    def test_28_cli_rejects_oversized_input(self):
        p = self.root / "too-large.json"
        p.write_bytes(b"{" + b"x" * 18000 + b"}")
        proc = subprocess.run([sys.executable, str(ROOT/"bridge/r19_offline_source_preflight.py"),str(p)],
                              capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")

    def test_29_synthetic_input_cannot_be_attested(self):
        d = self.doc()
        d["source"] = "SYNTHETIC_FIXTURE_ONLY"
        result = self.validate(d)
        self.assertEqual(result["source"], "SYNTHETIC_FIXTURE_ONLY")
        self.assertFalse(result["source_identity_verified"])

    def test_30_wrong_currency_literal_rejected(self):
        d = self.doc()
        d["engines"][0]["stake_currency_class"] = "BTC_SECRET"
        with self.assertRaises(r19.Rejected):
            self.validate(d)


if __name__ == "__main__":
    unittest.main()
