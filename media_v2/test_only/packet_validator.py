"""TEST_ONLY: deterministic, offline and deny-by-default editorial packet validation.

No requests, publication, Git operations, background scheduling, or storage are performed.
Every *.example.invalid URL is fictional. The date is Asia/Taipei's explicit calendar day.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
EXPECTED_PACKET_VERSION = "V2"
EXAMPLE_HOST_SUFFIX = ".example.invalid"
FORBIDDEN_CLAIMS = ("實測", "保證收益", "保證賺錢", "市場第一", "Guaranteed profits", "unbeatable")
ALLOWED_STATES = frozenset({"DRAFT_READY"})
REQUIRED_FIELDS = frozenset(json.loads((HERE / "editorial_packet_v2.schema.json").read_text(encoding="utf-8"))["required"])


def result(status: str, reason: str = "") -> dict:
    return {"status": status, "reason": reason, "external_mutation": False, "cost_usd": 0}


def topic_fingerprint(topic_id: str) -> str:
    return hashlib.sha256(topic_id.strip().lower().encode("utf-8")).hexdigest()[:16]


def daily_key(editorial_date_taiwan: str, topic_id: str) -> str:
    return f"media:{editorial_date_taiwan}:{topic_fingerprint(topic_id)}"


def invalid_example_url(url: object) -> bool:
    if not isinstance(url, str):
        return True
    p = urlsplit(url)
    return p.scheme != "https" or not p.hostname or not p.hostname.endswith(EXAMPLE_HOST_SUFFIX) or bool(p.username or p.password or p.port) or not p.path.startswith("/")


def valid_date(s: object) -> bool:
    try:
        if not isinstance(s, str) or date.fromisoformat(s).isoformat() != s:
            return False
        return True
    except (TypeError, ValueError):
        return False


def validate_runtime(runtime: dict | None) -> dict:
    r = runtime or {}
    if r.get("paid_api") or r.get("runner") in ("larger", "paid", "gpu") or r.get("expected_cost_usd", 0) != 0:
        return result("COST_HOLD", "paid inference or runner is forbidden")
    if r.get("secret_required") or r.get("secret_value") or r.get("external_network"):
        return result("SECRET_HOLD", "secrets and external calls are forbidden")
    if r.get("bridge_state", "MOCK_OK") != "MOCK_OK":
        return result("BRIDGE_ACCESS_FAILED", "synthetic bridge fail-closed")
    return result("RUNTIME_TEST_ONLY_OK")


def validate_scope(repo_state: dict | None) -> dict:
    r = repo_state or {}
    if r.get("base_sha") != r.get("expected_base_sha") or not r.get("base_sha"):
        return result("SCOPE_DRIFT_HOLD", "base SHA mismatch")
    allowed = frozenset(r.get("allowed_paths", []))
    changed = frozenset(r.get("changed_paths", []))
    if not allowed or not changed or not changed.issubset(allowed):
        return result("SCOPE_DRIFT_HOLD", "path scope mismatch")
    return result("SCOPE_TEST_ONLY_OK")


def validate_browser_probe(probe: dict | None) -> dict:
    """Validate synthetic browser metrics, NOT proof of a real browser screenshot."""
    b = probe or {}
    if b.get("viewport_width") != 375 or b.get("scroll_width", 999999) > b.get("client_width", 0) + 2 or not b.get("menu_operable"):
        return result("BROWSER_VISUAL_HOLD", "synthetic viewport fail")
    return result("BROWSER_PROBE_SYNTHETIC_OK")


def validate_deployment_probe(probe: dict | None) -> dict:
    p = probe or {}
    if p.get("pages_success") and (p.get("http_status") != 200 or not p.get("canonical_matches") or not p.get("content_matches")):
        return result("DEPLOYED_HTTP_UNVERIFIED", "Pages status is not a public HTTP/body proof")
    if not p.get("pages_success"):
        return result("DEPLOYMENT_HOLD", "Pages not proven successful")
    return result("SYNTHETIC_HTTP_PROBE_OK")


def validate_packet(packet: dict, *, known_paths: set[str] | None = None, sitemap_locs: list[str] | None = None, canonical_url: str | None = None, quality_score: int = 100, publish_worthy: bool = True) -> dict:
    """Pure validation; outputs decisions only; never writes or publishes."""
    if os.environ.get("NO_EXTERNAL_MUTATION") != "1":
        return result("TEST_ONLY_ISOLATION_HOLD", "NO_EXTERNAL_MUTATION must be 1")
    if not isinstance(packet, dict) or not REQUIRED_FIELDS.issubset(packet):
        return result("SCHEMA_HOLD", "missing required fields")
    if packet.get("packet_version") != EXPECTED_PACKET_VERSION or packet.get("created_from_model") != "TEST_ONLY_MOCK":
        return result("SCHEMA_HOLD", "packet version/mock mismatch")
    if packet.get("stage_status") not in ALLOWED_STATES or packet.get("human_tested") is not False:
        return result("SCHEMA_HOLD", "wrong stage/human-tested claim")
    if not all(isinstance(packet.get(k), str) and packet[k].startswith("TEST_ONLY_") for k in ("task_id", "topic_id", "media_brand")):
        return result("SCHEMA_HOLD", "non synthetic identity")
    if not valid_date(packet.get("editorial_date_taiwan")) or not valid_date(packet.get("verified_at")):
        return result("SOURCE_VERIFICATION_HOLD", "missing date")
    if packet["verified_at"] < packet["editorial_date_taiwan"]:
        return result("SOURCE_VERIFICATION_HOLD", "unverified on publication date")
    sources = packet.get("source_urls")
    dates = packet.get("source_published_dates")
    if not isinstance(sources, list) or len(sources) < 2 or len(set(sources)) != len(sources) or any(invalid_example_url(x) for x in sources):
        return result("SOURCE_VERIFICATION_HOLD", "at least two unique fictional source URLs required")
    if not isinstance(dates, list) or len(dates) != len(sources) or any(not valid_date(x) or x > packet["verified_at"] for x in dates):
        return result("SOURCE_VERIFICATION_HOLD", "source dates must be valid and aligned")
    claims = packet.get("claim_evidence_map")
    if not isinstance(claims, list) or not claims or any(not isinstance(x, dict) or not isinstance(x.get("claim"), str) or not x["claim"].strip() or x.get("source_url") not in sources for x in claims):
        return result("SOURCE_VERIFICATION_HOLD", "unsupported claim")
    content = packet.get("article_html_or_markdown", "")
    if not isinstance(content, str) or any(word.casefold() in content.casefold() for word in FORBIDDEN_CLAIMS):
        return result("CONTENT_POLICY_HOLD", "misleading evidence or earnings claim")
    if re.search(r"(?i)https?://(?![a-z0-9.-]*\.example\.invalid/)", content):
        return result("CONTENT_POLICY_HOLD", "real external URLs are prohibited in offline fixtures")
    if len(content) < 40 or hashlib.sha256(content.encode("utf-8")).hexdigest() != packet.get("content_sha256"):
        return result("SCHEMA_HOLD", "content hash invalid")
    if not isinstance(packet.get("affiliate_disclosure"), str) or "TEST_ONLY" not in packet["affiliate_disclosure"] or not isinstance(packet.get("self_brand_disclosure"), str) or "TEST_ONLY" not in packet["self_brand_disclosure"]:
        return result("DISCLOSURE_HOLD", "fictional disclosure or owner relationship omitted")
    if packet.get("mentions_self_brand") is True and "關聯" not in packet["self_brand_disclosure"]:
        return result("DISCLOSURE_HOLD", "brand relationship unclear")
    if not isinstance(packet.get("title"), str) or len(packet["title"]) < 12 or not isinstance(packet.get("summary"), str) or len(packet["summary"]) < 12 or not isinstance(packet.get("target_reader"), str) or len(packet["target_reader"]) < 5:
        return result("SCHEMA_HOLD", "missing editorial substance")
    if not isinstance(packet.get("meta_description"), str) or not 40 <= len(packet["meta_description"]) <= 180 or packet.get("search_intent") not in ("informational", "how-to", "comparison"):
        return result("SEO_LINK_HOLD", "bad metadata")
    slug = packet.get("slug")
    if not isinstance(slug, str) or not re.fullmatch("test-only-[a-z0-9-]+", slug):
        return result("SEO_LINK_HOLD", "unsafe slug")
    expected_canonical = f"https://editorial.example.invalid/articles/{slug}.html"
    if packet.get("canonical_url") != expected_canonical or (canonical_url is not None and canonical_url != expected_canonical):
        return result("SEO_LINK_HOLD", "canonical conflict")
    if not isinstance(packet.get("source_doc_url"), str) or invalid_example_url(packet["source_doc_url"]):
        return result("SCHEMA_HOLD", "mock source document only")
    links = packet.get("internal_links")
    if not isinstance(links, list) or not links or any(not isinstance(x, str) or not x.startswith("/") or x.startswith("//") or ".." in x or "?" in x for x in links):
        return result("SEO_LINK_HOLD", "unsafe links")
    if known_paths is not None and any(x not in known_paths for x in links):
        return result("SEO_LINK_HOLD", "synthetic broken link")
    if sitemap_locs is not None and sitemap_locs.count(expected_canonical) != 1:
        return result("SEO_LINK_HOLD", "duplicate/missing sitemap loc")
    if packet.get("daily_publish_key") != daily_key(packet["editorial_date_taiwan"], packet["topic_id"]):
        return result("SCHEMA_HOLD", "idempotency key invalid")
    if quality_score < 75 or not publish_worthy or not packet.get("new_value", "").strip():
        return result("NO_PUBLISH", "low quality or no new value; skip intentionally")
    return result("DRAFT_READY", "synthetic candidate only; not approved for publication")


class PublicationRegistry:
    """Pure in-memory stand-in: never persists or performs a release."""
    def __init__(self):
        self.keys: set[str] = set()
        self.topics: dict[str, str] = {}
        self.days: dict[str, int] = {}
        self.published: dict[str, str] = {}

    def admit(self, packet: dict) -> dict:
        day = packet["editorial_date_taiwan"]
        topic = packet["topic_id"]
        key = daily_key(day, topic)
        if key in self.published:
            return result("ALREADY_PUBLISHED_NOOP", "already accepted Git commit in synthetic registry")
        if key in self.keys:
            return result("NO_DUPLICATE_RELEASE", "same canonical key replay")
        if topic in self.topics:
            return result("TOPIC_DUPLICATE_HOLD", "topic title rewrite ignored")
        if self.days.get(day, 0) >= 1:
            return result("DAILY_CAP_HOLD", "maximum 1 synthetic admission per Taiwan day")
        self.keys.add(key)
        self.topics[topic] = key
        self.days[day] = self.days.get(day, 0) + 1
        return result("ADMITTED_SYNTHETIC_ONLY", "no external publication")

    def record_success(self, packet: dict, synthetic_commit_sha: str) -> dict:
        key = daily_key(packet["editorial_date_taiwan"], packet["topic_id"])
        if key not in self.keys or not synthetic_commit_sha.startswith("TEST_ONLY_"):
            return result("PUBLISH_STATE_HOLD", "unknown canonical key or non-synthetic commit")
        if key in self.published:
            return result("ALREADY_PUBLISHED_NOOP", "synthetic success already stored")
        self.published[key] = synthetic_commit_sha
        return result("SYNTHETIC_COMMIT_RECORDED", "mock local state only")
