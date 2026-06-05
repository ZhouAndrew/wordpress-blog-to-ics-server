#!/usr/bin/env python3
"""Compatibility wrapper for listing recent WordPress post metadata."""
from __future__ import annotations

import argparse
import json
import sys

from wp_log_parser.config import load_config
from wp_log_parser.service import list_recent_posts


def _print_human(posts: list[dict], days: int) -> None:
    print(f"Recent posts from last {days} days:")
    if not posts:
        print("(none)")
        return
    for post in posts:
        print(f"{post.get('date')} [{post.get('status', '')}] {post.get('title', '')} (ID: {post.get('id')})")


def _print_jsonl(posts: list[dict]) -> None:
    for post in posts:
        print(json.dumps({"id": post.get("id"), "title": post.get("title"), "date": post.get("date"), "status": post.get("status")}, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List recent WordPress posts by title and ID.")
    parser.add_argument("--config", default="./config.json", help="Path to config.json")
    parser.add_argument("--days", "-n", type=int, default=7, help="List posts from the last N days (default: 7)")
    parser.add_argument("--format", choices=["human", "jsonl"], default="human", help="Output format")
    args = parser.parse_args(argv)

    if args.days < 0:
        print("Error: --days must be >= 0", file=sys.stderr)
        return 2
    try:
        posts = list_recent_posts(load_config(args.config), args.days)
        if args.format == "jsonl":
            _print_jsonl(posts)
        else:
            _print_human(posts, args.days)
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
