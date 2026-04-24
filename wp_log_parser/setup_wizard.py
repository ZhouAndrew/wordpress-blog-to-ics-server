from __future__ import annotations

import getpass
from dataclasses import asdict
from pathlib import Path

from .config import AppConfig, create_default_config, save_config
from .service import list_posts
from .validators import (
    validate_dependencies,
    validate_output_dir,
    validate_python_path,
    validate_rest_credentials,
    validate_wordpress_path,
    validate_wp_cli,
)


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def prompt_text(label: str, explanation: str, default: str | None = None) -> str:
    while True:
        default_part = f" [default: {default}]" if default is not None else ""
        print(f"\n{label}\n{explanation}{default_part}")
        value = input("> ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("Please enter a value.")


def prompt_yes_no(label: str, explanation: str, default: bool = True) -> bool:
    default_str = "y" if default else "n"
    while True:
        print(f"\n{label}\n{explanation} [default: {default_str}]")
        value = input("> ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Invalid input. Enter y/yes or n/no.")


def prompt_choice(label: str, explanation: str, choices: list[str], default: str) -> str:
    index_default = choices.index(default) + 1
    while True:
        print(f"\n{label}\n{explanation}")
        for idx, choice in enumerate(choices, 1):
            print(f"  {idx}) {choice}")
        print(f"[default: {index_default}]")
        value = input("> ").strip()
        if not value:
            return default
        if value.isdigit() and 1 <= int(value) <= len(choices):
            return choices[int(value) - 1]
        print("Invalid choice. Enter a valid number.")


def prompt_post_selection(label: str, explanation: str, posts: list[dict[str, str | int]], default_index: int = 1) -> int:
    if not posts:
        raise ValueError("No posts available for selection")
    default_index = max(1, min(default_index, len(posts)))
    while True:
        print(f"\n{label}\n{explanation}")
        for idx, post in enumerate(posts, 1):
            print(
                f"  {idx}) {post['date']} [{post['status']}] {post['title']} (ID: {post['id']})"
            )
        
def prompt_post_selection(
    label: str,
    explanation: str,
    posts: list[dict[str, str | int]],
    default_index: int | None = None,
) -> int:
    if not posts:
        raise ValueError("No posts available for selection")

   
    default_index = default_index or len(posts)
    default_index = max(1, min(default_index, len(posts)))

    while True:
        print(f"\n{label}\n{explanation}")
        for idx, post in enumerate(posts, 1):
            print(
                f"  {idx}) {post['date']} [{post['status']}] {post['title']} (ID: {post['id']})"
            )

        print(f"[default: {default_index}]")
        value = input("> ").strip()

        if not value:
            return int(posts[default_index - 1]["id"])

        if value.isdigit():
            chosen = int(value)
            if 1 <= chosen <= len(posts):
                return int(posts[chosen - 1]["id"])
            for post in posts:
                if post["id"] == chosen:
                    return chosen

        print("Invalid choice. Enter the number shown or an exact post ID.")


def prompt_int(label: str, explanation: str, default: int) -> int:
    while True:
        raw = prompt_text(label, explanation, str(default))
        try:
            return int(raw)
        except ValueError:
            print("Invalid input. Please enter an integer.")


def prompt_existing_path(label: str, explanation: str, default: str) -> str:
    while True:
        value = prompt_text(label, explanation, default)
        if Path(value).exists() or value in {"wp", "python", "python3"}:
            return value
        print("Path does not exist.")


def prompt_directory(label: str, explanation: str, default: str) -> str:
    while True:
        value = prompt_text(label, explanation, default)
        try:
            Path(value).mkdir(parents=True, exist_ok=True)
            return value
        except OSError as exc:
            print(f"Unable to create directory: {exc}")


def run_setup_wizard(config_path: str) -> AppConfig:
    print("Welcome to wp_log_parser setup wizard")
    cfg = create_default_config()

    cfg.wordpress_mode = prompt_choice(
        "1) Fetch mode",
        "Choose how to fetch posts.",
        ["wpcli", "rest"],
        cfg.wordpress_mode,
    )

    if cfg.wordpress_mode == "wpcli":
        cfg.wp_cli_path = prompt_text("2) wp command", "Path or command name for wp-cli.", cfg.wp_cli_path)
        cfg.wp_path = prompt_existing_path("WordPress path", "Path to WordPress installation.", cfg.wp_path)
    else:
        cfg.base_url = prompt_text("2) WordPress base URL", "Example: https://example.com", cfg.base_url)
        cfg.username = prompt_text("Username", "WordPress username for REST API.", cfg.username)
        pwd_default = "" if not cfg.app_password else "(hidden default)"
        print(f"\nApplication password\nWordPress application password. [default: {pwd_default}]")
        pwd_input = getpass.getpass("> ")
        cfg.app_password = pwd_input if pwd_input else cfg.app_password
        cfg.verify_ssl = prompt_yes_no("Verify SSL", "Verify TLS certificate for REST calls.", cfg.verify_ssl)

    cfg.python_path = prompt_text("3) Python path", "Python executable to use.", cfg.python_path)
    cfg.output_dir = prompt_directory("4) Output directory", "Where generated files should go.", cfg.output_dir)
    cfg.error_dir = prompt_directory("Error directory", "Where error payloads should be written.", cfg.error_dir)

    cfg.log_format = prompt_choice(
        "5) Log format",
        "Select the input format to parse.",
        ["gutenberg_raw", "rendered_html"],
        cfg.log_format,
    )
    cfg.timezone = prompt_text("Timezone", "IANA timezone string.", cfg.timezone)
    cfg.save_ignored_blocks = prompt_yes_no(
        "Save ignored blocks",
        "Keep ignored block details in parser output.",
        cfg.save_ignored_blocks,
    )

    cfg.default_last_event_minutes = prompt_int(
        "6) Final event fallback",
        "Default minutes to assign to final event if it has no next event (0 disables).",
        cfg.default_last_event_minutes,
    )
    cfg.allow_empty_summary = prompt_yes_no("Allow empty summary", "Allow time-only lines such as '10:11'.", cfg.allow_empty_summary)
    cfg.auto_cross_midnight = prompt_yes_no(
        "Auto crossing midnight",
        "Allow timeline to cross midnight when entries go from later to earlier clock time.",
        cfg.auto_cross_midnight,
    )
    cfg.post_selection_count = prompt_int(
        "8) Post selection count",
        "How many recent posts should be listed when selecting a post interactively?",
        cfg.post_selection_count,
    )

    cfg.ics_base_url = prompt_text("9) ICS base URL", "Public base URL for generated ICS files.", cfg.ics_base_url)

    print("\n10) Environment validation")
    results = []
    results.extend(validate_dependencies())
    results.append(validate_python_path(cfg.python_path))
    results.append(validate_output_dir(cfg.output_dir))
    results.append(validate_output_dir(cfg.error_dir))

    if cfg.wordpress_mode == "wpcli":
        results.append(validate_wp_cli(cfg.wp_cli_path))
        results.append(validate_wordpress_path(cfg.wp_path))
    else:
        results.append(validate_rest_credentials(cfg.base_url, cfg.username, cfg.app_password, cfg.verify_ssl))

    for result in results:
        status = "[OK]" if result.ok else "[ERROR]"
        print(f"{status} {result.name}: {result.message}")
        if result.details:
            print(f"      {result.details}")

    print("\nConfiguration summary:")
    summary = asdict(cfg)
    summary["app_password"] = mask_secret(summary["app_password"])
    for key, value in summary.items():
        print(f"  - {key}: {value}")

    should_save = prompt_yes_no("Save config", f"Write config to {config_path}?", True)
    if should_save:
        save_config(cfg, config_path)
        print(f"Saved config to {config_path}")
    else:
        print("Config not saved.")
    return cfg


def select_post_id(config: AppConfig, per_page: int | None = None) -> int:
    per_page = config.post_selection_count if per_page is None else per_page
    posts = list_posts(config, per_page=per_page)
    if not posts:
        raise ValueError("No posts found for interactive selection")
    return prompt_post_selection(
        "Select post to fetch",
        "Choose a post from the list below. Enter the number or exact post ID.",
        posts,
        default_index=len(posts),
    )
