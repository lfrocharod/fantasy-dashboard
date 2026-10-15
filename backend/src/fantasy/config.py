"""Environment + the keys of the `settings` table (config the app and jobs share)."""

from __future__ import annotations

import os
from dataclasses import dataclass


class Keys:
    LEAGUE_ID = "ucl.league_id"
    LEAGUE_CODE = "ucl.league_code"
    ENTRY_ID = "ucl.entry_id"
    # Manual pin from Settings; blank = follow the game. The resolved matchday
    # itself is written to leagues.current_round, never read back as input.
    MATCHDAY_OVERRIDE = "ucl.matchday_override"
    UEFA_TOKEN = "ucl.uefa_token_enc"
    UEFA_TOKEN_SAVED_AT = "ucl.uefa_token_saved_at"
    UEFA_AUTH_STATE = "ucl.uefa_auth_state"
    MODEL_PARAMS = "model.params"
    # In-matchday substitutions the game allows / rolls over (parsed from the
    # fixtures feed; a manual `ucl.subs_allowed` row still wins if you set one).
    SUBS_ALLOWED = "ucl.subs_allowed"
    SUBS_CARRY = "ucl.subs_carry"
    # De-dupe key so the matchday push alert only fires when something changes.
    LAST_ALERT_HASH = "ucl.last_alert_hash"


class Docs:
    """Keys of the `documents` table: computed outputs the UI reads whole."""

    UCL_OPTIMIZER = "ucl.optimizer"
    # Live-matchday state (CL overview). Present while a matchday is live or
    # just finished; removed once the next matchday is fully upcoming.
    UCL_LIVE_STATE = "ucl.live_state"
    # Live rival scores (per mini-league entry), same cadence as UCL_LIVE_STATE.
    UCL_LIVE_RIVALS = "ucl.live_rivals"
    # xPts model calibration vs actual matchday points.
    UCL_CALIBRATION = "ucl.calibration"
    # xG name-match coverage from the last run (which players got a stat row).
    UCL_XG_COVERAGE = "ucl.xg_coverage"
    # FPL Draft live gameweek (points banked, H2H score), while a GW is on.
    FPL_LIVE = "fpl.live"
    # ESPN basketball: rules, the matchup calendar and the NBA schedule.
    NBA_LEAGUE = "nba.league"


@dataclass(slots=True)
class Env:
    database_url: str
    uefa_email: str | None
    uefa_password: str | None
    web_crypto_key: str | None
    # Comma-separated Understat league names for the (fallback) domestic source.
    source_leagues: str
    fbref_season: str | None
    skip_sources: bool
    # "understat" (big-five domestic leagues, default) | "sofascore" (all
    # competitions; refuses this app since 2026-10) | "both"
    recent_form_source: str
    recent_form_lookback: int
    # only fetch per-match form for players at/above this price (trims cheap fodder)
    recent_form_min_price: float

    @classmethod
    def load(cls, *, require_db: bool = True) -> Env:
        # A set-but-empty value (GitHub Actions passing an undefined vars.X) is
        # treated the same as unset.
        def env(name: str, default: str | None = None) -> str | None:
            v = os.environ.get(name)
            return v if v else default

        db = env("DATABASE_URL") or ""
        if require_db and not db:
            raise RuntimeError("DATABASE_URL not set")
        # Understat / FBref season = the start year of the current campaign
        # (e.g. "2026" for 2026/27). European seasons roll over in July.
        import datetime as _dt

        _now = _dt.datetime.now(tz=_dt.UTC)
        _season = str(_now.year if _now.month >= 7 else _now.year - 1)
        return cls(
            database_url=db,
            uefa_email=env("UEFA_EMAIL"),
            uefa_password=env("UEFA_PASSWORD"),
            web_crypto_key=env("WEB_CRYPTO_KEY"),
            source_leagues=env(
                "SOURCE_LEAGUES",
                "ENG-Premier League,ESP-La Liga,GER-Bundesliga,ITA-Serie A,FRA-Ligue 1",
            ) or "",
            fbref_season=env("FBREF_SEASON", _season),
            skip_sources=(env("SKIP_SOURCES") or "").lower() in ("1", "true", "yes"),
            # Recent form is the last-N matches OVERALL (CL + domestic + cups),
            # which only Sofascore carries; it's slow-paced + circuit-broken +
            # incrementally cached so it covers all clubs without a hard block.
            # "both" adds Understat domestic logs as a big-5 depth layer;
            # "understat_only" is the offline/debug fallback.
            recent_form_source=(env("RECENT_FORM_SOURCE", "understat") or "understat").lower(),
            recent_form_lookback=int(env("RECENT_FORM_LOOKBACK", "5") or 5),
            recent_form_min_price=float(env("RECENT_FORM_MIN_PRICE", "4.5") or 4.5),
        )


def load_env_file(path: str | os.PathLike[str] | None = None) -> str | None:
    """Fill os.environ from a KEY=VALUE file without overriding what is already
    set. Values are taken literally (no shell expansion) — secrets contain $, &
    and !. Looks at $FANTASY_ENV_FILE, then ./.env. Returns the path used."""
    candidates = [path] if path else [os.environ.get("FANTASY_ENV_FILE"), ".env"]
    for cand in candidates:
        if not cand or not os.path.isfile(cand):
            continue
        with open(cand, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip().removeprefix("export ").strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                os.environ.setdefault(key, value)
        return str(cand)
    return None
