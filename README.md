# WordPress Blog Log → ICS CLI

Convert diary-style WordPress posts into timeline events and `.ics` calendar files.

This project is for developers and power users who already work with WordPress and command-line workflows.

---

## Status

**Pre-alpha / internal validation build**

This project is **not public-alpha ready yet**. It remains in internal validation until the maintainer completes an end-to-end validation run across setup, publish, service, and sync workflows.

## Before v0.1.0-alpha

- [ ] fresh clone
- [ ] install script
- [ ] run script
- [ ] setup wizard
- [ ] health summary
- [ ] recent post list
- [ ] timeline preview
- [ ] local ICS generation
- [ ] today.ics update
- [ ] local service subscription
- [ ] CalDAV setup
- [ ] CalDAV doctor
- [ ] dry-run sync
- [ ] real sync
- [ ] second sync idempotency
- [ ] Ctrl+C handling
- [ ] secret redaction

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

## Quick Start (End-user Workflow)

```bash
./install.sh
./run.sh
```

Windows:

```bat
install.bat
run.bat
```

Inside the interactive app (`python -m wp_log_parser app`) you can run checks, inspect config, and run a dry-run sync.


## First-run walkthrough

1. `./install.sh`
2. `./run.sh`
3. Guided setup wizard
4. Health check summary in app
5. Preview timeline from a selected recent post
6. Generate/publish local ICS files
7. Update `today.ics`
8. Configure CalDAV, run dry-run sync, then real sync

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
- `caldav_url`: CalDAV collection URL (for `sync-caldav`)
- `caldav_username`, `caldav_password`: CalDAV credentials
- `caldav_uid_domain`: UID suffix domain for event resources
- `caldav_index_path`: local sync index JSON file path
- `caldav_deletion_mode`: deletion strategy for removed events (`delete` default, or `cancel`)

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

### 7) Incremental CalDAV sync

```bash
python -m wp_log_parser sync-caldav --config ./config.json
```

Dry-run (report changes without writing to CalDAV or the index file):

```bash
python -m wp_log_parser sync-caldav --config ./config.json --dry-run
```

Interactive app safety gate for real sync:

- The app requires a successful dry-run marker from the last 24 hours before allowing real CalDAV writes.
- A marker becomes incompatible when sync-affecting configuration changes, including timezone, parser behavior (`custom_parsing_patterns`, `default_last_event_minutes`, cross-midnight/summary handling), WordPress source mode/path, CalDAV target/index/deletion settings, or CalDAV credential identity.
- Display-only settings (for example `post_selection_count`) are intentionally excluded and do not invalidate the marker.

### 8) Config operations

```bash
python -m wp_log_parser config --config ./config.json get timezone
python -m wp_log_parser config --config ./config.json set timezone Asia/Seoul
python -m wp_log_parser config --config ./config.json edit
```

### 9) Doctor checks

```bash
python -m wp_log_parser doctor --config ./config.json
```

`doctor` currently validates environment and configuration checks (paths, dependencies, mode-specific settings, optional/required CalDAV settings). It does not run a full fetch/parse pipeline health simulation.

Debug mode (extra diagnostics + sanitized run snapshot):

```bash
python -m wp_log_parser sync-caldav --config ./config.json --debug
python -m wp_log_parser run-today --config ./config.json --debug
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213 --debug
python -m wp_log_parser publish-ics --config ./config.json --days 7 --debug
```

UID behavior in v1:

- UIDs are stable across insertion of unrelated entries.
- If an entry start time changes, identity changes too, so sync performs **delete + create** (not in-place move/update).
- This behavior is expected/accepted for v1.

Deletion behavior:

- `caldav_deletion_mode: "delete"` (default): removed events are removed with CalDAV `DELETE`.
- `caldav_deletion_mode: "cancel"`: removed events are tombstoned using a `PUT` with `STATUS:CANCELLED` and incremented `SEQUENCE`.
- In `cancel` mode, tombstones stay in `index.events` for idempotency and compatibility with stricter clients/servers.
- Restoring a previously removed event in `cancel` mode reuses the same UID/resource path and sends `STATUS:CONFIRMED` with an incremented `SEQUENCE`.
- Whole-post removal:
  - In `delete` mode, previously tracked events are removed from CalDAV and then removed from the sync index.
  - In `cancel` mode, previously tracked events are written once as `STATUS:CANCELLED` tombstones and retained in `index.events`.
  - Post ownership state in `index.posts` is dropped when the post disappears from the source listing.
  - Tombstone retention in `index.events` makes repeated runs idempotent even after post ownership is dropped.
