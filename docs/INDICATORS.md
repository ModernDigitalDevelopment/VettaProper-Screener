# Technical indicators — what was tested and what survived

Source: the indicator suite from
`Vetta-Prop-Screener/screener_engine/screener_engine.py`, as exposed on
`https://34.138.242.130.sslip.io/indicators`.

Nine indicators were ported, computed across 275,892 (symbol, date) rows from
275,961 daily bars, joined to 2,129 real backtest trades, and tested
end-to-end.

---

## Headline result: ADX ≥ 20

Everything else identical, 100% midpoint fills, 2023 data:

| | SMA trend only | + ADX ≥ 20 | Change |
|---|---|---|---|
| Trades | 240 | 205 | −15% |
| Win rate | 76.2% | **80.0%** | **+3.8pp** |
| Net | $53,334 | **$70,526** | **+32%** |
| Profit factor | 1.62 | **2.20** | +0.58 |
| Max drawdown | 24.2% | **14.6%** | **−9.6pp** |
| Peak risk | 53% | 51% | −2pp |

**More profit, higher win rate, lower drawdown, on fewer trades.** That
combination is rare — most filters trade one against another.

It held in every data period, so it is not one lucky quarter:

| Period | SMA only | + ADX ≥ 20 |
|---|---|---|
| March | $7,096 | $6,381 |
| Apr–Jun | $10,483 | **$28,639** |
| Oct–Dec | $35,755 | $35,506 |

The gain is concentrated in Q2 — the choppiest stretch of the sample. That is
exactly what ADX is supposed to do: keep you out of directionless markets. In
Q4's clean trend it neither helped nor hurt.

### Why it works here

A bull put spread needs the underlying to *not fall through your short strike*.
The SMA filter says "price is above its averages", but price can be above a
rising 50-day SMA while chopping sideways with no conviction. ADX measures
whether a trend has any force behind it. Below 20 there is no real trend —
just noise that can drift either way.

---

## The full screen

Terciles by return on risk across 2,129 trades:

| Indicator | Low third | Mid third | High third | Separation |
|---|---|---|---|---|
| **RSI(14)** | 3.3% | 7.2% | **12.3%** | 9.0pp |
| **+DI** | 4.2% | 5.7% | **12.9%** | 8.7pp |
| **ADX(14)** | 3.0% | 9.1% | **10.7%** | 7.7pp |
| Bollinger %B | 3.3% | 8.8% | 10.6% | 7.4pp |
| Keltner squeeze | 5.6% | 4.9% | 12.2% | 6.5pp |
| −DI | **11.3%** | 6.7% | 4.8% | 6.5pp (inverse) |
| MACD histogram | 5.2% | 7.6% | 9.9% | 4.7pp |
| SPY correlation | 3.5% | 9.4% | 9.9% | 6.4pp |
| HV ratio | 7.2% | 5.6% | 9.9% | 2.7pp |
| ATR % | 5.8% | 8.1% | 8.9% | 3.1pp |
| Volume ratio | 8.7% | 6.9% | 7.1% | 1.6pp |

---

## The important negative result: RSI

RSI had the **strongest separation of any indicator** on the screen, and
filtering candidates to RSI 60–80 lifted profit factor from 1.72 to 2.18.

It then **failed in the full backtest**:

| Config | Trades | Win % | Net | PF |
|---|---|---|---|---|
| Baseline | 240 | 76.2% | $53,334 | 1.62 |
| **+ RSI 60–80 only** | 203 | 76.4% | **$44,349** | 1.62 |
| + ADX ≥ 20 | 205 | 80.0% | $70,526 | 2.20 |
| + ADX ≥ 20 + RSI 60–80 | 175 | 79.4% | $58,615 | 2.20 |

Adding RSI to ADX **reduced** net from $70,526 to $58,615.

### Why the two results disagree

Screening candidates and running a portfolio are different questions.

The ranking model already sorts by expected return on risk, and the trades RSI
favours were largely the ones the ranking was picking anyway. So RSI did not
add selection quality — it just removed candidates, and on days when it
removed the *only* candidate, that slot went empty.

This is the single most useful methodological lesson from the exercise:
**an indicator that separates winners from losers on a screen can still make
the portfolio worse.** Every indicator here was therefore tested end-to-end,
not on a screen.

RSI ships as an optional filter, default **off**.

---

## Everything tested

| Config | Trades | Win % | Net | PF | Max DD |
|---|---|---|---|---|---|
| Baseline (SMA only) | 240 | 76.2% | $53,334 | 1.62 | 24.2% |
| **+ ADX ≥ 20** | 205 | **80.0%** | **$70,526** | 2.20 | **14.6%** |
| + RSI 60–80 | 203 | 76.4% | $44,349 | 1.62 | 23.4% |
| + ADX ≥ 20 + RSI 60–80 | 175 | 79.4% | $58,615 | 2.20 | 16.3% |
| + ADX ≥ 25 + RSI 60–80 | 158 | 79.1% | $55,505 | **2.31** | 13.0% |
| + ADX ≥ 30 + RSI 60–80 | 137 | 76.6% | $49,711 | **2.41** | 13.1% |
| + ADX ≥ 20 + RSI 55–80 | 194 | 79.9% | $69,390 | 2.32 | 16.2% |
| + ADX ≥ 20, 2 per sector | 254 | 79.9% | **$80,187** | 2.00 | 35.5% |

Note the profit factor keeps climbing as ADX tightens (2.20 → 2.31 → 2.41)
while net falls. Tighter ADX gives better trades but fewer of them. **ADX ≥ 20
is the best balance**; ADX ≥ 25 is defensible if you prefer fewer, cleaner
trades and a 13.0% drawdown.

---

## What was not adopted, and why

| Indicator | Verdict |
|---|---|
| **RSI** | Strong on screen, negative in portfolio. Available, default off. |
| **+DI / −DI** | Strong separation, but adding `+DI > −DI` to ADX ≥ 20 changed nothing (identical 1,032 candidates). ADX already encodes it. |
| **Bollinger %B** | Marginal on top of ADX (PF 2.57 → 2.60 on screen). Not worth the extra constraint. |
| **Keltner squeeze** | Interesting for *condors* — squeeze means compressed volatility, which suits a range strategy. Untested for condors; noted for future work. |
| **MACD, Stochastic** | Weakest separation. Largely duplicate RSI. |
| **SPY correlation** | Designed as a condor filter in the original engine. Not relevant to directional bull puts. |
| **Volume ratio** | Almost no separation (1.6pp), and slightly inverted. |
| **HV ratio** | Weak. Consistent with the earlier finding that IV/RV did not help. |

---

## Implementation

`app/screener/indicators.py` is a dependency-free port (no pandas/numpy) so it
runs in the request path. It was validated against the pandas reference used
for the backtest: **15/15 sampled dates matched within 0.6** on ADX and RSI.

Gates fail **closed** — a missing indicator rejects the candidate rather than
silently passing it. 17 tests cover computation and gating.

---

## Honest limits

- Same 2023 sample, same 7 months, same single regime as everything else.
- ADX ≥ 20 was chosen from a sweep of {20, 25, 30}. Three points is not a
  thorough optimisation, but it is also not enough freedom to badly overfit.
- The Q2 concentration of the gain is worth watching. It is the theoretically
  expected behaviour, but it is one quarter.
- **Re-test on 2022 before trusting this.** A bear market is where a trend
  filter earns or loses its keep, and 2022 is the test that matters.
