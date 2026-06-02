# WordPress Blog Log → ICS CLI

Convert diary-style WordPress posts into structured timeline events and `.ics` calendar files.

This project is for developers and power users who already work with WordPress and command-line workflows.

---

## Status

**Pre-alpha / internal validation build**

Phase 2 has moved the main publish workflow into the `wp_log_parser` package and CLI. The repository is still **not public-alpha ready** until the maintainer completes a fresh-clone validation run against a real WordPress source and, optionally, a real CalDAV collection.

## Before v0.1.0-alpha

### CI-covered gates

- [x] [CI Smoke] CLI help and usage guardrails
- [x] [CI Smoke] `post-to-ics` command dispatch (stubbed, no WordPress required)
- [x] [CI Smoke] `publish-ics` command dispatch (stubbed, no WordPress required)
- [x] [CI Smoke] `update-today-ics` command dispatch (stubbed/local files only)
- [x] [CI Smoke] `run-ics-service` command dispatch (stubbed, no WordPress required)
- [x] [CI Smoke] parser contract, range formats, config validation, and docs regression checks
- [x] [CI Smoke] interactive app menu dispatch for publish, today alias, service, and CalDAV guardrails

### Manual gates still required

- [ ] [Local Manual] fresh clone on target host
- [ ] [Local Manual] `./install.sh` and `./run.sh`
- [ ] [Local Manual] setup wizard with real WordPress settings
- [ ] [Local Manual] `validate-config` against the target environment
- [ ] [Local Manual] real WordPress fetch/parse/export for a known post
- [ ] [Local Manual] `publish-ics`, `update-today-ics`, and generated artifacts (`.ics`, `today.ics`, `index.json`, `index.html`)
- [ ] [Local Manual] local HTTP service subscription
- [ ] [Local Manual] optional CalDAV setup, doctor, dry-run sync, real sync, and second-sync idempotency
- [ ] [Local Manual] Ctrl+C handling and secret redaction in local logs/artifacts

## Project Overview

`wp_log_parser` uses a modular pipeline:

WordPress source → parser → structured events → exporters / sync → services

- **sources** fetch WordPress data using `wpcli` or REST.
- **parsers** extract log entries from raw WordPress/Gutenberg content.
- **exporters** generate JSON diagnostics and ICS files.
- **sync** modules synchronize structured events to CalDAV.
- **services** orchestrate publish/update loops and static HTTP serving.

The CLI calls the service layer; parsers do not fetch data, exporters do not parse data, and the HTTP server does not call WordPress APIs directly.

Typical use cases:

- Personal daily log → calendar timeline
- Local automation for publishing fresh ICS feeds
- Stable `today.ics` URL for calendar subscriptions

---

## Fresh-clone setup and verification

These commands describe the real Phase 2 workflow. Replace post ID `10213` with a known WordPress post that contains timed log paragraphs.

```bash
# 1) Clone and install
git clone <your-repo-url>
cd wordpress-blog-to-ics-server
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt

# 2) Create and edit config
python -m wp_log_parser init-config --config ./config.json
# or: python -m wp_log_parser init-config --wizard --config ./config.json
$EDITOR ./config.json

# 3) Validate config and environment
python -m wp_log_parser validate-config --config ./config.json

# 4) Export one known post
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213 --verbose

# 5) Publish recent posts and local index artifacts
python -m wp_log_parser publish-ics --config ./config.json --days 7 --verbose

# 6) Refresh the stable today alias
python -m wp_log_parser update-today-ics --config ./config.json --verbose

# 7) Run the local service loop and HTTP server
python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 60
```

The final command runs until interrupted. During first setup you can also use `./install.sh` followed by `./run.sh`; `run.sh` starts the interactive TTY app (`python -m wp_log_parser app --config ./config.json`) and does not start a background daemon.

---

## Requirements

### Runtime

- Python **3.10+** (3.11 recommended)
- `pip`
- Dependencies from `requirements.txt`

### Continuous Integration (CI)

GitHub Actions CI runs on every `pull_request` and every push to `main`. The workflow sets up Python 3.11, installs `requirements.txt`, and runs `pytest -vv`.

### For `wpcli` mode

