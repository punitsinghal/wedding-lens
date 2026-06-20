# ADR: SelfieUpload uses raw fetch for multipart POST with guest auth
Date: 2026-06-20
Status: accepted

## Context

`SelfieUpload` needs to POST a multipart form (`selfie` file field) to
`POST /api/v1/events/{event_id}/search` using the guest JWT, and must read the
`X-Guest-Token` response header from a non-2xx response as well as from a 2xx
response so the token can be refreshed even when an error is returned.

The existing `guestApiFetch` helper in `lib/api.ts` handles JSON bodies only:
it sets `Content-Type: application/json` and calls `JSON.stringify` on the
body, both of which are incompatible with multipart form data. It also throws
immediately on non-2xx responses without first reading response headers.

`uploadPhoto` (also in `lib/api.ts`) uses the same raw `fetch` approach for its
multipart owner upload, establishing a precedent for multipart within the
project.

## Decision

`SelfieUpload` calls `fetch` directly with a `FormData` body, attaches the
guest JWT from `getGuestToken`, reads `X-Guest-Token` from the response
headers before branching on `response.ok`, and delegates token persistence to
the `onTokenRefresh` prop rather than calling `setGuestToken` internally.

This keeps the component testable in isolation (the `onTokenRefresh` callback
can be mocked) and follows the same raw-fetch-for-multipart pattern already
used by `uploadPhoto`.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Extend `guestApiFetch` to accept `FormData` | Centralised helper; consistent with other guest calls | `guestApiFetch` currently sets `Content-Type: application/json` and calls `JSON.stringify`; touching it risks breaking existing callers |
| Add a new `guestApiFetchMultipart` helper in `lib/api.ts` | Keeps API calls out of components | Adds another generic helper for one use-case; the logic is simple enough to live inline |
| Raw `fetch` in `SelfieUpload` (chosen) | Consistent with `uploadPhoto` precedent; component stays self-contained; no risk to existing helpers | Slight duplication of auth header assembly; mitigated by delegating token storage via prop |

## Consequences

- Any future guest multipart endpoint should follow the same raw-fetch pattern
  (or extract a `guestFetchMultipart` helper if there are multiple callers).
- `SelfieUpload` receives the current guest token as a prop and calls
  `onTokenRefresh` rather than reading/writing `localStorage` itself — this
  makes the component easier to unit-test and avoids tight coupling to storage.

## References

- `frontend/components/search/SelfieUpload.tsx`
- `frontend/lib/api.ts` — `uploadPhoto` (raw fetch precedent for multipart)
- `frontend/lib/api.ts` — `guestApiFetch` (existing guest JSON helper)
- Backend endpoint: `POST /api/v1/events/{event_id}/search`
