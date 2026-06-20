---
feature: Admin Platform & Analytics
status: Draft
owner: Product Team
created: 2026-06-19
---

# Admin Platform & Analytics — Requirements

## Epic

docs/epics/admin-platform/EPIC.md

---

## Purpose

Give platform administrators a central dashboard to manage all wedding events, monitor the face processing pipeline, and view platform health metrics, while giving event owners visibility into their own event analytics — so the platform runs reliably and event owners can measure guest engagement without contacting support.

---

## Scenarios in Scope

1. Admin views a paginated list of all events with key metrics (status, photo count, last activity).
2. Admin suspends or unsuspends an event, with analytics context visible alongside the action.
3. Admin hard-deletes an event, bypassing the 30-day soft-delete grace period.
4. Admin views the face processing pipeline monitor per event (pending / processing / failed / completed counts).
5. Admin receives an automated email alert when per-event processing failure rate exceeds 10% in a 1-hour window.
6. Event owner views analytics for their own event (total views, total downloads, total face searches).
7. Admin views the platform-level health dashboard (total storage used, total events, total photos, 24-hour error rate).

---

## User Stories / Use Cases

**Scenario 1 — Event list**
- As an admin, I want to see all events in a paginated table with their status, photo count, storage used, and last activity timestamp, so that I can monitor platform usage at a glance without opening each event individually.

**Scenario 2 — Suspend / unsuspend**
- As an admin, I want to suspend or unsuspend an event from the event detail view, and see the event's photo count and last activity before acting, so that I have enough context to make the right call before restricting guest access.

**Scenario 3 — Hard delete**
- As an admin, I want to permanently delete a soft-deleted or active event — including all photos, face embeddings, and analytics records — bypassing the 30-day grace period, so that I can honour GDPR erasure requests or remove policy-violating content immediately.

**Scenario 4 — Processing monitor**
- As an admin, I want to view per-event counts of face processing jobs in each state (pending, in-progress, failed, completed), so that I can identify stuck or failing pipelines and intervene before guests notice degraded search results.

**Scenario 5 — Automated failure alert**
- As an admin, I want to receive an email notification when the face processing failure rate for any event exceeds 10% in a rolling 1-hour window, so that I am alerted to failures without having to monitor the dashboard continuously.

**Scenario 6 — Event owner analytics**
- As an event owner, I want to see the total views, total downloads, and total face searches performed for my event, so that I can understand how guests are engaging with the gallery.

**Scenario 7 — Platform health dashboard**
- As an admin, I want to see aggregate platform metrics — total events, total photos, total storage used (GB), and the error rate for the past 24 hours — so that I can assess overall platform health at a glance.

---

## Functional Requirements

**REQ-1 (Scenario 1): Event list view**
The admin event list must display all events (across all statuses: draft, published, suspended, soft-deleted) in a paginated table. Each row must show: event name, event status, total photo count, storage used (MB or GB), and last activity timestamp. The list must support filtering by status and sorting by last activity and photo count.

**REQ-2 (Scenario 2): Suspend / unsuspend with context**
The admin event detail view must display the event's photo count, storage used, last activity timestamp, and processing monitor summary alongside the suspend / unsuspend action. Suspending an event must set its status to `suspended` and immediately block guest access. Unsuspending must restore the event to `published` status.

