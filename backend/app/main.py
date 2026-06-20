"""FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.routers import auth, events, albums, admin, guest_auth
from app.routers.gallery import router as gallery_router
from app.routers.photo_actions import router as photo_actions_router
from app.routers.photos import router as photos_router, status_router as face_status_router
from app.routers.search import router as search_router
from app.routers.share import router as share_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("weddinglens")


async def _assert_schema_current() -> None:
    """Fail fast if the DB migration is behind the Alembic head revision.

    Reads the applied revision from ``alembic_version`` and compares it to the
    head defined by the scripts on disk.  Raises ``RuntimeError`` if they do
    not match so the process exits before accepting traffic.
    """
    from app.config import settings

    # Locate alembic.ini relative to this file's package root (backend/).
    _here = os.path.dirname(__file__)
    alembic_ini = os.path.join(_here, "..", "alembic.ini")
    alembic_ini = os.path.normpath(alembic_ini)

    cfg = AlembicConfig(alembic_ini)
    script = ScriptDirectory.from_config(cfg)
    expected_head: str = script.get_current_head()  # type: ignore[assignment]

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    try:
        async with engine.connect() as conn:
            try:
                result = await conn.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
                row = result.fetchone()
            except Exception:
                raise RuntimeError(
                    "alembic_version table does not exist. "
                    "Run `alembic upgrade head` before starting the server."
                )
    finally:
        await engine.dispose()

    applied: str | None = row[0] if row else None

    if applied != expected_head:
        # Collect unapplied revisions for a helpful error message.
        unapplied = []
        rev = script.get_revision(expected_head)
        while rev is not None and rev.revision != applied:
            unapplied.insert(0, rev.revision)
            rev = script.get_revision(rev.down_revision)  # type: ignore[arg-type]

        unapplied_str = ", ".join(unapplied) if unapplied else "(unknown)"
        msg = (
            f"Database schema is out of date. "
            f"Applied: {applied}. "
            f"Expected head: {expected_head}. "
            f"Unapplied migrations: {unapplied_str}. "
            f"Run `alembic upgrade head` before starting the server."
        )
        logger.error(msg)
        raise RuntimeError(msg)

    logger.info('{"event": "schema_ok", "revision": "%s"}', applied)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Import jobs here to avoid circular imports at module level
    from app.services.purge import purge_expired_events
    from app.services.retry import retry_failed_photos

    await _assert_schema_current()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        purge_expired_events,
        trigger="cron",
        hour=2,
        minute=0,
        id="purge_expired_events",
        replace_existing=True,
    )
    scheduler.add_job(
        retry_failed_photos,
        trigger="interval",
        minutes=5,
        id="retry_failed_photos",
        replace_existing=True,
    )
    scheduler.start()
    logger.info('{"event": "scheduler_started"}')

    yield

    scheduler.shutdown(wait=False)
    logger.info('{"event": "scheduler_stopped"}')


app = FastAPI(
    title="WeddingLens API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(events.router)
app.include_router(albums.router)
app.include_router(admin.router)
app.include_router(guest_auth.router)
app.include_router(photos_router)
app.include_router(face_status_router)
app.include_router(gallery_router)
app.include_router(search_router)
app.include_router(photo_actions_router)
app.include_router(share_router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
