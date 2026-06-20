## Epic
docs/epics/album-gallery/EPIC.md

## Purpose
Give wedding guests a fast, filterable photo gallery experience with ceremony-based album filters and multiple sorting options so they can browse the full set of photos without being overwhelmed.

## Scenarios in scope
1. Guest opens the gallery — sees the first 50 photos loaded via "Load more" pagination, default sort = Latest, filter = All
2. Guest filters by a ceremony album (e.g. Sangeet) — grid reloads showing only photos in that category
3. Guest switches sort order (Latest / Popular / Photographer Choice) — grid reloads with new order
4. Guest opens a photo in the full-size lightbox — sees original-resolution image, can navigate prev/next within current filter/sort context
5. Guest shares or refreshes the page — URL reflects current filter, sort, and total loaded count, and the page loads to the same state
6. Photographer marks a photo as "Photographer Choice" from the photographer dashboard
7. Gallery renders without errors for an event with 50,000+ photos (pagination handles load)

## User stories / use cases
- As a guest, I want to open the gallery and immediately see a grid of the most recent photos, so that I can start browsing without any configuration.
- As a guest, I want to filter the gallery by ceremony album (e.g. Sangeet, Haldi), so that I can quickly find photos from a specific part of the day.
- As a guest, I want to sort photos by Latest, Popular, or Photographer Choice, so that I can surface the most relevant photos for my needs.
- As a guest, I want to open a photo in a full-size lightbox and navigate to adjacent photos, so that I can view images at full quality without leaving the gallery.
- As a guest, I want the URL to encode my current filter, sort, and loaded count, so that I can share or bookmark a specific gallery view and return to the same state after a refresh.
- As a photographer, I want to flag a photo as "Photographer Choice" from my dashboard, so that guests can sort the gallery to surface my curated selections.
- As a guest attending a large wedding, I want the gallery to load quickly even when the event has 50,000+ photos, so that I am not blocked by slow or failed page loads.

## Functional requirements

### Scenario 1 — Default gallery view
1. REQ-1 (Scenario 1): On load, the gallery must display the first 50 photos for the event, sorted by Latest (most recently uploaded first) with the filter set to All.
2. REQ-2 (Scenario 1): Photos are displayed in a responsive grid; thumbnail images are lazy-loaded — original-resolution files are not fetched on grid render.
3. REQ-3 (Scenario 1): The gallery uses a "Load more" UX pattern — the backend serves 50 photos per request; the frontend appends results to the existing grid when the guest clicks "Load more". The backend must return a total count so the frontend can determine when all photos have been loaded and hide the "Load more" button.
4. REQ-4 (Scenario 1): Each album category filter tab must display a badge showing the total count of photos in that album for the current event, regardless of the active sort selection.

### Scenario 2 — Album filter
5. REQ-5 (Scenario 2): The filter bar must offer one tab per album category present in the event, drawn from the fixed global list: All, Ceremony, Sangeet, Mehendi, Haldi, Reception, Family Photos. Tabs for categories with zero photos in the event must not be shown.
6. REQ-6 (Scenario 2): Selecting an album filter tab resets the grid — all previously loaded photos are cleared and the first 50 photos for the selected album are fetched fresh.
7. REQ-7 (Scenario 2): Photos not assigned to any album appear in the "All" tab only — they do not appear under any specific category tab.
8. REQ-8 (Scenario 2): The "All" tab is always shown and is the default selection.

### Scenario 3 — Sort order
9. REQ-9 (Scenario 3): The gallery must offer three sort options: Latest (upload timestamp descending), Popular (download count descending), and Photographer Choice (flagged photos first, then remaining photos in Latest order).
10. REQ-10 (Scenario 3): Changing the sort selection resets the grid — all previously loaded photos are cleared and the first 50 photos in the new order are fetched fresh.
11. REQ-11 (Scenario 3): Sort and filter are independent — both are applied simultaneously on every fetch (e.g. filter = Sangeet, sort = Popular).

