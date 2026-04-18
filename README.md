# WordPress Daily Log → ICS Exporter

This project parses daily logs stored in WordPress posts (Gutenberg format) and converts them into structured events and ready-to-publish ICS calendar files.

## ✨ Overview

Daily activities are recorded in WordPress posts as simple paragraph blocks:

```html
<!-- wp:paragraph -->
<p>07:45 Breakfast and baked pizza</p>
<!-- /wp:paragraph -->
```

This project transforms those logs into calendar events by applying a simple rule:

> **The end time of one event is the start time of the next event.**

## 🧠 Core Concept

Logs are interpreted as a **sequence of time-based events**.

Example:

```text
07:45 Breakfast
08:30 Enabled Thunderbird
```

Becomes:

| Event               | Start | End       |
| ------------------- | ----- | --------- |
| Breakfast           | 07:45 | 08:30     |
| Enabled Thunderbird | 08:30 | (unknown) |

## 📥 Input Format

* Source: WordPress `post_content`
* Format: Gutenberg blocks
* Primary block used: `wp:paragraph`

## ✅ Log Detection Rules

A paragraph is considered a valid log entry if it starts with:

* `H:MM` (example: `8:30`)
* `HH:MM` (example: `07:45`)

Normalization:

```text
8:30 → 08:30
```

## ❌ Ignored Content

The following block types are ignored:

* `wp:file`
* `wp:image`
* `wp:list`
* `wp:heading`
* paragraphs without a leading time

## ⏱ Event Construction

Events are built using sequential inference:

```text
event[i].end = event[i+1].start
```

The last event has no inferred end unless a fallback duration is configured.

## 📤 Output Format

### Structured parser output

Default parser output contains:

* `entries`
* `ignored_blocks`
* `ics_preview`

Each entry includes:

* `date`
* `start_time`
* `end_time` (or `null`)
* `summary`
* `raw`
* `status` (`ready` or `needs_review`)

### ICS export

Generates valid `VCALENDAR` content with one `VEVENT` per parsed entry.

## Local CLI Tooling

The repository now includes a configurable local CLI package: `wp_log_parser/`.

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install requests pytest
```

### Configuration wizard

```bash
python -m wp_log_parser init-config --wizard --config ./config.json
```

Wizard features:

* numbered choices for enum prompts
* `y/yes/n/no` support
* Enter accepts defaults
* immediate validation loops on invalid input
* summary output with masked application password

### Dependency checks

```bash
python -m wp_log_parser validate-config --config ./config.json
```

### wp-cli mode

```bash
python -m wp_log_parser fetch-post --config ./config.json --post-id 123
```

### Interactive post selection

```bash
python -m wp_log_parser fetch-post --config ./config.json --select-post-id
```

The number of posts returned in the interactive selector is controlled by `post_selection_count` in `config.json`.

### REST mode

```bash
python -m wp_log_parser run-today --config ./config.json
```

### Example command set

```bash
python -m wp_log_parser init-config --wizard
python -m wp_log_parser validate-config --config ./config.json
python -m wp_log_parser fetch-post --config ./config.json --post-id 10213
python -m wp_log_parser fetch-post --config ./config.json --select-post-id
python -m wp_log_parser parse-post --config ./config.json --post-id 10213
python -m wp_log_parser run-today --config ./config.json
```

## Round 2 Commands

### `post-to-ics`

Export one specific post to one ICS file.

```bash
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213 --verbose
```

What it does:

1. fetches the post (`wp-cli` or REST, based on config),
2. parses timed Gutenberg paragraph entries,
3. writes one ICS file into `output_dir`.

Generated files:

* `YYYY-MM-DD_post_<post_id>_<slug>.ics`

---

### `publish-ics`

Publish all recent posts in the requested day window and build index artifacts.

```bash
python -m wp_log_parser publish-ics --config ./config.json --days 7
python -m wp_log_parser publish-ics --config ./config.json --days 7 --verbose
```

What it does:

1. finds recent posts,
2. parses each post into entries,
3. writes one `.ics` per post,
4. (optional) writes ignored block details per post when `save_ignored_blocks` is enabled,
5. writes `index.json` and `index.html`,
6. attempts to refresh `today.ics` automatically.

Generated files (in `output_dir`):

* `YYYY-MM-DD_post_<post_id>_<slug>.ics`
* `YYYY-MM-DD_post_<post_id>_<slug>.ignored.json` (if enabled)
* `index.json`
* `index.html`
* `today.ics` (best effort refresh after publish)

---

### `update-today-ics`

Refresh only the `today.ics` alias from existing published files.

```bash
python -m wp_log_parser update-today-ics --config ./config.json
python -m wp_log_parser update-today-ics --config ./config.json --mode symlink
python -m wp_log_parser update-today-ics --config ./config.json --post-id 10213
```

Notes:

* this command validates only the output directory + timezone (it does not require wp-cli/REST connectivity),
* it selects today’s candidate ICS file by date and optional `--post-id`,
* `today.ics` is the recommended stable subscription target for clients.

---

### `run-ics-service`

Run periodic publishing plus local static HTTP serving.

```bash
python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 60
python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 300 --host 0.0.0.0 --port 5333 --verbose
```

Service behavior:

1. runs one initial publish cycle,
2. starts local HTTP server for `output_dir`,
3. waits until the next interval boundary,
4. runs publish cycles repeatedly with drift-aware scheduling.

HTTP serving:

* served directory: `output_dir` from config,
* default bind: `127.0.0.1:5333`,
* all generated `.ics`, `.ignored.json`, `index.json`, `index.html`, `today.ics` are served as static files.

## Thunderbird Subscription

Recommended target:

* Subscribe to `today.ics` (stable URL), not per-post filenames.

Example URLs (depending on your local/public setup):

* `http://127.0.0.1:5333/today.ics`
* `https://your-domain.example/calendars/today.ics`