- Automatic tombstone cleanup is not implemented yet.
- Recommended future cleanup policy:
  - keep tombstones for a retention window (for example, 30 days), or
  - add an explicit cleanup command so pruning is operator-controlled.

---


## Validation Matrix (Docs ↔ Scripts ↔ CLI)

| Flow | Command / Entry Point | Mode | Expected Status | Notes |
|---|---|---|---|---|
| Fetch source via wp-cli | `python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213` | `wordpress_mode=wpcli` | Supported | `--post-id` is required for `post-to-ics`. |
| Fetch source via REST | `python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213` | `wordpress_mode=rest` | Supported | Requires `base_url`, `username`, `app_password`. |
| Local ICS batch publish | `python -m wp_log_parser publish-ics --config ./config.json --days 7` | wpcli/rest | Supported | Generates per-post ICS + `index.json` + `index.html`; auto-refreshes `today.ics` when possible. |
| Today alias update | `python -m wp_log_parser update-today-ics --config ./config.json` | wpcli/rest | Supported | Use `--mode copy` (default) or `--mode symlink`. |
| Service mode | `python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 300 --host 127.0.0.1 --port 5333` | wpcli/rest | Supported | Periodic publish plus local HTTP server. |
| Dry-run CalDAV sync | `python -m wp_log_parser sync-caldav --config ./config.json --dry-run` | wpcli/rest | Supported | Reports planned changes; does not write CalDAV or sync index. |
| Real CalDAV sync | `python -m wp_log_parser sync-caldav --config ./config.json` | wpcli/rest | Supported with preconditions | Requires `caldav_url`, `caldav_username`, `caldav_password` and reachable CalDAV collection. |
| Interactive app launcher | `./run.sh` → `python -m wp_log_parser app --config ./config.json` | wpcli/rest | Supported | `run.sh` only starts the TTY app; no background daemon. |

## Known Limitations (Current)

- `run.sh` opens the interactive TTY app only; it does **not** directly run `publish-ics`, `update-today-ics`, or `run-ics-service`.
- `install.sh` installs dependencies and optionally runs `init-config --wizard`, but it does not validate WordPress/CalDAV connectivity end-to-end.
- `publish-ics` requires `--days`; there is no implicit default on that command.
- `post-to-ics` requires `--post-id`; there is no silent fallback to an arbitrary post.
- `doctor` validates configuration/environment checks but does not execute a full fetch→parse→export simulation.
- Automatic tombstone cleanup for `caldav_deletion_mode: "cancel"` is not implemented yet.

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
- `sync-caldav` – incremental event-level CalDAV synchronization

> Note: if you choose `caldav_deletion_mode: "cancel"`, removed entries are kept as CANCELLED tombstones in `index.events` (while `index.posts` ownership for removed posts is dropped). Tombstone cleanup is not implemented yet.

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


### No timed entries found in sampled posts

- Connection can still be healthy while sampled posts contain no diary-style time lines.
- Verify target posts begin entries with `H:MM` or `HH:MM`.

### CalDAV not configured

- `ics_base_url` is for subscribing to generated ICS files.
- `caldav_url` is for uploading events to a CalDAV collection.
- Configure `caldav_url`, `caldav_username`, and `caldav_password` before sync.

### WordPress post list shows unexpected posts

- Confirm your fetch mode and credentials/path.
- In wp-cli mode, verify command permissions and accessible WordPress path.

### Caddy/service restart requires sudo

- Restart system-managed services with appropriate elevated privileges.

## Debugging

- Add `--debug` to these commands:
  - `sync-caldav`
  - `run-today`
  - `post-to-ics`
  - `publish-ics`
- `--debug` prints a human-readable diagnostics header (selected config path, sanitized config summary, WordPress mode, timezone, output/error directories, deletion mode, dry-run state, operation counts, and index path when available).
- A sanitized snapshot is always written to:
  - `<error_dir>/last_run.json`
- On failures, a timestamped copy is also written:
  - `<error_dir>/debug_YYYYMMDDTHHMMSSZ.json`
- Snapshot content includes:
  - UTC timestamp, command, success/failure, dry-run, sanitized config, result summary, processed post IDs (when known), changed post count, CalDAV counts, index path, and sanitized error traceback on failures.
- Redaction rules:
  - Password/token-like fields (for example `app_password`, `caldav_password`) are redacted as `***` when non-empty and `\"\"` when empty.
  - Raw post content and CalDAV ICS payload bodies are intentionally excluded.
- When reporting bugs, share `errors/last_run.json` (or your configured `error_dir/last_run.json`).

---

## Getting Started Guide

For a step-by-step setup and first run walkthrough, see:

- [Getting Started](./GETTING_STARTED.md)

---

## License

MIT