### Scenario 4 — Lightbox
12. REQ-12 (Scenario 4): Clicking any thumbnail opens a lightbox overlay displaying the original-resolution image for that photo.
13. REQ-13 (Scenario 4): The lightbox must provide Previous and Next controls that navigate through photos in the same order and filter context as the current grid view.
14. REQ-14 (Scenario 4): The lightbox must provide a download action that triggers download of the original-resolution file for that photo and increments that photo's download count.
15. REQ-15 (Scenario 4): Closing the lightbox returns the guest to the grid at the same scroll position they were on before opening.

### Scenario 5 — URL state persistence
16. REQ-16 (Scenario 5): The active album filter, sort order, and total number of loaded photos must be encoded in URL query parameters (e.g. `?album=Sangeet&sort=popular&limit=150`) and kept in sync as the guest navigates.
17. REQ-17 (Scenario 5): On page load, the gallery must read filter, sort, and limit from the URL query parameters and apply them before the first data fetch; if parameters are absent or invalid, defaults (All, Latest, 50) are used.
18. REQ-18 (Scenario 5): When restoring from a URL with a `limit` greater than 50, the frontend must fetch enough batches to restore the full loaded count before rendering the grid (e.g. `limit=150` fetches 3 batches of 50).

### Scenario 6 — Photographer Choice flag
19. REQ-19 (Scenario 6): The "Photographer Choice" flag is stored as a boolean field on the `photos` table in PostgreSQL; it is set and cleared exclusively from the photographer dashboard.
20. REQ-20 (Scenario 6): A guest-scoped session must receive a 403 if it calls any endpoint to set or clear the Photographer Choice flag.
21. REQ-21 (Scenario 6): The backend must include the Photographer Choice flag value in the photo list response so the frontend can display an indicator on flagged thumbnails in the grid.

### Scenario 7 — Large event performance
22. REQ-22 (Scenario 7): Gallery list endpoints must use server-side pagination; the backend must never return all photos for an event in a single response.
23. REQ-23 (Scenario 7): The backend gallery list query must be backed by appropriate database indexes (event_id, album category, upload timestamp, download count) to ensure response time does not degrade linearly with event size.
24. REQ-24 (Scenario 7): The frontend must not attempt to load or cache all photos for an event client-side — only the current batch of thumbnails is fetched per "Load more" action.

## Non-functional requirements
- NFR-1: The gallery list API response (50-photo batch) must be served in under 500 ms at p95 for an event with 50,000 photos on the target VM hardware.
- NFR-2: Thumbnail images must be lazy-loaded; no thumbnail outside the viewport should be fetched on initial render.
- NFR-3: Lightbox original-resolution image must begin loading only on lightbox open — not on grid render.
- NFR-4: Gallery state (filter, sort, loaded count) must be fully encodable in the URL so any URL is shareable and produces the same view for any guest session.
- NFR-5: The gallery must be functional for anonymous guest sessions (no login required); all gallery endpoints must accept the guest session token issued at event entry.

## Context
- Guest sessions are anonymous and token-based; no user account is required to view the gallery.
- Album categories are a fixed global list (not configurable per event): Ceremony, Sangeet, Mehendi, Haldi, Reception, Family Photos. Custom per-event categories are out of scope for MVP.
- The "Photographer Choice" flag is set exclusively from the photographer dashboard (see `docs/features/photographer-dashboard/requirements.md`, REQ-18 through REQ-20).
- "Photographer Choice" sort order: flagged photos appear first, followed by remaining photos ordered by Latest (upload timestamp descending).
- Photos with no album assignment appear in the "All" tab only — there is no "Uncategorised" tab.
- Album tab count badges reflect total photos in that album and are unaffected by the active sort selection.
- Download count (used for Popular sort) is incremented by the backend on each photo download; the gallery list API must reflect current counts.
- The backend owns all data stores; the frontend fetches photos exclusively via the REST API — it does not query PostgreSQL or SSD directly (architecture constraint).
- Searches scoped per `event_id` — no cross-event photo leakage (architecture constraint).
- Thumbnail generation strategy (size, format, storage location) is a design-time decision not yet made; this requirements document assumes thumbnails exist and are served via the backend.

