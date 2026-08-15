# ADR: Processing-Failure Alerts — In-Process Dedup State, Plain SMTP, No Third-Party Alerting

**Date:** 2026-08-15
**Status:** Accepted
**Deciders:** Engineering

---

## Context

The Admin Platform feature (REQ-5a→c) requires an automated email alert when an event's face
processing failure rate exceeds 10% in a rolling 1-hour window, checked at least every 5 minutes,
with repeat alerts for the same event suppressed for at least 1 hour while the condition persists
(NFR-4). Requirements explicitly rule out third-party alerting integrations (PagerDuty, Slack,
OpsGenie, webhooks) — email only, no SDK dependency.

Two things needed a decision:
1. **Where does "don't alert on the same event twice within an hour" state live?**
2. **Who receives the email, and how is it sent?**

Precedent already exists in this codebase for exactly this shape of problem: `GuestRateLimiter`
(`backend/app/services/guest_auth.py:56`) and the search rate limiter (ADR
`2026-06-22-guest-search-in-process-rate-limiter`) both use in-process, per-key sliding-window
state for "don't let X happen too often," with an explicit, accepted trade-off that state resets on
backend restart.

## Decision

**Dedup state:** an in-process `dict[event_id, last_alerted_at]` inside the new
`check_processing_failure_rates` job module. Before sending an alert for an event, check whether
`now() - dict.get(event_id, epoch) < 1 hour`; if so, skip. Resets on restart — a brief fail-open
identical in spirit to the search rate limiter's accepted trade-off.

**Recipients:** every `User` row with `is_admin = true`, queried at alert time — not a separate
`ADMIN_ALERT_EMAIL` config value. This means the recipient list can never drift from who is
actually an admin; promoting/demoting an admin (even via the manual SQL update NFR-5 already
specifies for MVP) automatically changes who gets alerted, with no second place to update.

**Delivery:** stdlib `smtplib` against an operator-configured SMTP relay (new settings: `SMTP_HOST`,
`SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`), following the same `.env`/`config.py`
pattern as every other credential in this codebase. No alerting SDK, no webhook fan-out.

---

## Options Considered

| Option | New infra | Survives restart | Fit |
|--------|-----------|-------------------|-----|
| **In-process dedup dict + plain SMTP (selected)** | None | No (fail-open) | Matches existing rate-limiter/favourites convention; zero new infra |
| Postgres-backed dedup table | One new table + migration | Yes | NFR-4 explicitly allows this, but it's more moving parts for a control whose worst-case failure mode (one duplicate email within an hour after a restart) is cosmetic, not a compliance or safety issue |
| Third-party alerting (PagerDuty/OpsGenie/webhook) | External service + credentials | Yes | Explicitly ruled out by requirements (Out of Scope) — single-VM MVP, no external alerting dependency wanted |
| Config-driven single admin email | None | Yes | Rejected: a second place that can drift from the actual `is_admin` roster; querying `User` at send time is no more expensive and can't go stale |

---

## Consequences

**Positive:**
- Zero new infrastructure; consistent with two other in-process, time-windowed controls already in
  this codebase (guest rate limiting, favourites).
- Recipient list is always correct by construction — no separate admin-email setting to keep in
  sync with the `User.is_admin` roster.

**Negative:**
- A backend restart within the 1-hour dedup window can produce one duplicate alert email for a
  still-failing event. Acceptable: the cost of a duplicate email is far lower than the cost of a
  missed one, and this is a notification control, not a safety interlock.
- Not correct across multiple backend instances (dedup state is per-process). Moot today
  (single-VM deployment); if the deployment ever goes multi-instance, this is the trigger to move
  dedup state to Postgres or Redis — same upgrade path already documented for the search rate
  limiter.

**Convention for future code:**
- A new "don't repeat this notification more than once per window" control defaults to an
  in-process, per-key dict on a single-VM deployment. Move to a persisted store only when either
  (a) the miss/duplicate cost is asymmetric enough that fail-open is unacceptable, or (b) the
  deployment goes multi-instance.

---

## References
- `docs/features/admin-platform/requirements.md` — REQ-5a→c, NFR-4
- `docs/features/admin-platform/design.md` — Decision D4
- `docs/decisions/2026-06-22-guest-search-in-process-rate-limiter.md` — the precedent this mirrors
- `docs/decisions/2026-06-20-favourites-in-process-store.md` — a second precedent for in-process, per-session state
- `backend/app/services/retry.py` — the existing 5-minute APScheduler job this new job runs alongside
