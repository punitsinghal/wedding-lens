"""Tests for photographer assignment endpoints."""
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import EventPhotographer
from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.services.auth import create_access_token, hash_password


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def owner(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email="assign-owner@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def photographer(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email="photographer@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def third_user(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email="third@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
def owner_headers(owner: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(owner.id))}"}


@pytest.fixture
def photographer_headers(photographer: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(photographer.id))}"}


@pytest.fixture
def third_headers(third_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(third_user.id))}"}


@pytest_asyncio.fixture
async def event(db: AsyncSession, owner: User) -> Event:
    ev = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="Assignment Test Wedding",
        bride_name="Alice",
        groom_name="Bob",
        slug=f"assign-test-{uuid.uuid4().hex[:8]}",
        status="published",
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


@pytest_asyncio.fixture
async def assigned_event(
    db: AsyncSession, event: Event, owner: User, photographer: User
) -> Event:
    """Event with photographer already assigned."""
    assignment = EventPhotographer(
        event_id=event.id,
        photographer_id=photographer.id,
        assigned_by=owner.id,
    )
    db.add(assignment)
    await db.commit()
    return event


# ---------------------------------------------------------------------------
# 1. Assign photographer by email → 201
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_photographer_returns_201(
    client: AsyncClient,
    owner_headers: dict,
    event: Event,
    photographer: User,
):
    resp = await client.post(
        f"/api/v1/events/{event.id}/photographers",
        headers=owner_headers,
        json={"email": photographer.email},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["photographer_id"] == str(photographer.id)
    assert body["email"] == photographer.email


@pytest.mark.asyncio
async def test_assign_photographer_nonexistent_email(
    client: AsyncClient, owner_headers: dict, event: Event
):
    resp = await client.post(
        f"/api/v1/events/{event.id}/photographers",
        headers=owner_headers,
        json={"email": "nobody@example.com"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_assign_photographer_already_assigned_returns_422(
    client: AsyncClient,
    owner_headers: dict,
    assigned_event: Event,
    photographer: User,
):
    resp = await client.post(
        f"/api/v1/events/{assigned_event.id}/photographers",
        headers=owner_headers,
        json={"email": photographer.email},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_assign_photographer_requires_owner(
    client: AsyncClient,
    photographer_headers: dict,
    event: Event,
    third_user: User,
):
    """A non-owner (even an assigned photographer) cannot assign other photographers."""
    resp = await client.post(
        f"/api/v1/events/{event.id}/photographers",
        headers=photographer_headers,
        json={"email": third_user.email},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 2. Assigned photographer can access upload/album endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assigned_photographer_can_list_photos(
    client: AsyncClient,
    photographer_headers: dict,
    assigned_event: Event,
):
    resp = await client.get(
        f"/api/v1/events/{assigned_event.id}/photos",
        headers=photographer_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_assigned_photographer_can_initiate_upload(
    client: AsyncClient,
    photographer_headers: dict,
    assigned_event: Event,
    tmp_path: Path,
):
    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.post(
            f"/api/v1/events/{assigned_event.id}/uploads",
            headers=photographer_headers,
            json={
                "filename": "shot.jpg",
                "file_size_bytes": 1024,
                "content_hash": "photo-hash-999",
            },
        )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_assigned_photographer_can_create_album(
    client: AsyncClient,
    photographer_headers: dict,
    assigned_event: Event,
):
    resp = await client.post(
        f"/api/v1/events/{assigned_event.id}/albums",
        headers=photographer_headers,
        json={"name": "Ceremony"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_assigned_photographer_can_toggle_choice(
    client: AsyncClient,
    photographer_headers: dict,
    assigned_event: Event,
    db: AsyncSession,
):
    photo = Photo(
        id=uuid.uuid4(),
        event_id=assigned_event.id,
        filename="choice.jpg",
        storage_path=f"events/{assigned_event.id}/choice.jpg",
        file_size=512,
        processing_status="complete",
    )
    db.add(photo)
    await db.commit()

    resp = await client.patch(
        f"/api/v1/events/{assigned_event.id}/photos/{photo.id}/photographer-choice",
        headers=photographer_headers,
        json={"is_photographer_choice": True},
    )
    assert resp.status_code == 200
    assert resp.json()["is_photographer_choice"] is True


# ---------------------------------------------------------------------------
# 3. Non-assigned user gets 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_assigned_user_cannot_list_photos(
    client: AsyncClient,
    third_headers: dict,
    event: Event,
):
    resp = await client.get(
        f"/api/v1/events/{event.id}/photos",
        headers=third_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_assigned_user_cannot_initiate_upload(
    client: AsyncClient,
    third_headers: dict,
    event: Event,
    tmp_path: Path,
):
    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads",
            headers=third_headers,
            json={"filename": "x.jpg", "file_size_bytes": 100, "content_hash": "h"},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. Revoke assignment → 204; revoked user gets 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_assignment_returns_204(
    client: AsyncClient,
    owner_headers: dict,
    assigned_event: Event,
    photographer: User,
):
    resp = await client.delete(
        f"/api/v1/events/{assigned_event.id}/photographers/{photographer.id}",
        headers=owner_headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_revoked_photographer_gets_403(
    client: AsyncClient,
    owner_headers: dict,
    photographer_headers: dict,
    assigned_event: Event,
    photographer: User,
):
    # Revoke
    revoke_resp = await client.delete(
        f"/api/v1/events/{assigned_event.id}/photographers/{photographer.id}",
        headers=owner_headers,
    )
    assert revoke_resp.status_code == 204

    # Revoked user can no longer access photos
    photos_resp = await client.get(
        f"/api/v1/events/{assigned_event.id}/photos",
        headers=photographer_headers,
    )
    assert photos_resp.status_code == 403


@pytest.mark.asyncio
async def test_revoke_nonexistent_assignment_returns_404(
    client: AsyncClient,
    owner_headers: dict,
    event: Event,
    photographer: User,
):
    resp = await client.delete(
        f"/api/v1/events/{event.id}/photographers/{photographer.id}",
        headers=owner_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_requires_owner(
    client: AsyncClient,
    photographer_headers: dict,
    assigned_event: Event,
    photographer: User,
):
    resp = await client.delete(
        f"/api/v1/events/{assigned_event.id}/photographers/{photographer.id}",
        headers=photographer_headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 5. List my assigned events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_my_events_as_photographer(
    client: AsyncClient,
    photographer_headers: dict,
    assigned_event: Event,
):
    resp = await client.get(
        "/api/v1/photographers/me/events",
        headers=photographer_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "events" in body
    event_ids = [e["id"] for e in body["events"]]
    assert str(assigned_event.id) in event_ids


@pytest.mark.asyncio
async def test_list_my_events_empty_when_not_assigned(
    client: AsyncClient,
    third_headers: dict,
):
    resp = await client.get(
        "/api/v1/photographers/me/events",
        headers=third_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["events"] == []


@pytest.mark.asyncio
async def test_list_my_events_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/photographers/me/events")
    assert resp.status_code in (401, 403)
