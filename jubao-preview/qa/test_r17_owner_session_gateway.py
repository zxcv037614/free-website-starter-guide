#!/usr/bin/env python3
"""R17 synthetic, localhost-only contract tests; never touch the live VPS."""
import http.client
import json
from pathlib import Path
import sys
import threading
from datetime import datetime, timezone
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
import r17_local_owner_session_gateway as r17
import r15_private_paper_endpoint as r15

SECRET = "synthetic-owner-secret-" + "a" * 40
TOKEN = "synthetic-upstream-token-" + "b" * 40


def valid_report():
    return {
        "schema_version": "jubao-report-v1",
        "paper_only": True, "live_trading": False,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engines": [
            {"id": "spot", "source": "DRY_RUN_SQLITE_READ_ONLY",
             "connected": True, "open_trades": 1, "closed_trades": 2,
             "realized_pnl_usdt": "3.50", "private_key": "MUST_NOT_LEAK"},
            {"id": "futures", "source": "NOT_CONNECTED",
             "connected": False, "open_trades": None, "closed_trades": None,
             "realized_pnl_usdt": None},
            {"id": "solana", "source": "SOLANA_MONITOR_SNAPSHOT",
             "connected": False, "open_trades": None, "closed_trades": None,
             "realized_pnl_usdt": None},
        ],
        "private_database_path": "MUST_NOT_LEAK",
    }


