from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .aliases import find_today_ics_candidates, generate_today_ics, select_today_ics, today_date_str
from .config import config_exists, create_default_config, load_config, save_config
from .fetcher import fetch_post, normalize_post_date
from .ics import generate_ics
from .ics_exporter import write_parsed_post_json, write_post_ics
from .parser import parse_post_content
from .service import fetch_post as fetch_post_legacy, run_today_pipeline
from .service_mode import publish_once, run_service_loop
from .setup_wizard import run_setup_wizard, select_post_id
from .validators import (
    validate_dependencies,
    validate_output_dir,
    validate_python_path,
    validate_rest_credentials,
    validate_wordpress_path,
    validate_wp_cli,
)


def _print_validation(config) -> bool:
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

    p_post_to_ics = sub.add_parser("post-to-ics")
    p_post_to_ics.add_argument("--config", default="./config.json")
    p_post_to_ics.add_argument("--post-id", type=int, required=True)
    p_post_to_ics.add_argument("--verbose", action="store_true")

    p_publish_ics = sub.add_parser("publish-ics")
    p_publish_ics.add_argument("--config", default="./config.json")
    p_publish_ics.add_argument("--days", type=int, required=True)
    p_publish_ics.add_argument("--verbose", action="store_true")

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

    return parser


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
        if not _print_validation(config):
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
        parsed = parse_post_content(post.post_content, normalize_post_date(post.post_date), config)
        parsed.post_id = post.post_id
        parsed.source_id = f"wp:{post.post_id}"
        print(json.dumps(parsed.to_dict(include_ignored=config.save_ignored_blocks), ensure_ascii=False, indent=2))
        return 0

    if args.command == "export-ics":
        entries = json.loads(Path(args.entries_json).read_text(encoding="utf-8"))
        print(generate_ics(entries, timezone=config.timezone))
        return 0

    if args.command == "run-today":
        print(json.dumps(run_today_pipeline(config), ensure_ascii=False, indent=2))
        return 0

    if args.command == "post-to-ics":
        post = fetch_post(config, args.post_id)
        post_date = normalize_post_date(post.post_date)
        parsed = parse_post_content(post.post_content, post_date, config, verbose=args.verbose)
        parsed.post_id = post.post_id
        parsed.source_id = f"wp:{post.post_id}"
        for entry in parsed.entries:
            entry.source_id = parsed.source_id
        parsed_dict = parsed.to_dict(include_ignored=config.save_ignored_blocks)
        parsed_dict["ics_preview"] = generate_ics(parsed_dict["entries"], timezone=config.timezone)
        if not parsed.entries:
            print("No valid timed log entries found in post.")
            return 1
        out_path = write_post_ics(post, parsed, config.output_dir, config.timezone)
        write_parsed_post_json(config.output_dir, out_path.name, parsed)
        if args.verbose:
            print(f"[OK] Wrote ICS file: {out_path}")
        print(
            json.dumps(
                {
                    "post_id": post.post_id,
                    "title": post.title,
                    "post_date": post.post_date,
                    "output_file": str(out_path),
                    "parsed_json_file": out_path.name.replace(".ics", ".parsed.json"),
                    "entry_count": len(parsed.entries),
                    "ignored_block_count": len(parsed.ignored_blocks),
                    "warning_count": len(parsed.warnings),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "publish-ics":
        result = publish_once(config, days=args.days, verbose=args.verbose)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

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

    return 0
