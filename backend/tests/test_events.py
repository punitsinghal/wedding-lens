"""Event endpoint tests."""

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo
from app.services import r2



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def create_event(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {
        "name": "Test Wedding",
        "bride_name": "Priya",
        "groom_name": "Rahul",
        "access_mode": "public",
        **overrides,
    }
    resp = await client.post("/api/v1/events", json=payload, headers=headers)
    return resp


# ---------------------------------------------------------------------------
# CRUD happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_event_success(client: AsyncClient, auth_headers: dict):
    resp = await create_event(client, auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Test Wedding"
    assert body["slug"] == "priya-rahul"
    assert body["status"] == "draft"


@pytest.mark.asyncio
async def test_create_event_custom_slug(client: AsyncClient, auth_headers: dict):
    resp = await create_event(client, auth_headers, slug="my-custom-slug")
    assert resp.status_code == 201
    assert resp.json()["slug"] == "my-custom-slug"


@pytest.mark.asyncio
async def test_get_event(client: AsyncClient, auth_headers: dict):
    create_resp = await create_event(client, auth_headers)
    event_id = create_resp.json()["id"]
    resp = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == event_id


@pytest.mark.asyncio
async def test_update_event(client: AsyncClient, auth_headers: dict):
    event_id = (await create_event(client, auth_headers)).json()["id"]
    resp = await client.put(
        f"/api/v1/events/{event_id}",
        json={"name": "Updated Wedding"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Wedding"


@pytest.mark.asyncio
async def test_delete_event_soft(client: AsyncClient, auth_headers: dict):
    event_id = (await create_event(client, auth_headers)).json()["id"]
    resp = await client.delete(f"/api/v1/events/{event_id}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_deleted_event_returns_404_to_owner(client: AsyncClient, auth_headers: dict):
    event_id = (await create_event(client, auth_headers)).json()["id"]
    await client.delete(f"/api/v1/events/{event_id}", headers=auth_headers)
    resp = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Slug conflict + suggestions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slug_conflict_returns_422_with_suggestions(
    client: AsyncClient, auth_headers: dict
):
    # Create first event occupying the slug "priya-rahul"
    await create_event(client, auth_headers)
    # Second event with same bride/groom auto-generates same slug
    resp = await create_event(client, auth_headers)
    assert resp.status_code == 422
    body = resp.json()
    detail = body["detail"]
    assert detail["detail"] == "slug_taken"
    assert len(detail["suggestions"]) > 0
    # All suggestions must be different from the taken slug
    for suggestion in detail["suggestions"]:
        assert suggestion != "priya-rahul"


@pytest.mark.asyncio
async def test_slug_conflict_on_explicit_slug(client: AsyncClient, auth_headers: dict):
    await create_event(client, auth_headers, slug="taken-slug")
    resp = await create_event(
        client,
        auth_headers,
        bride_name="Other",
        groom_name="Person",
        slug="taken-slug",
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["detail"] == "slug_taken"


# ---------------------------------------------------------------------------
# Slug redirect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slug_change_creates_redirect(client: AsyncClient, auth_headers: dict):
    event_id = (await create_event(client, auth_headers)).json()["id"]
    # Change slug
    resp = await client.put(
        f"/api/v1/events/{event_id}",
        json={"slug": "new-slug"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["slug"] == "new-slug"

    # Old slug should 301
    resp = await client.get(
        "/api/v1/events/by-slug/priya-rahul",
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert "new-slug" in resp.headers["location"]


@pytest.mark.asyncio
async def test_by_slug_found(client: AsyncClient, auth_headers: dict):
    await create_event(client, auth_headers)
    resp = await client.get("/api/v1/events/by-slug/priya-rahul")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "priya-rahul"


@pytest.mark.asyncio
async def test_by_slug_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/events/by-slug/does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Public cover-photo endpoint (guest access-code screen background)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cover_by_slug_not_found_for_unknown_slug(client: AsyncClient):
    resp = await client.get("/api/v1/events/by-slug/does-not-exist/cover")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cover_by_slug_404_when_draft(client: AsyncClient, auth_headers: dict):
    create_resp = await create_event(client, auth_headers)
    slug = create_resp.json()["slug"]
    resp = await client.get(f"/api/v1/events/by-slug/{slug}/cover")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cover_by_slug_404_when_cover_photo_row_missing(
    client: AsyncClient, auth_headers: dict
):
    # Published events always have a cover_photo_id, but there is no FK
    # constraint (see models/event.py) — the row itself may not exist.
    event_id = (await create_event(client, auth_headers)).json()["id"]
    fake_photo_id = str(uuid.uuid4())
    await client.put(
        f"/api/v1/events/{event_id}",
        json={"cover_photo_id": fake_photo_id},
        headers=auth_headers,
    )
    publish_resp = await client.post(f"/api/v1/events/{event_id}/publish", headers=auth_headers)
    slug = publish_resp.json()["slug"]

    resp = await client.get(f"/api/v1/events/by-slug/{slug}/cover")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cover_by_slug_success(
    client: AsyncClient, db: AsyncSession, auth_headers: dict
):
    event_id = (await create_event(client, auth_headers)).json()["id"]

    thumbnail_path = f"events/{event_id}/thumbs/{uuid.uuid4()}.webp"

    photo = Photo(
        id=uuid.uuid4(),
        event_id=uuid.UUID(event_id),
        filename="cover.jpg",
        storage_path=f"events/{event_id}/{uuid.uuid4()}.jpg",
        file_size=1024,
        processing_status="complete",
        thumbnail_path=thumbnail_path,
    )
    db.add(photo)
    await db.commit()

    await client.put(
        f"/api/v1/events/{event_id}",
        json={"cover_photo_id": str(photo.id)},
        headers=auth_headers,
    )
    publish_resp = await client.post(f"/api/v1/events/{event_id}/publish", headers=auth_headers)
    slug = publish_resp.json()["slug"]

    signed_url = "https://r2.example.com/signed-cover"
    with patch("app.routers.events.r2.generate_get_url", return_value=signed_url) as mock_gen:
        resp = await client.get(f"/api/v1/events/by-slug/{slug}/cover")
    assert resp.status_code == 302
    assert resp.headers["location"] == signed_url
    mock_gen.assert_called_once_with(thumbnail_path)


@pytest.mark.asyncio
async def test_cover_by_slug_503_when_storage_unavailable(
    client: AsyncClient, db: AsyncSession, auth_headers: dict
):
    event_id = (await create_event(client, auth_headers)).json()["id"]

    thumbnail_path = f"events/{event_id}/thumbs/{uuid.uuid4()}.webp"
    photo = Photo(
        id=uuid.uuid4(),
        event_id=uuid.UUID(event_id),
        filename="cover.jpg",
        storage_path=f"events/{event_id}/{uuid.uuid4()}.jpg",
        file_size=1024,
        processing_status="complete",
        thumbnail_path=thumbnail_path,
    )
    db.add(photo)
    await db.commit()

    await client.put(
        f"/api/v1/events/{event_id}",
        json={"cover_photo_id": str(photo.id)},
        headers=auth_headers,
    )
    publish_resp = await client.post(f"/api/v1/events/{event_id}/publish", headers=auth_headers)
    slug = publish_resp.json()["slug"]

    with patch(
        "app.routers.events.r2.generate_get_url",
        side_effect=r2.StorageUnavailableError("boom"),
    ):
        resp = await client.get(f"/api/v1/events/by-slug/{slug}/cover")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Owner-authenticated cover thumbnail (dashboard event cards)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_cover_thumbnail_404_without_cover_photo(
    client: AsyncClient, auth_headers: dict
):
    event_id = (await create_event(client, auth_headers)).json()["id"]
    resp = await client.get(
        f"/api/v1/events/{event_id}/cover-thumbnail", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_owner_cover_thumbnail_success_while_draft(
    client: AsyncClient, db: AsyncSession, auth_headers: dict
):
    # Unlike the public by-slug endpoint, the owner-authenticated variant
    # must serve the cover thumbnail even before the event is published.
    event_id = (await create_event(client, auth_headers)).json()["id"]

    thumbnail_path = f"events/{event_id}/thumbs/{uuid.uuid4()}.webp"

    photo = Photo(
        id=uuid.uuid4(),
        event_id=uuid.UUID(event_id),
        filename="cover.jpg",
        storage_path=f"events/{event_id}/{uuid.uuid4()}.jpg",
        file_size=1024,
        processing_status="complete",
        thumbnail_path=thumbnail_path,
    )
    db.add(photo)
    await db.commit()

    await client.put(
        f"/api/v1/events/{event_id}",
        json={"cover_photo_id": str(photo.id)},
        headers=auth_headers,
    )

    signed_url = "https://r2.example.com/signed-cover-thumb"
    with patch("app.routers.events.r2.generate_get_url", return_value=signed_url) as mock_gen:
        resp = await client.get(
            f"/api/v1/events/{event_id}/cover-thumbnail", headers=auth_headers
        )
    assert resp.status_code == 302
    assert resp.headers["location"] == signed_url
    mock_gen.assert_called_once_with(thumbnail_path)


@pytest.mark.asyncio
async def test_owner_cover_thumbnail_403_for_non_owner(
    client: AsyncClient, auth_headers: dict
):
    event_id = (await create_event(client, auth_headers)).json()["id"]
    await client.post(
        "/api/v1/auth/register",
        json={"email": "other-cover@example.com", "password": "pass"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "other-cover@example.com", "password": "pass"},
    )
    other_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}
    resp = await client.get(
        f"/api/v1/events/{event_id}/cover-thumbnail", headers=other_headers
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Publish validation (REQ-31)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_fails_without_cover_photo(client: AsyncClient, auth_headers: dict):
    event_id = (await create_event(client, auth_headers)).json()["id"]
    resp = await client.post(f"/api/v1/events/{event_id}/publish", headers=auth_headers)
    assert resp.status_code == 422
    assert "cover_photo_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_publish_success(client: AsyncClient, auth_headers: dict):
    event_id = (await create_event(client, auth_headers)).json()["id"]
    fake_photo_id = str(uuid.uuid4())
    await client.put(
        f"/api/v1/events/{event_id}",
        json={"cover_photo_id": fake_photo_id},
        headers=auth_headers,
    )
    resp = await client.post(f"/api/v1/events/{event_id}/publish", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


@pytest.mark.asyncio
async def test_publish_fails_access_code_mode_without_code(
    client: AsyncClient, auth_headers: dict
):
    resp = await create_event(
        client,
        auth_headers,
        access_mode="access-code",
    )
    # Creating with access-code but no access_code should fail at create time
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unpublish_event(client: AsyncClient, auth_headers: dict):
    event_id = (await create_event(client, auth_headers)).json()["id"]
    fake_photo_id = str(uuid.uuid4())
    await client.put(
        f"/api/v1/events/{event_id}",
        json={"cover_photo_id": fake_photo_id},
        headers=auth_headers,
    )
    await client.post(f"/api/v1/events/{event_id}/publish", headers=auth_headers)
    resp = await client.post(f"/api/v1/events/{event_id}/unpublish", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"


# ---------------------------------------------------------------------------
# QR code
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_qr_code_returns_png(client: AsyncClient, auth_headers: dict):
    event_id = (await create_event(client, auth_headers)).json()["id"]
    resp = await client.get(f"/api/v1/events/{event_id}/qr-code", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    # PNG magic bytes
    assert resp.content[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# Ownership checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_other_user_cannot_access_event(
    client: AsyncClient, auth_headers: dict
):
    event_id = (await create_event(client, auth_headers)).json()["id"]
    # Register a second user and log in
    await client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "pass"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "other@example.com", "password": "pass"},
    )
    other_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}
    resp = await client.get(f"/api/v1/events/{event_id}", headers=other_headers)
    assert resp.status_code == 403
