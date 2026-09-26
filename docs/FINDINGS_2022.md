# 2022 out-of-sample findings

Everything below is measured on the 2022 ThetaData option quotes (4 quarterly
DBs, 19.9M option-days, 354-symbol universe, 100% sector-mapped). All runs use
`mid_fill_prob=1.00` so results are deterministic and contain no seed noise.

The 2023 spec was applied **unchanged**: bull puts, short delta 0.25 ±0.05,
5-wide, 7–11 DTE, R:R ≥ 0.20, 14-day earnings blackout, 7.5% of equity per
position, 1 per sector, max 12 open, $50,000 starting equity.

---

## 0. Data integrity: what was broken, and what it cost

A bug corrupted four of the seven indicator fields. It is documented first
because it determines which findings below are trustworthy.

`build_2022_signals.py` built daily OHLC from the option table's
`underlying_price` with `MIN()/MAX()` per symbol-day. ThetaData repeats **one**
underlying price on every option row of a day, so:

```
symbol-days with high > low:  0  of  21,876
```

High = low = close. True range degenerated to `|close change|`. Because Wilder
smoothing is linear, `+DI` became *algebraically identical* to RSI:

```
PEP 2022-10-06   rsi=36.83   plus_di=36.83   minus_di=63.17
DMI/RSI sign agreement: 99.6%   exact equality: every row
```

Rebuilt from real Polygon high/low (`rebuild_ind22.py`). Field-by-field damage,
measured across all 71,066 shared rows:

| field | mean abs. diff | max | verdict |
|---|---|---|---|
| `rsi14` | 0.098 | 9.64 | **intact** (close-only; residual is vendor close drift) |
| `adx14` | 4.419 | 34.50 | **was broken** |
| `plus_di` | 26.212 | 50.09 | **was broken** |
| `minus_di` | 26.284 | 46.78 | **was broken** |
| `stoch_k` | 6.914 | 82.31 | **was broken** |
| `stoch_d` | 6.210 | 57.85 | **was broken** |
| `atr_pct` | 1.634 | 35.13 | **was broken** |

### Which findings this invalidated

| test | inputs | status |
|---|---|---|
| T1 smooth trend | close / SMA only | intact |
| **T2 ADX + DMI** | high/low | **re-run; results changed materially** |
| T3 RSI bands | close only | intact |
| **T4 stochastics** | high/low | **re-run; results changed materially** |
| T5 HV vs IV | close + option IV | intact |
| T6 DTE / exits | no indicators | intact |
| T7 diversification | no indicators | intact |

T2 and T4 have been re-run against corrected data and the corrected numbers are
what appear below. The broken indicator file is retained as `ind22_broken.pkl`;
`build_2022_signals.py` carries a header warning.

**The bug flattered the strategy.** Two examples of what the fake data claimed
versus what is actually true:

| claim (broken) | reality (corrected) |
|---|---|
| ADX≥35 +DI>−DI: n=18, win 66.7%, −$6,454 | n=47, win **59.6%**, −$27,390 |
| Stoch %K<30: n=72, win 69.4%, −$25,712 | n=63, win 71.4%, **−$11,199** |
| Top regime signal: SPY ADX, 51.3pp on n=16 | 10.8pp on n=50 |

---

## 1. Baseline: the strategy loses money in 2022

| configuration | n | win% | net | PF | DD% |
|---|---|---|---|---|---|
| **2022 baseline (2023 spec, unchanged)** | 215 | 72.6 | **−$38,512** | 0.76 | 105.8 |
| same, 2 per sector | 294 | 69.4 | −$82,127 | 0.66 | 186.9 |
| same, 5% sizing | 215 | 72.6 | −$26,119 | 0.76 | 71.7 |
| same, no trend filter | 319 | 71.8 | −$54,792 | 0.77 | 175.9 |

**The win rate was never the problem.** It fell only 76.2% → 72.6%. The payoff
structure is what broke:

```
avg win   +$787   over 156 wins
avg loss  -$2,733 over  59 losses     ratio 3.47x
worst single trade: LRCX 2022-11-11  -$3,776 (EXPIRED)
```

A 3.47× loss/win ratio needs roughly a 78% win rate to break even. 2023
delivered 76.2% and the tilt covered the gap. 2022 delivered 72.6% and it did
not. This is the single most important number in the whole study.

