# Photo Source Integration

**Status:** Draft
**Owner:** Product Team
**Last Updated:** 2026-06-19

## Summary
Allow photographers and admins to connect multiple photo sources (Google Drive, Google Photos, web servers) to an event so that photos are automatically imported, thumbnailed, and indexed without manual uploads.

## Requirements
1. Support Google Drive as a photo source: admin provides folder ID and OAuth credentials; system reads images, syncs metadata, downloads thumbnails, and processes faces.
2. Support Google Photos as a source: admin connects a Google Photos account; system reads selected albums and automatically processes new photos on sync.
3. Support generic web server / CDN URLs: system scans a directory URL, imports photos, generates thumbnails, and indexes faces.
4. Future support planned for Amazon S3 and Microsoft Azure Blob Storage (not in MVP).
5. Each sync run must be idempotent — re-importing the same photo must not create duplicates.
6. Sync progress must be visible to the photographer/admin (photos uploaded, processed, processing).
7. Face indexing per photo must complete in under 2 seconds.
8. Thumbnails must load in under 1 second.

## User Stories
- As a photographer, I want to link my Google Drive folder to an event, so that all photos I upload there are automatically available to guests.
- As a photographer, I want to link my Google Photos album, so that newly added photos sync automatically without manual steps.
- As an admin, I want to point the system at a web server URL, so that photos hosted on any CDN are imported and indexed.
- As a photographer, I want to see a progress dashboard showing how many photos are uploaded vs processed, so that I know when the gallery is ready for guests.
- As a system, I want sync runs to be idempotent, so that retrying a failed sync never creates duplicate entries.

## Features
| Feature | Status |
|---------|--------|
| Google Drive OAuth connection and folder sync | Backlog |
| Google Photos OAuth connection and album sync | Backlog |
| Web server / CDN URL import and directory scan | Backlog |
| Thumbnail generation pipeline | Backlog |
| Duplicate detection on re-import | Backlog |
| Sync progress tracking (uploaded / processed / pending) | Backlog |
| Scheduled / webhook-triggered re-sync | Backlog |

## Success Metrics
- Thumbnail generation completes in under 1 second per photo at p95.
- Face indexing completes in under 2 seconds per photo at p95.
- Zero duplicate photos after a re-sync of the same source.
- 50,000+ photos per event supported without degradation.

## Decisions
<!-- Decisions made during this epic's lifetime -->

## Open Questions
- [ ] Should Google Drive / Photos sync be continuous (webhook) or scheduled (cron)? — owner: Product Team
- [ ] What image formats are supported (JPEG, PNG, HEIC, RAW)? — owner: Product Team
- [ ] Who manages OAuth credential rotation for Google integrations? — owner: Product Team
