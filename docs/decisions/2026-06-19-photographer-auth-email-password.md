# ADR: Photographer Authentication — Email + Password
Date: 2026-06-19
Status: accepted

## Context

Photographers and event owners need to log in to upload photos, configure events, and generate guest QR codes. Two approaches were considered: email+password with JWT, or a third-party OAuth provider (Google, GitHub, etc.).

## Decision

Use email + password authentication. The backend hashes passwords with bcrypt, issues a signed JWT on successful login, and expects a `Bearer <token>` header on all authenticated requests.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Email + password / JWT (chosen) | No external dependency; full control over auth flow; works offline on a local VM | Must implement password reset, hashing, and token lifecycle |
| Google OAuth | No password management; simpler for users with Google accounts | Requires internet connectivity and Google credentials config; adds external dependency to a system designed to run self-hosted |

## Consequences

- The backend must implement: password hashing (bcrypt), JWT issuance and validation, token expiry, and a password-reset flow (email or admin reset).
- Because the system targets single-VM self-hosted deployment (see ADR `2026-06-19-single-vm-local-storage-deployment.md`), avoiding an OAuth provider dependency keeps the system operable without internet access.
- If the platform later becomes a multi-tenant SaaS, OAuth can be added as an additional login method without replacing this flow.

## References

- `docs/architecture/constraints.md` — Cross-cutting Standards → Auth
- `docs/decisions/2026-06-19-single-vm-local-storage-deployment.md`