class R17GatewayTests(unittest.TestCase):
    def setUp(self):
        self.now = [1800000000.]
        self.calls = []
        self.data = valid_report()
        self.server = r17.make_server(
            owner_secret=SECRET, upstream_token=TOKEN,
            provider=self.provider, port=0, clock=lambda: self.now[0])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.origin = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def provider(self):
        self.calls.append("read")
        return self.data

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        raw = json.dumps(body).encode() if body is not None else None
        h = {"Host": f"127.0.0.1:{self.port}"}
        if raw is not None:
            h["Content-Type"] = "application/json"
        if headers:
            h.update(headers)
        try:
            conn.request(method, path, body=raw, headers=h)
            response = conn.getresponse()
            data = response.read()
            return response.status, dict(response.getheaders()), json.loads(data)
        finally:
            conn.close()

    def login(self):
        status, headers, body = self.request(
            "POST", r17.LOGIN_PATH, {"owner_secret": SECRET},
            {"Origin": self.origin})
        self.assertEqual(status, 200)
        self.assertTrue(body["test_only"])
        return headers["Set-Cookie"].split(";", 1)[0]

    def test_01_no_session_no_read(self):
        status, _, value = self.request("GET", r17.REPORT_PATH)
        self.assertEqual((status, value["error"]), (401, "OWNER_SESSION_REQUIRED"))
        self.assertEqual(self.calls, [])

    def test_02_login_requires_origin(self):
        status, _, _ = self.request("POST", r17.LOGIN_PATH, {"owner_secret": SECRET})
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

    def test_03_login_rejects_bad_secret(self):
        status, _, _ = self.request(
            "POST", r17.LOGIN_PATH, {"owner_secret": "bad"},
            {"Origin": self.origin})
        self.assertEqual(status, 401)

    def test_04_cookie_http_only_secure_strict(self):
        status, headers, _ = self.request(
            "POST", r17.LOGIN_PATH, {"owner_secret": SECRET},
            {"Origin": self.origin})
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"]
        for flag in ("HttpOnly", "Secure", "SameSite=Strict", "Max-Age=600", "Path=/"):
            self.assertIn(flag, cookie)
        self.assertIn("__Host-jubao_owner=", cookie)

    def test_05_auth_projection(self):
        cookie = self.login()
        status, headers, body = self.request(
            "GET", r17.REPORT_PATH, headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertEqual(body["engines"][0]["realized_pnl_usdt"], "3.50")
        self.assertFalse(body["provenance"]["profit_verified"])
        self.assertFalse(body["live_trading"])
        self.assertNotIn("MUST_NOT_LEAK", json.dumps(body))
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.calls, ["read"])

    def test_06_invalid_cookie_rejected(self):
        status, _, _ = self.request(
            "GET", r17.REPORT_PATH,
            headers={"Cookie": "__Host-jubao_owner=fake"})
        self.assertEqual(status, 401)
        self.assertEqual(self.calls, [])

    def test_07_logout_revokes_session(self):
        cookie = self.login()
        status, headers, _ = self.request(
            "POST", r17.LOGOUT_PATH, {}, {"Origin": self.origin, "Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        status, _, _ = self.request("GET", r17.REPORT_PATH,
                                    headers={"Cookie": cookie})
        self.assertEqual(status, 401)
        self.assertEqual(self.calls, [])

    def test_08_expired_cookie_rejected(self):
        cookie = self.login()
        self.now[0] += 601
        status, _, _ = self.request("GET", r17.REPORT_PATH,
                                    headers={"Cookie": cookie})
        self.assertEqual(status, 401)
        self.assertEqual(self.calls, [])

    def test_09_live_mode_rejected(self):
        cookie = self.login()
        self.data["live_trading"] = True
        status, _, body = self.request("GET", r17.REPORT_PATH,
                                       headers={"Cookie": cookie})
        self.assertEqual((status, body["error"]), (503, "REPORT_UNAVAILABLE"))

    def test_10_fake_B_profit_never_exported(self):
        cookie = self.login()
        self.data["engines"][2]["realized_pnl_usdt"] = "10000000"
        status, _, body = self.request("GET", r17.REPORT_PATH,
                                       headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertIsNone(body["engines"][2]["realized_pnl_usdt"])

    def test_11_host_rejected(self):
        cookie = self.login()
        status, _, _ = self.request("GET", r17.REPORT_PATH,
                                    headers={"Host": "attacker.example",
                                             "Cookie": cookie})
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

    def test_12_methods_are_read_only(self):
        for method in ("PUT", "PATCH", "DELETE", "OPTIONS"):
            status, _, _ = self.request(method, r17.REPORT_PATH)
            self.assertEqual(status, 405)
        self.assertEqual(self.calls, [])

    def test_13_unknown_path_denied(self):
        status, _, _ = self.request("GET", "/api/v1/owner/orders")
        self.assertEqual(status, 404)

    def test_14_invalid_body_fails_closed(self):
        status, _, _ = self.request("POST", r17.LOGIN_PATH,
                                    {"owner_secret": "a" * 5000},
                                    {"Origin": self.origin})
        self.assertEqual(status, 401)

    def test_15_cross_site_logout_blocked(self):
        cookie = self.login()
        status, _, _ = self.request(
            "POST", r17.LOGOUT_PATH, {},
            {"Origin": "https://attacker.example", "Cookie": cookie})
        self.assertEqual(status, 403)
        status, _, _ = self.request("GET", r17.REPORT_PATH,
                                    headers={"Cookie": cookie})
        self.assertEqual(status, 200)

    def test_16_bad_source_rejected(self):
        cookie = self.login()
        self.data["engines"][0]["source"] = "EXCHANGE_LIVE"
        status, _, _ = self.request("GET", r17.REPORT_PATH,
                                    headers={"Cookie": cookie})
        self.assertEqual(status, 503)

    def test_17_login_lockout(self):
        for _ in range(5):
            status, _, _ = self.request(
                "POST", r17.LOGIN_PATH, {"owner_secret": "incorrect"},
                {"Origin": self.origin})
            self.assertEqual(status, 401)
        status, _, _ = self.request(
            "POST", r17.LOGIN_PATH, {"owner_secret": SECRET},
            {"Origin": self.origin})
        self.assertEqual(status, 429)

    def test_18_setup_requires_secrets(self):
        for secret in ("short", None):
            with self.assertRaises((ValueError, TypeError)):
                r17.make_server(owner_secret=secret, upstream_token=TOKEN)

    def test_19_upstream_failure_no_details(self):
        cookie = self.login()
        self.data = {"schema_version": "invalid", "private_key": "SECRET_VALUE"}
        status, _, body = self.request("GET", r17.REPORT_PATH,
                                       headers={"Cookie": cookie})
        self.assertEqual(status, 503)
        self.assertEqual(body, {"error": "REPORT_UNAVAILABLE"})


class R17R15LoopbackIntegration(unittest.TestCase):
    def test_20_end_to_end_synthetic_r15_loopback(self):
        upstream = r15.make_server(token=TOKEN, provider=valid_report, port=0)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        gateway = r17.make_server(owner_secret=SECRET, upstream_token=TOKEN,
                                   upstream_port=upstream.server_port, port=0)
        gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
        gateway_thread.start()
        try:
            port = gateway.server_port
            origin = f"http://127.0.0.1:{port}"
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            login_body = json.dumps({"owner_secret": SECRET}).encode()
            conn.request("POST", r17.LOGIN_PATH, login_body,
                         {"Origin": origin, "Content-Type": "application/json"})
            reply = conn.getresponse()
            self.assertEqual(reply.status, 200)
            cookie = reply.getheader("Set-Cookie").split(";", 1)[0]
            reply.read()
            conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("GET", r17.REPORT_PATH, headers={"Cookie": cookie})
            reply = conn.getresponse()
            body = json.loads(reply.read())
            self.assertEqual(reply.status, 200)
            self.assertEqual(body["engines"][0]["closed_trades"], 2)
            self.assertIsNone(body["engines"][2]["realized_pnl_usdt"])
            conn.close()
        finally:
            gateway.shutdown()
            gateway.server_close()
            gateway_thread.join(timeout=2)
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
