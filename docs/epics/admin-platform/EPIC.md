# Admin Platform & Analytics

**Status:** Groomed — ready for /design
**Owner:** Product Team
**Last Updated:** 2026-08-15

## Summary
Give platform administrators a central dashboard to manage all wedding events, monitor photo processing pipelines, manage storage and subscriptions, and view event-level analytics so the platform runs reliably at scale.

## Requirements
1. Admins can view, suspend, or delete any event on the platform.
2. Admins can monitor the face processing pipeline: queue depth, error rate, throughput, and per-event processing status.
3. Admins can manage storage quotas and allocations per event.
4. Admins can manage platform subscriptions and billing tiers (if applicable).
5. Event-level analytics are available to event owners: total views, downloads, face searches performed, most-viewed photos.
6. Platform must support 99.9% uptime; admin tooling includes health checks and alerting.
7. Admins receive automated alerts for pipeline failures or queue backlogs exceeding thresholds.

## User Stories
- As an admin, I want to view all active events and their photo counts, so that I can monitor platform usage at a glance.
- As an admin, I want to see face processing queue depth and error rates per event, so that I can intervene when processing is stuck.
- As an admin, I want to suspend an event that violates terms of service, so that I can take action without deleting data permanently.
- As a bride/groom, I want to see analytics for my event (views, downloads, searches), so that I can understand how guests are engaging with our gallery.
- As an admin, I want to receive automated alerts when a processing pipeline fails, so that issues are caught before guests notice.

## Features
| Feature | Status |
|---------|--------|
| Admin event list (view/suspend/delete) | Partial — endpoints + UI shipped under Event Management (#12); missing photo count/storage/last-activity columns. Groomed — ready for /design to close the gap |
| Admin hard delete | Partial — shipped (#12), but Qdrant vector deletion is currently a stub (`_stub_qdrant_delete`); pulled into scope as REQ-3a. Groomed — ready for /design |
| Face processing pipeline monitor (per-event pending/processing/failed/completed) | Groomed — ready for /design |
| Automated failure-rate alerting (email, APScheduler) | Groomed — ready for /design |
| Event-level analytics for event owners (views, downloads, searches) | Groomed — ready for /design |
| Platform health dashboard (event/photo/storage totals, 24h error rate) | Groomed — ready for /design |
| Storage quota management per event | Deferred — out of scope for MVP (admin can view usage, not enforce caps); see requirements.md Out of Scope |
| Subscription and billing management | Deferred — out of scope for MVP; no in-platform billing UI |

## Success Metrics
- Admin can identify and respond to a processing failure within 10 minutes via automated alert.
- Platform achieves 99.9% uptime measured monthly.
- Event owners can access analytics without contacting support.

## Decisions
<!-- Decisions made during this epic's lifetime -->
- **2026-08-15 (grooming):** Storage quota management and subscription/billing are out of scope for MVP — deferred, no in-platform enforcement or billing UI. This epic's MVP scope is the 4 net-new scenarios (processing monitor, failure alerting, event-owner analytics, platform health dashboard) plus closing two gaps found in already-shipped admin code (missing photo-count/storage/last-activity context; stubbed Qdrant deletion on hard delete).
- **2026-08-15:** Storage usage metric = original photo file bytes only (thumbnails/variants excluded).
- **2026-08-15:** `download_events`/`search_events` store raw counts only — no guest session token, consistent with the Privacy & Security epic's no-guest-identity-in-analytics stance.
- **2026-08-15:** Processing-failure alert emails include a direct link to the event's monitor page.
- **2026-08-15:** Event owners see views/downloads/searches only; storage usage and photo counts are admin-only surfaces.
- Full detail: `docs/features/admin-platform/requirements.md`.

## Open Questions
- [x] What analytics are shown to event owners vs restricted to admins only? → Owners see views/downloads/searches; storage/photo-count totals are admin-only. — resolved 2026-08-15
- [x] Is billing managed in-platform or via an external provider? → Deferred; out of scope for MVP, no billing UI at all. — resolved 2026-08-15
- [x] What is the storage quota per event tier? → Deferred; no per-event quota enforcement in MVP, admin can only view usage. — resolved 2026-08-15
- [ ] What is the admin promotion flow long-term — manual DB update (MVP) or a dedicated promotion UI post-MVP? — owner: Engineering, not a build blocker
