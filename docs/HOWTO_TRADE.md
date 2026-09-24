# How to trade this — the operating procedure

Exactly what the backtest did, step by step, so live trading matches tested
behaviour. Deviating from this means the numbers in `BACKTEST.md` no longer
describe what you are doing.

---

## The strategy in one paragraph

Every trading day, sell a put credit spread on a stock in an uptrend, about 9
days from expiry, with the short strike around 0.25–0.30 delta, collecting at
least $1 of credit for every $5 at risk. Never on a stock with earnings or a
dividend in the next 12 days. Never more than one position per sector open at
once. Risk 5% of the account per position. Close at 80% of max profit or at
expiry, whichever comes first.

---

## Daily routine

### 1. Before the open — check state

```
GET /api/health                  → is the data provider configured?
GET /api/ibkr/status             → if using IBKR, is the session alive?
GET /api/reconcile/alpaca        → what do I actually hold right now?
```

The reconcile call is not optional. The sector cap is **portfolio-wide**, not
per-day — see §"Diversification" below — so the screener must know your live
book before it can apply the cap correctly.

### 2. Run the screener

One scan per day. The backtest evaluated candidates once daily on end-of-day
data; scanning repeatedly and picking the best moment is a different strategy
with unknown results.

Feed your open sectors in so caps apply against the real book:

```json
POST /api/scan
{
  "preset": "validated_conservative",
  "open_sectors": { "TECH": 1, "HEALTH": 1 }
}
```

### 3. Take the ranked list in order

The screener returns candidates sorted by expected return on risk. **Take them
top-down until a cap binds.** Do not skip the top-ranked trade because you
dislike the ticker — that is discretion, and discretion is untested.

Caps that stop you:
- 1 per sector, counted across your whole open book
- 4 new positions per day
- 12 open positions total
- 5% of equity at risk per position

### 4. Place the order

- **One multi-leg order**, never two single-leg orders. Legging into a spread
  exposes you to the market between fills.
- **IBKR MidPrice (or equivalent limit at mid).** Fill quality is worth ~41% of
  the result — see §"Execution" — so this matters.
- If unfilled, let it rest or improve by $0.01–0.02. **Do not chase.** A missed
  trade costs far less than a bad fill (quantified below).

### 5. Manage exits

Two rules, both mechanical:

| Trigger | Action |
|---|---|
| Position reaches **80% of max profit** | Close it |
| **Expiry day** arrives | Close it |

**There is no stop loss, and that is deliberate.** The predecessor system used
credit-multiple stops and 35 of 75 stops fired on day one — round-trip friction
(~$0.20) against a typical credit (~$0.33) made the close quote read 2–3× the
credit the instant the position opened. The defined-risk structure *is* the
stop: max loss is capped at (width − credit) × 100 per contract.

If you add a stop, you are trading something that was not tested.

---

## Diversification — how the sector cap actually works

### It is portfolio-wide, not daily

The cap counts **every position currently open**, regardless of when it was
entered:

```python
for p in open_positions:        # the entire live book
    sector_count[p.sector] += 1
...
if sector_count[candidate.sector] >= max_per_sector:
    skip
```

With `max_per_sector = 1`, holding an open TECH spread blocks **all** other
TECH candidates until it closes — whether they appear today, tomorrow, or four
days from now.

Verified by replaying the backtest timeline and counting concurrent positions
per sector at every open and close event: **zero violations** within any
contiguous trading sequence.

**Operationally this means:** always pass your real open book into the scan via
`open_sectors`. If you skip that, the screener only sees today's entries and
will happily hand you a second TECH spread while you already hold one.

### Thin days are normal — and they are good days

The most common outcome is a single qualifying trade. Across 104 entry days in
the backtest:

| Positions available | Days | Win % | Expectancy | PF |
|---|---|---|---|---|
| **1 only** | **39** | **82.1%** | $446 | **3.82** |
| 2 | 21 | 76.2% | $6 | 1.01 |
| 3 | 17 | 76.5% | $455 | 4.32 |
| 4 | 27 | 76.9% | $238 | 1.59 |

**37% of entry days produced exactly one position, and those days had the
highest win rate of any bucket.**

This is the single most counter-intuitive result in the research, and the one
most likely to be second-guessed at 9:30am. When only one spread clears every
gate, that spread is one the filters genuinely liked — not a compromise made to
fill a slot.

