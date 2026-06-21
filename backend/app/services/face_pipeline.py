"""Face detection + embedding pipeline using InsightFace/ArcFace."""
import logging
import uuid
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import func, select, update

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.photo import FaceRecord, Photo
from app.utils.crypto import encrypt_embedding

logger = logging.getLogger("weddinglens.face_pipeline")

MIN_FACE_SIZE = 40  # pixels; InsightFace default

_face_app = None


def _get_face_app():
    """Lazy-init InsightFace app. Monkeypatch this in tests."""
    global _face_app
    if _face_app is None:
        from insightface.app import FaceAnalysis
        _face_app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
        _face_app.prepare(ctx_id=0, det_size=(640, 640))
    return _face_app


def _detect_faces(image_bytes: bytes) -> list[dict]:
    """
    Run InsightFace detection + ArcFace embedding on raw image bytes.
    Returns list of dicts: {"bbox": [x,y,w,h], "embedding": np.ndarray[512]}.
    Faces smaller than MIN_FACE_SIZE in either dimension are skipped.
    """
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")

    app = _get_face_app()
    faces = app.get(img)

    results = []
    for face in faces:
        bbox = face.bbox.astype(int)  # [x1, y1, x2, y2]
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE:
            continue
        results.append({
            "bbox": [x1, y1, w, h],
            "embedding": face.normed_embedding,  # float32[512]
        })
    return results


async def process_photo(photo_id: uuid.UUID, event_id: uuid.UUID) -> None:
    """
    Background task: detect faces, embed, encrypt, store in Qdrant + face_records.

    Idempotency gate: atomically transitions pending/failed → processing.
    If the gate returns 0 rows, another worker owns this job — exit immediately.
    """
    async with AsyncSessionLocal() as db:
        # Idempotency gate
        result = await db.execute(
            update(Photo)
            .where(
                Photo.id == photo_id,
                Photo.processing_status.in_(["pending", "failed"]),
            )
            .values(
                processing_status="processing",
                processing_attempts=Photo.processing_attempts + 1,
                last_processed_at=datetime.now(timezone.utc),
                updated_at=func.now(),
            )
            .returning(Photo.id)
        )
        await db.commit()
        claimed = result.fetchone()
        if claimed is None:
            logger.info(
                '{"event": "face_pipeline_skip", "photo_id": "%s", "reason": "already_owned"}',
                photo_id,
            )
            return

    await _run_pipeline(photo_id, event_id)


async def _run_pipeline(photo_id: uuid.UUID, event_id: uuid.UUID) -> None:
    """Execute detection, embedding, and storage. Handles errors → failed/error status."""
    from app.services.qdrant import ensure_collection, upsert_face_vectors

    # Read storage_path and processing_attempts in a single session, then close
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Photo).where(Photo.id == photo_id))
        photo = result.scalar_one_or_none()
        if photo is None:
            logger.error('{"event": "face_pipeline_no_photo", "photo_id": "%s"}', photo_id)
            return
        storage_path = photo.storage_path
        attempts = photo.processing_attempts

    try:
        # Read image bytes from storage
        from pathlib import Path

        image_path = Path(settings.STORAGE_PATH) / storage_path
        image_bytes = image_path.read_bytes()

        faces = _detect_faces(image_bytes)

        if not faces:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Photo)
                    .where(Photo.id == photo_id)
                    .values(face_count=0, processing_status="complete", updated_at=func.now())
                )
                await db.commit()
            logger.info(
                '{"event": "face_pipeline_complete", "photo_id": "%s", "face_count": 0}',
                photo_id,
            )
            return

        # Build Qdrant points and face_record rows (no session held)
        qdrant_points = []
        face_record_objs = []
        for face in faces:
            record_id = uuid.uuid4()
            bbox = face["bbox"]
            embedding: np.ndarray = face["embedding"]
            enc = encrypt_embedding(embedding, settings.SECRET_KEY)

            qdrant_points.append({
                "id": record_id,
                "vector": embedding.tolist(),
                "payload": {
                    "photo_id": str(photo_id),
                    "event_id": str(event_id),
                    "bbox": bbox,
                },
            })
            face_record_objs.append(
                FaceRecord(
                    id=record_id,
                    photo_id=photo_id,
                    event_id=event_id,
                    qdrant_point_id=record_id,
                    bbox_x=bbox[0],
                    bbox_y=bbox[1],
                    bbox_w=bbox[2],
                    bbox_h=bbox[3],
                    embedding_enc=enc,
                )
            )

        # Qdrant upsert outside any DB session — no connection held across network I/O
        ensure_collection(event_id)
        upsert_face_vectors(event_id, qdrant_points)

        # Short-lived session: batch insert face_records + mark photo complete
        async with AsyncSessionLocal() as db:
            db.add_all(face_record_objs)
            await db.execute(
                update(Photo)
                .where(Photo.id == photo_id)
                .values(face_count=len(faces), processing_status="complete", updated_at=func.now())
            )
            await db.commit()

        logger.info(
            '{"event": "face_pipeline_complete", "photo_id": "%s", "face_count": %d}',
            photo_id,
            len(faces),
        )

    except Exception as exc:
        logger.error(
            '{"event": "face_pipeline_error", "event_id": "%s", "photo_id": "%s", "exc_type": "%s", "detail": "%s"}',
            event_id,
            photo_id,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        # Determine next status: failed (retryable) or error (permanent)
        async with AsyncSessionLocal() as db:
            next_status = "error" if attempts >= 5 else "failed"
            await db.execute(
                update(Photo)
                .where(Photo.id == photo_id)
                .values(processing_status=next_status, updated_at=func.now())
            )
            await db.commit()
