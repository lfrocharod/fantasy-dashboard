from fantasy_ingest.draft.fpl import (
    _SCORING,
    _depth_bump,
    _gw_projection,
    _p_start,
    _pos_fdr,
    _rank_pstart,
    _set_piece,
)
from fantasy_ingest.draft.fpl_league import parse_choices, parse_standings


def _el(**kw):
    base = {
        "id": 1, "status": "a", "chance_of_playing_next_round": None, "starts": 3, "minutes": 270,
        "expected_goals": 1.5, "expected_assists": 0.4, "saves": 0, "bps": 60,
        "defensive_contribution": 0, "penalties_order": None, "direct_freekicks_order": None,
        "corners_and_indirect_freekicks_order": None, "draft_rank": 50, "web_name": "X",
    }
    base.update(kw)
    return base


def _proj(el, pos, own="ARS", opp="HUL", home=True, ps=0.9, pa=0.95):
    return _gw_projection(el, pos, _SCORING, own, opp, home, ps, pa)


def test_out_players_score_zero():
    assert _p_start(_el(status="i"), 3, [], 0.0, None, False) == (0.0, 0.0)
    assert _p_start(_el(status="s"), 3, [], 0.0, None, False) == (0.0, 0.0)


def test_nailed_starter_high_pstart():
    ps, pa = _p_start(_el(starts=3, minutes=270), 3, [90, 90, 90], 0.0, None, False)
    assert ps > 0.85 and pa >= ps


def test_new_signing_gets_role_prior_not_cameo_score():
    # elite draft_rank, barely any minutes, no recent data -> tentatively a
    # starter on pedigree (not written off as a bench body)
    ps, _pa = _p_start(_el(draft_rank=8, starts=0, minutes=26), 3, [], 0.0, None, False)
    assert ps >= 0.5


def test_deep_bench_stays_low_even_after_a_cameo():
    ps, _pa = _p_start(_el(draft_rank=450, starts=1, minutes=95), 3, [12, 0, 5], 0.0, None, False)
    assert ps < 0.5


def test_depth_bump_when_starter_ahead_is_injured():
    me = _el(id=2, draft_rank=441)
    ahead_out = _el(id=3, draft_rank=190, status="d", chance_of_playing_next_round=25)
    bump = _depth_bump(me, [me, ahead_out])
    assert bump > 0
    ps_no, _ = _p_start(me, 3, [], 0.0, None, False)
    ps_yes, _ = _p_start(me, 3, [], bump, None, False)
    assert ps_yes > ps_no


def test_role_override_forces_pstart():
    ps, _pa = _p_start(_el(starts=0, minutes=0, draft_rank=600), 3, [], 0.0, 0.85, False)
    assert ps >= 0.8


def test_rank_prior_monotonic():
    assert _rank_pstart(5) > _rank_pstart(120) > _rank_pstart(400)


def test_gw_projection_scales_with_fixture():
    easy = _proj(_el(), "FWD", opp="HUL", home=True)[0]
    hard = _proj(_el(), "FWD", opp="MCI", home=False)[0]
    assert easy > hard > 0


def test_strong_defence_clean_sheet_prob_high():
    _x1, cs_ars, _c1 = _proj(_el(), "DEF", own="ARS", opp="HUL", home=True)
    _x2, cs_hul, _c2 = _proj(_el(), "DEF", own="HUL", opp="MCI", home=False)
    assert cs_ars > 0.45 and cs_ars > cs_hul


def test_keeper_save_component():
    comp = _proj(_el(saves=12), "GKP", own="HUL", opp="MCI", home=False)[2]
    assert comp["saves"] > 0


def test_defcon_rewards_high_rate():
    lo = _proj(_el(defensive_contribution=6), "DEF")[2]["defcon"]
    hi = _proj(_el(defensive_contribution=40), "DEF")[2]["defcon"]
    assert hi > lo >= 0


def test_set_piece_flags():
    assert _set_piece(_el(penalties_order=1)) == "P"
    assert _set_piece(_el(penalties_order=1, corners_and_indirect_freekicks_order=1)) == "PC"
    assert _set_piece(_el(penalties_order=2)) == ""


def test_parse_standings_maps_names():
    det = {
        "league_entries": [
            {"id": 5, "entry_id": 900, "entry_name": "My FC",
             "player_first_name": "A", "player_last_name": "B"},
        ],
        "standings": [
            {"league_entry": 5, "rank": 1, "total": 12, "points_for": 300,
             "points_against": 250, "matches_won": 4, "matches_drawn": 0, "matches_lost": 1},
        ],
    }
    rows = parse_standings(det)
    assert rows[0]["name"] == "My FC" and rows[0]["entry_id"] == 900 and rows[0]["rank"] == 1


class _FakeClient:
    def get(self, url):
        class R:
            status_code = 200

            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"choices": [
                    {"index": 1, "round": 1, "pick": 1, "entry": 900,
                     "entry_name": "My FC", "element": 42},
                    {"index": 2, "round": 1, "pick": 2, "entry": 901,
                     "entry_name": "Rival", "element": None},
                ]}
        return R()


def test_parse_choices_skips_empty():
    picks = parse_choices(_FakeClient(), "1")
    assert len(picks) == 1 and picks[0]["player_ext_id"] == 42 and picks[0]["source"] == "fpl"


def test_pos_fdr_is_position_aware():
    # ARS: elite defence (0.56), strong attack (1.28). Away fixture.
    fwd = _pos_fdr("FWD", "ARS", is_home=False)
    gk = _pos_fdr("GKP", "ARS", is_home=False)
    dfd = _pos_fdr("DEF", "ARS", is_home=False)
    mid = _pos_fdr("MID", "ARS", is_home=False)
    # forward: hard to score on that back line
    assert fwd[0] >= 4 and fwd[2] == fwd[0]
    # keeper: their attack is strong-ish -> some clean-sheet risk, but the
    # attacking axis (which kills the forward) doesn't apply
    assert gk[2] == gk[1] and gk[2] < fwd[2]
    # defender sits between keeper and midfielder because of the set-piece upside
    assert gk[2] <= dfd[2] <= mid[2]

    # A leaky minnow (COV: attack 0.82, defence 1.18) at home -> green for attackers
    weak = _pos_fdr("FWD", "COV", is_home=True)
    assert weak[2] <= 2


def test_split_auth_extracts_bearer_and_cookie():
    from fantasy_ingest.draft.fpl_league import has_auth, split_auth

    jwt = "eyJhbGciOi.eyJzdWIiOi.SflKxwRJ_signature-part"
    # bare token
    assert split_auth(jwt) == ("", jwt)
    assert has_auth(jwt)
    # "Bearer <token>"
    assert split_auth(f"Bearer {jwt}")[1] == jwt
    # a whole curl blob with -b cookie and an x-api-authorization header
    blob = (
        "curl 'https://draft.premierleague.com/api/entry/1/my-team' "
        f"-b 'a=b; c=d' -H 'x-api-authorization: Bearer {jwt}'"
    )
    cookie, bearer = split_auth(blob)
    assert bearer == jwt and cookie == "a=b; c=d"
    # a plain cookie string is not auth
    assert split_auth("a=b; c=d") == ("a=b; c=d", None)
    assert not has_auth("a=b; c=d")