**Rule: take the one trade. Do not relax criteria to find a second.**

### The account is supposed to sit mostly in cash

| Metric | Value |
|---|---|
| Max concurrent positions | 11 (of 12 allowed) |
| Median concurrent positions | 7 |
| **Median capital at risk** | **$16,192 — 32% of a $50k account** |
| Peak capital at risk | $26,255 (53%) |

**Median utilisation was 32%.** Two-thirds of the account is idle on a typical
day. That is not inefficiency — it is the reason max drawdown was 24.2% instead
of the 38.3% seen at 2 per sector, and far below the 44%+ seen when caps were
loosened further.

If you find yourself fully deployed, something has gone wrong with your caps.

### Choosing 1 vs 2 per sector

Both rows below use the same deterministic 100%-midpoint fill assumption, so
they are directly comparable:

| Setting | Trades | Win % | Net | PF | Max DD | Peak risk |
|---|---|---|---|---|---|---|
| **1 per sector** | 240 | **76.2%** | $53,334 | 1.62 | **24.2%** | 53% |
| 2 per sector | 303 | 75.2% | $84,168 | 1.69 | 38.3% | 58% |

Two per sector earns **58% more** ($84,168 vs $53,334) for **58% more
drawdown** (38.3% vs 24.2%). Profit factor barely moves (1.69 vs 1.62), which
tells you the extra return is compensation for extra risk rather than extra
edge.

The risk being taken is correlated risk, and that is precisely what destroyed
the predecessor system — 84% of its $28,529 loss came from a single sector with
no cap at all.

Default is 1. Choose 2 only if a ~38% drawdown is genuinely survivable for you,
both financially and psychologically.

---

## Position sizing

```
contracts = floor( (equity × 0.05) / max_loss_per_contract )
max_loss_per_contract = (width − credit) × 100
```

Worked example — $50,000 account, $5-wide spread, $1.21 credit:

```
max loss/contract = (5.00 − 1.21) × 100 = $379
budget            = 50,000 × 0.05      = $2,500
contracts         = floor(2500 / 379)  = 6
total risk        = 6 × 379            = $2,274
max profit        = 6 × 121            = $726
```

Cap at 20 contracts regardless of what the maths says.

---

## Compounding — the case for and against

### What it does

Position size is recomputed from **realised** equity on every entry. Equity
updates only when a trade closes; unrealised profit is not tradable capital.

These runs use the 95%-midpoint fill assumption (see the note at the end of
this section):

| Sizing | Final equity | Return | Max DD |
|---|---|---|---|
| Fixed $50k base, 5% | $116,526 | 133% | 19.8% |
| **Compounding 5%** | **$161,839** | **224%** | 13.0% |
| Compounding 7.5% | $205,400 | 311% | 19.0% |
| Compounding 10% | $221,277 | 343% | 23.2% |

Note drawdown *falls* as returns rise. That is not an error — drawdown is
measured against the running peak, and the peak grows with the account. A $10k
loss is 20% of $50k but 8% of $120k. Dollar losses got bigger; relative losses
got smaller.

### Why you should not switch it on yet

**1. The return is concentrated, and compounding concentrated it further.**

| Month | P&L | Equity after |
|---|---|---|
| Mar | +$7,427 | $57,427 |
| Apr | −$2,652 | $54,775 |
| May | +$180 | $54,955 |
| Jun | +$23,115 | $78,070 |
| Oct | +$1,810 | $79,880 |
| Nov | +$29,322 | $109,201 |
| **Dec** | **+$52,638** | **$161,839** |

94% of profit came from three months; December alone was 47%. December was both
the biggest month *and* the month with the biggest account behind it. Had the
calendar run the other way — December's conditions arriving in March on $50k —
the compounded result would be far smaller.

**+224% is one ordering of one favourable 7-month sample.**

**2. Compounding amplifies execution risk in both directions.**

At a 30% shortfall, the 10% configuration loses more than twice what the 5% one
does. Compounding is an argument for **smaller** position sizing, not larger.

**3. The 20-contract cap increasingly binds.** It caught 12% of trades by
December and would throttle growth further as the account grows.

### Recommended sequence

1. Trade a **fixed base** for a full quarter.
2. Measure your actual fill rate and price-versus-mid.
3. Re-run `backtest/engine/compound.py` with your measured numbers.
4. Only then decide whether to compound — and if you do, **stay at 5%**.

