# Admin Platform & Analytics

**Status:** Draft
**Owner:** Product Team
**Last Updated:** 2026-06-19

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
| Admin event list and management (view / suspend / delete) | Backlog |
| Face processing pipeline monitor (queue, errors, throughput) | Backlog |
| Storage quota management per event | Backlog |
| Subscription and billing management | Backlog |
| Event-level analytics for event owners | Backlog |
| Automated alerting on pipeline failures | Backlog |
| Platform health dashboard (uptime, latency, error rates) | Backlog |

## Success Metrics
- Admin can identify and respond to a processing failure within 10 minutes via automated alert.
- Platform achieves 99.9% uptime measured monthly.
- Event owners can access analytics without contacting support.

## Decisions
<!-- Decisions made during this epic's lifetime -->

## Open Questions
- [ ] What analytics are shown to event owners vs restricted to admins only? — owner: Product Team
- [ ] Is billing managed in-platform or via an external provider (Stripe, etc.)? — owner: Product Team
- [ ] What is the storage quota per event tier? — owner: Product Team
