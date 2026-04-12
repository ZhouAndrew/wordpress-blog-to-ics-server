#!/usr/bin/env python3
import argparse
import subprocess
import sys
import threading
import time
from datetime import datetime


class Logger:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def _ts(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def info(self, msg: str) -> None:
        print(f"[{self._ts()}] [INFO] {msg}")

    def ok(self, msg: str) -> None:
        print(f"[{self._ts()}] [OK] {msg}")

    def error(self, msg: str) -> None:
        print(f"[{self._ts()}] [ERROR] {msg}", file=sys.stderr)


def run_publish_server(cmd: list[str], log: Logger) -> None:
    log.info("Starting publish_ics_server")
    subprocess.run(cmd)


def run_today_updater(
    cmd: list[str],
    interval: int,
    log: Logger,
) -> None:
    log.info("Starting today.ics updater loop")
    while True:
        try:
            log.info("Updating today.ics")
            subprocess.run(cmd, check=True)
            log.ok("today.ics updated")
        except subprocess.CalledProcessError as e:
            log.error(f"today.ics update failed: {e}")

        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run full ICS service (publisher + today.ics updater)"
    )

    parser.add_argument("--config", default="./config.json")
    parser.add_argument("--publish-dir", default="./published_ics")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--port", type=int, default=5333)
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()
    log = Logger(verbose=args.verbose)

    log.info("Starting full ICS service")

    # --- command: publish server ---
    publish_cmd = [
        sys.executable,
        "publish_ics_server.py",
        "--config", args.config,
        "--publish-dir", args.publish_dir,
        "--interval", str(args.interval),
        "--days", str(args.days),
        "--port", str(args.port),
    ]
    if args.verbose:
        publish_cmd.append("--verbose")

    # --- command: today updater ---
    today_cmd = [
        sys.executable,
        "update_today_ics.py",
        "--config", args.config,
        "--publish-dir", args.publish_dir,
        "--mode", "copy",
    ]
    if args.verbose:
        today_cmd.append("--verbose")

    # --- thread 1: publisher (includes HTTP server) ---
    t1 = threading.Thread(
        target=run_publish_server,
        args=(publish_cmd, log),
        daemon=True,
    )

    # --- thread 2: today updater ---
    t2 = threading.Thread(
        target=run_today_updater,
        args=(today_cmd, args.interval, log),
        daemon=True,
    )

    t1.start()
    time.sleep(2)  # give server a bit time
    t2.start()

    log.ok("All services started")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log.info("Shutting down")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())