# WordPress log to ICS rules

This repository parses WordPress daily logs from Gutenberg `post_content` and converts them into structured events and ICS output.

## Source format

* Input is raw WordPress `post_content`
* Logs are usually stored in Gutenberg paragraph blocks
* Example:

  * `<p>07:45 Breakfast</p>`
  * `<p>8:30 Enabled Thunderbird on laptop</p>`

## Log detection

A paragraph is a valid log entry only if its visible text starts with a time in:

* `H:MM`
* `HH:MM`

Normalize to:

* `HH:MM`

## Event summary

* The event summary is the paragraph text after the leading time
* Do not paraphrase or summarize unless asked

## Ignore

Do not treat these as log entries:

* `wp:file`
* `wp:image`
* `wp:list`
* `wp:heading`
* paragraphs without leading time

## Event duration rule

* One event ends when the next event begins
* Therefore:

  * `entry[i].end = entry[i+1].start`
* The last event has no inferred end unless a separate fallback rule is enabled

## ICS export rules

* Build a valid `VCALENDAR`
* Export one `VEVENT` per parsed log entry
* Always include `DTSTART`
* Include `DTEND` only when inferred from the next event
* Keep local date from the associated post date
* Escape special ICS characters safely
* Use deterministic UID generation when possible

## Output contract

Default parser result should contain:

* `entries`
* `ignored_blocks`
* `ics_preview`

Each entry should contain:

* `date`
* `start_time`
* `end_time` or null
* `summary`
* `raw`
* `status`

## Status values

Use:

* `ready` for entries with inferred start and end
* `needs_review` for the last entry without inferred end
