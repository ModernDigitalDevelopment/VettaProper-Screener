# Backtest methodology and results

Every number in this repo and on the `/research` page traces back to the runs
described here. Where a result is weak, ambiguous, or was produced by code that
later turned out to be buggy, that is stated rather than omitted.

---

## 1. Data

| Source | Contents |
|---|---|
| `thetadata_options_march_2023.db` | March 2023 EOD option chains (386 MB) |
| `thetadata_options_q2_2023.db` | April–June 2023 (1.1 GB) |
| `thetadata_options_q4_2023.db` | October–December 2023 (1.1 GB) |
| `ib_screener_cache.db` | 753 contiguous daily price bars for trend SMAs (44 MB) |

Total ≈ 6.33 million option records across 365 symbols.

**The gap matters.** Coverage is March, April–June, and October–December. There
is no July, August, or September. A 50-day SMA computed naively across the raw
option tables would blend June prices into October and silently corrupt the
trend filter. All SMAs are therefore computed from the contiguous
`price_bars` table, never from the option tables.

---

## 2. Execution model

| Assumption | Value | Comment |
|---|---|---|
| Fill price | 95% at midpoint, 5% crossing the spread | Optimistic but not absurd for liquid spreads |
| Commission | $0.65 per contract per leg | Retail rate |
| Assignment | Not modelled | Positions exit before expiry by default |
| Slippage beyond spread | Not modelled | Real fills in fast markets are worse |
| Intraday moves | Not modelled | EOD data only |

A fill-sensitivity sweep was run on every headline configuration. The
recommended configuration remains profitable when the midpoint fill rate is
dropped all the way to 0% (every fill crossing the spread). An earlier
10%/wide-delta configuration collapsed from +$394 to −$70 under the same test
and was discarded for that reason.

---

## 3. The ranking model

### Why a model at all

The original engine ranked candidates by `credit / width`. That is a reasonable
first guess but it is a guess. Rather than assume, 2,129 candidate spreads were
taken **with no ranking at all** — every candidate that passed the gates was
entered — so that the relationship between candidate attributes and outcomes
could be measured without selection bias.

### Target variable

Return on risk (`net P&L / max loss`), not dollar P&L. Dollar P&L is
contaminated by position sizing: a spread with a small max loss gets more
contracts, so it books larger dollar swings for reasons that have nothing to do
with whether it was a good trade.

### Fit

Ordinary least squares, features `[1, rr, rr², δ, δ², rr·δ]`:

```
const      +0.1408
rr         +1.1350
rr²        +0.2034
delta      -1.2623
delta²     +2.3618
rr*delta   -2.5379

R² = 0.063,  n = 2129
```

### Reading the R²

0.063 is low. It is *supposed* to be low. In a strategy that wins ~77% of the
time, an individual trade's outcome is dominated by whether the underlying
happened to stay above a strike — essentially unpredictable from the candidate's
own attributes. No two-factor model will explain that variance.

What the fit does establish is the **shape and sign** of the relationship, and
those are what a ranking needs:

- Risk-reward is the dominant positive driver.
- Delta carries a penalty.
- The interaction is negative — **a fat credit is worth much less when you had
  to go close to the money to get it.**

That interaction term is the part intuition tends to get wrong.

### Measured value of ranking

5% sizing, 2 per sector, everything else identical:

| Ranking | Trades | Win % | Net | PF | Peak risk |
|---|---|---|---|---|---|
| `credit / width` | 302 | 71.9% | $61,015 | 1.40 | 58% |
| fitted δ × R:R | 304 | 75.0% | **$74,144** | **1.60** | 58% |

+21.5% net and +3.1pp win rate for no additional capital at risk.

### Delta × risk-reward surface

Mean return on risk per trade, from the unranked sample:

| delta \ R:R | 0.00–0.15 | 0.15–0.20 | 0.20–0.26 | 0.26–0.34 | 0.34–0.50 | 0.50+ |
|---|---|---|---|---|---|---|
| 0.20–0.26 | 5.2% | −0.5% | – | – | – | – |
| 0.26–0.30 | 3.2% | 5.4% | 9.0% | 9.3% | 13.2% | – |
| 0.30–0.34 | 1.2% | 6.5% | 7.7% | 6.2% | 18.7% | – |
| 0.34–0.40 | 1.0% | 4.0% | 11.4% | 6.9% | 5.5% | 25.1% |
| 0.40–0.51 | −4.0% | 6.2% | 14.0% | 2.5% | 11.5% | 14.0% |

Cells with fewer than 15 trades are omitted. The 0.50+ column is thin and should
not be over-interpreted.

---

## 4. Results by configuration

All runs: bull put spreads, 7–11 DTE, ≤10% relative spread, SMA10>50 trend
filter, 12-day earnings + ex-dividend blackout, **no IV/RV filter**,
$50,000 starting equity, 80% profit target.

| Configuration | Trades | Win % | Expectancy | Net | PF | Max DD | Peak risk |
|---|---|---|---|---|---|---|---|
| **5% · 1/sector · R:R≥0.2 · ranked** | 240 | **77.5%** | $277 | $66,526 | **1.86** | **19.8%** | 53% |
| 5% · 2/sector · δ0.25±0.07 · ranked | 300 | **83.7%** | $172 | $51,738 | 1.70 | 31.0% | 57% |
| 5% · 1/sector · R:R≥0.2 · max 8 open | 215 | 73.5% | $253 | $54,501 | 1.58 | 36.2% | **39%** |
| 5% · 2/sector · ranked | 304 | 75.0% | $244 | $74,144 | 1.60 | 44.4% | 58% |
| 5% · 2/sector · credit/width rank | 302 | 71.9% | $202 | $61,015 | 1.40 | 42.2% | 58% |
| 10% · 1/sector · R:R≥0.2 · max 6 | 174 | 73.6% | $418 | $72,800 | 1.54 | 41.0% | 59% |
| 7.5% · 1/sector · R:R≥0.2 · max 8 | 215 | 73.5% | $367 | $78,842 | 1.56 | 57.1% | 58% |
| ~~10% · 2/sector · ranked~~ | 304 | 75.0% | $438 | $133,115 | 1.53 | **94.9%** | **117%** |
| ~~10% · 2/sector · credit/width~~ | 302 | 71.9% | $412 | $124,396 | 1.41 | 82.5% | 117% |

