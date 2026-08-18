# ADR: Signed-in user profile dropdown, backed by email/is_admin JWT claims
Date: 2026-08-16
Status: accepted

## Context

The nav bar showed a bare "Sign out" link for signed-in photographers/admins,
with no indication of *who* was signed in. Adding a profile display (avatar +
name in the top-right corner) surfaced a pre-existing bug: `create_access_token`
(`backend/app/services/auth.py`) only ever put `sub` and `exp` into the JWT
payload, while `frontend/lib/auth.ts` already assumed `email` and `is_admin`
claims existed. In practice this meant `isAdmin()` on the frontend always
returned `false` (admin nav link/gating silently broken for real admins) and
`getCurrentUserEmail()` always fell back to the raw user-id string.

There is no `name`/`full_name` column anywhere in the data model, no `/me`
endpoint, and no profile page. Adding a real display-name field would mean a
migration plus registration-form changes — out of scope for what was asked
(a nav display + moving Sign out into a menu). The user confirmed showing
just the local part of the email (before `@`) is sufficient for now.

## Decision

1. **Backend**: `create_access_token` now accepts optional `email` and
   `is_admin` keyword args and includes them as JWT claims when provided.
   `decode_access_token` is unchanged — it still only extracts `sub`, since
   `get_current_user` re-fetches the full `User` row from the DB anyway and
   nothing needs the token itself as the source of truth for `is_admin`.
   This is additive and fixes the frontend/backend claim mismatch without
   changing the trust model (the DB row remains authoritative for admin
   checks server-side).

2. **Frontend**: `AuthProvider` now exposes `displayName` (email local part,
   via a new `getDisplayName()` helper in `lib/auth.ts`) and `email` in
   addition to the existing `isLoggedIn`/`isAdminUser` fields. `Nav.tsx`
   renders an avatar (initial letter) + display name as a dropdown trigger;
   the dropdown shows the full email and the "Sign out" action, replacing the
   old always-visible sign-out link. The dropdown is a plain
   `useState` + `ref` + `mousedown`/`Escape` listener implementation — there
   is no existing dropdown/menu component or `useOnClickOutside` hook in the
   codebase to reuse, and this establishes the pattern for future nav-area
   menus (see `.nav-profile` / `.nav-dropdown` classes in `globals.css`).

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Add `email`/`is_admin` JWT claims + email-local-part display name (chosen) | Fixes an existing bug (`isAdmin()`/`getCurrentUserEmail()`), no schema change, ships today | Display name is derived from email, not a "real" name |
| Add a `full_name` column + migration + registration field | Real display name | Bigger surface (migration, registration UX, backend schema) for a request that only asked for a nav display; deferred until actually needed |
| Frontend-only, decode `sub` as-is | No backend change at all | `sub` is a raw UUID for every existing user — would show a UUID in the nav, not useful |

## Consequences

Admin gating (`isAdminUser` in `Nav.tsx`, and any future client-side
`isAdmin()` check) now actually reflects the signed-in user's admin status,
where before it was silently always `false`. Future nav-area menus should
reuse the `.nav-profile`/`.nav-dropdown` CSS classes and the ref+listener
pattern in `Nav.tsx` rather than re-inventing click-outside handling. If a
real display name is needed later, it requires a `full_name` column, a
registration-form field, and a JWT claim — this ADR intentionally does not
build that.

## References

- `backend/app/services/auth.py`, `backend/app/routers/auth.py`
- `frontend/lib/auth.ts`, `frontend/components/AuthProvider.tsx`, `frontend/components/Nav.tsx`
- `frontend/app/globals.css` (`.nav-profile`, `.nav-dropdown`)
