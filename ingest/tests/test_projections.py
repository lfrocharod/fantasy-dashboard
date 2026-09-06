from fantasy_ingest.model.params import ModelParams
from fantasy_ingest.model.projections import project_player, start_probability
from fantasy_ingest.types import Player, PlayerStat, Team

PARAMS = ModelParams()

STRONG = Team(uefa_team_id=1, name="Strong", attack_rating=1.3, defence_rating=0.8)
WEAK = Team(uefa_team_id=2, name="Weak", attack_rating=0.8, defence_rating=1.3)


def _player(pos, pid=10, form=3.0, status=0):
    return Player(uefa_player_id=pid, name="Test Player", team_id=1, position=pos,
                  price=8.0, uefa_form=form, status_code=status)


def _stat(pid=10, npxg90=0.6, xag90=0.3, minutes=1200, matches=15):
    return PlayerStat(player_id=pid, npxg90=npxg90, xag90=xag90, minutes=minutes, matches=matches)


def test_captain_is_double():
    p = project_player(_player("FWD"), _stat(), STRONG, WEAK, True, 5, PARAMS)
    assert abs(p.xpts_captain - 2 * p.xpts) <= 0.011


def test_striker_beats_benchwarmer():
    starter = project_player(_player("FWD"), _stat(minutes=1400, matches=15), STRONG, WEAK, True, 5, PARAMS)
    fringe = project_player(
        _player("FWD", pid=11), _stat(pid=11, npxg90=0.1, xag90=0.05, minutes=200, matches=12),
        STRONG, WEAK, True, 5, PARAMS,
    )
    assert starter.xpts > fringe.xpts
    assert starter.p_start > fringe.p_start


def test_injury_zeroes_start_probability():
    assert start_probability(_player("MID", status=2), _stat()) == 0.0
    out = project_player(_player("MID", status=2), _stat(), STRONG, WEAK, True, 5, PARAMS)
    assert out.p_start == 0.0
    assert out.exp_minutes == 0.0


def test_defender_gets_clean_sheet_value_vs_weak_opponent():
    strong_def = project_player(_player("DEF"), _stat(npxg90=0.1, xag90=0.1), STRONG, WEAK, True, 5, PARAMS)
    # same defender but their team is weak and the opponent strong -> lower CS value
    weak_def = project_player(_player("DEF"), _stat(npxg90=0.1, xag90=0.1), WEAK, STRONG, False, 5, PARAMS)
    assert strong_def.components["clean_sheet"] > weak_def.components["clean_sheet"]
    assert strong_def.xpts > weak_def.xpts


def test_easier_opponent_raises_attacking_output():
    vs_weak = project_player(_player("FWD"), _stat(), STRONG, WEAK, True, 5, PARAMS)
    vs_strong = project_player(_player("FWD"), _stat(), STRONG, STRONG, True, 5, PARAMS)
    assert vs_weak.components["goals"] > vs_strong.components["goals"]


def test_value_and_ranges_are_consistent():
    p = project_player(_player("MID"), _stat(), STRONG, WEAK, True, 5, PARAMS)
    assert p.value > 0
    assert p.xpts_low <= p.xpts <= p.xpts_high
    assert {"goals", "assists", "appearance", "clean_sheet", "cs_prob"}.issubset(p.components)
