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

### REST mode

```bash
python -m wp_log_parser run-today --config ./config.json
```

### Example command set

```bash
python -m wp_log_parser init-config --wizard
python -m wp_log_parser validate-config --config ./config.json
python -m wp_log_parser fetch-post --config ./config.json --post-id 10213
python -m wp_log_parser parse-post --config ./config.json --post-id 10213
python -m wp_log_parser run-today --config ./config.json
```

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

### Troubleshooting

* `wp-cli not found`: set `wp_cli_path`.
* `Path exists but does not look like WordPress`: fix `wp_path`.
* `REST authentication failed`: verify username + application password.
* Validation is read-only and does not mutate `config.json`.

## 📄 License

MIT (or your choice)
