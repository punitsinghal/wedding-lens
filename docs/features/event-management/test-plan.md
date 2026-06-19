## Summary

This test plan covers the event-management feature: creating, editing, deleting, and publishing wedding events; slug assignment and uniqueness; album management; QR code generation; and admin event controls. The feature is the entry point for the entire platform — every other flow (guest access, photo upload, face search) depends on a correctly created, scoped, and published event. Test coverage here directly gates platform correctness and data isolation guarantees.

---

## Scope

**In scope:**
- Event CRUD (create, read, update, delete) via the owner-authenticated API
- Slug auto-generation, validation, uniqueness, and redirect on change
- Album management (create, rename, delete, photo reassignment, 10-album cap)
- QR code generation and regeneration on slug change
- Publish / unpublish controls and precondition enforcement
- Admin event list, suspend, unsuspend, and hard delete
- 30-day soft-delete grace period and purge cascade (Qdrant + disk + PostgreSQL)
- Auth enforcement (401 on unauthenticated requests)
- Slug uniqueness race condition (database-level enforcement)

**Out of scope:**
- Guest access flows (QR scan landing, OTP, access-code entry) — covered by Guest Access feature
- Photo upload and face processing — covered by Photographer Dashboard and AI Face Processing features
- Event owner account creation and login — assumed prerequisite
- Admin analytics and pipeline monitoring — covered by Admin Platform feature
- Mobile QR scan testing beyond manual verification

---

## Assumptions (pending your answers)

The following defaults are used in this draft; update after clarification:

| # | Assumption | TC affected |
|---|------------|-------------|
| A1 | AC-7 "no full page reload" = DOM updates with new name within 1000ms of save response, no browser navigation event fires | TC-07 |
| A2 | "Active guest session" (REQ-13) = a non-expired JWT issued before the access mode change | TC-16 |
| A3 | The 30-day purge job is triggerable via a dedicated API endpoint (admin-only); TC-36 calls this endpoint directly rather than mocking the clock | TC-36 |
| A4 | AC-15 QR scan test is manual only | TC-19 |
| A5 | NFR-1 "under 2 minutes" is a manual UX checklist item, not an automated latency assertion | M-06 |

---

## Test cases

### Happy path

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-01 | Create event — all required fields, access-code mode | POST `/api/v1/events` with name, bride, groom, date, `access_mode=access-code`, access code, as authenticated owner | 201; response contains event ID, unpublished status, auto-assigned slug, QR code URL | Yes |
| TC-02 | Create event — public access mode (no access code) | POST `/api/v1/events` with `access_mode=public`; no access code field | 201; event created successfully | Yes |
| TC-03 | Slug auto-generated from bride + groom names | POST with `bride_name=Priya`, `groom_name=Rahul`; no slug override | Response slug equals `priya-rahul` (or documented derivation rule) | Yes |
| TC-04 | Owner overrides default slug at creation | POST with explicit `slug=our-big-day` | Event created with slug `our-big-day`, not the auto-generated default | Yes |
| TC-05 | New event starts unpublished | POST to create event | `status=draft`; GET `/<slug>` returns guest-inaccessible (404 or 403 depending on design) | Yes |
| TC-06 | Edit event name | PATCH event with new name | 200; GET event returns updated name | Yes |
| TC-07 | Edit event name — DOM updates within 1000ms, no page reload (A1) | Via UI: save event name change; measure time from save response to DOM update | DOM updates with new name within 1000ms; no browser navigation event fires; URL unchanged | No (manual) |
| TC-08 | Change slug — old slug 301 redirects | PATCH event with new slug; GET `/<old-slug>` | 301 to `/<new-slug>` | Yes |
| TC-09 | Change slug — QR code regenerates | PATCH event slug; GET QR code | QR code PNG encodes new gallery URL | Yes |
| TC-10 | Delete event — returns 404 immediately | Owner confirms deletion; GET `/<slug>` | 404; event data still present in database (verifiable via admin endpoint) | Yes |
| TC-11 | Delete event — data recoverable within 30 days | Delete event; query admin endpoint for soft-deleted event | Event record exists with deleted-at timestamp; photos accessible via admin | Yes |
| TC-12 | Create album with category tag | POST `/api/v1/events/{id}/albums` with name="Pre-Wedding", tag=`Mehendi` | 201; album appears in event's album list with tag | Yes |
| TC-13 | Delete album — photos move to uncategorized | Assign photos to album; delete album | 200; photos remain in event, album_id set to null / uncategorized | Yes |
| TC-14 | Admin views paginated event list | GET `/api/v1/admin/events?page=1&per_page=20` | 200; response contains event name, owner, date, status, photo count; pagination metadata present | Yes |
| TC-15 | Admin suspends event — guests blocked | Admin POST suspend on event; GET `/<slug>` as guest | 200 admin response; guest request returns informative unavailable (not 404) | Yes |
| TC-16 | Admin unsuspends event — access restored immediately | Admin POST unsuspend; GET `/<slug>` as guest | Event accessible again; response time < 1s from unsuspend call | Yes |
| TC-17 | Publish event — guests can access | Set slug, access mode, cover photo; owner POSTs publish | 200; GET `/<slug>` as guest returns event page | Yes |
| TC-18 | Unpublish published event — guests blocked | Owner POSTs unpublish | GET `/<slug>` as guest returns informative unavailable message | Yes |
| TC-19 | QR code encodes correct URL and is downloadable | GET QR code endpoint after event creation | PNG returned; decoded QR content equals `<host>/<slug>` | Yes |
| TC-19b | QR code scans on mobile camera | Download QR PNG; scan with iOS and Android cameras | Opens correct event URL in browser | No (manual) |
| TC-20 | Access mode change — active guest sessions unaffected (A2) | Issue guest JWT under `access-code` mode; change event to `public`; use existing JWT | Existing JWT still accepted; new guests follow `public` flow | Yes |

