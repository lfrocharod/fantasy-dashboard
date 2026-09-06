"""Tunable model parameters. Overridable per deployment via the `model.params`
settings row (JSON), merged over these defaults."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(slots=True)
class ModelParams:
    # Weight given to UEFA's own recent form (points/match) vs the xG model.
    form_weight: float = 0.30
    # Home team xG multiplier (away divides by it).
    home_adv: float = 1.12
    # Average goals scored by one team in one match (competition baseline).
    league_avg_goals: float = 1.45
    # Shots on target produced per unit of xG (for GK save estimation).
    sot_per_xg: float = 3.1
    gk_save_pct_default: float = 0.69
    # Expected point drag from cards, per appearance.
    discipline_rate: float = 0.16
    # Monte-Carlo draws for the ceiling / floor.
    sim_n: int = 1500
    # Matchdays to look ahead in the transfer planner.
    horizon: int = 2
    # Minutes model.
    starter_minutes: float = 82.0
    sub_minutes: float = 11.0
    sub_appearance_prob: float = 0.12

    @classmethod
    def load(cls, raw: str | None) -> ModelParams:
        p = cls()
        if not raw:
            return p
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return p
        for k, v in data.items():
            if hasattr(p, k) and isinstance(v, (int, float)):
                setattr(p, k, type(getattr(p, k))(v))
        return p

    def to_dict(self) -> dict:
        return asdict(self)
