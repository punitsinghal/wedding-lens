# ADR: Photographer-Event Assignment — Join Table
Date: 2026-06-19
Status: accepted

## Context

Event owners must be able to assign one or more photographers to their event by email, and revoke that assignment at any time. The assignment must be immediately enforceable on every API request — a revoked photographer must not be able to upload or manage albums.

## Decision

Use a dedicated join table `event_photographers(event_id, photographer_id, assigned_by, assigned_at)` with a composite primary key `(event_id, photographer_id)`.

## Options Considered

| Option | Schema | Assessment |
|--------|--------|------------|
| A — chosen | Join table `event_photographers` | Clean; queryable; stores assignment metadata (who assigned, when); revocation is a single `DELETE`; supports future additions (e.g. permissions column) without schema changes to the `events` table |
| B | Array column `events.photographer_ids UUID[]` | Simpler; no join needed for existence check; cannot store assignment metadata; harder to query "which events does photographer X have access to"; revocation requires array element removal |
| C | Invitation model with status | Supports pending/accepted workflow — over-engineered for an owner-controlled direct assignment; adds UI complexity not required by the requirements |

## Consequences

- Authorization middleware must join `event_photographers` on every photographer-authenticated request to verify assignment. This is a single indexed lookup (`WHERE event_id = X AND photographer_id = Y`) and is negligible in cost.
- Revocation takes effect on the next request — no session invalidation is required because the authorization check is performed per-request against the current assignment table state.
- The `assigned_by` column provides a basic audit trail without a separate audit log.
- A photographer with no rows in `event_photographers` sees an empty dashboard — no special "no assignments" state is needed.
- Future extension (e.g. read-only vs upload permissions per photographer) can be added as a column on this table without changing call sites significantly.

## References

- `docs/features/photographer-dashboard/requirements.md` — REQ-21, REQ-22, REQ-23, REQ-24
- `docs/features/photographer-dashboard/design.md`
