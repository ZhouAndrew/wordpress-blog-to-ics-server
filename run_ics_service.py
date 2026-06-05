#!/usr/bin/env python3
"""Compatibility wrapper for the package ICS publishing service."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace

from wp_log_parser.config import load_config
from wp_log_parser.service import publish_once, run_service_loop


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the WordPress log ICS publishing service.")
    parser.add_argument("--config", default="./config.json")
    parser.add_argument("--publish-dir", default=None, help="Published ICS directory; overrides config.output_dir")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5333)
    parser.add_argument("--once", action="store_true", help="Run one publish cycle without starting the HTTP server")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        if args.publish_dir:
            config = replace(config, output_dir=args.publish_dir)
        if args.once:
            result = publish_once(config, days=args.days, verbose=args.verbose)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            run_service_loop(config, days=args.days, interval_seconds=args.interval, host=args.host, port=args.port, verbose=args.verbose)
        return 0
    except KeyboardInterrupt:
        print("[INFO] Service interrupted. Shutting down cleanly.")
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
