"""Prior attack / defence ratings for the 36 league-phase clubs.

The in-competition model only learns team strength from *finished* UCL games, so
before matchday 1 (and for the first few matchdays, when the sample is tiny)
every club sits at 1.0 and the projection has no opponent signal. These priors —
eyeballed from UEFA club coefficients + squad quality + domestic strength — give
the model something real to work with from MD1, and `blend_prior_observed`
hands control over to the live data as the league phase plays out.

Convention matches `team_strength`:
    attack  > 1  => scores more than an average side
    defence > 1  => concedes more than an average side (i.e. weaker at the back)
Competition mean is ~1.0 on both axes.
"""

from __future__ import annotations

# keyed by UEFA team id -> (attack, defence)
CLUB_PRIORS: dict[int, tuple[float, float]] = {
    50051: (1.40, 0.70),   # Real Madrid
    52919: (1.42, 0.72),   # Man City
    50037: (1.44, 0.76),   # Bayern München
    52747: (1.40, 0.73),   # Paris SG
    7889: (1.34, 0.79),    # Liverpool
    50080: (1.40, 0.86),   # Barcelona
    52280: (1.24, 0.68),   # Arsenal
    50138: (1.18, 0.72),   # Inter
    50124: (1.08, 0.73),   # Atlético
    50136: (1.12, 0.82),   # Napoli
    2603790: (1.14, 0.92), # RB Leipzig
    52758: (1.20, 0.96),   # Borussia Dortmund
    70691: (1.04, 0.98),   # Villarreal
    52683: (1.08, 0.86),   # Aston Villa
    52682: (1.05, 0.96),   # Man Utd
    50149: (1.10, 0.93),   # Sporting CP
    50062: (1.14, 1.02),   # PSV
    52749: (1.06, 1.06),   # Feyenoord
    50137: (1.00, 0.86),   # Roma
    50064: (1.02, 0.90),   # Porto
    75797: (1.00, 0.95),   # Lille
    50067: (1.04, 1.03),   # Galatasaray
    52692: (1.02, 1.00),   # Fenerbahçe
    52265: (1.00, 1.00),   # Real Betis
    50043: (0.94, 1.05),   # Club Brugge
    52277: (0.95, 0.95),   # Lens
    50107: (1.02, 1.06),   # Stuttgart
    52498: (0.84, 1.05),   # Slavia Praha
    59333: (0.90, 1.16),   # Bodø/Glimt
    52707: (0.85, 1.10),   # Shakhtar
    79946: (0.90, 1.05),   # Como
    50129: (0.80, 1.12),   # AEK Athens
    63405: (0.70, 1.30),   # LASK
    52319: (0.64, 1.40),   # Viking
    52797: (0.62, 1.44),   # Slovan Bratislava
    2609356: (0.60, 1.46), # Sabah
}

_DEFAULT = (0.85, 1.10)  # unknown club -> slightly below average

# UEFA team id -> Sofascore team id. Hardcoded because Sofascore's fuzzy search
# resolves short UEFA names ("Atleti", "Man Utd", "Porto") to the wrong club,
# a youth side, or a national team (which carries every star's career history
# and blanked a dozen premiums in the projections).
SS_TEAM_ID: dict[int, int] = {
    7889: 44, 50037: 2672, 50043: 2888, 50051: 2829, 50062: 2952, 50064: 3002,
    50067: 3061, 50080: 2817, 50107: 2677, 50124: 2836, 50129: 3250, 50136: 2714,
    50137: 2702, 50138: 2697, 50149: 3001, 52265: 2816, 52277: 1648, 52280: 42,
    52319: 1164, 52498: 2216, 52682: 35, 52683: 40, 52692: 3052, 52707: 3313,
    52747: 1644, 52749: 2959, 52758: 2673, 52797: 2404, 52919: 17, 59333: 656,
    63405: 2058, 70691: 2819, 75797: 1643, 79946: 2704, 2603790: 36360, 2609356: 267828,
}


def prior_for(team_id: int) -> tuple[float, float]:
    return CLUB_PRIORS.get(team_id, _DEFAULT)


def blend_prior_observed(
    team_id: int,
    observed: tuple[float, float] | None,
    games_played: int,
    *,
    full_trust_at: int = 6,
) -> tuple[float, float]:
    """Weighted mean of the static prior and what we've seen in finished UCL
    games. `games_played` 0 -> all prior; `full_trust_at`+ -> mostly observed."""
    pa, pd = prior_for(team_id)
    if not observed or games_played <= 0:
        return pa, pd
    w = min(1.0, games_played / float(full_trust_at)) * 0.85
    oa, od = observed
    return (1 - w) * pa + w * oa, (1 - w) * pd + w * od
