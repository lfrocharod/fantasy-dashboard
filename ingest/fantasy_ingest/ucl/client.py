"""Client for UEFA's Champions League Fantasy backend.

Endpoints were reverse-engineered from the site's own config feed
(`services/feeds/config/web.json`) plus a browser HAR. Two kinds:

* **Static feeds** — `services/feeds/...` — plain JSON, no auth. Players,
  fixtures, teams, config. Reachable from anywhere (incl. CI).
* **User API** — `services/api/...` — needs the site's static `entity` header
  AND the logged-in session cookie. Squad, private leagues, league standings.
  The cookie is pasted into the app (Settings) and passed here as `token`.

Everything is keyed off a competition/"tour" id (currently **90**) and matchday.
Overridable via env: UEFA_COMP_ID, UEFA_FEEDS_BASE, UEFA_API_BASE, UEFA_ENTITY.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Self

import httpx


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v else default


COMP_ID = _env("UEFA_COMP_ID", "90")
FEEDS_BASE = _env("UEFA_FEEDS_BASE", "https://gaming.uefa.com/en/uclfantasy/services/feeds")
API_BASE = _env("UEFA_API_BASE", "https://gaming.uefa.com/en/uclfantasy/services/api")
# Static app key baked into UEFA's site JS; required on every services/api call.
ENTITY = _env("UEFA_ENTITY", "ed0t4n$3!")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://gaming.uefa.com/en/uclfantasy/",
    "Origin": "https://gaming.uefa.com",
}


class UefaError(RuntimeError):
    pass


class UefaAuthError(UefaError):
    pass


@dataclass
class UefaClient:
    # Raw `Cookie:` header value from a logged-in browser (Settings paste box).
    token: str | None = None
    # Kept for signature compatibility; UEFA moved to Gigya SSO so these are unused.
    email: str | None = None
    password: str | None = None
    comp_id: str = COMP_ID
    timeout: float = 30.0

    guid: str | None = None
    auth_state: str = "unknown"  # authed | public_only
    _client: httpx.Client | None = None

    def __enter__(self) -> Self:
        headers = dict(_HEADERS)
        if self.token:
            headers["Cookie"] = self.token.strip()
        self._client = httpx.Client(
            headers=headers, timeout=self.timeout, follow_redirects=True
        )
        return self

    def __exit__(self, *exc: object) -> None:
        if self._client:
            self._client.close()

    # -- low level ---------------------------------------------------------

    def _get_json(self, url: str, *, api: bool) -> Any:
        assert self._client is not None
        headers = {"entity": ENTITY} if api else {}
        r = self._client.get(url, headers=headers)
        if r.status_code in (401, 403):
            raise UefaAuthError(f"{r.status_code} for {url}")
        r.raise_for_status()
        data = r.json()
        # UEFA signals auth failure in-body with retVal -70 and HTTP 200.
        if isinstance(data, dict):
            meta = data.get("meta", {})
            if meta.get("success") is False or meta.get("retVal") == -70:
                raise UefaAuthError(f"{meta.get('message', 'not authorized')}: {url}")
        return data

    def _feed(self, path: str) -> Any:
        return self._get_json(f"{FEEDS_BASE}/{path.lstrip('/')}", api=False)

    def _api(self, path: str) -> Any:
        return self._get_json(f"{API_BASE}/{path.lstrip('/')}", api=True)

    # -- public feeds (no auth) -----------------------------------------

    def get_config(self) -> dict:
        return self._feed("config/web.json")

    def get_teams(self, lang: str = "en") -> Any:
        return self._feed(f"teams/teams_{self.comp_id}_{lang}.json")

    def get_fixtures(self, lang: str = "en") -> Any:
        return self._feed(f"fixtures/fixtures_{self.comp_id}_{lang}.json")

    def get_players(self, matchday: int, lang: str = "en") -> Any:
        return self._feed(f"players/players_{self.comp_id}_{lang}_{matchday}.json")

    # -- user API (needs cookie) --------------------------------------

    def check_auth(self, guid: str | None = None) -> str:
        """Set auth_state by probing a cheap authed endpoint."""
        g = guid or self.guid
        if not self.token or not g:
            self.auth_state = "public_only"
            return self.auth_state
        try:
            self._api(f"Gameplay/user/{g}/gamedays")
            self.auth_state = "authed"
        except UefaAuthError:
            self.auth_state = "public_only"
        return self.auth_state

    def get_my_team(self, guid: str, matchday: int, phase: int = 1) -> Any:
        return self._api(
            f"Gameplay/user/{guid}/team?matchdayId={matchday}&phaseId={phase}"
        )

    def get_private_leagues(self, guid: str) -> Any:
        return self._api(f"Leagues/user/{guid}/private")

    def get_league_standings(self, league_id: str) -> Any:
        return self._api(f"Leagues/{league_id}/stats")

    def get_league_members(self, league_id: str) -> Any:
        return self._api(f"Leagues/{league_id}/members")


__all__ = ["COMP_ID", "UefaAuthError", "UefaClient", "UefaError"]
