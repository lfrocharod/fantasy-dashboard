"""Single-user auth: one password (bcrypt hash in APP_PASSWORD_HASH) mints a
signed session cookie. Wire-compatible with the previous app — the same hash
and SESSION_SECRET keep existing sessions and passwords working."""

from __future__ import annotations

import os
import time
from collections import deque

import bcrypt
import jwt

SESSION_COOKIE = "fd_session"
MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days


def _secret() -> str:
    s = os.environ.get("SESSION_SECRET", "")
    if len(s) < 16:
        raise RuntimeError("SESSION_SECRET must be set (>= 16 chars)")
    return s


def password_ok(password: str) -> bool:
    hashed = os.environ.get("APP_PASSWORD_HASH", "")
    if not hashed:
        raise RuntimeError("APP_PASSWORD_HASH is not set")
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_session_token(now: float | None = None) -> str:
    iat = int(now if now is not None else time.time())
    return jwt.encode({"ok": True, "iat": iat, "exp": iat + MAX_AGE_SECONDS}, _secret(), algorithm="HS256")


def verify_session_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return False
    return True


class LoginThrottle:
    """At most `limit` failed logins per client per window (per instance —
    enough to make guessing a single-user password pointless)."""

    def __init__(self, limit: int = 10, window_s: float = 600.0) -> None:
        self.limit, self.window = limit, window_s
        self._fails: dict[str, deque[float]] = {}

    def blocked(self, client: str) -> bool:
        q = self._fails.get(client)
        if not q:
            return False
        cutoff = time.monotonic() - self.window
        while q and q[0] < cutoff:
            q.popleft()
        return len(q) >= self.limit

    def failed(self, client: str) -> None:
        self._fails.setdefault(client, deque()).append(time.monotonic())

    def reset(self, client: str) -> None:
        self._fails.pop(client, None)


def demo_mode() -> bool:
    """Public read-only demo: no login, seeded data, writes refused."""
    return os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")
