"""Admin endpoint tests."""

import uuid

import pytest
from httpx import AsyncClient



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def make_event(client: AsyncClient, headers: dict, slug: str) -> str:
    payload = {
        "name": "Wedding",
        "bride_name": "Admin",
        "groom_name": "Test",
        "access_mode": "public",
        "slug": slug,
    }
    resp = await client.post("/api/v1/events", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# List events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_list_events(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    await make_event(client, auth_headers, "event-admin-1")
    await make_event(client, auth_headers, "event-admin-2")
    resp = await client.get("/api/v1/admin/events", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    assert "items" in body
    assert body["page"] == 1


@pytest.mark.asyncio
async def test_admin_list_events_pagination(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    for i in range(5):
        await make_event(client, auth_headers, f"pag-event-{i}")
    resp = await client.get(
        "/api/v1/admin/events?page=1&page_size=2", headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["page_size"] == 2


@pytest.mark.asyncio
async def test_admin_list_requires_admin(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/admin/events", headers=auth_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Suspend / unsuspend
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_suspend_event(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    event_id = await make_event(client, auth_headers, "suspend-me")
    resp = await client.post(
        f"/api/v1/admin/events/{event_id}/suspend", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"


@pytest.mark.asyncio
async def test_admin_unsuspend_event(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    event_id = await make_event(client, auth_headers, "unsuspend-me")
    await client.post(f"/api/v1/admin/events/{event_id}/suspend", headers=admin_headers)
    resp = await client.post(
        f"/api/v1/admin/events/{event_id}/unsuspend", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


@pytest.mark.asyncio
async def test_suspend_nonexistent_event(client: AsyncClient, admin_headers: dict):
    resp = await client.post(
        f"/api/v1/admin/events/{uuid.uuid4()}/suspend", headers=admin_headers
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Hard delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_hard_delete(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    event_id = await make_event(client, auth_headers, "hard-delete-me")
    resp = await client.delete(
        f"/api/v1/admin/events/{event_id}", headers=admin_headers
    )
    assert resp.status_code == 204
    # Confirm gone
    resp = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_hard_delete_nonexistent(client: AsyncClient, admin_headers: dict):
    resp = await client.delete(
        f"/api/v1/admin/events/{uuid.uuid4()}", headers=admin_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_delete_requires_admin(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.delete(
        f"/api/v1/admin/events/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 403
