from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import traceback
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .aliases import (
    find_today_ics_candidates,
    generate_today_ics,
    select_today_ics,
    select_today_ics_from_post_metadata,
    today_date_str,
)
from .config import config_exists, create_default_config, load_config, save_config
from .exceptions import ConfigError
from .debug_report import sanitize_config, write_recent_run_snapshot
from .fetcher import fetch_post, normalize_post_date
from .health import run_health_check
from .ics import generate_ics
from .ics_exporter import write_post_ics
from .models import LogEntry
from .parser import parse_post_content
from .source_metadata import attach_source_metadata
from .service import run_today_pipeline, export_post_to_ics, publish_once, run_service_loop, update_today_ics
from . import service_mode as _service_mode
from .setup_wizard import run_setup_wizard, select_post_id
from .sync import run_caldav_sync
from .timeline import apply_timeline
from .operations import config_get, config_set, edit_config_file, write_runtime_log
from .service import list_posts
from .validators import (
    validate_caldav_config,
    validate_custom_parsing_patterns,
    validate_dependencies,
    validate_output_dir_readonly,
    validate_output_dir_writable,
    validate_python_path,
    validate_rest_credentials,
    validate_wordpress_path,
    validate_wp_cli,
)

_DRY_RUN_MARKER_FILE = "caldav_dry_run_marker.json"
_DRY_RUN_MARKER_MAX_AGE = timedelta(hours=24)


def _dry_run_marker_path(config) -> Path:
    return Path(config.logs_dir) / _DRY_RUN_MARKER_FILE


def _config_fingerprint(config) -> str:
    data = asdict(config)

    credential_identity = {
        "username": data.get("caldav_username", ""),
        "password_sha256": hashlib.sha256(str(data.get("caldav_password", "")).encode("utf-8")).hexdigest(),
    }
    relevant = {
        "timezone": data.get("timezone", "UTC"),
        "default_last_event_minutes": data.get("default_last_event_minutes"),
        "auto_cross_midnight": data.get("auto_cross_midnight"),
        "allow_empty_summary": data.get("allow_empty_summary"),
        "save_ignored_blocks": data.get("save_ignored_blocks"),
        "custom_parsing_patterns": data.get("custom_parsing_patterns", []),
        "caldav_url": data.get("caldav_url", ""),
        "caldav_credentials": credential_identity,
        "caldav_uid_domain": data.get("caldav_uid_domain", ""),
        "caldav_index_path": data.get("caldav_index_path", ""),
        "caldav_deletion_mode": data.get("caldav_deletion_mode", ""),
        "verify_ssl": data.get("verify_ssl", True),
        "wordpress_mode": data.get("wordpress_mode", ""),
        "wp_path": data.get("wp_path", ""),
        "wp_cli_path": data.get("wp_cli_path", ""),
        "base_url": data.get("base_url", ""),
        "username": data.get("username", ""),
    }
    payload = json.dumps(relevant, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_dry_run_marker(config, result: dict) -> Path:
    marker_path = _dry_run_marker_path(config)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": "caldav_dry_run_success",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_fingerprint": _config_fingerprint(config),
        "source_snapshot": {
            "changed_posts": result.get("changed_posts"),
            "index_path": result.get("index_path"),
        },
    }
    marker_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return marker_path


def _dry_run_marker_compatibility(config) -> tuple[bool, str]:
    marker_path = _dry_run_marker_path(config)
    if not marker_path.exists():
        return False, "No recent dry-run proof found. Run option 6 first."
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except Exception:
        return False, "Dry-run marker is unreadable. Run option 6 to refresh it."
    created_raw = payload.get("created_at_utc")
    if not isinstance(created_raw, str):
        return False, "Dry-run marker is invalid. Run option 6 to regenerate it."
    try:
        created_at = datetime.fromisoformat(created_raw)
    except ValueError:
        return False, "Dry-run marker timestamp is invalid. Run option 6."
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)
    if age > _DRY_RUN_MARKER_MAX_AGE:
        return False, "Dry-run marker is stale (>24h). Run option 6 again, then retry real sync."
    expected = _config_fingerprint(config)
    if payload.get("config_fingerprint") != expected:
        return False, "Dry-run marker is incompatible with current config. Run option 6 to refresh."
    return True, "CalDAV sync is ready."


