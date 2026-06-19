# Tech Stack: WeddingLens
Last updated: 2026-06-19

## Services

| Service | Language | Framework | Key Dependencies |
|---------|----------|-----------|-----------------|
| backend | Python 3.12 | FastAPI + Pydantic v2 | SQLAlchemy 2 (async), AsyncPG, InsightFace, Qdrant client, Alembic, ruff |
| frontend | TypeScript | Next.js 14 (App Router) | Tailwind CSS, React 18, ESLint |

## Infrastructure

| Layer | Technology | Provider |
|-------|-----------|---------|
| Hosting | Single VM, 4-core / 16GB RAM | Self-hosted |
| Database | PostgreSQL 16 | Self-hosted on VM |
| Vector DB | Qdrant Cloud (free tier) | Qdrant Cloud |
| Cache | None (initial) | — |
| Queue | FastAPI BackgroundTasks (in-process) | — |
| Storage | Local SSD or external USB SSD | Self-hosted |

## CI/CD

- **CI:** GitHub Actions (not yet configured)
- **Artifact store:** TBD
- **Deploy:** Manual to single VM
