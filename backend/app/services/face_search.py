"""Face similarity search service."""
import hashlib
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.photo import Photo
from app.services.face_pipeline import _detect_faces
from app.services.qdrant import search_faces
from app.services.search_cache import search_cache

logger = logging.getLogger("weddinglens.face_search")


class NoFaceDetectedError(Exception):
    pass


class NoDominantFaceError(Exception):
    pass


@dataclass
class SearchResult:
    photo_id: str
    thumbnail_url: str


async def run_search(
    selfie_bytes: bytes,
    event_id: uuid.UUID,
    sid: str,
    db: AsyncSession,
) -> list[SearchResult]:
    selfie_hash = hashlib.sha256(selfie_bytes).hexdigest()
    cached = search_cache.get(sid, selfie_hash)
    if cached is not None:
        logger.info('{"event": "search_cache_hit", "event_id": "%s"}', event_id)
        return cached

    try:
        faces = _detect_faces(selfie_bytes)
    finally:
        del selfie_bytes  # REQ-20/21 — delete bytes even on error

    if len(faces) == 0:
        raise NoFaceDetectedError()

    if len(faces) == 1:
        embedding = faces[0]["embedding"]
    else:
        faces_sorted = sorted(faces, key=lambda f: f["det_score"], reverse=True)
        if faces_sorted[0]["det_score"] - faces_sorted[1]["det_score"] < 0.10:
            raise NoDominantFaceError()
        embedding = faces_sorted[0]["embedding"]

    hits = search_faces(
        event_id,
        embedding.tolist(),
        settings.FACE_SEARCH_SCORE_THRESHOLD,
        settings.FACE_SEARCH_RESULT_CAP,
    )

    # Dedup by photo_id (keep highest score per photo)
    best: dict[str, float] = {}
    for h in hits:
        pid = h["photo_id"]
        if pid not in best or h["score"] > best[pid]:
            best[pid] = h["score"]

    # Sort by score descending
    ranked_ids = sorted(best.keys(), key=lambda pid: best[pid], reverse=True)

    # Fetch photos from DB
    photo_ids = [uuid.UUID(pid) for pid in ranked_ids]
    result = await db.execute(
        select(Photo).where(Photo.id.in_(photo_ids), Photo.event_id == event_id)
    )
    photos = {str(p.id): p for p in result.scalars().all()}

    results = []
    for pid in ranked_ids:
        photo = photos.get(pid)
        if photo is None:
            continue
        thumbnail_url = f"/api/v1/events/{event_id}/photos/{photo.id}/thumbnail"
        results.append(SearchResult(photo_id=str(photo.id), thumbnail_url=thumbnail_url))

    search_cache.set(sid, selfie_hash, results)
    logger.info(
        '{"event": "search_complete", "event_id": "%s", "result_count": %d}',
        event_id,
        len(results),
    )
    return results
