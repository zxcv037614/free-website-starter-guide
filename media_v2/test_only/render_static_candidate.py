"""TEST_ONLY offline HTML preview: pure function, never writes to disk or GitHub."""
from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from packet_validator import validate_packet


def render_preview_html(packet: dict, *, known_paths: set[str], sitemap_locs: list[str]) -> str:
    result = validate_packet(packet, known_paths=known_paths, sitemap_locs=sitemap_locs)
    if result["status"] != "DRAFT_READY":
        raise ValueError("TEST_ONLY renderer fail-closed: " + result["status"])
    canonical = packet["canonical_url"]
    if urlsplit(canonical).hostname != "editorial.example.invalid":
        raise ValueError("TEST_ONLY only")
    links = "\n".join(f'<li><a href="{escape(p, quote=True)}">TEST_ONLY 站內教學</a></li>' for p in packet["internal_links"])
    # Strict escaping: a Markdown-like plain text preview cannot inject script or HTML.
    paragraphs = "\n".join("<p>" + escape(part.strip()) + "</p>" for part in packet["article_html_or_markdown"].split("\n\n") if part.strip())
    return ("<!doctype html>\n<html lang=\"zh-Hant\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(packet["title"])}</title>'
            f'<meta name="description" content="{escape(packet["meta_description"], quote=True)}">'
            f'<link rel="canonical" href="{escape(canonical, quote=True)}">'
            "</head><body><main><article>"
            f'<h1>{escape(packet["title"])}</h1>'
            f'<p>{escape(packet["summary"])}</p>{paragraphs}'
            f'<p>{escape(packet["affiliate_disclosure"])}</p>'
            f'<p>{escape(packet["self_brand_disclosure"])}</p>'
            f'<ul>{links}</ul></article></main></body></html>')