def _print_validation(config, *, require_caldav: bool = False, include_caldav: bool = True) -> bool:
    checks = []
    checks.extend(validate_dependencies())
    checks.append(validate_custom_parsing_patterns(config))
    checks.append(validate_python_path(config.python_path))
    checks.append(validate_output_dir_readonly(config.output_dir))
    checks.append(validate_output_dir_readonly(config.error_dir))
    checks.append(validate_output_dir_readonly(config.logs_dir))
    if config.wordpress_mode == "wpcli":
        checks.append(validate_wp_cli(config.wp_cli_path))
        checks.append(validate_wordpress_path(config.wp_path))
    else:
        checks.append(validate_rest_credentials(config.base_url, config.username, config.app_password, config.verify_ssl))
    if include_caldav:
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


def _doctor(config, *, require_caldav: bool = False) -> bool:
    print("== Core checks ==")
    core_ok = _print_validation(config, require_caldav=False, include_caldav=False)
    if require_caldav:
        print("== CalDAV checks (required) ==")
        c = validate_caldav_config(
            config.caldav_url,
            config.caldav_username,
            config.caldav_password,
            config.caldav_uid_domain,
            config.caldav_index_path,
            required=True,
        )
        print(f"{'[OK]' if c.ok else '[ERROR]'} {c.name}: {c.message}")
        return core_ok and c.ok
    print("== CalDAV checks (optional) ==")
    c = validate_caldav_config(
        config.caldav_url,
        config.caldav_username,
        config.caldav_password,
        config.caldav_uid_domain,
        config.caldav_index_path,
        required=False,
    )
    print(f"{'[OK]' if c.ok else '[WARN]'} {c.name}: {c.message}")
    return core_ok




def _caldav_status(config, dry_run_seen: bool) -> tuple[str, str]:
    if not config.caldav_url.strip():
        return "not configured", "CalDAV is not configured. Configure CalDAV first or use local ICS mode."
    if not config.caldav_username.strip() or not config.caldav_password.strip():
        return "incomplete", "CalDAV configuration is incomplete."
    marker_ok, marker_message = _dry_run_marker_compatibility(config)
    if not marker_ok and dry_run_seen:
        return "needs test", "Session dry-run seen, but persisted marker is missing/stale. Run Dry-run CalDAV sync."
    if not marker_ok:
        return "needs test", marker_message
    return "ready", marker_message


def _print_health_summary(config, health: dict, dry_run_seen: bool) -> None:
    def _section_status(section: str) -> str:
        items = health.get(section, [])
        statuses = {i.get("status") for i in items}
        if "error" in statuses:
            return "error"
        if "warning" in statuses:
            return "warning"
        return "OK"

    caldav_state, next_step = _caldav_status(config, dry_run_seen)
    print("\n== Health summary ==")
    print(f"WordPress: {_section_status('wordpress_runtime')}")
    print(f"Parser: {_section_status('parser_runtime')}")
    print(f"Local ICS: {_section_status('ics_runtime')}")
    print(f"CalDAV: {caldav_state}")
    print(f"Next step: {next_step}")


def _select_post_interactively(config):
    posts = list_posts(config)
    if not posts:
        print('No posts found.')
        return None
    for i, post in enumerate(posts, 1):
        print(f"  {i}) {post['date']} [{post['status']}] {post['title']} (ID: {post['id']})")
    raw = input('Select post number (blank=1): ').strip()
    if not raw:
        idx = 1
    elif raw.isdigit():
        idx = int(raw)
    else:
        print("Invalid selection. Please enter a number.")
        return None
    if idx < 1 or idx > len(posts):
        print('Invalid selection.')
        return None
    return posts[idx-1]

def _validate_update_today(config) -> bool:
    output_check = validate_output_dir_readonly(config.output_dir)
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


