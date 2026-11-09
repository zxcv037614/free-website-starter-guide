"""R15 synthetic tests: owner-only loopback paper endpoint; NO VPS or keys."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'bridge'))
import r14_live_wal_aggregate as r14
import r15_private_paper_endpoint as r15

DUMMY_TOKEN = "SYNTHETIC_R15_TOKEN_" + "a" * 32


class R15PrivateEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jubao-r15-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'tradesv3.dryrun.sqlite'
        self.conn = sqlite3.connect(self.db)
        self.addCleanup(self.conn.close)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA wal_autocheckpoint=0')
        self.conn.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, is_open INTEGER, close_profit_abs REAL, pair TEXT, private_note TEXT)")
        self.conn.execute("INSERT INTO trades (is_open,close_profit_abs,pair,private_note) VALUES (0,8.25,'BTC/USDT','SYNTHETIC_SECRET_VALUE')")
        self.conn.commit()
        self.assertTrue(Path(str(self.db) + '-wal').exists())
        self.server = None
        self.opener = build_opener(ProxyHandler({}))

    def start(self, *, provider=None):
        self.server = r15.make_server(spot_db=self.db, token=DUMMY_TOKEN, port=0,
                                      provider=provider)
        self.addCleanup(self.stop)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:%d%s' % (self.server.server_port, r15.PATH)
        self.assertEqual(self.server.server_address[0], '127.0.0.1')

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
            self.server = None

    def get(self, path=None, method="GET", token=DUMMY_TOKEN, other_headers=None):
        headers = {} if token is None else {"Authorization": "Bearer " + token}
        headers.update(other_headers or {})
        req = Request(path or self.url, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=3) as f:
                return f.status, json.loads(f.read().decode()), dict(f.headers)
        except HTTPError as error:
            with closing(error):
                return error.code, json.loads(error.read().decode()), dict(error.headers)

    def test_01_authorized_get_returns_three_sanitized_engines(self):
        self.start()
        code, data, headers = self.get()
        self.assertEqual(code, 200)
        self.assertEqual([e['id'] for e in data['engines']], ['spot', 'futures', 'solana'])
        self.assertEqual(data['engines'][0]['realized_pnl_usdt'], '8.25')
        self.assertIsNone(data['engines'][2]['realized_pnl_usdt'])
        self.assertTrue(data['paper_only'])
        self.assertFalse(data['live_trading'])
        self.assertFalse(data['provenance']['profit_verified'])
        self.assertNotIn('BTC/USDT', json.dumps(data))
        self.assertNotIn('SYNTHETIC_SECRET_VALUE', json.dumps(data))
        self.assertNotIn(str(self.db), json.dumps(data))

    def test_02_second_get_reads_new_wal_data_on_demand(self):
        self.start()
        self.assertEqual(self.get()[1]['engines'][0]['closed_trades'], 1)
        self.conn.execute("INSERT INTO trades (is_open,close_profit_abs) VALUES (0,-1.25)")
        self.conn.commit()
        result = self.get()[1]
        self.assertEqual(result['engines'][0]['closed_trades'], 2)
        self.assertEqual(result['engines'][0]['realized_pnl_usdt'], '7.00')

    def test_03_missing_authorization_is_denied(self):
        self.start()
        code, data, _ = self.get(token=None)
        self.assertEqual((code, data['error']), (401, 'UNAUTHORIZED'))

    def test_04_invalid_token_is_denied(self):
        self.start()
        self.assertEqual(self.get(token="X" * 48)[0], 401)

    def test_05_token_in_url_cannot_bypass_auth(self):
        self.start()
        self.assertEqual(self.get(path=self.url + '?token=' + DUMMY_TOKEN)[0], 404)

    def test_06_rejects_dns_rebinding_host(self):
        self.start()
        self.assertEqual(self.get(other_headers={'Host':'attacker.example'})[0], 403)

    def test_07_missing_path_has_no_data(self):
        self.start()
        self.assertEqual(self.get(path=self.url.replace(r15.PATH,'/raw-config'))[0], 404)

    def test_08_post_is_never_supported(self):
        self.start()
        self.assertEqual(self.get(method='POST')[0], 405)

    def test_09_put_is_never_supported(self):
        self.start()
        self.assertEqual(self.get(method='PUT')[0], 405)

    def test_10_delete_is_never_supported(self):
        self.start()
        self.assertEqual(self.get(method='DELETE')[0], 405)

    def test_11_cors_preflight_is_denied(self):
        self.start()
        code, _, headers = self.get(method='OPTIONS',
            other_headers={'Origin':'https://untrusted.example',
                           'Access-Control-Request-Method':'GET'})
        self.assertEqual(code,405)
        self.assertNotIn('Access-Control-Allow-Origin',headers)

    def test_12_security_headers_prevent_cache_and_embedding(self):
        self.start()
        _, _, headers = self.get()
        self.assertEqual(headers.get('Cache-Control'), 'no-store')
        self.assertEqual(headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(headers.get('X-Frame-Options'), 'DENY')
        self.assertNotIn('Access-Control-Allow-Origin',headers)

    def test_13_provider_secret_fields_never_pass_whitelist(self):
        raw=r14.generate(self.db)
        raw['secret'] = "HIDDEN_SECRET"
        raw['engines'][0]['private_trade_rows'] = [{"pair":"SOL/USDT","password":"HIDDEN_SECRET"}]
        raw['brand'] = "HIDDEN_SECRET"
        raw['engines'][0]['notice'] = "HIDDEN_SECRET"
        self.start(provider=lambda:raw)
        code, data, _ = self.get()
        self.assertEqual(code,200)
        self.assertNotIn('HIDDEN_SECRET',json.dumps(data))
        self.assertNotIn('private_trade_rows',json.dumps(data))

    def test_14_malicious_verified_flags_are_forced_false(self):
        raw=r14.generate(self.db)
        raw['provenance']={'runtime_verified':True,'profit_verified':True,'heartbeat_verified':True}
        self.start(provider=lambda:raw)
        data=self.get()[1]
        self.assertFalse(data['provenance']['runtime_verified'])
        self.assertFalse(data['provenance']['profit_verified'])
        self.assertFalse(data['provenance']['heartbeat_verified'])

    def test_15_fake_connected_source_fails_closed(self):
        raw=r14.generate(self.db)
        raw['engines'][0]['source']='FAKE_VERIFIED'
        self.start(provider=lambda:raw)
        self.assertEqual(self.get()[0],503)

    def test_16_b_cannot_claim_swaps_or_profit(self):
        raw=r14.generate(self.db)
        raw['engines'][2]['source']='SOME_VERIFIED_SOURCE'
        raw['engines'][2]['realized_pnl_usdt']='99999'
        raw['engines'][2]['connected']=True
        self.start(provider=lambda:raw)
        data=self.get()[1]
        self.assertFalse(data['engines'][2]['connected'])
        self.assertIsNone(data['engines'][2]['realized_pnl_usdt'])

    def test_17_malformed_money_fails_closed(self):
        raw=r14.generate(self.db)
        raw['engines'][0]['realized_pnl_usdt']='NaN'
        self.start(provider=lambda:raw)
        self.assertEqual(self.get()[0],503)

    def test_18_missing_real_database_fails_with_no_path_leak(self):
        missing=self.root/'missing'/'tradesv3.dryrun.sqlite'
        self.server = r15.make_server(spot_db=missing,token=DUMMY_TOKEN,port=0)
        self.addCleanup(self.stop)
        self.thread=threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:%d%s' % (self.server.server_port,r15.PATH)
        code,data,_=self.get()
        self.assertEqual(code,503)
        self.assertNotIn(str(missing),json.dumps(data))

    def test_19_reject_missing_or_weak_authentication_config(self):
        with self.assertRaises(ValueError):
            r15.make_server(spot_db=self.db, token=None)
        with self.assertRaises(ValueError):
            r15.make_server(spot_db=self.db, token='a'*8)
        with self.assertRaises(ValueError):
            r15.make_server(spot_db=self.db, token=DUMMY_TOKEN, port=70000)

    def test_20_wal_metadata_not_mutated_by_authorized_get(self):
        self.start()
        files=[self.db,Path(str(self.db)+'-wal'),Path(str(self.db)+'-shm')]
        before=[(p.stat().st_size,p.stat().st_mtime_ns) for p in files]
        self.assertEqual(self.get()[0],200)
        self.assertEqual(before,[(p.stat().st_size,p.stat().st_mtime_ns) for p in files])

    def test_21_no_background_polling_before_owner_request(self):
        reads=[]
        self.start(provider=lambda:(reads.append(1),r14.generate(self.db))[1])
        self.assertEqual(reads,[])
        self.assertEqual(self.get(token=None)[0],401)
        self.assertEqual(reads,[])
        self.assertEqual(self.get()[0],200)
        self.assertEqual(len(reads),1)


if __name__ == '__main__':
    unittest.main()
