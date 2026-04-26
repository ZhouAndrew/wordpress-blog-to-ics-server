from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from .aliases import find_today_ics_candidates, generate_today_ics, select_today_ics, today_date_str
from .config import config_exists, create_default_config, load_config, save_config
from .debug_report import sanitize_config, write_recent_run_snapshot
from .fetcher import fetch_post, normalize_post_date
from .ics import generate_ics
from .ics_exporter import write_post_ics
from .models import LogEntry
from .parser import parse_post_content
from .service import fetch_post as fetch_post_legacy, run_today_pipeline
from .service_mode import publish_once, run_service_loop
from .setup_wizard import run_setup_wizard, select_post_id
from .sync import run_caldav_sync
from .timeline import apply_timeline
from .validators import (
    validate_caldav_config,
    validate_dependencies,
    validate_output_dir,
    validate_python_path,
    validate_rest_credentials,
    validate_wordpress_path,
    validate_wp_cli,
)


def _print_validation(config, *, require_caldav: bool = False) -> bool:
    checks = []
    checks.extend(validate_dependencies())
    checks.append(validate_python_path(config.python_path))
    checks.append(validate_output_dir(config.output_dir))
    checks.append(validate_output_dir(config.error_dir))
    if config.wordpress_mode == "wpcli":
        checks.append(validate_wp_cli(config.wp_cli_path))
        checks.append(validate_wordpress_path(config.wp_path))
    else:
        checks.append(validate_rest_credentials(config.base_url, config.username, config.app_password, config.verify_ssl))
    checks.append(
        validate_caldav_config(
            config.caldav_url,
            config.caldav_username,
            config.caldav_password,
            config.caldav_uid_domain,
            config.caldav_index_path,
            required=require_caldav,
        )
    )

    ok = True
    for c in checks:
        status = "[OK]" if c.ok else "[ERROR]"
        print(f"{status} {c.name}: {c.message}")
        if not c.ok:
            ok = False
    return ok


def _validate_update_today(config) -> bool:
    output_check = validate_output_dir(config.output_dir)
    status = "[OK]" if output_check.ok else "[ERROR]"
    print(f"{status} {output_check.name}: {output_check.message}")
    if not output_check.ok:
        return False

    try:
        today_date_str(config.timezone)
    except Exception as exc:
        print(f"[ERROR] timezone: {exc}")
        return False

    print(f"[OK] timezone: {config.timezone}")
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wp_log_parser")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-config")
    p_init.add_argument("--config", default="./config.json")
    p_init.add_argument("--wizard", action="store_true")

    p_validate = sub.add_parser("validate-config")
    p_validate.add_argument("--config", default="./config.json")

    p_fetch = sub.add_parser("fetch-post")
    p_fetch.add_argument("--config", default="./config.json")
    p_fetch.add_argument("--post-id", type=int)
    p_fetch.add_argument("--select-post-id", action="store_true", help="Interactively select a post ID from recent posts.")

    p_parse = sub.add_parser("parse-post")
    p_parse.add_argument("--config", default="./config.json")
    p_parse.add_argument("--post-id", type=int)
    p_parse.add_argument("--select-post-id", action="store_true", help="Interactively select a post ID from recent posts.")

    p_export = sub.add_parser("export-ics")
    p_export.add_argument("--config", default="./config.json")
    p_export.add_argument("--entries-json", required=True)

    p_run = sub.add_parser("run-today")
    p_run.add_argument("--config", default="./config.json")
    p_run.add_argument("--debug", action="store_true")

    p_post_to_ics = sub.add_parser("post-to-ics")
    p_post_to_ics.add_argument("--config", default="./config.json")
    p_post_to_ics.add_argument("--post-id", type=int, required=True)
    p_post_to_ics.add_argument("--verbose", action="store_true")
    p_post_to_ics.add_argument("--debug", action="store_true")

    p_publish_ics = sub.add_parser("publish-ics")
    p_publish_ics.add_argument("--config", default="./config.json")
    p_publish_ics.add_argument("--days", type=int, required=True)
    p_publish_ics.add_argument("--verbose", action="store_true")
    p_publish_ics.add_argument("--debug", action="store_true")

    p_update_today = sub.add_parser("update-today-ics")
    p_update_today.add_argument("--config", default="./config.json")
    p_update_today.add_argument("--mode", choices=["copy", "symlink"], default="copy")
    p_update_today.add_argument("--post-id", type=int)
    p_update_today.add_argument("--verbose", action="store_true")

    p_run_service = sub.add_parser("run-ics-service")
    p_run_service.add_argument("--config", default="./config.json")
    p_run_service.add_argument("--days", type=int, default=7)
    p_run_service.add_argument("--interval", type=int, default=60)
    p_run_service.add_argument("--host", default="127.0.0.1")
    p_run_service.add_argument("--port", type=int, default=5333)
    p_run_service.add_argument("--verbose", action="store_true")

    p_sync_caldav = sub.add_parser("sync-caldav")
    p_sync_caldav.add_argument("--config", default="./config.json")
    p_sync_caldav.add_argument("--dry-run", action="store_true")
    p_sync_caldav.add_argument("--debug", action="store_true")

    return parser