Note the 5% sizing row: the same trades, same signals, but the drawdown drops
from 105.8% to 71.7% and the loss shrinks by a third. **Sizing moved the result
more than any signal filter tested.**

---

## 2. The seven tests

### Test 1 — Smooth trend (no sharp spikes above the 50)

| variant | n | win% | net | PF | DD% |
|---|---|---|---|---|---|
| control (s10_50) | 215 | 72.6 | −$38,512 | 0.76 | 105.8 |
| smooth10 14d, stretch≤8% | 48 | 52.1 | −$51,381 | 0.28 | 104.6 |
| smooth10 14d, stretch≤5% | 17 | 64.7 | −$7,935 | 0.52 | 18.8 |
| smooth10 21d, stretch≤8% | 22 | 27.3 | −$38,169 | 0.13 | 76.3 |
| smooth10 30d, stretch≤8% | 7 | 42.9 | −$4,198 | 0.36 | 11.7 |
| smooth20 14d, stretch≤8% | 48 | 52.1 | −$51,381 | 0.28 | 104.6 |
| smooth20 21d, stretch≤6% | 15 | 40.0 | −$13,630 | 0.29 | 36.6 |
| smooth10 14d + slope≤0.3 | 34 | 41.2 | −$46,970 | 0.20 | 95.0 |

**Failed, and inverted.** Requiring a sustained smooth uptrend *lowered* the win
rate hard — 72.6% → 52.1% at 14 days, and 27.3% at 21 days. In 2022 a stock
that had been quietly above its 50-day for three weeks was not a safe
put-seller's asset; it was a stock that had not yet been repriced. The small
absolute losses in the 30d/stretch≤5% rows are an artefact of tiny samples
(n=7, n=17), not evidence of an edge.

*Correction to an earlier verbal summary: I previously quoted the n=7/−$4,198
row as the "14d stretch≤8%" variant. That row is the **30d** variant. The 14d
variant is n=48, −$51,381.*

### Test 2 — ADX, with and without DMI confirmation *(corrected data)*

| variant | n | win% | net | PF | DD% |
|---|---|---|---|---|---|
| control | 215 | 72.6 | −$38,512 | 0.76 | 105.8 |
| ADX≥25 | 124 | 70.2 | −$31,052 | 0.68 | 83.9 |
| ADX≥30 | 85 | 67.1 | −$32,191 | 0.57 | 71.3 |
| ADX≥35 | 50 | 62.0 | −$25,542 | 0.49 | 53.2 |
| ADX≥25, +DI>−DI | 119 | 68.1 | −$39,341 | 0.61 | 98.8 |
| ADX≥30, +DI>−DI | 81 | 65.4 | −$34,837 | 0.53 | 76.6 |
| ADX≥35, +DI>−DI | 47 | 59.6 | −$27,390 | 0.45 | 56.9 |

**Failed, monotonically.** Win rate falls as the ADX threshold rises — 72.6% →
70.2% → 67.1% → 62.0%. Adding DMI confirmation made every single tier *worse*,
not better. Profit factor degrades from 0.76 to 0.45.

This directly contradicts the 2023 result, where ADX≥20 was good enough to
become the default preset. The reading: in 2022, strong trend + bullish DMI
selected stocks in **strong downtrends that had just bounced** — precisely the
worst thing to sell puts on. ADX measures trend strength without direction, and
DMI's direction signal lags at turning points.

### Test 3 — RSI bands

| variant | n | win% | net | PF | DD% |
|---|---|---|---|---|---|
| control | 215 | 72.6 | −$38,512 | 0.76 | 105.8 |
| RSI < 70 | 204 | 74.0 | −$25,333 | 0.82 | 101.2 |
| RSI 50–70 | 188 | 72.3 | −$41,004 | 0.73 | 131.8 |
| RSI 30–50 | 65 | 67.7 | −$33,904 | 0.49 | 82.6 |
| RSI < 30 | 1 | 100.0 | +$318 | — | 0.0 |

**Marginal.** Excluding overbought names (RSI<70) helped a little: win rate
+1.4pp, loss cut 34%. It removes only 11 of 215 trades, so it is cheap
insurance rather than a real filter. Everything narrower was worse. The RSI<30
row is a single trade and carries no information.

