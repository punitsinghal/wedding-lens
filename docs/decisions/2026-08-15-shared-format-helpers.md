# ADR: Shared display-formatting helpers in `lib/format.ts`
Date: 2026-08-15
Status: accepted

## Context

The admin platform work (admin event list, admin event detail, platform health
dashboard) needs to render the same kinds of values in multiple places:
human-readable byte counts (`storage_used_bytes`, `total_storage_bytes`),
full timestamps (`last_activity_at`), and a percentage (`error_rate_24h`).
The codebase already has an established inline convention for date-only
formatting (`new Date(x).toLocaleDateString('en-IN', {...})`, repeated in
`app/admin/page.tsx`, `components/EventCard.tsx`, `components/AssignedEventCard.tsx`),
but no existing helper for byte counts or percentages, and no precedent for
formatting a full date+time (as opposed to a date-only field like `event_date`).

Copy-pasting a byte-formatting `switch`/loop into three separate admin pages
would drift (different rounding, different unit thresholds) the moment one of
them is edited without the others.

## Decision

Add `frontend/lib/format.ts` with three small, pure functions:
`formatBytes`, `formatDateTime`, `formatPercent`. `formatDateTime` follows the
same `en-IN` locale convention already used for date-only fields elsewhere,
extended with an hour/minute component. Admin pages import these instead of
each writing their own conversion.

This is a plain utility module, not a class or a new data-fetching pattern —
existing date-only formatting call sites are intentionally left as-is (no
value in a repo-wide refactor here); only new code introduced by the admin
platform feature uses the shared helper.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Shared `lib/format.ts` helpers | One place to fix rounding/units; consistent across admin list, detail, and health dashboard | One more file to be aware of |
| Inline formatting per page (status quo pattern for dates) | No new file | Byte-formatting logic would be duplicated 3x across this feature alone, and drift risk is high given they render the same underlying byte counts from different endpoints |

## Consequences

Future admin/owner-facing pages that need to display byte counts, full
timestamps, or percentages should import from `lib/format.ts` rather than
reintroducing inline conversions.

## References

- `docs/features/admin-platform/design.md` (D1, D6)
- `frontend/lib/format.ts`
