"""Thin cached client for Sofascore's public API.

Sofascore fronts Cloudflare, so plain httpx gets a 403 from datacenter IPs;
`curl_cffi` with a real Chrome TLS fingerprint gets through. Responses are
cached to disk so a re-run only fetches new matches.

No key needed. Be polite: small delay between calls, backoff on 429/403.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

try:
    from curl_cffi import requests as _cr
except ImportError:  # pragma: no cover
    _cr = None

_BASE = "https://api.sofascore.com/api/v1"
_CACHE = Path.home() / ".cache" / "fantasy-ingest" / "sofascore"


class SofaError(RuntimeError):
    pass


class SofaClient:
    def __init__(self, *, delay: float = 0.18, ttl_hours: float = 12.0):
        if _cr is None:
            raise SofaError("curl_cffi not installed — pip install curl_cffi")
        self._s = _cr.Session(impersonate="chrome", timeout=25)
        self._delay = delay
        self._cooldown = 0.0  # extra per-call sleep, grows under sustained throttling
        self._ttl = ttl_hours * 3600
        self._block_streak = 0  # consecutive fully-failed calls (no 200)
        self._calls = 0
        _CACHE.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, path: str) -> Path:
        safe = path.strip("/").replace("/", "_").replace("?", "_").replace("&", "_")
        return _CACHE / f"{safe}.json"

    def get(self, path: str, *, cache: bool = True, allow_404: bool = False) -> dict | None:
        cp = self._cache_path(path)
        if cache and cp.exists() and (time.time() - cp.stat().st_mtime) < self._ttl:
            try:
                return json.loads(cp.read_text())
            except json.JSONDecodeError:
                pass
        # Circuit breaker: once Sofascore has hard-blocked ~10 calls in a row,
        # stop grinding through multi-minute backoffs for every remaining
        # request — fail fast and let the caller fall back to stored data. Retry
        # for real only every 25th call in case the block lifts.
        self._calls += 1
        if self._block_streak >= 10 and self._calls % 25 != 0:
            raise SofaError(f"circuit-open (blocked x{self._block_streak}) {path}")

        # Exponential backoff on 403/429 — Sofascore throttles a busy IP for
        # minutes; give it some time to recover, but fewer attempts once we're
        # clearly being blocked.
        max_attempts = 3 if self._block_streak >= 4 else 6
        for attempt in range(max_attempts):
            time.sleep(self._delay + self._cooldown)
            try:
                r = self._s.get(_BASE + path)
            except Exception as e:
                if attempt == max_attempts - 1:
                    self._block_streak += 1
                    raise SofaError(f"transport error {path}: {e}") from e
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code == 200:
                self._cooldown = max(0.0, self._cooldown - 0.4)
                self._block_streak = 0
                data = r.json()
                if cache:
                    cp.write_text(json.dumps(data))
                return data
            if r.status_code == 404:
                if allow_404:
                    return None
                raise SofaError(f"404 {path}")
            if r.status_code in (403, 429):
                wait = min(45.0, 2.0 ** attempt)
                self._cooldown = min(4.0, self._cooldown + 0.5)
                time.sleep(wait)
                continue
            raise SofaError(f"{r.status_code} {path}")
        self._block_streak += 1
        raise SofaError(f"rate-limited on {path}")

    # -- convenience -----------------------------------------------------

    def search_team(self, name: str) -> int | None:
        d = self.get(f"/search/all?q={name}&page=0", allow_404=True) or {}
        from rapidfuzz import fuzz

        q = name.lower().strip()
        best_id, best_s, first_club = None, 0.0, None
        for row in d.get("results", []):
            if row.get("type") != "team":
                continue
            ent = row.get("entity", {}) or {}
            tid = ent.get("id")
            # We want CLUBS. "Porto" must not resolve to the Portugal national
            # team (which carries every Portuguese star's career history).
            if ent.get("national"):
                continue
            if (ent.get("sport") or {}).get("name") not in (None, "Football"):
                continue
            if first_club is None:
                first_club = tid
            nm = (ent.get("name") or "").lower()
            s = fuzz.token_set_ratio(q, nm) / 100.0
            if any(t in f" {nm} " for t in (" w ", " women", " u19", " u21", " u23", " youth", " ii ")):
                s -= 0.25
            if s > best_s:
                best_id, best_s = tid, s
        if best_id is not None and best_s >= 0.5:
            return best_id
        return first_club

    def team_players(self, team_id: int) -> list[dict]:
        d = self.get(f"/team/{team_id}/players") or {}
        return d.get("players", [])

    def player_last_events(self, player_id: int) -> dict:
        return self.get(f"/player/{player_id}/events/last/0") or {}

    def team_events_next(self, team_id: int) -> list[dict]:
        d = self.get(f"/team/{team_id}/events/next/0", allow_404=True) or {}
        return d.get("events", []) or []

    def team_events_last(self, team_id: int) -> list[dict]:
        d = self.get(f"/team/{team_id}/events/last/0", allow_404=True) or {}
        return d.get("events", []) or []

    def player_match_stats(self, event_id: int, player_id: int) -> dict | None:
        d = self.get(
            f"/event/{event_id}/player/{player_id}/statistics", allow_404=True
        )
        return (d or {}).get("statistics") if d else None

    def event_lineups(self, event_id: int, *, fresh: bool = False) -> dict | None:
        # near kickoff a lineup flips from predicted -> confirmed within the
        # hour, so a matchday pull must bypass the disk cache.
        return self.get(f"/event/{event_id}/lineups", cache=not fresh, allow_404=True)

    def lineup_slot(self, event_id: int, player_id: int) -> dict | None:
        """This player's row in a match lineup: {position, substitute, ...}."""
        lu = self.event_lineups(event_id) or {}
        for side in ("home", "away"):
            for row in (lu.get(side) or {}).get("players", []):
                if (row.get("player") or {}).get("id") == player_id:
                    return row
        return None
