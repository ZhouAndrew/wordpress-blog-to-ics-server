# Getting Started

This guide gets you from zero to generated `.ics` files using `wp_log_parser`.

Estimated time: 10–20 minutes.

---

## 1) Set up your environment

```bash
git clone <your-repo-url>
cd wordpress-blog-to-ics-server
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install requests pytest
```

---

## 2) Create your config

Run the setup wizard:

```bash
python -m wp_log_parser init-config --wizard --config ./config.json
```

When prompted, choose one mode:

- **`wpcli`** if this machine has local WordPress + wp-cli access
- **`rest`** if you are connecting to a remote WordPress site

Validate setup:

```bash
python -m wp_log_parser validate-config --config ./config.json
```

If validation reports errors, fix config values first before continuing.

---

## 3) Fetch a post

Use a known WordPress post ID:

```bash
python -m wp_log_parser fetch-post --config ./config.json --post-id 10213
```

If you do not know the post ID, use interactive selection:

```bash
python -m wp_log_parser fetch-post --config ./config.json --select-post-id
```

What to confirm:

- The command returns the expected post title/date/content summary
- The post contains time-based lines such as `07:45 Breakfast`

---

## 4) Parse and preview timeline entries

```bash
python -m wp_log_parser parse-post --config ./config.json --post-id 10213
```

What to look for:

- Entries with `start_time`
- `end_time` inferred from next entry (or explicit range)
- A final entry that may require fallback/end-time handling

---

## 5) Generate ICS for one post

```bash
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213
```

Verbose example:

```bash
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213 --verbose
```

Expected result:

- A file like `YYYY-MM-DD_post_10213_<slug>.ics` in `output_dir`

---

## 6) Run today’s log workflow

```bash
python -m wp_log_parser run-today --config ./config.json
```

This is the quickest daily operation when your config is already set.

---

## 7) Publish recent posts + generate indexes

```bash
python -m wp_log_parser publish-ics --config ./config.json --days 7
```

Expected output artifacts in `output_dir`:

- Per-post `.ics` files
- `index.json`
- `index.html`
- `today.ics` (if a valid candidate exists)

---

## 8) Refresh `today.ics` explicitly

```bash
python -m wp_log_parser update-today-ics --config ./config.json
```

Optional symlink mode:

```bash
python -m wp_log_parser update-today-ics --config ./config.json --mode symlink
```

---

## 9) (Optional) Run local ICS service

```bash
python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 300 --host 127.0.0.1 --port 5333
```

Then open:

- `http://127.0.0.1:5333/index.html`
- `http://127.0.0.1:5333/today.ics`

---

## Practical tips

- Start with one known-good post before automating everything.
- Keep `timezone` in `config.json` explicit and correct.
- Use `--verbose` when available during first setup.
- Subscribe calendar clients to `today.ics` (stable URL), not per-post filenames.

---

## Quick command checklist

```bash
python -m wp_log_parser init-config --wizard --config ./config.json
python -m wp_log_parser validate-config --config ./config.json
python -m wp_log_parser fetch-post --config ./config.json --post-id 10213
python -m wp_log_parser parse-post --config ./config.json --post-id 10213
python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213
python -m wp_log_parser publish-ics --config ./config.json --days 7
python -m wp_log_parser update-today-ics --config ./config.json
```
