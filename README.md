# WordPress Blog Log → ICS CLI

Convert diary-style WordPress posts into timeline events and `.ics` calendar files.

This project is for developers and power users who already work with WordPress and command-line workflows.

---

## Project Overview

`wp_log_parser` is a command-line tool that:

1. Fetches posts from WordPress (via **wp-cli** or **REST API**)
2. Parses Gutenberg block content
3. Extracts time-based log lines (for example, `07:45 Breakfast`)
4. Builds structured timeline entries
5. Exports ICS files you can subscribe to in calendar apps

Typical use cases:

- Personal daily log → calendar timeline
- Local automation for publishing fresh ICS feeds
- Stable `today.ics` URL for calendar subscriptions

---

## Features

- Supports two fetch modes:
  - `wpcli` (recommended when running on a host with WordPress + wp-cli)
  - `rest` (recommended for remote access)
- Parses Gutenberg post content for time-based entries
- Supports point-in-time and range-style log entries
- Exports valid ICS files per post
- Generates index artifacts (`index.json`, `index.html`)
- Maintains a stable `today.ics` alias for subscriptions
- Includes a local HTTP service mode for continuous publishing
- Configurable through `config.json` (including custom parsing patterns)

---

## Requirements

### Runtime

- Python **3.10+** (3.11 recommended)
- `pip`

### For `wpcli` mode

- `wp-cli` installed and available on PATH (or configured via `wp_cli_path`)
- Local filesystem access to your WordPress installation
- Valid WordPress root path (set as `wp_path`)

### For `rest` mode

- Reachable WordPress site URL (`base_url`)
- WordPress username
- WordPress application password

---

## Installation

```bash
# 1) Clone repository
git clone <your-repo-url>
cd wordpress-blog-to-ics-server

# 2) Create virtual environment
python -m venv .venv
source .venv/bin/activate

# 3) Install dependencies
pip install -U pip
pip install requests pytest
```

> If your environment already uses dependency management tooling, adapt accordingly.

---

## Configuration (`config.json`)

Create config interactively (recommended):

```bash
python -m wp_log_parser init-config --wizard --config ./config.json
```

Validate config and environment:

```bash
python -m wp_log_parser validate-config --config ./config.json
```

You can also start from `example.config.json`.

### Common config fields

- `wordpress_mode`: `wpcli` or `rest`
- `wp_cli_path`: path/command for wp-cli (`wp`)
- `wp_path`: WordPress install path (required for `wpcli` mode)
- `base_url`: WordPress base URL (required for `rest` mode)
- `username`, `app_password`: REST credentials
- `output_dir`: generated files destination
- `timezone`: timezone used for exported events
- `default_last_event_minutes`: fallback duration for final event
- `save_ignored_blocks`: write ignored block diagnostics
- `custom_parsing_patterns`: optional custom regex parsing rules

---

## CLI Usage

General help:

```bash
python -m wp_log_parser --help
```

### 1) Fetch a post

```bash
python -m wp_log_parser fetch-post --config ./config.json --post-id 10213
```

Interactive selection from recent posts:

```bash
python -m wp_log_parser fetch-post --config ./config.json --select-post-id
```

### 2) Parse a post into structured timeline output

```bash
python -m wp_log_parser parse-post --config ./config.json --post-id 10213
```

### 3) Export one post to ICS

```bash
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213
```

Verbose mode:

```bash
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213 --verbose
```

### 4) Publish ICS for recent posts

```bash
python -m wp_log_parser publish-ics --config ./config.json --days 7
```

### 5) Refresh `today.ics`

```bash
python -m wp_log_parser update-today-ics --config ./config.json
```

Use symlink mode:

```bash
python -m wp_log_parser update-today-ics --config ./config.json --mode symlink
```

### 6) Run the local ICS service

```bash
python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 300 --host 127.0.0.1 --port 5333
```

---

## Command Reference

- `init-config` – create config (optionally with interactive wizard)
- `validate-config` – validate config and environment dependencies
- `fetch-post` – fetch and display one post by ID
- `parse-post` – parse one post and show structured entries
- `export-ics` – generate ICS from existing entries JSON input
- `run-today` – run the “today” flow from current configuration
- `post-to-ics` – fetch + parse + export one post to ICS
- `publish-ics` – generate ICS files for recent posts and index artifacts
- `update-today-ics` – create/update `today.ics` alias
- `run-ics-service` – periodic publish + static HTTP server

---

## Output Files

Depending on command and config, output can include:

- `YYYY-MM-DD_post_<post_id>_<slug>.ics`
- `today.ics`
- `index.json`
- `index.html`
- `*.ignored.json` (if ignored-block export enabled)

---

## Troubleshooting

### `wp-cli not found`

- Confirm `wp` is installed: `wp --info`
- Set `wp_cli_path` explicitly in `config.json`

### `Path exists but does not look like WordPress`

- Verify `wp_path` points to your real WordPress root (where `wp-config.php` is located)

### REST authentication errors (401/403)

- Confirm `base_url` is correct
- Recreate WordPress application password
- Ensure username has permission to read posts

### No entries parsed from a post

- Confirm your log lines begin with `H:MM` or `HH:MM`
- Verify logs are in Gutenberg paragraph content
- Check whether custom parsing patterns are too strict

### `today.ics` missing after publish

- Run manually: `python -m wp_log_parser update-today-ics --config ./config.json`
- Confirm there is at least one eligible `.ics` file in `output_dir`

### Command seems to run but no files appear

- Verify `output_dir` in `config.json`
- Use verbose command variants where available
- Check whether the selected post actually contains timed log entries

---

## Getting Started Guide

For a step-by-step setup and first run walkthrough, see:

- [Getting Started](./GETTING_STARTED.md)

---

## License

MIT
