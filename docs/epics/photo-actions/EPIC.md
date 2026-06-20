# Photo Actions (Download, Share & Favorites)

**Status:** In Review
**Owner:** Product Team
**Last Updated:** 2026-06-20

## Summary
Allow guests to download individual or bulk sets of photos, share photos via a generated link, and maintain a personal favourites list so they can curate and revisit their best memories from the wedding.

## Requirements
1. Single download: guest can download the original full-resolution image for any photo.
2. Bulk download: guest can download all matched photos (from face search) as a ZIP archive.
3. Share: system generates a shareable link for any individual photo or album subset.
4. Favorites: guest can mark/unmark any photo as a favourite; favourites are persisted for the session (and optionally per email identity if OTP access is used).
5. My Favourites view: guests can view all their favorited photos in one place.
6. Downloads must serve the original image, not the compressed thumbnail.
7. Shareable links must be event-scoped and optionally time-limited.

## User Stories
- As a guest, I want to download the original high-resolution photo, so that I have the best quality copy for printing.
- As a guest, I want to download all photos I appear in as a single ZIP, so that I don't have to download them one at a time.
- As a guest, I want to generate a shareable link to a photo, so that I can send it to family members who couldn't attend.
- As a guest, I want to favourite photos during browsing and review them later in My Favourites, so that I can keep track of the shots I love most.
- As a bride/groom, I want shareable links to remain within the event's access context, so that private photos aren't accessible to the general public.

## Features
| Feature | Status |
|---------|--------|
| Single photo download (original resolution) | ✅ Done (reuses gallery endpoint) |
| Bulk ZIP download for face-search results | ✅ Done |
| Shareable link generation per photo | ✅ Done |
| Favourite / unfavourite toggle on photo | ✅ Done |
| My Favourites page | ✅ Done |
| Download tracking (for analytics) | Backlog (Admin Platform epic) |

## Success Metrics
- Single photo download starts within 2 seconds of clicking.
- ZIP download for 100 photos generates in under 30 seconds.
- Shareable links resolve to the correct photo 100% of the time.
- Favourites persist correctly across page refreshes.

## Decisions
- **2026-06-20:** Favourites are anonymous (session-only), keyed by JWT `sid` claim. No cross-session sync for MVP. See ADR `docs/decisions/2026-06-20-favourites-in-process-store.md`.
- **2026-06-20:** No per-guest download limit for MVP (REQ-9).
- **2026-06-20:** Shareable links expire after 72 hours (fixed window from creation). See ADR `docs/decisions/2026-06-20-share-token-jwt.md`.

## Open Questions
- [x] ~~Should favourites be anonymous (session-only) or tied to an email/OTP identity?~~ — Resolved: session-only, no cross-session sync for MVP.
- [x] ~~Is there a download limit per guest to control bandwidth costs?~~ — Resolved: no limit for MVP.
- [x] ~~Should shareable links expire, and if so, after how long?~~ — Resolved: 72-hour fixed window from creation.
