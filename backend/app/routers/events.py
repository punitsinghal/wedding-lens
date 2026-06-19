"""Event CRUD and guest slug-resolution endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.event import Event, SlugRedirect
from app.models.user import User
from app.schemas.event import EventCreate, EventOut, EventPublicOut, EventUpdate
from app.services import events as event_svc
from app.services import qr as qr_svc

router = APIRouter(prefix="/api/v1/events", tags=["events"])


def _assert_owner(event: Event, user: User) -> None:
    if event.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the event owner")


def _assert_not_deleted(event: Event) -> None:
    if event.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")


async def _get_owned_event(
    event_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
    allow_deleted: bool = False,
) -> Event:
    event = await event_svc.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if not allow_deleted:
        _assert_not_deleted(event)
    _assert_owner(event, current_user)
    return event


# ---------------------------------------------------------------------------
# Guest entry point — unauthenticated
# ---------------------------------------------------------------------------

@router.get("/by-slug/{slug}")
async def get_event_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> EventPublicOut:
    result = await event_svc.resolve_by_slug(db, slug)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if isinstance(result, SlugRedirect):
        # Fetch the current event to get its current slug for the redirect target
        event = await event_svc.get_event(db, result.event_id)
        if event is None or event.status == "deleted":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        raise HTTPException(
            status_code=status.HTTP_301_MOVED_PERMANENTLY,
            detail=f"/api/v1/events/by-slug/{event.slug}",
            headers={"Location": f"/api/v1/events/by-slug/{event.slug}"},
        )
    return EventPublicOut.model_validate(result)


# ---------------------------------------------------------------------------
# Owner endpoints (JWT required)
# ---------------------------------------------------------------------------

@router.get("", response_model=list[EventOut])
async def list_events(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EventOut]:
    events = await event_svc.list_events_by_owner(db, current_user.id)
    return [EventOut.model_validate(e) for e in events]


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    data: EventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventOut:
    try:
        event = await event_svc.create_event(db, data, current_user.id)
    except event_svc.SlugTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": "slug_taken", "suggestions": exc.suggestions},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return EventOut.model_validate(event)


@router.get("/{event_id}", response_model=EventOut)
async def get_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventOut:
    event = await _get_owned_event(event_id, db, current_user)
    return EventOut.model_validate(event)


@router.put("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: uuid.UUID,
    data: EventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventOut:
    event = await _get_owned_event(event_id, db, current_user)
    try:
        event = await event_svc.update_event(db, event, data)
    except event_svc.SlugTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": "slug_taken", "suggestions": exc.suggestions},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return EventOut.model_validate(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    event = await _get_owned_event(event_id, db, current_user)
    await event_svc.soft_delete_event(db, event)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{event_id}/publish", response_model=EventOut)
async def publish_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventOut:
    event = await _get_owned_event(event_id, db, current_user)
    try:
        event = await event_svc.publish_event(db, event)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return EventOut.model_validate(event)


@router.post("/{event_id}/unpublish", response_model=EventOut)
async def unpublish_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventOut:
    event = await _get_owned_event(event_id, db, current_user)
    event = await event_svc.unpublish_event(db, event)
    return EventOut.model_validate(event)


@router.get("/{event_id}/qr-code")
async def get_qr_code(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    event = await _get_owned_event(event_id, db, current_user)
    png_bytes = qr_svc.generate_qr_png(event.slug)
    return StreamingResponse(
        iter([png_bytes]),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
