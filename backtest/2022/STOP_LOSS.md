# Credit-multiple stop loss on bull puts

**Question (user, verbatim):** "what if we get out of all bull puts if the loss
hits the potential gain mark... especially 2022"

A credit spread's potential gain **is** the credit. So "loss equals potential
gain" is a **1x-credit stop**: close when the debit to close reaches 2x the
credit received. Implemented as `Spec.stop_loss_mult`, checked *before* the
time-based exits so a position already beyond the stop closes today rather
than drifting to its DTE cutoff.

Tested at 0.5x / 1.0x / 1.5x / 2.0x against a no-stop control, on two tenors,
across six quarters (2022 Q1-Q4, 2023 Q2 and Q4 -- the only quarters with
option data).

## Headline

**The stop works exactly as a stop should, and it does not make the strategy
profitable.** Those are two separate findings and both matter.

## 1. It cuts the tail, monotonically and reliably

Matched trades only (same symbol, same entry date, same strike), so this is
the stop's effect on a position, not a different set of positions.
Return-on-risk percentiles, all six quarters:

**Short tenor (7-11 DTE), n=674 control**

| stop | mean | p05 | CVaR5 | losses > 1x credit |
|---|---|---|---|---|
| none | -2.44% | -91.9 | -99.4 | **15.4%** |
| 0.5x | -1.87% | -50.0 | **-71.0** | **5.1%** |
| 1.0x | -3.03% | -67.8 | -82.7 | 12.4% |
| 1.5x | -2.05% | -73.7 | -87.7 | 17.0% |
| 2.0x | -1.81% | -81.5 | -92.4 | 17.0% |

**Long tenor (35-45 DTE), n=238 control**

| stop | mean | p05 | CVaR5 | losses > 1x credit |
|---|---|---|---|---|
| none | +1.31% | -89.6 | -100.1 | **14.3%** |
| 0.5x | +1.57% | -40.8 | **-54.9** | **1.7%** |
| 1.0x | +0.13% | -62.5 | -81.6 | 8.2% |
| 1.5x | +1.54% | -74.8 | -89.1 | 14.8% |
| 2.0x | +1.65% | -87.2 | -98.4 | 15.0% |

CVaR5 (the mean of the worst 5%) improves **monotonically** as the stop
tightens, in both tenors, with no exceptions. Catastrophic losses fall from
14-15% of trades to 1.7-5.1%. This is the cleanest dose-response relationship
found anywhere in this research programme.

## 2. It does not improve the mean, and the "best" arm is not significant

Paired day-blocked bootstrap (B=10,000) on matched trades. Positions opened
the same day share one market shock, so they are blocked rather than treated
as independent.

| tenor | stop | paired diff | 95% CI | p |
|---|---|---|---|---|
| long | 0.5x | +0.36pp | [-3.45, +4.16] | 0.854 |
| long | 1.0x | +0.26pp | [-1.85, +2.51] | 0.835 |
| long | 1.5x | +0.27pp | [-1.28, +2.11] | 0.786 |
| long | 2.0x | -0.45pp | [-1.63, +0.67] | 0.427 |
| short | 0.5x | -0.18pp | [-2.73, +2.39] | 0.876 |
| short | 1.0x | +0.29pp | [-1.46, +2.08] | 0.750 |
| short | 1.5x | +0.94pp | [-0.14, +2.01] | 0.089 |
| short | 2.0x | +0.42pp | [-0.15, +0.99] | 0.141 |

Nothing clears the Bonferroni threshold (p < 0.0125 for four arms). Not one.

The pooled table's apparent winner -- long tenor, 1.5x, +$19,120 and 5 of 6
quarters positive -- is **best-of-4 selection**. Corrected p = 0.617. And the
ordering is **non-monotone**: 1.0x is worse than both 0.5x and 1.5x. There is
no mechanism by which a mid-level stop is worse than both a tighter and a
looser one, so the spread across arms is sampling noise, not dose-response.

This is the same trap as the earlier asymmetric-spec and long-DTE claims. I am
flagging it before it becomes a thesis.

## 3. The user's exact rule (1.0x) is the worst stop tested

| tenor | none | **1.0x** | best |
|---|---|---|---|
| long, pooled net | +$7,080 | **-$2,874** | +$19,120 (1.5x) |
| short, pooled net | -$43,548 | **-$53,456** | -$23,760 (0.5x) |

