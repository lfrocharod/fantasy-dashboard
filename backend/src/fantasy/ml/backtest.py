"""Walk-forward backtest: for every test gameweek, train only on what came
before it, then score the predictions against what actually happened.

Compared against:
  * FPL xP    — the game's own expected points, as of the previous gameweek
                (the same-week figure in the dataset was recorded after the
                games and leaks the result; see features.py)
  * form      — the player's points per fixture over their last 4 gameweeks
  * season    — season-to-date points per 90, scaled by recent minutes

Metrics are reported for every player with a fixture ("all") and for the
players a manager actually weighs up ("regulars": minutes in one of the
previous three gameweeks), because the thousands of squad players who never
play make any model look accurate.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from fantasy.ml import model as M

TEST_SEASONS: tuple[str, ...] = ("2022-23", "2023-24", "2024-25", "2025-26")
TOP_K = 20


def _form_baseline(df: pd.DataFrame) -> pd.Series:
    """Points per fixture over the last 4 gameweeks, then last season's per-90 rate."""
    prev = (df["total_points"] / df["n_fix"]).groupby([df["season"], df["code"]], sort=False).shift(1)
    r4 = (
        prev.groupby([df["season"], df["code"]], sort=False)
        .rolling(4, min_periods=1).mean()
        .reset_index(level=[0, 1], drop=True).sort_index()
    )
    fallback = df["prev_pts90"] * (df["prev_mins"] / (38 * 90)).clip(upper=1)
    return (r4.fillna(fallback).fillna(0) * df["n_fix"]).rename("form")


def _season_baseline(df: pd.DataFrame) -> pd.Series:
    """Season-to-date points per 90 × expected minutes (recent average)."""
    rate = df["pts90_std"].where(df["mins_std"] >= 270, df["prev_pts90"])
    minutes = df["mins_r6"].fillna(df["prev_mins"] / 38)
    return (rate.fillna(0) * minutes.fillna(0) / 90 * df["n_fix"]).rename("season")


def walk_forward(
    df: pd.DataFrame,
    test_seasons: Sequence[str] = TEST_SEASONS,
    block: int = 4,
    log: Callable[[str], None] = print,
) -> pd.DataFrame:
    """Predictions for every test gameweek from models that never saw it."""
    df = df.copy()
    df["pred_fpl"] = df["xp_prev"] * df["n_fix"]
    df["pred_form"] = _form_baseline(df)
    df["pred_season"] = _season_baseline(df)
    out = []
    for season in test_seasons:
        sidx = int(season[:4])
        gws = sorted(df.loc[df["season"] == season, "gw"].unique())
        for start in range(0, len(gws), block):
            chunk = gws[start:start + block]
            train = df[(df["season_idx"] < sidx) | ((df["season"] == season) & (df["gw"] < chunk[0]))]
            test = df[(df["season"] == season) & df["gw"].isin(chunk)].copy()
            t = time.monotonic()
            test["pred_model"] = M.predict(M.fit(train), test)
            out.append(test)
            log(f"{season} GW{chunk[0]}-{chunk[-1]}: trained on {len(train):,} rows "
                f"in {time.monotonic() - t:.0f}s")
    return pd.concat(out, ignore_index=True)


METHODS = {"model": "pred_model", "fpl_xp": "pred_fpl", "form": "pred_form", "season": "pred_season"}


@dataclass
class Score:
    n: int
    mae: float
    rmse: float
    bias: float
    spearman: float  # mean within-gameweek rank correlation
    top_k: float  # mean actual points of the method's top-K picks per gameweek


def _spearman(a: pd.Series, b: pd.Series) -> float:
    return float(a.rank().corr(b.rank())) if len(a) > 2 else float("nan")


def score(preds: pd.DataFrame, column: str) -> Score:
    p = preds.dropna(subset=[column])
    err = p[column] - p["y"]
    per_gw = p.groupby(["season", "gw"])
    rho = per_gw.apply(lambda g: _spearman(g[column], g["y"]), include_groups=False)
    top = per_gw.apply(lambda g: g.nlargest(TOP_K, column)["y"].mean(), include_groups=False)
    return Score(
        n=len(p), mae=float(err.abs().mean()), rmse=float(np.sqrt((err**2).mean())),
        bias=float(err.mean()), spearman=float(rho.mean()), top_k=float(top.mean()),
    )


def table(preds: pd.DataFrame, *, regulars_only: bool, fpl_rows_only: bool = False) -> pd.DataFrame:
    """Scores per season and overall. `fpl_rows_only` restricts every method to
    the rows FPL's xP covers, for a like-for-like comparison."""
    p = preds[preds["regular"]] if regulars_only else preds
    if fpl_rows_only:
        p = p[p["pred_fpl"].notna()]
    rows = []
    for season, sp in [*p.groupby("season"), ("all", p)]:
        for name, col in METHODS.items():
            if sp[col].isna().all():
                continue
            s = score(sp, col)
            rows.append({"season": season, "method": name, **s.__dict__})
    return pd.DataFrame(rows)


