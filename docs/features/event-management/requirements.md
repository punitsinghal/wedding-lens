## Epic
docs/epics/event-management/EPIC.md

## Purpose
Enable bride/groom event owners to create and manage a wedding event — setting its identity (name, slug, cover photo), access model, and album structure — so that the event serves as a single, branded entry point that photographers can upload into and guests can access.

## Scenarios in scope
1. Event owner creates a new event (required fields, access mode, slug assigned, QR code generated)
2. Slug assignment and uniqueness validation (auto-generated default, owner-overridable, conflict rejection with suggestions)
3. Event owner edits an existing event (any field, including slug with redirect)
4. Event owner deletes an event (30-day soft-delete grace period before permanent purge)
5. Owner manages albums within an event (custom names, optional ceremony category tag, max 10)
6. QR code generation and download (PNG, auto-regenerates on slug change)
7. Admin manages events across the platform (view all, suspend, unsuspend, delete)
8. Owner publishes or unpublishes an event (controls guest accessibility independently of event existence)

## User stories / use cases
- As a bride/groom, I want to create a wedding event with a custom URL slug, so that I can share a memorable link with guests.
- As a bride/groom, I want the slug auto-generated from our names with the option to override it, so that I get a sensible default without being forced to type one.
- As a bride/groom, I want to edit my event details after creation, so that I can correct mistakes or update information as plans change.
- As a bride/groom, I want to delete my event, knowing I have 30 days to recover it, so that I can act without fear of irreversible data loss.
- As a bride/groom, I want to create albums with custom names and optional ceremony tags, so that guests can filter photos by the part of the wedding they attended.
- As a bride/groom, I want to download a print-quality QR code for my event, so that I can include it on wedding invitations.
- As a bride/groom, I want to publish my event only when it's ready, so that guests cannot access an incomplete gallery.
- As an admin, I want to view and suspend any event on the platform, so that I can take action without permanently deleting data.

## Functional requirements

### Scenario 1 — Event creation
1. REQ-1 (Scenario 1): The system must accept event creation with the following required fields: event name, bride name, groom name, event date, and access mode (`access-code`, `magic-link-otp`, or `public`).
2. REQ-2 (Scenario 1): When access mode is `access-code`, the owner must supply an access code at creation time.
3. REQ-3 (Scenario 1): On successful creation, the system assigns a unique slug and generates a QR code for the event.
4. REQ-4 (Scenario 1): Only an authenticated event owner (email+password JWT) may create an event.
5. REQ-5 (Scenario 1): A newly created event starts in unpublished (draft) state and is inaccessible to guests.

### Scenario 2 — Slug assignment and uniqueness
6. REQ-6 (Scenario 2): The slug is auto-generated from bride and groom names (e.g. `rahul-priya`) at creation time as a default; the owner may override it before saving.
7. REQ-7 (Scenario 2): Slugs must be unique across the platform; uniqueness is enforced as a hard constraint.
8. REQ-8 (Scenario 2): Slug format: lowercase letters, digits, and hyphens only; no spaces, special characters, or leading/trailing hyphens; maximum 50 characters.
9. REQ-9 (Scenario 2): On a slug conflict, the system rejects the submission with a validation error and presents a list of suggested alternative slugs for the owner to choose from or further edit.

### Scenario 3 — Event editing
10. REQ-10 (Scenario 3): The owner may update any event field after creation, including the slug.
11. REQ-11 (Scenario 3): Changes to event fields are reflected on the public event page immediately upon save.
12. REQ-12 (Scenario 3): When the slug is changed, the old slug permanently redirects (301) to the new slug so that existing QR codes and shared links remain valid.
13. REQ-13 (Scenario 3): When the owner changes the access mode, the change applies only to new guest access attempts; existing active guest sessions are not invalidated.

### Scenario 4 — Event deletion
14. REQ-14 (Scenario 4): When an owner deletes an event, the event enters a 30-day soft-delete grace period; it is inaccessible to guests (returns 404) but data is retained and recoverable by an admin.
15. REQ-15 (Scenario 4): After the 30-day grace period, all associated data is permanently purged: photos on disk (`STORAGE_PATH`), face embeddings in Qdrant (scoped by `event_id`), and all PostgreSQL records for that event.
16. REQ-16 (Scenario 4): The owner must pass an explicit confirmation step before deletion is executed.

### Scenario 5 — Album management
17. REQ-17 (Scenario 5): An owner can create albums within an event; each album has a free-text name and an optional ceremony category tag from the fixed list: `Ceremony`, `Sangeet`, `Mehendi`, `Haldi`, `Reception`, `Family Photos`.
18. REQ-18 (Scenario 5): The ceremony category tag drives guest-facing album filtering; the free-text name is for owner organisation.
19. REQ-19 (Scenario 5): Albums can be renamed and deleted by the event owner.
20. REQ-20 (Scenario 5): When an album is deleted, photos assigned to it are automatically moved to an uncategorized state; deletion is never blocked by photo presence.
21. REQ-21 (Scenario 5): A maximum of 10 albums per event is enforced.

### Scenario 6 — QR code
22. REQ-22 (Scenario 6): The system generates a QR code for each event at creation time, encoding the event's public gallery URL (based on the current slug).
23. REQ-23 (Scenario 6): The owner can download the QR code as a PNG file.
24. REQ-24 (Scenario 6): When the event slug changes, the QR code is automatically regenerated to encode the new URL; the old QR code remains functional via the 301 redirect.

