# Album & Gallery Browsing

**Status:** Draft
**Owner:** Product Team
**Last Updated:** 2026-06-19

## Summary
Give wedding guests a fast, filterable photo gallery experience with ceremony-based album filters and multiple sorting options so they can browse the full set of photos without being overwhelmed.

## Requirements
1. Gallery displays photo thumbnails in a responsive grid; thumbnails load in under 1 second.
2. Guests can filter by ceremony album: Ceremony, Sangeet, Mehendi, Haldi, Reception, Family Photos.
3. Guests can sort the gallery by: Latest, Popular, Photographer Choice.
4. Clicking a thumbnail opens a full-size lightbox view with navigation to next/previous photos.
5. The gallery must support events with 50,000+ photos without performance degradation (pagination / virtual scroll required).
6. Photo count per album is shown on the filter UI.
7. Gallery state (active filter + sort) is preserved in URL params for shareability.

## User Stories
- As a guest, I want to filter photos by ceremony (e.g. Sangeet), so that I can quickly find photos from the specific part of the wedding I attended.
- As a guest, I want to sort photos by Latest or Popular, so that I can discover the best shots easily.
- As a photographer, I want to mark certain photos as "Photographer Choice", so that they surface prominently for guests.
- As a guest, I want to open a photo in full size without leaving the page, so that I can view details without losing my place in the gallery.
- As a guest, I want the gallery to load quickly even for an event with thousands of photos, so that browsing feels snappy.

## Features
| Feature | Status |
|---------|--------|
| Responsive thumbnail grid with infinite scroll / pagination | Backlog |
| Album filter tabs (Ceremony, Sangeet, Mehendi, Haldi, Reception, Family) | Backlog |
| Sort controls (Latest, Popular, Photographer Choice) | Backlog |
| Full-size lightbox with prev/next navigation | Backlog |
| Album photo count indicators | Backlog |
| URL-persisted filter and sort state | Backlog |
| Photographer Choice flag on photos | Backlog |

## Success Metrics
- Thumbnail grid initial load under 1 second for 100-photo page.
- Gallery renders without layout shifts on filter change.
- 50,000-photo events browsable with no timeout or crash.

## Decisions
<!-- Decisions made during this epic's lifetime -->

## Open Questions
- [ ] Should album categories be configurable per event or fixed globally? — owner: Product Team
- [ ] What is the page size for pagination (e.g. 50 or 100 photos)? — owner: Engineering
- [ ] Is "Popular" sort based on download count, favorites, or a combined score? — owner: Product Team
