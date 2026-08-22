# ADR: Presigned R2 URLs Replace Fetch+Blob Image Delivery
Date: 2026-08-22
Status: accepted (delivery mechanism refined during /build — see amendment below)

> **Amendment (2026-08-22, during Phase 3 implementation):** the delivery
> mechanism for one-off/on-demand endpoints (lightbox, single download,
> photographer preview, cover photo) changed from "return `{url}` as JSON,
> rewrite the frontend to consume it directly" to **302-redirecting the
> existing authenticated endpoint straight to the presigned R2 URL**.
> `fetch()` follows redirects transparently and drops `Authorization` on the
> cross-origin hop (harmless — the presigned URL's signature is the real
> auth), so the existing `guestFetchBlob`/`ownerFetchBlob`/`fetchAuthedBlob`
> pattern keeps working completely unchanged for these endpoints, while
> bytes still flow R2→browser directly — the same egress saving, zero
> frontend rewrite. The "8 components need rewriting" consequence below no
> longer holds for 7 of them. The one exception is the gallery list
> endpoint's `thumbnail_url` field: it's fetched up to 50-at-a-time per page
> load, so embedding a ready-to-use presigned URL directly in the list
> response (rather than 50 individual redirect round-trips) is worth the
> small frontend change — `PhotoThumbnail`/favourites-grid/search-results
> components still need to switch from fetch+blob to `<img src>` directly
> for that one field. Everything else in this ADR's reasoning (why a
> presigned URL is self-authenticating, why the original blob-fetch ADR's
> problem no longer applies, why ZIP stays backend-proxied) is unchanged.

## Context

`2026-08-22-cloudflare-r2-photo-storage.md` decided to migrate photo storage to Cloudflare R2 specifically to capture R2's $0/GB egress benefit (vs. Railway's $0.05/GB) — but that saving only materializes if photo bytes flow directly between the client and R2, not through the backend. `docs/wip/analysis-photo-storage-migration-r2-2026-08-22.md` found that the frontend currently does the opposite everywhere: `2026-06-20-authenticated-image-blob-url-pattern.md` established `fetch()` + `Authorization: Bearer` header + `blob()` + `URL.createObjectURL()` as the way to display every authenticated image (thumbnails, lightbox, album views, cover-photo picker), specifically because `<img src>` cannot carry a custom header.

A presigned R2 URL is self-authenticating — its signature, embedded in the query string, is the credential — and is designed to be dropped directly into `<img src>`. Continuing to wrap a presigned URL in an authenticated `fetch()` call is not just redundant, it can actively break: an `Authorization` header sent cross-origin to `*.r2.cloudflarestorage.com` has no meaning to R2 and may trigger CORS preflight failures depending on bucket CORS configuration.

This ADR was reached during `/design` for the R2 storage migration (see `docs/features/photo-storage-migration/design.md`), where three read-delivery options were presented — backend-proxied (no frontend change, no egress saving), presigned-everywhere (full egress saving, full frontend rewrite), and a cover-photo-only hybrid. Presigned-everywhere was chosen.

## Decision

Replace the fetch+blob pattern with direct `<img src={presignedUrl}>` (and direct `<a href={presignedUrl}>`/`window.location` for single-photo downloads) across every component that currently implements `2026-06-20-authenticated-image-blob-url-pattern.md`. The backend's photo/thumbnail/lightbox/download API responses change from returning a backend-relative path (`thumbnail_url: "/api/v1/events/.../thumbnail"`) to returning a presigned, single-object, single-operation R2 URL with a bounded TTL.

This ADR **supersedes `2026-06-20-authenticated-image-blob-url-pattern.md`** for all photo-display and single-photo-download surfaces. That ADR's reasoning is not wrong — it correctly solved "how do you send an auth header to an `<img>` tag" — it's just solving a problem that no longer exists once the URL itself carries its own scoped authorization instead of relying on the guest's session token.

