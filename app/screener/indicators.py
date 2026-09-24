"""Technical indicators, ported from the Vetta screener engine.

Source: research/Vetta-Prop-Screener/screener_engine/screener_engine.py,
with parameter defaults from indicator_params.py.

Only indicators that EARNED their place in backtesting are gated on. The rest
are computed and surfaced for display, because seeing them helps you
understand a candidate even when they are not filtering it.

Backtested effect of ADX >= 20 (2023, everything else identical):

    trades     240  ->  205    (-15%)
    win rate   76.2% -> 80.0%  (+3.8pp)
    net        $53,334 -> $70,526  (+32%)
    max DD     24.2% -> 14.6%  (-9.6pp)

More profit, higher win rate, lower drawdown, on fewer trades. The improvement
held in all three data periods, so it is not one lucky quarter.

RSI was ALSO strong when screening candidates in isolation (profit factor
1.72 -> 2.18) but did NOT survive a full portfolio backtest: RSI 60-80 alone
produced $44,349 versus a $53,334 baseline. The candidates it favoured were
already being picked by the ranking model, so it removed opportunities without
adding edge. It is available as an optional filter, default OFF.

This gap between "filters good candidates" and "improves the portfolio" is
why every indicator here was tested end-to-end rather than on a screen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


def wilder_smooth(values: Sequence[float], period: int) -> list[float]:
    """Wilder's smoothing — an EMA with alpha = 1/period."""
    if not values:
        return []
    out = [float(values[0])]
    a = 1.0 / period
    for v in values[1:]:
        out.append(out[-1] + a * (float(v) - out[-1]))
    return out


@dataclass
class Indicators:
    adx14: float | None = None
    plus_di: float | None = None
    minus_di: float | None = None
    rsi14: float | None = None
    bb_pctb: float | None = None
    bb_width: float | None = None
    atr14: float | None = None
    atr_pct: float | None = None
    macd_hist: float | None = None
    hv30: float | None = None

    def to_dict(self):
        return {k: (round(v, 3) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


def compute(highs: Sequence[float], lows: Sequence[float],
            closes: Sequence[float], period: int = 14) -> Indicators:
    """Compute indicators from OHLC history. Needs ~50+ bars."""
    n = len(closes)
    ind = Indicators()
    if n < period * 2 + 2:
        return ind

    h = [float(x) for x in highs]
    l = [float(x) for x in lows]
    c = [float(x) for x in closes]

    # --- True range ------------------------------------------------------
    tr = [h[0] - l[0]]
    for i in range(1, n):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    atr = wilder_smooth(tr, period)
    ind.atr14 = atr[-1]
    ind.atr_pct = 100 * atr[-1] / c[-1] if c[-1] else None

    # --- ADX / DMI -------------------------------------------------------
    plus_dm, minus_dm = [0.0], [0.0]
    for i in range(1, n):
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        plus_dm.append(up if (up > dn and up > 0) else 0.0)
        minus_dm.append(dn if (dn > up and dn > 0) else 0.0)

    sp, sm = wilder_smooth(plus_dm, period), wilder_smooth(minus_dm, period)
    pdi = [100 * s / a if a else 0.0 for s, a in zip(sp, atr)]
    mdi = [100 * s / a if a else 0.0 for s, a in zip(sm, atr)]
    dx = [100 * abs(p - m) / (p + m) if (p + m) else 0.0 for p, m in zip(pdi, mdi)]

    ind.adx14 = wilder_smooth(dx, period)[-1]
    ind.plus_di = pdi[-1]
    ind.minus_di = mdi[-1]

    # --- RSI -------------------------------------------------------------
    gains = [max(c[i] - c[i - 1], 0.0) for i in range(1, n)]
    losses = [max(c[i - 1] - c[i], 0.0) for i in range(1, n)]
    ag, al = wilder_smooth(gains, period)[-1], wilder_smooth(losses, period)[-1]
    ind.rsi14 = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)

    # --- Bollinger (20, 2 sigma) -----------------------------------------
    if n >= 20:
        w = c[-20:]
        mean = sum(w) / 20
        sd = math.sqrt(sum((x - mean) ** 2 for x in w) / 20)
        upper, lower = mean + 2 * sd, mean - 2 * sd
        if upper > lower:
            ind.bb_pctb = (c[-1] - lower) / (upper - lower)
            ind.bb_width = 100 * (upper - lower) / mean if mean else None

    # --- MACD histogram (12/26/9) ----------------------------------------
    def ema(series, span):
        k = 2 / (span + 1)
        e = series[0]
        for v in series[1:]:
            e = v * k + e * (1 - k)
        return e

    if n >= 35:
        macd_series = []
        for i in range(26, n + 1):
            macd_series.append(ema(c[:i], 12) - ema(c[:i], 26))
        if len(macd_series) >= 9:
            ind.macd_hist = macd_series[-1] - ema(macd_series, 9)

    # --- HV30 ------------------------------------------------------------
    if n >= 31:
        # guard BOTH prices: a non-positive close makes the log undefined
        rets = [math.log(c[i] / c[i - 1]) for i in range(n - 30, n)
                if c[i - 1] > 0 and c[i] > 0]
        if len(rets) > 1:
            mu = sum(rets) / len(rets)
            var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
            ind.hv30 = 100 * math.sqrt(var) * math.sqrt(252)

    return ind


def passes(ind: Indicators, min_adx: float = 0.0,
           rsi_lo: float = 0.0, rsi_hi: float = 0.0,
           require_di_bullish: bool = False) -> tuple[bool, str]:
    """Apply indicator gates. Returns (ok, reason_if_rejected)."""
    if min_adx > 0:
        if ind.adx14 is None:
            return False, "no ADX data"
        if ind.adx14 < min_adx:
            return False, f"ADX {ind.adx14:.1f} < {min_adx}"
    if rsi_hi > 0:
        if ind.rsi14 is None:
            return False, "no RSI data"
        if not (rsi_lo <= ind.rsi14 <= rsi_hi):
            return False, f"RSI {ind.rsi14:.1f} outside {rsi_lo}-{rsi_hi}"
    if require_di_bullish:
        if ind.plus_di is None or ind.minus_di is None:
            return False, "no DMI data"
        if ind.plus_di <= ind.minus_di:
            return False, f"-DI {ind.minus_di:.1f} >= +DI {ind.plus_di:.1f}"
    return True, ""
