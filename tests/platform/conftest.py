"""Fixtures for platform tests that need real Postgres (RLS, and anything else that
SQLite can't emulate). See CLAUDE.md: "new platform/HR code that uses Postgres-only
features (RLS, ltree) is tested against Postgres, not SQLite."

These tests are marked `postgres` (see pytest.ini) and skip themselves cleanly when
no Postgres is reachable, so `pytest tests/` still passes with SQLite alone. Point
PLATFORM_TEST_DATABASE_URL at a real database to run them (docker-compose's `db`
service, on host port 5433, works out of the box).
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.modules.platform.db import set_tenant_context

REPO_ROOT = Path(__file__).resolve().parents[2]

PG_URL = os.environ.get(
    "PLATFORM_TEST_DATABASE_URL",
    "postgresql://postgres:password@localhost:5433/astrynox_platform_test",
)

RLS_TEST_ROLE = "platform_rls_test_role"


def _pg_reachable(url: str) -> bool:
    try:
        conn = psycopg2.connect(url, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tests/platform/" in str(item.fspath).replace(os.sep, "/") or "tests\\platform\\" in str(item.fspath):
            item.add_marker(pytest.mark.postgres)


@pytest.fixture(scope="session")
def pg_engine():
    if not _pg_reachable(PG_URL):
        pytest.skip(f"Postgres not reachable at {PG_URL} — set PLATFORM_TEST_DATABASE_URL to run platform tests")

    env = {
        **os.environ,
        "ALEMBIC_DATABASE_URL": PG_URL,
        "DATABASE_URL": os.environ.get("DATABASE_URL", "sqlite:///./test_billflow.db"),
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(REPO_ROOT),
        env=env,
        check=True,
    )

    engine = create_engine(PG_URL, future=True)
    with engine.connect() as conn:
        conn.execute(text(
            f"""
            DO $$
            BEGIN
               IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{RLS_TEST_ROLE}') THEN
                  CREATE ROLE {RLS_TEST_ROLE} NOLOGIN;
               END IF;
            END$$;
            """
        ))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {RLS_TEST_ROLE}"))
        conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {RLS_TEST_ROLE}"))
        conn.commit()

    yield engine
    engine.dispose()


@pytest.fixture()
def pg_conn(pg_engine):
    """A connection with its own transaction, rolled back after the test — keeps
    platform tests isolated from each other without truncating shared tables."""
    conn = pg_engine.connect()
    trans = conn.begin()
    yield conn
    trans.rollback()
    conn.close()


@pytest.fixture()
def pg_session(pg_conn):
    """ORM Session bound to pg_conn's transaction. Service functions only flush(),
    never commit(), so the outer rollback in pg_conn cleans up everything."""
    Session = sessionmaker(bind=pg_conn, future=True)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def make_org(pg_session):
    """Seed a bare organizations row (superuser/table-owner connection, so RLS on
    the platform tables doesn't apply to this setup step)."""
    def _make(name="Acme Corp", slug=None):
        org_id = uuid.uuid4()
        pg_session.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": org_id, "name": name, "slug": slug or f"org-{org_id.hex[:8]}"},
        )
        pg_session.flush()
        return org_id
    return _make


@pytest.fixture()
def as_tenant(pg_session):
    """Switch pg_session to the low-privilege RLS test role scoped to one org_id,
    the way a real request would after authenticating. Everything queried through
    pg_session after this call is subject to the org_units RLS policies."""
    def _use(org_id):
        pg_session.execute(text(f"SET LOCAL ROLE {RLS_TEST_ROLE}"))
        set_tenant_context(pg_session, org_id)
    return _use


PLATFORM_TABLES_FOR_TRUNCATION = [
    "org_unit_heads",
    "org_unit_reporting_lines",
    "org_unit_assignments",
    "org_unit_closures",
    "org_units",
    "platform_audit_logs",
]


@pytest.fixture()
def pg_committing_session(pg_engine):
    """For code paths that call db.commit() themselves (e.g.
    app.modules.platform.services.audit.log_action) — pg_session's rollback-based
    cleanup can't undo a real commit. Truncates every platform table plus
    organizations after the test instead, same as tests/conftest.py's clean_db."""
    Session = sessionmaker(bind=pg_engine, future=True)
    session = Session()
    yield session
    session.rollback()
    session.close()
    with pg_engine.connect() as conn:
        conn.execute(text(
            f"TRUNCATE {', '.join(PLATFORM_TABLES_FOR_TRUNCATION)}, organizations RESTART IDENTITY CASCADE"
        ))
        conn.commit()


@pytest.fixture()
def make_org_committing(pg_committing_session):
    """Same as make_org, but for use with pg_committing_session."""
    def _make(name="Acme Corp", slug=None):
        org_id = uuid.uuid4()
        pg_committing_session.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": org_id, "name": name, "slug": slug or f"org-{org_id.hex[:8]}"},
        )
        pg_committing_session.flush()
        return org_id
    return _make
