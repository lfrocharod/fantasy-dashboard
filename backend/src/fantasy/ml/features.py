"""Model features: one row per player per gameweek, built only from what was
known before that gameweek's deadline.

Every rolling / to-date statistic is computed on the player's *previous*
gameweeks (a one-row shift inside the player's season), team strength only
counts matches already played, and market signals (price, ownership, net
transfers) are the values at the deadline. `tests/test_ml.py` checks this:
changing a future result must never move an earlier row's features.

The target is points per fixture, weighted by fixtures that gameweek, so a
double gameweek is learnt as two games rather than one big one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from fantasy.ml.history import POS_CODE

KEYS = ["season", "season_idx", "code", "gw"]
PLAYER = ["season", "code"]

# per-fixture rates rolled over the previous gameweeks
ROLL = {
    "pts": "total_points", "mins": "minutes", "bps": "bps", "bonus": "bonus", "ict": "ict_index",
    "threat": "threat", "creat": "creativity", "goals": "goals_scored", "assists": "assists",
    "cs": "clean_sheets", "saves": "saves", "starts": "starts",
    "xgi": "expected_goal_involvements", "xgc": "expected_goals_conceded", "dc": "defensive_contribution",
}
WINDOWS = (3, 6)
TEAM_PRIOR_GAMES = 6.0  # shrink a team's scoring rates toward the league mean this hard

FEATURES: list[str] = [
    "pos", "gw", "dc_era", "n_fix", "home",
    "opp_att", "opp_def", "own_att", "own_def",
    "value", "value_change", "selected_pct", "transfers_pct",
    *(f"{k}_r{w}" for k in ROLL for w in WINDOWS),
    "mins_last", "full90_share6", "gws_since_played",
    "mins_std", "apps_std", "pts90_std", "xgi90_std", "bonus90_std",
    "prev_mins", "prev_pts90", "prev_xgi90", "prev_apps",
]


def _team_strength(fx: pd.DataFrame) -> pd.DataFrame:
    """(season, gw, team) → goals scored / conceded per game in matches played
    before that gameweek, shrunk toward the league mean."""
    m = (
        fx.dropna(subset=["team_goals", "opp_goals"])
        .drop_duplicates(["season", "fixture", "team"])
        .groupby(["season", "team", "gw"], as_index=False)
        .agg(gf=("team_goals", "sum"), ga=("opp_goals", "sum"), games=("fixture", "nunique"))
    )
    rows = []
    for season, sm in m.groupby("season"):
        teams = sm["team"].unique()
        grid = pd.MultiIndex.from_product([teams, range(1, 40)], names=["team", "gw"])
        s = sm.set_index(["team", "gw"])[["gf", "ga", "games"]].reindex(grid, fill_value=0)
        # totals strictly before gameweek g
        before = s.groupby(level="team").cumsum() - s
        league = before.groupby(level="gw").sum()
        mean = (league["gf"] / league["games"].where(league["games"] > 0)).fillna(1.4)
        mean = mean.reindex(before.index.get_level_values("gw")).to_numpy()
        n = before["games"].to_numpy()
        k = TEAM_PRIOR_GAMES
        out = pd.DataFrame({
            "season": season,
            "team": before.index.get_level_values("team"),
            "gw": before.index.get_level_values("gw"),
            "att": (before["gf"].to_numpy() + k * mean) / (n + k),
            "dfn": (before["ga"].to_numpy() + k * mean) / (n + k),
        })
        rows.append(out)
    return pd.concat(rows, ignore_index=True)


def _roll(df: pd.DataFrame, col: pd.Series, window: int) -> pd.Series:
    """Mean of `col` over the player's previous `window` gameweeks."""
    prev = col.groupby([df["season"], df["code"]], sort=False).shift(1)
    return (
        prev.groupby([df["season"], df["code"]], sort=False)
        .rolling(window, min_periods=1)
        .mean()
        .reset_index(level=[0, 1], drop=True)
        .sort_index()
    )


def _before(df: pd.DataFrame, col: pd.Series) -> pd.Series:
    """Season-to-date total of `col` up to (not including) this gameweek."""
    return col.fillna(0).groupby([df["season"], df["code"]], sort=False).cumsum() - col.fillna(0)


