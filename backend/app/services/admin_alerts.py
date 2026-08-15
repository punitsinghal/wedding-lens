"""APScheduler job: automated processing-failure-rate alerting (design D4).

Runs every 5 minutes (REQ-5c), alongside the existing `retry_failed_photos`
job (`app/services/retry.py`) — same registration style, same interval.

For each event with any `complete`/`failed`/`error` photo whose
`last_processed_at` falls within the trailing
`ADMIN_FAILURE_RATE_WINDOW_MINUTES` window, computes:

    rate = (failed + error) / (failed + error + complete)

If `rate > ADMIN_FAILURE_RATE_THRESHOLD`, emails every `is_admin=true` user —
see ADR `docs/decisions/2026-08-15-admin-alert-in-process-dedup.md`.

Dedup state is an in-process `dict[event_id, last_alerted_at]`, mirroring the
existing in-process, per-key, time-windowed pattern already used by
`SearchRateLimiter` (`app/services/search_rate_limit.py`) and
`GuestRateLimiter` (`app/services/guest_auth.py`). It resets on backend
restart — an accepted fail-open trade-off (ADR, same as those precedents).

The whole per-tick body is wrapped in defensive error handling (matching
`retry.py`/`purge.py`'s style) so a single bad event, a DB hiccup, or an SMTP
failure never permanently kills the APScheduler job.
"""

from __future__ import annotations

import logging
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Callable

from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User

logger = logging.getLogger("weddinglens.admin_alerts")

# Photo states that count toward the failure-rate denominator (D4).
_COUNTED_STATUSES = ("complete", "failed", "error")

# event_id -> last-alerted-at (in-process dedup state, D4 / ADR 2026-08-15).
# Module-level so it survives across scheduler ticks within one process but
# resets on restart (accepted fail-open — see ADR "Consequences").
_last_alerted: dict[uuid.UUID, datetime] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def check_processing_failure_rates(
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Entry point for the APScheduler 5-minute job (REQ-5c).

    `clock` is injectable for tests (defaults to real UTC now) — same
    "inject a clock, don't sleep" pattern already used by
    `SearchRateLimiter` (`app/services/search_rate_limit.py`).

    Never raises: a query error or a per-event send failure is logged and the
    job returns normally so APScheduler keeps ticking every 5 minutes.
    """
    now = (clock or _utcnow)()

    try:
        rates = await _compute_failure_rates(now)
    except Exception:
        logger.exception('{"event": "admin_alert_query_error"}')
        return

    for event_id, event_name, rate in rates:
        if rate <= settings.ADMIN_FAILURE_RATE_THRESHOLD:
            continue
        try:
            await _maybe_alert(event_id, event_name, rate, now)
        except Exception:
            logger.exception(
                '{"event": "admin_alert_event_error", "event_id": "%s"}',
                event_id,
            )


async def _compute_failure_rates(
    now: datetime,
) -> list[tuple[uuid.UUID, str, float]]:
    """Per-event (complete/failed/error) counts over the trailing window.

    GROUP BY event_id, processing_status over `Photo.last_processed_at` —
    same shape as `admin_stats.get_platform_health`'s 24h platform-wide query,
    but per-event and over `ADMIN_FAILURE_RATE_WINDOW_MINUTES` (1h default).
    Skips events where the (failed + error + complete) denominator is 0.
    """
    window_start = now - timedelta(minutes=settings.ADMIN_FAILURE_RATE_WINDOW_MINUTES)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Photo.event_id, Photo.processing_status, func.count(Photo.id))
            .where(
                Photo.last_processed_at > window_start,
                Photo.processing_status.in_(_COUNTED_STATUSES),
            )
            .group_by(Photo.event_id, Photo.processing_status)
        )
        counts: dict[uuid.UUID, dict[str, int]] = {}
        for event_id, status_val, cnt in result.all():
            counts.setdefault(
                event_id, {"complete": 0, "failed": 0, "error": 0}
            )[status_val] = cnt

        if not counts:
            return []

        names_result = await db.execute(
            select(Event.id, Event.name).where(Event.id.in_(counts.keys()))
        )
        names = {eid: name for eid, name in names_result.all()}

    rates: list[tuple[uuid.UUID, str, float]] = []
    for event_id, c in counts.items():
        denom = c["complete"] + c["failed"] + c["error"]
        if denom == 0:
            continue
        rate = (c["failed"] + c["error"]) / denom
        rates.append((event_id, names.get(event_id, str(event_id)), rate))
    return rates


async def _maybe_alert(
    event_id: uuid.UUID, event_name: str, rate: float, now: datetime
) -> None:
    """Dedup-check, then send if not recently alerted (D4)."""
    dedup_window = timedelta(minutes=settings.ADMIN_ALERT_DEDUP_MINUTES)
    last = _last_alerted.get(event_id)
    if last is not None and now - last < dedup_window:
        logger.info(
            '{"event": "admin_alert_deduped", "event_id": "%s"}', event_id
        )
        return

    emails = await _get_admin_emails()
    if not emails:
        logger.info(
            '{"event": "admin_alert_no_admins", "event_id": "%s"}', event_id
        )
        return

    try:
        _send_alert_email(event_id, event_name, rate, emails)
    except Exception:
        logger.exception(
            '{"event": "admin_alert_smtp_error", "event_id": "%s"}', event_id
        )
        # Do not update dedup state — retry on the next tick since the
        # send itself failed (worst case per the ADR: a duplicate email is
        # cheap, a missed one is not).
        return

    _last_alerted[event_id] = now


async def _get_admin_emails() -> list[str]:
    """All `is_admin=true` users' emails, queried fresh at alert time (D4/ADR)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User.email).where(User.is_admin.is_(True)))
        return [row[0] for row in result.all()]


def _monitor_url(event_id: uuid.UUID) -> str:
    """Link to the affected event's admin monitor page (REQ-5b).

    Matches the dynamic-route convention already used elsewhere in the
    frontend (`/events/[eventId]`, `/g/[slug]`) applied under `/admin`.
    """
    return f"{settings.FRONTEND_URL}/admin/events/{event_id}"


def _send_alert_email(
    event_id: uuid.UUID, event_name: str, rate: float, emails: list[str]
) -> None:
    """Send one alert email to all admin recipients via stdlib smtplib.

    If `SMTP_HOST` is unconfigured (dev/test default), logs that the alert
    would have been sent and returns without attempting a connection — this
    keeps the job safe to run every 5 minutes indefinitely in environments
    with no SMTP relay configured.
    """
    subject = f"[WeddingLens] Processing failure rate alert — {event_name}"
    body = (
        f"Event: {event_name}\n"
        f"Event ID: {event_id}\n"
        f"Processing failure rate: {rate:.1%} over the last "
        f"{settings.ADMIN_FAILURE_RATE_WINDOW_MINUTES} minutes "
        f"(threshold: {settings.ADMIN_FAILURE_RATE_THRESHOLD:.0%}).\n\n"
        f"Monitor this event: {_monitor_url(event_id)}\n"
    )

    if not settings.SMTP_HOST:
        logger.info(
            '{"event": "admin_alert_smtp_unconfigured", "event_id": "%s", '
            '"recipients": %d}',
            event_id,
            len(emails),
        )
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = ", ".join(emails)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_USER:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM, emails, msg.as_string())

    logger.info(
        '{"event": "admin_alert_sent", "event_id": "%s", "recipients": %d}',
        event_id,
        len(emails),
    )