---

### Edge cases

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-21 | Duplicate slug rejected — alternatives suggested | POST with slug that already exists on platform | 409; response body contains ≥2 alternative slug suggestions | Yes |
| TC-22 | Slug uniqueness under race condition (NFR-2) | Two concurrent POST requests with identical slug | Exactly one succeeds (201), one fails (409); no duplicate slugs in database | Yes |
| TC-23 | Invalid slug format — uppercase | POST with `slug=Priya-Rahul` | 422; validation error naming slug format rule | Yes |
| TC-24 | Invalid slug format — spaces | POST with `slug=priya rahul` | 422; validation error | Yes |
| TC-25 | Invalid slug format — special characters | POST with `slug=priya&rahul!` | 422; validation error | Yes |
| TC-26 | Invalid slug format — leading/trailing hyphen | POST with `slug=-priya-rahul-` | 422; validation error | Yes |
| TC-27 | Slug exceeds 50 characters | POST with 51-character slug | 422; validation error referencing 50-char limit | Yes |
| TC-28 | 10-album cap enforced | Create 10 albums; attempt to create 11th | 422; error message states maximum albums reached | Yes |
| TC-29 | Publish rejected — missing cover photo | Event has slug and access mode but no cover photo; owner POSTs publish | 422; error lists `cover_photo` as missing required field | Yes |
| TC-30 | Publish rejected — missing slug | Event has cover photo and access mode but no slug; owner POSTs publish | 422; error lists `slug` as missing | Yes |
| TC-31 | Publish rejected — missing access mode | Event has slug and cover photo but no access mode; owner POSTs publish | 422; error lists `access_mode` as missing | Yes |
| TC-32 | access-code mode requires access code at creation | POST with `access_mode=access-code` and no `access_code` field | 422; error states access code is required for this mode | Yes |
| TC-33 | Album rename | PATCH album with new name | 200; album name updated; photos and tag unaffected | Yes |
| TC-34 | Admin hard delete — immediate cascade, no grace period | Admin DELETE event | Event, photos, Qdrant embeddings (by event_id), and database records purged immediately | Yes |
| TC-35 | Admin paginates large event list (NFR-4) | GET admin event list with 1000 events in DB; `per_page=20` | Response returns 20 items; server memory footprint does not load all 1000 | Yes |
| TC-36 | 30-day purge cascade — complete and consistent (NFR-3, A3) | Delete event; POST `/api/v1/admin/jobs/purge-deleted-events`; verify all three stores | PostgreSQL records gone; Qdrant vectors for `event_id` gone; disk files at `STORAGE_PATH/<event_id>` gone; no partial state | Yes |

---

### Failure / error paths

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-40 | Unauthenticated create → 401 (AC-2) | POST `/api/v1/events` with no `Authorization` header | 401 | Yes |
| TC-41 | Unauthenticated edit → 401 | PATCH event with no auth | 401 | Yes |
| TC-42 | Unauthenticated delete → 401 | DELETE event with no auth | 401 | Yes |
| TC-43 | Wrong owner cannot edit another owner's event | Authenticated as owner-B; PATCH event belonging to owner-A | 403 | Yes |
| TC-44 | Wrong owner cannot delete another owner's event | Authenticated as owner-B; DELETE event belonging to owner-A | 403 | Yes |
| TC-45 | Missing required fields at creation | POST with event name omitted | 422; error identifies missing field | Yes |
| TC-46 | Delete without confirmation step | DELETE request that bypasses the confirm flag | 400 or 422; deletion not executed | Yes |
| TC-47 | Soft-deleted event inaccessible to guests | Delete event; GET `/<slug>` as guest | 404 | Yes |
| TC-48 | Soft-deleted event still in admin list | Delete event; GET admin event list with `include_deleted=true` | Event appears with `deleted_at` timestamp | Yes |
| TC-49 | GET non-existent event | GET `/api/v1/events/00000000-fake-id` | 404 | Yes |
| TC-50 | Suspended event — guest sees informative message, not 404 | Suspend event; GET `/<slug>` | Response is 200 or 403 with a message body (not a bare 404) | Yes |

