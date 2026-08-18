## Impact Analysis: Navigation consistency fix (issue #40)
Date: 2026-08-15

## Change
Current: Three uncoordinated back-navigation idioms — arrow-link (event detail, admin event detail), full breadcrumb chain (Photos/Albums/Album detail/QR), bespoke per-page buttons (guest gallery/search/favourites) — plus a global `Nav` that renders unconditionally on every route, including guest routes under `/g/[slug]/...`, and one `router.back()` call in `events/new`.

Proposed (per `docs/features/navigation-consistency/ux.md`):
1. Suppress global `Nav` on `/g/[slug]/...`; guest routes get their own persistent header, "Home" always → Gallery.
2. Standardize owner pages on the existing breadcrumb pattern (`Dashboard / {Event} / {Page}`); collapse event-detail's arrow-link + Quick Links row into it.
3. Replace `router.back()` in `events/new` with fixed `href="/dashboard"`.
4. Standardize error-state fallback targets to each page's breadcrumb parent.

Classification: **Breaking — owned**. Every file involved is in this repo (`frontend/`); no external consumer touches these components. But item 2 is entangled with an open, unresolved design question (see below), which turns it from a simple styling pass into a possible routing change.

## Consumers found

| Location | File:line | Classification | Action needed |
|---|---|---|---|
| Global Nav | `frontend/app/layout.tsx:16` | Owned | Wrap in a persona check, or move `<Nav/>` out of root layout and into owner/admin-scoped layouts |
| Global Nav render | `frontend/components/Nav.tsx` | Owned | Add guest-route awareness or leave as-is and rely on layout-level suppression |
| Guest layout (no-op today) | `frontend/app/g/layout.tsx:1-7` | Owned | Currently just a styled `<div>` — this is where the persistent guest header (event name + Home) needs to be added |
| Guest gallery header | `frontend/app/g/[slug]/gallery/page.tsx:295-330` | Owned | Existing header with "Find my photos" / "Favourites" pills — becomes the template the new persistent header standardizes on |
| Guest search back-link | `frontend/app/g/[slug]/search/page.tsx:66-72` | Owned | Icon-link "Back to gallery" — reconcile style with favourites' text link (rule 4) |
| Guest favourites back-links | `frontend/app/g/[slug]/favourites/page.tsx:101-102,128` | Owned | Two separate text links to gallery today — consolidate to one shared component |
| Event detail header/quick-links | `frontend/app/events/[eventId]/page.tsx:334-349` | Owned | Arrow-link `← Dashboard` + separate "Quick links" row (Manage Photos, etc.) — target of rule 2 |
| Event detail error fallback | `frontend/app/events/[eventId]/page.tsx:311-313` | Owned | "Back to Dashboard" — already matches target convention |
| Photos page error fallback | `frontend/app/events/[eventId]/photos/page.tsx:532` | Owned | "Back to Dashboard" — matches |
| Albums page error fallback | `frontend/app/events/[eventId]/albums/page.tsx:54` | Owned | "Back to Dashboard" — matches |
| QR page error fallback | `frontend/app/events/[eventId]/qr/page.tsx:100` | Owned | "Back to Dashboard" — matches |
| **Album detail error fallback (outlier)** | `frontend/app/events/[eventId]/albums/[albumId]/page.tsx:107` | Owned | "Back to Albums" instead of "Back to Dashboard" — the one confirmed inconsistency; fix is a one-line link-target change |
| `events/new` Cancel button | `frontend/app/events/new/page.tsx:221` | Owned | Only `router.back()` call in the codebase — swap for `router.push('/dashboard')` or a plain `<Link href="/dashboard">` |
| Admin event detail back-link | `frontend/app/admin/events/[eventId]/page.tsx:38-39` | Owned | Arrow-link `← Admin — All Events`, structurally same idiom as old event-detail — needs same-component treatment if admin breadcrumb is unified with owner breadcrumb (open question) |
| `isAuthenticated()` gate | `frontend/lib/auth.ts:21` + 8 call sites (`app/page.tsx`, `app/dashboard/layout.tsx`, `app/admin/layout.tsx`, `app/events/new/page.tsx`, `app/events/[eventId]/page.tsx`, `.../photos`, `.../albums`, `.../albums/[albumId]`, `.../qr`) | Owned | Not modified by this proposal (explicitly out of scope in ux.md) — confirmed no auth-logic change needed, only what renders around it |