def _prepare_entries_for_export(entries: list[LogEntry], mode: str) -> list[LogEntry]:
    if mode == "include":
        return entries
    review_entries = [entry for entry in entries if entry.status == "needs_review"]
    if mode == "skip":
        return [entry for entry in entries if entry.status != "needs_review"]
    if review_entries:
        raise RuntimeError(f"Refusing to export {len(review_entries)} entries with status=needs_review.")
    return entries


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
    p_parse.add_argument("--verbose", action="store_true")

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
    p_run_service.add_argument("--once", action="store_true", help="Run one publish cycle without starting the HTTP server.")

    p_sync_caldav = sub.add_parser("sync-caldav")
    p_sync_caldav.add_argument("--config", default="./config.json")
    p_sync_caldav.add_argument("--dry-run", action="store_true")
    p_sync_caldav.add_argument("--apply", action="store_true")
    p_sync_caldav.add_argument("--force-real-sync", action="store_true")
    p_sync_caldav.add_argument("--debug", action="store_true")

    p_doctor = sub.add_parser("doctor")
    p_doctor.add_argument("--config", default="./config.json")
    p_doctor.add_argument("--require-caldav", action="store_true")
    p_doctor.add_argument("--full", action="store_true")
    p_doctor.add_argument("--test-caldav-write", action="store_true")

    p_config = sub.add_parser("config")
    p_config.add_argument("--config", default="./config.json")
    p_config_sub = p_config.add_subparsers(dest="config_command", required=True)
    p_config_get = p_config_sub.add_parser("get")
    p_config_get.add_argument("key")
    p_config_set = p_config_sub.add_parser("set")
    p_config_set.add_argument("key")
    p_config_set.add_argument("value")
    p_config_sub.add_parser("edit")

    sub.add_parser("app").add_argument("--config", default="./config.json")

    return parser



def _export_post_to_ics_via_service(config, post_id: int, verbose: bool = False):
    """Call the service-layer export flow, preserving legacy test monkeypatch seams."""
    _service_mode.fetch_post = fetch_post
    _service_mode.normalize_post_date = normalize_post_date
    _service_mode.parse_post_content = parse_post_content
    _service_mode.attach_source_metadata = attach_source_metadata
    _service_mode.write_post_ics = write_post_ics
    return export_post_to_ics(config, post_id, verbose=verbose)