### Why the two largest net figures are struck through

Peak concurrent capital at risk of **117%** means the strategy committed more
capital than the account contained. That is not a return, it is a margin call.
Those rows exist to show what happens when sizing and sector caps are both
loosened, not as options to select.

This is the single most important thing to understand about this table: **the
highest net column is not the best configuration.** Read peak risk and drawdown
first.

---

## 5. Profit concentration

Monthly P&L for the recommended configuration:

| Month | Net |
|---|---|
| Mar 2023 | +$7,292 |
| Apr 2023 | −$1,000 |
| May 2023 | +$413 |
| Jun 2023 | +$19,422 |
| Oct 2023 | +$2,587 |
| Nov 2023 | +$15,299 |
| Dec 2023 | +$22,513 |

**86% of all profit came from three months.** The remaining four were roughly
flat. A strategy whose returns depend on a handful of months is considerably
more fragile than its average expectancy implies, and position sizing should
reflect that rather than the headline number.

---

## 6. On annualised figures

$66,526 was earned over **7 months of data spanning a 10-month calendar
window**. Scaling that to a year requires assuming the missing months behave
like the observed ones. Given that 86% of profit came from three months, that
assumption is doing enormous work.

If an annual figure is needed for discussion, state it as: *"$66.5K measured
across 7 months of 2023 data, with profit heavily concentrated in three of
them."* Do not present a smooth annual number.

---

## 7. Filter provenance

| Filter | Effect when tested | Kept? |
|---|---|---|
| Earnings + ex-div blackout | Largest single improvement | **Yes**, 12 days |
| SMA10 > SMA50 trend | Improved win rate and cut drawdown | **Yes** |
| Risk:reward ≥ 0.20 | Fewer trades, much better PF | **Yes** |
| 1 per sector | Cut max drawdown 44.4% → 19.8% | **Yes** |
| IV/RV ≥ 1.2 | **Reduced** performance once trend + earnings were applied | **No** |
| Term structure signal | Real but not tradable in isolation | No |
| Weekend theta capture | No measurable edge | No |
| Contract scaling to dilute friction | **No effect** — bid/ask is per-share, friction stays ~43% | No |

The IV/RV result is worth dwelling on: it was assumed to be essential early in
the research and asserted as such. Testing showed it was not, once better
filters were in place. It is retained in the code as an optional toggle, default
**off**.

---

## 8. Known defects found during research

### 8.1 The −$73 quadrillion iron condor

An early condor run produced a nonsensical figure. Cause: the
`credit >= width` guard was written for verticals. For a condor, max loss is the
wider wing, and on certain quote artifacts `width - credit` evaluated to
near zero. The position sizer then computed
`contracts = capital / (max_loss ≈ 0)` and bought thousands of contracts.

Fixed with two guards, both now in the live screener:

```python
min_max_loss_per_ct = 25.0   # reject structures with ~no real risk
max_contracts       = 20     # hard cap regardless of sizing math
```

All affected results were recomputed. This is documented rather than quietly
fixed because it is exactly the class of bug that makes a backtest lie, and
anyone evaluating these numbers deserves to know it occurred.

### 8.2 Day-one stop-outs in the predecessor system

35 of 75 stops fired on entry day. Round-trip friction (~$0.20) against a
typical credit (~$0.33) made the close quote read 2–3× the credit the instant
the position opened. Any stop based on a multiple of credit triggered
immediately. This is why the current design uses a profit target and a
time-based exit rather than a credit-multiple stop.

### 8.3 Claims made during research that were later retracted

- *"There is no backtesting anywhere in these repos."* Wrong — a 2,090-line
  backtester existed in `Vetta-Options-Prop`.
- *"Scaling contracts dilutes friction by an order of magnitude."* Wrong —
  bid/ask is per-share, so friction stays at ~43% regardless of size.
- *"Iron condors are not worth testing."* Premature — a 0.40δ condor
  configuration was performing well and had been dismissed without examination.

---

## 9. What these results do not establish

1. **Seven months, one year, one regime.** 2023 was a recovery year with
   falling volatility — close to the best possible environment for selling
   premium. There is no 2022, no COVID crash, no 2018 vol spike in this sample.
2. **EOD only.** Intraday adverse moves between decision and fill are invisible.
3. **Modelled fills.** 95% midpoint is optimistic under stress.
4. **Survivorship.** The universe is a current index snapshot; symbols delisted
   during 2023 are absent.
5. **No walk-forward.** The ranking coefficients were fitted on the same period
   the configurations were evaluated on. This is a genuine overfitting exposure.
   The mitigation is that the model has only five parameters and the relationship
   it encodes is directionally stable across every delta bucket — but it is not
   the same thing as out-of-sample validation.

**Point 5 is the most serious limitation in this document.** Before committing
real capital, the recommended sequence is: paper trade the screener for a full
quarter, then compare realised fills and win rate against these figures.

---

## 10. Reproducing

The derived datasets in `backtest/data/` are sufficient to re-run the trend,
event and sector logic. The raw ThetaData `.db` files (2.5 GB) exceed GitHub's
file size limits and are not in this repository — see `docs/DATA.md` for how to
store and retrieve them.
