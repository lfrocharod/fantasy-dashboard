import time

from fantasy_ingest.sources.blend import Signal, compose


def test_agreeing_sources_high_confidence_low_disagreement():
    c = compose([
        Signal("uefa_feed", 0.90, 0.6),
        Signal("sofascore_form", 0.88, 0.7),
        Signal("fpl_bootstrap", 0.92, 0.5),
    ])
    assert c is not None
    assert 0.88 <= c.value <= 0.92
    assert c.disagreement < 0.15
    assert c.confidence > 0.6
    assert c.n == 3


def test_conflicting_sources_flag_disagreement():
    c = compose([
        Signal("stats_provider", 0.85, 0.6),  # says nailed
        Signal("official_club", 0.20, 0.8),   # says doubtful
    ])
    assert c is not None
    assert c.disagreement >= 0.33
    assert "disagree" in c.why()
    # the higher-confidence source pulls the mean down
    assert c.value < 0.55


def test_prior_used_when_no_signals():
    c = compose([], prior=0.7, prior_weight=0.2)
    assert c is not None and abs(c.value - 0.7) < 1e-6
    assert c.n == 0


def test_recency_decay_downweights_stale_news():
    fresh = Signal("lineup_leak", 0.2, 0.9, asof=time.time())
    stale = Signal("lineup_leak", 0.2, 0.9, asof=time.time() - 12 * 3600)
    c_fresh = compose([Signal("base", 0.9, 0.6), fresh], half_life_h=2.0)
    c_stale = compose([Signal("base", 0.9, 0.6), stale], half_life_h=2.0)
    assert c_fresh is not None and c_stale is not None
    # stale contradicting signal barely moves the result
    assert c_stale.value > c_fresh.value


def test_clamps_to_range():
    c = compose([Signal("a", 1.4, 0.6), Signal("b", 1.6, 0.6)], hi=1.0)
    assert c is not None and c.value == 1.0
