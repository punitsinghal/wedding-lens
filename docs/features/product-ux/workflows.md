# WeddingLens — UI Workflow Atlas

## Purpose

A complete map of every user-facing workflow in the current WeddingLens frontend, one diagram per workflow, meant as a design-review handoff — not an audit. Where `docs/features/product-ux/ux.md` narrates friction, this document exists so a designer with no prior context on the codebase can see every screen, every state a screen can be in, and every transition between them, and propose interface improvements against the real shipped structure rather than a description of it.

Three personas use this product:

- **Guest** — no account, arrives via QR code or a shared link, on a phone, wants their own photos fast.
- **Photographer / event owner** — uploads and organizes thousands of photos per event, controls publish and access, hands the couple a QR code.
- **Platform admin** — monitors processing health across all events, handles suspensions and face-data removal requests.

Each workflow below is numbered `G` (guest), `P` (photographer/owner), or `A` (admin) and cites the source file(s) so implementation detail is one click away.

---

## Guest workflows

### G1 — Entry & access gate

Source: `app/g/[slug]/page.tsx`

Every guest journey starts here, regardless of access mode. A `public` event skips the form entirely; `access-code` and `magic-link-otp` events show one input. A guest who already holds a valid session token for this event is bounced straight through.

```mermaid
flowchart LR
    QR["Scan QR code /\nopen shared link"] --> Entry["/g/[slug]\nEntry page"]
    Entry --> Check{Event status?}
    Check -->|not found| NotFound["Event not found"]
    Check -->|found, unpublished| Unavailable["'This event is\ncurrently unavailable'"]
    Check -->|published, public| Bypass["Skip form —\nissue guest token silently"]
    Check -->|published, access-code\nor magic-link-otp| HasSession{Valid session\nalready stored?}
    HasSession -->|yes| Gallery
    HasSession -->|no| CodeForm["Enter access code / OTP"]
    CodeForm -->|valid| Gallery["Gallery"]
    CodeForm -->|invalid| InvalidMsg["'Invalid code.\nPlease check and try again.'"] --> CodeForm
    CodeForm -->|rate-limited| LockoutMsg["'Too many attempts.\nTry again in 15 minutes.'"] --> CodeForm
    CodeForm -->|access revoked| RevokedMsg["'Guest access has been\ndisabled. Contact photographer.'"] --> CodeForm
    Bypass --> Gallery
```

**Design-relevant detail:** the three failure states (`invalid`, `rate-limited`, `revoked`) all render inside the same single-line error slot under the code input — a designer should decide whether these deserve visually distinct treatment (severity, icon, color) rather than three sentences competing for one line.

---

### G2 — Browse gallery, filter, and act on a photo

Source: `app/g/[slug]/gallery/page.tsx`, `components/gallery/*`, `components/photo-actions/*`

The gallery is the guest's home base — everything else (search, favourites, share) branches off it and returns to it.

```mermaid
flowchart TD
    Gallery["Gallery grid\n(header: event name, couple names)"] --> Filter["Album tabs\n(Ceremony / Sangeet / Mehendi / ...)"]
    Gallery --> Sort["Sort selector\n(Latest / Popular / Photographer's Choice)"]
    Filter --> Grid["Photo grid re-fetches"]
    Sort --> Grid
    Grid --> LoadMore["'Load more' button\n(paginated, 50/page)"]
    Grid -->|tap thumbnail| Lightbox["Full-screen lightbox\n(keyboard + swipe nav)"]
    Lightbox -->|arrow past loaded set| LoadMore
    Grid -->|hover / tap heart| Favourite["Toggle favourite"]
    Grid -->|hover / tap share icon| ShareLink["Copy 72h share link"]
    Lightbox --> Favourite
    Lightbox --> ShareLink
    Lightbox --> Download["Download original"]
    Gallery -->|header CTA| Search["Find my photos →"]
    Gallery -->|header link| Favourites["Favourites page →"]
    Gallery -->|header button| RemovalForm["Remove my face data →"]
```

