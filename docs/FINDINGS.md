# Vetta Options — Complete Findings & Backtest Record

**Date:** 2026-09-19
**Scope:** Every analysis, test, and result produced in this engagement.
**Data:** 6.33M option-day records · 138 real-money trades · 4 repos · 4 archives
**Configurations tested:** ~300 across 9 phases

---

## PART I — WHAT WAS INHERITED

### 1.1 The four repositories

| Repo | Commits | Stack | Verdict |
|---|---|---|---|
| `Vetta-Options-Prop` | 12 | Python | Ancestor. Holds the 2,090-line friction-aware backtester |
| `Vetta-Prop-Screener` | 3 main / **1,363** on `manus/paper-automation` | Python+JS | **The live system** (v2.2.0, 52 endpoints) |
| `VettaPropDesk2026` | 18 | TypeScript | Abandoned rewrite |
| `AlphaGrowthPropDesk` | 39 | TypeScript | **97% duplicate**; holds 33 spec documents |

**Critical:** the live system lives on a hidden branch 1,360 commits ahead of its
own `main` (+17,543 lines). Cloning the default branch gets the wrong code.

### 1.2 Architectural defects found

| Defect | Evidence |
|---|---|
| **Two parallel execution paths** | `/api/paper/automation/*` → internal simulator; `/api/paper/broker/*` → real Alpaca. They share no state. |
| **The "automated" path was fake** | `automation.py` docstring: *"It contains no broker order submission code."* Hardcodes `broker_mode: "SIMULATOR"`, fills at the proposal's own asking price — zero slippage, always. |
| **No scheduler anywhere** | Zero hits for apscheduler / BackgroundScheduler / asyncio task / cron. Every "automated" cycle required a manual HTTP POST. |
| **IBKR cannot work as deployed** | 5 endpoints require backend co-located with TWS; backend runs on a GCP VM. |
| **Docs contradict code** | Screener uses 30/180 SMAs; documentation describes 20/50. |

**Why defects survived months:** the simulator always filled at the asking price,
so the automated path never revealed execution problems that the real path had.

### 1.3 Quality worth keeping

SHA-256 idempotency keys · `SENT_UNKNOWN` never blind-retried · hard-locked
paper-only Alpaca endpoint · 9-second modification pacing · atomic writes with
directory fsync · `fcntl` advisory locks · market calendar fails closed.

### 1.4 Security — still outstanding

1. **Live Polygon API key hardcoded** as a `getenv` default in
   `screener_engine/polygon_chain.py:42`
2. **`.env` committed to git history**, `Vetta-Prop-Screener` commit `f4ffef8`

Both were flagged in the project's own consolidation doc and never remediated.

---

## PART II — THE $28,529 REAL-MONEY LOSS

Source: `SpreadEngine_Tracker.xlsm`, 138 closed trades.

| Metric | Value |
|---|---|
| Trades | 138 (90W / 48L) |
| Win rate | **65.2%** |
| **Net P&L** | **−$28,528.93** |
| Avg win / avg loss | +$505.26 / **−$1,541.71** |
| Expectancy | **−$206.73** |
| Profit factor | 0.61 |
| Worst trade | −$7,376 |

### 2.1 The tracker's headline number is misleading

`TOTAL = 113,956.74` is **`SUM(Ext)` = total credit collected**, not profit.
The companion `590,393.26` is `SUM(Max Loss)` = total risk taken.
Verified actual P&L: **−$28,528.93**.

### 2.2 Cause 1 — sector concentration (84% of loss)

| Group | Trades | Total | Avg |
|---|---|---|---|
| **Semis / AI hardware** | 83 | **−$23,847** | −$287 |
| Everything else | 55 | −$4,682 | −$85 |

**17 of the 20 worst losses were semiconductors.** One position in eleven tickers.

### 2.3 Cause 2 — position sizing

Median max loss **7.5%** of a $50k account; largest **25.3%**; **52% of trades
exceeded 5%**.

### 2.4 Cause 3 — directional skew

111 short puts vs 27 short calls — a leveraged long, not a neutral book.

### 2.5 No black swans

| Sym | Short | Stock | OTM | Days | P&L |
|---|---|---|---|---|---|
| ON | 105.0 | 122.5 | −14.3% | 12 | −$7,376 |
| LRCX | 330.0 | 403.0 | −18.1% | 9 | −$5,806 |
| AMD | 465.0 | 558.0 | −16.7% | 17 | −$5,141 |
| CAT | 905.0 | 1009.0 | −10.3% | 9 | −$4,668 |

