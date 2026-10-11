"""Public FPL history, normalised to one row per player per fixture.

Source: github.com/vaastav/Fantasy-Premier-League (code MIT; the data belongs
to the Premier League). Files are downloaded on demand into the cache dir and
never committed. Columns differ by season — xG arrives in 2022-23, defensive
contributions in 2025-26 — so missing ones are NaN, never zero.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

BASE_URL = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
SEASONS: tuple[str, ...] = (
    "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26",
)
FILES = {
    "merged_gw.csv": "gws/merged_gw.csv",
    "players_raw.csv": "players_raw.csv",
    "fixtures.csv": "fixtures.csv",
}
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}  # 5 = assistant manager (2024-25), dropped
POS_CODE = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}

# per-fixture stats kept from merged_gw; NaN where a season doesn't have them
STATS = (
    "minutes", "total_points", "goals_scored", "assists", "clean_sheets", "goals_conceded",
    "own_goals", "penalties_saved", "penalties_missed", "yellow_cards", "red_cards", "saves",
    "bonus", "bps", "influence", "creativity", "threat", "ict_index", "starts",
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded", "defensive_contribution",
)
MARKET = ("value", "selected", "transfers_balance", "xP")


def cache_dir() -> Path:
    root = os.environ.get("FANTASY_CACHE_DIR") or Path.home() / ".cache" / "fantasy"
    return Path(root) / "fpl-history"


def season_index(season: str) -> int:
    """'2019-20' → 2019, so seasons sort and subtract naturally."""
    return int(season[:4])


def download(
    seasons: Iterable[str] = SEASONS,
    *,
    max_age_days: float | None = None,
    client: httpx.Client | None = None,
) -> Path:
    """Fetch any missing season files (or ones older than `max_age_days`).
    Writes atomically, so an interrupted download never leaves a half file."""
    root = cache_dir()
    own = client is None
    c = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        for season in seasons:
            for local, remote in FILES.items():
                path = root / season / local
                fresh = path.is_file() and (
                    max_age_days is None or time.time() - path.stat().st_mtime < max_age_days * 86400
                )
                if fresh:
                    continue
                r = c.get(f"{BASE_URL}/{season}/{remote}")
                r.raise_for_status()
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".part")
                tmp.write_bytes(r.content)
                tmp.replace(path)
    finally:
        if own:
            c.close()
    return root


def load_season(season: str, root: Path | None = None) -> pd.DataFrame:
    """One season as tidy player-fixture rows (see module docstring)."""
    d = (root or cache_dir()) / season
    gw = pd.read_csv(d / "merged_gw.csv", low_memory=False, encoding="utf-8")
    players = pd.read_csv(d / "players_raw.csv", usecols=["id", "code", "element_type"])
    fixtures = pd.read_csv(
        d / "fixtures.csv",
        usecols=["id", "event", "team_h", "team_a", "team_h_score", "team_a_score", "kickoff_time"],
    )

    out = pd.DataFrame({
        "season": season,
        "season_idx": season_index(season),
        "element": gw["element"].astype(int),
        "name": gw["name"].astype(str),
        "fixture": gw["fixture"].astype(int),
        "was_home": gw["was_home"].astype(str).str.lower().eq("true"),
        "opp": gw["opponent_team"].astype(int),
        "gw": gw["GW"].astype(int),
    })
    # 2019-20 was paused for COVID; the dataset numbers the restart GWs 39-47.
    out.loc[out["gw"] > 38, "gw"] -= 9
    for col in (*STATS, *MARKET):
        out[col] = pd.to_numeric(gw[col], errors="coerce") if col in gw else np.nan

    p = players.rename(columns={"id": "element"})
    out = out.merge(p, on="element", how="left")
    out["position"] = out["element_type"].map(POSITIONS)
    out = out.drop(columns="element_type")

    f = fixtures.rename(columns={"id": "fixture"})
    out = out.merge(f, on="fixture", how="left")
    home = out["was_home"]
    out["team"] = np.where(home, out["team_h"], out["team_a"])
    out["team_goals"] = np.where(home, out["team_h_score"], out["team_a_score"])
    out["opp_goals"] = np.where(home, out["team_a_score"], out["team_h_score"])
    out["kickoff"] = pd.to_datetime(out["kickoff_time"], utc=True, errors="coerce")
    out = out.drop(columns=["team_h", "team_a", "team_h_score", "team_a_score", "kickoff_time", "event"])

    # FPL's own expected points were not recorded for every gameweek (most of
    # 2025-26 is all zeros): treat a gameweek with no non-zero xP as missing.
    recorded = out.groupby("gw")["xP"].transform(lambda x: bool((x.fillna(0) != 0).any()))
    out.loc[~recorded.astype(bool), "xP"] = np.nan

    out = out[out["position"].notna() & out["code"].notna()].copy()
    out["code"] = out["code"].astype(int)
    out["team"] = out["team"].astype(int)
    return out.reset_index(drop=True)


def load(seasons: Sequence[str] = SEASONS, root: Path | None = None) -> pd.DataFrame:
    return pd.concat([load_season(s, root) for s in seasons], ignore_index=True)
