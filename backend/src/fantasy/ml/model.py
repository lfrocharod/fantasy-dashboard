"""The estimator: gradient-boosted trees on per-fixture points.

HistGradientBoostingRegressor because the features are mixed-scale, partly
missing by construction (no xG before 2022-23, no defensive contributions
before 2025-26, nothing for a debutant) and interact (a defender's clean-sheet
odds matter, a forward's don't): trees take NaN natively and need no scaling.
Squared error, because what a manager wants is the *expected* score.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from fantasy.ml.features import FEATURES

PARAMS: dict[str, Any] = {
    "learning_rate": 0.05,
    "max_iter": 400,
    "max_leaf_nodes": 31,
    "min_samples_leaf": 80,
    "l2_regularization": 1.0,
}


def make_estimator(random_state: int = 0) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="squared_error",
        categorical_features=["pos"],
        early_stopping=False,
        random_state=random_state,
        **PARAMS,
    )


def usable(rows: pd.DataFrame, features: Sequence[str] = FEATURES) -> list[str]:
    """Features that vary in this training window. An all-missing one (no
    defensive-contribution stats before 2025-26) carries no signal and trips
    the binner, so it is left out of that fit."""
    return [f for f in features if rows[f].nunique(dropna=True) > 1]


def fit(
    rows: pd.DataFrame, features: Sequence[str] = FEATURES, random_state: int = 0
) -> HistGradientBoostingRegressor:
    est = make_estimator(random_state)
    est.fit(rows[usable(rows, features)], rows["y_pf"], sample_weight=rows["n_fix"])
    return est


def predict(est: HistGradientBoostingRegressor, rows: pd.DataFrame) -> np.ndarray:
    """Expected points for the gameweek (per-fixture estimate × fixtures)."""
    x = rows[list(est.feature_names_in_)]
    return np.asarray(est.predict(x)) * rows["n_fix"].to_numpy()


@dataclass
class Artifact:
    estimator: HistGradientBoostingRegressor
    features: list[str]
    seasons: list[str]
    trained_rows: int
    trained_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))


def save(artifact: Artifact, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    joblib.dump(artifact, tmp)
    tmp.replace(path)


def load(path: Path) -> Artifact:
    artifact = joblib.load(path)
    if not isinstance(artifact, Artifact) or artifact.features != FEATURES:
        raise ValueError(f"{path} was trained with a different feature set — retrain it")
    return artifact