Bulk ZIP download is **explicitly excluded** from this decision and keeps the existing fetch+blob pattern unchanged — R2 has no server-side "combine N objects into one archive" primitive, so ZIP generation must remain backend-proxied regardless (the backend fetches each constituent object from R2 and streams the assembled archive, exactly as it reads from local disk today).

Event cover photo delivery is unaffected in kind — it already uses a direct, unauthenticated URL (`getEventCoverUrl`); only the URL's origin changes (backend route → R2 presigned URL).

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Presigned URLs, direct `<img src>` (chosen) | Realizes the R2 storage ADR's egress-cost case in full; removes a fetch+blob+revoke lifecycle from 8 components; browser-native image loading (caching, lazy-load, prefetch all work normally, which `blob:` URLs partially defeat) | Rewrites 8 frontend components; retires an existing, deliberate ADR; requires a TTL/expiry strategy so a long-open gallery tab doesn't show broken images (see `design.md` REQ-10) |
| Keep fetch+blob, backend proxies R2 under existing endpoints | Zero frontend change | Forfeits the egress-cost saving that is the primary financial justification for choosing R2 in the first place — see `2026-08-22-cloudflare-r2-photo-storage.md`'s option table, which already rejected this shape for the same reason |
| Token-in-query-param on today's backend endpoints (put the guest JWT itself in the URL, skip R2 presigning) | No R2-specific work, `<img src>` works directly | This is exactly Option 1 the original ADR rejected, and for good reason: it leaks the guest's actual session credential into logs/history. A presigned R2 URL is meaningfully different — it authorizes exactly one object for a short window, not the guest's whole session — but reusing the *guest token* this way would reintroduce the original ADR's rejected risk without gaining anything R2 presigning doesn't already provide |

## Consequences

- 8 components lose their `fetch`+`useEffect`+`URL.revokeObjectURL` lifecycle: `PhotoThumbnail`, favourites grid, `SearchResults`' result cards, photographer upload/manage grid, album detail grid, event-dashboard cover picker, `Lightbox`, and the share-page photo view. Each becomes a plain `<img src={url}>` (or `<a href={url}>` for downloads).
- `guestFetchBlob`, `ownerFetchBlob`, and `fetchAuthedBlob` in `frontend/lib/api.ts` are no longer needed for photo display once this ships; confirm no other binary-fetch use before removing them.
- API responses that currently return a relative path (`thumbnail_url`, and the hand-built `/lightbox` and `/thumbnail` paths in `Lightbox.tsx` and the share page) must instead return a ready-to-use presigned URL string. The share page and lightbox specifically need a new response field, since today they construct the path themselves rather than reading it from a response.
- Presigned URL TTL must satisfy REQ-10 from `docs/features/photo-storage-migration/requirements.md` ("must remain valid for at least the duration of a guest's normal active browsing session") — sized and refreshed per the approach in `design.md`.
- Browser-level image caching now behaves normally (an `<img src>` URL can be cached by the browser/CDN the way a `blob:` URL cannot be shared across requests) — a minor positive side effect, not a design goal.
- Single-photo download (`downloadPhoto` in `lib/api.ts`) changes from "fetch full bytes through the backend, then blob-download" to "navigate to / anchor-download the presigned URL directly" — bytes no longer transit the Railway backend at all for this path, which is where most of the per-download egress saving comes from.
- No change to guest session token authentication itself — the guest JWT still gates every API call that *issues* a presigned URL; only the already-issued URL's own bytes bypass the backend.

## References
- `docs/decisions/2026-06-20-authenticated-image-blob-url-pattern.md` — superseded by this ADR for photo display and single-photo download
- `docs/decisions/2026-08-22-cloudflare-r2-photo-storage.md` — the storage migration this ADR realizes the cost case for
- `docs/wip/analysis-photo-storage-migration-r2-2026-08-22.md` — impact analysis that surfaced this collision
- `docs/features/photo-storage-migration/design.md` — full technical design, including TTL/refresh approach and per-component change list
