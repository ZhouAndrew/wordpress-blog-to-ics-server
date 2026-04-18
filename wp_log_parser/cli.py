from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .aliases import find_today_ics_candidates, generate_today_ics, select_today_ics, today_date_str
from .config import config_exists, create_default_config, load_config, save_config
from .fetcher import fetch_post, list_recent_post_ids
from .ics import build_public_ics_url, generate_ics
from .ics_exporter import write_post_ics, write_publish_index
from .parser import parse_post_content
from .service import fetch_post as fetch_post_legacy, run_today_pipeline
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

    if not _print_validation(config):
        print("Critical validation errors found. Aborting execution.")
        return 1

    if args.command == "fetch-post":
        if args.select_post_id and args.post_id is not None:
            print("Cannot use --select-post-id and --post-id together.")
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
        post_id = args.post_id
        if args.select_post_id:
            if not sys.stdin.isatty():
                print("Interactive post selection requires a TTY.")
                return 2
            post_id = select_post_id(config)
        post_id, content = fetch_post_legacy(config, post_id)
        from datetime import date
        parsed = parse_post_content(content, date.today().isoformat(), config)
        parsed["post_id"] = post_id
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
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
        post_date = post.post_date.split(" ")[0]
        parsed = parse_post_content(post.post_content, post_date, config, verbose=args.verbose)
        parsed["ics_preview"] = generate_ics(parsed["entries"], timezone=config.timezone)
        if not parsed["entries"]:
            print("No valid timed log entries found in post.")
            return 1
        out_path = write_post_ics(post, parsed["entries"], config.output_dir, config.timezone)
        if args.verbose:
            print(f"[OK] Wrote ICS file: {out_path}")
        print(
            json.dumps(
                {
                    "post_id": post.post_id,
                    "title": post.title,
                    "post_date": post.post_date,
                    "output_file": str(out_path),
                    "entry_count": len(parsed["entries"]),
                    "ignored_block_count": len(parsed["ignored_blocks"]),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "publish-ics":
        post_ids = list_recent_post_ids(config, args.days)
        items = []
        for post_id in post_ids:
            post = fetch_post(config, post_id)
            post_date = post.post_date.split(" ")[0]
            parsed = parse_post_content(post.post_content, post_date, config, verbose=args.verbose)
            if not parsed["entries"]:
                if args.verbose:
                    print(f"[WARN] Skipped post {post_id}: no valid timed entries")
                continue
            out_path = write_post_ics(post, parsed["entries"], config.output_dir, config.timezone)
            if args.verbose:
                print(f"[OK] Published post {post_id}: {out_path.name}")
            items.append(
                {
                    "post_id": post.post_id,
                    "title": post.title,
                    "post_date": post.post_date,
                    "ics_file": out_path.name,
                    "ics_url": build_public_ics_url(config.ics_base_url, out_path.name),
                    "entry_count": len(parsed["entries"]),
                    "ignored_block_count": len(parsed["ignored_blocks"]),
                }
            )

        items.sort(key=lambda x: x["post_date"], reverse=True)
        index_path = write_publish_index(config.output_dir, items, args.days)
        if args.verbose:
            print(f"[OK] Wrote publish index: {index_path}")
        print(
            json.dumps(
                {
                    "generated_at": datetime.now().isoformat(),
                    "recent_days": args.days,
                    "published_count": len(items),
                    "items": items,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "update-today-ics":
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

    return 0
