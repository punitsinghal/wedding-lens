"""Tests for the startup schema assertion in app.main._assert_schema_current."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.main import _assert_schema_current


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine_mock(version_num: str | None, table_exists: bool = True):
    """Return an async context-manager mock for create_async_engine.

    Parameters
    ----------
    version_num:
        The value to return from ``SELECT version_num FROM alembic_version``.
        ``None`` simulates an empty table (no row).
    table_exists:
        When ``False`` the execute call raises an exception, simulating the
        absence of the ``alembic_version`` table.
    """
    # Row mock
    if table_exists:
        row = (version_num,) if version_num is not None else None
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        conn_mock = AsyncMock()
        conn_mock.execute = AsyncMock(return_value=result_mock)
    else:
        conn_mock = AsyncMock()
        conn_mock.execute = AsyncMock(side_effect=Exception("no such table: alembic_version"))

    # The engine's connect() is an async context manager
    connect_ctx = AsyncMock()
    connect_ctx.__aenter__ = AsyncMock(return_value=conn_mock)
    connect_ctx.__aexit__ = AsyncMock(return_value=False)

    engine_mock = MagicMock()
    engine_mock.connect = MagicMock(return_value=connect_ctx)
    engine_mock.dispose = AsyncMock()

    return engine_mock


def _make_script_mock(head: str):
    """Return a minimal ScriptDirectory mock with a fixed head revision chain.

    The chain used here is: 001 → 002 (head).
    """
    rev_001 = MagicMock()
    rev_001.revision = "001"
    rev_001.down_revision = None

    rev_002 = MagicMock()
    rev_002.revision = "002"
    rev_002.down_revision = "001"

    revisions = {"001": rev_001, "002": rev_002}

    script_mock = MagicMock()
    script_mock.get_current_head.return_value = head
    script_mock.get_revision = MagicMock(side_effect=lambda rev: revisions.get(rev))
    return script_mock


# ---------------------------------------------------------------------------
# Happy path: DB at head → no error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_current_no_error():
    """When DB revision matches head, _assert_schema_current completes silently."""
    engine_mock = _make_engine_mock(version_num="002")
    script_mock = _make_script_mock(head="002")

    with (
        patch("app.main.create_async_engine", return_value=engine_mock),
        patch("app.main.ScriptDirectory.from_config", return_value=script_mock),
        patch("app.main.AlembicConfig"),
    ):
        # Should not raise
        await _assert_schema_current()


# ---------------------------------------------------------------------------
# Stale migration: DB at 001, head is 002 → RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_out_of_date_raises_runtime_error():
    """When DB is behind head, RuntimeError is raised with upgrade instruction."""
    engine_mock = _make_engine_mock(version_num="001")
    script_mock = _make_script_mock(head="002")

    with (
        patch("app.main.create_async_engine", return_value=engine_mock),
        patch("app.main.ScriptDirectory.from_config", return_value=script_mock),
        patch("app.main.AlembicConfig"),
    ):
        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            await _assert_schema_current()


@pytest.mark.asyncio
async def test_schema_out_of_date_error_mentions_revisions():
    """Error message names the applied and expected head revisions."""
    engine_mock = _make_engine_mock(version_num="001")
    script_mock = _make_script_mock(head="002")

    with (
        patch("app.main.create_async_engine", return_value=engine_mock),
        patch("app.main.ScriptDirectory.from_config", return_value=script_mock),
        patch("app.main.AlembicConfig"),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            await _assert_schema_current()

    msg = str(exc_info.value)
    assert "001" in msg, "Applied revision should appear in error message"
    assert "002" in msg, "Expected head revision should appear in error message"
    assert "alembic upgrade head" in msg


# ---------------------------------------------------------------------------
# Missing alembic_version table → RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_alembic_version_table_raises():
    """If alembic_version doesn't exist, RuntimeError is raised."""
    engine_mock = _make_engine_mock(version_num=None, table_exists=False)
    script_mock = _make_script_mock(head="002")

    with (
        patch("app.main.create_async_engine", return_value=engine_mock),
        patch("app.main.ScriptDirectory.from_config", return_value=script_mock),
        patch("app.main.AlembicConfig"),
    ):
        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            await _assert_schema_current()
