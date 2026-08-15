## Review: docs/features/product-ux/ux.md (+ dead-route cleanup)
Date: 2026-08-15
Reviewer: Punit Singhal
Related issue: none (no board issue tracks this session — a cross-cutting audit, not tied to a single epic)

Scope: two local commits on `main`, not yet pushed to `origin/main`:
- `427b6e9` — docs: ux product-ux (adds `docs/features/product-ux/ux.md`)
- `2834ea4` — chore: remove dead `/events/[eventId]/search` route (deletes the page, corrects two stale doc references, amends the audit's open question)

No feature branch or PR exists for this work — see note under Architecture conformance.

## Summary

**Approve.** This is a documentation deliverable plus a small, verified dead-code deletion — there is no application logic at risk and no architecture-constraint surface to violate. I fact-checked every quantitative and behavioral claim in `ux.md` against `requirements.md`/ADRs for the epics it describes (guest-access, face-recognition-search, photo-actions, event-management, privacy-security) and found the audit accurate, with one claim (favourites persistence) that undersells how ephemeral the underlying store actually is, and one open question that new evidence resolves into a confirmed finding. Both are non-blocking — the doc is fine to keep as-is, but should be tightened on a follow-up pass.

## Findings

### Blocking

None.

### Non-blocking

- [ ] `docs/features/product-ux/ux.md` (Guest journey / Screen inventory, Favourites row) — describes favourites as "persisted server-side per guest token," which is true only loosely. Per `docs/decisions/2026-06-20-favourites-in-process-store.md`, `FavouritesStore` is an **in-process, in-memory singleton** with a 24-hour sliding TTL, explicitly "lost on server restart" by design (accepted for MVP). A guest who favourites photos and returns after 24h of inactivity, or after any backend restart, loses their favourites with zero warning in the UI. Worth adding a row to the Edge Cases table (`condition: guest returns after favourites TTL/restart` → `sees an empty favourites list, no explanation`) rather than describing it as straightforwardly "persisted."
- [ ] `docs/features/product-ux/ux.md` (Photographer journey, "Notable friction" bullet on cover-photo publish gating) — this was written as an open question ("worth verifying against the backend"), but `docs/features/event-management/requirements.md` REQ-31/AC-19 and `design.md` (`POST /publish` "validates slug + access_mode + cover_photo set") confirm the backend **does** reject publish when no cover photo is set. That means the frontend gap is real and confirmed, not hypothetical: `frontend/app/events/[eventId]/page.tsx`'s publish-button `disabled` condition checks `consentChecked` and event status but never `event.cover_photo_id`, so an owner can click Publish, round-trip to the server, and get rejected — an avoidable failed submission the UI could prevent client-side. Recommend promoting this from the Open Questions list to a stated finding.
- [ ] Both commits landed directly on `main`. `.claude/pai-orbit-config.md` declares GitHub Flow with squash-merge PRs as the branching model, and this session didn't use a `docs/`-prefixed (or any) feature branch. Reasonable for a solo-founder docs/cleanup session with no reviewer other than yourself, but flagging since it's a declared convention with no documented exception for docs-only work.

### Positive observations

- Every quantitative claim in the doc was checked against source-of-truth requirements/ADRs and came back exact: 200-photo ZIP cap and its top-ranked-by-score fallback (`photo-actions/requirements.md` REQ-4/REQ-5/REQ-27), 20 MB selfie limit (`face-recognition-search/requirements.md` NFR-5), 25 MB photo upload limit (`photographer-dashboard/requirements.md` REQ-2), 30-day retention (`privacy-security/requirements.md`), 24-hour removal-request SLA (`privacy-security/requirements.md` REQ-12/AC-3b), 72-hour share-link expiry (`docs/decisions/2026-06-20-share-token-jwt.md`), and the 10-album cap (matches `MAX_ALBUMS` in `AlbumList.tsx`). Zero numeric errors across a genuinely large set of cross-checks.
- The dead-route claim (`/events/[eventId]/search`) was verified properly before being asserted and acted on: grepped for any link/redirect referencing the path shape, traced QR-code generation to `backend/app/services/qr.py` to confirm guest URLs are always slug-based, and used `git log --diff-filter=A` to establish the epic sequencing that explains *why* the orphan exists. That's a well-substantiated claim, not a guess — and the removal was verified with a passing `npm run lint` and `npm run build` before committing.
- The ConfirmDialog friction-level comparison (event delete requires typing `DELETE`; album delete does not) is precisely correct against the component's actual optional `confirmText` prop (`frontend/components/ConfirmDialog.tsx:22,37` — `canConfirm` only requires exact-match input when `confirmText` is passed, and `AlbumList.tsx`'s delete call omits it).
- The doc follows the `/ux` skill's template faithfully, and both Mermaid flows accurately reflect the real route/component structure I independently traced (guest: entry → gallery/search/favourites/lightbox; photographer: dashboard → event detail → photos/albums/QR).

## Architecture conformance

- [x] No violations of rules in `docs/architecture/constraints.md` — no code path changed other than deleting an unreachable page; no new frontend→data-store connection, no new service.
- [x] No undeclared service or communication path added (`docs/architecture/system.md`) — nothing added.
- [x] No cross-service DB connection introduced.
- [x] Stays within layer boundaries defined in CLAUDE.md.
- [x] No conflicts with ADRs in `docs/decisions/` — the deleted route's replacement (`/g/[slug]/search`) is consistent with the guest-session-token and slug-based guest-access ADRs; no ADR referenced the deleted page as a required artifact.
- [x] No undiscussed dependencies introduced.
- Note (not a violation, out of scope for this diff): `docs/features/privacy-security/requirements.md:96` anchors the 30-day retention rule to "30 days of the event end date" and states there is "no separate grace period distinction," while the actual purge implementation (`docs/decisions/2026-06-19-apscheduler-purge-job.md`) anchors the 30-day window to `deleted_at` (the soft-delete timestamp) instead. `ux.md`'s Danger Zone description matches the *implemented* (`deleted_at`-based) behavior faithfully, so this isn't a defect in the reviewed doc — but the two governance docs disagree with each other and should be reconciled separately from this review.

## Requirements coverage

Not applicable in the usual sense (no `requirements.md`/`design.md` exists for a "product-ux" feature, since this is a cross-cutting audit rather than a scoped feature). In lieu of that checklist, every factual claim the audit makes about existing epics' behavior was spot-checked against those epics' own `requirements.md`/ADRs — see Positive observations above for the full list of confirmed cross-checks.

## Sign-off
- [ ] Both non-blocking findings resolved (favourites-persistence wording, cover-photo open-question promotion) — optional, doesn't block keeping the doc as merged
- Reviewer: Punit Singhal — 2026-08-15
