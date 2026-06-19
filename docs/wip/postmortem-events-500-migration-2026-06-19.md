## Incident: GET /api/v1/events 500 after login — migration not applied on deploy

Date: 2026-06-19
Severity: P2
Duration: ~18:13 → ~18:17 (approx. 4 minutes, contained quickly)
Affected: All authenticated photographers — dashboard failed to load event list after login

## Timeline

- 18:13 — `GET /api/v1/events` begins returning 500 for authenticated requests following deploy of `90e2340`
- 18:13 — `POST /api/v1/events` returns 422
- 18:13 — React error #423 ("component suspended during synchronous input") appears in browser console, crashing the photographer dashboard
- 18:14 — Incident triage: root cause identified as unapplied migration `002_guest_access.py`
- 18:16 — `alembic upgrade head` run; migration `001 → 002` applied
- 18:17 — `pm2 restart wl-backend` completes; process online (pid 54367)
- 18:17 — Application startup complete; incident resolved

## Root cause

Commit `90e2340` (feat: implement guest access) added three columns to the `events` ORM model and `EventOut` schema (`otp_code`, `guest_access_enabled`, `guest_access_revoked_at`) and shipped the corresponding migration file (`002_guest_access.py`). The migration was not run against the database before or after the backend was restarted with the new code.

When an authenticated request hit `GET /api/v1/events`, SQLAlchemy attempted to SELECT all mapped columns — including the three new ones — against a table that still had the `001` schema. PostgreSQL rejected the query, producing an unhandled 500. Unauthenticated paths (`/by-slug/{slug}`) were unaffected because they return `EventPublicOut`, which does not include the new fields.

The frontend had no error boundary around the events list fetch; the 500 caused a React suspense violation (#423), crashing the entire dashboard view rather than showing a degraded state.

## Fix

Ran `alembic upgrade head` to apply migration `002_guest_access.py` (adds `otp_code`, `guest_access_enabled`, `guest_access_revoked_at` to the `events` table with safe defaults). Restarted `wl-backend` via PM2. No code changes were needed.

## Follow-up items

- [ ] Add migration check to deploy runbook — `alembic upgrade head` must be run before restarting the backend whenever migrations are present
- [ ] Add a startup assertion in the FastAPI lifespan handler that checks `alembic_version` matches the expected head revision; fail fast with a clear error rather than serving 500s
- [ ] Add an error boundary in the frontend around the events list so a backend 500 shows a degraded state instead of crashing the dashboard

## What went well

- Root cause was identified within one minute of seeing the logs: the pattern (500 only after login, immediately after a deploy that added ORM fields) pointed directly at a missing migration.
- The fix was non-destructive and instantly reversible (downgrade path exists in `002_guest_access.py`).
- Guest-facing paths were never affected — only authenticated photographers saw the breakage.

## What could be better

- No deploy checklist enforced the migration step — it was easy to skip.
- The backend started without error even though the DB schema was out of sync with the ORM; a startup schema check would have surfaced this immediately.
- The frontend had no resilience for a list-fetch 500 — a single endpoint failure crashed the whole dashboard.