def importances(df: pd.DataFrame, season: str, n_rows: int = 20000, seed: int = 0) -> pd.Series:
    """Permutation importance (MAE increase) on one held-out season."""
    sidx = int(season[:4])
    est = M.fit(df[df["season_idx"] < sidx])
    test = df[(df["season"] == season) & df["regular"]]
    test = test.sample(min(n_rows, len(test)), random_state=seed)
    cols = list(est.feature_names_in_)
    r = permutation_importance(
        est, test[cols], test["y_pf"], sample_weight=test["n_fix"],
        scoring="neg_mean_absolute_error", n_repeats=3, random_state=seed,
    )
    return pd.Series(r.importances_mean, index=cols).sort_values(ascending=False)


def xp_leak_check(df: pd.DataFrame, seasons: Sequence[str] = ("2022-23", "2023-24", "2024-25")) -> pd.DataFrame:
    """Regress the dataset's same-week xP on points scored before, during and
    after that gameweek. A pre-deadline estimate can only load on the past; a
    weight on week g itself means the figure was recorded after the games."""
    rows = []
    for season in seasons:
        r = df[(df["season"] == season) & df["xP"].notna() & df["regular"]].copy()
        r["ypf"] = r["y"] / r["n_fix"]
        g = r.groupby("code", sort=False)["ypf"]
        cols = {"g−1": g.shift(1), "g−2": g.shift(2), "g−3": g.shift(3), "g": r["ypf"], "g+1": g.shift(-1)}
        x = pd.DataFrame(cols).dropna()
        a = np.column_stack([np.ones(len(x)), x.to_numpy()])
        coef, *_ = np.linalg.lstsq(a, r.loc[x.index, "xP"].to_numpy(), rcond=None)
        rows.append({"season": season, **{f"points in {k}": c for k, c in zip(cols, coef[1:], strict=True)}})
    return pd.DataFrame(rows)


def market_leak_check(df: pd.DataFrame, season: str = "2024-25") -> pd.DataFrame:
    """The same test for the market features the model relies on: standardised
    weights of points before, during and after gameweek g. Pre-deadline signals
    load on the past; a large weight on g (or g+1) would mean leakage."""
    r = df[(df["season"] == season) & df["regular"]].copy()
    r["ypf"] = r["y"] / r["n_fix"]
    g = r.groupby("code", sort=False)["ypf"]
    x = pd.DataFrame({"g−1": g.shift(1), "g−2": g.shift(2), "g": r["ypf"], "g+1": g.shift(-1)})
    targets = {
        "net transfers": r["transfers_balance"],
        "price change": r.groupby("code", sort=False)["value"].diff(),
        "ownership": r["selected"],
    }
    rows = []
    for name, t in targets.items():
        ok = x.notna().all(axis=1) & t.notna()
        xs = (x[ok] - x[ok].mean()) / x[ok].std()
        ts = (t[ok] - t[ok].mean()) / t[ok].std()
        coef, *_ = np.linalg.lstsq(np.column_stack([np.ones(int(ok.sum())), xs.to_numpy()]), ts.to_numpy(), rcond=None)
        rows.append({"feature": name, **{f"points in {k}": c for k, c in zip(x.columns, coef[1:], strict=True)}})
    return pd.DataFrame(rows)


def calibration(preds: pd.DataFrame, column: str = "pred_model", bins: int = 10) -> pd.DataFrame:
    """Mean predicted vs mean actual points by predicted decile (regulars)."""
    p = preds[preds["regular"]].dropna(subset=[column])
    q = pd.qcut(p[column], bins, labels=False, duplicates="drop")
    return p.groupby(q).agg(predicted=(column, "mean"), actual=("y", "mean"), n=("y", "size"))


def _md(df: pd.DataFrame, floatfmt: str = ".3f") -> str:
    """A markdown table, formatted by column type (ints with separators)."""
    cols = list(df.columns)

    def fmt(col: str, v: object) -> str:
        if pd.api.types.is_integer_dtype(df[col]):
            return f"{int(v):,}"  # type: ignore[call-overload]
        if pd.api.types.is_float_dtype(df[col]):
            return format(float(v), floatfmt)  # type: ignore[arg-type]
        return str(v)

    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(fmt(c, v) for c, v in zip(cols, row, strict=True)) + " |")
    return "\n".join(lines)


