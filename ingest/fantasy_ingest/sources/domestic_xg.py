"""External underlying stats (xG / xA / minutes / shots / SCA / recoveries).

Primary source: FBref via `soccerdata` (Big-5 league season stats). Understat is a
cross-check / gap-filler. `soccerdata` and `pandas` are heavy and only needed
here, so they're imported lazily and the whole module is optional: if the import
or scrape fails, `run.py` carries on and the projection model falls back to
UEFA's own form numbers.

Output: a list of `SourceRow` — one per source player, with a normalised
name + team string for fuzzy matching against the UEFA player list.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(slots=True)
class SourceRow:
    name: str
    norm_name: str
    team: str
    norm_team: str
    minutes: float
    matches: int
    npxg90: float
    xag90: float
    shots90: float
    sca90: float
    recoveries90: float
    save_pct: float
    source: str


def normalise(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().replace(".", " ").replace("-", " ").split())


def _col(df, *candidates):
    """Return the first matching flattened column name present in df, else None."""
    flat = {}
    for c in df.columns:
        key = c if isinstance(c, str) else " ".join(str(x) for x in c if str(x) not in ("", "nan"))
        flat[key.lower().strip()] = c
        if not isinstance(c, str):
            flat[str(c[-1]).lower().strip()] = c
    for cand in candidates:
        hit = flat.get(cand.lower())
        if hit is not None:
            return hit
    return None


def _per90(value: float, minutes: float) -> float:
    return float(value) / (minutes / 90.0) if minutes and minutes > 0 else 0.0


def fetch_fbref_rows(leagues: list[str], season: str | None) -> list[SourceRow]:  # pragma: no cover - network/heavy
    import soccerdata as sd

    seasons = [season] if season else None
    fb = sd.FBref(leagues=leagues, seasons=seasons)

    std = fb.read_player_season_stats("standard").reset_index()
    try:
        sht = fb.read_player_season_stats("shooting").reset_index()
    except Exception:  # noqa: BLE001
        sht = None
    try:
        gca = fb.read_player_season_stats("goal_shot_creation").reset_index()
    except Exception:  # noqa: BLE001
        gca = None
    try:
        misc = fb.read_player_season_stats("misc").reset_index()
    except Exception:  # noqa: BLE001
        misc = None
    try:
        gk = fb.read_player_season_stats("keeper").reset_index()
    except Exception:  # noqa: BLE001
        gk = None

    c_player = _col(std, "player")
    c_team = _col(std, "team", "squad")
    c_min = _col(std, "playing time min", "min", "minutes")
    c_mp = _col(std, "playing time mp", "mp", "matches")
    c_npxg = _col(std, "expected npxg", "npxg")
    c_xag = _col(std, "expected xag", "xag", "expected xa", "xa")

    def key(row) -> tuple[str, str]:
        return (normalise(row[c_player]), normalise(row[c_team]))

    shots_by = _index_metric(sht, "player", ("team", "squad"), ("standard sh", "sh", "shooting sh"))
    sca_by = _index_metric(gca, "player", ("team", "squad"), ("sca sca", "sca"))
    recov_by = _index_metric(misc, "player", ("team", "squad"), ("performance recov", "recov"))
    save_by = _index_metric(gk, "player", ("team", "squad"), ("performance save%", "save%"), per90=False)

    rows: list[SourceRow] = []
    for _, r in std.iterrows():
        minutes = float(r[c_min] or 0) if c_min else 0.0
        if minutes < 1:
            continue
        k = key(r)
        rows.append(
            SourceRow(
                name=str(r[c_player]),
                norm_name=k[0],
                team=str(r[c_team]),
                norm_team=k[1],
                minutes=minutes,
                matches=int(float(r[c_mp] or 0)) if c_mp else 0,
                npxg90=_per90(r[c_npxg] if c_npxg else 0.0, minutes),
                xag90=_per90(r[c_xag] if c_xag else 0.0, minutes),
                shots90=_per90(shots_by.get(k, 0.0), minutes),
                sca90=_per90(sca_by.get(k, 0.0), minutes),
                recoveries90=_per90(recov_by.get(k, 0.0), minutes),
                save_pct=_frac(save_by.get(k, 0.0)),
                source="fbref",
            )
        )
    return rows


def _index_metric(df, player_col: str, team_cols: tuple[str, ...], metric_cols: tuple[str, ...], per90: bool = True):
    out: dict[tuple[str, str], float] = {}
    if df is None:
        return out
    cp = _col(df, player_col)
    ct = _col(df, *team_cols)
    cm = _col(df, *metric_cols)
    if cp is None or ct is None or cm is None:
        return out
    for _, r in df.iterrows():
        try:
            out[(normalise(r[cp]), normalise(r[ct]))] = float(r[cm] or 0.0)
        except (TypeError, ValueError):
            continue
    return out


def _frac(v: float) -> float:
    v = float(v or 0.0)
    return v / 100.0 if v > 1.5 else v


def fetch_understat_rows(leagues: list[str], season: str | None) -> list[SourceRow]:  # pragma: no cover
    import soccerdata as sd

    us = sd.Understat(leagues=leagues, seasons=[season] if season else None)
    df = us.read_player_season_stats().reset_index()
    c_player = _col(df, "player", "player_name")
    c_team = _col(df, "team", "team_title")
    c_min = _col(df, "minutes", "time")
    c_xg = _col(df, "xg")
    c_xa = _col(df, "xa")
    c_shots = _col(df, "shots")
    rows: list[SourceRow] = []
    for _, r in df.iterrows():
        minutes = float(r[c_min] or 0) if c_min else 0.0
        if minutes < 1:
            continue
        npxg = float(r[c_xg] or 0) if c_xg else 0.0  # understat xg already excludes pens in npg; keep xg as proxy
        rows.append(
            SourceRow(
                name=str(r[c_player]),
                norm_name=normalise(r[c_player]),
                team=str(r[c_team]),
                norm_team=normalise(r[c_team]),
                minutes=minutes,
                matches=0,
                npxg90=_per90(npxg, minutes),
                xag90=_per90(r[c_xa] if c_xa else 0.0, minutes),
                shots90=_per90(r[c_shots] if c_shots else 0.0, minutes),
                sca90=0.0,
                recoveries90=0.0,
                save_pct=0.0,
                source="understat",
            )
        )
    return rows
