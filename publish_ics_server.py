#!/usr/bin/env python3
"""Compatibility wrapper for periodically publishing ICS files and serving them over HTTP."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from urllib.parse import urlparse

from wp_log_parser.config import load_config
from wp_log_parser.service import publish_once, run_service_loop


def _default_host_port(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url or "http://0.0.0.0:5333/")
    return parsed.hostname or "0.0.0.0", parsed.port or 5333


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild ICS files from WordPress posts and publish them locally.")
    parser.add_argument("--config", default="./config.json")
    parser.add_argument("--days", type=int, default=7, help="Publish recent posts from last N days")
    parser.add_argument("--interval", type=int, default=60, help="Refresh interval in seconds")
    parser.add_argument("--publish-dir", default=None, help="Directory to store published ICS files")
    parser.add_argument("--host", help="HTTP bind host; default from ics_base_url or 0.0.0.0")
    parser.add_argument("--port", type=int, help="HTTP bind port; default from ics_base_url")
    parser.add_argument("--public-base-url", help="Public base URL; overrides config.ics_base_url")
    parser.add_argument("--once", action="store_true", help="Run one publish cycle without starting the HTTP server")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        updates = {}
        if args.publish_dir:
            updates["output_dir"] = args.publish_dir
        if args.public_base_url:
            updates["ics_base_url"] = args.public_base_url.rstrip("/")
        if updates:
            config = replace(config, **updates)
        default_host, default_port = _default_host_port(config.ics_base_url)
        host = args.host or default_host
        port = args.port or default_port
        if args.once:
            result = publish_once(config, days=args.days, verbose=args.verbose)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            run_service_loop(config, days=args.days, interval_seconds=args.interval, host=host, port=port, verbose=args.verbose)
        return 0
    except KeyboardInterrupt:
        print("[INFO] Service interrupted. Shutting down cleanly.")
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
