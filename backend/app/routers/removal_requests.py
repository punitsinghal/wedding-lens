"""Guest face-data removal request endpoint (D6 — REQ-9 to REQ-12)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_validated_guest_event
from app.models.privacy import RemovalRequest
from app.schemas.privacy import RemovalRequestCreate, RemovalRequestSubmittedOut

router = APIRouter(prefix="/api/v1/events/{event_id}", tags=["removal-requests"])


@router.post(
    "/removal-requests",
    response_model=RemovalRequestSubmittedOut,
    status_code=status.HTTP_200_OK,
)
async def submit_removal_request(
    event_id: uuid.UUID,
    body: RemovalRequestCreate,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> RemovalRequestSubmittedOut:
    """Submit a face-data removal request for this event (REQ-11).

    Authentication: guest JWT (existing event session).
    All three fields are required — missing any → 422 automatically (AC-3d).
    Returns 200 with on-screen confirmation message (AC-3b).
    """
    # guest_event is validated; we only need event_id which is path param.
    # We do NOT log name/email (PII constraint — constraints.md).
    request = RemovalRequest(
        id=uuid.uuid4(),
        event_id=event_id,
        submitted_at=datetime.now(timezone.utc),
        guest_name=body.name,
        guest_email=body.email,
        description=body.description,
        status="pending",
        fulfilled_at=None,
    )
    db.add(request)
    await db.flush()

    return RemovalRequestSubmittedOut(
        id=request.id,
        status=request.status,
        message=(
            "Your face data removal request has been received and will be "
            "processed within 24 hours."
        ),
    )
