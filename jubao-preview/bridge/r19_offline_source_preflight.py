#!/usr/bin/env python3
"""JUBAO R19: strictly bounded OFFLINE review of redacted runtime evidence.

Does not connect to VPS, Docker, exchanges, SQLite, SSH or the internet.
Operator input is never proof of remote identity; all verification flags remain
false. Never send private config/logs/DBs/keys to this tool or public GitHub.
"""
import argparse
from datetime import datetime, timezone, timedelta
import json
import re
import sys
from pathlib import Path

SCHEMA = "jubao-r19-source-preflight-v1"
MAX_INPUT_BYTES = 16 * 1024
SOURCE_LABELS = frozenset({"SYNTHETIC_FIXTURE_ONLY", "OPERATOR_REDACTED_UNATTESTED"})
ENGINE_KEYS = frozenset({
    "id", "container_running", "process_seen", "static_dry_run",
    "static_trading_mode", "stake_currency_class",
    "effective_dry_run_claim", "effective_trading_mode_claim",
    "paper_db_candidate", "db_identity_distinct_claim",
    "process_db_binding_claim", "heartbeat_count_15m",
    "last_heartbeat_utc",
})
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class Rejected(ValueError):
    pass


def strict_pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise Rejected("Duplicate field")
        out[key] = value
    return out


def iso_time(s):
    if type(s) is not str or not TIME_RE.fullmatch(s):
        raise Rejected("Invalid timestamp")
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != s:
            raise Rejected("Noncanonical timestamp")
        return dt
    except (ValueError, OverflowError):
        raise Rejected("Invalid timestamp") from None


def optional_bool(x):
    if x is not None and type(x) is not bool:
        raise Rejected("Invalid observation flag")


