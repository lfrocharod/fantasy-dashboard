"""API integration tests against a freshly migrated, demo-seeded database."""

from __future__ import annotations

import os
import uuid
import warnings
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import bcrypt
import psycopg
import pytest

pytestmark = pytest.mark.db

PAGES = [
    "/api/home",
    "/api/settings/ucl", "/api/settings/draft?sport=fpl", "/api/settings/draft?sport=nfl",
    "/api/ucl/overview", "/api/ucl/players", "/api/ucl/players?position=MID&maxPrice=8",
    "/api/ucl/teams", "/api/ucl/fixtures", "/api/ucl/optimizer", "/api/ucl/rivals",
    "/api/ucl/league",
    "/api/fpl/board", "/api/fpl/overview", "/api/fpl/teams", "/api/fpl/fixtures",
    "/api/fpl/optimizer?horizon=short", "/api/fpl/optimizer?horizon=medium",
    "/api/fpl/optimizer?horizon=season", "/api/fpl/rivals", "/api/fpl/standings",
    "/api/fpl/trade?horizon=medium",
    "/api/nfl/overview", "/api/nfl/players", "/api/nfl/players?horizon=week&position=WR",
    "/api/nfl/teams", "/api/nfl/fixtures", "/api/nfl/optimizer", "/api/nfl/rivals",
    "/api/nfl/standings", "/api/nfl/standings?seeding=TOTAL_POINTS_SCORED", "/api/nfl/trade",
    "/api/draft/board?sport=nfl",
]


def _reset_engine() -> None:
    from fantasy.core import database

    if database.engine.cache_info().currsize:
        database.engine().dispose()
    database.engine.cache_clear()
    database.session_factory.cache_clear()


@pytest.fixture(scope="session")
def demo_db(pg_server_url: str, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """One migrated + demo-seeded database for the whole session (~20 s)."""
    from fantasy.core import migrations
    from fantasy.demo.seed import seed

    name = f"fantasy_api_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(pg_server_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = urlunsplit(urlsplit(pg_server_url)._replace(path=f"/{name}"))
    saved = {k: os.environ.get(k) for k in ("DATABASE_URL", "FANTASY_CACHE_DIR")}
    os.environ["DATABASE_URL"] = url
    os.environ["FANTASY_CACHE_DIR"] = str(tmp_path_factory.mktemp("cache"))
    try:
        _reset_engine()
        migrations.upgrade("head")
        seed(url)
        yield url
    finally:
        _reset_engine()
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        with psycopg.connect(pg_server_url, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def client(demo_db: str, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from fastapi.testclient import TestClient

    from fantasy.api.main import create_app

    monkeypatch.setenv("DATABASE_URL", demo_db)
    monkeypatch.setenv("SESSION_SECRET", "test-secret-test-secret-test-secret")
    monkeypatch.setenv("APP_PASSWORD_HASH", bcrypt.hashpw(b"letmein", bcrypt.gensalt(4)).decode())
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    from fantasy.api.routers import auth

    monkeypatch.setattr(auth, "throttle", auth.LoginThrottle())
    _reset_engine()
    with TestClient(create_app()) as c:
        yield c
    _reset_engine()


def _login(client) -> None:  # type: ignore[no-untyped-def]
    r = client.post("/api/auth", json={"password": "letmein"})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("path", PAGES)
def test_every_page_renders(client, path: str) -> None:  # type: ignore[no-untyped-def]
    _login(client)
    r = client.get(path)
    assert r.status_code == 200, r.text[:500]
    assert r.headers["cache-control"] == "no-store"


def test_pages_need_a_session(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/home").status_code == 401
    assert client.get("/api/session").json() == {"authenticated": False, "demo": False}
    assert client.post("/api/auth", json={"password": "nope"}).status_code == 401
    _login(client)
    assert client.get("/api/session").json()["authenticated"] is True
    assert client.get("/api/home").status_code == 200
    client.delete("/api/auth")
    assert client.get("/api/home").status_code == 401


def test_login_is_throttled(client, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from fantasy.api.routers import auth

    monkeypatch.setattr(auth, "throttle", auth.LoginThrottle(limit=3, window_s=600))
    for _ in range(3):
        assert client.post("/api/auth", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth", json={"password": "letmein"}).status_code == 429


def test_demo_mode_is_open_but_read_only(client, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DEMO_MODE", "1")
    assert client.get("/api/home").status_code == 200
    assert client.post("/api/settings/ucl", json={"leagueCode": "X"}).status_code == 403
    assert client.post("/api/draft/pick", json={"extId": "1"}).status_code == 403


def test_home_ranks_alerts_by_urgency(client) -> None:  # type: ignore[no-untyped-def]
    _login(client)
    h = client.get("/api/home").json()
    assert h["ucl"]["active"] and h["fpl"]["active"] and h["nfl"]["active"]
    order = {"bad": 0, "warn": 1, "accent": 2}
    tones = [order[a["tone"]] for a in h["alerts"]]
    assert tones == sorted(tones)


def test_settings_round_trip(client) -> None:  # type: ignore[no-untyped-def]
    _login(client)
    assert client.post("/api/settings/ucl", json={"matchdayOverride": 3}).status_code == 200
    assert client.get("/api/settings/ucl").json()["matchdayOverride"] == "3"
    assert client.post("/api/settings/ucl", json={"matchdayOverride": 0}).status_code == 200
    assert client.get("/api/settings/ucl").json()["matchdayOverride"] == ""
    bad = client.post("/api/settings/ucl", json={"modelParams": "{not json"})
    assert bad.status_code == 400


def test_fpl_trade_evaluation(client) -> None:  # type: ignore[no-untyped-def]
    _login(client)
    lab = client.get("/api/fpl/trade").json()
    mine = lab["me"]["players"]
    rival = lab["rivals"][0]["players"]
    give = next(p for p in mine if p["pos"] == "MID")
    get = next(p for p in rival if p["pos"] == "MID")
    ev = client.post("/api/fpl/trade/evaluate", json={"give": [give["extId"]], "get": [get["extId"]]}).json()
    assert ev["balanced"] is True and ev["posGive"] == "MID" and ev["verdict"]
    lopsided = client.post(
        "/api/fpl/trade/evaluate", json={"give": [give["extId"]], "get": []}
    ).json()
    assert lopsided["balanced"] is False


def test_nfl_standings_seeding_toggle(client) -> None:  # type: ignore[no-untyped-def]
    _login(client)
    h2h = client.get("/api/nfl/standings").json()
    pts = client.get("/api/nfl/standings?seeding=TOTAL_POINTS_SCORED").json()
    assert h2h["rule"] == "H2H_RECORD" and not h2h["byPoints"]
    assert pts["byPoints"] and pts["pace"] is not None
    assert [r["pf"] for r in pts["rows"]] == sorted((r["pf"] for r in pts["rows"]), reverse=True)


def test_draft_pick_tracker(client) -> None:  # type: ignore[no-untyped-def]
    _login(client)
    board = client.get("/api/draft/board?sport=nfl").json()
    ext = board["players"][0]["extId"]
    first = client.post("/api/draft/pick", json={"sport": "nfl", "extId": ext, "isMine": True}).json()
    assert first["overall"] == 1
    assert client.get("/api/draft/board?sport=nfl").json()["picks"][0]["isMine"] is True
    assert client.delete("/api/draft/pick?sport=nfl").json()["ok"] is True
    assert client.get("/api/draft/board?sport=nfl").json()["picks"] == []
