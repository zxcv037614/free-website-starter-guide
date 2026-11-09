#!/usr/bin/env python3
"""JUBAO R15: LOCALHOST-ONLY owner-authenticated read-only paper report endpoint.

Sandbox only. No public binding, no credential persistence, no trading, no
schedule, no database writes. The existing R14 WAL reader runs ON DEMAND after
owner Bearer authentication. R14 and R15 do not verify real-world profitability.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import json
import os
import re
import sys

import r14_live_wal_aggregate as r14

HOST = "127.0.0.1"
PATH = "/api/v1/paper-report"
MAX_BYTES = 1024 * 1024
TOKEN_ENV = "JUBAO_R15_OWNER_TOKEN"
TIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
MONEY_PATTERN = re.compile(r"^-?\d{1,40}(?:\.\d{1,20})?$")


class ReportUnavailable(ValueError):
    pass


def _number(x):
    if x is None:
        return None
    if type(x) is not int or x < 0 or x > r14.MAX_TRADES:
        raise ReportUnavailable("Invalid aggregate count")
    return x


def _money(x):
    if x is None:
        return None
    if not isinstance(x, str) or not MONEY_PATTERN.fullmatch(x):
        raise ReportUnavailable("Invalid aggregate value")
    try:
        if not Decimal(x).is_finite():
            raise ReportUnavailable("Nonfinite aggregate")
    except InvalidOperation:
        raise ReportUnavailable("Invalid aggregate")
    return x


def public_report(raw):
    """Whitelist-only projection. Never expose unchecked provenance or secrets."""
    if not isinstance(raw, dict) or raw.get("schema_version") != "jubao-report-v1":
        raise ReportUnavailable("Invalid report schema")
    if raw.get("paper_only") is not True or raw.get("live_trading") is not False:
        raise ReportUnavailable("No live-trading reports allowed")
    when = raw.get("generated_at_utc")
    if not isinstance(when, str) or not TIME_PATTERN.fullmatch(when):
        raise ReportUnavailable("Invalid source time")
    try:
        ts = datetime.fromisoformat(when.replace("Z", "+00:00"))
        if ts > datetime.now(timezone.utc).replace(microsecond=0):
            raise ReportUnavailable("Future source time")
    except (ValueError, OverflowError):
        raise ReportUnavailable("Invalid source time") from None
    items = raw.get("engines")
    if not isinstance(items, list) or len(items) != 3:
        raise ReportUnavailable("Expected three engines")
    projected = []
    for index, kind in enumerate(("spot", "futures")):
        item = items[index]
        if not isinstance(item, dict) or item.get("id") != kind:
            raise ReportUnavailable("Wrong engine ordering")
        source = item.get("source")
        connected = item.get("connected")
        if source == "DRY_RUN_SQLITE_READ_ONLY" and connected is True:
            closed, opened, pnl = (_number(item.get("closed_trades")),
                                   _number(item.get("open_trades")),
                                   _money(item.get("realized_pnl_usdt")))
            if closed is None or opened is None:
                raise ReportUnavailable("Missing aggregate")
        elif source == "NOT_CONNECTED" and connected is False:
            closed = opened = pnl = None
        else:
            raise ReportUnavailable("Untrusted source or connection")
        projected.append({
            "id": kind, "source": source, "connected": connected,
            "closed_trades": closed, "open_trades": opened,
            "realized_pnl_usdt": pnl,
            "notice": "LOCAL_ONLY UNVERIFIED PAPER AGGREGATE; not authenticated profit, balance or runtime",
        })
    b = items[2]
    if not isinstance(b, dict) or b.get("id") != "solana":
        raise ReportUnavailable("Wrong B monitor")
    projected.append({
        "id": "solana", "source": "SOLANA_MONITOR_SNAPSHOT", "connected": False,
        "closed_trades": None, "open_trades": None, "realized_pnl_usdt": None,
        "notice": "B monitoring only; verified swaps and PnL unavailable",
    })
    return {
        "schema_version": "jubao-report-v1",
        "generated_at_utc": when,
        "brand": "JUBAO private local read-only paper preview; all profit UNVERIFIED",
        "live_trading": False, "paper_only": True,
        "provenance": {
            "mode": "LOCAL_ACTIVE_WAL_RO",
            "heartbeat_verified": False, "runtime_verified": False,
            "profit_verified": False, "source_identity_verified": False,
        },
        "engines": projected,
    }


def make_server(*, spot_db=None, futures_db=None, token, port=0, provider=None):
    if not isinstance(token, str) or len(token) < 32 or "\n" in token or "\r" in token:
        raise ValueError("Owner token must be at least 32 characters")
    if not isinstance(port, int) or not (0 <= port <= 65535):
        raise ValueError("Invalid local port")
    if provider is None:
        if not spot_db and not futures_db:
            raise ValueError("At least one local paper database required")
        provider = lambda: r14.generate(spot_db, futures_db)

    class Handler(BaseHTTPRequestHandler):
        server_version = "JubaoPrivatePaper/0"
        sys_version = ""

        def log_message(self, format, *args):
            # Never log URL, Authorization headers, tokens, private DB paths.
            return

        def _send(self, code, content):
            body = json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(body) > MAX_BYTES:
                code, body = 503, b'{"error":"REPORT_UNAVAILABLE"}'
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'")
            # Deliberately no Access-Control-Allow-Origin. Loopback ONLY.
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            # Prevent DNS rebinding via Host; no public reverse proxy in R15.
            host = self.headers.get("Host", "")
            if host not in (f"127.0.0.1:{self.server.server_port}",
                            f"localhost:{self.server.server_port}"):
                return self._send(403, {"error": "LOCALHOST_ONLY"})
            if self.path != PATH:
                return self._send(404, {"error": "NOT_FOUND"})
            auth = self.headers.get("Authorization", "")
            expected = "Bearer " + token
            if not hmac.compare_digest(auth, expected):
                return self._send(401, {"error": "UNAUTHORIZED"})
            try:
                data = public_report(provider())
                self._send(200, data)
            except (r14.Rejected, ReportUnavailable, OSError, OverflowError,
                    TypeError, ValueError):
                self._send(503, {"error": "REPORT_UNAVAILABLE"})

        def do_POST(self):
            self._send(405, {"error": "READ_ONLY_GET_ONLY"})

        def do_PUT(self):
            self._send(405, {"error": "READ_ONLY_GET_ONLY"})

        def do_DELETE(self):
            self._send(405, {"error": "READ_ONLY_GET_ONLY"})

        def do_OPTIONS(self):
            self._send(405, {"error": "READ_ONLY_GET_ONLY"})

    # Strict loopback-only even if caller passes a custom port.
    return HTTPServer((HOST, port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="JUBAO local-owner-only paper report read")
    parser.add_argument("--spot-db")
    parser.add_argument("--futures-db")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        token = os.environ.get(TOKEN_ENV)
        server = make_server(spot_db=args.spot_db, futures_db=args.futures_db,
                             token=token, port=args.port)
    except (ValueError, TypeError, OSError):
        print("JUBAO_R15_REJECTED: local paper endpoint configuration unavailable", file=sys.stderr)
        return 2
    try:
        print("JUBAO R15 local read-only owner endpoint bound to loopback only; NO public access")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