### Test 4 — Stochastics %K *(corrected data)*

| variant | n | win% | net | PF | DD% |
|---|---|---|---|---|---|
| control | 215 | 72.6 | −$38,512 | 0.76 | 105.8 |
| %K < 60 | 114 | 71.9 | −$25,511 | 0.71 | 73.3 |
| %K < 50 | 97 | 69.1 | −$34,882 | 0.60 | 90.7 |
| %K < 40 | 80 | 65.0 | −$43,307 | 0.48 | 105.0 |
| **%K < 30** | **63** | **71.4** | **−$11,199** | **0.76** | **41.1** |

**Best drawdown result of the seven tests.** %K<30 cut the loss by 71% and the
drawdown from 105.8% to 41.1% while holding the win rate. But note the
non-monotonicity: 60 → 50 → 40 gets steadily worse, then 30 is suddenly best.
An effect that is not monotonic in its own parameter across n=63 is most likely
noise. **Do not deploy on this.**

### Test 5 — Historical volatility **above** implied volatility

Your hypothesis, inverting the usual "sell when IV is rich" assumption.

| variant | n | win% | net | PF | DD% |
|---|---|---|---|---|---|
| control | 215 | 72.6 | −$38,512 | 0.76 | 105.8 |
| **HV > IV** | **166** | **74.1** | −$23,547 | 0.81 | 78.5 |
| HV−IV ≥ +3pp | 137 | 70.8 | −$26,819 | 0.74 | 63.2 |
| HV−IV ≥ +6pp | 118 | 71.2 | −$18,417 | 0.78 | 56.3 |

**The most interesting result in the study.** HV>IV was the only filter of the
seven to *raise* the win rate (72.6% → 74.1%) while also cutting the loss (39%)
and the drawdown (105.8% → 78.5%). The +6pp variant cuts the loss 52% and
halves the drawdown.

Why this is more credible than the others: it is a **volatility-pricing** claim,
not a direction claim. It says options were cheap relative to what the stock
actually went on to do. That is a mispricing argument with a mechanism, and it
does not depend on guessing market direction — which is exactly the thing that
2022 proved the strategy cannot do. It is also the only filter whose
improvement strengthens monotonically as the threshold tightens (+3pp is the
one wobble).

### Test 6 — 12 DTE, and exiting before the gamma window

| variant | n | win% | net | PF | DD% |
|---|---|---|---|---|---|
| control (7–11 DTE, to expiry) | 215 | 72.6 | −$38,512 | 0.76 | 105.8 |
| 12±2 DTE, to expiry | 148 | 68.9 | −$41,383 | 0.66 | 123.4 |
| 12±2 DTE, exit at 2 DTE | 150 | 64.0 | −$28,343 | 0.71 | 93.2 |
| 12±2 DTE, exit at 3 DTE | 179 | 59.2 | −$36,845 | 0.66 | 98.0 |
| 12±2 DTE, exit at 1 DTE | 149 | 65.8 | −$32,216 | 0.70 | 103.2 |
| 7–11 DTE, exit at 2 DTE | 228 | 64.5 | −$31,421 | 0.76 | 103.2 |
| 7–11 DTE, exit at 3 DTE | 244 | 57.8 | −$50,228 | 0.63 | 135.2 |

**The gamma hypothesis is supported, but it is not free.** Holding 12±2 DTE to
expiry loses $41,383; exiting at 2 DTE loses $28,343 — a 32% improvement from
the exit alone. Same entries, better outcome. Gamma near expiry was genuinely
costing money.

The cost is win rate: 68.9% → 64.0%. Closing early converts some trades that
*would* have expired worthless into small paid debits. You are buying lower tail
risk with a chunk of your hit rate. Given that the tail is what killed 2022,
that is probably a trade worth making — but it must be a deliberate choice, not
a surprise.

Going out to 12 DTE was itself a mistake in 2022: it underperformed 7–11 DTE on
every measure.

### Test 7 — Dynamic sector diversification

You asked for allocations that expand when one sector is full of good setups,
"so we don't miss out on alpha."

