"""Environment + `settings` table access. Keys must match web/lib/settings.ts."""

from __future__ import annotations

import os
from dataclasses import dataclass


class Keys:
    LEAGUE_ID = "ucl.league_id"
    LEAGUE_CODE = "ucl.league_code"
    ENTRY_ID = "ucl.entry_id"
    CURRENT_MATCHDAY = "ucl.current_matchday"
    DEADLINE = "ucl.deadline_iso"
    UEFA_TOKEN = "ucl.uefa_token_enc"
    UEFA_TOKEN_SAVED_AT = "ucl.uefa_token_saved_at"
    UEFA_AUTH_STATE = "ucl.uefa_auth_state"
    MODEL_PARAMS = "model.params"
    OPTIMIZER_OUTPUT = "model.optimizer_output"
    # Live-matchday state blob (CL overview). Written during a live/finished
    # matchday, cleared to "" once the matchday is fully upcoming again.
    LIVE_STATE = "model.live_state"
    # Live rival scores blob (per mini-league entry), same cadence as LIVE_STATE.
    LIVE_RIVALS = "model.live_rivals"
    # In-matchday substitutions the game allows / rolls over (parsed from the
    # fixtures feed; a manual `ucl.subs_allowed` row still wins if you set one).
    SUBS_ALLOWED = "ucl.subs_allowed"
    SUBS_CARRY = "ucl.subs_carry"
    # De-dupe key so the matchday push alert only fires when something changes.
    LAST_ALERT_HASH = "ucl.last_alert_hash"
    # xG name-match coverage from the last run: which players got an underlying
    # stat row and which didn't (so a missed star shows up on the Settings page).
    XG_COVERAGE = "ingest.xg_coverage"


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
    # "sofascore" (all competitions, default) | "understat" (domestic only)
    recent_form_source: str
    recent_form_lookback: int
    # only fetch per-match form for players at/above this price (trims cheap fodder)
    recent_form_min_price: float

    @classmethod
    def load(cls) -> Env:
        # A set-but-empty value (GitHub Actions passing an undefined vars.X) is
        # treated the same as unset.
        def env(name: str, default: str | None = None) -> str | None:
            v = os.environ.get(name)
            return v if v else default

        db = env("DATABASE_URL")
        if not db:
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
            ),
            fbref_season=env("FBREF_SEASON", _season),
            skip_sources=(env("SKIP_SOURCES") or "").lower() in ("1", "true", "yes"),
            # Recent form is the last-N matches OVERALL (CL + domestic + cups),
            # which only Sofascore carries; it's slow-paced + circuit-broken +
            # incrementally cached so it covers all clubs without a hard block.
            # "both" adds Understat domestic logs as a big-5 depth layer;
            # "understat_only" is the offline/debug fallback.
            recent_form_source=(env("RECENT_FORM_SOURCE", "sofascore") or "sofascore").lower(),
            recent_form_lookback=int(env("RECENT_FORM_LOOKBACK", "5") or 5),
            recent_form_min_price=float(env("RECENT_FORM_MIN_PRICE", "4.5") or 4.5),
        )