## Out of scope
- Guest uploading photos (gallery is read-only for guests)
- Face-search results filtering (covered by Face Recognition Search epic)
- My Favourites view (covered by Photo Actions epic)
- Guest ability to add comments or reactions to photos
- Custom album categories per event (fixed global list only in MVP)
- ZIP download of multiple photos from the gallery grid (covered by Photo Actions epic)
- Offline or cached gallery access
- Traditional numbered page controls (Load more pattern only)

## Open questions
- [ ] OQ-1 (design): What is the batch size for "Load more" — fixed at 50 or configurable? — owner: Engineering
- [ ] OQ-2 (design): How does the lightbox handle navigating to a photo beyond the currently loaded batch — does it fetch the next batch on demand? — owner: Engineering
- [ ] OQ-3 (design): Thumbnail generation strategy — size, format (WebP/JPEG), and storage location. — owner: Engineering

## Acceptance criteria
- AC-1 (Scenario 1): A guest opens the gallery for an event with 120 photos; the grid displays exactly 50 thumbnails sorted by Latest, with the "All" tab selected and a "Load more" button visible.
- AC-1b (Scenario 1): Each album tab that has at least one photo displays a numeric badge matching the total count of photos in that album, regardless of the active sort.
- AC-1c (Scenario 1): No original-resolution image requests are made to the backend during initial grid render; only thumbnail-sized images are fetched.
- AC-2 (Scenario 2): A guest selects the "Sangeet" filter tab; the grid resets and reloads showing only photos assigned to the Sangeet album category, and album tabs with zero photos for the event are not shown.
- AC-2b (Scenario 2): A photo with no album assignment is visible in the "All" tab but does not appear when any specific category tab is selected.
- AC-3 (Scenario 3): A guest selects the "Popular" sort; the grid resets and reloads with photos ordered by download count descending; the first photo shown has a download count greater than or equal to all subsequent photos in the batch.
- AC-3b (Scenario 3): Sort and filter are applied simultaneously: selecting filter = Haldi and sort = Popular returns only Haldi photos, ordered by download count descending.
- AC-3c (Scenario 3): A guest selects "Photographer Choice" sort; flagged photos appear first in the grid, followed by unflagged photos in Latest order.
- AC-4 (Scenario 4): A guest clicks a thumbnail; the lightbox opens showing the original-resolution image. The guest clicks Next; the next photo in the current sort/filter order is displayed.
- AC-4b (Scenario 4): A guest clicks Download in the lightbox; the original-resolution file is downloaded and that photo's download count is incremented by 1 in the database.
- AC-4c (Scenario 4): Closing the lightbox returns the guest to the same scroll position they were on before opening.
- AC-5 (Scenario 5): A guest loads 150 photos (3 batches) of the Sangeet filter sorted by Popular, then refreshes; the URL is `?album=Sangeet&sort=popular&limit=150` and the page restores with all 150 photos loaded.
- AC-5b (Scenario 5): A guest copies the URL from their browser and pastes it in a new tab; the new tab loads the identical filter, sort, and loaded-count state.
- AC-6 (Scenario 6): A photographer toggles the Photographer Choice flag on a photo from the dashboard; a guest subsequently selecting "Photographer Choice" sort sees that photo surfaced first in the grid.
- AC-6b (Scenario 6): A guest-scoped session calling the flag-set endpoint receives a 403 response and the flag state is unchanged.
- AC-7 (Scenario 7): The gallery list API returns a batch of 50 photos in under 500 ms at p95 for a test event containing 50,000 photos, verified under load on the target VM.
- AC-7b (Scenario 7): A guest loading multiple batches for a 50,000-photo event does not produce a timeout or error response.

## Status
Groomed — ready for /design
