"""Tests for admin processing-failure-rate alerting (design D4, REQ-5a/5b/5c).

Covers:
  Rate calc     — 1h-window failure rate, photos outside the window excluded,
                   events with a zero denominator skipped.
  Threshold     — alert fires above ADMIN_FAILURE_RATE_THRESHOLD, not at/below it.
  Dedup         — repeat alert within ADMIN_ALERT_DEDUP_MINUTES suppressed;
                   resent once the dedup window has passed (injected clock, no sleep).
  Recipients    — every is_admin=true user's email; zero admins is a no-op.
  Resilience    — smtplib is always mocked; an SMTP failure does not raise out
                   of the job and does not mark the event as alerted (so the
                   next tick retries).
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.services import admin_alerts
from app.services.auth import hash_password

# Redirect admin_alerts' AsyncSessionLocal to the test SQLite session — same
# pattern as tests/test_face_pipeline.py.
from tests.conftest import TestSessionLocal

NOW = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)


def fixed_clock() -> datetime:
    return NOW


@pytest.fixture(autouse=True)
def patch_async_session_local():
    with patch("app.services.admin_alerts.AsyncSessionLocal", TestSessionLocal):
        yield


@pytest.fixture(autouse=True)
def clear_dedup_state():
    """Reset the in-process dedup dict before/after each test (module-level state)."""
    admin_alerts._last_alerted.clear()
    yield
    admin_alerts._last_alerted.clear()


@pytest_asyncio.fixture
async def owner(db) -> User:
    u = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def admin(db) -> User:
    u = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        password_hash=hash_password("pw"),
        is_admin=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def event(db, owner) -> Event:
    ev = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="Test Wedding",
        bride_name="A",
        groom_name="B",
        slug=f"evt-{uuid.uuid4().hex[:8]}",
        status="published",
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


async def _make_photos(db, event_id, status: str, count: int, last_processed_at: datetime) -> None:
    for _ in range(count):
        p = Photo(
            id=uuid.uuid4(),
            event_id=event_id,
            filename="f.jpg",
            storage_path="/tmp/f.jpg",
            file_size=100,
            processing_status=status,
            last_processed_at=last_processed_at,
        )
        db.add(p)
    await db.commit()


async def _seed_above_threshold(db, event_id) -> None:
    """8 complete + 2 failed in-window => rate = 0.2 > default 0.10 threshold."""
    in_window = NOW - timedelta(minutes=10)
    await _make_photos(db, event_id, "complete", 8, in_window)
    await _make_photos(db, event_id, "failed", 2, in_window)


# ---------------------------------------------------------------------------
# Rate calculation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_calculation_excludes_photos_outside_window(db, event):
    in_window = NOW - timedelta(minutes=10)
    outside_window = NOW - timedelta(minutes=90)

    # In window: 7 complete, 2 failed, 1 error -> rate = 3/10 = 0.3
    await _make_photos(db, event.id, "complete", 7, in_window)
    await _make_photos(db, event.id, "failed", 2, in_window)
    await _make_photos(db, event.id, "error", 1, in_window)

    # Outside window: 10 failed — must NOT be counted (would swing the rate to ~0.87 if it were).
    await _make_photos(db, event.id, "failed", 10, outside_window)

    rates = await admin_alerts._compute_failure_rates(NOW)

    assert len(rates) == 1
    got_event_id, got_name, rate = rates[0]
    assert got_event_id == event.id
    assert got_name == event.name
    assert rate == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_rate_skips_event_with_zero_denominator(db, event):
    """pending/processing photos never count toward the denominator."""
    await _make_photos(db, event.id, "pending", 3, NOW - timedelta(minutes=5))
    await _make_photos(db, event.id, "processing", 2, NOW - timedelta(minutes=5))

    rates = await admin_alerts._compute_failure_rates(NOW)
    assert rates == []


# ---------------------------------------------------------------------------
# Threshold — fires above, not at/below
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_fires_when_rate_exceeds_threshold(db, event, admin, monkeypatch):
    monkeypatch.setattr(admin_alerts.settings, "SMTP_HOST", "smtp.example.com")
    await _seed_above_threshold(db, event.id)

    with patch("app.services.admin_alerts.smtplib.SMTP") as mock_smtp:
        instance = mock_smtp.return_value.__enter__.return_value
        await admin_alerts.check_processing_failure_rates(clock=fixed_clock)

    mock_smtp.assert_called_once()
    instance.sendmail.assert_called_once()
    _from, recipients, _msg = instance.sendmail.call_args[0]
    assert admin.email in recipients
    assert event.id in admin_alerts._last_alerted


@pytest.mark.asyncio
async def test_alert_does_not_fire_at_threshold(db, event, admin, monkeypatch):
    monkeypatch.setattr(admin_alerts.settings, "SMTP_HOST", "smtp.example.com")
    in_window = NOW - timedelta(minutes=10)
    # rate = 1/10 = 0.10 exactly => must NOT fire (strictly greater than threshold).
    await _make_photos(db, event.id, "complete", 9, in_window)
    await _make_photos(db, event.id, "failed", 1, in_window)

    with patch("app.services.admin_alerts.smtplib.SMTP") as mock_smtp:
        await admin_alerts.check_processing_failure_rates(clock=fixed_clock)

    mock_smtp.assert_not_called()
    assert event.id not in admin_alerts._last_alerted


@pytest.mark.asyncio
async def test_alert_does_not_fire_below_threshold(db, event, admin, monkeypatch):
    monkeypatch.setattr(admin_alerts.settings, "SMTP_HOST", "smtp.example.com")
    in_window = NOW - timedelta(minutes=10)
    # rate = 0/10 = 0.0
    await _make_photos(db, event.id, "complete", 10, in_window)

    with patch("app.services.admin_alerts.smtplib.SMTP") as mock_smtp:
        await admin_alerts.check_processing_failure_rates(clock=fixed_clock)

    mock_smtp.assert_not_called()


# ---------------------------------------------------------------------------
# Dedup — in-process dict, injected clock (no sleep)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_suppresses_repeat_then_resends_after_window(db, event, admin, monkeypatch):
    monkeypatch.setattr(admin_alerts.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(admin_alerts.settings, "ADMIN_ALERT_DEDUP_MINUTES", 5)
    await _seed_above_threshold(db, event.id)

    clock_time = [NOW]

    def clock() -> datetime:
        return clock_time[0]

    with patch("app.services.admin_alerts.smtplib.SMTP") as mock_smtp:
        await admin_alerts.check_processing_failure_rates(clock=clock)
        assert mock_smtp.call_count == 1

        # 2 minutes later — still within the 5-minute dedup window: suppressed.
        clock_time[0] = NOW + timedelta(minutes=2)
        await admin_alerts.check_processing_failure_rates(clock=clock)
        assert mock_smtp.call_count == 1

        # 6 minutes after the first alert — dedup window has passed: resent.
        clock_time[0] = NOW + timedelta(minutes=6)
        await admin_alerts.check_processing_failure_rates(clock=clock)
        assert mock_smtp.call_count == 2


# ---------------------------------------------------------------------------
# Recipients — every is_admin=true email; zero admins is a no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recipients_are_every_admin_email(db, event, monkeypatch):
    monkeypatch.setattr(admin_alerts.settings, "SMTP_HOST", "smtp.example.com")
    admin1 = User(
        id=uuid.uuid4(), email="admin1@example.com",
        password_hash=hash_password("pw"), is_admin=True,
    )
    admin2 = User(
        id=uuid.uuid4(), email="admin2@example.com",
        password_hash=hash_password("pw"), is_admin=True,
    )
    non_admin = User(
        id=uuid.uuid4(), email="notadmin@example.com",
        password_hash=hash_password("pw"), is_admin=False,
    )
    db.add_all([admin1, admin2, non_admin])
    await db.commit()

    await _seed_above_threshold(db, event.id)

    with patch("app.services.admin_alerts.smtplib.SMTP") as mock_smtp:
        instance = mock_smtp.return_value.__enter__.return_value
        await admin_alerts.check_processing_failure_rates(clock=fixed_clock)

    _from, recipients, _msg = instance.sendmail.call_args[0]
    assert set(recipients) == {"admin1@example.com", "admin2@example.com"}
    assert "notadmin@example.com" not in recipients


@pytest.mark.asyncio
async def test_zero_admins_is_a_noop(db, event, monkeypatch):
    """No is_admin=true users at all => log and skip, no crash."""
    monkeypatch.setattr(admin_alerts.settings, "SMTP_HOST", "smtp.example.com")
    await _seed_above_threshold(db, event.id)

    with patch("app.services.admin_alerts.smtplib.SMTP") as mock_smtp:
        await admin_alerts.check_processing_failure_rates(clock=fixed_clock)  # must not raise

    mock_smtp.assert_not_called()
    assert event.id not in admin_alerts._last_alerted


# ---------------------------------------------------------------------------
# Resilience — smtplib always mocked; SMTP failure never raises out of the job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_survives_smtp_failure(db, event, admin, monkeypatch):
    monkeypatch.setattr(admin_alerts.settings, "SMTP_HOST", "smtp.example.com")
    await _seed_above_threshold(db, event.id)

    with patch(
        "app.services.admin_alerts.smtplib.SMTP",
        side_effect=OSError("connection refused"),
    ):
        # Must complete without raising.
        await admin_alerts.check_processing_failure_rates(clock=fixed_clock)

    # Send failed — dedup state must not be marked, so the next tick retries.
    assert event.id not in admin_alerts._last_alerted


@pytest.mark.asyncio
async def test_smtp_unconfigured_skips_send_without_crashing(db, event, admin, monkeypatch):
    """SMTP_HOST empty (dev/test default) — logs and skips, never connects."""
    monkeypatch.setattr(admin_alerts.settings, "SMTP_HOST", "")
    await _seed_above_threshold(db, event.id)

    with patch("app.services.admin_alerts.smtplib.SMTP") as mock_smtp:
        await admin_alerts.check_processing_failure_rates(clock=fixed_clock)

    mock_smtp.assert_not_called()
    # Treated as delivered for dedup purposes (matches design's "would have sent" logging).
    assert event.id in admin_alerts._last_alerted