**Design-relevant detail:** favourite/share icons are hover-revealed on desktop but always-visible on mobile (`opacity-100 sm:opacity-0 sm:group-hover:opacity-100`) — worth a deliberate touch-target pass rather than an accident of the breakpoint. Download failures are swallowed silently on every one of these paths (single photo in the lightbox, bulk ZIP from favourites/results) — there is currently no error state to design for here because none exists yet.

---

### G3 — Face search (selfie → results)

Source: `app/g/[slug]/search/page.tsx`, `components/search/*`

```mermaid
flowchart TD
    Entry["'Find my photos' tapped\nfrom gallery header"] --> Consent["Privacy notice\n(what we collect / why / retention)\nmust acknowledge once per page visit"]
    Consent -->|"I understand, continue"| Upload["Native camera / file picker\n(JPEG or PNG, max 20 MB)"]
    Upload -->|file too large, client-side| ErrTooLarge["'Photo is too large' inline error"] --> Upload
    Upload -->|submitted| Searching["Searching... spinner"]
    Searching -->|match found| Results["Results grid\n(favourite / share / download per photo)"]
    Searching -->|no face detected| ErrNoFace["'Couldn't detect a face'"] --> Upload
    Searching -->|multiple faces| ErrMultiFace["'Selfie shows multiple faces'"] --> Upload
    Searching -->|zero matches| EmptyResults["'No photos found' +\n'Try another photo'"] --> Upload
    Searching -->|rate-limited, 429| RateLimit["'Too many attempts.\nWait ~N seconds.'"] --> Upload
    Results -->|"Try another photo"| Upload
```

**Design-relevant detail:** the privacy-notice gate is local component state — it resets on every remount, so a guest who leaves for the gallery and comes back re-clicks through the same screen. There is no preview/crop step between picking a photo and firing the search; a bad selfie is only discovered after the full round trip lands on one of the four error states above.

---

### G4 — Favourites

Source: `app/g/[slug]/favourites/page.tsx`, `hooks/useFavourites.ts`

```mermaid
flowchart LR
    Gallery -->|"Favourites" link,\nbadge shows count| FavPage["Favourites page"]
    FavPage --> Check{Any favourites?}
    Check -->|none| Empty["Empty state:\n'Tap the heart on any photo...'\n+ 'Browse photos' CTA"] --> Gallery
    Check -->|has favourites| List["Grid + non-permanence notice\n('may disappear after inactivity')"]
    List --> BulkZip["Bulk download ZIP"]
    List -->|un-heart| Remove["Card disappears immediately"]
```

**Design-relevant detail:** favourites are stored server-side in-process with a 24-hour sliding TTL and do not survive a backend restart — the on-page notice is the only signal a guest gets that this list isn't durable. There is no distinct "your favourites expired" state; an expired list looks identical to a never-populated one (both render the same empty state).

---

### G5 — Shared photo link resolution

Source: `app/share/[token]/page.tsx`

A `/share/[token]` link is generated from the share icon and is meant to be opened by anyone the guest forwards it to (WhatsApp, etc.) — so this is the one guest surface that must handle "visitor with zero context."

```mermaid
stateDiagram-v2
    [*] --> Loading
    Loading --> Expired: token expired\n(>72h old)
    Loading --> Invalid: token malformed\nor photo deleted
    Loading --> NeedsAccess: valid token,\nno guest session for this event
    Loading --> Ready: valid token,\nguest session present
    NeedsAccess --> [*]: redirect to /g/[slug]\nwith ?next= back to this link
    Ready --> Ready: Download original
    Expired --> [*]: 'Go to home' link
    Invalid --> [*]: 'Go to home' link
```

**Design-relevant detail:** three of the four end states (`Expired`, `Invalid`, a `NeedsAccess` visitor with no event slug to redirect to) dead-end at a bare "Go to home" link with no way back to the actual photo — worth deciding whether any of these should instead explain *why* and point somewhere more useful than the marketing root.

---

### G6 — Remove my face data

Source: `app/g/[slug]/gallery/page.tsx` (modal), form fields only

```mermaid
flowchart LR
    Gallery -->|"Remove my face data"\nbutton in header| Modal["Modal:\nname, email, description\n(all required)"]
    Modal -->|submit, validation fails| Inline["Per-field inline errors"] --> Modal
    Modal -->|submit, server error| ServerErr["Server error message"] --> Modal
    Modal -->|submit succeeds| Success["'Request received' +\nprocessed within 24h"]
    Success -->|close| Gallery
    Modal -->|cancel| Gallery
```

