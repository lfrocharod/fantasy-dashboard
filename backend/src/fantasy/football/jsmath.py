"""JavaScript-compatible rounding.

The views were ported from TypeScript, where `Math.round` rounds halves up;
Python's `round` rounds halves to even (round(2.5) == 2). These keep the
ported numbers identical to what the old app showed.
"""

from __future__ import annotations

import math


def js_round(x: float) -> int:
    """Math.round: nearest integer, halves towards +infinity."""
    return math.floor(x + 0.5)


def round1(x: float) -> float:
    """Math.round(x * 10) / 10."""
    return math.floor(x * 10 + 0.5) / 10


def js_to_fixed(x: float, digits: int) -> str:
    """Number.prototype.toFixed: rounds the exact binary value half away from
    zero (Python's format() rounds half to even)."""
    from decimal import ROUND_HALF_UP, Decimal

    q = Decimal(1).scaleb(-digits)
    return str(Decimal(x).quantize(q, rounding=ROUND_HALF_UP))
