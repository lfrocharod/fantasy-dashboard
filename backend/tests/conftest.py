"""Shared fixtures. Database tests need a Postgres server: set TEST_DATABASE_URL
(CI provides one as a service container); each test gets a fresh, throwaway
database on that server."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest


@pytest.fixture(scope="session")
def pg_server_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set — skipping database tests")
    return url


def _reset_engine_caches() -> None:
    from fantasy.core import database

    if database.engine.cache_info().currsize:
        database.engine().dispose()
    database.engine.cache_clear()
    database.session_factory.cache_clear()


@pytest.fixture
def empty_db(pg_server_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A brand-new empty database; DATABASE_URL points at it for the test."""
    name = f"fantasy_test_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(pg_server_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = urlunsplit(urlsplit(pg_server_url)._replace(path=f"/{name}"))
    monkeypatch.setenv("DATABASE_URL", url)
    _reset_engine_caches()
    try:
        yield url
    finally:
        _reset_engine_caches()
        with psycopg.connect(pg_server_url, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def migrated_db(empty_db: str) -> str:
    """An empty database upgraded to the latest schema."""
    from fantasy.core import migrations

    migrations.upgrade("head")
    return empty_db
