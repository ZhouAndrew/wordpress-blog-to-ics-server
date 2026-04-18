# AGENTS.md

## Project overview

This repository parses WordPress daily logs from Gutenberg `post_content` and converts them into structured events and ICS output.

The repository currently contains validated prototype scripts for:

* exporting one post to ICS
* publishing ICS files on a local HTTP server
* generating `today.ics`
* running the full local ICS service

The goal is to integrate these prototypes into the main `wp_log_parser` package and CLI.

## Engineering rules

* Prefer refactoring prototype scripts into package modules instead of copying whole scripts.
* Reuse existing package code whenever practical.
* Keep config compatibility with existing `config.json`.
* Preserve transparent logs for fetch / parse / export / publish steps.
* Prefer `wpcli` mode first.
* Do not silently fall back to an arbitrary post when `--post-id` is missing.
* Use timezone-aware UTC APIs; do not use deprecated `datetime.utcnow()`.
* Keep CLI behavior explicit and easy to debug.
* Minimize duplicated parsing or ICS generation logic.
* Update README when adding or changing user-facing commands.

## WordPress log to ICS rules

### Source format

* Input is raw WordPress `post_content`
* Logs are usually stored in Gutenberg paragraph blocks
* Example:

  * `<p>07:45 Breakfast</p>`
  * `<p>8:30 Enabled Thunderbird on laptop</p>`

### Log detection

A paragraph is a valid log entry only if its visible text starts with a time in:

* `H:MM`
* `HH:MM`

Normalize to:

* `HH:MM`

## Custom parsing support (NEW)

Parsing rules MUST be configurable.

The system SHOULD support multiple regex patterns:

* built-in patterns (default)
* user-defined patterns from config

Each pattern defines:

* name
* regex
* type: "point" or "range"

Matching order:

1. custom patterns
2. built-in patterns

Unmatched lines:

* may be ignored
* or optionally appended to previous entry (configurable) 

### Event summary

* The event summary is the paragraph text after the leading time
* Do not paraphrase or summarize unless asked

### Ignore

Do not treat these as log entries:

* `wp:file`
* `wp:image`
* `wp:list`
* `wp:heading`
* paragraphs without leading time

### Event duration rule

* One event ends when the next event begins
* Therefore:

  * `entry[i].end = entry[i+1].start`
* The last event has no inferred end unless a separate fallback rule is enabled

### ICS export rules

* Build a valid `VCALENDAR`
* Export one `VEVENT` per parsed log entry
* Always include `DTSTART`
* Include `DTEND` when an end time is available
* Usually `DTEND` is inferred from the next event
* For the last event, `DTEND` may be added if a fallback duration is enabled by config
* Keep local date from the associated post date
* Escape special ICS characters safely
* Prefer deterministic UID generation derived from stable event fields when practical

## Extended log format support

In addition to single time entries, the parser MUST support time ranges.

### Time range format (NEW)

Supported examples:

* `18:00-18:23 Dinner`
* `18:00 - 18:23 Dinner`
* `18:00–18:23 Dinner`
* `18:00—18:23 Dinner`
* `18:00~18:23 Dinner`

Rules:

* Range format MUST be matched before single time format
* Range entries define explicit start and end
* Range entries MUST NOT rely on next entry for end time

### Output contract

Default parser result should contain:

* `entries`
* `ignored_blocks`
* `ics_preview`

Each entry should contain:

* `date`
* `start_time`
* `end_time` or `null`
* `summary`
* `raw`
* `status`

### Status values

Use:

* `ready` for entries with inferred start and end
* `needs_review` for the last entry without inferred end

## Expected CLI outcomes

The integrated CLI should support commands such as:

* `python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213`
* `python -m wp_log_parser publish-ics --config ./config.json`
* `python -m wp_log_parser update-today-ics --config ./config.json`
* `python -m wp_log_parser run-ics-service --config ./config.json`

## Validation

Before finishing work:

* run the relevant CLI commands locally when possible
* verify that `.ics`, `today.ics`, `index.json`, and `index.html` are generated
* confirm ignored Gutenberg blocks are reported with reasons
* confirm the local HTTP publishing flow still works

## Output expectations

When summarizing work:

* list files changed
* explain module responsibilities
* include exact validation commands used
* mention any remaining gaps honestly
## Architecture principles (MUST FOLLOW)

The project MUST follow a modular pipeline design:

WordPress source → parser → structured events → exporters / sync

Core modules:

* sources: fetch WordPress data (wp-cli, REST)
* parsers: extract and interpret logs
* exporters: generate output formats (json, ics)
* sync: synchronize to external systems (Radicale / CalDAV)
* services: orchestration, scheduling, HTTP serving

Strict rules:

* parsers MUST NOT fetch data
* exporters MUST NOT parse data
* sync MUST NOT generate ICS directly
* HTTP server MUST NOT call WordPress APIs
* CLI MUST call service layer only

All transformations MUST go through a unified structured model.