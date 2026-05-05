from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig
from .debug_report import sanitize_config
from .fetcher import fetch_post, normalize_post_date
from .ics import generate_ics
from .operations import write_runtime_log
from .parser import parse_post_content
from .source_metadata import attach_source_metadata
from .service import list_posts
from .validators import (
    validate_caldav_config,
    validate_custom_parsing_patterns,
    validate_dependencies,
    validate_output_dir,
    validate_python_path,
    validate_rest_credentials,
    validate_wordpress_path,
    validate_wp_cli,
)

try:
    import requests as _requests
except Exception:  # pragma: no cover
    _requests = None


def _item(status: str, message: str, details: dict[str, Any] | None = None, fixable: bool = False) -> dict[str, Any]:
    return {"status": status, "message": message, "details": details or {}, "fixable": fixable}


def run_health_check(
    config: AppConfig,
    *,
    full: bool = True,
    test_caldav_write: bool = False,
    require_caldav: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "config": [], "environment": [], "wordpress_runtime": [], "parser_runtime": [], "ics_runtime": [],
        "caldav_runtime": [], "caldav_write_test": [], "logs": [],
    }
    report["config"].append(_item("ok", "sanitized config loaded", sanitize_config(config), False))
    parser_config = validate_custom_parsing_patterns(config)
    report["config"].append(
        _item(
            "ok" if parser_config.ok else "error",
            parser_config.message,
            {"name": parser_config.name},
            fixable=not parser_config.ok,
        )
    )
    if not parser_config.ok:
        _write_health_files(config, report)
        return report

    for c in [*validate_dependencies(), validate_python_path(config.python_path), validate_output_dir(config.output_dir), validate_output_dir(config.error_dir), validate_output_dir(config.logs_dir)]:
        report["environment"].append(_item("ok" if c.ok else "error", c.message, {"name": c.name}, fixable=not c.ok))

    if config.wordpress_mode == "wpcli":
        for c in [validate_wp_cli(config.wp_cli_path), validate_wordpress_path(config.wp_path)]:
            report["config"].append(_item("ok" if c.ok else "error", c.message, {"name": c.name}, fixable=not c.ok))
    else:
        c = validate_rest_credentials(config.base_url, config.username, config.app_password, config.verify_ssl)
        report["config"].append(_item("ok" if c.ok else "error", c.message, {"name": c.name}, fixable=not c.ok))

    if full:
        try:
            posts = list_posts(config)
            report["wordpress_runtime"].append(_item("ok", "listed posts", {"posts_listed": len(posts)}))
        except Exception as exc:
            report["wordpress_runtime"].append(_item("error", f"failed to list posts: {exc}", fixable=True))
            posts = []
        if posts:
            parsed = None
            sampled = 0
            for sample in sorted(posts, key=lambda p: str(p.get("date", "")), reverse=True):
                sampled += 1
                try:
                    post = fetch_post(config, int(sample["id"]))
                    candidate = parse_post_content(post.post_content, normalize_post_date(post.post_date), config)
                    attach_source_metadata(candidate, post)
                except Exception as exc:
                    report["parser_runtime"].append(_item("warning", f"skipped sample post due to error: {exc}", {"sample_post_id": sample.get("id")}, True))
                    continue
                if candidate.entries:
                    parsed = candidate
                    report["parser_runtime"].append(_item("ok", "parsed sample post with timed entries", {
                        "sample_post_id": post.post_id, "sample_title": post.title, "sample_post_date": post.post_date,
                        "entry_count": len(candidate.entries), "ignored_block_count": len(candidate.ignored_blocks), "warning_count": len(candidate.warnings),
                        "sampled_posts": sampled,
                    }))
                    break

            if parsed is None:
                report["parser_runtime"].append(
                    _item("warning", "WordPress connection OK, but no timed diary entries were found in sampled posts.", {"sampled_posts": sampled})
                )
                report["ics_runtime"].append(
                    _item("warning", "ics runtime skipped because sampled posts had zero timed entries", {"ics_generation_status": "skipped", "ics_byte_size": 0})
                )
            else:
                try:
                    ics = generate_ics([e.to_dict() for e in parsed.entries], timezone=config.timezone)
                    report["ics_runtime"].append(_item("ok", "ics generated", {"ics_generation_status": "ok", "ics_byte_size": len(ics.encode("utf-8"))}))
                except Exception as exc:
                    report["ics_runtime"].append(_item("error", f"ics generation failed: {exc}", {"ics_generation_status": "error"}, fixable=True))
        elif full:
            report["wordpress_runtime"].append(_item("error", "no sample post available", fixable=True))

    cal = validate_caldav_config(
        config.caldav_url,
        config.caldav_username,
        config.caldav_password,
        config.caldav_uid_domain,
        config.caldav_index_path,
        required=require_caldav,
    )
    if not config.caldav_url.strip():
        status = "error" if require_caldav else "skipped"
        report["caldav_runtime"].append(_item(status, "caldav is not configured", {"configured": False}, fixable=True))
    elif not cal.ok:
        status = "error" if require_caldav else "warning"
        report["caldav_runtime"].append(_item(status, cal.message, {"configured": False}, fixable=True))
    else:
        try:
            status = _request_status("OPTIONS", config.caldav_url, config)
            ok = status < 400
            report["caldav_runtime"].append(_item("ok" if ok else "error", "caldav connectivity/auth tested", {
                "server_reachable": True, "authentication_appears_valid": ok, "collection_accessible": ok, "http_status": status,
            }, fixable=not ok))
        except Exception as exc:
            report["caldav_runtime"].append(_item("error", f"caldav connectivity failed: {exc}", {"server_reachable": False}, True))

    if test_caldav_write and cal.ok and config.caldav_url.strip():
        report["caldav_write_test"].append(run_caldav_write_test(config))
    elif test_caldav_write:
        report["caldav_write_test"].append(
            _item(
                "error" if require_caldav else "warning",
                "disposable write test requested but CalDAV configuration is invalid",
                {"configured": False},
                fixable=True,
            )
        )
    else:
        report["caldav_write_test"].append(_item("skipped", "disposable write test not requested"))

    _write_health_files(config, report)
    return report