Shorts sat 10–18% OTM and were breached by ordinary 2–3 week drawdowns. All
survivable at correct size.

### 2.6 Process

22 trades carry manual comments: `"Col R formula error!"`, `"system screw up"`,
`"manual override"`, `"nudged wrong dir?"` — discretionary intervention on a
spreadsheet with known formula errors.

---

## PART III — THE STRATEGY WAS ALREADY KNOWN TO LOSE

`results/backtest_2023_full/` existed six months before the losses:

| Metric | Value |
|---|---|
| Trades | 195 |
| Win rate | **64.1%** |
| **Net P&L** | **−$4,904.53** |
| P&L before friction | **+$3,729.58** |
| Total friction | **−$8,634** |
| Expectancy | −$25.15 |
| Sharpe | −3.05 |

**Five independent datasets, ~500 trades, all negative:**

| Dataset | n | Win | Expectancy |
|---|---|---|---|
| Backtest 2023 full | 195 | 64.1% | −$25.15 |
| Backtest Q2 loose | 119 | 71.4% | −$2.88 |
| Backtest March tuned | 38 | 44.7% | −$48.95 |
| Live Alpaca paper | 9 | 0% | −$210.67 |
| **Live real money** | **138** | **65.2%** | **−$206.73** |

**Invariant:** avg loss ÷ avg win ≈ **3.05** (real money) and **3.04** (backtest).
At 3:1 you need >75% win rate to break even. You got 65%.

---

## PART IV — DATA ASSETS

| Asset | Rows | Coverage |
|---|---|---|
| ThetaData Q4 2023 | 2,768,979 | Oct–Dec, 360 symbols |
| ThetaData Q2 2023 | 2,599,309 | Apr–Jun, 357 symbols |
| ThetaData Mar 2023 | 963,340 | March, 356 symbols |
| `ib_screener_cache` price_bars | 275,961 | **753 continuous days 2022–2024** |
| `ib_screener_cache` events | 31,729 | 4,600 EARNINGS + 27,129 EX_DIV |
| VIX series | 753 days | Real VIX, 2022–2024 |

Full fields: bid, ask, bid_size, ask_size, volume, all greeks, IV, underlying.

---

## PART V — EVERYTHING THAT FAILED

Negative results are recorded because they eliminate expensive options.

### 5.1 Exit-rule optimization — flat and futile

Stop × target grid, all combinations **−$20.79 to −$25.15**:

| Stop | PT 0.25 | PT 0.35 | PT 0.50 |
|---|---|---|---|
| 1.25× | −$21.88 | −$22.39 | −$23.24 |
| 1.50× | −$21.94 | −$22.61 | −$24.10 |
| 2.00× | −$23.33 | −$24.47 | −$24.12 |
| 3.00× | −$20.79 | −$22.85 | −$21.55 |

**Tightening stops raises the loss/win ratio** (1.25× → 2.04; 3.0× → 4.02) by
converting would-be winners into losers. The hypothesis "cut avg loss and 65%
wins turns positive" is **false**.

### 5.2 Contract scaling — mathematically cannot work

| Contracts | Exp/trade | **Exp/contract** | Friction |
|---|---|---|---|
| 1 | −$10.57 | **−$10.57** | $12.61 |
| 3 | −$31.70 | **−$10.57** | $37.84 |
| 10 | −$105.66 | **−$10.57** | $126.14 |

Bid/ask is a **per-share** cost. Friction stays at **43% of credit** at every
size. (This corrects an earlier incorrect claim that scaling would dilute friction.)

### 5.3 Other failures

| Test | Result |
|---|---|
| DTE optimization | 7d −$17.27 · 15d −$24.00 · 30d −$32.79 · 45d −$38.09 |
| ATR breach exit (ported from `legacy_strategy.py`) | −$12.06 — worse than no stop |
| Weekend theta (Fri→Mon) | Negative in **17 of 18** configs |
| Mid-fills on single names | −$10.57 → −$2.51 even at 100% mid |
| Credit/width ≥ 20% gate | Only **1 qualifying trade in 148 days** |
| Iron condors | Negative at 0.20 / 0.30 / 0.50 delta |
| 0.50δ ATM condor | **−$40,713, 136% DD**; one trade (BIIB) lost **$30,004 = 60% of account** |
| `below50` trend (buy dips) | Loses head-to-head to `s10_50` in **25 of 36** matched settings |

