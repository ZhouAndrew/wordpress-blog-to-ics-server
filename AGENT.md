# AGENT.md

This document defines HARD architectural constraints.

All agents MUST follow these rules.

---

# 1. Core Pipeline (NON-NEGOTIABLE)

All processing MUST follow:

WordPressSource → Parser → ParsedDayLog → Exporters / Sync

NO shortcuts allowed.

---

# 2. Single Data Model

`ParsedDayLog` is the ONLY valid intermediate representation.

Rules:

- parsers MUST output ParsedDayLog
- exporters MUST consume ParsedDayLog
- sync MUST consume ParsedDayLog
- no module may bypass this structure

---

# 3. Layer Isolation (STRICT)

Allowed dependency direction:

cli → services → (sources, parsers, exporters, sync)

Forbidden:

- exporters calling sources ❌
- parsers calling sources ❌
- sync calling sources ❌
- HTTP server calling sources ❌
- exporters calling parsers ❌

---

# 4. Source Responsibility

Sources ONLY:

- fetch WordPress data
- return normalized metadata + raw content

Sources MUST NOT:

- parse content
- generate events
- generate ICS

---

# 5. Parser Responsibility

Parsers ONLY:

- extract text
- detect time patterns
- build structured events

Parsers MUST NOT:

- access WordPress
- generate ICS
- write files

---

# 6. Exporter Responsibility

Exporters ONLY:

- convert ParsedDayLog → output format

Exporters MUST NOT:

- fetch WordPress data
- parse raw content
- perform sync operations

---

# 7. Sync Responsibility (IMPORTANT)

Sync is NOT export.

Sync MUST:

- compare desired vs remote state
- create / update / delete events

Sync MUST NOT:

- generate ICS as primary logic
- overwrite unrelated data
- operate without UID comparison

---

# 8. UID Rules

All events MUST have stable deterministic UID.

UID MUST be derived from:

- post_id
- date
- start_time
- summary (normalized)

UID MUST NOT change across runs.

---

# 9. Service Entry Point

All workflows MUST go through:

publish_once(config)

No duplicated pipelines allowed.

---

# 10. HTTP Server Rules

HTTP server MUST:

- serve static output directory
- call publish_once() at startup

HTTP server MUST NOT:

- fetch WordPress
- parse logs

---

# 11. Parsing Rules Priority

Order is STRICT:

1. custom patterns
2. range patterns
3. point patterns

Range MUST override point.

---

# 12. No Hidden Behavior

The system MUST NOT:

- silently select posts
- silently ignore errors
- silently mutate data

All decisions MUST be explicit in logs.

---

# 13. No Logic Duplication

Parsing logic and ICS generation logic MUST NOT be duplicated.

All modules MUST reuse shared functions.

---

# 14. Future Compatibility

All code MUST allow:

- new sources
- new exporters
- new sync targets

WITHOUT modifying core parser logic.

---

# 15. Absolute Prohibitions

DO NOT:

- mix parser + exporter logic
- mix source + parser logic
- implement sync inside exporter
- bypass ParsedDayLog
- hardcode parsing formats