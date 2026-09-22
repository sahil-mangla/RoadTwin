"""Alembic environment wired for the sync driver and GeoAlchemy2 autogenerate.

Two pitfalls this file exists to avoid (01-RESEARCH.md):

- Pitfall 2: Alembic's default type-comparison logic does not understand
  PostGIS geometry column semantics (SRID, dimension, spatial index) --
  `geoalchemy2.alembic_helpers.include_object` / `.writer` / `.render_item`
  must all three be wired into both `run_migrations_online()` and
  `run_migrations_offline()`, or autogenerate mishandles geometry columns.
- Pitfall 3: Alembic's `engine_from_config()` builds a *synchronous*
  engine -- it cannot drive the app's async-only database driver. This
  file reads `settings.database_url_sync` (a `postgresql+psycopg://` URL)
  exclusively; the app's async driver URL must never reach Alembic.
"""

from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import engine_from_config, pool

from backend.core.config import settings
from backend.models import Base

# Alembic Config object, providing access to values within alembic.ini.
config = context.config

# Interpret the config file for Python logging, unless run in a context
# (e.g. a test harness) that has already configured logging itself.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `target_metadata` drives autogenerate -- Alembic diffs the live database
# against this metadata object. Extended in Plan 04 as the other six
# entities are added to `backend/models/__init__.py`.
target_metadata = Base.metadata

# The app's async database URL must never reach Alembic (Pitfall 3) --
# only `database_url_sync` (`postgresql+psycopg://`) is used here.
config.set_main_option("sqlalchemy.url", settings.database_url_sync)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine, though an
    Engine is acceptable here as well. By skipping the Engine creation we
    don't even need a DBAPI to be available. Calls to context.execute()
    here emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=alembic_helpers.include_object,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Builds a sync engine (psycopg, not the app's async driver -- Pitfall 3)
    and associates a connection with the migration context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=alembic_helpers.include_object,
            process_revision_directives=alembic_helpers.writer,
            render_item=alembic_helpers.render_item,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
