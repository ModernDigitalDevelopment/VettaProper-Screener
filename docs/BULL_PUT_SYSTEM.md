# Bull Put Credit Spread System — Research Summary & Operating Outline

**Prepared for partner review.** Every number below is measured on our own
backtest, not sourced from literature. Where something failed, it says so.

---

## 1. What was tested

Seven quarters of ThetaData option chains (2022 Q1–Q4, 2023 Mar/Q2/Q4 — the
only quarters we hold), ~26 million option-days, 494-symbol large-cap
universe. **2,866 unique bull-put trades** across all configurations;
**912 trades** in the clean six-quarter baseline used for the statistics here.

Statistical standards applied throughout:

- Day-blocked bootstraps (positions opened the same day share one market shock)
- Multiple-comparison correction whenever more than one variant was scanned
- Matched-fraction random nulls (a rule skipping X% must beat skipping X% at random)
- Within-quarter stratification to remove calendar composition
- Leave-one-quarter-out stability checks

---

## 2. Headline: thirteen timing mechanisms were tested. All thirteen failed.

| # | Mechanism | Result |
|---|---|---|
| 1 | ADX / DMI trend strength | No edge (and the indicator was fabricated — see §5) |
| 2 | Advance-decline breadth (9 measures) | Best rule died under multiple-comparison correction |
| 3 | Per-symbol SMA side-switch | Capacity failure; edge p=0.087 |
| 4 | Contrarian 5/20 SMA mean reversion | Worked on calls, not puts |
| 5 | Macro regime overlay (NH-NL, VIX, credit spreads) | Labels accurate, forward returns wrong-signed |
| 6 | A/D reaction-low breach protocol | Actively hurt |
| 7 | Golden cross (50/200) | Failed |
| 8 | Asymmetric per-side spec | +$64,854 in 2022 → −$32,074 in 2023 frozen |
| 9 | Keltner squeeze | Failed |
| 10 | Micro-VVIX + short-term A/D divergence | Fires ≤3× in all of 2022; no skill vs random |
| 11 | VVIX level gate (regime) | Calendar confound (§4) |
| 12 | 200-day MA position sizing | Calendar confound; sign reverses within quarter |
| 13 | Endogenous pause-after-N-losses | Pure exposure reduction, zero timing alpha |

**There is no entry or re-entry timing signal in this data.** That is the
central finding, and it is worth more than a fragile one would be.

---

## 3. What actually works: tail control

One lever survived every check — a **stop at 0.5× the credit collected**
(close when the debit to close reaches 1.5× the credit).

Matched trades, same symbol/date/strike, so this is the stop's effect on a
position rather than a different set of positions:

| stop level | CVaR5 (long) | losses > 1× credit (long) | CVaR5 (short) | losses > 1× credit (short) |
|---|---|---|---|---|
| none | −100.1% | 14.3% | −99.4% | 15.4% |
| **0.5× (recommended)** | **−54.9%** | **1.7%** | **−71.0%** | **5.1%** |
| 1.0× | −81.6% | 8.2% | −82.7% | 12.4% |
| 1.5× | −89.1% | 14.8% | −87.7% | 17.0% |
| 2.0× | −98.4% | 15.0% | −92.4% | 17.0% |

**Monotone in both tenors with no exceptions** — the cleanest dose-response
relationship found anywhere in the programme. Catastrophic losses fall from
roughly 1-in-7 trades to 1-in-20 (short) or 1-in-60 (long).

It also drives the **loss/win ratio below 1.0** (0.91 on the long tenor vs
1.36 unstopped) — the variable a 180-configuration meta-analysis identified as
the single most decisive input to profitability.

### What the stop does NOT do

- **It does not improve average return.** Paired bootstrap: no stop level is
  significant at Bonferroni p<0.0125. Mean RoR is statistically unchanged.
- **It does not reduce portfolio drawdown as much as hoped.** Freed capital
  gets redeployed into the same selloff; 40–48% of those replacement trades
  were themselves stopped out.
- **It costs money in dollar terms.** Long tenor: +$3,143 with the stop vs
  +$7,080 without, over six quarters.

