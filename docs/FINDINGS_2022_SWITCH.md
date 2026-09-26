# 2022 out-of-sample: the seven tests, and the bull-put/bear-call switch

## Headline

The switching idea is **not supported by the data**. Bear calls made money in
2022, but the edge is direction, not signal: it inverts in up months, fails a
permutation test at p=0.087, and 70% of its profit is one month.

A separate, real bug was found and fixed along the way (see §0).

## 0. Bug found: ADX/DMI/stochastics were invalid in the first 2022 build

`build_2022_signals.py` derived daily OHLC from the option table's
`underlying_price` using `MIN()/MAX()` per symbol-day. ThetaData repeats a
single underlying price on every option row, so:

    symbol-days with high > low: 0 of 21,876

High = low = close. True range collapsed to |close change|, and because Wilder
smoothing is linear, `+DI` became **algebraically identical to RSI**:

    PEP 2022-10-06  rsi=36.83  plus_di=36.83  minus_di=63.17
    DMI/RSI sign agreement: 99.6%; exact equality on every row

Rebuilt from real Polygon high/low (`rebuild_ind22.py`). After the fix: 0 exact
matches, 90.1% sign agreement (genuine correlation between two momentum
measures). The broken file is kept as `ind22_broken.pkl`.

This invalidated the first regime run, which reported SPY ADX as the top signal
at 51.3pp separation on n=16. After the fix that collapses to 10.8pp on n=50.
Test 2's `require_di_bullish` variants are also affected and would need re-running.

## 1. Baseline

2023 spec unchanged, applied to 2022: n=215, win 72.6%, **-$38,512**, PF 0.76,
DD 105.8%. The win rate held (76.2% -> 72.6%); the payoff broke. Losses averaged
-$2,733 against +$787 wins, a 3.5x ratio.

## 2. The seven tests

All at 100% mid fills (deterministic, no seed noise). None was profitable.

| Test | Best variant | n | win% | net | PF | DD% |
|---|---|---|---|---|---|---|
| T1 smooth trend | smooth10 30d stretch<=8% | 7 | 42.9 | -4,198 | 0.36 | 11.7 |
| T2 ADX | ADX>=35 +DI>-DI | 18 | 66.7 | -6,454 | 0.59 | 16.3 |
| T3 RSI | RSI<70 | 204 | 74.0 | -25,333 | 0.82 | 101.2 |
| T4 stochastics | %K<30 | 72 | 69.4 | -25,712 | 0.61 | 69.0 |
| **T5 HV>IV** | **HV>IV** | **166** | **74.1** | **-23,547** | **0.81** | **78.5** |
| T6 exits | 12+-2 DTE, exit 2 DTE | 150 | 64.0 | -28,343 | 0.71 | 93.2 |
| T7 diversification | fixed 1/sector (control) | 215 | 72.6 | -38,512 | 0.76 | 105.8 |

Notes:
- **T5 was the only filter to raise the win rate** (72.6% -> 74.1%) while cutting
  the loss 39%. Your inverted assumption (sell when HV > IV) has support.
- **Every T7 relaxation was worse than the control.** 2 per sector: -$82,127,
  DD 186.9%. Dynamic diversification did not find alpha; it found correlated risk.
- T6's 2-DTE exit beat plain 12+-2 DTE (-$28,343 vs -$41,383), supporting the
  gamma hypothesis, but cost win rate (68.9% -> 64.0%).

## 3. Bear calls, identical parameters

Same delta 0.25+-0.05, same R:R >= 0.20, same width, same DTE, same 14-day
blackout, same sizing, same 1-per-sector cap. Only the side flips.