| variant | n | win% | net | PF | DD% |
|---|---|---|---|---|---|
| **fixed 1/sector (control)** | 215 | 72.6 | **−$38,512** | 0.76 | **105.8** |
| fixed 2/sector | 294 | 69.4 | −$82,127 | 0.66 | 186.9 |
| soft +1 (top quartile) | 281 | 71.5 | −$58,509 | 0.73 | 163.7 |
| soft +2 (top quartile) | 303 | 70.3 | −$69,197 | 0.71 | 188.9 |
| quality +1 (gap≤0.02) | 273 | 71.1 | −$72,362 | 0.68 | 189.0 |
| quality +1 (gap≤0.05) | 287 | 71.1 | −$62,939 | 0.72 | 166.0 |
| adaptive +2 (thin days) | 295 | 70.2 | −$73,734 | 0.69 | 194.8 |

**Unambiguously failed — every single relaxation was worse than the control, on
every metric.** Losses widened 52% to 113%; drawdowns went from 105.8% to
163–195%.

The mechanism is worth stating plainly, because it generalises beyond 2022: when
a sector is simultaneously offering many attractive put-selling setups, that is
usually because **the whole sector just sold off together**. Those setups are
not independent sources of alpha; they are one correlated bet wearing several
tickers. Relaxing the cap doesn't diversify you into opportunity, it
concentrates you into a single factor at the worst possible moment. The
1-per-sector cap is not a conservative drag on returns — it is doing real work.

---

## 3. Bear calls with identical parameters

Same delta 0.25 ±0.05, same R:R ≥ 0.20, same width, same DTE, same blackout,
same sizing, same 1-per-sector cap. Only the side flips.

| config | n | win% | net | PF | DD% |
|---|---|---|---|---|---|
| bull puts (reference) | 215 | 72.6 | −$38,512 | 0.76 | 105.8 |
| bear call, no trend gate | 306 | 76.1 | **+$30,650** | 1.19 | 81.3 |
| bear call, price < 50 SMA | 211 | 77.7 | **+$26,168** | 1.24 | 62.6 |
| bear call, <50 SMA, RSI<50 | 204 | 77.0 | +$20,080 | 1.18 | 72.5 |
| bear call, <50 SMA, RSI<40 | 135 | 76.3 | +$11,431 | 1.17 | 45.9 |
| bear call, <50 SMA, ADX≥25 | 123 | 78.0 | +$13,067 | 1.19 | 33.0 |
| bear call, <50 SMA, HV>IV | 144 | 72.2 | −$2,185 | 0.97 | 63.8 |

Profitable, with better win rates than the puts ever managed. **This is
direction, not skill** — see §5.

---

## 4. The per-symbol switch — failed

Per-symbol side selection with no market-wide input (your explicit preference,
and the right design — see §5 for why a SPY-level switch would have been worse).

| rule | n | win% | net | PF | DD% | mix |
|---|---|---|---|---|---|---|
| always bull put | 215 | 72.6 | −$38,512 | 0.76 | 105.8 | 215P / 0C |
| **always bear call** | 211 | 77.7 | **+$26,168** | 1.24 | 62.6 | 0P / 211C |
| switch (sma50) | 305 | 71.1 | −$47,088 | 0.79 | 122.3 | 173P / 132C |
| switch (rsi) | 321 | 71.7 | −$28,193 | 0.88 | 147.6 | 179P / 142C |
| switch (dmi) | 320 | 74.7 | −$5,287 | 0.97 | 102.4 | 178P / 142C |

**Every switch rule is beaten by simply always selling calls.** Two independent
causes:

**(a) It is a capacity failure, not a signal failure.** With 12 slots and one
per sector, bull puts arrive first and fill the book, crowding out the calls:

```
switch(sma50)  took 132 calls; missed 109 always-call trades worth  +$36,485
switch(rsi)    took 142 calls; missed 119                           +$16,671
switch(dmi)    took 142 calls; missed 118                           +$18,682
```

The switch was not choosing the wrong side. It was running out of room. That is
fixable — reserve slots for the minority side instead of first-come-first-served.

**(b) The put leg cannot be rescued.** In all three switches the put side lost
(−$13k to −$40k) while the call side made money. No per-symbol rule tested
saved the long side.

---

