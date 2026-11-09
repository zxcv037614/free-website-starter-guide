#!/usr/bin/env python3
"""JUBAO R20: evidence of a Freqtrade process holding a candidate dryrun DB.

NO reading raw DB, WAL, logs, config, argv, environ, keys, or private paths.
ONLY process comm, bounded directory listing and (dev,ino) file metadata.
Sandbox/test tool, NOT deployed or executed on any user's VPS by ChatGPT.
An observed file descriptor proves *one process had that file open at capture*;
it does NOT authenticate effective dry_run, profit or 24h strategy health.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

SCHEMA = "jubao-r20-process-db-fd-v1"
NAMES = ("tradesv3.dryrun.sqlite", "tradesv3.dry_run.sqlite")
DEFAULT_DIRS = (
    Path("/freqtrade/user_data"), Path("/freqtrade"),
    Path("/freqtrade/user_data/db"), Path.cwd()
)
MAX_PROC = 4096
MAX_FDS = 1024


class ProbeError(ValueError):
    pass


def _is_regular(path):
    try:
        if path.is_symlink():
            return None
        result = path.stat()
        return result if stat.S_ISREG(result.st_mode) else None
    except (OSError, ValueError):
        return None


def _candidates(dirs):
    seen_paths = set()
    results = []
    for folder in dirs:
        for name in NAMES:
            path = folder / name
            if str(path) in seen_paths:
                continue
            seen_paths.add(str(path))
            info = _is_regular(path)
            if info is not None:
                results.append((path, info))
    return results


def _freqtrade_processes(proc_root):
    try:
        entries = list(proc_root.iterdir())
    except OSError as exc:
        raise ProbeError("Process metadata unavailable") from exc
    if len(entries) > MAX_PROC:
        raise ProbeError("Process scan size exceeded")
    result = []
    for path in entries:
        if not path.name.isascii() or not path.name.isdecimal():
            continue
        try:
            # comm only: no cmdline, environ, logs or full process arguments.
            name = (path / "comm").read_text(encoding="ascii").strip()
            if name == "freqtrade":
                result.append(path)
        except (OSError, UnicodeError, ValueError):
            continue
    return result


def _held_file_identifiers(proc_dir):
    try:
        fd_dir = proc_dir / "fd"
        items = list(fd_dir.iterdir())
    except OSError:
        return None
    if len(items) > MAX_FDS:
        return None
    held = set()
    for f in items:
        if not f.name.isascii() or not f.name.isdecimal():
            continue
        try:
            # stat follows an already-open file descriptor, WITHOUT opening it.
            st = f.stat()
            if stat.S_ISREG(st.st_mode):
                held.add((st.st_dev, st.st_ino))
        except OSError:
            continue
    return held


def observe(*, engine, proc_root=Path("/proc"), candidate_dirs=None, now=None):
    if engine not in ("spot", "futures"):
        raise ProbeError("Only A1/A2 paper engines supported")
    now = now or datetime.now(timezone.utc)
    if candidate_dirs is None:
        candidate_dirs = DEFAULT_DIRS
    candidates = _candidates(candidate_dirs)
    procs = _freqtrade_processes(proc_root)
    states = []
    for proc in procs:
        states.append(_held_file_identifiers(proc))
    # If process fd listing is inaccessible, fail closed and report unknown.
    inaccessible = any(s is None for s in states)
    all_fds = set().union(*(s for s in states if s is not None))
    candidate_ids = {(st.st_dev, st.st_ino) for _, st in candidates}
    if len(candidates) == 1 and not inaccessible:
        st = candidates[0][1]
        identity = (st.st_dev, st.st_ino)
        observed = identity in all_fds
        fd_binding = "OBSERVED_OPEN_AT_CAPTURE" if observed else "NOT_OBSERVED"
        # Stable hint only for comparison in this observation; never output path.
        digest = hashlib.sha256(
            f"jubao-r20-devino:{st.st_dev}:{st.st_ino}".encode("ascii")
        ).hexdigest()[:16]
    else:
        fd_binding = "UNKNOWN_OR_AMBIGUOUS"
        digest = None
    return {
        "schema_version": SCHEMA,
        "source": "UNATTESTED_LOCAL_OPERATOR_METADATA",
        "captured_at_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine": engine,
        "freqtrade_process_count": len(procs),
        "paper_candidate_count": len(candidates),
        "db_fd_binding": fd_binding,
        "candidate_identity_hint": digest,
        "effective_dry_run_verified": False,
        "db_runtime_config_verified": False,
        "exchange_market_data_verified": False,
        "paper_profit_verified": False,
        "strategy_24h_verified": False,
        "note": "FD metadata only. Never infer dry-run configuration, trades, equity, or profit.",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="JUBAO R20 metadata only (NO DB reads)")
    p.add_argument("--engine", choices=("spot", "futures"), required=True)
    args = p.parse_args(argv)
    try:
        print(json.dumps(observe(engine=args.engine), ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError, TypeError):
        print("JUBAO_R20_UNAVAILABLE: process/file metadata only; no runtime proof",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