---

## Acceptance criteria coverage

| Criterion | TC IDs | Status |
|-----------|--------|--------|
| AC-1: Event created unpublished with slug and QR | TC-01, TC-05, TC-19 | Covered |
| AC-2: Unauthenticated create → 401 | TC-40 | Covered |
| AC-3: Slug auto-generated from bride/groom names | TC-03 | Covered |
| AC-4: Duplicate slug rejected, ≥2 alternatives suggested | TC-21 | Covered |
| AC-5: Invalid slug format (uppercase, spaces, special chars) rejected | TC-23, TC-24, TC-25 | Covered |
| AC-6: Slug > 50 chars rejected | TC-27 | Covered |
| AC-7: Event name update visible without full page reload | TC-07 | Covered (manual — pending A1 clarification) |
| AC-8: Old slug 301 redirects to new slug | TC-08 | Covered |
| AC-9: Active guest sessions survive access mode change | TC-20 | Covered (pending A2 clarification) |
| AC-10: Post-deletion event returns 404; data retained | TC-10, TC-47 | Covered |
| AC-11: 30-day purge removes all data | TC-36 | Covered (pending A3 clarification) |
| AC-12: Album with category tag appears in guest filter | TC-12 | Partially covered — guest-facing filter rendering is out of scope here; API side covered |
| AC-13: Delete album → photos go uncategorized | TC-13 | Covered |
| AC-14: 11th album rejected | TC-28 | Covered |
| AC-15: QR code encodes correct URL and scans on mobile | TC-19, TC-19b | Covered (TC-19b manual) |
| AC-16: QR regenerates on slug change | TC-09 | Covered |
| AC-17: Admin suspends event → guests see unavailable message | TC-15 | Covered |
| AC-18: Admin unsuspends → guests can access immediately | TC-16 | Covered |
| AC-19: Publish rejected when cover photo missing | TC-29 | Covered |
| AC-20: Published event accessible to guests via slug and QR | TC-17 | Covered |
| AC-21: Unpublished event returns informative unavailable message | TC-18 | Covered |

**AC-12 note:** The criterion includes "appears in the guest-facing Mehendi filter" — the API-side album creation is covered by TC-12, but rendering of the guest filter UI is in scope for the Guest Access feature test plan, not here.

---

## Manual test checklist

- [ ] **M-01 (AC-7):** Edit event name in the photographer dashboard — confirm the new name renders in the UI without a visible page reload or URL change.
- [ ] **M-02 (AC-8):** Change event slug in dashboard; paste the old slug URL into a browser — confirm 301 redirect arrives at the new slug page.
- [ ] **M-03 (AC-15 / TC-19b):** Download QR code PNG; scan with iOS Camera app and Android Camera app — confirm both open the correct event URL.
- [ ] **M-04 (AC-17):** As a guest, attempt to open a suspended event URL — confirm a human-readable "event unavailable" message appears (not a bare error or blank page).
- [ ] **M-05 (AC-21):** As a guest, attempt to open an unpublished event URL — confirm a human-readable "event unavailable" message appears.
- [ ] **M-06 (NFR-1):** Time the full event creation workflow (form fill → save → QR download) — confirm it completes within 2 minutes on a normal connection.
- [ ] **M-07 (REQ-16):** Trigger event deletion in the UI — confirm an explicit confirmation dialog appears before deletion is executed.

---

## Known risks

1. **30-day purge atomicity (NFR-3):** The purge job touches three stores (PostgreSQL, Qdrant, disk). A crash mid-job could leave partial state. Risk: difficult to test automatically without a fault-injection harness; needs a compensating reconciliation query to detect orphaned Qdrant vectors.

2. **Slug redirect at scale:** 301 redirects are served by the backend. If the event has been permanently purged, the old slug redirect record must also be purged — otherwise the redirect points to a dead event. This case is not currently captured in the requirements.

3. **Race condition on slug uniqueness (TC-22):** NFR-2 mandates database-level enforcement. If the backend doesn't use a `UNIQUE` constraint (relying only on an application-level check), concurrent POSTs will silently create duplicates. The test validates the constraint, but the risk is missed if test DB config differs from production.

4. **Qdrant scoping on admin hard delete (TC-34):** Purging Qdrant by `event_id` payload filter requires Qdrant to support payload-indexed deletion. If the collection schema changes, this silently fails. No API-level feedback is available to confirm the delete count.

5. **Guest session behaviour on access mode change (TC-20 / A2):** The requirement says existing sessions are not invalidated, but the definition of "active session" is unresolved. If JWT TTL is long (e.g. 7 days) and access mode changes to `access-code`, a guest with an old JWT could retain access indefinitely — which may or may not be the intended behaviour.

---

## Sign-off

- [x] All acceptance criteria covered
- [x] Edge cases documented
- [x] Manual checklist reviewed
- QA: Punit Singhal — 2026-06-19
