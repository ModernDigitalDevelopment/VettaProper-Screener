# VVIX level gate: looked excellent, is a calendar confound

Follow-up to MICRO_VVIX_AD.md, where I proposed testing a fixed-threshold
VVIX **level** gate ("don't open bull puts when VVIX > X") as distinct from the
percentile gate that failed. I suggested this would need a quarter of engine
time. **It did not** -- a level gate is a pure entry-date filter, so it can be
screened on the 912 trades already in hand, across all six quarters, for free.
Doing that first was the right call, because it fails.

## The screen looked very strong

`vvix_level.py`, blocking entries whose day breached the threshold, judged
against 5,000 random equal-size day-block nulls:

**Long tenor (35-45 DTE), ungated net +$7,080**

| gate | blocked days | blocked RoR | kept RoR | kept net | null mean | pctile |
|---|---|---|---|---|---|---|
| VVIX>90 | 64 | -8.31% | **+12.13%** | **+$29,923** | +$3,327 | **1.00** |
| VVIX>95 | 54 | -4.97% | +6.02% | +$17,215 | +$4,107 | 0.95 |
| VVIX>100 | 43 | -4.83% | +4.60% | +$16,394 | +$4,601 | 0.93 |
| VVIX>110 | 21 | -12.26% | +4.13% | +$18,743 | +$5,928 | 0.98 |

**Short tenor (7-11 DTE), ungated net -$43,548**

| gate | blocked days | blocked RoR | kept RoR | kept net | null mean | pctile |
|---|---|---|---|---|---|---|
| VVIX>90 | 142 | -4.65% | -0.49% | **-$6,379** | -$21,484 | 0.83 |
| VVIX>100 | 77 | -9.00% | -0.38% | -$9,860 | -$31,222 | 0.93 |
| VVIX>110 | 44 | -12.21% | -1.03% | -$17,925 | -$36,516 | 0.94 |

Percentiles 0.83-1.00, monotone-ish in threshold, both tenors agreeing, and
the short tenor's loss shrinks from -$43,548 to -$6,379. On the face of it
this is the best timing result in the entire programme.

## It is composition, not skill

The tell is in the same script's first panel -- VVIX on our actual entry days,
by quarter:

| quarter | entry days | median VVIX | % > 100 |
|---|---|---|---|
| 2022Q1 | 35 | 124 | **100%** |
| 2022Q2 | 46 | 111 | **65%** |
| 2022Q3 | 56 | 88 | 11% |
| 2022Q4 | 49 | 83 | 14% |
| 2023Q2 | 56 | 91 | 5% |
| 2023Q4 | 56 | 87 | 14% |

The gate blocks **100% of Q1 2022 and 65% of Q2 2022** -- the two worst
quarters -- and barely touches the rest. It is not selecting bad *days*; it is
deleting bad *quarters* wholesale. "Don't trade H1 2022" is hindsight, not a
signal.

### Test 1: within-quarter split at each quarter's own VVIX median

Equal halves inside each quarter, so composition cannot drive the result. If
VVIX carries day-level information, the low half should beat the high half.

| quarter | long: low-high | short: low-high |
|---|---|---|
| 2022Q1 | +14.09 | +32.31 |
| 2022Q2 | **-7.12** | **-17.32** |
| 2022Q3 | +39.55 | **-0.82** |
| 2022Q4 | **-4.70** | **-0.57** |
| 2023Q2 | **-15.12** | **-2.49** |
| 2023Q4 | +23.77 | +3.88 |

Low-VVIX half better in **3 of 6** quarters (long) and **2 of 6** (short).
Sign test p = 1.000 on both. That is a coin flip.

### Test 2: the VVIX>100 gate judged within each quarter

| quarter | long pctile | short pctile |
|---|---|---|
| 2022Q1 | **degenerate -- blocks every entry day** | **degenerate** |
| 2022Q2 | 0.25 | 0.42 |
| 2022Q3 | 0.60 | 0.52 |
| 2022Q4 | 0.30 | 0.57 |
| 2023Q2 | 0.78 | 0.59 |
| 2023Q4 | 0.47 | 0.84 |

Judged against its own quarter's trades, the gate lands at 0.25-0.84 -- no
skill, and in Q1 2022 it is degenerate: it blocks the entire quarter, which is
a calendar rule with extra steps.

### Test 3: composition accounting

Share of the pooled lift attributable to each quarter's removed trades:

| tenor | lift | H1 2022's share |
|---|---|---|
| long | +$9,314 | **132%** |
| short | +$33,688 | **86%** |

Q2 2022 alone supplies 143% of the long-tenor lift (other quarters are
negative contributors, i.e. the gate removed *profitable* trades there). The
entire effect is two quarters out of six.

This is structurally the same error as the earlier "35-45 DTE survives both
regimes" claim that had to be retracted: a result driven by which quarters
happened to be in the sample, dressed up as a mechanism.

## Verdict

Reject. Same fate as the percentile gate, for a different reason -- the
percentile gate had no signal; the level gate has a signal that is entirely
"2022 H1 was bad," which is unusable prospectively.

There is also an honest-uncertainty point worth stating: with only six
quarters and one genuine bear episode, **any** regime filter will look
brilliant by deleting H1 2022 and cannot be distinguished from a calendar
rule. This dataset cannot validate regime filters. That is a data limitation,
not a verdict on regime filtering in general -- but it does mean no further
regime-gate test on this data is worth running. Eleven mechanisms, eleven
rejections.

## Why no engine run was needed

A level gate only removes entry days, so it can be evaluated on existing
trades. **Caveat:** this screen cannot capture capacity effects -- when the
gate blocks an entry, the real engine may fill a different position later with
the freed slot. The stop-loss work showed redeployment matters (40-48% of
replacement trades were themselves stopped out). So a *pass* here would have
justified an engine run; a *failure* at the day-selection level cannot be
rescued by capacity effects, because the gate would first have to pick the
right days, and it does not.

## Files

`bt/vvix_level.py` (gate screen + random-null control),
`bt/vvix_confound.py` (within-quarter, per-quarter-null, composition tests).
