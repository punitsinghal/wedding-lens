"""Photographer-to-event assignment and revocation endpoints."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, get_event_owner_only
from app.models.assignment import EventPhotographer
from app.models.event import Event
from app.models.user import User

router = APIRouter(prefix="/api/v1", tags=["assignments"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AssignPhotographerRequest(BaseModel):
    email: str


class AssignPhotographerResponse(BaseModel):
    photographer_id: uuid.UUID
    email: str


class AssignedEventsResponse(BaseModel):
    events: list[dict]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/events/{event_id}/photographers",
    response_model=AssignPhotographerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_photographer(
    event_id: uuid.UUID,
    body: AssignPhotographerRequest,
    event: Event = Depends(get_event_owner_only),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssignPhotographerResponse:
    """Assign a photographer to an event by email (owner only)."""
    # Find user by email
    user_result = await db.execute(
        select(User).where(User.email == body.email)
    )
    target_user = user_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No user found with email '{body.email}'",
        )

    # Check not already assigned
    existing_result = await db.execute(
        select(EventPhotographer).where(
            EventPhotographer.event_id == event_id,
            EventPhotographer.photographer_id == target_user.id,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Photographer is already assigned to this event",
        )

    assignment = EventPhotographer(
        event_id=event_id,
        photographer_id=target_user.id,
        assigned_by=current_user.id,
    )
    db.add(assignment)
    await db.commit()

    return AssignPhotographerResponse(
        photographer_id=target_user.id,
        email=target_user.email,
    )


@router.delete(
    "/events/{event_id}/photographers/{photographer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_photographer(
    event_id: uuid.UUID,
    photographer_id: uuid.UUID,
    event: Event = Depends(get_event_owner_only),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke a photographer's assignment from an event (owner only)."""
    result = await db.execute(
        select(EventPhotographer).where(
            EventPhotographer.event_id == event_id,
            EventPhotographer.photographer_id == photographer_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    await db.delete(assignment)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/photographers/me/events")
async def list_my_assigned_events(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssignedEventsResponse:
    """List all events this user is assigned to as photographer."""
    assignments_result = await db.execute(
        select(EventPhotographer).where(
            EventPhotographer.photographer_id == current_user.id
        )
    )
    assignments = list(assignments_result.scalars().all())

    event_ids = [a.event_id for a in assignments]
    if not event_ids:
        return AssignedEventsResponse(events=[])

    events_result = await db.execute(
        select(Event).where(
            Event.id.in_(event_ids),
            Event.status != "deleted",
        )
    )
    events = list(events_result.scalars().all())

    return AssignedEventsResponse(
        events=[
            {
                "id": str(e.id),
                "name": e.name,
                "slug": e.slug,
                "status": e.status,
                "bride_name": e.bride_name,
                "groom_name": e.groom_name,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    )