**A note on which fill assumption these use.** The compounding table above was
produced under the 95%-midpoint assumption, which a five-seed test later showed
carries up to $16,651 of random noise. Under the deterministic 100%-midpoint
assumption the fixed-base result is $53,334 rather than $66,526, so the
compounded figures would scale down correspondingly. Treat the *shape* of the
table — compounding roughly doubles the return, drawdown falls in percentage
terms — as the finding, not the absolute dollars.

---

## Execution — what fill quality is worth

| Scenario | Net |
|---|---|
| Always fill at midpoint | $53,334 |
| Always cross the spread | $31,573 |
| **Value of good fills** | **$21,761 (41%)** |

Worth using MidPrice for. But note the strategy remains profitable even in the
never-get-mid worst case.

### Two different risks, very different costs

MidPrice controls **what price you pay when you fill**. It does not control
**whether you fill.** A resting midpoint order needs someone to cross to you.

| Risk | Mechanism | Effect at 30% |
|---|---|---|
| Price slippage | Wins shrink, losses widen | +224% → **−27%** |
| Non-fills | Fewer trades, same edge each | +150% → **+89%** |

**Non-fills are far less damaging** — they remove winners and losers in
proportion, scaling P&L down without degrading the edge. This is why the
guidance above is "do not chase a fill." Missing a trade is cheap. Overpaying
is not.

### Log these two numbers from day one

1. **Fill rate** — what fraction of orders actually execute
2. **Price vs mid** — when filled, how far from the midpoint

They determine which row of the table above applies to you, and nothing else
you measure matters as much.

---

## Why each filter exists

| Filter | Default | Why |
|---|---|---|
| Earnings + ex-div blackout | 12 days | Largest single improvement in testing |
| Trend SMA10 > SMA50 | on | Better win rate, lower drawdown |
| Risk:reward ≥ 0.20 | on | Drives return on risk (7.6% → 10.1%) |
| Delta 0.25–0.30 target | on | Drives win rate (77.7% → 82.8%) |
| 1 per sector | on | Cut max drawdown 38.3% → 24.2% vs 2/sector |
| Max spread 10% of mid | on | Wide spreads eat the credit |
| IV/RV | **off** | Testing showed it *reduced* performance |

### Delta and risk-reward do different jobs

They are not redundant and neither is "better":

- **Risk-reward drives returns.** R² 0.0593 against return on risk.
- **Delta drives win rate.** R² 0.0009 against returns — almost nothing — but
  it lifts win rate from 77.7% to 82.8%.
- **Together: best profit factor (1.90).**

If you want more opportunities, `R:R ≥ 0.20 AND delta ≤ 0.34` gives **702
trades at PF 1.89** versus 310 trades at PF 1.90 for the tighter band. More
than double the trades, effectively identical quality.

---

## What breaks this

1. **Not passing your open book into the scan.** The sector cap silently stops
   working and you accumulate correlated positions.
2. **Cherry-picking from the ranked list.** The backtest took the top N.
3. **Forcing a second trade on a one-candidate day.** Those are your best days.
4. **Adding a stop loss.** See §5 above.
5. **Chasing fills.** Missing a trade costs ~1% of expectancy; a bad fill costs
   much more.
6. **Scanning intraday for a better entry.** Tested on one daily snapshot.
7. **Compounding before you have measured your fills.**
8. **Sizing up after a winning streak.** 94% of backtest profit came from three
   months — a hot streak is not evidence of anything.

---

## Before risking real money

1. Run the screener daily **without arming**. Watch what it picks for two weeks.
2. Paper trade for **a full quarter**, logging fill rate and price-vs-mid.
3. Compare realised results against `BACKTEST.md`.
4. Re-run the compounding model with your measured numbers.
5. Wait for the 2022 out-of-sample result.

Only then consider arming, with capital you can afford to lose.

---

## Known limits

- 7 months of data, not a year
- 94% of profit from three months
- One regime (2023 recovery), no bear market tested
- Ranking coefficients fitted on the same period they were evaluated on
- EOD data — intraday moves between decision and fill are invisible
- Headline net is $53,334 (deterministic, perfect mid fills). An earlier
  $66,526 figure was the luckiest of five random seeds — see `BACKTEST.md` §15