**Honest framing for your partner: this is insurance, not alpha.** You pay
~$3,900 of upside over six quarters to cut worst-case single-trade loss from
−100% of risk to −55%. That trade is worth making if — and only if — the
reduced tail lets you size larger or sleep better. It is not a profit engine.

---

## 4. The trap that caught us three times (worth your partner knowing)

Three separate rules looked excellent and all three were the **same
statistical artifact**:

| rule | pooled result | what it actually was |
|---|---|---|
| VVIX > 90 gate | short tenor −$43.5k → −$6.4k | Blocks 100% of Q1'22 and 65% of Q2'22 |
| 200dma sizing | +8.42pp, **p=0.034** | "Above 200dma" ≈ "2023"; 2023 was profitable |
| Pause after 3 losses | net/dd −0.49 → −0.26 | Skips 91% of trades; timing alpha +$361 on −$3,451 |

In every case the rule was correlated with the *calendar*, not with trade
quality. Within-quarter, all three collapse — and the 200dma one **reverses
sign**.

**Operational conclusion: with six quarters and one bear market, any regime
filter will look brilliant by deleting H1 2022.** This dataset cannot validate
regime filters. We should not deploy one on the strength of it.

---

## 5. Data integrity issues found and fixed

Stated because they affect how much weight the numbers deserve:

1. **ADX/DMI/stochastics/ATR were fabricated.** The data source repeats one
   price per symbol-day, so high=low=close on **all 21,876 symbol-days**.
   Wilder smoothing being linear made `+DI` *algebraically identical* to
   RSI(14). Rebuilt from Polygon OHLC. The bug had been *flattering* the
   strategy: corrected ADX≥35 went from 66.7% win (n=18) to 59.6% (n=47).
2. **Zero put/call overlap.** Put and call runs used mutually exclusive trend
   gates, so every side-switching comparison was meaningless. Rebuilt.
3. **Missed-exit bug.** When any leg lacked a quote, the exit check was skipped
   entirely — all 44 EXPIRED trades in one tuned run had ignored their DTE
   cutoff.
4. **Inverted condors at delta 0.50** — 124 of 125 sampled pairs were actually
   short straddles, mis-sizing risk.
5. **Commission double-count** on 2-leg structures.

### A claim I previously made and am now retracting

I earlier reported that *"expiry carries −29% to −40% RoR vs +10% for a
time-based exit — exit discipline is the single largest edge in the data."*

**That was backwards, and the whole comparison was invalid.** On the clean
population, EXPIRED trades show **+23.6%** and time-exited trades **−22.1%**.
Neither number means anything, because:

| exit route | mean debit to close | credit received | ratio |
|---|---|---|---|
| time-exited | 2.076 | 1.274 | **1.63** (deep losers) |
| expired | 0.488 | 1.273 | **0.38** (already winners) |

A position only reaches expiry when a leg has **no quote** — and a short put
with no bid is one nobody will pay for, i.e. already deep OTM and worthless.
So "EXPIRED" is a proxy for "finished profitably." Conditioning on it selects
winners by construction.

The legitimate test is a counterfactual — same entries, different exit rule:

| comparison | matched | difference | p |
|---|---|---|---|
| exit 10 DTE vs 12 DTE | 114 | +0.36pp | 0.582 |
| exit 10 DTE vs 15 DTE | 95 | −0.52pp | 0.773 |
| exit 12 DTE vs 15 DTE | 98 | −0.61pp | 0.739 |
| profit target 70/80/90% | 108–115 | 0.00pp | 1.000 |

**Exit timing within the 10–15 DTE window does not matter, and the profit
target does not matter.** Choose them for operational convenience.

---

## 6. The system, as I would actually run it

### Universe & entry
- Large-cap, liquid optionable names (our test universe was 494 names)
- **Short-leg delta 0.30 ± 0.05**
- **35–45 DTE at entry** (the long tenor; it was the only one profitable before costs — +$7,080 vs −$43,548 for 7–11 DTE)
- Bid/ask spread **< 10%** of mid on both legs
- Risk/reward **≥ 0.20** (credit ≥ 20% of width)
- **Earnings blackout: 14 days before AND after**
- No directional filter — all thirteen tested gates failed, so trade continuously

