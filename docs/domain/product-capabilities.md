# Product Capabilities

Last updated: 2026-06-20

---

## Event Management (Epic 1)

**Status:** Shipped — `feature/groom-event-management`

### What was added

**Backend (`backend/`):**
- Email+password auth: registration, login, JWT issuance and validation
- Event CRUD: create, read, update, soft-delete; owner-scoped access
- Slug management: auto-generation from bride+groom names, uniqueness enforced at DB level, 422 conflict with suggestions, redirect table for slug changes (301)
- Publish / unpublish: gates on slug + access_mode + cover_photo being set
- Album management: create, rename, delete, ceremony category tags (Ceremony / Sangeet / Mehendi / Haldi / Reception / Family Photos); max 10 per event
- QR code: on-demand PNG generation, streams to client, no disk storage; regenerates automatically when slug changes
- Admin endpoints: paginated event list, suspend / unsuspend, hard delete with full cascade
- APScheduler purge job: runs daily at 02:00, permanently purges events soft-deleted > 30 days ago (photos on disk, Qdrant vectors, PostgreSQL records)

**Frontend (`frontend/`):**
- Auth pages: login, register
- Owner dashboard: event list with status badges
- Event creation form: all required fields, access mode toggle, slug auto-generation from names, 422 suggestion pills
- Event edit page: update any field, publish / unpublish, delete with "type DELETE" confirmation and 30-day recovery messaging
- Album management page: create, rename, delete, ceremony category; album count display
- QR code page: display + download PNG button (proxied via Next.js API route)
- Admin dashboard: paginated all-events table, suspend / unsuspend / hard-delete with confirmation

---

## Guest Access (Epic: guest-access)

**Status:** Shipped — `feature/guest-access`

### What was added

**Backend (`backend/`):**
- Guest authentication endpoint (`POST /api/v1/events/{id}/guest-auth`): handles all three access modes in one call — access-code (case-insensitive), magic-link-otp (6-char system-generated code), public (no code required)
- Guest JWT issuance: `type: guest` discriminator, `sub = event_id`, sliding-window idle expiry via `X-Guest-Token` response header
- Session revocation: `POST /api/v1/events/{id}/revoke-guest-access` sets `guest_access_enabled=false` + `guest_access_revoked_at`; all tokens issued before revocation are rejected on validation
- Re-enable: `POST /api/v1/events/{id}/enable-guest-access`
- In-process `GuestRateLimiter`: per-`(event_id, ip)` lockout after 3 failed attempts; 15-minute cooldown; reset on success

**Frontend (`frontend/`):**
- `app/g/layout.tsx`: minimal no-Nav layout for all guest pages — clean entry and gallery experience
- `app/g/[slug]/page.tsx`: entry page; resolves event by slug, renders access-code or OTP entry form, handles already-authenticated redirect, lockout and revocation error messages, informative unavailable message for non-published events
- `app/g/[slug]/gallery/page.tsx`: auth guard redirects to entry if token missing/expired; placeholder for photo browsing (Album Gallery epic)
- `lib/api.ts` — `guestApiFetch`: guest-token-authenticated fetch helper; reads `X-Guest-Token` response header for sliding-window refresh; clears token on 401
- `lib/auth.ts` — `getGuestToken` / `setGuestToken` / `clearGuestToken` / `isGuestAuthenticated`: per-event guest token management in `localStorage`
