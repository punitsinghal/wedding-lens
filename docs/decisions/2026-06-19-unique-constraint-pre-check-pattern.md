# ADR: Unique Constraint Conflict Handling — Pre-Check, Not Catch-IntegrityError
Date: 2026-06-19
Status: accepted

## Context

The `events.slug` column carries a `UNIQUE` constraint enforced at the database level (per the design doc: "no race-condition window"). When a slug conflict occurs during event creation or update, the API must return a structured 422 response containing both `detail: "slug_taken"` and a list of checked-and-available slug suggestions.

The natural async-SQLAlchemy pattern for catching a constraint violation is to `await db.flush()` inside a try/except and catch `IntegrityError`. However, once a flush raises an `IntegrityError`, SQLAlchemy marks the session's transaction as `DEACTIVE` and requires an explicit `await db.rollback()` before any further queries can run. This makes it impossible to query the DB for available suggestion slugs in the same exception handler without rolling back first — which would discard any other work in the same transaction.

## Decision

Check slug availability with a lightweight `SELECT` query **before** attempting the insert/update, rather than attempting the write and catching the constraint error afterward.

```python
if not await _is_slug_available(db, slug):
    suggestions = await generate_slug_suggestions(db, slug, ...)
    raise SlugTakenError(suggestions=suggestions)
# Only after the pre-check succeeds, proceed with the INSERT/UPDATE
```

This keeps the session clean (no poisoned transaction state), makes the suggestions query trivially safe, and avoids the need to plumb a rollback-then-retry loop through the service layer.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Pre-check SELECT then INSERT (chosen) | Session stays clean; suggestions query runs safely; simple code path | Small TOCTOU window: a concurrent request could claim the slug between the check and the insert. Mitigated by the DB UNIQUE constraint, which acts as the ultimate guard — the constraint violation would bubble as a 500 rather than a 422 under extreme concurrent load |
| Catch `IntegrityError` on flush, rollback, then query suggestions | Catches concurrent conflicts correctly | Requires explicit `await db.rollback()` in the handler; all other work in the same unit of work is lost; adds complexity and is easy to get wrong with nested flushes |
| Savepoint per insert | Handles concurrent conflicts without full rollback | PostgreSQL-only feature; not supported by `aiosqlite` used in tests; adds driver-specific code |

## Consequences

- All future code paths that involve UNIQUE columns and need to return user-friendly conflict messages must follow this pre-check pattern.
- The DB UNIQUE constraint remains the definitive guard against duplicates. A pre-check failure gives a 422 with suggestions; a concurrent race that passes the pre-check but fails the constraint would return a 500 (acceptable for the target single-VM deployment with low concurrent write volume).
- The pattern is documented here so that it is not changed back to catch-IntegrityError without understanding the session-state implications.

## References

- `docs/features/event-management/design.md` — slug conflict response spec
- `app/services/events.py` — `create_event`, `update_event`, `_is_slug_available`
- SQLAlchemy docs: "Session Basics — When to use Session.rollback()"
