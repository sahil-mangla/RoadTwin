"""Shared pytest fixtures for the backend test suite.

Per 01-RESEARCH.md's "Note on SQLite fallback (D-04)", this phase's suite
runs against the docker-compose Postgres+PostGIS service rather than
splitting fixtures per test — geometry columns and PostGIS extensions have
no meaningful SQLite equivalent.
"""

from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from backend.core.config import settings

ALEMBIC_INI_PATH = Path(__file__).resolve().parents[2] / "backend" / "alembic.ini"


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    """The sync DSN for the docker-compose postgres service.

    Skips the test session (rather than erroring) when the service is not
    reachable, so a developer without Docker running gets a clear skip.
    """
    dsn = settings.database_url_sync
    try:
        conn = psycopg.connect(dsn.replace("postgresql+psycopg://", "postgresql://"))
        conn.close()
    except Exception:
        pytest.skip("docker-compose postgres service not reachable")
    return dsn


@pytest.fixture(scope="session")
def alembic_config(postgres_dsn: str):
    """Builds an Alembic Config pointed at backend/alembic.ini.

    Guarded with a skip when the ini file does not exist yet, so this
    fixture does not break collection before Plan 02 creates it.
    """
    if not ALEMBIC_INI_PATH.exists():
        pytest.skip("backend/alembic.ini does not exist yet (created in Plan 02)")

    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI_PATH))
    cfg.set_main_option("sqlalchemy.url", postgres_dsn)
    return cfg


@pytest.fixture(scope="session")
def migrated_database(alembic_config):
    """Runs the full migration cycle once per test session, then yields."""
    from alembic import command

    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    yield


@pytest_asyncio.fixture(scope="session")
async def async_engine():
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(migrated_database, async_engine):
    """An AsyncSession bound to a connection inside an outer transaction.

    The outer transaction is rolled back on teardown so tests never leak
    rows into the shared docker-compose database.
    """
    connection = await async_engine.connect()
    outer_transaction = await connection.begin()

    async_session = AsyncSession(bind=connection, expire_on_commit=False)

    try:
        yield async_session
    finally:
        await async_session.close()
        await outer_transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def client(session):
    """An httpx.AsyncClient bound to the app through an ASGI transport.

    Now that Plan 02 has created `backend.main`, `session` can be a normal
    fixture dependency again. An earlier revision pulled `session` in
    lazily via `request.getfixturevalue(...)` specifically so a
    pre-Plan-02 run would fail with a plain `ModuleNotFoundError:
    backend.main` (the correct RED reason) instead of an unrelated
    Alembic/migration skip further down the chain -- that trick is no
    longer needed and was also incompatible with pytest-asyncio's fixture
    runner (`request.getfixturevalue` on an async fixture from inside
    another async fixture raises "Runner.run() cannot be called from a
    running event loop").
    """
    import httpx

    from backend.main import app
    from backend.db.session import get_session

    async def _override_get_session():
        yield session

    app.dependency_overrides[get_session] = _override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.pop(get_session, None)