def run_caldav_write_test(config: AppConfig) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = f"wp-log-healthcheck-{ts}@{config.caldav_uid_domain}"
    resource_path = f"healthcheck-{ts}.ics"
    resource_url = f"{config.caldav_url.rstrip('/')}/{resource_path}"
    payload = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:%s\r\nDTSTART:20260101T000000Z\r\nSUMMARY:Healthcheck\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n" % uid
    details = {"resource_path": resource_path}
    details["put_status"] = _request_status("PUT", resource_url, config, data=payload.encode("utf-8"))
    if details["put_status"] not in {200, 201, 204}:
        return _item("error", "disposable write PUT failed", details, fixable=True)

    get_status: int | None = None
    get_error: str | None = None
    try:
        get_status = _request_status("GET", resource_url, config)
        details["get_status"] = get_status
    except Exception as exc:
        get_error = str(exc)
        details["get_error"] = get_error

    delete_status: int | None = None
    delete_error: str | None = None
    try:
        delete_status = _request_status("DELETE", resource_url, config)
        details["delete_status"] = delete_status
    except Exception as exc:
        delete_error = str(exc)
        details["delete_error"] = delete_error

    if delete_error is not None:
        return _item("error", "cleanup failed for disposable resource", details, fixable=True)
    if delete_status not in {200, 204, 404}:
        return _item("warning", "cleanup failed for disposable resource", details, fixable=True)
    if get_error is not None:
        return _item("error", "disposable write GET raised; cleanup succeeded", details, fixable=True)
    if get_status in {405, 501}:
        return _item("warning", "disposable write GET unsupported; cleanup succeeded", details)
    if get_status not in {200, 204}:
        return _item("error", "disposable write GET failed; cleanup succeeded", details, fixable=True)
    return _item("ok", "disposable write test completed", details)


def _write_health_files(config: AppConfig, report: dict[str, Any]) -> None:
    err = Path(config.error_dir)
    err.mkdir(parents=True, exist_ok=True)
    log_path = write_runtime_log(config, "health", "health check completed", {"sections": list(report.keys())})
    report["logs"].append(
        _item(
            "ok",
            "health report and runtime log written",
            {"last_health_report_path": str(err / "last_health_report.json"), "runtime_log_path": str(log_path)},
        )
    )
    (err / "last_health_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _request_status(method: str, url: str, config: AppConfig, data: bytes | None = None) -> int:
    if _requests is None:
        raise RuntimeError("requests package is required for CalDAV runtime checks")
    r = _requests.request(
        method,
        url,
        data=data,
        auth=(config.caldav_username, config.caldav_password),
        verify=config.verify_ssl,
        headers={"Content-Type": "text/calendar; charset=utf-8"} if method == "PUT" else None,
        timeout=20,
    )
    return int(r.status_code)