No breadcrumb component exists yet — "breadcrumb" in the doc refers to hand-written `Dashboard / {Event} / {Page}` JSX repeated per page (Photos/Albums/QR), not a shared component. Grepping for a shared component turned up none.

## Scope-narrowing finding (since the doc was written)

Commit `73a0938` ("split event detail page into tabs", 2026-08-15, prior to this doc) already resolved the *product-ux* audit's complaint about event-detail carrying too many jobs — it added an internal `TabKey` (`overview` / `publish` / `photographers` / `danger`) to `app/events/[eventId]/page.tsx`. **This did not touch the Photos/Albums/QR relationship** — those remain separate routes reached via the "Quick links" row (`page.tsx:343-349`), untouched by the tabs refactor. So ux.md's open question #2 ("should Photos/Albums/QR become tabs within event-detail, or remain routes with a shared sub-nav?") is still fully open and unaffected by the tabs work — the two tab sets are orthogonal (one is intra-page sections, the other is inter-page navigation).

## Migration path

The four proposed changes have very different blast radii and can ship independently:

1. **Trivial, no open questions** — ship immediately, no design sign-off needed:
   - Album detail error fallback → "Back to Dashboard" (1 line)
   - `events/new` Cancel → fixed `href="/dashboard"` (1 line, removes the only `router.back()` in the app)
2. **Owned, needs one design decision (guest "home")** — ux.md flags this as an open question ("Confirm: is Gallery the intended guest home, or does the user need an explicit way back to `/g/[slug]` PIN entry?"). Once confirmed, implementation is scoped to `app/g/layout.tsx` (add header) + `app/g/[slug]/{search,favourites}/page.tsx` (swap to shared "Home" control) + suppressing `<Nav/>` for `/g/...` in `app/layout.tsx`.
3. **Owned, needs a routing decision before starting** — the event-detail breadcrumb consolidation (rule 2) depends on the still-open question of whether Photos/Albums/QR become tabs (routing change, touches 3 page files + navigation) or stay routes with a shared sub-nav component (component-only change, touches header markup only in the same 3 files). Building this before that's decided risks throwaway work either way.
4. **Owned, needs a product decision** — admin breadcrumb styling (match owner exactly vs. stay visually distinct) — cosmetic only, low risk either direction, can be deferred without blocking 1–3.

Recommended order: ship (1) now as a standalone small PR, resolve the two open questions in (2)/(3) with product/engineering sign-off, then build (2), (3), (4) in that order since (3) is the only one with routing implications.

## Recommendation
**Proceed with the migration path above.** Nothing here reaches outside `frontend/` (no backend or auth changes, confirmed by grep — `isAuthenticated()` call sites are unchanged), so this is entirely owned and low-risk. The only real risk is item 3 (event-detail breadcrumb) being built twice if started before its open routing question is resolved.

## Open questions (carried over from ux.md, still unresolved)
- [ ] Shared breadcrumb component vs. scoped per-page fix — owner: engineering
- [ ] Photos/Albums/QR as tabs-in-event-detail vs. routes with shared sub-nav — owner: engineering (blocks item 3 above)
- [ ] Admin breadcrumb: match owner styling exactly, or stay visually distinct — owner: product
- [ ] Guest "home": Gallery only, or keep an explicit path back to `/g/[slug]` PIN entry — owner: product (blocks item 2 above)
