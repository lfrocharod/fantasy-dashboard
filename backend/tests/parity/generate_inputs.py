"""Generate the randomised FPL / NFL boards the parity goldens were recorded on.

    uv run python tests/parity/generate_inputs.py   # -> tests/parity/inputs.json

Seeded, so re-running reproduces the committed file. The shapes mirror
`draft_players` rows (camelCase, as the old web app's API returned them), with
edge cases on purpose: injured/suspended players, byes, missing stats, odd
statuses, tied values, news strings that hit the stash regexes.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).with_name("inputs.json")

FPL_TEAMS = ["ARS", "AVL", "BOU", "BRE", "BHA", "CHE", "CRY", "EVE", "FUL", "LIV",
             "MCI", "MUN", "NEW", "NFO", "TOT", "WHU", "SUN", "LEE", "BUR", "WOL"]
NEWS = ["", "", "", "Knock - 75% chance of playing", "Hamstring injury - Expected back 25 Oct",
        "Unknown return date", "ACL injury - out for the season", "Suspended until 02 Nov",
        "Ankle - late fitness test", "Illness - assessed", "Long-term knee injury",
        "Expected back 14 Nov"]


def r1(x: float) -> float:
    return round(x, 1)


def fpl_board(rng: random.Random) -> dict:
    players = []
    managers = ["101", "202", "303", "404", "505"]
    names = {"101": "Me United", "202": "Rival A", "303": "Rival B", "404": "", "505": "Rival D"}
    pos_cycle = ["GKP"] * 2 + ["DEF"] * 6 + ["MID"] * 7 + ["FWD"] * 4
    for i in range(160):
        pos = pos_cycle[i % len(pos_cycle)]
        team = FPL_TEAMS[i % len(FPL_TEAMS)]
        status = rng.choices(["a", "d", "i", "s", "u", "n"], [80, 8, 7, 2, 2, 1])[0]
        unavailable = status in ("i", "s", "u", "n") or (status == "d" and rng.random() < 0.5)
        gws = []
        for g in range(6):
            blank = rng.random() < 0.04
            xp = 0.0 if blank else r1(rng.uniform(0.5, 8.5))
            gws.append({
                "gw": 8 + g,
                "opp": "" if blank else f"{rng.choice(FPL_TEAMS)} ({rng.choice('HA')})",
                "home": None if blank else rng.random() < 0.5,
                "fdr": 0 if blank else rng.randint(1, 5),
                "fdrAtt": None if blank or rng.random() < 0.1 else rng.randint(1, 5),
                "fdrDef": None if blank or rng.random() < 0.1 else rng.randint(1, 5),
                "xpts": xp,
                "lo": r1(xp * 0.3),
                "hi": r1(xp * 1.9),
                "cs": round(rng.uniform(0, 0.55), 2),
            })
        owner_roll = rng.random()
        owner = rng.choice(managers) if owner_roll < 0.45 else ""
        ros_ppg = r1(rng.uniform(1.2, 6.8))
        players.append({
            "extId": str(1000 + i),
            "name": f"FPL Player {i}",
            "team": team,
            "primaryPos": pos,
            "projPoints": gws[0]["xpts"],
            "providerRank": rng.choice([None, *range(1, 400)]),
            "vbd": r1(rng.uniform(-20, 80)),
            "injuryStatus": status if rng.random() > 0.02 else None,
            "outlook": rng.choice(NEWS) if status != "a" else "",
            "raw": {
                "horizon_xpts": r1(sum(g["xpts"] for g in gws)),
                "fit_next": r1(gws[0]["xpts"] + (1.0 if unavailable else 0.0)),
                "fit_horizon": r1(sum(g["xpts"] for g in gws) + (6.0 if unavailable else 0)),
                "ros_xpts": r1(ros_ppg * 30),
                "ros_ppg": ros_ppg if rng.random() > 0.05 else 0,
                "yellows": rng.randint(0, 9),
                "yc_to_ban": rng.randint(1, 5),
                "susp_risk": rng.random() < 0.08,
                "p_start": round(rng.choice([0, rng.uniform(0.2, 0.99)]), 2),
                "unavailable": unavailable,
                "cs_prob": round(rng.uniform(0, 0.5), 2),
                "xgi90": round(rng.choice([0, rng.uniform(0.05, 0.95)]), 3),
                "ict90": r1(rng.uniform(0, 12)),
                "inf90": r1(rng.uniform(0, 6)),
                "cre90": r1(rng.uniform(0, 6)),
                "thr90": r1(rng.uniform(0, 6)),
                "xgc90": round(rng.choice([0, rng.uniform(0.6, 2.2)]), 3),
                "starts": rng.randint(0, 9),
                "gws": gws,
                "owner": owner,
                "owner_name": names.get(owner, "") if owner and rng.random() < 0.85 else "",
                "available": not owner,
                "set_piece": rng.choice(["", "", "", "P", "F", "C", "P,F", "F,C"]),
                "next_opp": gws[0]["opp"],
                "next_fdr": gws[0]["fdr"],
                "form": r1(rng.uniform(0, 9)),
                "minutes": rng.choice([0, 120, 269, 270, 450, 720]),
                "ppg": r1(rng.uniform(0, 7)),
                "total_points": rng.randint(0, 80),
            },
        })
    return {"players": players, "myEntryId": "101",
            "fallbackNames": {"404": "Rival C (standings)"}}


NFL_TEAMS = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET",
             "GB", "HOU", "IND", "JAX", "KC", "LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO",
             "NYG", "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS"]
INJ = ["ACTIVE"] * 14 + ["QUESTIONABLE", "DOUBTFUL", "OUT", "IR", "SUSPENSION"]


def nfl_board(rng: random.Random) -> dict:
    players = []
    pos_cycle = ["QB"] * 2 + ["RB"] * 4 + ["WR"] * 5 + ["TE"] * 2 + ["K", "DST"]
    teams = {t: rng.randint(6, 14) for t in NFL_TEAMS}  # bye week per pro team
    for i in range(220):
        pos = pos_cycle[i % len(pos_cycle)]
        team = NFL_TEAMS[i % len(NFL_TEAMS)]
        bye = teams[team]
        matchups = []
        for w in range(6, 14):
            if w == bye:
                matchups.append({"week": w, "opp": "BYE", "home": None, "fdr": 0})
            elif rng.random() < 0.03:
                matchups.append({"week": w, "opp": "", "home": None, "fdr": 0})
            else:
                matchups.append({"week": w, "opp": rng.choice(NFL_TEAMS), "home": rng.random() < 0.5,
                                 "fdr": rng.randint(1, 5)})
        owner = rng.choice([None, *range(1, 11)]) if rng.random() < 0.7 else None
        usage_games = rng.choice([0, 1, 2, 3, 4])
        exp_games = rng.choice([0, 1, 2, 4])
        week_proj = r1(rng.uniform(0, 26))
        players.append({
            "extId": str(5000 + i),
            "name": f"NFL Player {i}",
            "team": team if rng.random() > 0.01 else "",
            "primaryPos": pos,
            "projPoints": week_proj,
            "vbd": r1(rng.uniform(-30, 120)),
            "ecrRank": rng.choice([None, *range(1, 300)]),
            "ecrTier": rng.choice([None, *range(1, 15)]),
            "raw": {
                "weekProj": week_proj,
                "rosProj": r1(rng.choice([0, rng.uniform(10, 260)])),
                "bye": bye,
                "onBye": matchups[0]["opp"] == "BYE",
                "injury": rng.choice(INJ),
                "pctOwned": r1(rng.uniform(0, 100)),
                "pctStarted": r1(rng.uniform(0, 100)),
                "slot": rng.choice(["QB", "RB", "WR", "TE", "FLEX", "DST", "K", "BE", "BE", "IR", ""])
                if owner else "",
                "ownerTeamId": owner,
                "ownerName": f"Team Name {owner}" if owner and rng.random() < 0.9 else "",
                "available": owner is None,
                "matchups": matchups,
                "snapPct": round(rng.choice([0, rng.uniform(0.2, 1.0)]), 2),
                "snapTrend": round(rng.uniform(-0.2, 0.2), 2),
                "targetShare": round(rng.uniform(0, 0.35), 2),
                "wopr": round(rng.uniform(0, 0.8), 2),
                "touches": r1(rng.uniform(0, 25)),
                "usageGames": usage_games,
                "usageStale": rng.random() < 0.1,
                "xfpG": r1(rng.uniform(0, 22)),
                "xtdG": round(rng.uniform(0, 1.2), 2),
                "fpOE": r1(rng.uniform(-6, 6)),
                "expGames": exp_games,
            },
        })
    standings = [
        {"team_id": t, "name": f"Team Name {t}", "wins": rng.randint(0, 5), "losses": rng.randint(0, 5),
         "ties": rng.choice([0, 0, 0, 1]), "pf": r1(rng.uniform(400, 700))}
        for t in range(1, 11)
    ]
    schedule = []
    for w in range(6, 14):
        order = list(range(1, 11))
        rng.shuffle(order)
        for k in range(0, 10, 2):
            schedule.append({"week": w, "home": order[k], "away": order[k + 1]})
    return {"players": players, "myTeamId": 3, "standings": standings, "schedule": schedule,
            "slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "DST": 1, "K": 1},
            "week": 6, "regWeeks": 13, "playoffTeams": 4}


def main() -> None:
    rng = random.Random(20261010)
    data = {"fpl": fpl_board(rng), "nfl": nfl_board(rng)}
    # a few concrete trades to evaluate (ext ids drawn from the FPL board)
    fpl_players = data["fpl"]["players"]
    fpl_ids = [p["extId"] for p in fpl_players]
    trades = [{"give": rng.sample([p["extId"] for p in fpl_players if p["raw"]["owner"] == "101"], k),
               "get": rng.sample(fpl_ids, k + extra)}
              for k, extra in ((1, 0), (1, 1), (2, 0))]
    # position-balanced swaps: each give matched by a rival's player in the same slot
    for owner in ("101", "202", "303", "505"):
        mine = [p for p in fpl_players if p["raw"]["owner"] == owner]
        theirs = [p for p in fpl_players if p["raw"]["owner"] not in ("", owner)]
        for k in (1, 1, 2, 2, 3):
            give = rng.sample(mine, k)
            get = []
            for g in give:
                cands = [t for t in theirs if t["primaryPos"] == g["primaryPos"] and t not in get]
                if cands:
                    get.append(rng.choice(cands))
            if len(get) == k:
                trades.append({"owner": owner, "give": [x["extId"] for x in give],
                               "get": [x["extId"] for x in get]})
    data["fpl"]["trades"] = trades
    data["nfl"]["trades"] = [
        {"give": rng.sample([p["extId"] for p in data["nfl"]["players"] if p["raw"]["ownerTeamId"] == 3], 1),
         "get": rng.sample([p["extId"] for p in data["nfl"]["players"]], 1)}
        for _ in range(4)
    ]
    OUT.write_text(json.dumps(data, indent=None, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
