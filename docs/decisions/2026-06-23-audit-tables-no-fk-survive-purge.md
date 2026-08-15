# ADR: Audit Tables (`consent_records`, `removal_requests`) Use No FK to Survive the Event Purge

**Date:** 2026-06-23
**Status:** Accepted
**Deciders:** Engineering

---

## Context

The Privacy & Security feature introduces two tables that must be **retained for ≥3 years**,
independent of the event lifecycle (NFR-6), and removal requests specifically must **never be
deleted** (REQ-16):

- `consent_records` — owner consent confirmations captured at publish (S1)
- `removal_requests` — guest face-data removal requests (S3/S4)

Every other event-scoped child table in the schema declares
`ForeignKey("events.id", ondelete="CASCADE")` (see `app/models/photo.py`, `album.py`,
`assignment.py`, `upload_session.py`). The 30-day purge job deletes the event row directly —
`_purge_single_event` calls `await db.delete(event)` (`app/services/purge.py`) — which triggers the
database-level cascade and removes all such children.

If the new audit tables used the same `ondelete="CASCADE"` FK, the purge would **delete the very
records we are required to retain**. A non-cascading FK (`RESTRICT`/`NO ACTION`) is worse: it would
make `db.delete(event)` raise and **break the purge job entirely**.

---

## Decision

`consent_records` and `removal_requests` store `event_id` (and, for consent, `confirmed_by`) as
**bare indexed `UUID` columns with no foreign-key constraint**.

- The records are deliberately decoupled from the `events` / `users` rows they reference.
- When the event is purged at 30 days, these audit records **remain** as standalone rows — the
  `event_id` they carry is sufficient for audit lookup (AC-4c) even though the event no longer
  exists.
- `event_id` is indexed for admin lookup; no referential integrity is enforced at the DB layer.

---

## Options Considered

| Option | Survives purge? | Breaks purge? | Audit lookup intact? |
|--------|-----------------|---------------|----------------------|
| **Bare UUID, no FK (selected)** | Yes | No | Yes (`event_id` retained) |
| FK `ondelete="CASCADE"` | No — deleted with event | No | N/A — records gone |
| FK `ondelete="SET NULL"` | Yes | No | No — `event_id` nulled, can't locate target |
| FK `ondelete="RESTRICT"`/default | Yes | **Yes** — `db.delete(event)` raises | Yes |

---

## Consequences

**Positive:**
- Audit records outlive their event, satisfying NFR-6 and REQ-16 with no change to the purge job.
- The purge job needs no special-casing — it continues to delete only the event and its cascading
  children.

**Negative:**
- No DB-enforced referential integrity: a `consent_records.event_id` may point to an event row that
  no longer exists (by design). Application code and admins must treat these as historical records,
  not live joins.
- Inserts do not get FK validation, so a bad `event_id` would not be caught by the DB. Acceptable:
  the values are server-supplied (`event.id`, `current_user.id`), never client-supplied.

**Convention for future code:**
- Tables whose rows must outlive their parent (audit/compliance retention) use bare indexed UUID
  reference columns, **not** FKs. Do not add a cascade FK to these tables — it would re-introduce
  the purge-deletes-audit-data bug.

---

## References
- `docs/features/privacy-security/design.md` — Data model, retention-vs-purge note
- `docs/features/privacy-security/requirements.md` — NFR-6, REQ-16, AC-4b, AC-4c
- `app/services/purge.py` — `_purge_single_event` (the cascade trigger)
- `docs/decisions/2026-06-19-apscheduler-purge-job.md`