### Sizing
- **5% of account risk per position**, max loss basis
- **Max 2 positions per sector**, max 12 open
- Max 4 new positions per day
- *Rationale: an earlier ablation proved sizing does not change expectancy, only the return/risk ratio. These numbers control concentration, nothing more.*

### Exit ladder (checked daily, in this order)
1. **Profit target: close at 80% of max profit** (debit ≤ 20% of credit) — the level is arbitrary; 70/80/90% are statistically identical
2. **Stop: close if debit ≥ 1.5× credit** (loss = 0.5× credit) — **the one measured edge**
3. **Time: close at 15 DTE** regardless — 10/12/15 are statistically identical
4. Never hold to expiry; never let assignment happen

### What NOT to do
- Do not add a VVIX, A/D, SMA, ADX or breadth gate. Thirteen failed.
- Do not use the 1× credit stop (worse than no stop on both tenors).
- Do not trade 7–11 DTE. Pooled −$43,548 vs +$7,080 at 35–45 DTE.
- Do not pause after losing streaks. Zero timing alpha.

---

## 7. Expected performance, stated honestly

Six quarters, long tenor, 0.5× stop, average $2,251 risk per position:

| metric | with 0.5× stop | no stop |
|---|---|---|
| trades | 322 | 238 |
| win rate | 48.4% | 59.7% |
| net | +$3,143 | +$7,080 |
| max drawdown | $29,005 | $32,107 |
| net / drawdown | 0.11 | 0.22 |
| **loss/win ratio** | **0.91** | 1.36 |
| worst single trade | −100.9% of risk | −102.1% of risk |
| **2022 (bear)** | **−$24,585** | −$21,731 |
| **2023 (bull)** | **+$27,728** | +$28,811 |

**Read that bottom block carefully. The system's entire profit comes from
2023 and it loses money in 2022.** It is a long-biased strategy with no
demonstrated ability to detect which regime it is in.

Worst-case single trade still exceeds 100% of nominal risk — gap risk through
the short strike is real and the stop cannot prevent it.

---

## 8. Honest assessment for the partner conversation

**What we have:** a well-instrumented, bug-audited backtest showing bull puts
at 35–45 DTE with disciplined exits are roughly break-even-to-modestly-positive
across one bear and one bull year, with one genuine risk-control lever.

**What we do not have:**
1. **Any timing edge.** Thirteen mechanisms, thirteen failures.
2. **Enough bear data.** One drawdown (2022). Every regime filter is
   indistinguishable from "don't trade H1 2022."
3. **Out-of-sample validation.** All parameters chosen on the same seven quarters.
4. **Transaction cost realism beyond commissions.** Fills assumed at mid.
5. **Proof of positive expectancy.** Six-quarter net of +$3,143 on ~$2,251
   average risk is inside the noise band.

**My recommendation:** paper-trade or trade at minimum size for two quarters
before committing capital. The structure is sound and the risk controls are
real, but the measured edge is too small to distinguish from zero on this
sample.

**The single highest-value next step is more bear-market option data** —
2018 Q4, 2020 H1, or any second independent drawdown. That one input would
convert the biggest open question (does regime filtering work?) from
untestable to testable. No amount of additional analysis on the current seven
quarters can substitute for it.

---

## Appendix: supporting documents in this repo

| file | contents |
|---|---|
| `backtest/2022/STOP_LOSS.md` | Full stop-loss study, six quarters, all tail statistics |
| `backtest/2022/MICRO_VVIX_AD.md` | Micro-VVIX + A/D replication and rejection |
| `backtest/2022/INVERSION_TEST.md` | The inverted-signal hypothesis and the skew artifact |
| `backtest/2022/VVIX_LEVEL_GATE.md` | VVIX level gate and the composition confound |
| `backtest/2022/TREND_STRESS_OVERLAY.md` | 200dma Layer-1 test, sign reversal |
| `backtest/2022/GRIND_QUARTERS.md` | Long-DTE failure and prior retraction |
| `docs/FINDINGS_2022.md` | 2022 tests with per-field data-integrity audit |
| `bt/mine_exit.py`, `bt/mine_reentry.py`, `bt/streak_valid.py`, `bt/streak_final.py`, `bt/verify_core.py`, `bt/exit_truth.py` | This session's mining and verification scripts |