def _print_debug_header(command: str, config_path: str, config, extras: dict[str, object] | None = None) -> None:
    print(f"[DEBUG] command: {command}")
    print(f"[DEBUG] config_path: {config_path}")
    print(f"[DEBUG] config_summary: {json.dumps(sanitize_config(config), ensure_ascii=False, sort_keys=True)}")
    print(f"[DEBUG] wordpress_mode: {config.wordpress_mode}")
    print(f"[DEBUG] timezone: {config.timezone}")
    print(f"[DEBUG] output_dir: {config.output_dir}")
    print(f"[DEBUG] error_dir: {config.error_dir}")
    print(f"[DEBUG] caldav_deletion_mode: {config.caldav_deletion_mode}")
    if extras:
        for key, value in extras.items():
            print(f"[DEBUG] {key}: {value}")


def _debug_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "debug", False))


def _write_snapshot_best_effort(**kwargs):
    try:
        return write_recent_run_snapshot(**kwargs)
    except Exception as exc:
        print(f"[WARN] Failed to write run snapshot: {exc}")
        return None, None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init-config":
        if args.wizard:
            run_setup_wizard(args.config)
        else:
            save_config(create_default_config(), args.config)
            print(f"Created default config: {args.config}")
        return 0

    if not config_exists(args.config):
        print(f"Config does not exist: {args.config}")
        return 2

    config = load_config(args.config)

    if args.command == "validate-config":
        return 0 if _print_validation(config) else 1

    if args.command == "update-today-ics":
        if not _validate_update_today(config):
            print("Critical validation errors found. Aborting execution.")
            return 1
    else:
        if args.command == "sync-caldav":
            ok = _print_validation(config, require_caldav=True)
        else:
            ok = _print_validation(config)
        if not ok:
            print("Critical validation errors found. Aborting execution.")
            return 1

    if args.command == "fetch-post":
        if args.select_post_id and args.post_id is not None:
            print("Cannot use --select-post-id and --post-id together.")
            return 2
        if not args.select_post_id and args.post_id is None:
            print("Either --post-id or --select-post-id is required.")
            return 2
        post_id = args.post_id
        if args.select_post_id:
            if not sys.stdin.isatty():
                print("Interactive post selection requires a TTY.")
                return 2
            post_id = select_post_id(config)
        post_id, content = fetch_post_legacy(config, post_id)
        print(json.dumps({"post_id": post_id, "post_content": content}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "parse-post":
        if args.select_post_id and args.post_id is not None:
            print("Cannot use --select-post-id and --post-id together.")
            return 2
        if not args.select_post_id and args.post_id is None:
            print("Either --post-id or --select-post-id is required.")
            return 2
        post_id = args.post_id
        if args.select_post_id:
            if not sys.stdin.isatty():
                print("Interactive post selection requires a TTY.")
                return 2
            post_id = select_post_id(config)
        post = fetch_post(config, post_id)
        post_date = normalize_post_date(post.post_date)
        parsed = parse_post_content(post.post_content, post_date, config)
        parsed.post_id = post.post_id
        print(json.dumps(parsed.to_dict(include_ignored=True), ensure_ascii=False, indent=2))
        return 0

    if args.command == "export-ics":
        entries = json.loads(Path(args.entries_json).read_text(encoding="utf-8"))
        if entries and any(not item.get("start_dt") for item in entries):
            timeline_entries, _ = apply_timeline(
                [
                    LogEntry(
                        date=item["date"],
                        start_time=item["start_time"],
                        end_time=item.get("end_time"),
                        summary=item.get("summary", ""),
                        raw=item.get("raw", ""),
                        status=item.get("status", "needs_review"),
                        source_id=item.get("source_id"),
                    )
                    for item in entries
                ],
                config,
            )
            entries = [entry.to_dict() for entry in timeline_entries]
        print(generate_ics(entries, timezone=config.timezone))
        return 0

    if args.command == "run-today":
        if _debug_enabled(args):
            _print_debug_header(args.command, args.config, config)
        try:
            result = run_today_pipeline(config)
            _write_snapshot_best_effort(
                error_dir=config.error_dir,
                command=args.command,
                success=True,
                config=config,
                summary=result,
                processed_post_ids=[int(result["post_id"])] if result.get("post_id") is not None else None,
            )
            if _debug_enabled(args):
                print(f"[DEBUG] processed_post_ids: {result.get('post_id')}")
                print(f"[DEBUG] event_count: {len(result.get('entries', []))}")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            if _debug_enabled(args):
                print("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            try:
                last_run_path, timestamped_path = write_recent_run_snapshot(
                    error_dir=config.error_dir,
                    command=args.command,
                    success=False,
                    config=config,
                    error=exc,
                )
                print(f"Debug report written to: {last_run_path}")
                if timestamped_path is not None:
                    print(f"Debug report written to: {timestamped_path}")
            except Exception as snapshot_exc:
                print(f"[WARN] Failed to write debug report: {snapshot_exc}")
            print(f"[ERROR] {exc}")
            return 1

    if args.command == "post-to-ics":
        if _debug_enabled(args):
            _print_debug_header(args.command, args.config, config, {"post_ids": [args.post_id]})
        try:
            post = fetch_post(config, args.post_id)
            post_date = normalize_post_date(post.post_date)
            parsed = parse_post_content(post.post_content, post_date, config, verbose=args.verbose)
            if not parsed.entries:
                print("No valid timed log entries found in post.")
                last_run_path, timestamped_path = write_recent_run_snapshot(
                    error_dir=config.error_dir,
                    command=args.command,
                    success=False,
                    config=config,
                    summary={"post_id": post.post_id, "entry_count": 0},
                    processed_post_ids=[post.post_id],
                    error=RuntimeError("No valid timed log entries found in post."),
                )
                print(f"Debug report written to: {last_run_path}")
                if timestamped_path is not None:
                    print(f"Debug report written to: {timestamped_path}")
                return 1
            out_path = write_post_ics(post, parsed.entries, config.output_dir, config.timezone)
            result = {
                "post_id": post.post_id,
                "title": post.title,
                "post_date": post.post_date,
                "output_file": str(out_path),
                "entry_count": len(parsed.entries),
                "ignored_block_count": len(parsed.ignored_blocks),
            }
            _write_snapshot_best_effort(
                error_dir=config.error_dir,
                command=args.command,
                success=True,
                config=config,
                summary=result,
                processed_post_ids=[post.post_id],
            )
            if _debug_enabled(args):
                print(f"[DEBUG] processed_post_ids: {[post.post_id]}")
                print(f"[DEBUG] event_count: {len(parsed.entries)}")
            if args.verbose:
                print(f"[OK] Wrote ICS file: {out_path}")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            if _debug_enabled(args):
                print("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            try:
                last_run_path, timestamped_path = write_recent_run_snapshot(
                    error_dir=config.error_dir,
                    command=args.command,
                    success=False,
                    config=config,
                    processed_post_ids=[args.post_id],
                    error=exc,
                )
                print(f"Debug report written to: {last_run_path}")
                if timestamped_path is not None:
                    print(f"Debug report written to: {timestamped_path}")
            except Exception as snapshot_exc:
                print(f"[WARN] Failed to write debug report: {snapshot_exc}")
            print(f"[ERROR] {exc}")
            return 1

    if args.command == "publish-ics":
        if _debug_enabled(args):
            _print_debug_header(args.command, args.config, config, {"days": args.days})
        try:
            result = publish_once(config, days=args.days, verbose=args.verbose)
            post_ids = [int(item["post_id"]) for item in result.get("items", []) if item.get("post_id") is not None]
            _write_snapshot_best_effort(
                error_dir=config.error_dir,
                command=args.command,
                success=True,
                config=config,
                summary=result,
                processed_post_ids=post_ids,
                index_path=result.get("index_json"),
            )
            if _debug_enabled(args):
                print(f"[DEBUG] processed_post_ids: {post_ids}")
                print(f"[DEBUG] event_operation_counts: published={result.get('published_count', 0)}")
                print(f"[DEBUG] index_path: {result.get('index_json')}")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            if _debug_enabled(args):
                print("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            try:
                last_run_path, timestamped_path = write_recent_run_snapshot(
                    error_dir=config.error_dir,
                    command=args.command,
                    success=False,
                    config=config,
                    error=exc,
                )
                print(f"Debug report written to: {last_run_path}")
                if timestamped_path is not None:
                    print(f"Debug report written to: {timestamped_path}")
            except Exception as snapshot_exc:
                print(f"[WARN] Failed to write debug report: {snapshot_exc}")
            print(f"[ERROR] {exc}")
            return 1

    if args.command == "update-today-ics":
        try:
            today = today_date_str(config.timezone)
            candidates = find_today_ics_candidates(Path(config.output_dir), today)
            selected = select_today_ics(candidates, args.post_id)
            target = generate_today_ics(
                config.output_dir,
                config.timezone,
                preferred_post_id=args.post_id,
                mode=args.mode,
            )
            if args.verbose:
                print(f"[OK] Selected today's ICS: {selected.name}")
                print(f"[OK] Updated alias: {target.name}")
            print(
                json.dumps(
                    {
                        "today": today,
                        "source_file": selected.name,
                        "target_file": target.name,
                        "mode": args.mode,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        except Exception as exc:
            print(f"[ERROR] {exc}")
            return 1

    if args.command == "run-ics-service":
        run_service_loop(
            config=config,
            days=args.days,
            interval_seconds=args.interval,
            host=args.host,
            port=args.port,
            verbose=args.verbose,
        )
        return 0

    if args.command == "sync-caldav":
        debug_events = [] if _debug_enabled(args) else None
        if _debug_enabled(args):
            _print_debug_header(args.command, args.config, config, {"dry_run": args.dry_run})
        try:
            result = run_caldav_sync(config, dry_run=args.dry_run, debug_events=debug_events)
            caldav_counts = {
                "created": int(result.get("created", 0)),
                "updated": int(result.get("updated", 0)),
                "deleted": int(result.get("deleted", 0)),
                "cancelled": int(result.get("cancelled", 0)),
                "skipped": int(result.get("skipped", 0)),
            }
            _write_snapshot_best_effort(
                error_dir=config.error_dir,
                command=args.command,
                success=True,
                config=config,
                dry_run=args.dry_run,
                summary=result,
                changed_post_count=result.get("changed_posts"),
                caldav_counts=caldav_counts,
                index_path=result.get("index_path"),
                debug_operations=debug_events,
            )
            if _debug_enabled(args):
                print(f"[DEBUG] dry_run: {args.dry_run}")
                print(f"[DEBUG] event_operation_counts: {caldav_counts}")
                print(f"[DEBUG] changed_post_count: {result.get('changed_posts')}")
                print(f"[DEBUG] index_path: {result.get('index_path')}")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            if _debug_enabled(args):
                print("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            try:
                last_run_path, timestamped_path = write_recent_run_snapshot(
                    error_dir=config.error_dir,
                    command=args.command,
                    success=False,
                    config=config,
                    dry_run=args.dry_run,
                    debug_operations=debug_events,
                    error=exc,
                )
                print(f"Debug report written to: {last_run_path}")
                if timestamped_path is not None:
                    print(f"Debug report written to: {timestamped_path}")
            except Exception as snapshot_exc:
                print(f"[WARN] Failed to write debug report: {snapshot_exc}")
            print(f"[ERROR] {exc}")
            return 1

    return 0
