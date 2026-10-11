"""The learned FPL model: leakage-safety of the features, double-gameweek
handling, team strength, and an end-to-end fit on a synthetic league."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")

from fantasy.ml import features as F  # noqa: E402
from fantasy.ml import model as M  # noqa: E402
from fantasy.ml.history import MARKET, STATS  # noqa: E402

TEAMS = (1, 2, 3, 4)
POSITIONS = ("GK", "DEF", "MID", "FWD")


def _league(seasons: tuple[str, ...] = ("2023-24", "2024-25"), gws: int = 8, seed: int = 0) -> pd.DataFrame:
    """A tiny round-robin league with one player per position per team, shaped
    like history.load(). GW3 is a double gameweek for teams 1 and 2."""
    rng = np.random.default_rng(seed)
    rows = []
    fixture = 0
    for season in seasons:
        for gw in range(1, gws + 1):
            pairs = [(1, 2), (3, 4)] if gw % 2 else [(1, 3), (2, 4)]
            if gw == 3:
                pairs = [*pairs, (2, 1)]
            for home, away in pairs:
                fixture += 1
                hg, ag = rng.poisson(1.4, 2)
                for team, opp, is_home, gf, ga in ((home, away, True, hg, ag), (away, home, False, ag, hg)):
                    for i, pos in enumerate(POSITIONS):
                        code = team * 10 + i
                        mins = int(rng.choice([0, 90], p=[0.2, 0.8]))
                        pts = int(rng.integers(0, 10)) if mins else 0
                        row = {
                            "season": season, "season_idx": int(season[:4]), "element": code, "code": code,
                            "name": f"P{code}", "fixture": fixture, "was_home": is_home, "opp": opp, "gw": gw,
                            "position": pos, "team": team, "team_goals": gf, "opp_goals": ga,
                            "kickoff": pd.Timestamp("2024-08-01", tz="UTC") + pd.Timedelta(days=7 * gw),
                        }
                        row.update({s: np.nan for s in (*STATS, *MARKET)})
                        row.update(minutes=mins, total_points=pts, bps=pts * 3, bonus=min(pts // 4, 3),
                                   ict_index=pts * 1.5, value=50 + code % 7, selected=1000 * code,
                                   transfers_balance=int(rng.integers(-500, 500)), xP=float(pts))
                        rows.append(row)
    return pd.DataFrame(rows)


def _feature_rows(df: pd.DataFrame, upto_gw: int, season: str = "2024-25") -> pd.DataFrame:
    keep = (df["season"] < season) | ((df["season"] == season) & (df["gw"] <= upto_gw))
    return df.loc[keep, ["season", "code", "gw", *F.FEATURES]].reset_index(drop=True)


def test_features_never_see_the_gameweek_they_describe() -> None:
    fx = _league()
    base = F.build(fx)
    # rewrite everything that happened in GW5 of the second season…
    later = fx.copy()
    hit = (later["season"] == "2024-25") & (later["gw"] == 5)
    later.loc[hit, "total_points"] = 25
    later.loc[hit, "minutes"] = 90
    later.loc[hit, ["team_goals", "opp_goals"]] = [7, 0]
    later.loc[hit, "bps"] = 99
    changed = F.build(later)
    # …features up to and including GW5 must not move (GW5's are pre-deadline)
    pd.testing.assert_frame_equal(_feature_rows(base, 5), _feature_rows(changed, 5))
    # but the target and later gameweeks' features do
    after = (changed["season"] == "2024-25") & (changed["gw"] == 6)
    assert not changed.loc[after, "pts_r3"].equals(base.loc[after, "pts_r3"])


def test_double_gameweek_is_learnt_per_fixture() -> None:
    df = F.build(_league())
    dgw = df[(df["season"] == "2024-25") & (df["gw"] == 3) & (df["code"] == 12)].iloc[0]
    assert dgw["n_fix"] == 2
    assert dgw["y_pf"] == pytest.approx(dgw["y"] / 2)


def test_team_strength_starts_at_the_league_mean_and_only_uses_played_games() -> None:
    df = F.build(_league())
    first = df[(df["gw"] == 1)]
    assert first["opp_def"].nunique() == 1 and first["opp_def"].iloc[0] == pytest.approx(1.4)
    assert df.loc[df["gw"] == 2, "opp_def"].nunique() > 1


def test_previous_season_output_carries_over_by_player_code() -> None:
    df = F.build(_league())
    first_season = df[df["season"] == "2023-24"]
    assert first_season["prev_mins"].isna().all()
    p = df[(df["season"] == "2024-25") & (df["code"] == 22)].iloc[0]
    expected = df[(df["season"] == "2023-24") & (df["code"] == 22)]["minutes"].sum()
    assert p["prev_mins"] == expected


def test_model_fits_and_scales_by_fixtures() -> None:
    df = F.build(_league(gws=12))
    est = M.fit(df[df["season"] == "2023-24"])
    # the all-missing defensive-contribution features are dropped, not fatal
    assert "dc_r3" not in est.feature_names_in_
    test = df[df["season"] == "2024-25"]
    pred = M.predict(est, test)
    assert pred.shape == (len(test),) and np.isfinite(pred).all()
    per_fix = est.predict(test[list(est.feature_names_in_)])
    np.testing.assert_allclose(pred, per_fix * test["n_fix"].to_numpy())


# ---- live serving ---------------------------------------------------------------------------


def _live_payloads() -> tuple[dict, list[dict], dict, dict]:
    """Draft bootstrap, classic fixtures, draft lives and classic market for a
    four-team league two gameweeks into a season; GW2 is a double for teams 1/2."""
    boot = {
        "events": {"data": [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z", "finished": True},
                            {"id": 2, "deadline_time": "2026-08-28T17:30:00Z", "finished": True},
                            {"id": 3, "deadline_time": "2026-09-04T17:30:00Z", "finished": False}],
                   "next": 3},
        "elements": [
            {"id": 100 + t * 10 + i, "code": t * 10 + i, "team": t, "element_type": i + 1,
             "web_name": f"P{t}{i}", "ep_next": 2.0}
            for t in TEAMS for i in range(4)
        ],
    }
    fixtures = [
        {"id": 1, "event": 1, "team_h": 1, "team_a": 2, "team_h_score": 2, "team_a_score": 0, "kickoff_time": "2026-08-22T14:00:00Z"},
        {"id": 2, "event": 1, "team_h": 3, "team_a": 4, "team_h_score": 1, "team_a_score": 1, "kickoff_time": "2026-08-22T14:00:00Z"},
        {"id": 3, "event": 2, "team_h": 1, "team_a": 3, "team_h_score": 0, "team_a_score": 1, "kickoff_time": "2026-08-29T14:00:00Z"},
        {"id": 4, "event": 2, "team_h": 2, "team_a": 4, "team_h_score": 3, "team_a_score": 0, "kickoff_time": "2026-08-29T14:00:00Z"},
        {"id": 5, "event": 2, "team_h": 2, "team_a": 1, "team_h_score": 1, "team_a_score": 1, "kickoff_time": "2026-08-31T19:00:00Z"},
        {"id": 6, "event": 3, "team_h": 4, "team_a": 1, "team_h_score": None, "team_a_score": None, "kickoff_time": "2026-09-05T14:00:00Z"},
        {"id": 7, "event": 3, "team_h": 3, "team_a": 2, "team_h_score": None, "team_a_score": None, "kickoff_time": "2026-09-05T14:00:00Z"},
    ]
    # only some players appear in the live data — the rest must still get rows
    lives = {gw: {"elements": {str(100 + t * 10 + 3): {"stats": {"minutes": 90, "total_points": 6 * gw, "bps": 20}}
                               for t in TEAMS}} for gw in (1, 2)}
    market = {t * 10 + i: {"value": 60.0, "start_value": 55.0, "selected": float(t), "transfers_balance": float(i)}
              for t in TEAMS for i in range(4)}
    return boot, fixtures, lives, market


def test_season_rows_cover_every_player_and_split_doubles() -> None:
    from fantasy.ml import serve

    boot, fixtures, lives, market = _live_payloads()
    rows = serve.season_rows(boot, fixtures, lives, market, "2026-27", 3)
    # 16 players: GW1 one fixture each, GW2 two for teams 1/2, GW3 one each
    assert len(rows) == 16 + (8 * 2 + 8) + 16
    fwd = rows[(rows["code"] == 13) & (rows["gw"] == 2)]
    assert len(fwd) == 2 and fwd["total_points"].tolist() == [6.0, 6.0]  # 12 split across the double
    benched = rows[(rows["code"] == 10) & (rows["gw"] == 1)].iloc[0]
    assert benched["minutes"] == 0 and benched["total_points"] == 0
    upcoming = rows[rows["gw"] == 3]
    assert upcoming["total_points"].isna().all() and (upcoming["value"] == 60.0).all()
    assert (rows.loc[rows["gw"] < 3, "value"] == 55.0).all()  # start price → value_change


def test_predict_next_is_keyed_by_draft_id() -> None:
    from fantasy.ml import serve

    boot, fixtures, lives, market = _live_payloads()
    art = M.Artifact(estimator=M.fit(F.build(_league(gws=12))), features=list(F.FEATURES),
                     seasons=["2023-24", "2024-25"], trained_rows=0)
    preds = serve.predict_next(art, boot, fixtures, lives, market, 3, last_season=None)
    assert set(preds) == {str(e["id"]) for e in boot["elements"]}
    assert all(np.isfinite(v) for v in preds.values())


def test_fpl_ep_comes_from_the_classic_game_by_player_code() -> None:
    from fantasy.ml import serve

    boot = {"elements": [{"id": 7, "code": 70, "ep_next": "0.0"}, {"id": 8, "code": 80}]}
    classic = {"elements": [{"id": 401, "code": 70, "ep_next": "5.2"}]}
    assert serve.fpl_ep(boot, classic) == {"7": 5.2}