def _update_today_ics_via_service(config, mode: str = "copy", post_id: int | None = None, verbose: bool = False):
    """Call the service-layer today alias flow, preserving legacy test monkeypatch seams."""
    _service_mode.today_date_str = today_date_str
    _service_mode.find_today_ics_candidates = find_today_ics_candidates
    _service_mode.select_today_ics = select_today_ics
    _service_mode.generate_today_ics = generate_today_ics
    return update_today_ics(config, mode=mode, post_id=post_id, verbose=verbose)

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
        if args.command == "app" and sys.stdin.isatty():
            print(f"Config does not exist: {args.config}")
            choice = input("Create config now? (wizard/default/cancel): ").strip().lower()
            if choice == "wizard":
                run_setup_wizard(args.config)
            elif choice == "default":
                save_config(create_default_config(), args.config)
                print(f"Created default config: {args.config}")
            else:
                return 2
        else:
            print(f"Config does not exist: {args.config}")
            return 2

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"[ERROR] config: {exc}")
        return 2

    if args.command == "validate-config":
        return 0 if _print_validation(config) else 1
    if args.command == "doctor":
        write_runtime_log(config, "doctor", "running environment checks")
        if args.full:
            report = run_health_check(
                config,
                full=True,
                test_caldav_write=args.test_caldav_write,
                require_caldav=args.require_caldav,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            has_error = any(item["status"] == "error" for section in report.values() for item in section)
            return 1 if has_error else 0
        return 0 if _doctor(config, require_caldav=args.require_caldav) else 1
    if args.command == "config":
        try:
            if args.config_command == "get":
                print(json.dumps({"key": args.key, "value": config_get(args.config, args.key)}, ensure_ascii=False))
                return 0
            if args.config_command == "set":
                config_set(args.config, args.key, args.value)
                print(json.dumps({"updated": args.key}, ensure_ascii=False))
                return 0
            if args.config_command == "edit":
                edit_config_file(args.config)
                return 0
        except Exception as exc:
            print(f"[ERROR] {exc}")
            return 2
    if args.command == "app":
        if not sys.stdin.isatty():
            print("Interactive app requires a TTY.")
            return 2
        health = run_health_check(config, full=True, test_caldav_write=False)
        dry_run_seen = False
        _print_health_summary(config, health, dry_run_seen)
        if any(i.get("fixable") for section in health.values() for i in section if i.get("status") in {"warning", "error"}):
            if input("Run repair wizard now? (y/N): ").strip().lower() == "y":
                run_setup_wizard(args.config)
                try:
                    config = load_config(args.config)
                except ConfigError as exc:
                    print(f"[ERROR] config: {exc}")
                    return 2
        while True:
            print("\n== wp_log_parser app ==")
            print("1) Run runtime health check")
            print("2) Repair configuration")
            print("3) Show sanitized config")
            print("4) List recent posts")
            print("5) Preview parsed timeline")
            print("6) Dry-run CalDAV sync")
            print("7) Real CalDAV sync")
            print("8) View last run report")
            print("9) View last health report")
            print("10) Generate local ICS files")
            print("11) Update today.ics")
            print("12) Start local ICS service (runs until Ctrl+C)")
            print("13) Show detailed health JSON")
            print("0) exit")
            try:
                choice = input("Select: ").strip()
                if choice == "1":
                    health = run_health_check(config, full=True)
                    _print_health_summary(config, health, dry_run_seen)
                elif choice == "2":
                    run_setup_wizard(args.config); config = load_config(args.config)
                elif choice == "3":
                    print(json.dumps(sanitize_config(config), ensure_ascii=False, indent=2))
                elif choice == "4":
                    posts = list_posts(config)
                    if not posts:
                        print("No recent posts found.")
                    else:
                        print("\nRecent posts (newest first):")
                        for idx, post in enumerate(posts, 1):
                            print(f"  {idx}) {post['date']} [{post['status']}] {post['title']} (ID: {post['id']})")
                        if input("View detailed JSON? (y/N): ").strip().lower() == "y":
                            print(json.dumps(posts, ensure_ascii=False, indent=2))
                elif choice == "5":
                    chosen = _select_post_interactively(config)
                    if not chosen: continue
                    post = fetch_post(config, int(chosen['id']))
                    parsed = parse_post_content(post.post_content, normalize_post_date(post.post_date), config)
                    attach_source_metadata(parsed, post)
                    print(f"Previewing: {chosen['title']} ({chosen['date']}) [{chosen['status']}]")
                    for e in parsed.entries:
                        print(f"- start={e.start_time} end={e.end_time or '-'} summary={e.summary} status={e.status}")
                    print(f"ignored_blocks={len(parsed.ignored_blocks)} warnings={len(parsed.warnings)}")
                    if input('View detailed JSON? (y/N): ').strip().lower()=='y':
                        print(json.dumps(parsed.to_dict(include_ignored=True), ensure_ascii=False, indent=2))
                elif choice == "6":
                    state,_ = _caldav_status(config, dry_run_seen)
                    if state == "not configured":
                        print("CalDAV is not configured. Configure CalDAV first or use local ICS mode."); continue
                    if state == "incomplete":
                        print("CalDAV configuration is incomplete."); continue
                    result = run_caldav_sync(config, dry_run=True)
                    dry_run_seen = True
                    marker_path = _write_dry_run_marker(config, result)
                    print(f"Dry-run marker saved: {marker_path}")
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                elif choice == "7":
                    state,_ = _caldav_status(config, dry_run_seen)
                    if state == "not configured":
                        print("CalDAV is not configured. Configure CalDAV first or use local ICS mode."); continue
                    if state == "incomplete":
                        print("CalDAV configuration is incomplete."); continue
                    marker_ok, marker_msg = _dry_run_marker_compatibility(config)
                    if not marker_ok:
                        print(f"Real sync blocked: {marker_msg} Remediation: run option 6, then retry option 7."); continue
                    if input("Type YES to run real sync: ").strip()=="YES":
                        print(json.dumps(run_caldav_sync(config, dry_run=False), ensure_ascii=False, indent=2))
                elif choice == "8":
                    last_run = Path(config.error_dir) / "last_run.json"; print(last_run.read_text(encoding='utf-8') if last_run.exists() else 'No last run report found.')
                elif choice == "9":
                    last_health = Path(config.error_dir) / "last_health_report.json"; print(last_health.read_text(encoding='utf-8') if last_health.exists() else 'No last health report found.')
                elif choice == "10":
                    days_raw = input("Days to publish (default 7): ").strip()
                    days = int(days_raw) if days_raw.isdigit() else 7
                    result = publish_once(config, days=days, verbose=True)
                    print(f"Published local ICS files for {days} day(s).")
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                elif choice == "11":
                    try:
                        preferred_post_id = None
                        today = today_date_str(config.timezone)
                        candidates = find_today_ics_candidates(Path(config.output_dir), today)
                        if len(candidates) > 1:
                            metadata_choice = select_today_ics_from_post_metadata(candidates, list_posts(config))
                            if metadata_choice is not None:
                                match = re.match(r"^\d{4}-\d{2}-\d{2}_post_(\d+)_.*\.ics$", metadata_choice.name)
                                if match:
                                    preferred_post_id = int(match.group(1))
                            print("Multiple today.ics source candidates found:")
                            for idx, candidate in enumerate(candidates, 1):
                                print(f"  {idx}) {candidate.name}")
                            if preferred_post_id is not None:
                                print(f"Suggested by post metadata: post ID {preferred_post_id}")
                            selection = input("Choose candidate number (Enter for suggested/latest): ").strip()
                            if selection.isdigit():
                                selected_index = int(selection) - 1
                                if 0 <= selected_index < len(candidates):
                                    selected_path = candidates[selected_index]
                                    selected_match = re.match(r"^\d{4}-\d{2}-\d{2}_post_(\d+)_.*\.ics$", selected_path.name)
                                    if selected_match:
                                        preferred_post_id = int(selected_match.group(1))
                        target = generate_today_ics(config.output_dir, config.timezone, preferred_post_id=preferred_post_id, mode="copy")
                        print(f"Updated today.ics: {target}")
                    except FileNotFoundError:
                        print("No ICS file for today exists yet. Generate local ICS files first.")
                elif choice == "12":
                    print(f"Subscription URL: {config.ics_base_url.rstrip('/')}/today.ics")
                    host = input("Host (default 127.0.0.1): ").strip() or "127.0.0.1"
                    port_raw = input("Port (default 5333): ").strip()
                    interval_raw = input("Interval seconds (default 300): ").strip()
                    days_raw = input("Days window (default 7): ").strip()
                    run_service_loop(
                        config,
                        days=int(days_raw) if days_raw.isdigit() else 7,
                        interval_seconds=int(interval_raw) if interval_raw.isdigit() else 300,
                        host=host,
                        port=int(port_raw) if port_raw.isdigit() else 5333,
                        verbose=True,
                    )
                elif choice == "13":
                    print(json.dumps(run_health_check(config, full=True), ensure_ascii=False, indent=2))
                elif choice == "0":
                    return 0
                else:
                    print("Unknown option.")
            except KeyboardInterrupt:
                print("Operation cancelled.")
            except Exception as exc:
                print(f"[ERROR] {exc}")

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
        post = fetch_post(config, post_id)
        print(json.dumps({"post_id": post.post_id, "post_content": post.post_content}, ensure_ascii=False, indent=2))
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
        parsed = parse_post_content(post.post_content, post_date, config, verbose=args.verbose)
        attach_source_metadata(parsed, post)
        getattr(parsed, "refresh_ics_preview", lambda _timezone: "")(config.timezone)
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
        typed_entries = [
            LogEntry(
                date=item["date"],
                start_time=item["start_time"],
                end_time=item.get("end_time"),
                summary=item.get("summary", ""),
                raw=item.get("raw", ""),
                status=item.get("status", "needs_review"),
                source_id=item.get("source_id"),
                start_dt=datetime.fromisoformat(item["start_dt"]) if item.get("start_dt") else None,
                end_dt=datetime.fromisoformat(item["end_dt"]) if item.get("end_dt") else None,
            )
            for item in entries
        ]
        export_entries = _prepare_entries_for_export(typed_entries, config.review_entry_export_mode)
        print(generate_ics(export_entries, timezone=config.timezone))
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
            attach_source_metadata(parsed, post)
            getattr(parsed, "refresh_ics_preview", lambda _timezone: "")(config.timezone)
            warnings = getattr(parsed, "warnings", [])
            if warnings:
                print(f"[WARN] Timeline warnings: {len(warnings)}")
                for warn in warnings:
                    print(f"[WARN] {warn.reason}: {warn.message}")
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
            export_entries = _prepare_entries_for_export(parsed.entries, config.review_entry_export_mode)
            out_path = write_post_ics(post, export_entries, config.output_dir, config.timezone)
            result = {
                "post_id": post.post_id,
                "title": post.title,
                "post_date": post.post_date,
                "output_file": str(out_path),
                "entry_count": len(export_entries),
                "ignored_block_count": len(parsed.ignored_blocks),
                "warning_count": len(warnings),
            }
            public_result = {k: v for k, v in result.items() if k not in {"entries", "ignored_blocks"}}
            _write_snapshot_best_effort(
                error_dir=config.error_dir,
                command=args.command,
                success=True,
                config=config,
                summary=public_result,
                processed_post_ids=[int(result["post_id"])],
            )
            if _debug_enabled(args):
                print(f"[DEBUG] processed_post_ids: {[int(result['post_id'])]}")
                print(f"[DEBUG] event_count: {len(result.get('entries', []))}")
            print(json.dumps(public_result, ensure_ascii=False, indent=2))
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
            for path in (config.output_dir, config.error_dir, config.logs_dir):
                dir_check = validate_output_dir_writable(path)
                if not dir_check.ok:
                    print(f"[ERROR] {dir_check.name}: {dir_check.message}")
                    return 1
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
            result = _update_today_ics_via_service(config, mode=args.mode, post_id=args.post_id, verbose=args.verbose)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            print(f"[ERROR] {exc}")
            return 1

    if args.command == "run-ics-service":
        try:
            if args.once:
                result = publish_once(config, days=args.days, verbose=args.verbose)
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                run_service_loop(
                    config=config,
                    days=args.days,
                    interval_seconds=args.interval,
                    host=args.host,
                    port=args.port,
                    verbose=args.verbose,
                )
            return 0
        except KeyboardInterrupt:
            print("[INFO] Service interrupted. Shutting down cleanly.")
            return 0

    if args.command == "sync-caldav":
        if args.dry_run and args.apply:
            print("Cannot combine --dry-run and --apply.")
            return 2
        debug_events = [] if _debug_enabled(args) else None
        dry_run = args.dry_run or not args.apply
        if _debug_enabled(args):
            _print_debug_header(args.command, args.config, config, {"dry_run": dry_run, "force_real_sync": args.force_real_sync})
        try:
            if not dry_run and not args.force_real_sync:
                marker_ok, marker_msg = _dry_run_marker_compatibility(config)
                if not marker_ok:
                    print(f"Real sync blocked: {marker_msg} Use --force-real-sync to override deliberately.")
                    return 1
            write_runtime_log(config, "sync-caldav", "starting sync", {"dry_run": dry_run})
            print("[PHASE] source: listing WordPress posts")
            result = run_caldav_sync(config, dry_run=dry_run, debug_events=debug_events)
            if dry_run:
                marker_path = _write_dry_run_marker(config, result)
                print(f"Dry-run marker saved: {marker_path}")
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
                dry_run=dry_run,
                summary=result,
                changed_post_count=result.get("changed_posts"),
                caldav_counts=caldav_counts,
                index_path=result.get("index_path"),
                debug_operations=debug_events,
            )
            if _debug_enabled(args):
                print(f"[DEBUG] dry_run: {dry_run}")
                print(f"[DEBUG] event_operation_counts: {caldav_counts}")
                print(f"[DEBUG] changed_post_count: {result.get('changed_posts')}")
                print(f"[DEBUG] index_path: {result.get('index_path')}")
            write_runtime_log(config, "sync-caldav", "sync completed", caldav_counts | {"changed_posts": result.get("changed_posts", 0)})
            print("[PHASE] complete: sync finished")
            print(f"[COUNTS] created={caldav_counts['created']} updated={caldav_counts['updated']} deleted={caldav_counts['deleted']} cancelled={caldav_counts['cancelled']} skipped={caldav_counts['skipped']} changed_posts={result.get('changed_posts', 0)}")
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
                    dry_run=dry_run,
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