In Thunderbird (high-level flow):

1. **File** → **New** → **Calendar**
2. choose **On the Network**
3. paste the `today.ics` URL
4. finish setup (name/color/refresh policy)

Why `today.ics`:

* per-post filenames change by date/post,
* `today.ics` stays stable and is refreshed by publish/update workflows.

## Architecture Summary

Core modules used by CLI/service mode:

* `fetcher`  
  Fetches post metadata/content from `wp-cli` or REST and normalizes post dates.
* `parser`  
  Extracts timed events from Gutenberg blocks and builds structured entries + ignored-block diagnostics.
* `ics_exporter`  
  Writes per-post ICS files plus `index.json`, `index.html`, and optional `.ignored.json`.
* `aliases`  
  Selects today's candidate ICS and writes `today.ics` via copy/symlink.
* `service_mode`  
  Runs one-shot publish cycles (`publish_once`), periodic loop scheduling, and local HTTP serving.

### Sample interactive wizard session

```text
Welcome to wp_log_parser setup wizard

1) Fetch mode
Choose how to fetch posts.
  1) wpcli
  2) rest
[default: 1]
> 2

2) WordPress base URL
Example: https://example.com [default: ]
> https://blog.local

Username
WordPress username for REST API. [default: ]
> andrew

Application password
WordPress application password. [default: ]
> ********

8) Environment validation
[OK] module:json: Module available
[ERROR] rest: REST endpoint unreachable (401)

Configuration summary:
  - wordpress_mode: rest
  - app_password: an********rd
```

### Config reference

See `example.config.json` for complete field reference.

Custom parsing patterns (`custom_parsing_patterns`) support two forms:

1. **String regex** (backward-compatible)  
   Treated as `kind=point`.
2. **Object**:

```json
{
  "name": "range_with_label",
  "kind": "range",
  "regex": "^(?P<start>\\d{2}:\\d{2})\\s*to\\s*(?P<end>\\d{2}:\\d{2})\\s+(?P<summary>.+)$"
}
```

Required named groups:

* `start` (required always)
* `end` (required when `kind=range`)
* `summary` (optional; empty summary rules still apply)

### Troubleshooting

* `wp-cli not found`: set `wp_cli_path`.
* `Path exists but does not look like WordPress`: fix `wp_path`.
* `REST authentication failed`: verify username + application password.
* Validation is read-only and does not mutate `config.json`.

## 📄 License

MIT (or your choice)
