"""
Test configuration.

Uses an in-memory SQLite database via aiosqlite so tests require no
external infrastructure. SQLite does not natively support UUID columns the
same way PostgreSQL does, so models use String(36) equivalently via SQLAlchemy's
TypeDecorator when needed. Because we use UUID(as_uuid=True) from the PostgreSQL
dialect, we override the engine dialect in conftest by using
render_as_batch=True and a synchronous SQLite URL so SQLAlchemy maps GUID columns
to VARCHAR(36) automatically.

The override DATABASE_URL is set via environment variable before imports.
"""

import os
import uuid

# Point the app at an in-memory SQLite database for tests.
# Must be set BEFORE app modules are imported.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest"
os.environ["FRONTEND_URL"] = "http://localhost:3000"
os.environ["STORAGE_PATH"] = "/tmp/weddinglens-test"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.dependencies import get_db
from app.main import app
from app.models.user import User
from app.services.auth import create_access_token, hash_password

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# Override get_db to use test session
# ---------------------------------------------------------------------------

async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture
async def regular_user(db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash=hash_password("password123"),
        is_admin=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        password_hash=hash_password("adminpass"),
        is_admin=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
def auth_headers(regular_user: User) -> dict:
    token = create_access_token(str(regular_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_user: User) -> dict:
    token = create_access_token(str(admin_user.id))
    return {"Authorization": f"Bearer {token}"}