### 5.4 Variance risk premium — real signal, not tradeable alone

| IV/RV quintile | Mean VRP | Hit rate |
|---|---|---|
| R1 (cheap, 0.58) | **−20.6%** | 0.0% |
| R3 (1.00) | −2.2% | 49.9% |
| **R5 (rich, 1.60)** | **+7.5%** | **87.8%** |

Monotonic across 41,452 observations, stable every quarter. **But:**

```
Edge at IV/RV ≥ 1.3  : +7.5 vol pts ≈ $12.50 per spread
Single-name friction : $11–13 per spread
Net                  : ≈ $0
```

**Note:** unconditional VRP in this sample is **negative** (mean −4.1%, only
44.8% positive). "Options are always overpriced" is false here.

**Later finding:** once trend + earnings filters are applied, the IV/RV gate
becomes redundant and in some configurations *reduces* performance.

### 5.5 Liquidity — the structural fact

| Product | Median relative bid/ask |
|---|---|
| **SPY** | **1.87%** |
| QQQ | 2.53% |
| IWM | 3.64% |
| **Single names** | **12.77%** |

Index options are **6.8× tighter**. Index spreads produced +$9.96/trade while
crossing — but that sample (n=27) had **zero max-loss events** and required a
90% win rate to break even, so it was not accepted.

---

## PART VI — WHAT WORKED

### 6.1 Progression of expectancy

| Phase | Config | Expectancy | Note |
|---|---|---|---|
| 0 | Original as traded | **−$206.73** | Real money |
| 1 | + liquidity filters | −$15.68 | Friction $37 → $12.61 |
| 2 | + min-hold, stop-on-mid, credit≥2×friction | −$10.57 | Fixed day-1 stop-out bug |
| 3 | Neil's spec (10 DTE, 5%, 2/sector, 80% TP) | **+$118.53** | First positive |
| 4 | + trend filter (SMA10>50) | +$134.36 | PF 1.53 |
| 5 | + 14-day earnings blackout | **+$166.09** | PF 1.88, P(exp≤0)=0.08% |
| 6 | + R:R ≥ 0.20, 1/sector, TP80-only | **+$493.59** | PF 3.57, P(exp≤0)=0.00% |

### 6.2 The day-1 stop-out bug (reproduced from live losses)

With $0.33 credit and ~$0.20 round-trip friction, **35 of 75 stops fired on day 1**
— the close quote instantly read 2–3× credit purely from crossing the spread.

```
ZS    in 10-02  out 10-03  credit 0.30  debit 1.00 = 3.33x  −$73
CRWD  in 10-02  out 10-03  credit 0.31  debit 0.90 = 2.90x  −$62
PEP   in 10-03  out 10-05  credit 0.24  debit 1.16 = 4.83x  −$95
```

Three fixes (min-hold 2 days, evaluate stop on mid, require credit ≥ 2× friction)
improved expectancy 56% and cut friction 34%.

### 6.3 Earnings blackout — highest-value single filter

Of the 12 worst losses the trend filter could not prevent, **8 had earnings inside
the window**, including the two largest (TMO −$7,546 with earnings 9 days out;
ILMN −$4,634 with earnings 2 days out).

| Blackout | n | Win | Expectancy | PF |
|---|---|---|---|---|
| None | 235 | 76.6% | +$134.36 | 1.53 |
| 10 days | 220 | 80.5% | +$165.24 | **1.88** |
| 14 days | 212 | 80.2% | **+$166.09** | **1.88** |

Ex-dividend blackout makes it worse. **Earnings only.**

### 6.4 Trend filter — SMA10 > SMA50 wins

Averaged over all 36 matched settings in the final grid:

| Mode | Mean exp | Mean PF | Mean DD |
|---|---|---|---|
| **s10_50** (px>50 & SMA10>50) | **+$277** | **2.2** | **14.4%** |
| s10_30 (px>50 & SMA10>30) | +$235 | 1.8 | 16.8% |
| none | +$221 | 1.8 | 23.0% |
| below50 (buy dips) | +$209 | 1.8 | 21.0% |

Answering the diagnostic question directly: losing trades were **only 6 points
more likely** to be below trend (46.5% of losers vs 52.5% of winners were above).
**46.5% of losers were in confirmed uptrends** — those were earnings gaps, which
is why the blackout matters more than the trend filter.

