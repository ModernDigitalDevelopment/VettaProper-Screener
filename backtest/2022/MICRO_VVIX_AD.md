# Micro-VVIX + short-term A/D divergence: can it gate the bull-put book?

Source: user's `micro.py` and `micro_results.csv` from a separate research
thread, plus his written summary. His headline: short-window VVIX percentile
AND unconfirmed-new-high A/D divergence, traded as a 5-day short, gives
CAGR 15.8% / Sharpe 0.81 vs 11.1% / 0.57 buy-and-hold, with the caveat that
"nearly all of the gain comes from two years, 2008 and 2018."

His recommendation for *this* book was specifically:
> "use the short-window signal to stop opening new trades for 5 days rather
> than to short. In this test, going to cash for 5 days already took Sharpe
> from 0.57 to about 0.73 with no short-side risk."

## Data unlocked

**Real VVIX is now in the repo** (`bt/vvix_cboe.csv`, 5,116 days,
2006-03-06..2026-10-02, from CBOE's public daily-price endpoint). This closes
a gap flagged repeatedly in earlier work: VVIX had 0 rows in every option DB,
and the stand-in -- 20-day realised vol *of* VIX -- had a median of 88 vs real
VVIX's ~100, so no numeric threshold could be mapped honestly. That excuse is
gone. Also added `bt/spy_yahoo.csv` (5,463 days from 2005, same Yahoo endpoint
`micro.py` uses).

## 1. His "fired zero times in 2022" is confirmed, and it is disqualifying

Signal replicated verbatim from `micro.py` on our own breadth
(`micro_sig.py`). Onset counts:

| cfg (vlook/pct/div_w) | 2022 | 2023 | 2024 |
|---|---|---|---|
| 21 / 0.80 / 5 | **3** | 4 | 9 |
| 21 / 0.80 / 10 | **1** | 5 | 8 |
| 21 / 0.80 / 20 | **0** | 4 | 8 |
| 21 / 0.90 / 5 | **1** | 5 | 8 |
| 63 / 0.80 / 5 | **2** | 2 | 6 |
| 63 / 0.80 / 10 | **3** | 2 | 4 |
| 63 / 0.90 / 5 | **0** | 1 | 1 |

At most **3 firings in the whole of 2022**. The reason is structural, not a
data artifact: the signal requires the S&P to make a **new N-day high**. 2022
was a downtrend. A rule armed by new highs cannot fire in a year that doesn't
make them -- and 2022 is precisely the year the bull-put book needs protecting.

Note the VVIX leg alone was *not* the constraint: VVIX sat at/above its
trailing 21-day 80th percentile on **61 days** in 2022 (p90 on 37). The
divergence leg is what suppresses it.

## 2. It touches almost none of our book, and what it touches is our best

Measured against the 912 bull-put trades from the stop-loss control arms
(`micro_overlap.py`), blocking entries for 5 days after each fire:

| cfg | entry days blocked | long-tenor BLOCKED RoR | long-tenor KEPT RoR |
|---|---|---|---|
| 21/0.80/5 | 29 of 298 (9.7%) | **+8.01%** | +0.63% |
| 21/0.80/10 | 21 of 298 (7.0%) | **+13.70%** | +0.71% |
| 63/0.80/10 | 12 of 298 (4.0%) | **+18.66%** | +1.01% |
| 63/0.90/5 | **0 of 298** | n=0 | +1.31% |

The gate blocks the *most profitable* long-tenor trades we have, by an order
of magnitude. High VVIX means fat credits; a gate that stands down on
high-VVIX days stands down exactly when bull puts are best paid.

On the short tenor the direction is inconsistent (one config helps, two hurt),
which is what noise looks like.

## 3. No skill versus random blocking

The above is suggestive but not sufficient -- blocked days aren't a random
sample. Proper control (`micro_skill.py`): does blocking *these* days beat
blocking the same **number** of randomly chosen entry days? 5,000 draws,
whole days in or out so the correlation structure is preserved.

| tenor | cfg | kept net | null mean | percentile |
|---|---|---|---|---|
| long | 21/0.80/5 | +$3,486 | +$6,421 | 0.29 |
| long | 21/0.80/10 | +$3,971 | +$6,665 | 0.25 |
| long | 21/0.90/5 | +$6,139 | +$6,525 | 0.49 |
| long | 63/0.80/10 | +$5,311 | +$6,850 | 0.32 |
| short | 21/0.80/5 | -$41,525 | -$38,856 | 0.40 |
| short | 21/0.80/10 | -$37,121 | -$40,253 | 0.65 |
| short | 21/0.90/5 | -$45,092 | -$40,225 | 0.29 |
| short | 63/0.80/10 | -$35,679 | -$42,006 | 0.85 |

Every percentile sits in 0.25-0.85. **No configuration distinguishes itself
from randomly skipping the same number of days.** Four of eight land below
0.50, i.e. mildly worse than random. This is the tenth mechanism tested for
"when to be in the market" and the tenth to show no skill.

## 4. The VVIX leg carries none of the signal -- all of it is the A/D leg

This is the decomposition his grid never ran, and it matters most because the
A/D data is the part he himself flagged as weakest. `micro_decomp.py`, forward
SPY excess return vs the unconditional mean:

**VVIX percentile alone, full 2006-2026 (no breadth needed, n=196-408):**

| signal | exc 5d | t | exc 10d | t | exc 20d | t |
|---|---|---|---|---|---|---|
| VVIX 21d p80 | -0.07 | -0.60 | -0.14 | -0.81 | -0.31 | -1.27 |
| VVIX 21d p90 | -0.08 | -0.52 | -0.08 | -0.41 | -0.31 | -1.17 |
| VVIX 63d p80 | +0.03 | +0.23 | -0.03 | -0.18 | -0.14 | -0.46 |
| VVIX 63d p90 | -0.07 | -0.42 | -0.01 | -0.02 | -0.14 | -0.39 |

**Nothing.** Twelve cells, |t| max 1.27, on 20 years and up to 408 events.
A high VVIX percentile on its own tells you nothing about forward S&P returns.

So the t = -2.2 to -3.1 in `micro_results.csv` is produced **entirely by the
A/D divergence leg**, on a breadth series that is official only to 2020-02 and
reconstructed-without-delistings afterwards. The entire result rests on the
one input he identified as the biggest open question. That is the opposite of
a robust finding.

## 5. In 2022-2024 the conjunction has the WRONG SIGN

Same script, panel B -- the conjunction on our breadth window:

| signal | n | exc 5d | t | exc 10d | t | exc 20d | t |
|---|---|---|---|---|---|---|---|
| VVIX 63d p80 + div5 | 10 | **+1.29** | 1.99 | **+2.02** | 2.39 | **+2.89** | 2.24 |

The S&P went **up** after these signals, by ~2pp over 10 days, with t = +2.4.
For a signal meant to precede weakness that is the wrong sign at conventional
significance. n=10, so I would not claim the market reliably rallies -- but it
certainly isn't falling, and this is a close relative of the 63/0.90/5 config
his grid selected as the winner.

Panel C (VVIX alone, same 2022-2024 window) is mildly negative
(-0.43 to -0.59 at 5d). So in recent data the breadth leg **flips the sign of
the VVIX leg** rather than sharpening it.

This independently reproduces his own concern -- "2020-2026: +0.7%, the market
went up" -- using *real* VVIX and a *different* A/D series. Two independent
breadth constructions agreeing that the effect reverses post-2020 points
toward the effect having stopped working, rather than toward his
reconstruction being at fault.

## Verdict

Do not gate the bull-put book with this signal.

1. It cannot fire in a downtrend (needs new N-day highs), so it is absent in
   2022 -- the only year we have that needs a gate.
2. It blocks 0-10% of our entry days, and the ones it blocks are our best.
3. It shows no skill against random day-blocking in any of 8 tested configs.
4. Its VVIX half has zero forward predictive power over 20 years; all the
   claimed power sits in the least reliable input.
5. In 2022-2024 the conjunction precedes *gains*, not losses.

His own framing was already honest about this -- "it works as a crash-hedge
overlay, it is not a dependable short-term trading edge", and "the rule fired
zero times in 2022." Those two statements together are sufficient to rule it
out as a timing gate for a 2022-era bull-put book, and the tests above confirm
it on our data rather than taking it on faith.

**What is worth keeping is the VVIX data itself.** A fixed-threshold VVIX
level gate (not a percentile, not conjoined with breadth) is now testable for
the first time, and is a different hypothesis from the one tested here: a
percentile measures *change* in vol-of-vol, a level measures *regime*. 2022
averaged VVIX 101.8 vs 2023-2024's calmer readings, so a level gate would
actually discriminate the years a percentile gate cannot. That is the next
test, and it does not depend on any A/D series.

## Method notes

- Our A/D is a 494-name large-cap line from the Polygon universe, **not** NYSE
  breadth. This is a replication on a different breadth series, not a
  reproduction of his run. Stated here rather than buried: a large-cap A/D
  line misses the small caps and non-operating issues that dominate NYSE
  breadth, so disagreement with his numbers is expected and is not by itself
  evidence against him. The agreement on the 2022 zero-firing and the
  post-2020 sign flip is the meaningful part, because those are structural.
- Signal logic is copied verbatim from `micro.py` (rolling VVIX percentile,
  rolling-max price/breadth comparison, K=3 arming window, onset detection).
- His t-stats are computed on signal days against an unconditional base; the
  same convention is used here for comparability.
- **Error caught mid-analysis:** the first run of `micro_sig.py` sourced SPY
  from `daily_2022.csv.gz`, which only covers 2022, so 2023/2024 firing counts
  read as a spurious zero and panel A's "full history" label was wrong. Fixed
  by pulling SPY 2005-2026 from Yahoo and re-running everything. The corrected
  panel A (n up to 408 rather than 115) is what is reported above.

## Files

`bt/micro_sig.py` (signal replication), `bt/micro_overlap.py` (book reach),
`bt/micro_skill.py` (random-blocking control), `bt/micro_decomp.py` (leg
decomposition). Data: `bt/vvix_cboe.csv`, `bt/spy_yahoo.csv`.
User-supplied originals: `bt/micro.py`, `bt/micro_results.csv`.
