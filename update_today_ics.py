#!/usr/bin/env python3
"""Compatibility wrapper for refreshing today.ics from published ICS files."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace

from wp_log_parser.config import load_config
from wp_log_parser.service import update_today_ics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update today.ics to point at/copy today's published ICS file.")
    parser.add_argument("--config", default="./config.json")
    parser.add_argument("--publish-dir", default=None, help="Published ICS directory; overrides config.output_dir")
    parser.add_argument("--mode", choices=["copy", "symlink"], default="copy")
    parser.add_argument("--post-id", type=int, help="Prefer a specific post ID when several today's files exist")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        if args.publish_dir:
            config = replace(config, output_dir=args.publish_dir)
        result = update_today_ics(config, mode=args.mode, post_id=args.post_id, verbose=args.verbose)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
