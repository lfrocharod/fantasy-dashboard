"""Learned FPL points model: public history → leakage-safe features →
gradient-boosted trees, judged by a walk-forward backtest against FPL's own
expected points and simple form baselines.

    history   download + normalise seven seasons of per-fixture player data
    features  one row per player per gameweek, built only from earlier gameweeks
    model     the estimator and its persistence
    backtest  walk-forward evaluation and the markdown report
"""
