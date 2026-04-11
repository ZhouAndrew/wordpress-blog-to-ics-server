# WordPress Daily Log → ICS Exporter

This project parses daily logs stored in WordPress posts (Gutenberg format) and converts them into structured events and ready-to-publish ICS calendar files.

---

## ✨ Overview

Daily activities are recorded in WordPress posts as simple paragraph blocks:

```html
<!-- wp:paragraph -->
<p>07:45 Breakfast and baked pizza</p>
<!-- /wp:paragraph -->
```

This project transforms those logs into calendar events by applying a simple rule:

> **The end time of one event is the start time of the next event.**

---

## 🧠 Core Concept

Logs are not treated as plain text.

They are interpreted as a **sequence of time-based events**.

Example:

```
07:45 Breakfast
08:30 Enabled Thunderbird
```

Becomes:

| Event               | Start | End       |
| ------------------- | ----- | --------- |
| Breakfast           | 07:45 | 08:30     |
| Enabled Thunderbird | 08:30 | (unknown) |

---

## 📥 Input Format

* Source: WordPress `post_content`
* Format: Gutenberg blocks
* Primary block used: `wp:paragraph`

Example:

```html
<!-- wp:paragraph -->
<p>8:30 Enabled Thunderbird on laptop</p>
<!-- /wp:paragraph -->
```

---

## ✅ Log Detection Rules

A paragraph is considered a valid log entry if:

* It starts with a time
* Supported formats:

  * `H:MM` (e.g. `8:30`)
  * `HH:MM` (e.g. `07:45`)

Normalization:

```
8:30 → 08:30
```

---

## ❌ Ignored Content

The following blocks are ignored:

* `wp:file`
* `wp:image`
* `wp:list`
* `wp:heading`
* Paragraphs without a leading time

---

## ⏱ Event Construction

Events are built using sequential inference:

```
event[i].end = event[i+1].start
```

### Example

```
07:45 Breakfast
08:30 Work
09:10 Meeting
```

→

* Breakfast: 07:45 → 08:30
* Work: 08:30 → 09:10
* Meeting: 09:10 → (unknown)

---

## ⚠️ Final Event Handling

The last event has no natural end time.

Supported strategies:

* `omit_last_without_end`
* `mark_last_for_review` (default)
* `fallback_duration_minutes`

Example:

```json
{
  "start_time": "09:10",
  "end_time": null,
  "status": "needs_review"
}
```

---

## 📤 Output Format

### 1. Structured JSON

```json
[
  {
    "date": "2026-04-11",
    "start_time": "07:45",
    "end_time": "08:30",
    "summary": "Breakfast and baked pizza",
    "status": "ready"
  }
]
```

---

### 2. ICS Calendar

Generated as a valid `VCALENDAR`:

```ics
BEGIN:VCALENDAR
VERSION:2.0

BEGIN:VEVENT
UID:20260411-0745-breakfast@example.com
DTSTART:20260411T074500
DTEND:20260411T083000
SUMMARY:Breakfast and baked pizza
END:VEVENT

END:VCALENDAR
```

---

## 🧩 Pipeline

```
WordPress post_content
        ↓
Parse Gutenberg blocks
        ↓
Extract time-based logs
        ↓
Normalize timestamps
        ↓
Infer event durations
        ↓
Generate structured JSON
        ↓
Export ICS
```

---

## 🛠 Design Principles

* **Deterministic** — no guessing of missing times
* **Append-only logs** — original content is never modified
* **Structure over text** — logs become events
* **Explicit uncertainty** — unknown end times are not hidden

---

## 🔧 Future Improvements

* Tag-based categorization (work / life / study)
* Multi-day log support
* Timezone handling
* CLI tool (e.g. `log "message"`)
* Direct WordPress → ICS sync

---

## 📌 Summary

This project turns simple daily logs into structured, calendar-ready data.

Key idea:

> Logs + time order = calendar events

---

## 📄 License

MIT (or your choice)

# wordpress-blog-to-ics-server
listen to wordpress server and convert post to ics server for user to subscripe

The post might be like 
```
andrew@andrew:~$ wp post get 10213 --field=post_content --path=/var/www/html/wordpress
<!-- wp:paragraph -->
<p>07:45 Into the breakfast and bake the pizza</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>07:48 Bake two pizzas for two minutes and 15 seconds</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>08:13 I finished the dinner and have some snacks for sample the beef a small stick of beef</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>8:30 I enabled Thunderbird on laptop</p>
<!-- /wp:paragraph -->

<!-- wp:file {"id":10221,"href":"https://andrew.local/wp-content/uploads/2026/04/ChatGPT-截图问题排查指南.html"} -->
<div class="wp-block-file"><a id="wp-block-file--media-5e0fe277-f1c3-467a-8141-900f64c0d798" href="https://andrew.local/wp-content/uploads/2026/04/ChatGPT-截图问题排查指南.html">ChatGPT-截图问题排查指南</a><a href="https://andrew.local/wp-content/uploads/2026/04/ChatGPT-截图问题排查指南.html" class="wp-block-file__button wp-element-button" download aria-describedby="wp-block-file--media-5e0fe277-f1c3-467a-8141-900f64c0d798">Download</a></div>
<!-- /wp:file -->

<!-- wp:paragraph -->
<p>9:56 I found the homework</p>
<!-- /wp:paragraph -->

<!-- wp:image {"id":10219,"sizeSlug":"large","linkDestination":"none"} -->
<figure class="wp-block-image size-large"><img src="https://andrew.local/wp-content/uploads/2026/04/8b45ac5741facb4310feb158a2ff5c88-1024x797.jpg" alt="" class="wp-image-10219"/><figcaption class="wp-element-caption">Oplus_16908288</figcaption></figure>
<!-- /wp:image -->

<!-- wp:file {"id":10224,"href":"https://andrew.local/wp-content/uploads/2026/04/ChatGPT-Transfer_Thunderbird_Data.html"} -->
<div class="wp-block-file"><a id="wp-block-file--media-c04713d4-7c58-4512-9cd9-6ffc577218eb" href="https://andrew.local/wp-content/uploads/2026/04/ChatGPT-Transfer_Thunderbird_Data.html">ChatGPT-Transfer_Thunderbird_Data</a><a href="https://andrew.local/wp-content/uploads/2026/04/ChatGPT-Transfer_Thunderbird_Data.html" class="wp-block-file__button wp-element-button" download aria-describedby="wp-block-file--media-c04713d4-7c58-4512-9cd9-6ffc577218eb">Download</a></div>
<!-- /wp:file -->

<!-- wp:paragraph -->
<p>10:11</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p></p>
<!-- /wp:paragraph -->
andrew@andrew:~$ ```
