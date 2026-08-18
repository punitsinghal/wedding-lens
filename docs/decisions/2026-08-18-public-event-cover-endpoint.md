# ADR: Unauthenticated cover-photo endpoint for the guest entry screen
Date: 2026-08-18
Status: accepted

## Context

Photographers can set a `cover_photo_id` on an `Event`, but nothing in the
guest-facing UI ever displayed it — the access-code entry screen
(`/g/[slug]`) showed only event name and date on a plain background.

We want the event's cover photo to render as the background of that entry
screen. The problem: that screen is shown *before* the guest has a guest JWT
(it's the screen where they type the access code / OTP to obtain one). Every
existing guest image endpoint (`/photos/{id}/thumbnail`) requires a validated
guest JWT via `get_validated_guest_event` (see
[[2026-06-20-authenticated-image-blob-url-pattern]]), and browsers can't
attach a Bearer token to a CSS `background-image` or plain `<img src>`
request anyway — so the established authenticated-blob-URL pattern cannot
apply here.

## Decision

Add a separate, unauthenticated endpoint,
`GET /api/v1/events/by-slug/{slug}/cover`, that serves image bytes directly
(no fetch/blob indirection needed) and is deliberately narrower than the
guest-authenticated gallery endpoints:

- It resolves the event by slug (same public lookup as
  `GET /api/v1/events/by-slug/{slug}`).
- It 404s unless `event.status == "published"` — draft/suspended events never
  leak their cover photo.
- It only ever serves the exact photo referenced by that event's
  `cover_photo_id` — there is no way to request an arbitrary `photo_id`
  through this route, so it cannot be used to enumerate or browse the rest of
  the event's photos. This keeps constraint 3 (searches/access scoped per
  `event_id`, no cross-event leakage) intact: the exposed surface is one
  photographer-chosen photo per published event, not the gallery.
- File resolution reuses the existing safe-path helper, now extracted as
  `gallery_service.get_thumbnail_path()`, so the path-traversal guard and
  storage-root check aren't duplicated.

Frontend consumes this as a plain URL
(`getEventCoverUrl(slug)` in `lib/api.ts`) set directly as a CSS
`background-image` — no `guestFetchBlob`, no object URL lifecycle.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Reuse `/photos/{id}/thumbnail` with a relaxed auth dependency | No new route | Would weaken auth for the *general* thumbnail route, or require a parallel dependency just for this case — larger blast radius for a one-photo need |
| Issue a short-lived guest token before the code form renders, then use the existing blob pattern | Reuses existing auth machinery | Defeats the purpose of the access-code gate (guest would get a valid session token without entering a code); adds a request before first paint |
| Unauthenticated endpoint scoped to `cover_photo_id` only (chosen) | Minimal new surface; cannot be used to browse other photos; simple `<img>`/CSS usage | A second, narrower auth model to keep in mind alongside the guest-JWT one |

## Consequences

- There are now two distinct trust models for serving photo bytes: guest-JWT-gated
  (`/events/{event_id}/photos/{photo_id}/thumbnail`, and everything else in
  `gallery.py`) and public-but-single-photo
  (`/events/by-slug/{slug}/cover`). Anyone adding a new "public-ish" image
  endpoint should scope it as narrowly as this one (one designated photo,
  published-only) rather than loosening the guest-JWT dependency.
- `cover_photo_id` has no FK constraint (by design, see `models/event.py`), so
  `get_thumbnail_path` returning `None` for a dangling id is expected and
  handled as a plain 404, not an error.
- Cache-Control on this route is `public, max-age=300` (short), not the
  `immutable, max-age=31536000` used for regular thumbnails — the cover URL
  doesn't change when the photographer picks a different cover photo, so a
  long cache would serve a stale image.

## References

- `backend/app/routers/events.py` — `get_event_cover_by_slug`
- `backend/app/services/gallery.py` — `get_thumbnail_path`
- `frontend/lib/api.ts` — `getEventCoverUrl`
- `frontend/app/g/[slug]/page.tsx` — background usage
- [[2026-06-20-authenticated-image-blob-url-pattern]] — the pattern this deliberately does not use, and why
