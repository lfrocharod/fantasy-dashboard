from fantasy.leagues.nfl import nflverse


def test_norm_name_strips_suffix_and_accents():
    assert nflverse.norm_name("Michael Pittman Jr.") == "michael pittman"
    assert nflverse.norm_name("Amon-Ra St. Brown") == "amon ra st brown"


def test_fetch_usage_empty_on_404(monkeypatch):
    monkeypatch.setattr(nflverse, "_get_csv", lambda url: [])
    assert nflverse.fetch_usage(1999) == {}


def test_fetch_usage_aggregates_last_n(monkeypatch):
    snaps = [
        {"player": "Bijan Robinson", "team": "ATL", "week": "1", "offense_pct": "0.60"},
        {"player": "Bijan Robinson", "team": "ATL", "week": "2", "offense_pct": "0.80"},
        {"player": "Bijan Robinson", "team": "ATL", "week": "3", "offense_pct": "0.90"},
    ]
    weekly = [
        {"player_display_name": "Bijan Robinson", "team": "ATL", "week": "3",
         "target_share": "0.18", "wopr": "0.55", "carries": "18", "receptions": "5"},
    ]
    monkeypatch.setattr(
        nflverse, "_get_csv",
        lambda url: snaps if "snap_counts" in url else weekly,
    )
    u = nflverse.fetch_usage(2025, last_n=3)
    key = ("bijan robinson", "ATL")
    assert key in u
    assert abs(u[key]["snap_pct"] - 0.767) < 0.01
    assert u[key]["snap_trend"] > 0  # 0.90 last vs 0.70 prior mean
    assert u[key]["touches"] == 23.0
    assert u[key]["target_share"] == 0.18
