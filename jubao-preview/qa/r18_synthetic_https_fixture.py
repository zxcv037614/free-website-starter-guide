#!/usr/bin/env python3
"""R18 synthetic HTTPS fixture: REAL R15->R17 HTTP chain, original R8 UI.

CI/local browser testing only. NO VPS, NO actual owner credentials, NO real
SQLite, NO exchange credentials, NO deploy and NO production auth.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import ssl
import sys
import threading

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "bridge"))

import r15_private_paper_endpoint as r15
import r17_local_owner_session_gateway as r17

TEST_SECRET = "R18-TEST-ONLY-OWNER-NOT-FOR-DEPLOY-" + "e" * 40
TEST_TOKEN = "R18-TEST-ONLY-R15-NOT-FOR-DEPLOY-" + "f" * 40


def synthetic_report():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema_version": "jubao-report-v1",
        "generated_at_utc": stamp,
        "paper_only": True, "live_trading": False,
        "engines": [
            {"id": "spot", "source": "DRY_RUN_SQLITE_READ_ONLY",
             "connected": True, "closed_trades": 2, "open_trades": 1,
             "realized_pnl_usdt": "11.25"},
            {"id": "futures", "source": "DRY_RUN_SQLITE_READ_ONLY",
             "connected": True, "closed_trades": 2, "open_trades": 0,
             "realized_pnl_usdt": "-3.50"},
            {"id": "solana", "source": "SOLANA_MONITOR_SNAPSHOT",
             "connected": False, "closed_trades": None, "open_trades": None,
             "realized_pnl_usdt": None},
        ]
    }


def build_preview():
    original = (BASE / "index.html").read_text(encoding="utf-8")
    if original.count("</body>") != 1:
        raise ValueError("Unchanged R8 HTML closing body anchor not found exactly once")
    r16 = (BASE / "bridge" / "r16_owner_dashboard_sync.js").read_text(encoding="utf-8")
    r18 = (BASE / "bridge" / "r18_local_owner_login.js").read_text(encoding="utf-8")
    if any("</script>" in s.lower() for s in (r16, r18)):
        raise ValueError("Script payload contains premature closing tag")
    return original.replace("</body>", "<script>\n" + r16 + "\n</script>\n"
                            "<script>\n" + r18 + "\n</script>\n</body>")


def make_fixture_server(certfile, keyfile):
    original_html = build_preview().encode("utf-8")
    upstream = r15.make_server(token=TEST_TOKEN, provider=synthetic_report, port=0)
    worker = threading.Thread(target=upstream.serve_forever, daemon=True)
    worker.start()
    gateway = r17.make_server(owner_secret=TEST_SECRET, upstream_token=TEST_TOKEN,
                               upstream_port=upstream.server_port, port=0)
    parent_handler = gateway.RequestHandlerClass

    class PreviewHandler(parent_handler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                if not self._host_ok():
                    return self._send(403, {"error": "LOCALHOST_ONLY"})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(original_html)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(original_html)
                return
            return super().do_GET()

    gateway.RequestHandlerClass = PreviewHandler
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile, keyfile)
    gateway.socket = context.wrap_socket(gateway.socket, server_side=True)
    return gateway, upstream, worker


def main(argv=None):
    parser = argparse.ArgumentParser(description="R18 LOCAL synthetic HTTPS browser test only")
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args(argv)
    gateway, upstream, worker = make_fixture_server(args.cert, args.key)
    try:
        # Print only non-secret local origin; no tokens or credentials in logs.
        print(f"https://127.0.0.1:{gateway.server_port}", flush=True)
        gateway.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        gateway.server_close()
        upstream.shutdown()
        upstream.server_close()
        worker.join(timeout=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
