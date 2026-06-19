# Photographer Dashboard

**Status:** In Progress
**Owner:** Product Team
**Last Updated:** 2026-06-19

## Summary
Provide photographers with a dedicated dashboard to upload photos via multiple methods, monitor processing progress in real time, and manage albums — so they can deliver a complete indexed gallery to the couple with minimal friction.

## Requirements
1. Photographers can upload photos via: drag-and-drop, folder upload, sync from Google Drive, sync from Google Photos.
2. Dashboard shows real-time upload and processing progress: total photos, processed count, and in-progress count.
3. Photographers can create, rename, and organise albums within an event.
4. Photographers can flag specific photos as "Photographer Choice" for surfacing in the guest gallery.
5. Photographers can be assigned to one or more events by the event owner (bride/groom).
6. Upload resumes automatically after a network interruption (chunked upload with resume support).
7. Face processing is triggered automatically after upload completes.

## User Stories
- As a photographer, I want to drag-and-drop an entire folder of photos onto the upload page, so that I can submit thousands of images without clicking individual files.
- As a photographer, I want to sync directly from my Google Drive or Google Photos, so that I don't have to re-download and re-upload photos I've already edited.
- As a photographer, I want to see a live progress bar showing processed vs. pending photos, so that I know when the gallery is ready for guests.
- As a photographer, I want to resume an interrupted upload from where it left off, so that I don't lose progress on large batch uploads over slow connections.
- As a photographer, I want to flag my best shots as "Photographer Choice", so that guests see the curated highlights first.

## Features
| Feature | Status |
|---------|--------|
| photographer-dashboard | Groomed — ready for /design |
| Google Drive sync | Deferred — Photo Source Integration epic |
| Google Photos sync | Deferred — Photo Source Integration epic |

## Success Metrics
- Upload of 1,000 photos completes without manual retry on a stable connection.
- Processing progress updates visible within 5 seconds of a photo being indexed.
- Photographer can set up an event gallery (upload + organise) in under 30 minutes for 500 photos.

## Decisions
- **Maximum file size: 25 MB per photo** — JPEG and PNG only; HEIC and RAW are out of scope.
- **Google Drive and Google Photos sync deferred** — moved to the Photo Source Integration epic; not part of this epic's delivery.
- **HEIC and RAW format support out of scope** — only JPEG and PNG accepted in the upload pipeline.
- **Photographer edit access restricted to upload and album management** — event settings (name, slug, access mode, cover photo) remain owner-only.
- **Per-event photo storage quotas out of scope** — deferred to the Admin Platform epic.

## Open Questions
- [x] What is the maximum single-file size supported? — **25 MB; JPEG and PNG only** (resolved 2026-06-19)
- [x] Should photographers have edit access to event settings? — **No; restricted to event owner** (resolved 2026-06-19)
- [x] Is there a per-event photo storage quota? — **Out of scope; deferred to Admin Platform epic** (resolved 2026-06-19)
