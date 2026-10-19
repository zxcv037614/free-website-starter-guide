"""Exactly 15 local, offline TEST_ONLY acceptance tests. No generated release files."""
import copy
import hashlib
import json
import os
import socket
import unittest
from pathlib import Path

# The process and code are fail-closed for actual network access.
os.environ["NO_EXTERNAL_MUTATION"] = "1"

def network_denied(*args, **kwargs):
    raise AssertionError("TEST_ONLY no external network access permitted")
socket.socket = network_denied
socket.create_connection = network_denied

from packet_validator import (PublicationRegistry, daily_key, validate_browser_probe,
    validate_deployment_probe, validate_packet, validate_runtime, validate_scope)
from render_static_candidate import render_preview_html

FILE = Path(__file__).resolve().parent / "fixtures.synthetic.json"
FIXTURE = json.loads(FILE.read_text(encoding="utf-8"))


def packet():
    p = copy.deepcopy(FIXTURE["candidate"])
    p["content_sha256"] = hashlib.sha256(p["article_html_or_markdown"].encode("utf-8")).hexdigest()
    p["daily_publish_key"] = daily_key(p["editorial_date_taiwan"], p["topic_id"])
    return p


def decision(p, **kwargs):
    return validate_packet(p, known_paths=set(FIXTURE["known_paths"]),
                           sitemap_locs=FIXTURE["sitemap_locs"], **kwargs)["status"]


