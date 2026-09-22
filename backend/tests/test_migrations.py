"""Migration round-trip integration test (Task 1, SCHM-01/SCHM-04).

Proves the Alembic environment is wired correctly against the live
compose Postgres+PostGIS database -- not merely that a migration file
exists, but that it applies, survives a full down-and-up round trip with
no drift, and produces the schema shapes the rest of this phase depends
on.
"""

import psycopg
import pytest


@pytest.mark.postgis
def test_migration_round_trips_cleanly(alembic_config, postgres_dsn):
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    conn = psycopg.connect(postgres_dsn.replace("postgresql+psycopg://", "postgresql://"))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = 'report'"
            )
            assert cur.fetchone()[0] == 1

            cur.execute("SELECT postgis_version();")
            assert cur.fetchone()[0] is not None
    finally:
        conn.close()


@pytest.mark.postgis
def test_migration_head_matches_model_metadata_no_drift(alembic_config, postgres_dsn):
    """Asserts `alembic upgrade head` leaves zero autogenerate drift.

    A non-empty diff here would mean the hand-authored migration in
    `0001_initial_report_schema.py` has silently fallen out of sync with
    `backend/models/report.py` -- e.g. a column type, nullability, or
    server default mismatch.
    """
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext
    from geoalchemy2 import alembic_helpers
    from sqlalchemy import create_engine

    from backend.models import Base

    command.upgrade(alembic_config, "head")

    # The `postgis/postgis` image's `search_path` includes the `tiger` and
    # `topology` schemas (its geocoder/topology extensions), so a
    # schema-unaware reflection sees dozens of extension-owned tables that
    # were never part of `Base.metadata`. `alembic_helpers.include_object`
    # alone only filters a handful of PostGIS core table-name patterns
    # (spatial_ref_sys, geometry_columns, ...) -- it does not know about
    # `tiger`/`topology`. Layer an explicit "only compare our own tables"
    # filter on top, so the diff reflects genuine drift between this
    # migration and `Report`, not PostGIS's own bundled schema.
    own_table_names = set(Base.metadata.tables.keys())

    def include_object(object_, name, type_, reflected, compare_to):
        if type_ == "table" and reflected and name not in own_table_names:
            return False
        return alembic_helpers.include_object(object_, name, type_, reflected, compare_to)

    sync_url = postgres_dsn
    engine = create_engine(sync_url)
    try:
        with engine.connect() as connection:
            migration_context = MigrationContext.configure(
                connection,
                opts={"include_object": include_object},
            )
            diff = compare_metadata(migration_context, Base.metadata)
    finally:
        engine.dispose()

    assert diff == [], f"Unexpected autogenerate drift: {diff}"