Use `wpcli` when running on a host with local WordPress filesystem access.

- `wp-cli` installed and available on `PATH` (or configured via `wp_cli_path`)
- Local filesystem access to the WordPress installation
- `wp_path` set to the WordPress root containing `wp-config.php`

### For `rest` mode

Use `rest` for remote WordPress access.

- Reachable WordPress site URL in `base_url`
- WordPress username in `username`
- WordPress **application password** in `app_password`
- The account must be authenticated and authorized to read the posts you want to export

REST mode is not anonymous scraping; expect 401/403 errors until application-password access is configured correctly.

---

## Quick Start (interactive app)

Unix-like shells:

```bash
./install.sh
./run.sh
```

Windows:

```bat
install.bat
run.bat
```

Inside the interactive app (`python -m wp_log_parser app`) you can run health checks, repair/setup configuration, preview recent posts, publish local ICS files, update `today.ics`, run the local service, and run CalDAV dry-run/real sync flows with guardrails.

---

## Configuration (`config.json`, untracked)

Create a local config:

```bash
python -m wp_log_parser init-config --config ./config.json
```

Or create/repair it interactively:

```bash
python -m wp_log_parser init-config --wizard --config ./config.json
```

Validate it before running fetch/export commands:

```bash
python -m wp_log_parser validate-config --config ./config.json
```

`example.config.json` is a template only. Keep real credentials in local `config.json`, which should stay untracked.

### Strict config behavior

`load_config` validates config values before commands run:

- `wordpress_mode` must be `wpcli` or `rest`.
- `log_format` must be `gutenberg_raw` or `rendered_html`.
- `overlap_policy` must be `warn`, `needs_review`, or `error`.
- `review_entry_export_mode` must be `include`, `skip`, or `error`.
- `caldav_deletion_mode` must be `delete` or `cancel`.
- `default_last_event_minutes` and `post_selection_count` must be integers.
- CalDAV string fields must be strings.
- `custom_parsing_patterns` must be a list; each object needs a string `regex`, a `kind`/`type` of `point` or `range`, a named `start` group, and range patterns also need a named `end` group.

Invalid config fails fast with an explicit error. Commands do not silently invent WordPress sources or fallback post IDs.

### Common config fields

- `wordpress_mode`: `wpcli` or `rest`
- `wp_cli_path`: path/command for wp-cli (`wp`)
- `wp_path`: WordPress install path (required for `wpcli` mode)
- `base_url`: WordPress base URL (required for `rest` mode)
- `username`, `app_password`: REST credentials (application-password access)
- `output_dir`: generated files destination
- `error_dir`, `logs_dir`: debug snapshots and runtime logs
- `timezone`: timezone used for local dates and exported events
- `default_last_event_minutes`: fallback duration for the final event when enabled by timeline/export policy
- `post_selection_count`: recent-post selection/listing size
- `allow_empty_summary`: allow entries with no text after the time
- `auto_cross_midnight`: allow ranges/timeline inference to cross midnight when needed
- `save_ignored_blocks`: write ignored-block diagnostics
- `custom_parsing_patterns`: optional custom regex parsing rules, matched before built-ins
- `overlap_policy`: handling for overlapping events (`warn`, `needs_review`, `error`)
- `review_entry_export_mode`: exporter handling for `needs_review` entries (`include`, `skip`, `error`)
- `ics_base_url`: public base URL used in generated indexes
- `caldav_url`, `caldav_username`, `caldav_password`: CalDAV sync credentials
- `caldav_uid_domain`: UID suffix domain for CalDAV event resources
- `caldav_index_path`: local CalDAV sync index JSON file path
- `caldav_deletion_mode`: deletion strategy for removed events (`delete` or `cancel`)

---

## CLI Usage

General help:

```bash
python -m wp_log_parser --help
```

### Fetch and inspect one post

```bash
python -m wp_log_parser fetch-post --config ./config.json --post-id 10213
```

Interactive selection from recent posts:

```bash
python -m wp_log_parser fetch-post --config ./config.json --select-post-id
```

### Parse a post into structured timeline output

```bash
python -m wp_log_parser parse-post --config ./config.json --post-id 10213
```

### Export one post to ICS