def build(fx: pd.DataFrame) -> pd.DataFrame:
    """Player-fixture rows (history.load) → one feature row per player-gameweek."""
    strength = _team_strength(fx)
    fx = fx.merge(
        strength.rename(columns={"team": "opp", "att": "opp_att", "dfn": "opp_def"}),
        on=["season", "gw", "opp"], how="left",
    ).merge(
        strength.rename(columns={"att": "own_att", "dfn": "own_def"}),
        on=["season", "gw", "team"], how="left",
    )

    stats = [c for c in fx.columns if c in {*ROLL.values(), "total_points", "minutes"}]
    g = fx.groupby(KEYS, sort=True)
    df = g[stats].sum(min_count=1).join(
        g.agg(
            element=("element", "first"), name=("name", "first"), position=("position", "first"),
            team=("team", "first"), n_fix=("fixture", "size"), home=("was_home", "mean"),
            kickoff=("kickoff", "min"), opp_att=("opp_att", "mean"), opp_def=("opp_def", "mean"),
            own_att=("own_att", "mean"), own_def=("own_def", "mean"), value=("value", "first"),
            selected=("selected", "first"), transfers_balance=("transfers_balance", "first"),
            xP=("xP", "first"),
        )
    ).reset_index()
    df = df.sort_values(KEYS, kind="stable").reset_index(drop=True)

    df["pos"] = df["position"].map(POS_CODE).astype(int)
    # FPL's own expected points, for the benchmark only. The dataset's xP for
    # gameweek g was snapshotted AFTER g was played — it loads on g's own points
    # more than on any earlier week (see backtest.xp_leak_check) — so it would
    # leak the answer. The previous gameweek's snapshot is genuinely known
    # before g's deadline. (As a model input it added nothing; left out.)
    df["xp_prev"] = df.groupby(PLAYER, sort=False)["xP"].shift(1)
    df["dc_era"] = (df["season_idx"] >= 2025).astype(int)
    df["y"] = df["total_points"]
    df["y_pf"] = df["total_points"] / df["n_fix"]

    for short, col in ROLL.items():
        per_fix = df[col] / df["n_fix"]
        for w in WINDOWS:
            df[f"{short}_r{w}"] = _roll(df, per_fix, w)

    mins_pf = df["minutes"] / df["n_fix"]
    by_player = mins_pf.groupby([df["season"], df["code"]], sort=False)
    df["mins_last"] = by_player.shift(1)
    df["full90_share6"] = _roll(df, (mins_pf >= 60).astype(float), 6)
    played = (df["minutes"] > 0).astype(int)
    # gameweeks since the player last got on the pitch (NaN before their first appearance)
    idx = pd.Series(np.arange(len(df)), index=df.index, dtype=float)
    last_played = idx.where(played == 1).groupby([df["season"], df["code"]], sort=False).ffill()
    last_played = last_played.groupby([df["season"], df["code"]], sort=False).shift(1)
    df["gws_since_played"] = idx - last_played

    df["mins_std"] = _before(df, df["minutes"])
    df["apps_std"] = _before(df, played.astype(float))
    per90 = 90.0 / df["mins_std"].clip(lower=90)
    df["pts90_std"] = _before(df, df["total_points"]) * per90
    df["xgi90_std"] = _before(df, df["expected_goal_involvements"]).where(
        df["expected_goal_involvements"].notna()) * per90
    df["bonus90_std"] = _before(df, df["bonus"]) * per90

    season_tot = (
        df.groupby(["season_idx", "code"])
        .agg(prev_mins=("minutes", "sum"), prev_pts=("total_points", "sum"),
             prev_xgi=("expected_goal_involvements", lambda s: s.sum(min_count=1)),
             prev_apps=("minutes", lambda s: int((s > 0).sum())))
        .reset_index()
    )
    season_tot["season_idx"] += 1  # last season's totals feed this season's rows
    p90 = 90.0 / season_tot["prev_mins"].clip(lower=90)
    season_tot["prev_pts90"] = season_tot["prev_pts"] * p90
    season_tot["prev_xgi90"] = season_tot["prev_xgi"] * p90
    df = df.merge(
        season_tot[["season_idx", "code", "prev_mins", "prev_pts90", "prev_xgi90", "prev_apps"]],
        on=["season_idx", "code"], how="left",
    )

    first_value = df.groupby(PLAYER, sort=False)["value"].transform("first")
    df["value_change"] = df["value"] - first_value
    gw_groups = df.groupby(["season", "gw"])
    df["selected_pct"] = gw_groups["selected"].rank(pct=True)
    df["transfers_pct"] = gw_groups["transfers_balance"].rank(pct=True)

    # "regular": got minutes in one of the previous three gameweeks — the
    # population a manager actually chooses between, used for evaluation
    df["regular"] = (_roll(df, played.astype(float), 3) > 0).fillna(False)
    return df.reset_index(drop=True)
