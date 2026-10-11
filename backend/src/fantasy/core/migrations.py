"""Run Alembic from code (`fantasy db upgrade`) — works from the installed
package, no alembic.ini needed (the Cloud Run migrate job uses this).

Production predates Alembic: its tables were created by drizzle-kit. The
baseline revision reproduces that schema exactly, so for a database that has
the tables but no `alembic_version`, `upgrade()` first stamps the baseline and
then applies everything after it.
"""

from __future__ import annotations

from importlib.resources import files

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from fantasy.core.database import database_url, engine

BASELINE = "0001_baseline"


def config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("fantasy") / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))
    return cfg


def _is_legacy_unversioned() -> bool:
    insp = inspect(engine())
    tables = set(insp.get_table_names())
    return "alembic_version" not in tables and "players" in tables


def upgrade(revision: str = "head") -> None:
    cfg = config()
    if _is_legacy_unversioned():
        print(f"[db] existing schema without alembic_version — stamping {BASELINE}")
        command.stamp(cfg, BASELINE)
    command.upgrade(cfg, revision)


def current() -> None:
    command.current(config(), verbose=True)


def stamp(revision: str) -> None:
    command.stamp(config(), revision)
