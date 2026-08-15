"""Internal admin-only endpoints — NOT on the public /api/v1 prefix.

The /internal prefix is intentionally separate so the Nginx/proxy layer can
block it from external traffic. AC-7b: "rejected from public path" is the
proxy's responsibility. The backend enforces require_admin (401/403) as a
defense-in-depth layer even if the proxy misconfigures the block.

Register in main.py with app.include_router(internal_router) — no prefix
override needed since the router itself uses /internal.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_admin
from app.models.photo import FaceRecord
from app.models.user import User
from app.utils.crypto import decrypt_embedding

logger = logging.getLogger("weddinglens")

# NOT /api/v1 — proxy must block /internal from external reach (AC-7b).
router = APIRouter(prefix="/internal", tags=["internal"])

# Number of face_records to sample for the decrypt check.
# Full O(n) scan is too slow for large events; sample is sufficient for an
# audit signal. If sampled rows all decrypt successfully, we return True.
_AUDIT_SAMPLE_SIZE = 100


@router.get("/audit/embedding-encryption")
async def audit_embedding_encryption(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """Verify face embeddings are encrypted at rest (REQ-24/25, AC-7a).

    Samples up to _AUDIT_SAMPLE_SIZE face_records from PostgreSQL and
    attempts to decrypt each embedding_enc value.  Returns:
      {
        "embeddings_encrypted": bool,   # true iff all sampled rows are
                                        # non-null and decrypt successfully
        "checked_count": int,           # number of rows actually checked
        "total_count": int,             # total face_records in DB
      }

    embeddings_encrypted=true with checked_count=0 when there are no records
    (no embeddings → trivially no unencrypted ones).

    AC-7b: external non-reachability is the Nginx/proxy responsibility.
    This endpoint enforces require_admin (401/403) as defense-in-depth.
    """
    from app.config import settings

    # Total count
    total_result = await db.execute(
        select(func.count()).select_from(FaceRecord)
    )
    total_count: int = total_result.scalar_one()

    if total_count == 0:
        return {
            "embeddings_encrypted": True,
            "checked_count": 0,
            "total_count": 0,
        }

    # Sample rows
    sample_result = await db.execute(
        select(FaceRecord.id, FaceRecord.embedding_enc)
        .order_by(FaceRecord.created_at.desc())
        .limit(_AUDIT_SAMPLE_SIZE)
    )
    rows = sample_result.all()

    checked_count = 0
    all_ok = True

    for row in rows:
        enc_bytes = row.embedding_enc
        if enc_bytes is None:
            all_ok = False
            checked_count += 1
            continue
        try:
            decrypt_embedding(enc_bytes, settings.SECRET_KEY)
            checked_count += 1
        except Exception:
            all_ok = False
            checked_count += 1

    embeddings_encrypted = all_ok and checked_count > 0

    logger.info(
        '{"event": "embedding_audit", "checked": %d, "total": %d, "ok": %s}',
        checked_count,
        total_count,
        str(embeddings_encrypted).lower(),
    )

    return {
        "embeddings_encrypted": embeddings_encrypted,
        "checked_count": checked_count,
        "total_count": total_count,
    }