class TestV2AOffline(unittest.TestCase):
    def test_01_valid_two_source_synthetic_original(self):
        p = packet()
        self.assertEqual(decision(p), "DRAFT_READY")
        html = render_preview_html(p, known_paths=set(FIXTURE["known_paths"]), sitemap_locs=FIXTURE["sitemap_locs"])
        self.assertIn('rel="canonical"', html)
        self.assertIn('href="/guide.html"', html)
        self.assertIn("TEST_ONLY", html)
        self.assertNotIn("<script", html)

    def test_02_same_day_packet_retry_canonical_idempotency(self):
        p, registry = packet(), PublicationRegistry()
        self.assertEqual(registry.admit(p)["status"], "ADMITTED_SYNTHETIC_ONLY")
        self.assertEqual(registry.admit(p)["status"], "NO_DUPLICATE_RELEASE")
        self.assertEqual(registry.days[p["editorial_date_taiwan"]], 1)

    def test_03_title_rewrite_same_topic_duplicate_hold(self):
        p, registry = packet(), PublicationRegistry()
        self.assertEqual(registry.admit(p)["status"], "ADMITTED_SYNTHETIC_ONLY")
        rewrite = copy.deepcopy(p)
        rewrite["title"] = "TEST_ONLY 另一種不同標題，實際為相同虛構燈籠主題"
        rewrite["editorial_date_taiwan"] = "2026-10-20"
        rewrite["daily_publish_key"] = daily_key(rewrite["editorial_date_taiwan"], rewrite["topic_id"])
        self.assertEqual(registry.admit(rewrite)["status"], "TOPIC_DUPLICATE_HOLD")

    def test_04_missing_official_date_or_broken_source(self):
        p = packet()
        p["source_published_dates"] = ["2026-10-19"]
        self.assertEqual(decision(p), "SOURCE_VERIFICATION_HOLD")
        p = packet()
        p["source_urls"][0] = "https://fictional.example.invalid/no-evidence"
        self.assertEqual(decision(p), "SOURCE_VERIFICATION_HOLD")

    def test_05_claimed_test_or_guaranteed_profit_hold(self):
        for claim in ("這是我們實測結果。", "保證收益"):
            p = packet()
            p["article_html_or_markdown"] += claim
            p["content_sha256"] = hashlib.sha256(p["article_html_or_markdown"].encode()).hexdigest()
            self.assertEqual(decision(p), "CONTENT_POLICY_HOLD")

    def test_06_disclosure_and_related_brand_hold(self):
        p=packet(); p["affiliate_disclosure"]=""
        self.assertEqual(decision(p),"DISCLOSURE_HOLD")
        p=packet(); p["mentions_self_brand"]=True; p["self_brand_disclosure"]="TEST_ONLY fake publisher."
        self.assertEqual(decision(p),"DISCLOSURE_HOLD")

    def test_07_canonical_sitemap_and_local_link_hold(self):
        p=packet()
        self.assertEqual(decision(p,canonical_url="https://editorial.example.invalid/wrong"),"SEO_LINK_HOLD")
        p=packet(); self.assertEqual(validate_packet(p,known_paths=set(FIXTURE["known_paths"]),sitemap_locs=FIXTURE["sitemap_locs"]*2)["status"],"SEO_LINK_HOLD")
        p=packet(); p["internal_links"]=["/missing.html"]
        self.assertEqual(decision(p),"SEO_LINK_HOLD")

    def test_08_synthetic_browser_metrics_fail_closed(self):
        self.assertEqual(validate_browser_probe({"viewport_width":375,"scroll_width":421,"client_width":375,"menu_operable":False})["status"],"BROWSER_VISUAL_HOLD")
        self.assertEqual(validate_browser_probe({"viewport_width":375,"scroll_width":375,"client_width":375,"menu_operable":True})["status"],"BROWSER_PROBE_SYNTHETIC_OK")

    def test_09_inaccessible_mock_bridge_fail_closed(self):
        self.assertEqual(validate_runtime({"bridge_state":"NO_ACCESS"})["status"],"BRIDGE_ACCESS_FAILED")

    def test_10_retry_delayed_task_daily_publish_cap(self):
        reg=PublicationRegistry(); p=packet()
        self.assertEqual(reg.admit(p)["status"],"ADMITTED_SYNTHETIC_ONLY")
        self.assertEqual(reg.admit(p)["status"],"NO_DUPLICATE_RELEASE")
        q=packet(); q["topic_id"]="TEST_ONLY_ANOTHER_SYNTHETIC_TOPIC"; q["daily_publish_key"]=daily_key(q["editorial_date_taiwan"],q["topic_id"])
        self.assertEqual(reg.admit(q)["status"],"DAILY_CAP_HOLD")
        self.assertEqual(reg.days[p["editorial_date_taiwan"]],1)

    def test_11_cost_paid_runner_and_secret_hold(self):
        self.assertEqual(validate_runtime({"paid_api":True})["status"],"COST_HOLD")
        self.assertEqual(validate_runtime({"runner":"larger"})["status"],"COST_HOLD")
        self.assertEqual(validate_runtime({"secret_required":True})["status"],"SECRET_HOLD")
        self.assertEqual(validate_runtime({"external_network":True})["status"],"SECRET_HOLD")

    def test_12_base_sha_and_scope_drift_hold(self):
        good={"base_sha":"TEST_ONLY_SHA","expected_base_sha":"TEST_ONLY_SHA","changed_paths":["media_v2/test_only/packet_validator.py"],"allowed_paths":["media_v2/test_only/packet_validator.py"]}
        self.assertEqual(validate_scope(good)["status"],"SCOPE_TEST_ONLY_OK")
        bad=dict(good,base_sha="TEST_ONLY_MOVED")
        self.assertEqual(validate_scope(bad)["status"],"SCOPE_DRIFT_HOLD")
        bad=dict(good,changed_paths=["main.html"])
        self.assertEqual(validate_scope(bad)["status"],"SCOPE_DRIFT_HOLD")

    def test_13_pages_success_but_public_404_not_complete(self):
        r={"pages_success":True,"http_status":404,"canonical_matches":False,"content_matches":False}
        self.assertEqual(validate_deployment_probe(r)["status"],"DEPLOYED_HTTP_UNVERIFIED")

    def test_14_low_value_no_real_news_intentionally_skip(self):
        self.assertEqual(decision(packet(),quality_score=45,publish_worthy=False),"NO_PUBLISH")

    def test_15_late_merge_ack_does_not_double_publish(self):
        p=packet(); reg=PublicationRegistry()
        self.assertEqual(reg.admit(p)["status"],"ADMITTED_SYNTHETIC_ONLY")
        self.assertEqual(reg.record_success(p,"TEST_ONLY_SHA_123")["status"],"SYNTHETIC_COMMIT_RECORDED")
        self.assertEqual(reg.record_success(p,"TEST_ONLY_SHA_123")["status"],"ALREADY_PUBLISHED_NOOP")
        self.assertEqual(reg.admit(p)["status"],"ALREADY_PUBLISHED_NOOP")
        self.assertEqual(len(reg.published),1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
