from __future__ import annotations

import importlib.util
import os
import re
import shutil
from pathlib import Path

from .line_patterns import compile_custom_patterns
from .models import ValidationResult


def validate_wp_cli(path: str) -> ValidationResult:
    resolved = shutil.which(path)
    if resolved and os.access(resolved, os.X_OK):
        return ValidationResult(True, "wp_cli", "wp-cli is executable", resolved)
    return ValidationResult(False, "wp_cli", "wp-cli not found or not executable", path)


def validate_python_path(path: str) -> ValidationResult:
    resolved = shutil.which(path) if not Path(path).exists() else path
    if resolved:
        return ValidationResult(True, "python", "Python executable found", resolved)
    return ValidationResult(False, "python", "Python executable not found", path)


def validate_wordpress_path(path: str) -> ValidationResult:
    p = Path(path)
    if not p.exists():
        return ValidationResult(False, "wordpress_path", "WordPress path does not exist", path)
    markers = [p / "wp-config.php", p / "wp-includes"]
    if any(m.exists() for m in markers):
        return ValidationResult(True, "wordpress_path", "WordPress path looks valid", str(p))
    return ValidationResult(False, "wordpress_path", "Path exists but does not look like WordPress", str(p))


def validate_output_dir(path: str) -> ValidationResult:
    """Backward-compatible alias for writable directory validation."""
    return validate_output_dir_writable(path)


def validate_output_dir_readonly(path: str) -> ValidationResult:
    p = Path(path)
    if not p.exists():
        return ValidationResult(False, "directory", "Directory is missing", str(p))
    if not p.is_dir():
        return ValidationResult(False, "directory", "Path exists but is not a directory", str(p))
    if not os.access(p, os.W_OK):
        return ValidationResult(False, "directory", "Directory is not writable", str(p))
    return ValidationResult(True, "directory", "Directory exists and is writable", str(p))


def validate_output_dir_writable(path: str) -> ValidationResult:
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ValidationResult(False, "directory", "Cannot create directory", str(exc))
    if not p.is_dir():
        return ValidationResult(False, "directory", "Path exists but is not a directory", str(p))
    if not os.access(p, os.W_OK):
        return ValidationResult(False, "directory", "Directory is not writable", str(p))
    return ValidationResult(True, "directory", "Directory exists and is writable", str(p))


def validate_rest_credentials(base_url: str, username: str, app_password: str, verify_ssl: bool) -> ValidationResult:
    if not isinstance(base_url, str) or not base_url.strip():
        return ValidationResult(False, "rest", "base_url is required for wordpress_mode=rest; update setting 'base_url'", None)
    if not base_url.startswith(("http://", "https://")):
        return ValidationResult(False, "rest", "base_url must start with http:// or https://; update setting 'base_url'", base_url)
    if not isinstance(username, str) or not username.strip():
        return ValidationResult(False, "rest", "username is required for wordpress_mode=rest; update setting 'username'", None)
    if not isinstance(app_password, str) or not app_password.strip():
        return ValidationResult(False, "rest", "app_password is required for wordpress_mode=rest; update setting 'app_password'", None)
    if not isinstance(verify_ssl, bool):
        return ValidationResult(False, "rest", "verify_ssl must be true or false; update setting 'verify_ssl'", None)

    if importlib.util.find_spec("requests") is None:
        return ValidationResult(False, "rest", "requests package is not installed", None)

    endpoint = f"{base_url.rstrip('/')}/wp-json/wp/v2/users/me?context=edit"
    try:
        import requests

        resp = requests.get(
            endpoint,
            auth=(username, app_password),
            verify=verify_ssl,
            timeout=10,
        )
    except Exception as exc:
        return ValidationResult(
            False,
            "rest",
            "REST connectivity failure while calling authenticated endpoint; check setting 'base_url' and network/SSL access",
            str(exc),
        )

    if resp.status_code in {401, 403}:
        return ValidationResult(
            False,
            "rest",
            "REST authentication failed at /wp-json/wp/v2/users/me; check settings 'username' and 'app_password'",
            None,
        )
    if resp.status_code >= 400:
        return ValidationResult(
            False,
            "rest",
            f"REST connectivity failure: authenticated endpoint returned HTTP {resp.status_code}; check setting 'base_url'",
            None,
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        return ValidationResult(
            False,
            "rest",
            "Malformed REST response: authenticated endpoint did not return JSON",
            str(exc),
        )

    if not isinstance(payload, dict):
        return ValidationResult(False, "rest", "Malformed REST response: expected a JSON object from authenticated endpoint", None)
    if "id" not in payload and "slug" not in payload and "username" not in payload and "name" not in payload:
        return ValidationResult(
            False,
            "rest",
            "Malformed REST response: authenticated user payload is missing expected user fields",
            None,
        )

    return ValidationResult(True, "rest", "REST authentication succeeded against /wp-json/wp/v2/users/me", None)


def validate_custom_parsing_patterns(config) -> ValidationResult:
    try:
        patterns = compile_custom_patterns(config)
    except (KeyError, TypeError, ValueError) as exc:
        return ValidationResult(False, "custom_parsing_patterns", str(exc), None)
    return ValidationResult(
        True,
        "custom_parsing_patterns",
        f"Custom parsing patterns are valid ({len(patterns)} configured)",
        None,
    )


def validate_dependencies() -> list[ValidationResult]:
    checks = []
    for module in ["json", "re", "datetime", "hashlib"]:
        ok = importlib.util.find_spec(module) is not None
        checks.append(
            ValidationResult(ok, f"module:{module}", "Module available" if ok else "Module missing", None)
        )
    return checks


def validate_caldav_config(
    caldav_url: str,
    caldav_username: str,
    caldav_password: str,
    caldav_uid_domain: str,
    caldav_index_path: str,
    *,
    required: bool = True,
) -> ValidationResult:
    if not required and not caldav_url and not caldav_username and not caldav_password:
        return ValidationResult(True, "caldav", "CalDAV settings are optional for this command", None)

    if not caldav_url.startswith(("http://", "https://")):
        return ValidationResult(False, "caldav", "caldav_url must start with http:// or https://", caldav_url)
    if not caldav_username:
        return ValidationResult(False, "caldav", "caldav_username is required", None)
    if not caldav_password:
        return ValidationResult(False, "caldav", "caldav_password is required", None)
    if not caldav_uid_domain:
        return ValidationResult(False, "caldav", "caldav_uid_domain is required", None)
    if not re.match(r"^[A-Za-z0-9.-]+$", caldav_uid_domain):
        return ValidationResult(False, "caldav", "caldav_uid_domain contains invalid characters", caldav_uid_domain)
    if not caldav_index_path:
        return ValidationResult(False, "caldav", "caldav_index_path is required", None)

    idx_path = Path(caldav_index_path)
    parent = idx_path.parent if idx_path.parent != Path("") else Path(".")
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ValidationResult(False, "caldav", "Cannot create caldav index directory", str(exc))

    return ValidationResult(True, "caldav", "CalDAV sync configuration looks valid", str(idx_path))