### 6.5 Exit rule — profit target alone beats adding a time exit

| Exit | Mean exp | Mean PF |
|---|---|---|
| **TP80 only** | **+$272** | **2.0** |
| Thursday only | +$228 | 1.9 |
| Both | +$207 | 1.8 |

In the winning config: TP80 alone **+$493.59** vs adding Thursday **+$322.58**.
The time exit **cuts winners short** — 39 of 92 trades ran to worthless expiry.

### 6.6 Risk/reward gate — helps, but interacts

| R:R gate | n | Expectancy | PF | DD |
|---|---|---|---|---|
| None | 212 | +$166.09 | 1.88 | 17% |
| ≥ 0.20 | 150 | +$201.91 | 1.91 | **8%** |
| ≥ 0.25 | 121 | +$216.90 | 1.91 | **8%** |
| ≥ 0.35 | 39 | +$276.47 | 2.04 | 7% |

Expectancy rises monotonically, drawdown halves. **But it is not universally
additive** — at 10%/1-sector it *hurt* (+$394 with vs +$357 without). At
7.5%/1-sector it helps strongly (+$494 vs +$322).

### 6.7 VIX — low VIX better, but confounded

| VIX gate | n | Expectancy | PF | Quarters kept |
|---|---|---|---|---|
| ≤ 14 | 102 | +$260.25 | **3.32** | ⚠️ **2 of 3** |
| ≤ 16 | 125 | +$219.07 | 2.35 | ⚠️ 2 of 3 |
| **≤ 20** | 207 | +$167.82 | 1.88 | ✅ **3 of 3** |

**VIX ≤ 14 takes zero trades in March 2023** (SVB crisis, VIX 18.5–26.5). The
filter flatters itself by sitting out the only stressed quarter. Cannot
distinguish "low VIX is better" from "March was bad" on this sample.

---

## PART VII — THE FINAL GRID (144 CONFIGURATIONS)

Dimensions: 4 trend modes × 2 R:R gates × 3 position sizes × 2 sector limits ×
3 exit rules. Fixed: bull put, delta 0.25 ±0.05, 14-day blackout, 7–11 DTE,
spread ≤ 10%.

### 7.1 Marginal effect of each dimension

