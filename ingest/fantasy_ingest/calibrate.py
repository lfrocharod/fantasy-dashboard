"""Grade the xPts model against what actually happened.

Joins the frozen pre-match `projections` against `player_scores` (UEFA's real
matchday points) for every finished matchday and reports error, bias and
calibration — overall, by position, by price band, and by predicted-points
bucket.

    python -m fantasy_ingest.calibrate            # all finished matchdays
    python -m fantasy_ingest.calibrate --matchday 3
    python -m fantasy_ingest.calibrate --played-only   # ignore 0-minute players

Reads `DATABASE_URL` the same way the ingest job does. Read-only.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import UTC, datetime

from .config import Env
from .db import DB


def _fetch(db: DB, matchday: int | None, played_only: bool) -> list[dict]:
    q = """
        select s.matchday, s.player_id, pl.name, pl.position, pl.price,
               s.points, s.played, pr.xpts, pr.xpts_low, pr.xpts_high, pr.p_start
        from player_scores s
        join projections pr on pr.player_id = s.player_id and pr.matchday = s.matchday
        join players pl on pl.uefa_player_id = s.player_id
        where s.final = true
    """
    params: list = []
    if matchday is not None:
        q += " and s.matchday = %s"
        params.append(matchday)
    if played_only:
        q += " and s.played = true"
    with db.conn() as c:
        rows = c.execute(q, tuple(params)).fetchall()
    cols = ["matchday", "player_id", "name", "position", "price", "points", "played",
            "xpts", "xpts_low", "xpts_high", "p_start"]
    return [dict(zip(cols, r, strict=True)) for r in rows]


def _stats(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    err = [r["points"] - r["xpts"] for r in rows]
    mae = sum(abs(e) for e in err) / n
    me = sum(err) / n
    rmse = math.sqrt(sum(e * e for e in err) / n)
    # Pearson r between predicted and actual
    ax = sum(r["xpts"] for r in rows) / n
    ay = sum(r["points"] for r in rows) / n
    cov = sum((r["xpts"] - ax) * (r["points"] - ay) for r in rows)
    vx = sum((r["xpts"] - ax) ** 2 for r in rows)
    vy = sum((r["points"] - ay) ** 2 for r in rows)
    r = cov / math.sqrt(vx * vy) if vx > 0 and vy > 0 else 0.0
    # coverage of the simulated [low, high] band
    within = sum(1 for x in rows if x["xpts_low"] - 0.5 <= x["points"] <= x["xpts_high"] + 0.5)
    return {"n": n, "mae": mae, "me": me, "rmse": rmse, "r": r,
            "mean_pred": ax, "mean_act": ay, "band": within / n}


def _line(label: str, s: dict) -> str:
    if not s.get("n"):
        return f"  {label:<16} —"
    return (f"  {label:<16} n={s['n']:<5} MAE={s['mae']:.2f}  bias={s['me']:+.2f}  "
            f"RMSE={s['rmse']:.2f}  r={s['r']:.2f}  pred/act={s['mean_pred']:.2f}/"
            f"{s['mean_act']:.2f}  band={s['band']*100:.0f}%")


def _price_band(p: float) -> str:
    if p < 5:
        return "€<5m"
    if p < 6.5:
        return "€5–6.5m"
    if p < 8.5:
        return "€6.5–8.5m"
    if p < 11:
        return "€8.5–11m"
    return "€11m+"


def _pred_bucket(x: float) -> str:
    lo = int(x // 2) * 2
    return f"{lo}–{lo + 2}" if x < 8 else "8+"


def report(rows: list[dict]) -> str:
    if not rows:
        return ("No finished-matchday data yet — run the ingest during/after a "
                "matchday so `player_scores` fills in, then try again.")
    out: list[str] = []
    mds = sorted({r["matchday"] for r in rows})
    out.append(f"xPts calibration — {len(rows)} player-matchdays across MD {mds}")
    out.append("")
    out.append("Overall")
    out.append(_line("all", _stats(rows)))
    out.append("")
    out.append("By matchday")
    for md in mds:
        out.append(_line(f"MD{md}", _stats([r for r in rows if r["matchday"] == md])))
    out.append("")
    out.append("By position")
    for pos in ("GK", "DEF", "MID", "FWD"):
        out.append(_line(pos, _stats([r for r in rows if r["position"] == pos])))
    out.append("")
    out.append("By price band")
    bands = defaultdict(list)
    for r in rows:
        bands[_price_band(r["price"])].append(r)
    for b in ("€<5m", "€5–6.5m", "€6.5–8.5m", "€8.5–11m", "€11m+"):
        out.append(_line(b, _stats(bands.get(b, []))))
    out.append("")
    out.append("Calibration by predicted bucket (mean predicted should ≈ mean actual)")
    buckets = defaultdict(list)
    for r in rows:
        buckets[_pred_bucket(r["xpts"])].append(r)
    for b in ("0–2", "2–4", "4–6", "6–8", "8+"):
        out.append(_line(b, _stats(buckets.get(b, []))))
    out.append("")
    s = _stats(rows)
    verdict = ("model runs HOT (predicts more than players score) — raise the "
               "regression toward the prior / lower form_weight"
               if s["me"] < -0.3 else
               "model runs COLD — it's underselling returns"
               if s["me"] > 0.3 else
               "bias is small; MAE is the number to beat")
    out.append(f"Takeaway: {verdict}.")
    return "\n".join(out)


def _verdict(s: dict) -> str:
    if not s.get("n"):
        return "no finished-matchday data yet"
    if s["me"] < -0.3:
        return "model runs HOT — predicts more than players score; lower form_weight / lean on the prior"
    if s["me"] > 0.3:
        return "model runs COLD — it's underselling returns"
    return "bias is small; MAE is the number to beat"


def report_json(rows: list[dict]) -> dict:
    """Structured version of `report()` for the dashboard — written to
    `ingest.calibration` each run so the Calibration panel is always current."""
    mds = sorted({r["matchday"] for r in rows})
    ov = _stats(rows)
    by_pos = {p: _stats([r for r in rows if r["position"] == p])
              for p in ("GK", "DEF", "MID", "FWD")}
    by_md = {str(md): _stats([r for r in rows if r["matchday"] == md]) for md in mds}
    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        buckets[_pred_bucket(r["xpts"])].append(r)
    by_bucket = {b: _stats(buckets.get(b, [])) for b in ("0–2", "2–4", "4–6", "6–8", "8+")}
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "matchdays": mds,
        "playerMatchdays": len(rows),
        "overall": ov,
        "byPosition": by_pos,
        "byMatchday": by_md,
        "byBucket": by_bucket,
        "verdict": _verdict(ov),
    }


def compute_and_store(db: DB) -> dict | None:
    """Best-effort: run the calibration and stash it. Returns the blob or None if
    there's nothing finished to grade yet."""
    rows = _fetch(db, None, played_only=False)
    if not rows:
        return None
    blob = report_json(rows)
    db.set_setting("ingest.calibration", json.dumps(blob))
    return blob


def main() -> int:
    ap = argparse.ArgumentParser(prog="fantasy_ingest.calibrate")
    ap.add_argument("--matchday", type=int, default=None)
    ap.add_argument("--played-only", action="store_true",
                    help="exclude players who logged 0 minutes")
    args = ap.parse_args()
    db = DB(Env.load().database_url)
    print(report(_fetch(db, args.matchday, args.played_only)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
