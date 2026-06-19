# Product Capabilities

Last updated: 2026-06-19

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
