"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, events, albums, admin, guest_auth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("weddinglens")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Import purge job here to avoid circular imports at module level
    from app.services.purge import purge_expired_events

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        purge_expired_events,
        trigger="cron",
        hour=2,
        minute=0,
        id="purge_expired_events",
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


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