```bash
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213 --verbose
```

`post-to-ics` requires `--post-id`; it will not silently fall back to an arbitrary post.

### Publish ICS for recent posts

```bash
python -m wp_log_parser publish-ics --config ./config.json --days 7
python -m wp_log_parser publish-ics --config ./config.json --days 7 --verbose
```

`publish-ics` requires `--days`. It fetches recent posts, exports eligible posts, writes per-post ICS files, writes parsed JSON/ignored-block reports when configured, generates `index.json` and `index.html`, and attempts to refresh `today.ics` when a deterministic candidate exists.

### Refresh `today.ics`

```bash
python -m wp_log_parser update-today-ics --config ./config.json
python -m wp_log_parser update-today-ics --config ./config.json --verbose
python -m wp_log_parser update-today-ics --config ./config.json --mode symlink
```

Optional disambiguation when multiple files exist for the local date:

```bash
python -m wp_log_parser update-today-ics --config ./config.json --post-id 10213
```

### Run the local ICS service

```bash
python -m wp_log_parser run-ics-service --config ./config.json
python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 300 --host 127.0.0.1 --port 5333
```

Service mode periodically publishes recent posts and serves `output_dir` over HTTP. Open:

- `http://127.0.0.1:5333/index.html`
- `http://127.0.0.1:5333/today.ics`

### Incremental CalDAV sync

Dry-run (safe; writes no CalDAV changes and refreshes the real-sync marker):

```bash
python -m wp_log_parser sync-caldav --config ./config.json
python -m wp_log_parser sync-caldav --config ./config.json --dry-run
```

Real sync (requires complete CalDAV config and a recent compatible dry-run marker unless forced):

```bash
python -m wp_log_parser sync-caldav --config ./config.json --apply
python -m wp_log_parser sync-caldav --config ./config.json --apply --force-real-sync
```

### Config operations and doctor checks

```bash
python -m wp_log_parser config --config ./config.json get timezone
python -m wp_log_parser config --config ./config.json set timezone Asia/Seoul
python -m wp_log_parser config --config ./config.json edit
python -m wp_log_parser doctor --config ./config.json
python -m wp_log_parser doctor --config ./config.json --full
```

`doctor` validates environment/configuration checks. It does not execute a full fetch→parse→export simulation.

---

## Parser contract

Input is raw WordPress `post_content`, usually Gutenberg paragraph blocks. A paragraph is a log entry only when the visible paragraph text starts with a supported time. Non-paragraph blocks (`wp:file`, `wp:image`, `wp:list`, `wp:heading`, and other unsupported block types) and paragraphs without a leading time are ignored with reasons.

Supported built-in point formats:

- `7:45 Breakfast`
- `07:45 Breakfast`

Supported built-in range formats (matched before point formats):

- `18:00-18:23 Dinner`
- `18:00 - 18:23 Dinner`
- `18:00–18:23 Dinner`
- `18:00—18:23 Dinner`
- `18:00~18:23 Dinner`

Time values normalize to `HH:MM`. The event summary is the paragraph text after the leading time/range; the parser does not paraphrase it.

Parsing order:

1. Custom patterns from `custom_parsing_patterns`
2. Built-in range pattern
3. Built-in point pattern

Default parser output is represented as structured entries plus ignored-block diagnostics and, in CLI/export flows, ICS/JSON previews or artifacts. Each entry contains `date`, `start_time`, `end_time` (or `null`), `summary`, `raw`, and `status`.

Status values:

- `ready`: entry has an end time, either explicit from a range or inferred from the next entry
- `needs_review`: entry lacks an inferred/explicit end or was marked for review by overlap policy

Event duration rules:

- A point entry ends when the next event begins.
- Range entries define explicit start/end and do not rely on the next entry for their end time.
- The final point entry has no inferred end unless fallback duration handling is enabled by config/export policy.

---

## Deterministic `today.ics` behavior

`today.ics` is selected from generated files whose filename date matches the current local date in `timezone`.

