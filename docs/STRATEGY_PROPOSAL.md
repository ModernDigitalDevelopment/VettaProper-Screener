# Strategy proposal, after 180 backtested configurations

Written for review. Every number below was recomputed from stored trade lists,
not copied from earlier summaries.

## 1. What the whole body of work actually says

180 configurations across 2022 and 2023 (7,879 unique simulated trades).
46 of 164 with n>=40 were profitable — a 26% hit rate, about what random
parameter search would produce. That is the honest baseline against which any
single "winner" must be judged.

**Nine direction-selection mechanisms were tested. All nine failed:**
ADX/DMI, A/D breadth (9 measures), per-symbol SMA switch, contrarian 5/20 SMA,
the macro regime overlay (200dma + NH-NL + VIX + credit), the A/D reaction-low
breach protocol, the golden cross (50/200), the asymmetric per-side gate, and
the Keltner squeeze.

The asymmetric gate was measured directly against random symbol selection and
came out **0.8–0.9pp WORSE than random** at avoiding adverse moves, in both
years. Its +$64,854 on 2022 became **−$32,074 on 2023** with the spec frozen.

Your read is correct: the indicators do not carry a usable directional signal
in this data.

## 2. The thing we missed

Pooling all 164 configs and asking what separates winners from losers:

| metric | profitable configs | unprofitable configs |
|---|---|---|
| median win rate | **58.9%** | **67.8%** |
| median loss/win ratio | **0.94** | **3.16** |
| median return-on-risk | +7.38% | −5.08% |

**Profitable configurations had a LOWER win rate.** The entire project had been
optimising the wrong variable.

Hit rate by loss/win band:

| loss/win ratio | configs | profitable | hit rate |
|---|---|---|---|
| 0.0–0.8 | 18 | 11 | 61% |
| **0.8–1.0** | 19 | 15 | **79%** |
| 1.0–1.5 | 18 | 6 | 33% |
| 1.5–2.5 | 28 | 6 | 21% |
| 2.5+ | 81 | 8 | **10%** |

By win rate the relationship is nearly the inverse — the 65–75% win-rate band
was profitable only **8%** of the time, because a high win rate was always
bought with a punishing loss/win ratio.

## 3. A bug that was hiding the main effect

`close_debit()` returns `None` when any leg lacks a quote. The old code then
did `still.append(p); continue` — **skipping the exit check entirely**, so a
position past its `exit_at_dte` cutoff drifted to expiration.

Measured: **all 44 EXPIRED trades** in the tuned 2023 condor run had run their
FULL dte despite `exit_at_dte=1`.

This mattered because expiry is the single worst outcome in the dataset:

| exit reason | n | win% | mean RoR |
|---|---|---|---|
| EXPIRED | 2,779 | 40.7% | **−29.0%** |
| EOD_EXIT_DTE2 | 2,423 | 55.4% | **+10.6%** |
| EOD_EXIT_DTE1 | 229 | 55.0% | **+17.8%** |

## 4. The one finding that holds in both years

Q2, condor 10 DTE delta 0.40, only the exit rule varied:

| | hold to expiry | best early exit | improvement |
|---|---|---|---|
| **Q2 2022** | −$97,820 (win 15.7%) | −$9,257 (win 44.9%) | **+$88,563** |
| **Q2 2023** | −$14,219 (win 31.1%) | +$48,550 (win 58.7%) | **+$62,769** |

Same sign, both years, and an effect size nothing else in 180 configs approaches.
**Exit discipline is the edge. Not entry selection.**

Supporting evidence from the pooled per-trade data, measured *within* each
structure so it is not a structure confound:

| structure | delta band | n | win% | L/W | RoR |
|---|---|---|---|---|---|
| bull_put | 0.20–0.30 | 1,551 | 64.6% | 3.10 | **−9.7%** |
| bull_put | 0.40–0.50 | 381 | 61.7% | 1.21 | **+7.2%** |
| iron_condor | 0.20–0.30 | 719 | 55.4% | 1.22 | −0.1% |
| iron_condor | 0.30–0.40 | 1,703 | 49.0% | 0.93 | **+3.9%** |
| iron_condor | 0.40–0.50 | 1,519 | 45.9% | 0.85 | **+4.0%** |

Delta 0.25 — the original spec — is the worst cell in the table.

## 5. Proposed strategy

Mechanical, no discretion, no directional forecast.

