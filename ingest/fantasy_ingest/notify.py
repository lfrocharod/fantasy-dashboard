"""Opt-in push notifications for time-sensitive matchday events.

Set one of these in the environment (or ingest/.env):

  * ``NTFY_TOPIC``    — an ntfy.sh topic; a POST to https://ntfy.sh/<topic>
                        arrives as a phone push if you've subscribed in the app.
  * ``NTFY_URL``      — full base URL for a self-hosted ntfy (``NTFY_TOPIC`` still
                        names the topic).
  * ``ALERT_WEBHOOK`` — any URL; receives ``{"title": ..., "text": ...}`` JSON.

No dependency on the rest of the package — best-effort, never raises.
"""

from __future__ import annotations

import json
import os
import urllib.request


def _post(url: str, data: bytes, headers: dict[str, str], timeout: float = 8.0) -> bool:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:  # noqa: BLE001
        return False


def notify(title: str, text: str) -> bool:
    """Send `title`/`text` to whichever channel is configured. Returns True if a
    channel was configured and accepted it."""
    topic = os.environ.get("NTFY_TOPIC")
    webhook = os.environ.get("ALERT_WEBHOOK")
    sent = False
    if topic:
        base = (os.environ.get("NTFY_URL") or "https://ntfy.sh").rstrip("/")
        sent = _post(
            f"{base}/{topic}",
            text.encode("utf-8"),
            {"Title": title, "Tags": "soccer", "Priority": "default"},
        ) or sent
    if webhook:
        sent = _post(
            webhook,
            json.dumps({"title": title, "text": text}).encode("utf-8"),
            {"Content-Type": "application/json"},
        ) or sent
    return sent
