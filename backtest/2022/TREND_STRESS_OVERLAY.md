# "Trend + Stress Overlay": what is testable, and what Layer 1 does to the book

Source: user's `analysis.py` + `results.csv` and his written summary proposing
a two-layer overlay (200dma position sizing + a 5-day VVIX/A-D stress
trigger).

## Data status: Layer 2 is NOT testable from this upload

`analysis.py` reads four files, **none of which were uploaded**:

| file | present |
|---|---|
| `vvix.csv` | no (I have CBOE VVIX, so this one is covered) |
| `NYSE_advn.csv` | **no** |
| `NYSE_decln.csv` | **no** |
| `ad_recon.csv` | **no** |

Only the scripts and the summary CSV came through. The official NYSE
advance/decline series -- the thing I actually asked for, and the thing his own
summary names as the top priority ("Get an official NYSE A/D feed for 2020
onward") -- is still missing. So Layer 2 cannot be run, and the micro-level A/D
work cannot start. **Still needed: `NYSE_advn.csv`, `NYSE_decln.csv`,
`ad_recon.csv`.**

## What `results.csv` actually contains

20 configurations. **Every one underperforms buy-and-hold on CAGR**:

| mode | best CAGR | best Sharpe | B&H |
|---|---|---|---|
| confluence | 9.6% | 0.546 | 11.2% / 0.582 |
| ad_only | 7.6% | 0.472 | " |
| vvix_only | 7.7% | 0.586 | " |

Worth noting: the only config whose Sharpe beats buy-and-hold is
`vvix_only / 0.95 / vvix` at 0.586 vs 0.582 -- a 0.004 difference, i.e. nothing
-- and it is **VVIX alone with no A/D at all**. Within this file, adding
breadth never helps. That is consistent with my own decomposition
(MICRO_VVIX_AD.md §4), where the VVIX leg had no forward power over 20 years
and all apparent signal sat in the A/D leg.

The headline numbers in his summary (Sharpe 0.92, maxDD -19%, the recommended
"200d trend sizing" variant) are **not in `results.csv`** and not produced by
`analysis.py`. They come from a run I have not been given. I am not disputing
them -- I simply cannot check them, and they should not be treated as verified.

## Layer 1 tested on the bull-put book

His recommendation: *"Below the 200-day: cut new position size in half, or move
to iron condors."* SPY 200dma from `spy_yahoo.csv`, full coverage of all 912
trades.

### The pooled split looks supportive

| tenor | above 200dma | below 200dma | gap | p |
|---|---|---|---|---|
| long 35-45 DTE | +5.09% (n=113) | -2.11% (n=125) | +7.20pp | 0.231 |
| short 7-11 DTE | **+1.81%** (n=334) | **-6.61%** (n=340) | **+8.42pp** | **0.034** |

p=0.034 is the first sub-0.05 result in this programme. It does not survive.

### It is the composition confound again

| quarter | short: n above | n below | quarter RoR |
|---|---|---|---|
| 2022Q3 | **2** | 131 | -8.11% |
| 2022Q4 | 16 | 105 | -4.16% |
| 2023Q2 | **140** | **0** | +5.64% |
| 2023Q4 | 129 | 7 | +7.46% |

"Above the 200dma" is nearly a synonym for *2023*, and 2023 was profitable.
"Below" is nearly a synonym for *2022 H2*, which was not. The variable being
measured is the calendar.

### Stratified within-quarter, the sign REVERSES

Holding quarter fixed so composition is removed mathematically rather than
argued away:

| tenor | stratified (above - below) | 95% CI | p |
|---|---|---|---|
| long | **-10.28pp** | [-21.77, +4.39] | 0.148 |
| short | **-11.36pp** | [-20.84, -1.94] | **0.019** |

Within a given quarter, bull puts entered **below** SPY's 200dma did
*better*, not worse -- the opposite of Layer 1's premise, and significant on
the short tenor. Per-quarter: "above" was better in 1/3 (long) and 1/4 (short)
comparable quarters.

### But the reversal is one quarter, so I am not claiming it either

Leave-one-quarter-out on the short tenor:

| dropped | stat | 95% CI | p |
|---|---|---|---|
| (none) | -11.36 | [-21.07, -1.91] | 0.018 |
| 2022Q1 | -17.19 | [-27.60, -7.47] | 0.001 |
| 2022Q2 | -12.99 | [-22.91, -2.39] | 0.015 |
| **2022Q4** | **-4.22** | **[-15.18, +6.64]** | **0.430** |
| 2023Q4 | -11.02 | [-23.53, +1.54] | 0.086 |

Dropping **Q4 2022** collapses the effect from -11.36pp (p=0.018) to -4.22pp
(p=0.430). Q4 2022 is the quarter where below-200dma trades returned +0.18%
against above-200dma's -32.59% on n=16 -- the October 2022 bottom, where being
short puts into a washed-out market worked and the handful of above-200dma
entries were unlucky.

So the honest statement is: **the 200dma split carries no reliable signal in
either direction.** The pooled version is calendar composition; the
within-quarter reversal is one quarter. Three quarters of comparable data
cannot settle it.

## Does halving size help anyway?

Sizing is a linear scaling of P&L, so it cannot change expectancy -- only the
return/risk ratio. Confirmed:

| tenor | rule | net | peak dd | net/dd |
|---|---|---|---|---|
| long | full size | +$7,080 | $32,107 | 0.22 |
| long | half below 200dma | +$9,973 | $21,456 | **0.46** |
| long | flat below 200dma | +$12,867 | $14,058 | **0.92** |
| short | full size | -$43,548 | $88,578 | -0.49 |
| short | half below 200dma | -$17,069 | $60,105 | -0.28 |
| short | flat below 200dma | +$9,410 | $33,360 | **0.28** |

net/dd improves monotonically as you de-risk below the 200dma, and "flat
below" turns the short tenor from -$43,548 to +$9,410.

**This is not evidence that the 200dma is informative.** It is the same
composition effect measured a third way: "flat below the 200dma" ≈ "don't
trade 2022 H2," and we already know 2022 H2 lost money. A rule that sits out
the losing period always improves net/dd in-sample. Given the stratified test
found the within-quarter effect pointing the *other* way, I would not deploy
this expecting the net/dd numbers to repeat.

## Verdict

- **Layer 2 is untestable** until the raw NYSE A/D files arrive.
- **Layer 1's premise does not hold on this book.** Pooled support is calendar
  composition; the within-quarter effect reverses sign; the reversal rests on
  one quarter. No reliable signal either way.
- The `results.csv` he sent has every config losing to buy-and-hold on CAGR,
  and the one config that edges it on Sharpe (by 0.004) is **VVIX with no A/D**.
- His own caveats are the right ones and I would not soften them: two crisis
  years drive the value, settings were chosen on the test data, and the
  post-2020 A/D is reconstructed.

## Agreement worth recording

His line *"the A/D line is better at confirming a bottom than warning before a
drop. Keep it as a re-entry check, not an exit signal"* is consistent with
everything measured here: the A/D breach protocol hurt as an exit, the A/D
timing gates showed no skill, and the one quarter where below-200dma entries
won (Q4 2022) was a bottom. If the A/D data arrives, the re-entry hypothesis
is the version worth testing first -- not another exit gate.

## Files

`bt/layer1.py` (200dma split + sizing), `bt/layer1_confound.py`
(composition, within-quarter, stratified bootstrap).
User originals: `analysis_user.py`, `analysis_results_user.csv`.
