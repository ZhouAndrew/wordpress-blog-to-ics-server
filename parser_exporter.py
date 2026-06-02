#!/usr/bin/env python3
"""Small compatibility demo for the canonical parser and ICS exporter."""
from __future__ import annotations

import json

from wp_log_parser.ics import generate_ics
from wp_log_parser.parser import parse_post_content as _parse_post_content


def parse_post_content(post_content: str, post_date: str = "2026-04-11") -> dict:
    """Parse sample post content through the package parser and return the public contract."""
    parsed = _parse_post_content(post_content, post_date)
    payload = parsed.to_dict(include_ignored=True)
    payload["ics_preview"] = generate_ics(payload["entries"])
    return payload


if __name__ == "__main__":
    sample_post_content = """<!-- wp:paragraph -->
<p>07:45 Into the breakfast and bake the pizza</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>07:48 Bake two pizzas for two minutes and 15 seconds</p>
<!-- /wp:paragraph -->

<!-- wp:file {\"id\":10221} -->
<div class=\"wp-block-file\"><a href=\"https://example.local/file.html\">file</a></div>
<!-- /wp:file -->
"""
    print(json.dumps(parse_post_content(sample_post_content), ensure_ascii=False, indent=2))
