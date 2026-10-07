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


@pytest.fixture(scope="session")
def minio_available():
    """A bucket-bootstrapped `minio.Minio` client, or a session skip.

    Byte-for-byte the same skip-rather-than-error shape as `postgres_dsn`
    above, so a developer without Docker running gets a clear skip instead
    of a confusing connection error. `minio` is imported lazily inside the
    fixture body (not at module scope) so test collection still works in
    an environment where the package is absent.
    """
    import minio as minio_sdk

    client = minio_sdk.Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    try:
        exists = client.bucket_exists(settings.minio_bucket)
        if not exists:
            client.make_bucket(settings.minio_bucket)
    except Exception:
        pytest.skip("docker-compose minio service not reachable")
    return client


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


@pytest.fixture
def jpeg_bytes() -> bytes:
    """A small valid in-memory JPEG -- no fixture file on disk."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def png_bytes() -> bytes:
    """A small valid in-memory PNG -- no fixture file on disk."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (128, 128, 128)).save(buf, format="PNG")
    return buf.getvalue()


@pytest_asyncio.fixture
async def client_isolated_sessions(migrated_database):
    """An httpx.AsyncClient where each request gets its own real DB session.

    The `client` fixture above shares one `AsyncSession` on one connection
    inside an outer transaction -- not safe under `asyncio.gather`, since a
    single `AsyncSession` is not concurrency-safe. This fixture instead
    builds a throwaway engine (own connection pool, `NullPool`) and session
    factory scoped to this one test function, so concurrent requests each
    get a real, independent connection and commit for real.

    A fresh, function-scoped engine (rather than the app's shared
    module-level `backend.db.session.engine`) is deliberate: pytest-asyncio
    gives each test function its own event loop by default, and an
    asyncpg connection created under one test's loop cannot be reused from
    another test's loop -- reusing the app's long-lived pooled engine
    across tests raised "Future attached to a different loop" once a
    second test also exercised this fixture.

    Because this fixture commits for real, every test that uses it is
    responsible for deleting the rows it creates (in a `finally` block).
    """
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from backend.db.session import get_session
    from backend.main import app

    isolated_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    isolated_session_factory = async_sessionmaker(isolated_engine, expire_on_commit=False)

    async def _override_get_session():
        async with isolated_session_factory() as real_session:
            try:
                yield real_session
                await real_session.commit()
            except Exception:
                await real_session.rollback()
                raise

    app.dependency_overrides[get_session] = _override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.pop(get_session, None)
    await isolated_engine.dispose()
