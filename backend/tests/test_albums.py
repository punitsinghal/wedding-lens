"""Album endpoint tests."""

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def make_event(client: AsyncClient, headers: dict, slug: str = None) -> str:
    payload = {
        "name": "Wedding",
        "bride_name": "Alice",
        "groom_name": "Bob",
        "access_mode": "public",
    }
    if slug:
        payload["slug"] = slug
    resp = await client.post("/api/v1/events", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def make_album(
    client: AsyncClient, headers: dict, event_id: str, name: str = "Ceremony", **kwargs
) -> dict:
    payload = {"name": name, **kwargs}
    resp = await client.post(
        f"/api/v1/events/{event_id}/albums", json=payload, headers=headers
    )
    return resp


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_album_success(client: AsyncClient, auth_headers: dict):
    event_id = await make_event(client, auth_headers)
    resp = await make_album(client, auth_headers, event_id)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Ceremony"
    assert body["event_id"] == event_id


@pytest.mark.asyncio
async def test_list_albums(client: AsyncClient, auth_headers: dict):
    event_id = await make_event(client, auth_headers, slug="alice-bob-list")
    await make_album(client, auth_headers, event_id, "Album A")
    await make_album(client, auth_headers, event_id, "Album B")
    resp = await client.get(f"/api/v1/events/{event_id}/albums", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_update_album(client: AsyncClient, auth_headers: dict):
    event_id = await make_event(client, auth_headers, slug="alice-bob-update")
    album_id = (await make_album(client, auth_headers, event_id)).json()["id"]
    resp = await client.put(
        f"/api/v1/events/{event_id}/albums/{album_id}",
        json={"name": "Updated Album"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Album"


@pytest.mark.asyncio
async def test_delete_album(client: AsyncClient, auth_headers: dict):
    event_id = await make_event(client, auth_headers, slug="alice-bob-del")
    album_id = (await make_album(client, auth_headers, event_id)).json()["id"]
    resp = await client.delete(
        f"/api/v1/events/{event_id}/albums/{album_id}", headers=auth_headers
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_album_then_list_is_empty(client: AsyncClient, auth_headers: dict):
    event_id = await make_event(client, auth_headers, slug="alice-bob-del2")
    album_id = (await make_album(client, auth_headers, event_id)).json()["id"]
    await client.delete(
        f"/api/v1/events/{event_id}/albums/{album_id}", headers=auth_headers
    )
    resp = await client.get(f"/api/v1/events/{event_id}/albums", headers=auth_headers)
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Max 10 albums enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_10_albums(client: AsyncClient, auth_headers: dict):
    event_id = await make_event(client, auth_headers, slug="alice-bob-max10")
    for i in range(10):
        resp = await make_album(client, auth_headers, event_id, f"Album {i}")
        assert resp.status_code == 201, f"Album {i} creation failed: {resp.text}"
    # 11th should be rejected
    resp = await make_album(client, auth_headers, event_id, "Album 10")
    assert resp.status_code == 422
    assert "10" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Ceremony category validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_ceremony_category(client: AsyncClient, auth_headers: dict):
    event_id = await make_event(client, auth_headers, slug="alice-bob-cat")
    resp = await make_album(
        client, auth_headers, event_id, "Sangeet Night", ceremony_category="Sangeet"
    )
    assert resp.status_code == 201
    assert resp.json()["ceremony_category"] == "Sangeet"


@pytest.mark.asyncio
async def test_invalid_ceremony_category(client: AsyncClient, auth_headers: dict):
    event_id = await make_event(client, auth_headers, slug="alice-bob-badcat")
    resp = await make_album(
        client, auth_headers, event_id, "Bad", ceremony_category="InvalidCategory"
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_albums_require_auth(client: AsyncClient):
    resp = await client.get("/api/v1/events/00000000-0000-0000-0000-000000000000/albums")
    assert resp.status_code == 403