This is the one privacy-compliance-facing flow a guest can trigger directly; it feeds **A3** below on the admin side.

---

## Photographer / event owner workflows

### P1 — Account access

Source: `app/(auth)/login/page.tsx`, `app/(auth)/register/page.tsx`, `components/AuthProvider.tsx`

```mermaid
flowchart LR
    Root["/ (root)"] -->|no token| Login
    Root -->|has token| Dashboard
    Login -->|success| Dashboard
    Login -->|invalid credentials| LoginErr["'Invalid email or password.'"] --> Login
    Login -->|"Register" link| Register
    Register -->|passwords mismatch\nor <8 chars| RegErr["Inline validation error"] --> Register
    Register -->|success| Dashboard
```

**Design-relevant detail:** there is no visible forgot-password path anywhere in this flow — confirm with product whether that's a real gap or simply out of scope for this pass.

---

### P2 — Dashboard

Source: `app/dashboard/page.tsx`, `components/EventCard.tsx`, `components/AssignedEventCard.tsx`

```mermaid
flowchart TD
    Dashboard["Dashboard"] --> Owned["My Events\n(owned, full control)"]
    Dashboard --> Assigned["Events I'm Photographing\n(assigned, view-only elsewhere)"]
    Owned -->|empty| EmptyOwned["'No events yet' +\n'Create your first event'"]
    Owned -->|"+ New Event"| CreateEvent
    Owned -->|card click| EventDetail
    Assigned -->|card click| EventDetail
```

Two independent lists load in parallel (`Promise.allSettled`) and fail independently — an owner with zero owned events but several assigned ones sees only the second section populate, which is correct today but easy to misread as a loading bug if the empty-owned state and the assigned list render at visually similar weight.

---

### P3 — Create event

Source: `app/events/new/page.tsx`, `components/SlugField.tsx`, `lib/slugUtils.ts`

```mermaid
flowchart TD
    Start["Dashboard →\n'+ New Event'"] --> Form["Name, bride/groom,\ndate, access mode, slug"]
    Form --> SlugAuto["Slug auto-generated from\nbride+groom names\n(editable — auto-gen stops once touched)"]
    Form -->|access mode = access-code| CodeField["Access code field\n(required)"]
    Form -->|submit| Validate{Valid?}
    Validate -->|slug taken| Suggestions["Suggested alternate slugs\nshown inline"] --> Form
    Validate -->|missing access code| CodeErr["'Access code is required'"] --> Form
    Validate -->|passes| Created["Event created →\nEvent Detail page"]
    Form -->|"Cancel"| Dashboard
```

---

### P4 — Event settings hub (tabbed)

Source: `app/events/[eventId]/page.tsx`

The single busiest surface in the product. It was split into four tabs in a recent refactor; an assigned (non-owner) photographer only ever sees the first two, all fields disabled.

```mermaid
flowchart TD
    Detail["Event Detail"] --> Tabs{Tab}
    Tabs --> Overview["Overview\nanalytics (views/downloads/searches)\n+ event identity form"]
    Tabs --> PublishTab["Publish & Access\ncover-photo picker, access mode,\npublish toggle, guest-access revoke"]
    Tabs -->|owner only| Photographers["Photographers\nassign/remove by email"]
    Tabs -->|owner only| Danger["Danger Zone\ndelete event (30-day grace)"]
    Detail --> QuickLinks["Quick links:\nManage Photos / Manage Albums / QR Code"]
```

Publish itself is gated by two independent client-side checks that both have to clear before the button is even clickable:

```mermaid
stateDiagram-v2
    [*] --> NoCover: cover_photo_id unset
    [*] --> HasCover: cover_photo_id set
    NoCover --> HasCover: pick a cover photo\n(grid in Publish & Access tab)
    HasCover --> NeedsConsent: consent checkbox unchecked
    HasCover --> Publishable: consent checked
    NeedsConsent --> Publishable: check consent box
    Publishable --> Published: click Publish
    Published --> Publishable: click Unpublish\n(consent resets — must re-check to republish)
```

