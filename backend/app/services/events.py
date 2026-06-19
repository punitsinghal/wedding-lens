"""Event business logic."""

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, SlugRedirect
from app.schemas.event import EventCreate, EventUpdate

ACCESS_MODES = ("access-code", "magic-link-otp", "public")
MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)


def _slugify(text: str) -> str:
    """Convert a string to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def _generate_base_slug(bride_name: str, groom_name: str) -> str:
    return _slugify(f"{bride_name}-{groom_name}")


async def _is_slug_available(db: AsyncSession, slug: str, exclude_id: uuid.UUID | None = None) -> bool:
    stmt = select(Event.id).where(Event.slug == slug)
    if exclude_id:
        stmt = stmt.where(Event.id != exclude_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is None


async def generate_slug_suggestions(
    db: AsyncSession,
    base_slug: str,
    event_date: datetime | None = None,
    exclude_id: uuid.UUID | None = None,
) -> list[str]:
    """
    Generate up to 3 slug suggestions that are guaranteed available in the DB.
    Strategy: append year, month name, then incrementing suffix.
    """
    now = datetime.now(timezone.utc)
    year = event_date.year if event_date else now.year
    month_name = MONTH_NAMES[(event_date.month - 1) if event_date else now.month - 1]

    candidates = [
        f"{base_slug}-{year}",
        f"{base_slug}-{month_name}",
    ]
    # Incrementing suffix — check 2, 3, 4, …
    counter = 2
    while len(candidates) < 6:
        candidates.append(f"{base_slug}-{counter}")
        counter += 1

    suggestions: list[str] = []
    for candidate in candidates:
        if await _is_slug_available(db, candidate, exclude_id):
            suggestions.append(candidate)
        if len(suggestions) == 3:
            break
    return suggestions


async def create_event(
    db: AsyncSession, data: EventCreate, owner_id: uuid.UUID
) -> Event:
    slug = _slugify(data.slug) if data.slug else _generate_base_slug(data.bride_name, data.groom_name)

    # Validate access_mode / access_code consistency
    if data.access_mode == "access-code" and not data.access_code:
        raise ValueError("access_code is required when access_mode is 'access-code'")

    # Check for slug availability before attempting the insert to avoid
    # poisoning the session with an IntegrityError that requires rollback.
    if not await _is_slug_available(db, slug):
        event_date_dt = (
            datetime(data.event_date.year, data.event_date.month, data.event_date.day)
            if data.event_date
            else None
        )
        suggestions = await generate_slug_suggestions(db, slug, event_date_dt)
        raise SlugTakenError(suggestions=suggestions)

    event = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name=data.name,
        bride_name=data.bride_name,
        groom_name=data.groom_name,
        event_date=data.event_date,
        slug=slug,
        access_mode=data.access_mode,
        access_code=data.access_code,
        status="draft",
    )
    db.add(event)
    await db.flush()
    return event


async def get_event(db: AsyncSession, event_id: uuid.UUID) -> Event | None:
    result = await db.execute(select(Event).where(Event.id == event_id))
    return result.scalar_one_or_none()


async def list_events_by_owner(db: AsyncSession, owner_id: uuid.UUID) -> list[Event]:
    result = await db.execute(
        select(Event)
        .where(Event.owner_id == owner_id, Event.status != "deleted")
        .order_by(Event.created_at.desc())
    )
    return list(result.scalars().all())


async def update_event(
    db: AsyncSession,
    event: Event,
    data: EventUpdate,
) -> Event:
    old_slug = event.slug
    slug_changed = False

    if data.slug is not None:
        new_slug = _slugify(data.slug)
        if new_slug != old_slug:
            slug_changed = True

    if data.name is not None:
        event.name = data.name
    if data.bride_name is not None:
        event.bride_name = data.bride_name
    if data.groom_name is not None:
        event.groom_name = data.groom_name
    if data.event_date is not None:
        event.event_date = data.event_date
    if data.cover_photo_id is not None:
        event.cover_photo_id = data.cover_photo_id
    if data.access_mode is not None:
        event.access_mode = data.access_mode
    if data.access_code is not None:
        event.access_code = data.access_code

    # Validate access_mode / access_code consistency after update
    if event.access_mode == "access-code" and not event.access_code:
        raise ValueError("access_code is required when access_mode is 'access-code'")

    if slug_changed:
        new_slug = _slugify(data.slug)  # type: ignore[arg-type]
        # Check availability before mutating state to keep the session clean.
        if not await _is_slug_available(db, new_slug, exclude_id=event.id):
            event_date_obj = event.event_date
            event_date_dt = (
                datetime(event_date_obj.year, event_date_obj.month, event_date_obj.day)
                if event_date_obj
                else None
            )
            suggestions = await generate_slug_suggestions(
                db, new_slug, event_date_dt, exclude_id=event.id
            )
            raise SlugTakenError(suggestions=suggestions)

        # Insert old slug into redirects table, then update the event slug.
        # Both happen atomically within the caller's transaction.
        redirect = SlugRedirect(
            id=uuid.uuid4(),
            old_slug=old_slug,
            event_id=event.id,
        )
        db.add(redirect)
        event.slug = new_slug

    event.updated_at = datetime.now(timezone.utc)
    db.add(event)
    await db.flush()
    return event


async def soft_delete_event(db: AsyncSession, event: Event) -> None:
    event.status = "deleted"
    event.deleted_at = datetime.now(timezone.utc)
    db.add(event)
    await db.flush()


async def publish_event(db: AsyncSession, event: Event) -> Event:
    """Validate and publish an event (REQ-31)."""
    errors: list[str] = []
    if not event.slug:
        errors.append("slug is required")
    if event.cover_photo_id is None:
        errors.append("cover_photo_id is required")
    if event.access_mode == "access-code" and not event.access_code:
        errors.append("access_code is required when access_mode is 'access-code'")
    if errors:
        raise ValueError("; ".join(errors))

    event.status = "published"
    event.updated_at = datetime.now(timezone.utc)
    db.add(event)
    await db.flush()
    return event


async def unpublish_event(db: AsyncSession, event: Event) -> Event:
    event.status = "draft"
    event.updated_at = datetime.now(timezone.utc)
    db.add(event)
    await db.flush()
    return event


async def resolve_by_slug(db: AsyncSession, slug: str) -> Event | SlugRedirect | None:
    """
    Return the event if slug matches directly, or a SlugRedirect if it's an
    old slug, or None if not found.
    """
    # Check current slugs first
    result = await db.execute(
        select(Event).where(Event.slug == slug, Event.status != "deleted")
    )
    event = result.scalar_one_or_none()
    if event:
        return event

    # Check slug_redirects
    result = await db.execute(
        select(SlugRedirect).where(SlugRedirect.old_slug == slug)
    )
    redirect = result.scalar_one_or_none()
    return redirect


async def list_events_paginated(
    db: AsyncSession, page: int, page_size: int
) -> tuple[list[Event], int]:
    offset = (page - 1) * page_size
    count_result = await db.execute(select(func.count()).select_from(Event))
    total = count_result.scalar_one()
    result = await db.execute(
        select(Event).order_by(Event.created_at.desc()).offset(offset).limit(page_size)
    )
    events = list(result.scalars().all())
    return events, total


class SlugTakenError(Exception):
    def __init__(self, suggestions: list[str]) -> None:
        super().__init__("slug_taken")
        self.suggestions = suggestions
