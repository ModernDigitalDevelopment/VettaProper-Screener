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

The reconcile call matters. The screener must know your **current open book**
to enforce the sector cap. If you hold a TECH spread, TECH is closed to new
entries until it exits.

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
- 1 per sector (default)
- 4 new positions per day
- 12 open positions total
- 5% of equity at risk per position

### 4. When only one trade qualifies — take it

This is the most common case and the one most likely to be second-guessed.

**39 of 104 entry days produced exactly one position**, and those days had the
**highest win rate of any bucket: 82.1%, PF 3.82.**

When one spread clears every gate, it is one the filters genuinely liked. Do
not relax criteria to find a second trade. Median capital utilisation in the
backtest was **32%** — the strategy sits mostly in cash by design, and that is
why max drawdown is 19.8% rather than 44%.

### 5. Place the order

- **One multi-leg order**, never two single-leg orders. Legging into a spread
  exposes you to the market between fills.
- **Limit at the net credit shown.** Do not market-order a spread.
- If unfilled after a few minutes, improve by $0.01–0.02. If you have given up
  more than ~10% of the credit, cancel — the edge is thin enough that
  overpaying for a fill destroys it.

### 6. Manage exits

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

### On compounding

Backtested compounding (equity updated on realised P&L only):

| Sizing | Final | Return | Max DD |
|---|---|---|---|
| Fixed $50k base, 5% | $116,526 | 133% | 19.8% |
| Compounding 5% | $161,839 | 224% | 13.0% |
| Compounding 10% | $221,277 | 343% | 23.2% |

**Do not act on these yet.** A 30% execution shortfall turns the 5% compounding
result into **−27%** and the 10% into **−68%**. Compounding multiplies
execution quality in both directions.

Recommended: **trade a fixed base until you have a quarter of real fills.**
Once you know your actual slippage, re-run `backtest/engine/compound.py` with a
haircut matching what you measured. Only then decide whether to compound.

---

## Why each filter exists

| Filter | Default | Why |
|---|---|---|
| Earnings + ex-div blackout | 12 days | Largest single improvement in testing |
| Trend SMA10 > SMA50 | on | Better win rate, lower drawdown |
| Risk:reward ≥ 0.20 | on | Drives return on risk (7.6% → 10.1%) |
| Delta 0.25–0.30 target | on | Drives win rate (77.7% → 82.8%) |
| 1 per sector | on | Cut max drawdown 44.4% → 19.8% |
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

1. **Cherry-picking from the ranked list.** The backtest took the top N. Taking
   #3 because you like the company is untested discretion.
2. **Adding a stop loss.** See above.
3. **Scanning intraday for a better entry.** Tested on one daily snapshot.
4. **Relaxing filters on quiet days.** The filters are the edge.
5. **Sizing up after a winning streak.** Neither tested nor safe — 86% of
   backtest profit came from three months.
6. **Ignoring the sector cap** because "this one is different."

---

## Before risking real money

1. Run the screener daily **without arming**. Watch what it picks for two weeks.
2. Paper trade on Alpaca for **a full quarter**.
3. Compare your realised fills against the 95%-at-midpoint assumption. This is
   the single most important measurement you can make.
4. Re-run the compounding model with your measured slippage.
5. Wait for the 2022 out-of-sample result. 2023 was a falling-volatility
   recovery year — close to best case for selling premium.

Only then consider arming, with capital you can afford to lose.

---

## Known limits

- 7 months of data, not a year
- 86% of profit from three months
- One regime (2023 recovery), no bear market tested
- Ranking coefficients fitted on the same period they were evaluated on
- EOD data — intraday moves between decision and fill are invisible
