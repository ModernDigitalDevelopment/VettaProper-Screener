# Is the INVERSE of the micro signal an entry trigger?

**User's argument:** "If it does the exact opposite — isn't that exactly what
we are looking for? We are looking for a signal to activate the bull puts...
if the opposite of what I am saying is happening, isn't the opposite a signal?"

The logic is sound, and it had real support in our own data. The earlier gate
test found the long-tenor trades the gate would have **blocked** earned
+8.01 / +13.70 / +18.66% RoR against +0.63 / +0.71 / +1.01% for the trades it
kept. The signal was pointing at our best days while we proposed skipping them.

There is also a coherent mechanism, and it is *not* the one the original
research proposed. A bull put is short vol, long market. The signal fires on
high-VVIX days — when premium is richest. If the subsequent move is benign,
that is the ideal setup: fat credit, then decay. On that reading you would not
need to predict direction at all; the edge would come from the credit.

So it was worth testing properly. It fails, for a reason worth keeping.

## The condition for a legitimate inversion

Inverting a failed hypothesis is valid only when the signal **carries
information** — a large effect with a **consistent sign** — and merely has the
sign pointed the wrong way. If the effect is small and the sign flips between
neighbouring configurations, there is nothing to invert: inverting noise
yields noise, and selecting the configs that came out positive is
conditioning on the outcome.

## My first pass was invalid — retracted

`micro_invert.py` reported "positive in 7/8 configs, sign test p=0.070" and I
was about to treat that as near-significant. It is not a valid test. The
configs' armed-day sets overlap heavily:

| pair | Jaccard |
|---|---|
| 21/0.8/5 ~ 21/0.9/5 | **0.79** |
| 21/0.9/10 ~ 21/0.9/20 | **0.80** |
| 21/0.8/10 ~ 21/0.8/20 | 0.75 |
| 21/0.8/10 ~ 21/0.9/10 | 0.75 |

Fifteen pairs exceed Jaccard 0.50. The union of all 12 configs is just **134
days**. The 21-day family is essentially *one test wearing six hats*, so a
sign test treating them as independent trials massively understates p.
Retracted and replaced.

## Test 1: the economic hypothesis, at full power

The inversion claim reduces to something testable on **all 912 trades**, with
no reliance on the micro signal: *do bull puts entered when vol-of-vol is
elevated perform better?* VVIX demeaned **within quarter**, so the H1-2022
composition confound that killed the level gate cannot operate.

| tenor | n | Spearman rho | p |
|---|---|---|---|
| long 35-45 DTE | 238 | **-0.0664** | 0.314 |
| short 7-11 DTE | 674 | **-0.0538** | 0.151 |

Both rho are **negative** — the opposite of the inversion hypothesis — and
neither is significant. Within-quarter terciles:

| quarter | long high-low | short high-low |
|---|---|---|
| 2022Q1 | -13.43 | -21.19 |
| 2022Q2 | **+14.12** | **+20.93** |
| 2022Q3 | -29.89 | +4.22 |
| 2022Q4 | +6.73 | -4.42 |
| 2023Q2 | +5.50 | -7.59 |
| 2023Q4 | -30.31 | -14.19 |

High-VVIX tercile better in **3/6** (long) and **2/6** (short) quarters. Sign
test p = 1.000 and 0.688. A coin flip, with the sign mildly against the
hypothesis.

## Test 2: the signal as an entry trigger, selection-corrected

Max-statistic permutation across all 12 configs, so the null knows we scanned
twelve. Day counts preserved per quarter.

| tenor | best config | effect | null mean | null p95 | corrected p |
|---|---|---|---|---|---|
| long | 21/0.8/10 | +12.39pp | **+23.92pp** | +35.17pp | **0.957** |
| short | 63/0.8/20 | +21.03pp | +16.51pp | +24.19pp | **0.142** |

Neither significant. Note the long tenor: the best observed effect (+12.39pp)
is **below the null's mean** (+23.92pp) — selecting 7 days at random typically
does *better* than the signal's choice.

## Why +18.66% looked so impressive — the real lesson

Return-on-risk is violently right-skewed (a credit spread wins a little often
and loses a lot rarely). So **any** small sample of days produces a large
positive average. Simulating random day-picks on our own trades:

**Long tenor, all-days RoR +1.31%:**

| days picked | mean | p90 | p99 | max |
|---|---|---|---|---|
| 4 | +2.73 | **+22.96** | +35.78 | +55.04 |
| 7 | +1.89 | +17.07 | +28.19 | +45.90 |
| 11 | +1.70 | +14.01 | +22.77 | +31.81 |
| 50 | +1.34 | +6.09 | +10.08 | +15.01 |

The config that produced +18.66% selected **4 days**. Random 4-day picks clear
+22.96% a tenth of the time. The headline number was never evidence — it was
the arithmetic of a skewed distribution and a tiny sample. This is why the
gate looked like it was blocking our best days: with n=4 to n=11, it could
hardly have looked like anything else.

## Verdict

The inversion is a legitimate question, correctly reasoned, and the answer is
no — not because the sign is wrong, but because **there is no signal of either
sign to invert**. The micro signal fires 0-16 times in our window; at that
sample size nothing it does is distinguishable from chance in either direction.

The genuinely useful finding is the skew artifact. It applies retroactively to
every small-sample subset result in this programme and is now the first thing
to check before any future subset claim.

## Honest limitation

This tests the inversion **on our 912 bull puts over six quarters**. It does
not test it over his 2007-2026 window, where the signal fires ~37 times and
2008/2018 dominate. If the inverse has an edge, it would have to show up in a
dataset with far more firings than ours contains. That is a data problem, not
a settled question — but it also means our data cannot be used to support the
inversion either.

## Files

`bt/micro_invert.py` (first pass, invalid sign test — retained with the error
documented), `bt/invert_proper.py` (corrected: within-quarter rank
correlation, tercile sign test, max-statistic permutation).
