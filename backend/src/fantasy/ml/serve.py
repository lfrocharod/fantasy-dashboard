"""Live use of the learned model: predict the next FPL gameweek and grade the
rounds that have been played.

Runs inside the FPL sync. It rebuilds the current season in exactly the shape
the model was trained on (history.load rows: one per player per fixture, all
players, minutes or not), prepends last season for the carry-over features,
and predicts the next gameweek. Each model's prediction is stored per player
(`model_predictions`) so the app can show, round by round, how the learned
model, the structural model and FPL's own estimate actually did.

Without a trained model (`fantasy ml train`) or the ml extra, it does nothing.
"""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd

from fantasy.ml import features as F
from fantasy.ml import history as H
from fantasy.ml import model as M

DRAFT = "https://draft.premierleague.com/api"
CLASSIC = "https://fantasy.premierleague.com/api"
STAT_KEYS = [s for s in H.STATS if s != "total_points"] + ["total_points"]


def season_label(events: Mapping[str, Any]) -> str:
    """'2026-27' from the first gameweek's deadline."""
    first = (events.get("data") or [{}])[0].get("deadline_time") or ""
    year = int(first[:4]) if first[:4].isdigit() else pd.Timestamp.now(tz="UTC").year
    return f"{year}-{str(year + 1)[2:]}"


def previous_season(season: str) -> str:
    y = int(season[:4]) - 1
    return f"{y}-{str(y + 1)[2:]}"


def _cache() -> Path:
    return H.cache_dir().parent / "fpl-live"


def live_gw(client: httpx.Client, season: str, gw: int, finished: bool) -> dict[str, Any]:
    """Draft `event/{gw}/live`, cached on disk once the gameweek is finished."""
    path = _cache() / season / f"{gw}.json"
    if finished and path.is_file():
        return json.loads(path.read_text())
    r = client.get(f"{DRAFT}/event/{gw}/live")
    r.raise_for_status()
    data: dict[str, Any] = r.json()
    if finished:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    return data