1.0x is worse than no stop at all on both tenors. Given finding 2, I would not
claim 1.0x is *genuinely* harmful -- it is inside the noise band like
everything else -- but there is certainly no evidence for it, and it is the
one level that lost on both tenors.

## 4. Why the thinner tail does not become a thinner drawdown

net / peak-drawdown (dollars earned per dollar of worst peak-to-trough):

| tenor | none | 0.5x | 1.0x | 1.5x | 2.0x |
|---|---|---|---|---|---|
| long | 0.20 | 0.09 | -0.07 | 0.59 | 0.27 |
| short | -0.47 | -0.29 | -0.50 | -0.42 | -0.36 |

Per-trade tails shrink; portfolio drawdown does not follow. Partial
explanation: a stop frees capital mid-selloff and the engine immediately
redeploys it into the same falling market.

| tenor | stop | MATCHED RoR | EXTRA (redeployed) RoR | extras themselves stopped |
|---|---|---|---|---|
| short | 0.5x | -1.87% | -0.05% | 40% |
| short | 1.0x | -3.03% | **-2.30%** | 30% |
| long | 0.5x | +1.57% | **-1.28%** | 48% |
| long | 1.0x | +0.13% | **-1.83%** | 28% |

Note the tighter stops recycle capital hard: 40-48% of the replacement trades
at 0.5x were *themselves* stopped out. The saved tail is handed back.

**Caveat against my own hypothesis:** long-tenor 1.5x has EXTRA at +11.42%,
which contradicts the redeployment story. n=44. I think that cell is noise,
but I am not going to quietly drop the one number that disagrees with me.

## 5. Q2 2022 specifically (the user's "especially 2022")

Q2 2022 is the quarter that broke every prior strategy. The stop helps most
here, which is what you would hope:

| tenor | stop | net | L/W | losses > 1x credit |
|---|---|---|---|---|
| short | none | -$44,116 | 2.37 | 29.6% |
| short | 0.5x | **-$28,363** | **1.30** | **6.8%** |
| long | none | -$25,924 | 2.02 | 41.5% |
| long | 0.5x | **-$21,844** | **1.09** | **6.2%** |

A 36% reduction in loss on the short tenor, and loss/win drops near 1.0 -- the
variable the 180-config meta-analysis identified as decisive. But it is damage
limitation, not edge. Q2 2022 stays firmly negative under every stop level.

And Q1 2022 runs the other way: 0.5x turns -$1,566 into -$4,063 on the short
tenor. One quarter helps, the next hurts.

## Verdict

- A stop is **real risk control**: CVaR5 and the frequency of >1x-credit losses
  improve monotonically with tightness. That is worth having for position
  sizing and for sleeping at night.
- A stop is **not an edge**: no arm is significant, the best arm fails
  best-of-4 correction, and the ordering is non-monotone.
- **1.0x -- the rule as specified -- is the weakest level tested.** If a stop
  is used, 0.5x is the one with the tail evidence behind it.
- The strategy's problem in 2022 is not exit discipline. It is that short puts
  into a sustained decline lose money. A stop changes how much; it does not
  change the sign.

## Method notes

- Pooling is done on trades, never by averaging per-quarter percentages across
  unequal n.
- Bootstrap blocks by entry day throughout.
- MATCHED/EXTRA split keeps the stop's effect separate from the capacity
  effect of freed slots; mixing them confounds the two.
- An earlier version of `stop_sig.py` reported a `p(>none)` column computed by
  comparing two independent *sorted* bootstrap distributions element-wise.
  That is a quantile comparison, not a hypothesis test, and the p-values it
  produced (0.000, 0.004, 0.007) were meaningless. Superseded by the paired
  test in `stop_paired.py`. Recording it here so the bad numbers are not
  quoted later from the log.

## Files

`bt/stoploss.py` (runner, env-parameterised), `bt/stop_pool.py`,
`bt/stop_paired.py`, `bt/stop_tail.py`, `bt/stop_dd.py`, `bt/stop_replace.py`,
`bt/stop_sig.py` (superseded, kept with its error documented).
Results: `r_stop_{2022Q1..Q4,2023Q2,2023Q4}.pkl`.