**Design-relevant detail:** the two disabled-button hints ("set a cover photo" / "check the consent box") both surface as the same amber inline box and can show up simultaneously — worth deciding whether a designer wants a single combined checklist state instead of stacked hints.

---

### P5 — Photo upload & processing

Source: `app/events/[eventId]/photos/page.tsx`

The most operationally complex screen: chunked, resumable, deduplicated upload running concurrently with a live server-sent-events processing monitor.

```mermaid
flowchart TD
    Drop["Drag-and-drop or\nclick-to-browse"] --> Queue["Upload queue\n(per-file status dot)"]
    Queue --> Validate{Type + size ok?\n(JPEG/PNG, ≤25MB)}
    Validate -->|no| QueuedErr["Item shown as error,\nnever uploads"]
    Validate -->|yes| Hash["Hash file (dedup check)"]
    Hash --> Initiate["Initiate session"]
    Initiate -->|duplicate hash| Duplicate["Marked 'duplicate',\nskipped"]
    Initiate -->|new or resumable| Chunks["Upload chunks\n(3 files concurrently,\n3 retries per chunk)"]
    Chunks -->|all chunks fail| ChunkErr["Item errored,\nstays in queue for retry"]
    Chunks -->|complete| Done["Item marked done →\nphoto grid refreshes"]
    Done -.SSE progress stream.-> Panel["Processing Status panel:\npending / processing / indexed / failed counts"]
    Panel -->|gallery_ready event| ReadyBanner["'Gallery ready —\nguests can now search!' banner"]
    Panel -->|per-photo failure| RetryBtn["Retry button on\nthat photo's card"]
    RetryBtn --> Chunks
```

**Design-relevant detail:** album assignment and the "Photographer's Choice" star are both one-photo-at-a-time controls on each grid card — for an app whose own architecture doc says "thousands of wedding pictures," this is the single biggest scale mismatch between the UI's interaction model and its stated use case. If the SSE connection drops, the panel goes stale with a silent 60-second fixed-interval reconnect and no "reconnecting…" indicator — currently no distinct visual state exists for that condition.

---

### P6 — Album management

Source: `app/events/[eventId]/albums/page.tsx`, `app/events/[eventId]/albums/[albumId]/page.tsx`, `components/AlbumList.tsx`

```mermaid
flowchart TD
    List["Albums list\n(max 10 per event)"] -->|"+ New Album"| CreateForm["Name + ceremony category\n(optional)"]
    CreateForm --> List
    List -->|"Rename"| EditForm["Inline edit: name + category"] --> List
    List -->|toggle| Visibility["Public ⇄ Private"]
    List -->|"Photos"| AlbumDetail["Album detail:\nphoto grid, click to set cover"]
    List -->|"Delete"| DeleteConfirm["Single-click confirm dialog\n(photos become uncategorized,\nnot deleted)"] --> List
    AlbumDetail -->|click photo| SetCover["Set as album cover"] --> AlbumDetail
```

**Design-relevant detail:** deleting an event requires typing `DELETE` to confirm; deleting an album — which can silently un-categorize hundreds of photos — is a single click. A designer weighing confirmation-dialog weight across the product should treat this as the same tier as the event deletion, not a lighter one.

---

### P7 — QR code & guest link

Source: `app/events/[eventId]/qr/page.tsx`

```mermaid
flowchart LR
    Detail["Event Detail\nquick link"] --> QRPage["QR Code page"]
    QRPage --> Image["QR image\n(auth-fetched, blob-rendered)"]
    QRPage --> LinkRow["Guest link + Copy button"]
    QRPage --> DownloadPNG["Download PNG"]
    QRPage -->|slug changed elsewhere| AutoUpdate["QR auto-updates\n(encodes current slug)"]
```

This is the smallest, calmest screen in the owner journey — a single-purpose handoff artifact, worth keeping that way.

---

## Platform admin workflows

### A1 — Platform events oversight

Source: `app/admin/page.tsx`