def _elements(live: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    els = live.get("elements") or {}
    items = els.items() if isinstance(els, dict) else ((e.get("id"), e) for e in els)
    return {int(k): (v or {}) for k, v in items}


def season_rows(
    boot: Mapping[str, Any],
    fixtures: list[dict[str, Any]],
    lives: Mapping[int, Mapping[str, Any]],
    market: Mapping[int, Mapping[str, Any]],
    season: str,
    next_gw: int,
) -> pd.DataFrame:
    """The current season as history.load-shaped rows: every player on every
    played gameweek where their team had a fixture, plus the next gameweek
    with unknown stats and deadline market values. `market` is keyed by player
    code: {"value", "start_value", "selected", "transfers_balance"}."""
    by_team: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for f in fixtures:
        if f.get("event"):
            for t in (f["team_h"], f["team_a"]):
                by_team.setdefault((int(f["event"]), int(t)), []).append(f)
    rows: list[dict[str, Any]] = []
    for el in boot.get("elements") or []:
        pos = H.POSITIONS.get(int(el.get("element_type") or 0))
        if pos is None:
            continue
        code, team, ext = int(el["code"]), int(el["team"]), int(el["id"])
        mk = market.get(code, {})
        for gw in [*sorted(lives), next_gw]:
            fxs = by_team.get((gw, team), [])
            if not fxs:
                continue  # blank gameweek for this team
            stats = (_elements(lives[gw]).get(ext, {}).get("stats") or {}) if gw in lives else {}
            for f in fxs:
                home = int(f["team_h"]) == team
                row: dict[str, Any] = {
                    "season": season, "season_idx": int(season[:4]), "element": ext, "code": code,
                    "name": el.get("web_name", ""), "position": pos, "team": team, "gw": gw,
                    "fixture": int(f["id"]), "was_home": home,
                    "opp": int(f["team_a"] if home else f["team_h"]),
                    "team_goals": f.get("team_h_score" if home else "team_a_score"),
                    "opp_goals": f.get("team_a_score" if home else "team_h_score"),
                    "kickoff": pd.to_datetime(f.get("kickoff_time"), utc=True),
                    "xP": np.nan, "selected": np.nan, "transfers_balance": np.nan,
                    "value": mk.get("start_value", np.nan),
                }
                if gw == next_gw:
                    row.update({k: np.nan for k in H.STATS})
                    row.update(value=mk.get("value", np.nan), selected=mk.get("selected", np.nan),
                               transfers_balance=mk.get("transfers_balance", np.nan))
                else:
                    # a double gameweek's totals are split evenly across its fixtures
                    row.update({k: (float(stats[k]) / len(fxs) if k in stats else np.nan) for k in H.STATS})
                    row["minutes"] = float(stats.get("minutes") or 0) / len(fxs)
                    row["total_points"] = float(stats.get("total_points") or 0) / len(fxs)
                rows.append(row)
    df = pd.DataFrame(rows)
    for c in ("team_goals", "opp_goals"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def classic_market(boot: Mapping[str, Any]) -> dict[int, dict[str, float]]:
    """Price, start price, ownership and net transfers by player code, from the
    classic game (the draft game has no prices)."""
    out: dict[int, dict[str, float]] = {}
    for e in boot.get("elements") or []:
        now = float(e.get("now_cost") or 0)
        out[int(e["code"])] = {
            "value": now,
            "start_value": now - float(e.get("cost_change_start") or 0),
            "selected": float(e.get("selected_by_percent") or 0),
            "transfers_balance": float(e.get("transfers_in_event") or 0)
            - float(e.get("transfers_out_event") or 0),
        }
    return out


def fpl_ep(boot: Mapping[str, Any], classic: Mapping[str, Any]) -> dict[str, float]:
    """FPL's own expected points for the next gameweek, by draft element id.
    Only the classic game publishes them (the draft API leaves ep_next at 0)."""
    by_code = {int(e["code"]): float(e.get("ep_next") or 0) for e in classic.get("elements") or []}
    return {str(e["id"]): by_code[int(e["code"])] for e in boot.get("elements") or []
            if int(e["code"]) in by_code}


def predict_next(
    artifact: M.Artifact,
    boot: Mapping[str, Any],
    fixtures: list[dict[str, Any]],
    lives: Mapping[int, Mapping[str, Any]],
    market: Mapping[int, Mapping[str, Any]],
    next_gw: int,
    last_season: pd.DataFrame | None,
) -> dict[str, float]:
    """{draft element id: expected points next gameweek}."""
    season = season_label(boot.get("events") or {})
    current = season_rows(boot, fixtures, lives, market, season, next_gw)
    if current.empty:
        return {}
    frame = pd.concat([last_season, current], ignore_index=True) if last_season is not None else current
    feats = F.build(frame)
    target = feats[(feats["season"] == season) & (feats["gw"] == next_gw)]
    pred = M.predict(artifact.estimator, target)
    return {str(int(e)): round(float(v), 2) for e, v in zip(target["element"], pred, strict=True)}


def run(db: Any, boot: Mapping[str, Any], next_gw: int, structural: Mapping[str, float],
        client: httpx.Client | None = None, say: Callable[[str], None] = print) -> None:
    """Predict, store and grade. Never raises: the board is already written."""
    from fantasy.ml.cli import artifact_path

    path = artifact_path()
    if not path.is_file():
        say(f"no trained FPL model at {path} — run `fantasy ml train`")
        return
    own = client is None
    c = client or httpx.Client(timeout=30, follow_redirects=True,
                               headers={"User-Agent": "fantasy-dashboard"})
    try:
        events = boot.get("events") or {}
        season = season_label(events)
        finished = {int(e["id"]) for e in events.get("data") or [] if e.get("finished")}
        played = sorted(g for g in finished if g < next_gw)
        lives = {gw: live_gw(c, season, gw, True) for gw in played}
        fixtures = c.get(f"{CLASSIC}/fixtures/").json()
        classic = c.get(f"{CLASSIC}/bootstrap-static/").json()
        market = classic_market(classic)
        prev = previous_season(season)
        H.download([prev])
        artifact = M.load(path)
        ml = predict_next(artifact, boot, fixtures, lives, market, next_gw, H.load_season(prev))

        db.put_predictions("fpl", next_gw, "ml", ml)
        db.put_predictions("fpl", next_gw, "structural", {k: round(v, 2) for k, v in structural.items()})
        db.put_predictions("fpl", next_gw, "fpl_ep", fpl_ep(boot, classic))

        for gw in db.ungraded_rounds("fpl", next_gw):
            if gw not in finished:
                continue
            live = lives.get(gw) or live_gw(c, season, gw, True)
            actual = {str(k): float((v.get("stats") or {}).get("total_points") or 0)
                      for k, v in _elements(live).items()}
            n = db.grade_predictions("fpl", gw, actual)
            say(f"graded GW{gw}: {n} predictions")
        say(f"ML predictions for GW{next_gw}: {len(ml)} players (model trained {artifact.trained_at})")
    except Exception:  # noqa: BLE001 — a model hiccup must not fail the sync
        traceback.print_exc()
        say("FPL model predictions skipped")
    finally:
        if own:
            c.close()
