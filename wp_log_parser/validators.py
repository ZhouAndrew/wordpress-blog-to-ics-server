from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path

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
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ValidationResult(False, "directory", "Cannot create directory", str(exc))
    return ValidationResult(True, "directory", "Directory is writable", str(p))


def validate_rest_credentials(base_url: str, username: str, app_password: str, verify_ssl: bool) -> ValidationResult:
    if not base_url.startswith(("http://", "https://")):
        return ValidationResult(False, "rest", "Base URL must start with http:// or https://", base_url)
    if not username or not app_password:
        return ValidationResult(False, "rest", "Username and app password are required", None)

    if importlib.util.find_spec("requests") is None:
        return ValidationResult(False, "rest", "requests package is not installed", None)

    try:
        import requests

        resp = requests.get(f"{base_url.rstrip('/')}/wp-json/wp/v2", verify=verify_ssl, timeout=10)
        if resp.status_code >= 400:
            return ValidationResult(False, "rest", f"REST endpoint unreachable ({resp.status_code})", None)
    except Exception as exc:
        return ValidationResult(False, "rest", "REST endpoint request failed", str(exc))

    return ValidationResult(True, "rest", "REST configuration looks reachable", None)


def validate_dependencies() -> list[ValidationResult]:
    checks = []
    for module in ["json", "re", "datetime", "hashlib"]:
        ok = importlib.util.find_spec(module) is not None
        checks.append(
            ValidationResult(ok, f"module:{module}", "Module available" if ok else "Module missing", None)
        )
    return checks
