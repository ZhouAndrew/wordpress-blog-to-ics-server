#!/usr/bin/env python3
"""Compatibility wrapper for exporting one WordPress post to ICS.

The canonical implementation lives in :mod:`wp_log_parser.service`.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace

from wp_log_parser.config import load_config
from wp_log_parser.service import export_post_to_ics


def _print_entries(entries: list[dict]) -> None:
    print("\nParsed entries:")
    if not entries:
        print("(none)")
        return
    for index, entry in enumerate(entries, start=1):
        print(
            f"{index:>3}) {entry.get('date')} {entry.get('start_time')}"
            f"-{entry.get('end_time') or '?'} {entry.get('summary', '')}"
        )


def _print_ignored(ignored_blocks: list[dict]) -> None:
    print("\nIgnored blocks:")
    if not ignored_blocks:
        print("(none)")
        return
    for index, block in enumerate(ignored_blocks, start=1):
        print(f"{index:>3}) {block.get('block_type') or block.get('type')} {block.get('reason')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read a WordPress post by ID and export it to an ICS file.")
    parser.add_argument("--config", default="./config.json", help="Path to config.json")
    parser.add_argument("--post-id", type=int, required=True, help="WordPress post ID")
    parser.add_argument("--output", help="Output .ics file path")
    parser.add_argument("--print-summary", action="store_true", help="Print parsed entries")
    parser.add_argument("--print-ignored", action="store_true", help="Print ignored blocks")
    parser.add_argument("--verbose", action="store_true", help="Show detailed logs")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        result = export_post_to_ics(config, args.post_id, verbose=args.verbose, output_path=args.output)
        public_result = {k: v for k, v in result.items() if k not in {"entries", "ignored_blocks"}}
        print("\nResult:")
        print(json.dumps(public_result, ensure_ascii=False, indent=2))
        if args.print_summary:
            _print_entries(result.get("entries", []))
        if args.print_ignored:
            _print_ignored(result.get("ignored_blocks", []))
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