- The local date comes from `timezone`, not from UTC unless `timezone` is `UTC`.
- Generated aliases skip `today.ics`, `latest.ics`, and `all.ics` as source candidates.
- If `--post-id` is supplied to `update-today-ics`, the matching post file is selected.
- Without `--post-id`, candidates are sorted deterministically by date, post ID, and filename, newest/highest first.
- In the interactive app, when multiple same-day candidates exist, post metadata is used to suggest the newest modified/published candidate and the user can disambiguate.

`publish-ics` tries to refresh `today.ics` after writing recent post files. If no file exists for the local date, the command still writes the other publish artifacts and reports the alias refresh warning in verbose mode.

---

## Generated artifacts

Depending on command and config, `output_dir` can include:

- `YYYY-MM-DD_post_<post_id>_<slug>.ics` — one calendar file per exported post
- `today.ics` — stable copy or symlink to the selected file for the local date
- `index.json` — machine-readable publish index
- `index.html` — browser-friendly local subscription/index page
- `*.parsed.json` — structured parser output for an exported post
- `*.ignored.json` — ignored Gutenberg block report when `save_ignored_blocks` is true
- `caldav_sync_index.json` — local CalDAV sync state when CalDAV sync is used

---

## Root scripts and package service status

The supported Phase 2 entry point is the package CLI:

```bash
python -m wp_log_parser <command> ...
```

`install.sh` / `install.bat` and `run.sh` / `run.bat` are convenience launchers for setup and the interactive app. Older root-level prototype scripts are retained for reference/backward compatibility during pre-alpha, but new documentation and validation use the package commands above.

---

## Validation Matrix (Docs ↔ Scripts ↔ CLI)

| Flow | Command / Entry Point | Mode | Expected Status | Notes |
|---|---|---|---|---|
| Create default config | `python -m wp_log_parser init-config --config ./config.json` | local | Supported | Creates a default local file; edit before real WordPress use. |
| Setup wizard | `python -m wp_log_parser init-config --wizard --config ./config.json` | local | Supported | Interactive repair/create flow; preserves unrelated existing fields. |
| Validate config | `python -m wp_log_parser validate-config --config ./config.json` | wpcli/rest | Supported | Fails fast on invalid strict config values or missing runtime dependencies. |
| Fetch source via wp-cli | `python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213` | `wordpress_mode=wpcli` | Supported | `--post-id` is required for `post-to-ics`. |
| Fetch source via REST | `python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213` | `wordpress_mode=rest` | Supported | Requires authenticated `base_url`, `username`, `app_password`. |
| Local ICS batch publish | `python -m wp_log_parser publish-ics --config ./config.json --days 7` | wpcli/rest | Supported | Generates per-post ICS + `index.json` + `index.html`; auto-refreshes `today.ics` when possible. |
| Today alias update | `python -m wp_log_parser update-today-ics --config ./config.json` | local files | Supported | Use `--mode copy` (default) or `--mode symlink`; optional `--post-id` disambiguates. |
| Service mode | `python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 300 --host 127.0.0.1 --port 5333` | wpcli/rest | Supported | Periodic publish plus local HTTP server. |
| One-shot publish flow | `python -m wp_log_parser publish-ics --config ./config.json --days 7 --verbose` | wpcli/rest | Supported | Best non-daemon verification path for fresh clones. |
| Dry-run CalDAV sync | `python -m wp_log_parser sync-caldav --config ./config.json --dry-run` | wpcli/rest | Supported | Reports planned changes; does not write CalDAV resources. |
| Real CalDAV sync | `python -m wp_log_parser sync-caldav --config ./config.json --apply` | wpcli/rest | Supported with preconditions | Requires CalDAV credentials and either a recent compatible dry-run marker or `--force-real-sync`. |
| Interactive app launcher | `./run.sh` → `python -m wp_log_parser app --config ./config.json` | wpcli/rest | Supported | `run.sh` only starts the TTY app; no background daemon. |

---

## Known Limitations (Current)