def validate(raw, *, now=None):
    """Validate UNATTESTED operator assertions, output only a fixed whitelist."""
    if type(raw) is not dict or set(raw) != {
        "schema_version", "source", "captured_at_utc", "engines"
    }:
        raise Rejected("Unexpected input envelope")
    if raw["schema_version"] != SCHEMA or raw["source"] not in SOURCE_LABELS:
        raise Rejected("Unsupported evidence")
    now = now or datetime.now(timezone.utc)
    captured = iso_time(raw["captured_at_utc"])
    if captured > now + timedelta(minutes=5):
        raise Rejected("Future observation")
    engines = raw["engines"]
    if type(engines) is not list or len(engines) != 2:
        raise Rejected("A1/A2 required")
    reasons = []
    if captured < now - timedelta(minutes=30):
        reasons.append("OBSERVATION_STALE_OVER_30M")
    sanitized = []
    possible_live = False
    possibly_same_db = False

    for index, expected in enumerate(("spot", "futures")):
        item = engines[index]
        if type(item) is not dict or set(item) != ENGINE_KEYS:
            raise Rejected("Unexpected engine evidence")
        if item["id"] != expected:
            raise Rejected("Wrong engine identity")
        for k in ("container_running", "process_seen", "static_dry_run",
                  "effective_dry_run_claim", "paper_db_candidate",
                  "db_identity_distinct_claim", "process_db_binding_claim"):
            optional_bool(item[k])
        for k in ("static_trading_mode", "effective_trading_mode_claim"):
            if item[k] not in ("spot", "futures", None):
                raise Rejected("Wrong trading mode label")
        if item["stake_currency_class"] not in ("USDT", "OTHER", "UNKNOWN"):
            raise Rejected("Only redacted currency classification allowed")
        n = item["heartbeat_count_15m"]
        if n is not None and (type(n) is not int or n < 0 or n > 1000):
            raise Rejected("Invalid bounded heartbeat count")
        last = item["last_heartbeat_utc"]
        if last is not None:
            last_dt = iso_time(last)
            if last_dt > captured + timedelta(minutes=5):
                raise Rejected("Future heartbeat")
            if n is None or n == 0:
                raise Rejected("Heartbeat conflict")
        elif n is not None and n > 0:
            raise Rejected("Heartbeat timestamp missing")
        else:
            last_dt = None
        recent = (n is not None and n > 0 and last_dt is not None
                  and timedelta(0) <= captured - last_dt <= timedelta(minutes=15))
        if item["static_dry_run"] is False or item["effective_dry_run_claim"] is False:
            possible_live = True
        if item["db_identity_distinct_claim"] is False:
            possibly_same_db = True
        if item["container_running"] is not True or item["process_seen"] is not True:
            reasons.append(expected.upper() + "_PROCESS_NOT_ESTABLISHED")
        if item["static_dry_run"] is not True:
            reasons.append(expected.upper() + "_STATIC_DRY_RUN_UNCONFIRMED")
        if item["static_trading_mode"] != expected:
            reasons.append(expected.upper() + "_STATIC_TRADING_MODE_UNCONFIRMED")
        if item["effective_dry_run_claim"] is not True or item["effective_trading_mode_claim"] != expected:
            reasons.append(expected.upper() + "_EFFECTIVE_RUNTIME_UNVERIFIED")
        if item["stake_currency_class"] != "USDT":
            reasons.append(expected.upper() + "_USDT_STAKE_UNCONFIRMED")
        if item["paper_db_candidate"] is not True:
            reasons.append(expected.upper() + "_PAPER_DB_CANDIDATE_UNKNOWN")
        if item["db_identity_distinct_claim"] is not True:
            reasons.append(expected.upper() + "_DB_INDEPENDENCE_UNVERIFIED")
        if item["process_db_binding_claim"] is not True:
            reasons.append(expected.upper() + "_PROCESS_DB_BINDING_UNVERIFIED")
        if not recent:
            reasons.append(expected.upper() + "_FRESH_APP_HEARTBEAT_UNCONFIRMED")
        sanitized.append({
            "id": expected,
            "claimed_static_dry_run": item["static_dry_run"],
            "claimed_effective_dry_run": item["effective_dry_run_claim"],
            "claimed_paper_db_candidate": item["paper_db_candidate"],
            "claimed_process_db_binding": item["process_db_binding_claim"],
            "heartbeat_within_15m_claim": recent,
            "remote_identity_verified": False,
            "authentic_paper_ledger_verified": False,
        })
    if possible_live:
        result = "HOLD_POSSIBLE_LIVE_TRADING"
    elif possibly_same_db:
        result = "HOLD_POSSIBLE_DUPLICATE_LEDGER"
    elif reasons:
        result = "HOLD_INCOMPLETE_REMOTE_EVIDENCE"
    else:
        result = "READY_FOR_INDEPENDENT_OPERATOR_REVIEW_ONLY"
    return {
        "schema_version": "jubao-r19-source-preflight-result-v1",
        "source": raw["source"],
        "gate_status": result,
        "source_identity_verified": False,
        "effective_runtime_verified": False,
        "continuous_24h_strategy_verified": False,
        "authentic_paper_ledger_verified": False,
        "real_profit_verified": False,
        "owner_gate_required_for_vps_changes": True,
        "reasons": sorted(set(reasons)),
        "engines": sanitized,
        "notice": "UNATTESTED OFFLINE INPUT ONLY; never display synthetic or unverified figures as real PnL",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="R19 offline strict UNATTESTED preflight")
    parser.add_argument("file", help="A local redacted JSON, never raw VPS files or secrets")
    args = parser.parse_args(argv)
    try:
        p = Path(args.file)
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_INPUT_BYTES:
            raise Rejected("Invalid input file")
        raw = p.read_bytes()
        if len(raw) > MAX_INPUT_BYTES:
            raise Rejected("Input too large")
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_pairs)
        report = validate(doc)
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, ValueError, UnicodeError, TypeError):
        print("JUBAO_R19_REJECTED: bounded redacted evidence unavailable", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
