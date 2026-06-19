# ADR: Frontend Event Management Architecture
Date: 2026-06-19
Status: accepted

## Context

The WeddingLens Event Management epic requires a Next.js 14 frontend covering: auth (login/register), event CRUD, album management, QR code display, and an admin dashboard. Several cross-cutting patterns needed to be decided for the frontend that all future frontend epics must follow.

## Decision

Four patterns are established:

**1. JWT stored in localStorage, managed via React Context (`AuthProvider`)**
A single `AuthProvider` (`components/AuthProvider.tsx`) wraps the app in the root layout. It initialises `isLoggedIn` and `isAdminUser` from `lib/auth.ts` helpers on mount. All components that need auth state import `useAuth()` from `AuthProvider`. The raw JWT helpers (`getToken`, `setToken`, `removeToken`, `isAuthenticated`, `isAdmin`, `decodeJwtPayload`) live in `lib/auth.ts` and are also importable directly by Server-side-less client code (e.g. layout guards).

**2. All API calls through `lib/api.ts` — typed functions, never raw fetch in components**
`lib/api.ts` exports one named function per backend endpoint. It injects the `Authorization: Bearer` header automatically by calling `getToken()`. Error responses are thrown as parsed JSON objects (not `Error` instances), so callers can inspect `err.detail` and `err.suggestions` directly.

**3. Next.js API route as a CORS-safe proxy for binary responses**
`app/api/events/[eventId]/qr-code/route.ts` proxies the backend QR PNG through the Next.js origin. This satisfies the architectural constraint (frontend never calls data stores directly) and avoids CORS pre-flight issues for binary image responses. The proxy forwards the `Authorization` header from the client.

**4. Route-group layouts for auth guards**
`dashboard/layout.tsx` and `admin/layout.tsx` are Client Components that call `isAuthenticated()` / `isAdmin()` in a `useEffect` on mount and push to `/login` or `/dashboard` if the check fails. This avoids RSC complications with localStorage-based tokens. The pattern must be followed for any future protected route groups.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| localStorage JWT + React Context (chosen) | Simple; works on self-hosted VM with no external auth service; no cookie/CSRF complexity | Token visible to JS; mitigated by HttpOnly cookie being incompatible with the chosen JWT scheme (ADR `2026-06-19-photographer-auth-email-password.md`) |
| HttpOnly cookie JWT | Immune to XSS token theft | Requires backend to set `Set-Cookie`; adds same-site/CORS config; more complex for the self-hosted single-VM deployment |
| Direct fetch in pages | Less indirection | No single place to inject auth headers; types scatter across pages; hard to test or swap |
| Next.js `<Image>` for QR | Optimised | `<Image>` requires `width`/`height` and does not stream arbitrary backend bytes cleanly; plain `<img>` with a proxied URL is simpler and sufficient |

## Consequences

- Every new protected page/layout must import `isAuthenticated()` from `lib/auth.ts` and redirect if false (following the layout guard pattern).
- Every new API endpoint must be added as a named export in `lib/api.ts` before being called from a page.
- If the auth scheme changes (e.g., HttpOnly cookies), only `lib/auth.ts` and `lib/api.ts` need updating; all pages are unaffected.
- The QR proxy pattern can be reused for any other binary asset the backend serves that would otherwise hit CORS.

## References

- `docs/decisions/2026-06-19-photographer-auth-email-password.md` — JWT auth scheme decision
- `docs/features/event-management/design.md` — API surface and QR code strategy
- `docs/features/event-management/requirements.md` — functional requirements
