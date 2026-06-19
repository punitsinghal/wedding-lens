# Face Recognition Search

**Status:** Draft
**Owner:** Product Team
**Last Updated:** 2026-06-19

## Summary
Let wedding guests upload a selfie on the wedding portal and instantly see all photos from the event in which they appear, eliminating the need to manually browse thousands of images.

## Requirements
1. Guest uploads a selfie image (JPEG/PNG) on the wedding event page.
2. System extracts the face from the selfie and generates an embedding.
3. System performs a vector similarity search against all face embeddings for that event.
4. Top matching photos are returned and displayed with match confidence score, thumbnail, download option, and share option.
5. The entire selfie-to-results flow must complete in under 5 seconds.
6. Uploaded selfies must be auto-deleted after the search completes (privacy requirement).
7. Results must be scoped strictly to the event the guest is accessing.
8. Guests must be able to re-run the search at any time during the event period.

## User Stories
- As a guest, I want to upload a selfie on the wedding website, so that I can instantly see all photos where I appear without browsing the full gallery.
- As a guest, I want to see a match confidence score with each result, so that I can judge which matches are most likely correct.
- As a guest, I want to download or share any matched photo directly from the results page, so that I can save or send my favourite shots immediately.
- As a guest, I want my uploaded selfie deleted after the search, so that I don't need to worry about my biometric data being retained.
- As a system, I want search results scoped to the specific event, so that a guest searching at one wedding cannot see photos from another event.

## Features
| Feature | Status |
|---------|--------|
| Selfie upload UI (drag-drop / camera capture) | Backlog |
| Selfie face extraction and embedding (client-side validation) | Backlog |
| Vector similarity search against event's Qdrant collection | Backlog |
| Results page: thumbnails with match confidence, download, share | Backlog |
| Auto-delete selfie after search completes | Backlog |
| Search result caching (same selfie hash → cached results) | Backlog |
| No-face-detected error handling with helpful UX message | Backlog |

## Success Metrics
- Selfie-to-results latency under 5 seconds at p95.
- Zero selfie images retained after search completion.
- Guest satisfaction: >80% of guests find at least one photo of themselves.
- False positive rate under 5% (wrong person returned in top-10 results).

## Decisions
<!-- Decisions made during this epic's lifetime -->

## Open Questions
- [ ] What similarity threshold determines a "match" vs a rejection? — owner: Engineering
- [ ] Should results page show all matches or cap at top N (e.g. top 50)? — owner: Product Team
- [ ] How is search handled if no face is detected in the uploaded selfie? — owner: Product Team
