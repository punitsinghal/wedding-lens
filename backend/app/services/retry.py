"""APScheduler job to retry failed face-processing jobs and reset stuck ones."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.photo import Photo

logger = logging.getLogger("weddinglens.retry")

STUCK_THRESHOLD_MINUTES = 15
MAX_ATTEMPTS = 5


async def retry_failed_photos() -> None:
    """Entry point for APScheduler every-5-min job."""
    await _reset_stuck_jobs()
    await _retry_failed()


async def _reset_stuck_jobs() -> None:
    threshold = datetime.now(timezone.utc) - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(Photo)
            .where(
                Photo.processing_status == "processing",
                Photo.last_processed_at < threshold,
            )
            .values(processing_status="pending")
            .returning(Photo.id)
        )
        await db.commit()
        reset_ids = result.fetchall()
    if reset_ids:
        logger.info(
            '{"event": "retry_reset_stuck", "count": %d}',
            len(reset_ids),
        )


async def _retry_failed() -> None:
    from app.services.face_pipeline import process_photo

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Photo.id, Photo.event_id)
            .where(
                Photo.processing_status == "failed",
                Photo.processing_attempts < MAX_ATTEMPTS,
            )
        )
        rows = result.fetchall()

    logger.info('{"event": "retry_job_found", "count": %d}', len(rows))

    for photo_id, event_id in rows:
        await process_photo(photo_id, event_id)
