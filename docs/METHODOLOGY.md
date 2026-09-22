# Methodology, Assumptions & Limitations

This document exists so a reviewer can judge how much to trust the numbers in
`REPORT.md`. It states what the backtest does, what it assumes, and where it
could be wrong.

---

## 1. Data

| Source | Rows | Coverage | Used for |
|---|---|---|---|
| `thetadata_options_march_2023.db` | 963,340 | 2023-03-01 → 03-31 (23 days) | Option chains |
| `thetadata_options_q2_2023.db` | 2,599,309 | 2023-04-03 → 06-30 (62 days) | Option chains |
| `thetadata_options_q4_2023.db` | 2,768,979 | 2023-10-02 → 12-29 (63 days) | Option chains |
| `ib_screener_cache.db → price_bars` | 275,961 | 2022-01-03 → 2024-12-31 (753 days) | SMAs |
| `ib_screener_cache.db → events` | 31,729 | 4,600 EARNINGS + 27,129 EX_DIV | Earnings blackout |

Option data is **end-of-day snapshots**, one row per contract per day, containing
`bid`, `ask`, `bid_size`, `ask_size`, `volume`, `delta`, `gamma`, `theta`, `vega`,
`implied_vol`, `underlying_price`.

Field completeness (Q4 2023): `ask` 100%, `bid` 89.9%, `delta` 99.3%,
`implied_vol` 95.9%, `underlying_price` 100%, `volume` 53.6%.

### 1.1 A data problem that was handled explicitly

The three option databases are **discontiguous** (March, then April–June, then
October–December). A naive 50-day moving average computed from option-implied
underlying prices would have silently blended June data into October.

**Resolution:** SMAs are computed from `ib_screener_cache.db → price_bars`, which
has 753 *continuous* trading days. This yields 100% valid SMA coverage inside all
three test quarters. Verified before use.

---

## 2. Trade Construction

For each trading day, for each symbol:

1. **Signal gates** — reject if earnings within N days; reject if not
   (price > 50 SMA AND 10 SMA > 50 SMA); optionally reject if IV/RV below threshold.
2. **Expiration** — choose the expiration nearest the target DTE within tolerance.
3. **Short leg** — the strike whose `|delta|` is closest to target, subject to
   relative bid/ask ≤ threshold.
4. **Long leg** — the strike closest to the desired width, same expiration,
   requiring a positive quote.
5. **Economics check** — reject if credit < minimum, if credit ≥ width, or if
   implied max loss per contract < $25 (see §4.2).
6. **Ranking** — candidates sorted by credit/width descending.
7. **Portfolio gates** — max open positions, max new per day, max per sector,
   one position per symbol at a time.
8. **Sizing** — contracts = floor(equity × 5% ÷ max_loss_per_contract), capped at 20.

### 2.1 Fill pricing

This is the most consequential modelling choice.

- **Crossing (`fill_aggr`/`mid_fill_prob = 0`)** — a sold leg fills at the **bid**,
  a bought leg at the **ask**. This is the pessimistic, always-executable case.
- **Midpoint** — legs fill at `(bid + ask) / 2`.
- `mid_fill_prob` is the probability a given order fills at mid; otherwise it crosses.
  Drawn per-order from a seeded RNG.

Closing uses exact reverse sides: a previously sold leg is bought back at the
**ask**, a previously bought leg sold at the **bid**.

**Commissions:** $0.65 per contract per leg, charged on both open and close
(2 legs × 2 sides for a vertical). Stress-tested at $1.00.

---

## 3. Exit Logic

Evaluated on each subsequent daily snapshot, in this order:

1. **Expiry settlement** — if DTE ≤ 0, settle at intrinsic value against the last
   observed underlying price.
2. **Profit target** — close when closing debit ≤ credit × (1 − target).
   "80% of max profit" means the position can be bought back for 20% of credit.
3. **Pre-expiry exit** — close at the last snapshot at or before
   `exit_days_before_expiry` (1 day = Thursday close for a Friday expiry).
4. **Optional stop / ATR breach** — tested and rejected (see `REPORT.md` §5).

There is no intraday data, so exits occur at **end-of-day marks only**.

---

## 4. Known Limitations

### 4.1 No intraday data — cuts both ways

