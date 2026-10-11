"""`fantasy ml …` — backtest and train the FPL points model. Imported lazily
by the main CLI, so the API image (no ML extra) never loads pandas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from fantasy.ml import backtest as B
from fantasy.ml import features as F
from fantasy.ml import history as H
from fantasy.ml import model as M

DEFAULT_REPORT = Path(__file__).resolve().parents[4] / "docs" / "ml" / "fpl-backtest.md"


def artifact_path() -> Path:
    return H.cache_dir().parent / "ml" / "fpl_points.joblib"


def _frame() -> pd.DataFrame:
    H.download(max_age_days=7)
    return F.build(H.load())


def backtest(block: int, out: Path, report_only: bool = False) -> None:
    feats = _frame()
    cached = H.cache_dir().parent / "ml" / f"backtest-block{block}.parquet"
    if report_only and cached.is_file():
        preds = pd.read_parquet(cached)
    else:
        preds = B.walk_forward(feats, B.TEST_SEASONS, block=block)
        cached.parent.mkdir(parents=True, exist_ok=True)
        preds.to_parquet(cached)
    imp = B.importances(feats, B.TEST_SEASONS[-1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(B.report(preds, feats, imp, block))
    metrics = B.table(preds, regulars_only=True)
    out.with_suffix(".json").write_text(json.dumps(metrics.to_dict(orient="records"), indent=1) + "\n")
    print(f"wrote {out} and {out.with_suffix('.json')}")


def train() -> Path:
    feats = _frame()
    art = M.Artifact(estimator=M.fit(feats), features=list(F.FEATURES),
                     seasons=list(H.SEASONS), trained_rows=len(feats))
    path = artifact_path()
    M.save(art, path)
    print(f"saved {path} ({art.trained_rows:,} rows)")
    return path


def run(args: argparse.Namespace) -> int:
    if args.ml_cmd == "backtest":
        backtest(args.block, Path(args.out) if args.out else DEFAULT_REPORT, args.report_only)
    else:
        train()
    return 0
