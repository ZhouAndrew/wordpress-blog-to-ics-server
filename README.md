# WordPress Daily Log → ICS Exporter

This project parses daily logs stored in WordPress Gutenberg `post_content` and converts them into structured events and ICS output.

## Rules implemented

- Parse only `wp:paragraph` blocks containing `<p>...</p>`.
- Accept only paragraphs that start with `H:MM` or `HH:MM`.
- Normalize time to `HH:MM`.
- Keep summary exactly as text after the leading time.
- Ignore non-paragraph blocks (`wp:file`, `wp:image`, `wp:list`, `wp:heading`) and paragraph blocks without a valid leading time.
- Infer event end time from the next entry: `event[i].end = event[i+1].start`.
- Keep last event open (`end_time = null`, `status = needs_review`).
- ICS exports one `VEVENT` per entry:
  - always includes `DTSTART`
  - includes `DTEND` only when `end_time` exists
  - uses deterministic UIDs

## Usage

```bash
python3 parser.py
```

The script prints:

1. JSON output (`entries`, `ignored_blocks`, `ics_preview`)
2. Generated ICS preview string

## Output contract

Each entry includes:

- `date`
- `start_time`
- `end_time` (or `null`)
- `summary`
- `raw`
- `status` (`ready` or `needs_review`)