### Scenario 7 — Admin event management
25. REQ-25 (Scenario 7): A platform admin can view a paginated list of all events across all owners, showing at minimum: event name, owner, event date, status (draft / published / suspended / deleted), and photo count.
26. REQ-26 (Scenario 7): A platform admin can suspend an event; suspended events are inaccessible to guests but data is retained.
27. REQ-27 (Scenario 7): A suspended event can be unsuspended by an admin, restoring guest access immediately.
28. REQ-28 (Scenario 7): A platform admin can permanently delete any event, applying the same cascade as owner deletion (REQ-15) without a grace period.

### Scenario 8 — Publish / unpublish
29. REQ-29 (Scenario 8): An event has a published state; only published events are accessible to guests.
30. REQ-30 (Scenario 8): The owner can publish or unpublish their event at any time.
31. REQ-31 (Scenario 8): An event may only be published if slug, access mode, and cover photo are all set.

## Non-functional requirements
- NFR-1: Event creation end-to-end must be completable in under 2 minutes.
- NFR-2: Slug uniqueness must be enforced at the database level; no race condition window.
- NFR-3: Event deletion cascade must be consistent — partial deletion (some data purged, some retained) is not an acceptable outcome.
- NFR-4: Admin event list must use server-side pagination; must not load all events into memory at once.

## Context
- The backend (FastAPI/PostgreSQL) owns all event data exclusively; the frontend must not access data stores directly (architectural constraint).
- Face embeddings are stored in Qdrant Cloud scoped per `event_id`; purging a deleted event's embeddings requires a Qdrant collection or payload filter delete by `event_id`.
- Auth for event owners is email+password with JWT (decided in ADR `docs/decisions/2026-06-19-photographer-auth-email-password.md`).
- The platform runs on a single VM; the 30-day grace period purge must be handled by a scheduled background job, not a real-time trigger.

## Out of scope
- Guest access flows (access code entry, OTP email, QR scan landing) — covered by the Guest Access epic.
- Admin analytics and pipeline monitoring — covered by the Admin Platform epic.
- Photo upload and processing — covered by the Photographer Dashboard and AI Face Processing epics.
- Owner notification when admin suspends or deletes an event — not required.
- Event owner account creation and authentication — assumed to exist as a prerequisite; not part of this feature.

## Open questions
All resolved during grooming session on 2026-06-19.

## Acceptance criteria
- AC-1 (Scenario 1): Given an authenticated owner submits all required fields with a valid access mode, the event is created in unpublished state, a unique slug is assigned, and a QR code PNG is available for download.
- AC-2 (Scenario 1): Given an unauthenticated request to create an event, the system returns 401.
- AC-3 (Scenario 2): Given the owner submits bride name "Priya" and groom name "Rahul", the system pre-fills the slug as `priya-rahul` (or similar derivation).
- AC-4 (Scenario 2): Given a slug that already exists on the platform, the system rejects the submission and presents at least two alternative slug suggestions.
- AC-5 (Scenario 2): Given a slug containing uppercase letters, spaces, or special characters, the system rejects it with a validation error.
- AC-6 (Scenario 2): Given a slug longer than 50 characters, the system rejects it with a validation error.
- AC-7 (Scenario 3): Given an owner changes the event name, the updated name is visible on the event page without a full page reload.
- AC-8 (Scenario 3): Given an owner changes the slug from `old-slug` to `new-slug`, navigating to `<host>/old-slug` redirects (301) to `<host>/new-slug`.
- AC-9 (Scenario 3): Given an owner changes the access mode, guests with active sessions retain access; new guests are prompted by the new mode.
- AC-10 (Scenario 4): Given an owner confirms deletion, the event URL returns 404 immediately and data remains on disk for 30 days.
- AC-11 (Scenario 4): Given 30 days have elapsed since deletion, all photos, embeddings, and database records for that event are permanently removed.
- AC-12 (Scenario 5): Given an owner creates an album named "Pre-Wedding" with category tag `Mehendi`, the album appears in the guest-facing `Mehendi` filter.
- AC-13 (Scenario 5): Given an owner deletes an album that contains photos, the photos move to uncategorized state and the album is removed.
- AC-14 (Scenario 5): Given an event already has 10 albums, the system rejects creation of an 11th album with a validation error.
- AC-15 (Scenario 6): Given a newly created event, the QR code encodes the correct public gallery URL and scans successfully on a standard mobile camera.
- AC-16 (Scenario 6): Given an owner changes the event slug, the downloadable QR code PNG encodes the new URL.
- AC-17 (Scenario 7): Given an admin suspends an event, guests attempting to access it see an informative unavailable message; event data is not deleted.
- AC-18 (Scenario 7): Given an admin unsuspends an event, guests can access it again immediately.
- AC-19 (Scenario 8): Given an owner attempts to publish an event missing a cover photo, the system rejects the publish action with a validation error listing missing required fields.
- AC-20 (Scenario 8): Given an owner publishes an event, guests can immediately access it via its slug URL and QR code.
- AC-21 (Scenario 8): Given an owner unpublishes a published event, guests attempting to access it receive an informative unavailable message.
