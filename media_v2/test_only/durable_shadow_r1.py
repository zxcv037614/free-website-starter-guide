"""TEST_ONLY_MEDIA V2-B: ephemeral SQLite crash-safe editorial SHADOW journal.

This module NEVER publishes, creates real articles, makes network calls, or touches
the checked-out repository. Callers MUST choose a TEST_ONLY_MEDIA_* temp directory.
The SQLite file is durable ONLY inside that test directory; it is not a cloud store.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

from packet_validator import daily_key, validate_packet, validate_runtime, validate_scope
from render_static_candidate import render_preview_html

SHADOW_NS = "TEST_ONLY_MEDIA"
TEST_SCOPE = {
    "base_sha": "TEST_ONLY_BASE_SHA",
    "expected_base_sha": "TEST_ONLY_BASE_SHA",
    "allowed_paths": ["media_v2/test_only/durable_shadow_r1.py"],
    "changed_paths": ["media_v2/test_only/durable_shadow_r1.py"],
}

class DurableShadowJournal:
    """SQLite BEGIN IMMEDIATE and a unique per-day key enforce a synthetic cap."""

    def __init__(self, sqlite_file):
        if os.environ.get("NO_EXTERNAL_MUTATION") != "1":
            raise ValueError("TEST_ONLY_ISOLATION_HOLD")
        self.path = Path(sqlite_file).resolve()
        if self.path.suffix != ".sqlite3" or not self.path.parent.name.startswith("TEST_ONLY_MEDIA_"):
            raise ValueError("TEST_ONLY_PATH_HOLD")
        if not self.path.parent.is_dir():
            raise ValueError("TEST_ONLY_PATH_HOLD")
        db = self._connect()
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS shadow_days (
                day TEXT PRIMARY KEY,
                topic_id TEXT NOT NULL,
                daily_key TEXT UNIQUE NOT NULL,
                fingerprint TEXT NOT NULL,
                phase TEXT NOT NULL CHECK(phase IN ('PREPARED','MOCK_ACKED')),
                proof TEXT,
                mock_sha TEXT
            )""")
            db.commit()
        finally:
            db.close()

    def _connect(self):
        conn = sqlite3.connect(str(self.path), timeout=6, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=6000")
        return conn

    def _read(self, day):
        db = self._connect()
        try:
            row = db.execute("SELECT * FROM shadow_days WHERE day=?", (day,)).fetchone()
            return dict(row) if row else None
        finally:
            db.close()

    def get(self, day):
        if not isinstance(day, str) or len(day) != 10:
            return None
        return self._read(day)

    def count(self):
        db = self._connect()
        try:
            return db.execute("SELECT count(*) FROM shadow_days").fetchone()[0]
        finally:
            db.close()

    def prepare(self, packet, fixture, *, runtime=None, scope=None, crash_before_commit=False):
        """Prepare fictional draft only. Returns statuses, never a release command."""
        if os.environ.get("NO_EXTERNAL_MUTATION") != "1":
            return "TEST_ONLY_ISOLATION_HOLD"
        runtime_status = validate_runtime(runtime)
        if runtime_status["status"] != "RUNTIME_TEST_ONLY_OK":
            return runtime_status["status"]
        scope_status = validate_scope(TEST_SCOPE if scope is None else scope)
        if scope_status["status"] != "SCOPE_TEST_ONLY_OK":
            return scope_status["status"]
        if not isinstance(packet, dict) or not isinstance(fixture, dict):
            return "SCHEMA_HOLD"
        verified = validate_packet(
            packet, known_paths=set(fixture["known_paths"]),
            sitemap_locs=fixture["sitemap_locs"],
        )
        if verified["status"] != "DRAFT_READY":
            return verified["status"]
        # This source renderer is pure: successful validation is NOT publishing.
        html = render_preview_html(packet,
            known_paths=set(fixture["known_paths"]), sitemap_locs=fixture["sitemap_locs"])
        if "TEST_ONLY" not in html or "<script" in html:
            return "TEST_ONLY_ISOLATION_HOLD"
        day, topic = packet["editorial_date_taiwan"], packet["topic_id"]
        key = packet["daily_publish_key"]
        if key != daily_key(day, topic):
            return "SCHEMA_HOLD"
        fingerprint = hashlib.sha256(
            (packet["title"] + "\n" + packet["content_sha256"]).encode("utf-8")
        ).hexdigest()
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM shadow_days WHERE day=?", (day,)).fetchone()
            if old:
                if old["topic_id"] != topic:
                    response = "DAILY_CAP_HOLD"
                elif old["daily_key"] != key or old["fingerprint"] != fingerprint:
                    response = "TOPIC_DUPLICATE_HOLD"
                elif old["phase"] == "MOCK_ACKED":
                    response = "ALREADY_ACKED_NOOP"
                else:
                    response = "NO_DUPLICATE_PREPARED"
                db.commit()
                return response
            db.execute(
                "INSERT INTO shadow_days(day,topic_id,daily_key,fingerprint,phase)"
                " VALUES(?,?,?,?,?)",
                (day, topic, key, fingerprint, "PREPARED"))
            if crash_before_commit:
                raise RuntimeError("TEST_ONLY_SIMULATED_CRASH_BEFORE_SQLITE_COMMIT")
            db.commit()
            return "ADMITTED_SYNTHETIC_ONLY"
        finally:
            if db.in_transaction:
                db.rollback()
            db.close()

    def record_mock_ack(self, day, key, proof, mock_sha):
        """Record FICTIONAL acknowledgement; there is no network or publish call."""
        if os.environ.get("NO_EXTERNAL_MUTATION") != "1":
            return "TEST_ONLY_ISOLATION_HOLD"
        if (not isinstance(proof, str) or not proof.startswith("TEST_ONLY_EVIDENCE_")
                or not isinstance(mock_sha, str) or not mock_sha.startswith("TEST_ONLY_SHA_")):
            return "INSUFFICIENT_EVIDENCE_HOLD"
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM shadow_days WHERE day=?", (day,)).fetchone()
            if not row or row["daily_key"] != key:
                db.commit()
                return "NO_PREPARED_RECORD_HOLD"
            if row["phase"] == "MOCK_ACKED":
                response = ("ALREADY_ACKED_NOOP" if
                            row["proof"] == proof and row["mock_sha"] == mock_sha
                            else "ACK_CONFLICT_HOLD")
                db.commit()
                return response
            db.execute("UPDATE shadow_days SET phase='MOCK_ACKED',proof=?,mock_sha=? WHERE day=?",
                       (proof, mock_sha, day))
            db.commit()
            return "SYNTHETIC_ACK_RECORDED"
        finally:
            if db.in_transaction:
                db.rollback()
            db.close()