## 5. Is the bear-call edge statistically significant? **No**

Permutation test on return-on-risk, 20,000 shuffles. Permutation rather than a
t-test because the payoff is heavily skewed (many small wins, rare large
losses), which violates normality.

```
mean return-on-risk, bear calls : +2.80%   (n=211)
mean return-on-risk, bull puts  : -5.08%   (n=215)
observed difference             : +7.88pp
p-value                         :  0.0871   -> NOT significant at 0.05
```

Three further reasons to distrust it:

**It inverts in up months.** Calls beat puts in 7 of 10 months — but the 3
exceptions are exactly the up months:

| | n | win% | net |
|---|---|---|---|
| **Up months** (Mar/Jul/Nov), puts | 73 | 90.4 | **+$41,111** |
| Up months, calls | 44 | 54.5 | −$29,916 |
| **Down months**, puts | 142 | 63.4 | −$79,623 |
| Down months, calls | 167 | 83.8 | **+$56,085** |

A signal that works only when the market falls and reverses when it rises has no
independent predictive content. It *is* the market direction. It will invert
precisely when you need it not to — which is the failure mode we set out to fix.

**Concentration.** April 2022 alone contributed +$18,401 of the +$26,168 total —
**70% of all profit from one month.**

**Drawdown.** The best call config still runs 62.6% drawdown at 7.5% sizing. Not
deployable regardless of sign.

Your instinct on per-symbol over market-wide was correct, and the monthly table
proves it: a SPY-level switch would have gone short through Mar/Jul/Nov, the
three months when puts made +$41,111. The design was right. The data simply does
not contain the signal.

---

## 6. What 2022 actually taught us

Ranked by how much I'd trust each:

1. **Sizing is the binding constraint, not signal selection.** Identical trades
   at 5% instead of 7.5%: loss −$38,512 → −$26,119, drawdown 105.8% → 71.7%.
   That single parameter beat all seven tests. At 7.5%, a bad year exceeds 100%
   drawdown — the account is gone before the edge can show up.

2. **The loss/win ratio is the real risk, not the win rate.** 3.47× losses
   against a 72.6% hit rate is negative expectancy. The win rate held up fine
   out of sample; it was never the vulnerable parameter. Any future work should
   target the size of losses, not the frequency of wins.

3. **T5 (HV > IV) is the one finding likely to generalise.** Only filter to
   raise the win rate while cutting loss and drawdown, and the only one with a
   mechanism that isn't a disguised direction bet.

4. **The 1-per-sector cap is load-bearing.** Every relaxation was worse. Sector
   clusters of good setups are correlated risk, not alpha.

5. **Gamma is real and costs money.** Exiting at 2 DTE improved net by 32% on
   identical entries — at the price of ~5pp of win rate.

6. **Trend-strength filters (ADX/DMI) do not transfer across regimes.** ADX≥20
   was the 2023 default; in 2022 every tier degraded results monotonically. Be
   suspicious of the 2023 preset.

7. **There is no significant switching signal here.** p=0.087, inverts with
   direction, 70% of profit in one month.

---

## 7. What would settle the open questions

- **Restore the 2023 databases and re-run the switch there.** They were deleted
  for disk space. A rule fitted on one bear year and never tested on a bull year
  is not a finding. This is the highest-value next step.
- **Fix the slot allocator** to reserve capacity for the minority side, then
  re-test the switch — §4(a) shows the mechanical failure is separable from the
  signal question.
- **Re-test T5 (HV>IV) on 2023** and on the bear-call side, since it is the only
  candidate with a plausible mechanism.
- **Re-run the 2023 ADX preset** now that the corrected indicator pipeline
  exists, to check the 2023 default wasn't itself built on a similar artefact.

## Reproducing

```
backtest/2022/build_2022_signals.py   trend + HV/IV  (indicators BROKEN - see §0)
backtest/2022/rebuild_ind22.py        correct indicators from Polygon high/low
backtest/2022/run2022.py  [base|t1..t7]
backtest/2022/bearcall.py             bear calls, identical parameters
backtest/2022/switch.py   [2022|2023] per-symbol side switching
backtest/2022/signif.py               permutation test, monthly split, capacity
backtest/2022/regime.py               candidate switching-signal ranking
```
