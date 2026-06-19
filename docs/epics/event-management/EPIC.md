# Event Management

**Status:** Done
**Owner:** Product Team
**Last Updated:** 2026-06-19

## Summary
Enable bride/groom and admins to create and manage wedding events with a unique URL, access code, and album structure so that guests have a single, branded entry point to all wedding photos.

## Requirements
1. A wedding event must have: event name, bride name, groom name, event date, cover photo, access code, and a human-readable slug URL (e.g. `wedding.app/rahul-priya`).
2. The event owner (bride/groom) can create, edit, and delete their event.
3. Albums within an event can be categorised by ceremony type: Ceremony, Sangeet, Mehendi, Haldi, Reception, Family Photos.
4. Each event has an access control mode: access-code, magic-link OTP, or public (no login).
5. Administrators can manage all events, suspend events, and view event-level analytics.
6. The system must generate a QR code for each event that links to the wedding album.
7. Event slugs must be unique across the platform.

## User Stories
- As a bride/groom, I want to create a wedding event with a custom URL, so that I can share a memorable link with our guests.
- As a bride/groom, I want to set an access code on my event, so that only invited guests can view our photos.
- As a bride/groom, I want to upload a cover photo for the event, so that the wedding portal has a personal feel.
- As a bride/groom, I want to create named albums (Sangeet, Mehendi, etc.) within my event, so that guests can browse photos by ceremony.
- As an admin, I want to view and manage all events on the platform, so that I can handle support requests and monitor usage.
- As a guest, I want to scan a QR code from my invitation, so that I can access the wedding album instantly without typing a URL.

## Features
| Feature | Status |
|---------|--------|
| Event creation form (name, date, slug, cover photo, access code) | Shipped |
| Unique slug generation and validation | Shipped |
| Album management (create, rename, delete, categorise) | Shipped |
| QR code generation per event | Shipped |
| Admin event management dashboard | Shipped |
| Event edit / delete by owner | Shipped |

## Success Metrics
- An event can be created end-to-end in under 2 minutes.
- QR code scan successfully routes to the correct event page 100% of the time.
- Slug uniqueness enforced with zero collisions in production.

## Decisions
<!-- Decisions made during this epic's lifetime -->

## Open Questions
- [ ] Should the slug be auto-generated from bride/groom names or manually set by the owner? — owner: Product Team
- [ ] What is the maximum number of albums per event? — owner: Product Team
- [ ] Should deleted events purge photos immediately or retain for 30 days? — owner: Product Team