```
UNIVERSE      S&P 500 + 400, liquid options only
STRUCTURE     Iron condor (no direction call) — sell both sides
SHORT DELTA   0.35 ± 0.05 both wings          (NOT 0.25)
WIDTH         5 points, or nearest listed
ENTRY DTE     10 ± 2
R:R FLOOR     credit / max-loss >= 0.20
SPREAD FILTER relative bid/ask < 20%
EVENTS        block 14 days before AND after earnings and ex-div
SIZING        2.0% of equity per position, hard cap 10 contracts
CONCURRENCY   max 10 open, max 1 per sector, max 3 new per day
EXIT          whichever comes first:
                - debit <= 20% of credit (80% profit target)
                - 3 DTE reached  -> close at market, no exceptions
                - NEVER hold to expiry
GUARD         reject if short call strike <= short put strike
```

### Why each choice, with the evidence

| choice | reason |
|---|---|
| iron condor | needs no direction call; the nine mechanisms that tried all failed |
| delta 0.35 | L/W 0.93 vs 3.10 at delta 0.25; the decisive variable |
| 10 DTE | the only tenor profitable in both years in the 36-cell grid |
| exit at 3 DTE | +$88,563 / +$62,769 vs holding; largest measured effect |
| never hold to expiry | 85% expiry rate produced a 15.7% win rate in 2022 |
| 2% sizing | 5% produced >100% drawdowns; sizing does not change expectancy (mean RoR was identical at 7.5/5/3.5/2.5/2/1.5%), only survival |
| 1 per sector | every relaxation tested was worse; sector clusters are one correlated bet |
| 14 days either side | your own spec; costs a little edge but removes event risk |

### Expected performance — stated conservatively

On Q2 2023 the comparable config made +$48,550 on $50k. **Do not expect that.**
That quarter was favourable and the figure came at 5% sizing with 2 per sector,
where a handful of 16-contract positions dominated. At 2% sizing with 1 per
sector, scale it down by roughly 2.5–3x and expect high variance.

Realistic planning assumption: **mean return-on-risk of +3 to +4% per trade**,
which is what the delta-0.30–0.50 condor bands produced across 3,200+ pooled
trades. Win rate near 50%. Drawdowns of 20–30% should be considered normal.

## 6. Screener implementation — minimal human involvement

Daily, after the close:

```
1  refresh chains for the universe
2  drop anything with an event inside +/-14 days
3  for each symbol, find the 10 +/- 2 DTE expiry
4  select short strikes nearest 0.35 delta both sides
5  reject: call_short <= put_short | spread > 20% | R:R < 0.20
6  rank by credit / max-loss, descending
7  apply caps: 1 per sector, 10 open, 3 new per day
8  size at 2% of equity, cap 10 contracts
9  output the order list
```

Position management needs **no** judgement:

```
every open position, every day:
  if debit <= 20% of credit      -> close (profit target)
  elif dte <= 3                  -> close (mandatory)
  else                           -> hold
```

That is the entire operating procedure. The only human decision is whether to
run the book at all.

### What to monitor, and what to ignore

**Monitor:** realised loss/win ratio (alarm above 1.5), share of positions
closed by the DTE rule versus the profit target, and any position that reaches
expiry — that should never happen and indicates a broken exit.

**Ignore:** ADX, RSI, DMI, stochastics, A/D breadth, NH-NL, the golden cross,
the 200-day SMA, and the Keltner squeeze. All were tested, none helped.

## 7. What would change my mind

This rests on two years, one of which is incomplete (2023 = March + Q2 + Q4;
no Jan/Feb, no Q3). Two specific reservations:

1. **Quote density near expiry.** A 4-leg condor needs all four legs quoted to
   close. In this EOD data only ~45% are fully quotable at 2 DTE (82% per leg,
   ^4). Real intraday NBBO would be far better, but a 3-DTE exit is chosen over
   2-DTE partly for this reason. If live fills prove worse than modelled, the
   2-leg vertical at delta 0.40–0.50 is the fallback (L/W 1.21, RoR +7.2%).

2. **Exit-reason selection.** Filtering pooled trades on exit reason is partly
   circular — a trade only reaches an EOD exit if it survived. The +31%/+37%
   figures from that split are inflated; the unconditional figure for the whole
   delta band is **+4.0%**, which is what section 5 plans against.

Before live capital: paper-trade one quarter and verify the realised loss/win
ratio lands near 0.9. If it comes in above 1.5, the edge is not present in
execution and the strategy should not be funded.
