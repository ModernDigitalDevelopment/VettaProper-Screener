"""Indicator computation and gate tests."""
import math

import pytest

from app.core.criteria import Criteria, PRESETS, preset
from app.screener.indicators import Indicators, compute, passes, wilder_smooth


def synth(n=120, trend=0.5, noise=1.0, seed=3):
    """Deterministic price series with a controllable trend."""
    import random
    rng = random.Random(seed)
    c, out = 100.0, []
    for _ in range(n):
        c += trend + rng.uniform(-noise, noise)
        h = c + abs(rng.uniform(0, noise))
        l = c - abs(rng.uniform(0, noise))
        out.append((h, l, c))
    return [x[0] for x in out], [x[1] for x in out], [x[2] for x in out]


def test_wilder_smoothing_converges():
    assert wilder_smooth([10] * 50, 14)[-1] == pytest.approx(10.0, abs=1e-6)


def test_insufficient_history_returns_empty():
    ind = compute([1, 2, 3], [1, 2, 3], [1, 2, 3])
    assert ind.adx14 is None and ind.rsi14 is None


def test_strong_uptrend_gives_high_adx_and_rsi():
    ind = compute(*synth(trend=1.0, noise=0.3))
    assert ind.adx14 > 25, f"strong trend should lift ADX, got {ind.adx14}"
    assert ind.rsi14 > 60
    assert ind.plus_di > ind.minus_di


def test_choppy_market_gives_low_adx():
    ind = compute(*synth(trend=0.0, noise=2.0))
    assert ind.adx14 < 30, f"chop should keep ADX low, got {ind.adx14}"


def test_downtrend_flips_dmi():
    ind = compute(*synth(trend=-1.0, noise=0.3))
    assert ind.minus_di > ind.plus_di
    assert ind.rsi14 < 40


def test_rsi_bounded():
    for tr in (-2.0, 0.0, 2.0):
        ind = compute(*synth(trend=tr))
        assert 0 <= ind.rsi14 <= 100


def test_bollinger_pctb_sane():
    ind = compute(*synth())
    assert ind.bb_pctb is not None
    assert -1 < ind.bb_pctb < 2


# ---- gates --------------------------------------------------------------

def test_adx_gate_rejects_weak_trend():
    ok, why = passes(Indicators(adx14=15.0), min_adx=20)
    assert not ok and "ADX" in why


def test_adx_gate_accepts_strong_trend():
    ok, _ = passes(Indicators(adx14=28.0), min_adx=20)
    assert ok


def test_gate_off_when_zero():
    ok, _ = passes(Indicators(adx14=5.0), min_adx=0)
    assert ok


def test_missing_data_rejected_not_passed():
    """A missing indicator must never silently pass a gate."""
    ok, why = passes(Indicators(adx14=None), min_adx=20)
    assert not ok and "no ADX" in why


def test_rsi_band_both_ends():
    assert not passes(Indicators(rsi14=45.0), rsi_lo=60, rsi_hi=80)[0]
    assert not passes(Indicators(rsi14=90.0), rsi_lo=60, rsi_hi=80)[0]
    assert passes(Indicators(rsi14=70.0), rsi_lo=60, rsi_hi=80)[0]


def test_di_bullish_gate():
    assert not passes(Indicators(plus_di=15.0, minus_di=25.0),
                      require_di_bullish=True)[0]
    assert passes(Indicators(plus_di=30.0, minus_di=12.0),
                  require_di_bullish=True)[0]


# ---- presets ------------------------------------------------------------

def test_adx_is_on_by_default():
    assert Criteria().min_adx == 20.0


def test_rsi_is_off_by_default():
    """RSI screened well in isolation but did not improve the portfolio."""
    c = Criteria()
    assert c.rsi_hi == 0.0


def test_recommended_preset_uses_adx():
    c = preset("adx_trend_strength")
    assert c.min_adx == 20.0
    assert PRESETS["adx_trend_strength"]["measured"]["profit_factor"] == 2.20


def test_adx_preset_beats_sma_only_on_record():
    adx = PRESETS["adx_trend_strength"]["measured"]
    sma = PRESETS["validated_conservative"]["measured"]
    assert adx["net"] > sma["net"]
    assert adx["win_rate"] > sma["win_rate"]
    assert adx["max_dd_pct"] < sma["max_dd_pct"]