| Dimension | Best setting | Effect |
|---|---|---|
| Trend | **s10_50** | +$277 mean exp vs +$209 for worst |
| R:R gate | **≥ 0.20** | +$281 vs +$190 |
| Position size | *risk dial* | 5%: +$156/13% DD/46% peak · 10%: +$310/24% DD/**90% peak** |
| Sector limit | **1/sector** | peak risk 56% vs 80% |
| Exit | **TP80 only** | +$272 vs +$207 for both |

### 7.2 Tradeability constraint

Requiring peak concurrent risk ≤ 60%, all quarters positive, P(exp≤0) ≤ 1%:
**only 34 of 144 configurations qualify.** Many top-expectancy results demand
**71–116% of account in simultaneous margin** — not executable on $50k.

### 7.3 Final recommended configuration

**Bull put · delta 0.25 ±0.05 · SMA10>SMA50 trend filter · R:R ≥ 0.20 ·
14-day earnings blackout · 7–11 DTE · spread ≤ 10% · 1 per sector ·
exit at 80% profit target only**

| Size | n | Win | Expectancy | Net | PF | Max DD | Peak risk | 95% CI | P(≤0) |
|---|---|---|---|---|---|---|---|---|---|
| **5.0%** | 92 | 88.0% | **+$326** | +$29,997 | 3.36 | **8.2%** | **37%** | +$191..+$441 | 0.00% |
| **7.5%** | 92 | 88.0% | **+$494** | +$45,411 | **3.57** | 12.3% | 53% | +$299..+$661 | 0.00% |
| 10.0% | 92 | 88.0% | +$639 | +$58,800 | 3.61 | 16.4% | 71% | +$385..+$856 | 0.00% |

Per-quarter (7.5%): Mar +$1,775 (n=3) · Q2 +$23,476 (n=45) · Q4 +$20,160 (n=44).

### 7.4 Stress tests on the final config

| Test | Result |
|---|---|
| **Mid-fill 0.95 → 0.00** | **+$494 → +$253 — stays positive at every rate** ✅ |
| Seed stability (5 seeds) | +$476 to +$516 — stable |
| Commission $1.00/leg | +$477 — survives |
| Concentration | top 5 = 13%, top 10 = 25% of profit |
| Exit mix | 43 take-profit · 39 expired worthless · 10 force-close |

**The fill-rate robustness is the key improvement.** An earlier 10%/wide-delta
variant collapsed from +$394 to −$70 between 95% and 0% mid-fills. This one does
not — it is the first configuration that does not depend on favourable execution.

---

## PART VIII — ANSWERS TO SPECIFIC QUESTIONS

**Q: Is delta the short leg or an average?**
Short leg only. `pick_short()` matches |delta| on the short strike; the long leg
is chosen by strike distance with no delta constraint (typically 0.12–0.15).
For condors, each short leg is independently matched — not averaged.

**Q: How far OTM?**
Short strike median **1.97%** below spot (p10 1.15%, p90 3.29%). Long strike
median 5.24% below spot. Long sits $5 below the short in 68% of cases; otherwise
nearest available.

**Q: Open or close price? Is 10 DTE calendar or trading days?**
**EOD close quotes** — no intraday data. **Calendar days**, not trading days.
Actual entries span 7–12 calendar DTE and occur on **every weekday**
(Mon 103 / Tue 97 / Wed 87 / Thu 121 / Fri 89), not a fixed Tuesday cadence.

**Q: Should risk/reward be 0.25 or better?**
0.20–0.25 is the sweet spot. Current median R:R is 0.212; only 36% of trades
naturally exceed 0.25. Above 0.35 the sample thins to 39 trades and significance
degrades (P(exp≤0) = 3.7%).

**Q: Were the losing trades below their 50 SMA?**
**No — only marginally.** 46.5% of losers vs 52.5% of winners were above trend,
a 6-point difference. Nearly half of all losers were in confirmed uptrends
(META, NKE, LULU, NFLX, MRNA) — those were **earnings gaps**, not trend failures.

---

## PART IX — LIMITATIONS

1. **Mid-fill assumption.** Final config is robust across all fill rates, but
   this has never been measured live. **Measure it before funding.**
2. **Three quarters, all 2023, all rising** (SPY +7.9% Q2, +11.2% Q4). A short-put
   book is structurally short-delta. Returns of 60–118% annualised are **not a
   forecast** — they are what this strategy earns in a melt-up.
3. **March contributes only 3 trades** to the final config, so "positive in all
   quarters" is effectively carried by Q2 and Q4.
4. **EOD data only** — no intraday fills, gaps, or stop triggers.
5. **A sizing bug was found and fixed mid-engagement** (see METHODOLOGY §4.2).
   All condor results before the fix were inflated; the 0.40δ condor is
   +$35,899, not +$47,839.
6. **Bootstrap CIs assume independent trades.** Positions overlap in time and
   share market exposure, so true intervals are wider than reported.

---

## PART X — RECOMMENDED NEXT STEPS

| Priority | Action |
|---|---|
| **1** | **Rotate credentials** — Polygon key in source, `.env` in git history |
| **2** | **Measure real mid-fill rate** — place 20–30 limit orders at mid on Alpaca paper, record fill rate without adjustment. Highest-value test remaining. |
| **3** | **Acquire 2021–2022 data** and re-run this harness through a bear market |
| **4** | **Build consolidated repo** — Alpaca paper only, single execution path, real scheduler, IBKR removed, final config as the entry/exit engine, existing OMS safety layer retained |
| **5** | **Merge `manus/paper-automation` → `main`**, archive the two TypeScript repos |

---

## APPENDIX — FILE INDEX

```
vetta_research/
├── FINDINGS.md                          This document
├── REPORT.md                            Earlier narrative report (phases 1–5)
├── METHODOLOGY.md                       Assumptions, limitations, reproduction
├── code/                                All backtest + analysis code
│   ├── spec_engine.py                   Final strategy engine
│   ├── engine.py                        General credit-spread backtester
│   ├── grid.py                          144-configuration grid
│   ├── winner.py                        Final config validation + stress
│   └── README.txt                       Script index
├── data/                                signals / trend / events / VIX / sectors
└── results/
    ├── FINAL_SUMMARY.csv                Final config, 3 position sizes
    ├── FINAL_v2_*_trades.csv            Trade-by-trade detail (276 rows)
    ├── grid_results.csv                 All 144 configurations
    ├── SUMMARY.csv                      Earlier phase configs
    ├── config_*_trades.csv              Earlier phase trades
    └── results_*.json                   Raw sweep output
```
