"""Is a Champions League matchday in play right now?

The live refresh (`fantasy sync ucl --mode live --if-live`) is meant to be
scheduled every few minutes, all week. Asking Postgres "is anything live?" on
every tick would keep a scale-to-zero database (Neon) awake around the clock,
so the answer comes from a small local cache of kickoff times instead: every
regular UCL sync rewrites it, and the gate only ever reads a file.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

# A match is "in play" from shortly before kickoff (confirmed XIs, last-minute
# armband moves) until well after the final whistle (UEFA settles bonus points
# and the static feeds lag), so the window is asymmetric.
BEFORE_KICKOFF = timedelta(minutes=20)
AFTER_KICKOFF = timedelta(minutes=150)


def cache_path() -> Path:
    base = os.environ.get("FANTASY_CACHE_DIR") or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "fantasy"
    )
    return Path(base) / "ucl_kickoffs.json"


def write_kickoffs(kickoffs: Iterable[datetime], path: Path | None = None) -> None:
    """Persist every known kickoff (UTC). Called by the regular UCL sync."""
    p = path or cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    stamps = sorted(
        {(k if k.tzinfo else k.replace(tzinfo=UTC)).astimezone(UTC).isoformat() for k in kickoffs}
    )
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"updatedAt": datetime.now(UTC).isoformat(), "kickoffs": stamps}))
    tmp.replace(p)


def read_kickoffs(path: Path | None = None) -> list[datetime] | None:
    p = path or cache_path()
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    return [datetime.fromisoformat(s) for s in data.get("kickoffs", [])]


def in_live_window(
    kickoffs: Iterable[datetime], now: datetime | None = None
) -> bool:
    now = now or datetime.now(UTC)
    for k in kickoffs:
        k = k if k.tzinfo else k.replace(tzinfo=UTC)
        if k - BEFORE_KICKOFF <= now <= k + AFTER_KICKOFF:
            return True
    return False


def should_run_live(now: datetime | None = None, path: Path | None = None) -> bool:
    """True when the live refresh should run. With no cache yet (fresh machine)
    the answer is True, so the first run populates it."""
    ks = read_kickoffs(path)
    if ks is None:
        return True
    return in_live_window(ks, now)
