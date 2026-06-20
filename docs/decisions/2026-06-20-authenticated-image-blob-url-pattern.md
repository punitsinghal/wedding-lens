# ADR: Authenticated image loading via fetch + blob URLs
Date: 2026-06-20
Status: accepted

## Context

The gallery and lightbox need to display images that are served by the backend
behind Bearer token authentication. Browsers cannot attach custom headers to
`<img src>` requests, so the standard pattern of pointing `src` at an API URL
does not work for authenticated endpoints.

Three approaches were considered:

1. **Signed URL / token-in-query-param** — embed the guest token in the image
   URL as a query parameter so the browser can fetch it directly. Requires
   backend changes to accept token-as-query-param, and leaks the token into
   server logs and browser history.

2. **Next.js API proxy route** — create a `/api/proxy/[...path]` route that
   re-fetches the image from the backend and streams it to the browser. Adds a
   network hop and a new code surface, but centralises auth concerns.

3. **fetch() + URL.createObjectURL** — in the client component, call `fetch()`
   with the `Authorization` header, receive a `Blob`, create an object URL, and
   assign it to `img.src`. Object URLs are revoked on component unmount.

## Decision

Use option 3: **fetch + blob URL** via the `guestFetchBlob` helper in
`lib/api.ts`. This requires no backend changes, no extra server round-trip, and
keeps authentication logic entirely in the existing guest-token layer.

The helper is exposed as `guestFetchBlob(eventId, path): Promise<Blob>` and
follows the same token-refresh pattern as `guestApiFetch` (reads the
`X-Guest-Token` response header and persists any refreshed token).

Components that display authenticated images (`PhotoThumbnail`, `Lightbox`)
call `guestFetchBlob` inside a `useEffect`, store the object URL in state, and
call `URL.revokeObjectURL` on cleanup.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Token in query param | No JS fetch overhead; works with plain `<img>` | Token leaks into logs/history; requires backend change |
| Next.js API proxy | Centralised; clean `<img src>` | Extra network hop; new server-side code |
| fetch + blob URL (chosen) | No backend change; token never in URL; uses existing auth layer | One fetch per image; object URLs must be revoked |

## Consequences

- Every displayed thumbnail requires one authenticated `fetch` call. For a
  grid of 50 images this means up to 50 parallel requests on mount. This is
  acceptable because thumbnails are 600 px WebP blobs (small), and the browser
  limits parallelism naturally.
- All image-displaying components must follow the `useEffect` + cleanup
  (`URL.revokeObjectURL`) pattern or risk memory leaks.
- The `guestFetchBlob` helper is the canonical way to fetch binary resources
  with guest auth. Do not use raw `fetch` in components for authenticated
  binary endpoints.

## References

- `frontend/lib/api.ts` — `guestFetchBlob` implementation
- `frontend/components/gallery/PhotoThumbnail.tsx` — thumbnail usage
- `frontend/components/gallery/Lightbox.tsx` — lightbox usage
- Backend endpoint: `GET /api/v1/events/{event_id}/photos/{photo_id}/thumbnail`
