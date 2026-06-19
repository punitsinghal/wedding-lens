# AI Face Processing Pipeline

**Status:** Draft
**Owner:** Product Team
**Last Updated:** 2026-06-19

## Summary
Build an automated pipeline that detects faces in every imported wedding photo, generates face embeddings, and stores them in a vector database so that guests can later find themselves using a selfie search.

## Requirements
1. For every imported photo, the pipeline must: detect faces, generate a 512-dimensional embedding per face, store the embedding vector with photo ID, event ID, and bounding box in the vector database.
2. Face detection must use one of: RetinaFace, MTCNN, or InsightFace (recommended: InsightFace).
3. Face embedding must use one of: ArcFace, FaceNet, or InsightFace (recommended: InsightFace + ArcFace).
4. Vector storage must use Qdrant (primary) with FAISS as a fallback option.
5. Each face record must store: vector embedding, face bounding box coordinates, event_id, photo_id.
6. Face embeddings at rest must be encrypted.
7. Pipeline must process each photo (detection + embedding + store) in under 2 seconds.
8. Processing must be asynchronous — photo import should not block the upload response.
9. Failed processing jobs must be retryable without reprocessing already-completed photos.

## User Stories
- As a system, I want to detect all faces in an imported photo, so that each person in the photo can later be matched by a guest's selfie.
- As a system, I want to generate a face embedding for each detected face, so that similarity search can find visually matching faces.
- As a system, I want to store embeddings in a vector database scoped to an event, so that searches are isolated per wedding.
- As an admin, I want to monitor face processing queue depth and failure rate, so that I can detect and resolve bottlenecks.
- As a system, I want face embeddings encrypted at rest, so that biometric data is protected from storage-level breaches.

## Features
| Feature | Status |
|---------|--------|
| Face detection service (InsightFace integration) | Backlog |
| Face embedding generation (ArcFace / InsightFace) | Backlog |
| Qdrant vector database setup and collection-per-event schema | Backlog |
| Async processing queue (face detection → embedding → store) | Backlog |
| Embedding encryption at rest | Backlog |
| Processing failure retry mechanism | Backlog |
| Admin processing monitor (queue depth, error rate, throughput) | Backlog |

## Success Metrics
- 100% of imported photos have their faces indexed before the gallery goes live.
- Face indexing p95 latency under 2 seconds per photo.
- Zero loss of embeddings on queue worker restart.
- Encryption verified on all stored vector records.

## Decisions
- Recommended stack: InsightFace (detection + embedding) + Qdrant (vector DB).

## Open Questions
- [ ] Should Qdrant use one collection per event or one global collection with event_id filtering? — owner: Product Team
- [ ] What is the GPU/CPU infrastructure plan for running InsightFace at scale? — owner: Engineering
- [ ] What is the minimum detectable face size (pixels) in a group photo? — owner: Product Team