- This is a pre-alpha validation build, not a production-readiness claim.
- Fresh-clone verification against real WordPress/wp-cli or authenticated REST still requires maintainer/local credentials.
- REST mode requires authenticated application-password access; anonymous REST reads are not the supported assumption.
- `run.sh` opens the interactive TTY app only; it does **not** directly run `publish-ics`, `update-today-ics`, or `run-ics-service`.
- `install.sh` installs dependencies and optionally runs `init-config --wizard`, but it does not validate WordPress/CalDAV connectivity end-to-end.
- `publish-ics` requires `--days`; there is no implicit default on that command.
- `post-to-ics` requires `--post-id`; there is no silent fallback to an arbitrary post.
- `doctor` validates configuration/environment checks but does not execute a full fetch→parse→export simulation.
- The final point entry may remain `needs_review` unless fallback duration/export policy includes it as desired.
- Automatic tombstone cleanup for `caldav_deletion_mode: "cancel"` is not implemented yet.

---

## Command Reference

- `init-config` – create config (optionally with interactive wizard)
- `validate-config` – validate config and environment dependencies
- `fetch-post` – fetch and display one post by ID or interactive selection
- `parse-post` – parse one post and show structured entries
- `export-ics` – generate ICS from existing entries JSON input
- `run-today` – fetch today’s post and run the today pipeline
- `post-to-ics` – fetch + parse + export one explicit post to ICS
- `publish-ics` – generate ICS files for recent posts and index artifacts
- `update-today-ics` – create/update `today.ics` alias from existing local files
- `run-ics-service` – periodic publish + static HTTP server
- `sync-caldav` – incremental event-level CalDAV synchronization
- `doctor` – environment/config diagnostics
- `config` – get/set/edit local config values
- `app` – interactive TTY app

> Note: if you choose `caldav_deletion_mode: "cancel"`, removed entries are kept as CANCELLED tombstones in `index.events` while `index.posts` ownership for removed posts is dropped. Tombstone cleanup is not implemented yet.

---

## Debugging

Add `--debug` to these commands:

```bash
python -m wp_log_parser sync-caldav --config ./config.json --debug
python -m wp_log_parser run-today --config ./config.json --debug
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213 --debug
python -m wp_log_parser publish-ics --config ./config.json --days 7 --debug
```

`--debug` prints a human-readable diagnostics header and writes a sanitized snapshot to `<error_dir>/last_run.json`. On failures, a timestamped copy is also written to `<error_dir>/debug_YYYYMMDDTHHMMSSZ.json`.

Redaction rules:

- Password/token-like fields (for example `app_password`, `caldav_password`) are redacted as `***` when non-empty and `""` when empty.
- Raw post content and CalDAV ICS payload bodies are intentionally excluded.

When reporting bugs, share `errors/last_run.json` or the equivalent file under your configured `error_dir`.

---

## Troubleshooting

### `wp-cli not found`

- Confirm `wp` is installed: `wp --info`
- Set `wp_cli_path` explicitly in `config.json`

### `Path exists but does not look like WordPress`

- Verify `wp_path` points to your real WordPress root where `wp-config.php` is located.

### REST authentication errors (401/403)

- Confirm `base_url` is correct.
- Recreate the WordPress application password.
- Ensure the username can read target posts.

### No entries parsed from a post

- Confirm log lines begin with `H:MM`, `HH:MM`, or a supported range format.
- Verify logs are in Gutenberg paragraph content.
- Check whether custom parsing patterns are too strict.

### `today.ics` missing after publish

- Run manually: `python -m wp_log_parser update-today-ics --config ./config.json`
- Confirm there is at least one eligible `.ics` file in `output_dir` whose filename date matches the local date in `timezone`.

### Command seems to run but no files appear

- Verify `output_dir` in `config.json`.
- Use `--verbose` command variants where available.
- Check whether the selected post actually contains timed log entries.

### CalDAV not configured

- `ics_base_url` is for subscribing to generated ICS files.
- `caldav_url` is for uploading events to a CalDAV collection.
- Configure `caldav_url`, `caldav_username`, and `caldav_password` before sync.

---

## Getting Started Guide

For a step-by-step setup and first run walkthrough, see:

- [Getting Started](./GETTING_STARTED.md)

---

## License

MIT

## Credential exposure response

If any credential is accidentally committed, shared, or exposed in logs/artifacts, rotate it immediately before continuing work:

- WordPress `app_password`
- CalDAV password/token
- Any API token or local secret used by this project

After rotation, update your local `config.json`, re-run validation, and confirm old credentials no longer work.