All entries and exits occur at EOD snapshots. Real intraday stop-outs, gap fills
and mid-session profit targets are not modelled. This is **optimistic** for stop
strategies (which would trigger more often intraday) and roughly **neutral** for
the validated configuration, which uses profit targets and a time-based exit.

### 4.2 A bug that was found and fixed — disclosed in full

The first iteration of the iron condor test produced an impossible
**−$73 quadrillion** result. Root cause:

- Validity check rejected `credit ≥ width`. For a condor this is wrong — it
  collects premium on both wings, so total credit legitimately approaches the
  width of one wing.
- Max loss = `width − credit`. As credit → width, max loss → ~$0.
- The 5% position sizer divided $2,500 by a near-zero number, producing thousands
  of contracts on what were **stale/crossed quote artifacts** (14 of 1,099 condors
  had credit ≥ 95% of width).

**Fix:** reject any structure whose implied max loss per contract is under $25,
and hard-cap position size at 20 contracts.

**Impact:** all condor results were inflated before this fix. The corrected
0.40-delta condor figure is **+$35,899, not +$47,839**. All numbers in
`REPORT.md` are post-fix. This is also why condors were ultimately rejected: on
inspection, 96% of the corrected profit came from **5 trades**, and removing the
single Q4 melt-up quarter left **−$15,793**.

### 4.3 Expiry settlement uses the last observed underlying price

Where an option's expiration falls inside the data window, settlement uses the
underlying price from the final available snapshot rather than the official
settlement price. Minor, but it can misprice strikes pinned very close to spot.

### 4.4 Positions held past the data window

Trades still open at the end of a quarter are marked `FORCE_CLOSE` at the last
available quote. In the validated configuration this affects ~12% of trades. It is
a modest optimism (no adverse gap beyond the window is possible).

### 4.5 Survivorship and universe composition

The symbol universe is whatever ThetaData collection captured (~360 names). It was
selected in 2026 for 2023 backtesting, so **delisted or acquired names from 2023
may be absent** — a mild survivorship bias.

### 4.6 Sector classification

Uses the project's own 365-symbol `SECTOR_MAP` from `screener_engine.py`. About
18% of trades in the validated config fall in `UNKNOWN`, which weakens the
"max 2 per sector" constraint for those names.

### 4.7 Single-period validation

Three quarters, all 2023, all in a rising market (SPY +7.9% Q2, +11.2% Q4). This
is the most important limitation in the whole package. See `REPORT.md` §7.

---

## 5. Statistical Approach

- **Expectancy** = mean net P&L per trade, after commission and modelled slippage.
- **Profit factor** = gross wins ÷ |gross losses|.
- **Max drawdown** = largest peak-to-trough decline of the cumulative P&L curve,
  ordered by exit date.
- **Bootstrap CI** — 20,000 resamples with replacement of the realised trade P&L
  distribution; reports the 2.5th/97.5th percentiles of resampled mean expectancy
  and the fraction of resamples at or below zero.
- **Cross-quarter robustness** — a configuration is only accepted if it is
  profitable in *each* of the three quarters independently, not merely in aggregate.

Bootstrap CIs assume trades are independent. Positions overlap in time and share
market exposure, so **true confidence intervals are wider than reported.**

---

## 6. Reproduction

```bash
# Prerequisites: python3, pandas, pyarrow, openpyxl
# Place the four .db files where code/dbs.py expects them, then:

cd code
python3 final_validate.py     # reproduces REPORT.md §6.2
python3 stress.py             # reproduces REPORT.md §6.4
python3 earn_test.py          # earnings blackout sweep
python3 trend_test.py         # trend filter sweep
python3 rerun.py              # delta sweep, post-bugfix
python3 scale_test.py         # contract scaling (negative result)
python3 weekend.py            # weekend theta (negative result)
```

`data/*.pkl` contain pre-computed signal, trend, event and sector lookups so the
scripts run without re-deriving them from the source databases.

---

## 7. What Would Change the Conclusion

Stated in advance, so the analysis is falsifiable:

1. **Measured fill rates below ~70% at midpoint** → expectancy falls toward
   +$17/trade; the strategy would not be worth trading at scale.
2. **A 2021–2022 backtest showing negative expectancy** → the configuration is a
   bull-market artifact and should be abandoned.
3. **A max-loss cluster** (3+ simultaneous breaches in correlated names) →
   indicates the 2-per-sector limit is insufficient; sector definitions would need
   to be tightened or correlation-based limits introduced.