| config | n | win% | net | PF | DD% |
|---|---|---|---|---|---|
| bull puts (reference) | 215 | 72.6 | -38,512 | 0.76 | 105.8 |
| bear call, no trend gate | 306 | 76.1 | +30,650 | 1.19 | 81.3 |
| bear call, price < 50 SMA | 211 | 77.7 | +26,168 | 1.24 | 62.6 |
| bear call, <50 SMA, ADX>=25 | 123 | 78.0 | +13,067 | 1.19 | 33.0 |
| bear call, <50 SMA, HV>IV | 144 | 72.2 | -2,185 | 0.97 | 63.8 |

## 4. The per-symbol switch -- FAILED

Per-symbol side selection, no market-wide input, three rules:

| rule | n | win% | net | PF | DD% | mix |
|---|---|---|---|---|---|---|
| always bull put | 215 | 72.6 | -38,512 | 0.76 | 105.8 | 215P/0C |
| always bear call | 211 | 77.7 | +26,168 | 1.24 | 62.6 | 0P/211C |
| switch (sma50) | 305 | 71.1 | -47,088 | 0.79 | 122.3 | 173P/132C |
| switch (rsi) | 321 | 71.7 | -28,193 | 0.88 | 147.6 | 179P/142C |
| switch (dmi) | 320 | 74.7 | -5,287 | 0.97 | 102.4 | 178P/142C |

**Every switch rule is worse than always-bear-call.** Two separate reasons:

**(a) Capacity, not signal.** The switch is slot-limited (max_open=12,
1/sector). Bull puts fill the book and crowd out calls:

    switch(sma50) took 132 calls; missed 109 always-call trades worth +$36,485
    switch(rsi)   took 142 calls; missed 119 worth +$16,671
    switch(dmi)   took 142 calls; missed 118 worth +$18,682

The switch is not picking the wrong side. It is running out of room.

**(b) The bull-put leg is unfixable in 2022.** In every switch, the put side
lost money (-$13k to -$40k) while the call side made money. No per-symbol rule
tested rescues the long side.

## 5. Is the bear-call edge statistically significant? NO

Permutation test, 20,000 shuffles, on return-on-risk (no normality assumption,
appropriate for the skewed payoff):

    mean RoR, bear calls : +2.80%  (n=211)
    mean RoR, bull puts  : -5.08%  (n=215)
    observed difference  : +7.88pp
    p-value              : 0.0871   -> NOT significant at 0.05

Three further reasons to distrust it:

**Monthly inversion.** Calls beat puts in 7 of 10 months -- but the 3 losing
months are exactly the up months:

    UP months (Mar/Jul/Nov):  puts 90.4% win, +$41,111 | calls 54.5% win, -$29,916
    DOWN months            :  puts 63.4% win, -$79,623 | calls 83.8% win, +$56,085

The signal is *direction*. It has no independent predictive content -- it will
invert the moment the market does, which is precisely the failure mode being
solved for.

**Concentration.** April 2022 alone is +$18,401 of the +$26,168 total = **70% of
all profit from one month.**

**Drawdown.** Even the best call config runs 62.6% DD at 7.5% sizing. Not
deployable regardless of sign.

## 6. Conclusion

There is no statistically significant per-symbol switching signal in this data.
What the 2022 test actually shows is simpler and more useful:

1. **The strategy is short-volatility with a directional tilt**, and 2022
   removed the tilt. Both sides lose when they fight the tape.
2. **The one genuine finding is T5**: selling when HV > IV raised the win rate.
   That is a volatility-pricing edge, not a direction bet, and it is the only
   result here that is conceptually likely to generalise.
3. **Sizing is the binding constraint.** 7.5% per position produces >100% DD in
   a bad year. Position sizing, not signal selection, is what makes 2022
   survivable.

## 7. What would actually settle this

- Re-run the switch on 2023 (the 2023 DBs were deleted for disk space and must
  be restored) -- a rule that only works in the year it was fitted is worthless.
- Re-run T2's DMI variants against the corrected indicators.
- Test a slot-allocation fix: reserve capacity for the minority side rather than
  first-come-first-served, which is what broke the switch mechanically.
