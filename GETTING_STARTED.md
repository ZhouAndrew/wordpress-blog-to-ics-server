# Getting Started

This guide gets you from a fresh clone to generated `.ics` files using the Phase 2 package CLI.

Estimated time: 10–20 minutes, plus time to confirm your WordPress credentials/path.

---

## 1) Set up your environment

```bash
git clone <your-repo-url>
cd wordpress-blog-to-ics-server
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

Convenience alternative on Unix-like systems:

```bash
./install.sh
```

`install.sh` creates `.venv`, installs dependencies, creates runtime directories, and starts the setup wizard if `config.json` is missing. It does not prove WordPress or CalDAV connectivity by itself.

---

## 2) Create your local config (untracked)

Default config:

```bash
python -m wp_log_parser init-config --config ./config.json
```

Interactive wizard/repair flow:

```bash
python -m wp_log_parser init-config --wizard --config ./config.json
```

Then edit `config.json` for your environment.

Choose one WordPress source mode:

- **`wpcli`**: use when this machine has local WordPress filesystem access and `wp-cli` can read posts. Set `wp_cli_path` and `wp_path`.
- **`rest`**: use for remote WordPress. Set `base_url`, `username`, and `app_password`.

REST mode requires authenticated WordPress application-password access. Anonymous REST reads are not the supported assumption.

Validate setup:

```bash
python -m wp_log_parser validate-config --config ./config.json
```

If validation reports errors, fix config values before continuing. Config validation is strict for modes, parsing patterns, CalDAV deletion mode, overlap/export policies, and integer fields.

---

## 3) Confirm the parser input format

The source is raw WordPress `post_content`, usually Gutenberg paragraph blocks. Valid log entries start with a time.

Supported point formats:

- `7:45 Breakfast`
- `07:45 Breakfast`

Supported range formats:

- `18:00-18:23 Dinner`
- `18:00 - 18:23 Dinner`
- `18:00–18:23 Dinner`
- `18:00—18:23 Dinner`
- `18:00~18:23 Dinner`

Range entries define their own end time. Point entries infer their end from the next entry. The last point entry may remain `needs_review` unless fallback duration/export policy handles it.

Ignored blocks can include `wp:file`, `wp:image`, `wp:list`, `wp:heading`, other non-paragraph blocks, empty paragraphs, and paragraphs without a leading time. When `save_ignored_blocks` is true, ignored-block reports are written next to generated artifacts.

---

## 4) Fetch a post

Use a known WordPress post ID:

```bash
python -m wp_log_parser fetch-post --config ./config.json --post-id 10213
```

If you do not know the post ID and you have a TTY, use interactive selection:

```bash
python -m wp_log_parser fetch-post --config ./config.json --select-post-id
```

What to confirm:

- The command returns the expected post ID/content.
- The post contains lines such as `07:45 Breakfast` or `18:00-18:23 Dinner`.

---

## 5) Parse and preview timeline entries

```bash
python -m wp_log_parser parse-post --config ./config.json --post-id 10213
```

What to look for:

- Entries include `date`, `start_time`, `end_time`, `summary`, `raw`, and `status`.
- `ready` entries have explicit or inferred end times.
- `needs_review` entries need operator attention or export-policy handling.
- `ignored_blocks` reports explain skipped Gutenberg blocks/paragraphs.

---

## 6) Generate ICS for one post

```bash
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213
```

Verbose example:

```bash
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213 --verbose
```

Expected result in `output_dir`:

- A file like `YYYY-MM-DD_post_10213_<slug>.ics`
- A matching `*.parsed.json` parser artifact
- A matching `*.ignored.json` file if `save_ignored_blocks` is true

`post-to-ics` requires `--post-id`; it does not silently choose an arbitrary post.

---

## 7) Publish recent posts and generate indexes

```bash
python -m wp_log_parser publish-ics --config ./config.json
```

Verbose example:

```bash
python -m wp_log_parser publish-ics --config ./config.json --verbose
```

Expected artifacts in `output_dir`:

- Per-post `.ics` files
- Per-post `*.parsed.json` files
- Per-post `*.ignored.json` files when enabled
- `index.json`
- `index.html`
- `today.ics` if at least one generated file matches the local date in `timezone`

`publish-ics` defaults to a 7-day window; pass `--days` when you need a different recent-post window.

---

## 8) Refresh `today.ics` explicitly

```bash
python -m wp_log_parser update-today-ics --config ./config.json
```

Verbose copy mode:

```bash
python -m wp_log_parser update-today-ics --config ./config.json --verbose
```

Optional symlink mode:

```bash
python -m wp_log_parser update-today-ics --config ./config.json --mode symlink
```

Optional post-ID disambiguation:

```bash
python -m wp_log_parser update-today-ics --config ./config.json --post-id 10213
```

Deterministic today behavior:

- The date is computed in your configured `timezone`.
- Only generated files matching that date are candidates.
- Alias files such as `today.ics`, `latest.ics`, and `all.ics` are never source candidates.
- `--post-id` selects a specific generated file for that post when present.
- Without `--post-id`, candidates are sorted deterministically by date, post ID, and filename.

---

## 9) Run the local ICS service

```bash
python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 300 --host 127.0.0.1 --port 5333
```

For the alpha verification checklist, a shorter interval is useful:

```bash
python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 60
```

Then open:

- `http://127.0.0.1:5333/index.html`
- `http://127.0.0.1:5333/today.ics`

Stop the service with Ctrl+C.

---

## 10) Optional one-shot daily flow

If your config is already valid and you want the today pipeline directly:

```bash
python -m wp_log_parser run-today --config ./config.json
```

For publish verification, prefer the explicit one-shot publish flow:

```bash
python -m wp_log_parser publish-ics --config ./config.json --verbose
python -m wp_log_parser update-today-ics --config ./config.json --verbose
```

---

## 11) Optional CalDAV sync

Dry-run is the safe default:

```bash
python -m wp_log_parser sync-caldav --config ./config.json
python -m wp_log_parser sync-caldav --config ./config.json --dry-run
```

Real sync requires configured `caldav_url`, `caldav_username`, and `caldav_password`, plus a recent compatible dry-run marker unless forced:

```bash
python -m wp_log_parser sync-caldav --config ./config.json --apply
python -m wp_log_parser sync-caldav --config ./config.json --apply --force-real-sync
```

---

## Fresh-clone command checklist

```bash
python -m wp_log_parser init-config --config ./config.json
python -m wp_log_parser validate-config --config ./config.json
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213 --verbose
python -m wp_log_parser publish-ics --config ./config.json --verbose
python -m wp_log_parser update-today-ics --config ./config.json --verbose
python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 60
```

If you do not have real WordPress/wp-cli or REST credentials on the current machine, you can still run CLI help, unit tests, and docs regression tests; real fetch/export validation needs an actual WordPress source.

---

## Practical tips

- Start with one known-good post before automating everything.
- Keep `timezone` explicit and correct.
- Use `--verbose` during first setup.
- Subscribe calendar clients to `today.ics` for a stable URL, not per-post filenames.
- Keep `config.json`, generated `.ics`, and generated indexes untracked.

---

## Credential exposure response

If credentials are leaked (repo commit, terminal logs, screenshots, or chat), rotate passwords/tokens immediately and do not reuse compromised values. Then update local `config.json` and re-run `validate-config`.
