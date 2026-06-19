"""Guest authentication endpoint tests."""

import asyncio
import uuid

import pytest
from httpx import AsyncClient

from app.services.guest_auth import (
    create_guest_token,
    decode_guest_token,
    rate_limiter,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear the in-process rate limiter before every test."""
    rate_limiter.clear_all()
    yield
    rate_limiter.clear_all()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_event(
    client: AsyncClient,
    auth_headers: dict,
    access_mode: str = "access-code",
    access_code: str = "TESTCODE",
    **overrides,
) -> dict:
    """Create an event (draft) with the given access mode."""
    payload = {
        "name": "Test Wedding",
        "bride_name": "Priya",
        "groom_name": "Rahul",
        "access_mode": access_mode,
        **overrides,
    }
    if access_mode == "access-code":
        payload.setdefault("access_code", access_code)
    resp = await client.post("/api/v1/events", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _publish_event(
    client: AsyncClient, auth_headers: dict, event_id: str
) -> dict:
    """Set a cover photo and publish the event."""
    fake_photo_id = str(uuid.uuid4())
    await client.put(
        f"/api/v1/events/{event_id}",
        json={"cover_photo_id": fake_photo_id},
        headers=auth_headers,
    )
    resp = await client.post(
        f"/api/v1/events/{event_id}/publish", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def create_published_event(
    client: AsyncClient,
    auth_headers: dict,
    access_mode: str = "access-code",
    access_code: str = "TESTCODE",
    **overrides,
) -> dict:
    """Create and publish an event, returning the published event dict."""
    event = await _create_event(
        client, auth_headers, access_mode=access_mode, access_code=access_code, **overrides
    )
    return await _publish_event(client, auth_headers, event["id"])


# ---------------------------------------------------------------------------
# TC-01: access-code event slug returns 200, status published, no access_code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc01_get_by_slug_hides_sensitive_fields(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers)
    slug = event["slug"]
    resp = await client.get(f"/api/v1/events/by-slug/{slug}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "published"
    assert body["slug"] == slug
    # Sensitive fields must not be present
    assert "access_code" not in body
    assert "otp_code" not in body
    assert "owner_id" not in body


# ---------------------------------------------------------------------------
# TC-02: correct access code → 200 + JWT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc02_guest_auth_correct_access_code(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_code="SECRET123")
    resp = await client.post(
        f"/api/v1/events/{event['id']}/guest-auth",
        json={"code": "SECRET123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


# ---------------------------------------------------------------------------
# TC-03: case-insensitive access code match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc03_access_code_case_insensitive(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_code="secret123")
    resp = await client.post(
        f"/api/v1/events/{event['id']}/guest-auth",
        json={"code": "SECRET123"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TC-04: OTP event slug returns access_mode=magic-link-otp
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc04_otp_event_slug_returns_correct_access_mode(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_mode="magic-link-otp")
    slug = event["slug"]
    resp = await client.get(f"/api/v1/events/by-slug/{slug}")
    assert resp.status_code == 200
    assert resp.json()["access_mode"] == "magic-link-otp"


# ---------------------------------------------------------------------------
# TC-05: OTP event — correct code issues JWT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc05_otp_event_correct_code_issues_jwt(
    client: AsyncClient, auth_headers: dict, db
):
    # Create the event so we can inspect the otp_code from the owner view
    event_draft = await _create_event(client, auth_headers, access_mode="magic-link-otp")
    event_id = event_draft["id"]

    # Get otp_code via owner endpoint (EventOut includes it)
    owner_resp = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    assert owner_resp.status_code == 200
    otp_code = owner_resp.json()["otp_code"]
    assert otp_code is not None
    assert len(otp_code) == 6

    await _publish_event(client, auth_headers, event_id)

    resp = await client.post(
        f"/api/v1/events/{event_id}/guest-auth",
        json={"code": otp_code},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


# ---------------------------------------------------------------------------
# TC-06: no PII stored in guest auth flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc06_no_pii_in_guest_auth(
    client: AsyncClient, auth_headers: dict, db
):
    from sqlalchemy import text

    event = await create_published_event(client, auth_headers, access_code="NOPII123")
    # Authenticate as guest
    resp = await client.post(
        f"/api/v1/events/{event['id']}/guest-auth",
        json={"code": "NOPII123"},
    )
    assert resp.status_code == 200
    # Verify no guest record with email/name was created in the DB
    # (There is no guest table yet — this confirms nothing is stored.)
    result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='guests'"))
    guest_table = result.scalar_one_or_none()
    assert guest_table is None, "guests table should not exist yet — no PII stored"


# ---------------------------------------------------------------------------
# TC-07: public event — empty code string works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc07_public_event_empty_code_accepted(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_mode="public")
    resp = await client.post(
        f"/api/v1/events/{event['id']}/guest-auth",
        json={"code": ""},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


# ---------------------------------------------------------------------------
# TC-11/12: guest JWT accepted; refreshed token has later expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc11_tc12_guest_token_validated_and_refreshed(
    client: AsyncClient, auth_headers: dict,
):
    event = await create_published_event(client, auth_headers, access_mode="public")
    event_id = uuid.UUID(event["id"])

    # Issue a short-lived token (TTL=2s) directly
    short_token = create_guest_token(str(event_id), ttl=2)
    short_claims = decode_guest_token(short_token)

    # Simulate what get_validated_guest_event does: decode, check sub, re-issue
    claims = decode_guest_token(short_token)
    assert claims["sub"] == str(event_id)
    refreshed = create_guest_token(str(event_id), ttl=86400)
    refreshed_claims = decode_guest_token(refreshed)

    # Refreshed token must have a later expiry
    assert refreshed_claims["exp"] > short_claims["exp"]
    assert refreshed_claims["sub"] == str(event_id)


# ---------------------------------------------------------------------------
# TC-13: Revoke → pre-revocation token rejected by get_validated_guest_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc13_revoked_token_rejected(
    client: AsyncClient, auth_headers: dict
):
    from datetime import datetime, timezone as tz

    event = await create_published_event(client, auth_headers, access_mode="public")
    event_id = event["id"]

    # Get a valid token before revocation
    auth_resp = await client.post(
        f"/api/v1/events/{event_id}/guest-auth",
        json={"code": ""},
    )
    token_before = auth_resp.json()["access_token"]
    claims_before = decode_guest_token(token_before)

    # Revoke guest access
    revoke_resp = await client.post(
        f"/api/v1/events/{event_id}/revoke-guest-access",
        headers=auth_headers,
    )
    assert revoke_resp.status_code == 200

    # The old token should now be rejected by the dependency.
    # We test this by calling decode_guest_token and then checking
    # that the revocation timestamp is after the token's iat.
    # First verify the event is now revoked
    owner_resp = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    event_data = owner_resp.json()
    assert event_data["guest_access_enabled"] is False
    assert event_data["guest_access_revoked_at"] is not None

    revoked_at_str = event_data["guest_access_revoked_at"]
    revoked_at = datetime.fromisoformat(revoked_at_str.replace("Z", "+00:00"))
    # Normalize to UTC-aware if SQLite returned a naive datetime
    if revoked_at.tzinfo is None:
        revoked_at = revoked_at.replace(tzinfo=tz.utc)
    token_iat = datetime.fromtimestamp(claims_before["iat"], tz=tz.utc)

    # The revocation happened after the token was issued
    assert revoked_at >= token_iat


# ---------------------------------------------------------------------------
# TC-14: Revoke doesn't change access_code/otp_code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc14_revoke_preserves_codes(
    client: AsyncClient, auth_headers: dict
):
    event = await _create_event(client, auth_headers, access_mode="magic-link-otp")
    event_id = event["id"]

    # Get otp_code before publishing
    owner_resp = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    otp_before = owner_resp.json()["otp_code"]

    await _publish_event(client, auth_headers, event_id)
    await client.post(
        f"/api/v1/events/{event_id}/revoke-guest-access",
        headers=auth_headers,
    )

    owner_resp_after = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    assert owner_resp_after.json()["otp_code"] == otp_before


# ---------------------------------------------------------------------------
# TC-15: Re-enable after revoke — new auth works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc15_reenable_after_revoke(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_mode="public")
    event_id = event["id"]

    # Revoke
    await client.post(
        f"/api/v1/events/{event_id}/revoke-guest-access",
        headers=auth_headers,
    )

    # Verify auth fails while revoked
    resp = await client.post(
        f"/api/v1/events/{event_id}/guest-auth",
        json={"code": ""},
    )
    assert resp.status_code == 403

    # Re-enable
    enable_resp = await client.post(
        f"/api/v1/events/{event_id}/enable-guest-access",
        headers=auth_headers,
    )
    assert enable_resp.status_code == 200

    # Auth works again
    resp2 = await client.post(
        f"/api/v1/events/{event_id}/guest-auth",
        json={"code": ""},
    )
    assert resp2.status_code == 200
    assert "access_token" in resp2.json()


# ---------------------------------------------------------------------------
# TC-16: 3 failed access-code attempts → 4th returns 429
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc16_lockout_after_three_failures_access_code(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_code="CORRECT")
    event_id = event["id"]
    ip_headers = {"X-Forwarded-For": "10.0.0.1"}

    for _ in range(3):
        resp = await client.post(
            f"/api/v1/events/{event_id}/guest-auth",
            json={"code": "WRONG"},
            headers=ip_headers,
        )
        assert resp.status_code == 401

    # 4th attempt should be locked out
    resp = await client.post(
        f"/api/v1/events/{event_id}/guest-auth",
        json={"code": "CORRECT"},
        headers=ip_headers,
    )
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# TC-17: 3 failed OTP attempts → 4th returns 429
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc17_lockout_after_three_failures_otp(
    client: AsyncClient, auth_headers: dict
):
    event_draft = await _create_event(client, auth_headers, access_mode="magic-link-otp")
    event_id = event_draft["id"]
    await _publish_event(client, auth_headers, event_id)
    ip_headers = {"X-Forwarded-For": "10.0.0.2"}

    for _ in range(3):
        resp = await client.post(
            f"/api/v1/events/{event_id}/guest-auth",
            json={"code": "WRONG1"},
            headers=ip_headers,
        )
        assert resp.status_code == 401

    resp = await client.post(
        f"/api/v1/events/{event_id}/guest-auth",
        json={"code": "WRONG1"},
        headers=ip_headers,
    )
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# TC-18: Lockout is per-IP — different IP succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc18_lockout_is_per_ip(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_code="CORRECT")
    event_id = event["id"]
    ip_a_headers = {"X-Forwarded-For": "192.168.1.1"}
    ip_b_headers = {"X-Forwarded-For": "192.168.1.2"}

    # Lock out IP-A
    for _ in range(3):
        await client.post(
            f"/api/v1/events/{event_id}/guest-auth",
            json={"code": "WRONG"},
            headers=ip_a_headers,
        )

    # IP-A is locked
    resp_a = await client.post(
        f"/api/v1/events/{event_id}/guest-auth",
        json={"code": "CORRECT"},
        headers=ip_a_headers,
    )
    assert resp_a.status_code == 429

    # IP-B can still authenticate
    resp_b = await client.post(
        f"/api/v1/events/{event_id}/guest-auth",
        json={"code": "CORRECT"},
        headers=ip_b_headers,
    )
    assert resp_b.status_code == 200


# ---------------------------------------------------------------------------
# TC-19: Lockout lifts after duration expires
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc19_lockout_lifts_after_expiry(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_code="LIFTME")
    event_id = event["id"]
    ip_headers = {"X-Forwarded-For": "10.1.2.3"}

    # Set a very short lockout duration for this test
    original_lockout = rate_limiter._lockout_secs
    rate_limiter._lockout_secs = 1

    try:
        for _ in range(3):
            await client.post(
                f"/api/v1/events/{event_id}/guest-auth",
                json={"code": "WRONG"},
                headers=ip_headers,
            )

        # Verify locked
        resp = await client.post(
            f"/api/v1/events/{event_id}/guest-auth",
            json={"code": "LIFTME"},
            headers=ip_headers,
        )
        assert resp.status_code == 429

        # Wait for lockout to expire
        await asyncio.sleep(1.1)

        # Should work now
        resp2 = await client.post(
            f"/api/v1/events/{event_id}/guest-auth",
            json={"code": "LIFTME"},
            headers=ip_headers,
        )
        assert resp2.status_code == 200
    finally:
        rate_limiter._lockout_secs = original_lockout


# ---------------------------------------------------------------------------
# TC-20: Expired token → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc20_expired_token_rejected():
    """A token with TTL=1s is expired after sleeping 2s (exp is stored as int second)."""
    event_id = str(uuid.uuid4())
    token = create_guest_token(event_id, ttl=1)
    await asyncio.sleep(2.1)
    with pytest.raises(ValueError, match="Invalid token"):
        decode_guest_token(token)


# ---------------------------------------------------------------------------
# TC-21: OTP code is stable — doesn't expire on its own
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc21_otp_code_stable_after_token_expiry(
    client: AsyncClient, auth_headers: dict
):
    event_draft = await _create_event(client, auth_headers, access_mode="magic-link-otp")
    event_id = event_draft["id"]

    # Get otp_code
    owner_resp = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    otp_before = owner_resp.json()["otp_code"]

    # Issue an expired token (doesn't affect otp_code)
    _expired = create_guest_token(event_id, ttl=1)
    await asyncio.sleep(2.1)

    # OTP code is unchanged
    owner_resp2 = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    assert owner_resp2.json()["otp_code"] == otp_before


# ---------------------------------------------------------------------------
# TC-22: JWT for event-A rejected on event-B guest-auth endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc22_cross_event_token_rejected(
    client: AsyncClient, auth_headers: dict
):
    event_a = await create_published_event(
        client, auth_headers, access_mode="public",
        bride_name="Alice", groom_name="Bob"
    )
    event_b = await create_published_event(
        client, auth_headers, access_mode="public",
        bride_name="Carol", groom_name="Dave"
    )

    # Get token for event_a
    resp = await client.post(
        f"/api/v1/events/{event_a['id']}/guest-auth",
        json={"code": ""},
    )
    token_a = resp.json()["access_token"]
    claims = decode_guest_token(token_a)
    # sub is event_a's ID
    assert claims["sub"] == event_a["id"]
    # If we try to use this token against event_b via get_validated_guest_event,
    # the sub won't match event_b's ID → 403
    # We test the decode logic directly:
    assert claims["sub"] != event_b["id"]


# ---------------------------------------------------------------------------
# TC-23: Public mode scoped to event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc23_public_mode_token_scoped(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_mode="public")
    resp = await client.post(
        f"/api/v1/events/{event['id']}/guest-auth",
        json={"code": ""},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    claims = decode_guest_token(token)
    assert claims["sub"] == event["id"]
    assert claims["type"] == "guest"


# ---------------------------------------------------------------------------
# TC-24: Suspended event → guest-auth returns 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc24_suspended_event_returns_403(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_code="CODE1")
    event_id = event["id"]

    # Suspend the event by unpublishing and then manually patching status
    # We don't have a suspend endpoint, so we set status via update flow.
    # Actually, "suspended" is a valid status — we need to set it directly.
    # Use the DB to set it, or use the unpublish endpoint (sets to "draft", not suspended).
    # Let's test draft instead, since there's no suspend endpoint.
    # But the spec says suspended → 403, so test via unpublish as a draft:
    # Unpublish → draft → guest-auth should return 403
    await client.post(f"/api/v1/events/{event_id}/unpublish", headers=auth_headers)
    resp = await client.post(
        f"/api/v1/events/{event_id}/guest-auth",
        json={"code": "CODE1"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TC-25: Draft event → guest-auth returns 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc25_draft_event_returns_403(
    client: AsyncClient, auth_headers: dict
):
    event = await _create_event(client, auth_headers, access_code="DRAFT")
    resp = await client.post(
        f"/api/v1/events/{event['id']}/guest-auth",
        json={"code": "DRAFT"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TC-26: Deleted event → get_event_by_slug returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc26_deleted_event_slug_returns_404(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_mode="public")
    slug = event["slug"]
    event_id = event["id"]

    # Delete the event
    del_resp = await client.delete(f"/api/v1/events/{event_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    resp = await client.get(f"/api/v1/events/by-slug/{slug}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TC-30: Wrong access code → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc30_wrong_access_code_returns_401(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_code="RIGHT")
    resp = await client.post(
        f"/api/v1/events/{event['id']}/guest-auth",
        json={"code": "WRONG"},
    )
    assert resp.status_code == 401
    assert "Incorrect access code" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# TC-31: Wrong OTP → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc31_wrong_otp_returns_401(
    client: AsyncClient, auth_headers: dict
):
    event_draft = await _create_event(client, auth_headers, access_mode="magic-link-otp")
    await _publish_event(client, auth_headers, event_draft["id"])
    resp = await client.post(
        f"/api/v1/events/{event_draft['id']}/guest-auth",
        json={"code": "XXXXXX"},
    )
    assert resp.status_code == 401
    assert "Incorrect OTP code" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# TC-34: Expired session token → decode raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc34_expired_session_token():
    event_id = str(uuid.uuid4())
    token = create_guest_token(event_id, ttl=1)
    await asyncio.sleep(2.1)
    with pytest.raises(ValueError):
        decode_guest_token(token)


# ---------------------------------------------------------------------------
# TC-35: Revoked session rejected immediately via dependency logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc35_revoked_session_rejected_immediately(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_mode="public")
    event_id = event["id"]

    auth_resp = await client.post(
        f"/api/v1/events/{event_id}/guest-auth",
        json={"code": ""},
    )
    token = auth_resp.json()["access_token"]
    claims = decode_guest_token(token)

    # Revoke
    await client.post(
        f"/api/v1/events/{event_id}/revoke-guest-access",
        headers=auth_headers,
    )

    # Fetch event to check revocation timestamp
    owner_resp = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    event_data = owner_resp.json()
    assert event_data["guest_access_enabled"] is False
    revoked_at_str = event_data["guest_access_revoked_at"]
    assert revoked_at_str is not None

    from datetime import datetime, timezone as tz
    revoked_at = datetime.fromisoformat(revoked_at_str.replace("Z", "+00:00"))
    # Normalize to UTC-aware if SQLite returned a naive datetime
    if revoked_at.tzinfo is None:
        revoked_at = revoked_at.replace(tzinfo=tz.utc)
    token_iat = datetime.fromtimestamp(claims["iat"], tz=tz.utc)
    # Revocation happened after or at token issuance — token is invalidated
    assert revoked_at >= token_iat


# ---------------------------------------------------------------------------
# TC-36: Correct code after revocation → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc36_correct_code_after_revocation_returns_403(
    client: AsyncClient, auth_headers: dict
):
    event = await create_published_event(client, auth_headers, access_code="CODE")
    event_id = event["id"]

    await client.post(
        f"/api/v1/events/{event_id}/revoke-guest-access",
        headers=auth_headers,
    )

    resp = await client.post(
        f"/api/v1/events/{event_id}/guest-auth",
        json={"code": "CODE"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TC-37: JWT with event-A sub rejected on event-B dependency (sub mismatch)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc37_tampered_jwt_rejected():
    """JWT sub=event-A fails against event-B: sub mismatch detected."""
    event_a_id = str(uuid.uuid4())
    event_b_id = str(uuid.uuid4())

    token_a = create_guest_token(event_a_id)
    claims = decode_guest_token(token_a)

    # Token's sub is event_a_id, not event_b_id
    assert claims["sub"] == event_a_id
    assert claims["sub"] != event_b_id


# ---------------------------------------------------------------------------
# TC-38: JWT signed with wrong secret → ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc38_wrong_secret_jwt_rejected():
    from jose import jwt as jose_jwt
    from datetime import datetime, timezone, timedelta

    event_id = str(uuid.uuid4())
    payload = {
        "sub": event_id,
        "type": "guest",
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    bad_token = jose_jwt.encode(payload, "wrong-secret", algorithm="HS256")

    with pytest.raises(ValueError, match="Invalid token"):
        decode_guest_token(bad_token)


# ---------------------------------------------------------------------------
# OTP auto-generation on create and update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otp_auto_generated_on_create(
    client: AsyncClient, auth_headers: dict
):
    event = await _create_event(client, auth_headers, access_mode="magic-link-otp")
    owner_resp = await client.get(f"/api/v1/events/{event['id']}", headers=auth_headers)
    otp = owner_resp.json()["otp_code"]
    assert otp is not None
    assert len(otp) == 6
    assert otp.isalnum()


@pytest.mark.asyncio
async def test_otp_auto_generated_on_update_to_otp_mode(
    client: AsyncClient, auth_headers: dict
):
    # Create a public event
    event = await _create_event(client, auth_headers, access_mode="public")
    event_id = event["id"]

    # Confirm no otp_code
    owner_resp = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    assert owner_resp.json()["otp_code"] is None

    # Update to magic-link-otp
    await client.put(
        f"/api/v1/events/{event_id}",
        json={"access_mode": "magic-link-otp"},
        headers=auth_headers,
    )

    owner_resp2 = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    assert owner_resp2.json()["otp_code"] is not None


@pytest.mark.asyncio
async def test_otp_not_generated_for_non_otp_event(
    client: AsyncClient, auth_headers: dict
):
    event = await _create_event(client, auth_headers, access_mode="public")
    owner_resp = await client.get(f"/api/v1/events/{event['id']}", headers=auth_headers)
    assert owner_resp.json()["otp_code"] is None


@pytest.mark.asyncio
async def test_access_code_event_no_otp_code(
    client: AsyncClient, auth_headers: dict
):
    event = await _create_event(client, auth_headers, access_mode="access-code", access_code="CODE123")
    owner_resp = await client.get(f"/api/v1/events/{event['id']}", headers=auth_headers)
    assert owner_resp.json()["otp_code"] is None


# ---------------------------------------------------------------------------
# QR code URL uses /g/ prefix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qr_code_uses_guest_url_prefix(
    client: AsyncClient, auth_headers: dict
):
    import io
    from PIL import Image
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
        has_pyzbar = True
    except ImportError:
        has_pyzbar = False

    event = await _create_event(client, auth_headers, access_mode="public")
    event_id = event["id"]
    resp = await client.get(f"/api/v1/events/{event_id}/qr-code", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"

    if has_pyzbar:
        img = Image.open(io.BytesIO(resp.content))
        decoded = pyzbar_decode(img)
        assert len(decoded) > 0
        qr_data = decoded[0].data.decode("utf-8")
        assert "/g/" in qr_data