def report(preds: pd.DataFrame, feats: pd.DataFrame, imp: pd.Series, block: int) -> str:
    """The markdown write-up (docs/ml/fpl-backtest.md)."""
    reg = table(preds, regulars_only=True)
    fair = table(preds, regulars_only=True, fpl_rows_only=True)
    every = table(preds, regulars_only=False)
    overall = reg[reg["season"] == "all"].set_index("method")
    m, f = overall.loc["model"], overall.loc["form"]
    fp = fair[fair["season"] == "all"].set_index("method")
    cal = calibration(preds).reset_index(drop=True)
    cal.index = cal.index + 1
    cal.index.name = "decile"
    top = cal.iloc[-1]
    leak = xp_leak_check(feats)
    market = market_leak_check(feats)
    seasons = ", ".join(sorted(preds["season"].unique()))
    view = ["season", "method", "n", "mae", "rmse", "bias", "spearman", "top_k"]
    return f"""# FPL points model — walk-forward backtest

_Generated by `fantasy ml backtest`. Test seasons: {seasons}; the model is
retrained every {block} gameweeks on everything before them, so no prediction
ever saw its own gameweek._

**Headline (regulars, all test seasons):** MAE **{m.mae:.3f}** vs **{f.mae:.3f}** for
recent form ({(1 - m.mae / f.mae) * 100:.1f}% lower), within-gameweek rank correlation
**{m.spearman:.3f}** vs {f.spearman:.3f}, and its top {TOP_K} picks per gameweek averaged
**{m.top_k:.2f}** points against {f.top_k:.2f}. Where FPL's own expected points exist,
the like-for-like MAE is **{fp.loc["model"].mae:.3f}** vs **{fp.loc["fpl_xp"].mae:.3f}** for FPL xP.

## Setup

* **Data** — every Premier League player-fixture from 2019-20 to 2025-26
  ([vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League);
  downloaded at run time, not committed), {len(feats):,} player-gameweeks.
* **Features** ({len(imp)} used) — built strictly from earlier gameweeks: rolling 3/6-week
  per-fixture rates (points, minutes, bonus, ICT, xG involvement, defensive
  contributions…), season-to-date per-90 rates, last season's output, team
  attack/defence strength from results so far, fixture count and venue, price,
  ownership and net-transfer percentiles at the deadline.
* **Model** — scikit-learn `HistGradientBoostingRegressor` on points per fixture,
  weighted by fixtures, so a double gameweek counts as two games.
* **Baselines** — *form*: points per fixture over the last 4 gameweeks;
  *season*: season-to-date points per 90 × recent minutes; *fpl_xp*: FPL's own
  expected points as of the previous gameweek (see the leakage note).
* **Metrics** — MAE / RMSE / bias in points; *spearman*: mean within-gameweek
  rank correlation (does it order players correctly?); *top_k*: mean actual
  points of each method's top {TOP_K} picks per gameweek. **Regulars** = players
  with minutes in one of the previous three gameweeks — the ones a manager
  actually chooses between; scoring every squad player flatters any model.

## Results — regulars

{_md(reg[view])}

### Like-for-like with FPL xP (regulars, gameweeks where FPL's figure exists)

{_md(fair[view])}

### Every player with a fixture

{_md(every[view])}

## Calibration (regulars, by predicted decile)

{_md(cal.reset_index())}

Well calibrated through the middle; the top decile runs {top.predicted - top.actual:+.2f} points
hot (predicted {top.predicted:.2f}, actual {top.actual:.2f}) — the model is most optimistic about
the players it rates highest, so treat a narrow gap between two of them as a tie.

## What the model leans on (permutation importance, 2025-26)

Increase in MAE when the feature is shuffled:

{_md(imp.head(15).rename("mae_increase").reset_index().rename(columns={"index": "feature"}), ".4f")}

## Leakage note: the dataset's same-week xP is recorded after the games

Regressing the dataset's xP for gameweek *g* on points per fixture before,
during and after *g*:

{_md(leak)}

A genuine pre-deadline estimate can only weigh the past. This one puts its
largest weight on week *g* itself — it was snapshotted after the games — so
comparing against it, or feeding it to a model, leaks the result (doing so
"improves" rank correlation to ~0.85). The benchmark and every feature here
use only information available before the deadline.

The same test on the market features the model leans on (standardised
weights, 2024-25):

{_md(market)}

Net transfers and price changes follow the *previous* week's points. Ownership
is a slow quality signal — it relates to week *g* no more than to week *g+1*,
which it cannot have seen. None of them carries the result of the gameweek
being predicted.

## Limitations

* No injury or team-news features: the history has no per-gameweek availability
  flags. In production the structural model's availability layer covers this.
* FPL's xP was not recorded for most of 2025-26, so the like-for-like
  comparison is mostly 2022-23 to 2024-25.
* Defensive-contribution points exist only from 2025-26; earlier seasons are
  scored without them.
"""
