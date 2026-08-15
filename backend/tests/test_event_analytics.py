"""Tests for event-owner analytics (design D5, REQ-6a/6b/6c)."""

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import EventPhotographer
from app.models.event import Event
from app.models.user import User
from app.services.analytics import (
    record_download_event,
    record_search_event,
    record_view_event,
)
from app.services.auth import create_access_token, hash_password
from tests.conftest import TestSessionLocal


@pytest.fixture(autouse=True)
def patch_analytics_session():
    with patch("app.services.analytics.AsyncSessionLocal", TestSessionLocal):
        yield


@pytest_asyncio.fixture
async def owner(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email="analytics-owner@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def other_user(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email="not-the-owner@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def event(db: AsyncSession, owner: User) -> Event:
    ev = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="Analytics Test Wedding",
        bride_name="Alice",
        groom_name="Bob",
        slug=f"analytics-test-{uuid.uuid4().hex[:8]}",
        access_mode="public",
        status="published",
        guest_access_enabled=True,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


def _headers(user: User) -> dict:
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_owner_analytics_returns_correct_counts(
    client: AsyncClient, event: Event, owner: User
):
    await record_view_event(event.id)
    await record_view_event(event.id)
    await record_view_event(event.id)
    await record_download_event(event.id)
    await record_search_event(event.id)
    await record_search_event(event.id)

    resp = await client.get(
        f"/api/v1/events/{event.id}/analytics", headers=_headers(owner)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "total_views": 3,
        "total_downloads": 1,
        "total_searches": 2,
    }


@pytest.mark.asyncio
async def test_owner_analytics_zero_when_no_activity(
    client: AsyncClient, event: Event, owner: User
):
    resp = await client.get(
        f"/api/v1/events/{event.id}/analytics", headers=_headers(owner)
    )
    assert resp.status_code == 200
    assert resp.json() == {"total_views": 0, "total_downloads": 0, "total_searches": 0}


@pytest.mark.asyncio
async def test_owner_analytics_403_for_non_owner(
    client: AsyncClient, event: Event, other_user: User
):
    """REQ-6c/AC-6 — a non-owner authenticated user gets 403, not filtered-empty."""
    resp = await client.get(
        f"/api/v1/events/{event.id}/analytics", headers=_headers(other_user)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_analytics_403_for_assigned_photographer_not_owner(
    client: AsyncClient, db: AsyncSession, event: Event, other_user: User
):
    """REQ-6a is scoped to the event OWNER — an assigned (non-owning)
    photographer must still receive 403 from the analytics endpoint."""
    assignment = EventPhotographer(
        event_id=event.id,
        photographer_id=other_user.id,
        assigned_by=event.owner_id,
    )
    db.add(assignment)
    await db.commit()

    resp = await client.get(
        f"/api/v1/events/{event.id}/analytics", headers=_headers(other_user)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_analytics_404_for_nonexistent_event(
    client: AsyncClient, owner: User
):
    resp = await client.get(
        f"/api/v1/events/{uuid.uuid4()}/analytics", headers=_headers(owner)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_owner_analytics_requires_auth(client: AsyncClient, event: Event):
    resp = await client.get(f"/api/v1/events/{event.id}/analytics")
    assert resp.status_code == 403