**REQ-3 (Scenario 3): Admin hard delete**
The admin must be able to permanently delete any event (regardless of current status). A hard delete must remove: all photo files from disk, all face embedding vectors from Qdrant (scoped to the event's `event_id` collection/namespace), all PostgreSQL records for the event (photos, face records, analytics events), and the event row itself. The action must require explicit confirmation (separate confirmation step, not just a single click). The operation must be irreversible.

**REQ-4a (Scenario 4): Per-event processing monitor**
The admin must be able to view a processing monitor for any event showing job counts in four states: pending, in-progress, failed, and completed. Counts must reflect the current state of the face processing pipeline for that event.

**REQ-4b (Scenario 4): Processing monitor access**
The processing monitor must be accessible from the admin event detail view. Counts must be queryable from the existing face processing job tracking in PostgreSQL.

**REQ-5a (Scenario 5): Failure rate alerting**
The system must calculate the face processing failure rate per event in a rolling 1-hour window. If the failure rate exceeds 10% (failed jobs / total completed + failed jobs in the window), the system must send an email notification to the platform administrator's registered email address.

**REQ-5b (Scenario 5): Alert delivery**
Alert emails must be sent via SMTP using no third-party alerting service. Each alert email must identify the affected event (event name and ID). Repeat alerts for the same event must not be sent more frequently than once per hour while the condition persists.

**REQ-5c (Scenario 5): Alert scheduling**
The failure rate check must run on a scheduled basis using APScheduler (consistent with the existing background job architecture). The check interval must be no greater than 5 minutes to ensure timely detection within the 1-hour window.

**REQ-6a (Scenario 6): Event owner analytics**
An authenticated event owner must be able to view analytics for their own event only. The analytics view must expose: total photo views (photo detail page loads or downloads initiated), total downloads (ZIP or individual photo downloads completed), and total face searches performed.

**REQ-6b (Scenario 6): Analytics data model**
Analytics events must be recorded in PostgreSQL in a `download_events` table (one row per download action) and a `search_events` table (one row per face search). Both tables must store `event_id` and a timestamp. Guest identity must not be stored — tracking is anonymous (no guest session ID or IP address in these records).

**REQ-6c (Scenario 6): Analytics isolation**
An event owner must not be able to view analytics for events they do not own. The backend must enforce ownership on all analytics endpoints.

**REQ-7a (Scenario 7): Platform health dashboard**
The admin health dashboard must display: total number of events on the platform (all statuses), total number of photos across all events, total storage used in GB (sum of photo file sizes on disk), and the platform-wide face processing error rate for the past 24 hours (failed jobs / total jobs in window).

**REQ-7b (Scenario 7): Health data source**
All platform health metrics must be computed from PostgreSQL queries at request time (batch queries — no real-time streaming). Metrics must reflect the state at the time the page is loaded; there is no requirement for automatic refresh.

**REQ-8 (All admin scenarios): Admin role enforcement**
All admin endpoints and views must be restricted to users with `is_admin = true` on their photographer/user record. Requests from non-admin authenticated users must receive HTTP 403. Unauthenticated requests must receive HTTP 401.

---

## Non-Functional Requirements

**NFR-1: Admin endpoint response time**
Admin list and dashboard endpoints must respond within 3 seconds under normal load (single VM, up to 500 events). Pagination must be used to avoid full-table scans returning unbounded result sets.

**NFR-2: Hard delete atomicity**
Hard delete must be performed in a way that prevents partial deletion leaving orphaned data. If any step fails (disk removal, Qdrant deletion, PostgreSQL deletion), the failure must be logged and the operation must be retried or flagged for manual remediation — the event must not be left in an ambiguous state.

**NFR-3: Analytics write path — no blocking**
Recording download and search events must be non-blocking with respect to the guest-facing response. Analytics writes may be fire-and-forget (using FastAPI BackgroundTasks) — a write failure must not cause the guest's download or search request to fail.

**NFR-4: Alert deduplication**
The alerting system must not send duplicate alert emails for the same event within a 1-hour window. Deduplication state may be stored in-memory (APScheduler job state) or in PostgreSQL.

**NFR-5: Admin promotion — manual in MVP**
Setting `is_admin = true` is a manual database operation in MVP. There is no admin promotion UI. Engineering performs this via direct SQL update during onboarding.

---

## Context

**Dependencies**

- Event management (view / suspend / soft-delete) is partially built in the Event Management epic. This feature extends those capabilities with analytics context (Scenario 2) and adds hard delete (Scenario 3).
- The face processing pipeline runs as FastAPI `BackgroundTask` workers, in-process. Job state (pending / in-progress / failed / completed) is tracked in PostgreSQL and is the source of truth for the processing monitor (Scenario 4) and failure rate alerting (Scenario 5).
- APScheduler is already present in the architecture for background scheduling. The failure-rate check job (Scenario 5) must be registered with APScheduler on startup.
- Qdrant Cloud is used for face embedding vector storage. Hard delete (Scenario 3) must call the Qdrant API to delete all vectors for the event's `event_id` namespace before the event record is removed from PostgreSQL.
- Analytics tables (`download_events`, `search_events`) are new — they require new PostgreSQL migrations.

**Auth model**

- Photographer / event owner authentication: email + password JWT (or Google OAuth — TBD in auth epic). The `is_admin` boolean lives on the same user table.
- Guest access uses QR + optional PIN — guests are not authenticated users and must not be granted any admin or analytics access.

**Storage usage metric**

- Storage used is the sum of photo file bytes on local disk for the event's photos directory. Whether thumbnails are included in this total is an open question (see below). For MVP the metric is best-effort — it does not need to be real-time to the byte.

---

## Out of Scope

- Billing and subscription management — single-tier MVP with flat fee or self-hosted deployment; no in-platform billing UI.
- Per-event storage quotas — admin can view storage usage but cannot set or enforce per-event caps in MVP.
- Third-party alerting integrations — no PagerDuty, Slack, OpsGenie, or webhook delivery; email only.
- Guest-level analytics — no tracking of which guest performed which search or download (privacy constraint). All analytics are aggregated at the event level.
- Real-time streaming analytics — no WebSocket or server-sent event dashboard; all metrics are batch PostgreSQL queries loaded on page request.
- Admin promotion UI — `is_admin` is set via direct SQL in MVP.

---

## Open Questions

- [ ] What analytics are visible to event owners vs restricted to admins only — for example, is total storage usage for their event visible to the owner, or admin-only? — owner: Product Team
- [ ] Should the processing failure alert email include a direct link to the affected event's monitor page in the admin dashboard? — owner: Product Team
- [ ] What is the admin promotion flow — is a manual DB update acceptable long-term, or should an admin-promotion UI be added post-MVP? — owner: Engineering
- [ ] Should `download_events` and `search_events` store a guest session ID (anonymous token, not identity) for deduplication, or is a raw count without deduplication acceptable? — owner: Legal / Product Team
- [ ] What is the storage usage metric — total bytes on disk including thumbnails and processed variants, or original uploads only? — owner: Engineering

---

## Acceptance Criteria

**AC-1 (Scenario 1): Event list**
- Given the admin is authenticated, when they navigate to the admin event list, then they see a paginated table of all events including draft, published, suspended, and soft-deleted events.
- Each row shows: event name, status, photo count, storage used, and last activity timestamp.
- The list can be filtered by status and sorted by last activity and photo count.
- A non-admin authenticated user receives HTTP 403 when accessing the event list endpoint.

**AC-2 (Scenario 2): Suspend / unsuspend**
- Given the admin views an event's detail page, then the page shows the event's photo count, storage used, last activity, and processing job summary before any action is taken.
- When the admin suspends a published event, then the event status changes to `suspended` and guests attempting to access the event receive an appropriate error response.
- When the admin unsuspends a suspended event, then the event status returns to `published` and guest access is restored.

**AC-3 (Scenario 3): Hard delete**
- Given the admin initiates a hard delete on any event, then a confirmation step is presented before the delete executes.
- When the admin confirms, then all photo files are removed from disk, all Qdrant vectors for the event's `event_id` are deleted, and all PostgreSQL records (event, photos, face records, analytics events) are removed.
- After deletion, any attempt to access the event by its ID returns HTTP 404.
- A partial failure (e.g. Qdrant delete fails) is logged and does not silently succeed — the operation is flagged for remediation.

**AC-4 (Scenario 4): Processing monitor**
- Given the admin views an event's detail page, then a processing monitor section shows counts for pending, in-progress, failed, and completed face processing jobs for that event.
- Counts are accurate to the current state of the PostgreSQL job tracking records at page load time.

**AC-5 (Scenario 5): Automated failure alert**
- Given face processing jobs are completing for an event, when the failure rate (failed / (failed + completed)) exceeds 10% in any rolling 1-hour window, then an email is sent to the platform administrator's registered email address within 10 minutes of the threshold being crossed.
- The alert email identifies the affected event by name and ID.
- If the condition persists, a second alert email for the same event is not sent until at least 1 hour after the previous alert for that event.
- The failure rate check runs on a schedule no less frequent than every 5 minutes.

**AC-6 (Scenario 6): Event owner analytics**
- Given an event owner is authenticated and views their event's analytics page, then they see: total views, total downloads, and total face searches for their event.
- An authenticated event owner cannot access analytics for an event they do not own — the backend returns HTTP 403.
- Analytics records do not contain guest identity or session information.

**AC-7 (Scenario 7): Platform health dashboard**
- Given the admin is authenticated and navigates to the platform health dashboard, then the page displays: total event count (all statuses), total photo count, total storage used in GB, and the platform-wide face processing error rate for the past 24 hours.
- All metrics reflect the state at page load time; no automatic refresh is required.
- A non-admin user cannot access the health dashboard endpoint — the backend returns HTTP 403.
