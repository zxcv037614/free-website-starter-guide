#!/usr/bin/env python3
"""JUBAO R17 localhost-only Owner Session -> R15 paper report gateway.

SANDBOX ONLY: synthetic/local review, not a public identity provider or VPS
deployment. No trade actions, background polling, raw SQLite or exchange keys.
Production requires external Owner identity, TLS, reverse-proxy, revocation
and independent security review; do not publish this process on 0.0.0.0.
"""
import argparse
from datetime import datetime, timezone
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
import http.client
import json
import os
import secrets
import sys
import time

from r15_private_paper_endpoint import public_report, ReportUnavailable

HOST = "127.0.0.1"
REPORT_PATH = "/api/v1/owner/paper-report"
LOGIN_PATH = "/api/v1/owner/session"
LOGOUT_PATH = "/api/v1/owner/logout"
OWNER_SECRET_ENV = "JUBAO_R17_LOCAL_TEST_OWNER_SECRET"
UPSTREAM_TOKEN_ENV = "JUBAO_R15_OWNER_TOKEN"
MAX_BODY = 4096
MAX_REPORT = 1024 * 1024
SESSION_SECONDS = 600
COOKIE = "__Host-jubao_owner"


def _upstream_report(port, token):
    """Fixed loopback destination: never accept user-controlled URLs or redirects."""
    conn = http.client.HTTPConnection(HOST, port, timeout=3)
    try:
        conn.request("GET", "/api/v1/paper-report",
                     headers={"Authorization": "Bearer " + token,
                              "Accept": "application/json",
                              "Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        if resp.status != 200:
            raise ReportUnavailable("Upstream unavailable")
        if "application/json" not in resp.getheader("Content-Type", "").lower():
            raise ReportUnavailable("Unexpected upstream type")
        data = resp.read(MAX_REPORT + 1)
        if not data or len(data) > MAX_REPORT:
            raise ReportUnavailable("Upstream payload size")
        return json.loads(data.decode("utf-8"))
    except (OSError, ValueError, UnicodeError, http.client.HTTPException) as exc:
        raise ReportUnavailable("Upstream unavailable") from exc
    finally:
        conn.close()


def make_server(*, owner_secret, upstream_token, upstream_port=8765,
                port=0, provider=None, clock=time.time):
    if not isinstance(owner_secret, str) or len(owner_secret) < 32:
        raise ValueError("Local test owner secret requires 32+ characters")
    if not isinstance(upstream_token, str) or len(upstream_token) < 32:
        raise ValueError("R15 secret requires 32+ characters")
    if any(c in owner_secret + upstream_token for c in "\r\n"):
        raise ValueError("No line breaks in secrets")
    if any(type(p) is not int or p < 0 or p > 65535
           for p in (port, upstream_port)):
        raise ValueError("Invalid port")
    if upstream_port == 0 and provider is None:
        raise ValueError("Upstream port required")
    # Session state only in process memory; never persistent, never logged.
    sessions = {}
    login_failures = [0]
    fetch = provider if provider is not None else lambda: _upstream_report(upstream_port, upstream_token)

    class Handler(BaseHTTPRequestHandler):
        server_version = "JubaoR17LocalTest/0"
        sys_version = ""

        def log_message(self, *_args):
            return  # Do not log cookies, secrets, paths or returned values.

        def _host_ok(self):
            return self.headers.get("Host", "") in (
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}")

        def _origin_ok(self):
            host = self.headers.get("Host", "")
            return self._host_ok() and self.headers.get("Origin", "") == "http://" + host

        def _send(self, status, payload, cookie=None):
            raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            if len(raw) > MAX_REPORT:
                status, raw = 503, b'{"error":"REPORT_UNAVAILABLE"}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            # Never allow CORS or expose the local bearer token.
            self.end_headers()
            self.wfile.write(raw)

        def _session(self):
            jar = SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie", ""))
            except Exception:
                return None
            item = jar.get(COOKIE)
            if not item:
                return None
            session_id = item.value
            expires = sessions.get(session_id)
            if expires is None:
                return None
            if clock() >= expires:
                sessions.pop(session_id, None)
                return None
            return session_id

        def _body(self):
            size = self.headers.get("Content-Length", "")
            if not size.isascii() or not size.isdigit():
                raise ValueError("Invalid length")
            length = int(size)
            if not 0 < length <= MAX_BODY:
                raise ValueError("Body size")
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Invalid body")
            return value

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "LOCALHOST_ONLY"})
            if self.path != REPORT_PATH:
                return self._send(404, {"error": "NOT_FOUND"})
            if self._session() is None:
                return self._send(401, {"error": "OWNER_SESSION_REQUIRED"})
            try:
                # R15's existing whitelist/provenance projection is reused here.
                result = public_report(fetch())
                if result["live_trading"] is not False or result["paper_only"] is not True:
                    raise ReportUnavailable("Unsafe mode")
                return self._send(200, result)
            except (OSError, ValueError, TypeError, OverflowError):
                return self._send(503, {"error": "REPORT_UNAVAILABLE"})

        def do_POST(self):
            if not self._origin_ok():
                return self._send(403, {"error": "ORIGIN_REJECTED"})
            if self.path == LOGIN_PATH:
                if login_failures[0] >= 5:
                    return self._send(429, {"error": "LOCAL_TEST_LOGIN_LOCKED"})
                try:
                    body = self._body()
                    attempt = body.get("owner_secret", "")
                    if not isinstance(attempt, str):
                        raise ValueError("Invalid secret")
                    accepted = hmac.compare_digest(attempt, owner_secret)
                except (ValueError, UnicodeError):
                    accepted = False
                if not accepted:
                    login_failures[0] += 1
                    return self._send(401, {"error": "OWNER_SESSION_REQUIRED"})
                login_failures[0] = 0
                sid = secrets.token_urlsafe(36)
                sessions[sid] = clock() + SESSION_SECONDS
                secure_cookie = (f"{COOKIE}={sid}; Path=/; HttpOnly; Secure;"
                                 f" SameSite=Strict; Max-Age={SESSION_SECONDS}")
                return self._send(200, {"authenticated": True,
                                        "test_only": True,
                                        "expires_in_seconds": SESSION_SECONDS},
                                  cookie=secure_cookie)
            if self.path == LOGOUT_PATH:
                sid = self._session()
                if sid:
                    sessions.pop(sid, None)
                return self._send(200, {"authenticated": False},
                                  cookie=f"{COOKIE}=; Path=/; HttpOnly; Secure;"
                                         " SameSite=Strict; Max-Age=0")
            return self._send(405, {"error": "METHOD_NOT_ALLOWED"})

        def do_PUT(self):
            return self._send(405, {"error": "READ_ONLY"})

        def do_PATCH(self):
            return self._send(405, {"error": "READ_ONLY"})

        def do_DELETE(self):
            return self._send(405, {"error": "READ_ONLY"})

        def do_OPTIONS(self):
            return self._send(405, {"error": "NO_CORS"})

    return HTTPServer((HOST, port), Handler)


def main(argv=None):
    args = argparse.ArgumentParser(description="JUBAO R17 LOCAL TEST gateway; not production")
    args.add_argument("--port", type=int, default=8787)
    args.add_argument("--upstream-port", type=int, default=8765)
    parsed = args.parse_args(argv)
    try:
        srv = make_server(
            owner_secret=os.environ.get(OWNER_SECRET_ENV),
            upstream_token=os.environ.get(UPSTREAM_TOKEN_ENV),
            upstream_port=parsed.upstream_port, port=parsed.port)
    except (ValueError, TypeError, OSError):
        print("JUBAO_R17_REJECTED: local test secrets/ports missing", file=sys.stderr)
        return 2
    try:
        print("JUBAO R17 SANDBOX: localhost-only test gateway; NO deployment")
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
