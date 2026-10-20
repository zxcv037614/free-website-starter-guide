"""V2-B incremental tests: synthetic, offline, temporary, no release or network.

Do not rerun the already completed V2-A 15/15 suite in this CI.
"""
import concurrent.futures
import copy
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["NO_EXTERNAL_MUTATION"] = "1"

from packet_validator import daily_key
from durable_shadow_r1 import DurableShadowJournal, TEST_SCOPE

HERE = Path(__file__).resolve().parent
FIXTURE = json.loads((HERE / "fixtures.synthetic.json").read_text(encoding="utf-8"))


class TestV2BDurableShadow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="TEST_ONLY_MEDIA_")
        self.addCleanup(self.tmp.cleanup)
        self.filename = Path(self.tmp.name) / "shadow.sqlite3"
        self.journal = DurableShadowJournal(self.filename)

    def p(self):
        return copy.deepcopy(FIXTURE["candidate"])

    def prepare(self, p=None, **options):
        return self.journal.prepare(p or self.p(), FIXTURE, **options)

    def test_01_synthetic_only_prepare_and_no_release(self):
        self.assertEqual(self.prepare(), "ADMITTED_SYNTHETIC_ONLY")
        state = self.journal.get("2026-10-19")
        self.assertEqual(state["phase"], "PREPARED")
        self.assertIsNone(state["mock_sha"])
        self.assertEqual(self.journal.count(), 1)

    def test_02_identical_retry_no_duplicate(self):
        self.assertEqual(self.prepare(), "ADMITTED_SYNTHETIC_ONLY")
        self.assertEqual(self.prepare(), "NO_DUPLICATE_PREPARED")
        self.assertEqual(self.journal.count(), 1)

    def test_03_durable_restart_retains_day_lock(self):
        self.assertEqual(self.prepare(), "ADMITTED_SYNTHETIC_ONLY")
        later = DurableShadowJournal(self.filename)
        self.assertEqual(later.prepare(self.p(), FIXTURE), "NO_DUPLICATE_PREPARED")
        self.assertEqual(later.count(), 1)

    def test_04_fresh_process_sees_same_daily_lock(self):
        self.assertEqual(self.prepare(), "ADMITTED_SYNTHETIC_ONLY")
        command = (
            "import json,sys;"
            "sys.path.insert(0,sys.argv[1]);"
            "from durable_shadow_r1 import DurableShadowJournal;"
            "from pathlib import Path;"
            "from json import loads;"
            "packet=loads(sys.stdin.read());"
            "fixture=loads((Path(sys.argv[1])/'fixtures.synthetic.json').read_text());"
            "print(DurableShadowJournal(sys.argv[2]).prepare(packet,fixture))"
        )
        done = subprocess.run(
            [sys.executable, "-c", command, str(HERE), str(self.filename)],
            input=json.dumps(self.p()), text=True, capture_output=True,
            check=True, timeout=12,
            env={**os.environ, "NO_EXTERNAL_MUTATION": "1"},
        )
        self.assertEqual(done.stdout.strip(), "NO_DUPLICATE_PREPARED")
        self.assertEqual(self.journal.count(), 1)

    def test_05_same_topic_retitle_is_duplicate_hold(self):
        self.assertEqual(self.prepare(), "ADMITTED_SYNTHETIC_ONLY")
        changed = self.p()
        changed["title"] = "TEST_ONLY 同一虛構燈籠主題的另一個資訊標題"
        self.assertEqual(self.prepare(changed), "TOPIC_DUPLICATE_HOLD")
        self.assertEqual(self.journal.count(), 1)

    def test_06_same_day_another_topic_hits_daily_cap(self):
        self.assertEqual(self.prepare(), "ADMITTED_SYNTHETIC_ONLY")
        second = self.p()
        second["topic_id"] = "TEST_ONLY_SECOND_VIRTUAL_LANTERN_TOPIC"
        second["daily_publish_key"] = daily_key(
            second["editorial_date_taiwan"], second["topic_id"])
        self.assertEqual(self.prepare(second), "DAILY_CAP_HOLD")
        self.assertEqual(self.journal.count(), 1)

    def test_07_new_day_is_independent_one_candidate(self):
        self.assertEqual(self.prepare(), "ADMITTED_SYNTHETIC_ONLY")
        next_day = self.p()
        next_day["editorial_date_taiwan"] = "2026-10-20"
        next_day["verified_at"] = "2026-10-20"
        next_day["daily_publish_key"] = daily_key(
            next_day["editorial_date_taiwan"], next_day["topic_id"])
        self.assertEqual(self.prepare(next_day), "ADMITTED_SYNTHETIC_ONLY")
        self.assertEqual(self.journal.count(), 2)

    def test_08_late_mock_ack_is_idempotent_after_restart(self):
        p = self.p()
        self.assertEqual(self.prepare(p), "ADMITTED_SYNTHETIC_ONLY")
        later = DurableShadowJournal(self.filename)
        self.assertEqual(later.record_mock_ack(p["editorial_date_taiwan"],
            p["daily_publish_key"], "TEST_ONLY_EVIDENCE_FICTIONAL",
            "TEST_ONLY_SHA_FICTIONAL"), "SYNTHETIC_ACK_RECORDED")
        again = DurableShadowJournal(self.filename)
        self.assertEqual(again.record_mock_ack(p["editorial_date_taiwan"],
            p["daily_publish_key"], "TEST_ONLY_EVIDENCE_FICTIONAL",
            "TEST_ONLY_SHA_FICTIONAL"), "ALREADY_ACKED_NOOP")
        self.assertEqual(again.prepare(p, FIXTURE), "ALREADY_ACKED_NOOP")
        self.assertEqual(again.count(), 1)

    def test_09_insufficient_mock_evidence_never_acks(self):
        p = self.p()
        self.assertEqual(self.prepare(p), "ADMITTED_SYNTHETIC_ONLY")
        for proof, sha in (("", "TEST_ONLY_SHA_FICTIONAL"),
                           ("TEST_ONLY_EVIDENCE_FICTIONAL", ""),
                           ("REAL_EVIDENCE", "TEST_ONLY_SHA_FICTIONAL"),
                           ("TEST_ONLY_EVIDENCE_FICTIONAL", "REAL_SHA")):
            self.assertEqual(self.journal.record_mock_ack(
                p["editorial_date_taiwan"], p["daily_publish_key"],
                proof, sha), "INSUFFICIENT_EVIDENCE_HOLD")
        self.assertEqual(self.journal.get(p["editorial_date_taiwan"])["phase"], "PREPARED")

    def test_10_crash_before_sqlite_commit_rolls_back(self):
        with self.assertRaisesRegex(RuntimeError, "TEST_ONLY_SIMULATED_CRASH"):
            self.prepare(crash_before_commit=True)
        later = DurableShadowJournal(self.filename)
        self.assertEqual(later.count(), 0)
        self.assertEqual(later.prepare(self.p(), FIXTURE), "ADMITTED_SYNTHETIC_ONLY")
        self.assertEqual(later.count(), 1)

    def test_11_crash_after_prepare_before_ack_no_double(self):
        p = self.p()
        self.assertEqual(self.prepare(p), "ADMITTED_SYNTHETIC_ONLY")
        # Process disappears after PREPARED durable commit and before mock ACK.
        self.journal = DurableShadowJournal(self.filename)
        self.assertEqual(self.prepare(p), "NO_DUPLICATE_PREPARED")
        self.assertEqual(self.journal.count(), 1)

    def test_12_conflicting_late_ack_is_hold(self):
        p = self.p()
        self.assertEqual(self.prepare(p), "ADMITTED_SYNTHETIC_ONLY")
        day, key = p["editorial_date_taiwan"], p["daily_publish_key"]
        self.assertEqual(self.journal.record_mock_ack(day,key,
            "TEST_ONLY_EVIDENCE_FIRST", "TEST_ONLY_SHA_FIRST"),
            "SYNTHETIC_ACK_RECORDED")
        self.assertEqual(self.journal.record_mock_ack(day,key,
            "TEST_ONLY_EVIDENCE_SECOND", "TEST_ONLY_SHA_SECOND"),
            "ACK_CONFLICT_HOLD")
        self.assertEqual(self.journal.count(), 1)

    def test_13_reject_paid_api_runner_or_nonzero_cost(self):
        for params in ({"paid_api": True},{"runner":"larger"},
                       {"runner":"gpu"},{"expected_cost_usd":1}):
            self.assertEqual(self.prepare(runtime=params), "COST_HOLD")
        self.assertEqual(self.journal.count(), 0)

    def test_14_secret_network_and_external_send_prohibited(self):
        for params in ({"secret_required":True},{"secret_value":"TEST_ONLY_CANNOT_USE"},
                       {"external_network":True}):
            self.assertEqual(self.prepare(runtime=params), "SECRET_HOLD")
        for params in ({"external_send":True}, {"real_article":True}, {"production_target":True}):
            self.assertEqual(self.prepare(runtime=params), "SECRET_HOLD")
        self.assertEqual(self.journal.count(), 0)

    def test_15_base_or_allowed_path_drift_is_hold(self):
        wrong_base = dict(TEST_SCOPE,base_sha="TEST_ONLY_OTHER_BASE")
        wrong_paths = dict(TEST_SCOPE,
            changed_paths=["articles/TEST_ONLY_PUBLICATION_FORBIDDEN.html"])
        self.assertEqual(self.prepare(scope=wrong_base), "SCOPE_DRIFT_HOLD")
        self.assertEqual(self.prepare(scope=wrong_paths), "SCOPE_DRIFT_HOLD")
        self.assertEqual(self.journal.count(), 0)

    def test_16_real_url_or_nonfictional_namespace_fail_closed(self):
        p = self.p()
        p["source_urls"][0] = "https://real-public-site.example.com/news"
        self.assertEqual(self.prepare(p), "SOURCE_VERIFICATION_HOLD")
        p = self.p()
        p["created_from_model"] = "REAL_PUBLIC_PROVIDER"
        self.assertEqual(self.prepare(p), "SCHEMA_HOLD")
        self.assertEqual(self.journal.count(), 0)

    def test_17_concurrent_prepare_only_one_record(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.prepare(), range(2)))
        self.assertEqual(sorted(results),
                         ["ADMITTED_SYNTHETIC_ONLY","NO_DUPLICATE_PREPARED"])
        self.assertEqual(self.journal.count(), 1)

    def test_18_restrict_journal_file_to_test_only_temp(self):
        with self.assertRaisesRegex(ValueError,"TEST_ONLY_PATH_HOLD"):
            DurableShadowJournal(Path(self.tmp.name).parent / "production.sqlite3")
        with self.assertRaisesRegex(ValueError,"TEST_ONLY_PATH_HOLD"):
            DurableShadowJournal(Path(self.tmp.name) / "production.json")
        self.assertEqual(self.journal.count(), 0)

    def test_19_no_external_socket_calls_and_no_git(self):
        with patch.object(socket, "socket", side_effect=AssertionError("NO_EXTERNAL_NETWORK")):
            self.assertEqual(self.prepare(), "ADMITTED_SYNTHETIC_ONLY")
        self.assertEqual(self.journal.count(), 1)

    def test_20_no_ack_without_prepared_or_wrong_key(self):
        self.assertEqual(self.journal.record_mock_ack(
            "2026-10-19", "TEST_ONLY_UNEXPECTED_KEY",
            "TEST_ONLY_EVIDENCE_SAMPLE", "TEST_ONLY_SHA_SAMPLE"),
            "NO_PREPARED_RECORD_HOLD")
        self.assertEqual(self.journal.count(), 0)


if __name__=="__main__":
    unittest.main(verbosity=2)