```mermaid
flowchart TD
    Admin["/admin"] --> Health["Platform Health tiles\n(events / photos / storage / 24h error rate)"]
    Admin --> Table["All-events table\n(paginated, 20/page,\nno search or filter)"]
    Table -->|status = active| Suspend["Suspend"] --> Table
    Table -->|status = suspended| Unsuspend["Unsuspend"] --> Table
    Table -->|any non-deleted| Delete["Delete\n(typed-confirm dialog,\nhard delete, no grace period)"] --> Table
    Table -->|row click| EventDetailAdmin["Admin Event Detail →"]
    Admin --> RemovalQueue["Face-Data Removal Requests\n(see A3)"]
```

**Design-relevant detail:** admin delete is a hard, immediate, no-grace-period purge — visually it should read as more dangerous than the owner-side delete (which has a 30-day recovery window), not the same or lighter weight.

---

### A2 — Admin event detail (read-only)

Source: `app/admin/events/[eventId]/page.tsx`

```mermaid
flowchart LR
    Table["Admin events table"] -->|row click| Detail["Read-only detail:\nowner, photo count, storage,\nlast activity"]
    Detail --> Monitor["Processing Monitor:\npending / processing / complete /\nfailed / error counts"]
    Detail -->|back| Table
```

No actions live on this screen at all — suspend/unsuspend/delete only exist back on the list. Confirm with product whether that split is intentional (drill-down = diagnosis, list = action) or an oversight.

---

### A3 — Face-data removal fulfillment

Source: `app/admin/page.tsx` (Removal Requests section)

```mermaid
flowchart LR
    Guest["Guest submits request\n(see G6)"] --> Queue["Pending Removal Requests\ntable, badge count"]
    Queue -->|"Mark fulfilled"| Fulfilled["Request removed from list —\nno fulfilled-history view"]
```

**Design-relevant detail:** once marked fulfilled, a request simply disappears from the UI — there is no audit trail visible anywhere for compliance review. If that history exists only in the database, a designer should know this screen currently can't show it.

---

## Screen inventory

| Screen | Persona | Purpose | Reached from |
|---|---|---|---|
| `/g/[slug]` | Guest | Entry gate — code/OTP or straight through | QR code, shared link |
| `/g/[slug]/gallery` | Guest | Browse, filter, sort, lightbox | Entry page |
| `/g/[slug]/search` | Guest | Consent → selfie → results | Gallery header |
| `/g/[slug]/favourites` | Guest | Saved photos, bulk ZIP | Gallery header |
| `/share/[token]` | Guest | Single shared photo, 72h expiry | External share link |
| `/login`, `/register` | Owner | Auth | Nav, root redirect |
| `/dashboard` | Owner | Owned + assigned events | Nav, post-login |
| `/events/new` | Owner | Create event | Dashboard |
| `/events/[eventId]` | Owner | Settings hub — 4 tabs | Dashboard, breadcrumbs |
| `/events/[eventId]/photos` | Owner | Upload + processing status | Event detail |
| `/events/[eventId]/albums` | Owner | Create/rename/delete/visibility | Event detail |
| `/events/[eventId]/albums/[albumId]` | Owner | Pick album cover | Albums list |
| `/events/[eventId]/qr` | Owner | QR image, guest link, PNG | Event detail |
| `/admin` | Admin | Health, events table, removal queue | Nav (admin only) |
| `/admin/events/[eventId]` | Admin | Read-only drill-down | Admin table |
| `/privacy` | All | Platform privacy notice | Search consent link |

---

## Cross-cutting states worth designing deliberately

These recur across nearly every workflow above and are currently handled ad hoc, screen by screen:

| State | Where it shows up today | Note for design |
|---|---|---|
| Loading | Plain `"Loading..."` text, no skeleton, on most pages | Gallery and Photos pages do have skeleton grids; most other screens don't |
| Empty | Bespoke copy per screen (favourites, albums, photos, admin tables) | No shared empty-state component exists yet |
| Inline field/form error | Red text under the field, consistent styling | The one consistent pattern in the app — good baseline to extend |
| Silent failure | Photo/ZIP downloads only | The one place errors don't surface at all |
| Disabled + hint | Publish button (consent / cover), form fields for non-owners | Hint text appears as a title tooltip *and* an amber inline box — pick one |
| Confirm dialog | Two weights exist: typed `DELETE` vs. single-click confirm | Currently not mapped consistently to the actual risk of the action |
