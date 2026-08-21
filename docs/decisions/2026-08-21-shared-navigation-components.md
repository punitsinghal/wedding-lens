# ADR: Shared navigation components (Breadcrumb, GuestHomeLink) and persona-aware Nav
Date: 2026-08-21
Status: accepted

## Context

Issue #40 reported that navigation "feels random" across the app. Investigation (`docs/features/navigation-consistency/ux.md`) found the cause wasn't visual polish but that every section of the app invented its own back-navigation idiom independently: three different breadcrumb markup styles across owner-side pages, three different visual treatments for "back to gallery" on guest pages, and — most seriously — the global `Nav` component rendering unconditionally on guest routes (`/g/[slug]/...`). Since guests never authenticate, `Nav`'s logo (`href="/"`) sent them to `/`, which redirects unauthenticated visitors to `/login` — ejecting a guest from their own wedding gallery onto a photographer login form.

There was no shared breadcrumb component anywhere in `frontend/components/`; breadcrumb JSX was hand-duplicated in six files with inconsistent wrappers (`<div>` with `<span>/</span>` separators vs. `<p>` with text-node `/` separators).

## Decision

Introduce two shared components and one behavioral change to `Nav`, and use them everywhere a comparable navigation control is needed going forward:

1. **`components/Breadcrumb.tsx`** — the only breadcrumb implementation in the codebase now. Takes `items: { label: string; href?: string }[]` (last item unlinked, current page) and an optional `trailing` slot (e.g. `StatusBadge`). All six owner/admin breadcrumbs (event detail, photos, albums, album detail, QR, admin event detail, new-event) now render through it. Any future page needing a breadcrumb must use this component, not hand-rolled JSX.
2. **`components/guest/GuestHomeLink.tsx`** — the only "return to gallery" control for guest routes. Used by `search` and `favourites`; any future guest page needing a way back to the gallery hub must use this component.
3. **`Nav.tsx` is now guest-route-aware**: on paths starting with `/g/` it still renders the PicsLeLo brand/logo (for identity — losing it read as broken branding, filed as a follow-up regression), but suppresses the Login/Register/Dashboard/profile-menu links, none of which a guest can use. The logo links to `/dashboard` for authenticated users, to the guest's own `/g/{slug}/gallery` on guest routes, and to `/` otherwise — never unconditionally to `/`, which would eject a guest onto the photographer login form.
4. Event-scoped pages (`app/events/[eventId]/layout.tsx`) now include an "Overview" entry alongside Photos/Albums/QR, so any event-scoped page can reach any other without returning to the breadcrumb's parent first.
5. Error-state fallbacks on event-scoped pages now target their own immediate breadcrumb parent (Photos/Albums/QR → Event Overview; Album detail → Albums list) instead of uniformly jumping to `/dashboard`.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Shared `Breadcrumb`/`GuestHomeLink` components (chosen) | Single source of truth; eliminates the per-page drift that caused this issue; future pages inherit consistency for free | More upfront work than a scoped inline fix |
| Scoped inline pass (fix each page's markup individually, no extraction) | Faster to ship | Leaves the door open for the same drift to recur — doesn't address the root cause |
| Merge Photos/Albums/QR into event-detail tabs | Fewer routes, more "single page" feel | Bigger change (routing/URL structure), higher risk; rejected — kept as separate routes per product decision |

## Consequences

- Easier: adding a new owner-scoped or guest-scoped page with correct, consistent navigation — just import `Breadcrumb`/`GuestHomeLink` rather than inventing new markup.
- Easier: guest-facing pages can no longer accidentally inherit the photographer/admin nav links, while still keeping the PicsLeLo brand for identity.
- Harder/requires discipline: any future ad hoc breadcrumb or back-link added outside these components is now a regression, not just an inconsistency — code review should catch direct `<Link>`-based breadcrumb JSX reappearing.
- No routing or URL changes; no backend changes; no visual/color/typography redesign — scope was intentionally limited to navigation consistency (see `docs/features/navigation-consistency/ux.md`, "Out of scope").

## References

- Issue #40 — Fix inconsistent cross-page navigation
- `docs/features/navigation-consistency/ux.md` — UX audit and target navigation model
- `docs/features/product-ux/ux.md` — broader product UX audit this navigation review extends
