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
        return cls(
            database_url=db,
            uefa_email=env("UEFA_EMAIL"),
            uefa_password=env("UEFA_PASSWORD"),
            web_crypto_key=env("WEB_CRYPTO_KEY"),
            source_leagues=env(
                "SOURCE_LEAGUES",
                "ENG-Premier League,ESP-La Liga,GER-Bundesliga,ITA-Serie A,FRA-Ligue 1",
            ),
            fbref_season=env("FBREF_SEASON"),
            skip_sources=(env("SKIP_SOURCES") or "").lower() in ("1", "true", "yes"),
            recent_form_source=(env("RECENT_FORM_SOURCE", "sofascore") or "sofascore").lower(),
            recent_form_lookback=int(env("RECENT_FORM_LOOKBACK", "5") or 5),
            recent_form_min_price=float(env("RECENT_FORM_MIN_PRICE", "4.5") or 4.5),
        )
