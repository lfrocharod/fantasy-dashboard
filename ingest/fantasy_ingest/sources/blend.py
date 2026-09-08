"""Combine signals from several independent sources into one value we trust.

Every projection input we care about — will a player start, is there an injury
scare, how many points will they score — is a blend of a handful of sources
(the game's own feed, a stats provider, recent match data, expert lineups,
betting markets, the official club). This module is the small, testable core
that merges them:

  * each source contributes a `Signal(value, confidence, asof)`;
  * `compose()` returns a confidence-weighted, recency-decayed mean plus a
    `disagreement` score — when sources genuinely conflict, that IS the signal
    (a rotation risk / fitness doubt the point estimate would hide).

Add a source by producing `Signal`s from it; nothing else changes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class Signal:
    source: str  # "uefa_feed", "sofascore_form", "fpl_bootstrap", "official_club", …
    value: float
    confidence: float = 0.6  # 0..1, how much this source is worth for this metric
    asof: float = field(default_factory=time.time)  # unix seconds
    note: str = ""


@dataclass(slots=True)
class Composite:
    value: float
    confidence: float  # aggregate — rises with agreement and number of sources
    disagreement: float  # 0 (sources agree) .. ~1 (they pull hard opposite ways)
    n: int
    parts: list[Signal]

    def why(self) -> str:
        """One-line provenance for the UI / logs."""
        bits = [f"{s.source} {s.value:.2f}" for s in sorted(self.parts, key=lambda x: -x.confidence)]
        tag = " · sources disagree" if self.disagreement >= 0.33 else ""
        return ", ".join(bits) + tag


def _age_decay(asof: float, half_life_h: float) -> float:
    if half_life_h <= 0:
        return 1.0
    age_h = max(0.0, (time.time() - asof) / 3600.0)
    return 0.5 ** (age_h / half_life_h)


def compose(
    signals: list[Signal],
    *,
    prior: float | None = None,
    prior_weight: float = 0.15,
    half_life_h: float = 0.0,
    lo: float = 0.0,
    hi: float = 1.0,
) -> Composite | None:
    """Confidence-weighted mean of `signals`, optionally anchored to `prior`.

    `half_life_h > 0` decays a signal's weight by age (use for lineup news that
    goes stale fast; leave 0 for season-long stats). Result is clamped to
    [lo, hi]. Returns None if there is nothing to go on.
    """
    usable = [s for s in signals if s.confidence > 0]
    if not usable and prior is None:
        return None

    weighted: list[tuple[float, float]] = []  # (value, weight)
    for s in usable:
        w = max(0.0, s.confidence) * _age_decay(s.asof, half_life_h)
        if w > 0:
            weighted.append((min(hi, max(lo, s.value)), w))
    if prior is not None and prior_weight > 0:
        weighted.append((min(hi, max(lo, prior)), prior_weight))

    if not weighted:
        return None

    tw = sum(w for _v, w in weighted)
    mean = sum(v * w for v, w in weighted) / tw

    # disagreement: weighted mean absolute deviation, scaled to the value range
    span = max(1e-6, hi - lo)
    mad = sum(w * abs(v - mean) for v, w in weighted) / tw
    disagreement = min(1.0, (mad / span) * 1.8)

    # aggregate confidence: more sources + agreement -> higher; capped
    base = min(0.95, 0.35 + 0.16 * len(usable))
    agg_conf = round(base * (1.0 - 0.5 * disagreement), 3)

    return Composite(
        value=round(min(hi, max(lo, mean)), 4),
        confidence=agg_conf,
        disagreement=round(disagreement, 3),
        n=len(usable),
        parts=usable,
    )


__all__ = ["Composite", "Signal", "compose"]
