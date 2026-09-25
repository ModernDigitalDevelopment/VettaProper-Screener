# Vetta Proper Screener

Options credit-spread screener with a backtest-derived ranking model, live
Polygon data, and order submission to Alpaca or Interactive Brokers.

Every default in this application traces to a measured backtest result.
Where the evidence is weak, the UI says so.

---

## What it does

1. Scans the S&P 500 / 400 and Nasdaq 100 for credit spreads meeting your criteria
2. Ranks candidates using a model fitted on 2,129 historical trades
   (delta × risk-reward)
3. Sizes positions against your equity and per-sector limits
4. Submits to Alpaca or IBKR — **dry run until explicitly armed**
5. Shows the full research record at `/research`

---

## Headline results

Recommended configuration, backtested on ThetaData 2023 EOD chains:

| Metric | Value |
|---|---|
| Trades | 205 |
| Win rate | **80.0%** |
| Expectancy | $344/trade |
| Net | $70,526 on $50,000 |
| Profit factor | 2.20 |
| Max drawdown | 14.6% |
| Peak capital at risk | 51% |

That configuration includes an **ADX ≥ 20 trend-strength filter**, ported from
the indicator suite in the predecessor screener. Against the same setup without
it: +32% net, +3.8pp win rate, −9.6pp drawdown, on 15% fewer trades. See
[`docs/INDICATORS.md`](docs/INDICATORS.md).

**Correction:** an earlier version of this README quoted $66,526. That was the
luckiest of five random seeds at a 95% midpoint-fill assumption. The
deterministic result with perfect midpoint fills is **$53,334**; the seed-mean
at 95% is $59,597. Details in `docs/BACKTEST.md` §15.

**Read this before quoting those numbers:**

- The data covers **7 months**, not a year (Mar, Apr–Jun, Oct–Dec 2023).
- **86% of profit came from three months.** Four were roughly flat.
- 2023 was a falling-volatility recovery year — close to best case for selling
  premium. The strategy has never been tested against 2022, 2020 or 2018.
- The ranking model was fitted on the same period it was evaluated on. There is
  no out-of-sample validation yet.

Configurations reaching $133K net exist in the grid. They are **not executable** —
they ran 117% peak capital at risk, which is a margin call, not a return. They
are shown on the research page struck through, for honesty rather than as options.

Full detail: [`docs/BACKTEST.md`](docs/BACKTEST.md)

---

## The ranking model

Candidates are ranked by predicted return on risk, from an OLS fit on 2,129
unranked trades:

```
rr         +1.1350     risk-reward drives returns
delta      -1.2623     higher delta is penalised
rr × delta -2.5379     high delta erodes the benefit of high risk-reward
```

R² is 0.063 — low, and expected to be. In a 77% win-rate strategy, individual
outcomes are dominated by whether the underlying stayed above a strike. What the
fit establishes is the shape, and the interaction term is the insight:
**a fat credit is worth much less when you had to go close to the money to get it.**

Measured effect, 5% sizing / 2 per sector, all else equal:

| Ranking | Win % | Net | PF |
|---|---|---|---|
| credit / width | 71.9% | $61,015 | 1.40 |
| fitted δ × R:R | **75.0%** | **$74,144** | **1.60** |

---

## Quick start

```bash
git clone https://github.com/ModernDigitalDevelopment/VettaProper-Screener.git
cd VettaProper-Screener

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # paste your Polygon key into POLYGON_API_KEY=
python check_config.py --live   # verify the key works before trading
uvicorn app.main:app --reload --port 3000
```

Open <http://localhost:3000>.

Full detail: [`docs/SETUP_KEYS.md`](docs/SETUP_KEYS.md)

### Polygon plan

Options snapshots with greeks require a **paid options plan**. A stocks-only
plan returns 403. The app reports this clearly rather than silently returning
nothing.

---

## Configurable criteria

Everything below is a UI toggle. Each was a variable in the backtest grid.

| Group | Controls |
|---|---|
| Structure | bull put / bear call / iron condor, target delta, tolerance, width |
| Expiry | target DTE, tolerance |
| Edge gates | min risk:reward, IV/RV filter (**off by default**) |
| Blackout | earnings window days, include ex-dividend |
| Trend | SMA10>50, SMA10>30, below 50, or none |
| Liquidity | max bid/ask spread, min open interest, min credit |
| Sizing | equity, % per position, max per sector, max open, max new/day |
| Exits | profit target, days before expiry |
| Ranking | fitted score, risk:reward, credit/width, lowest delta |

### Presets

Four presets carry their measured backtest results in the UI, so selecting one
shows you what you are actually choosing:

- **Validated Conservative** — 77.5% win, 19.8% DD ← recommended
- **High win rate** — 83.7% win, lower expectancy, 31% DD
- **2 per sector** — more trades, 44% DD
- **Aggressive 10%** — labelled with its 41% drawdown

Changing any field switches to "Custom" and warns that the combination was not
backtested as a set. That warning is deliberate: individually-validated settings
do not compose into a validated strategy.

### On IV/RV

Off by default. It was assumed essential early in the research and asserted as
such — testing showed it **reduced** performance once trend and earnings filters
were in place. It remains available as a toggle.

---

## Brokers

| | Alpaca | IBKR |
|---|---|---|
| Serverless deployment | ✅ | ❌ requires Client Portal Gateway |
| Native multi-leg orders | ✅ | ✅ |
| Unattended operation | ✅ | ⚠️ session expires, 2FA to renew |

**Both adapters are DRY RUN by default.** Arming requires a server-side
environment variable (`VPS_ALPACA_LIVE=1`), never a UI control.

Orders carry a deterministic SHA-256 client order id, so a retry cannot
double-fill. Ambiguous sends return `SENT_UNKNOWN` rather than being treated as
failures and retried.

See [`docs/BROKERS.md`](docs/BROKERS.md) — **read the IBKR section before
planning a deployment around it.**

---

## Backtest data

`backtest/data/` contains everything needed to re-run and challenge the research
(9.2 MB): event calendar, trend SMAs, VIX, sectors, and the 2,129-trade sample
the ranking was fitted on.

The raw ThetaData databases (2.5 GB) are not in git — two of the four files
exceed GitHub's 100 MB limit by more than 10×. Use object storage:

```bash
export BACKTEST_DATA_URL=https://<account>.r2.cloudflarestorage.com/vetta-backtest-data
python backtest/fetch_data.py --all
```

Roughly $0.04/month on Cloudflare R2. See [`docs/DATA.md`](docs/DATA.md).

### Re-running backtests

```bash
pip install -r requirements-dev.txt
python backtest/engine/screener_bt.py      # 5% and 10%, ranked vs unranked
python backtest/engine/screener_tune.py    # risk-level variants
```

---

## Project layout

```
app/
  core/criteria.py      every toggle + presets with measured results
  core/ranking.py       the fitted model, with its derivation in comments
  providers/polygon.py  chain snapshots, greeks, daily bars
  screener/engine.py    gates, construction, sizing (mirrors backtest order)
  screener/scan.py      orchestration + rejection accounting
  brokers/              alpaca.py, ibkr.py, base.py (idempotency, arming)
web/                    screener UI + research page
backtest/               engine, data, results
docs/                   BACKTEST.md, BROKERS.md, DATA.md, FINDINGS.md
tests/                  28 tests
```

`app/screener/engine.py` deliberately mirrors the gate order in
`backtest/engine/spec_engine.py`. **Change one, change both** — otherwise live
results stop matching tested results.

---

## Tests

```bash
pytest -q        # 28 passed
```

Covers ranking monotonicity, every gate, sizing caps, sector caps, OCC symbol
formatting, order idempotency, and that both brokers default to dry run.

---

## Recommended path to live

1. Run the screener daily without arming. Watch what it selects.
2. Paper trade on Alpaca for **a full quarter**.
3. Compare realised fills and win rate against `docs/BACKTEST.md`.
4. If reality matches, consider arming with capital you can afford to lose.
5. Before scaling, extend the backtest to 2022 — a bear market is the single
   most informative missing test.

The predecessor system lost $28,529 with no black swan involved. The causes were
sector concentration (84% of the loss), friction-driven day-one stop-outs
(35 of 75 stops), and an automation path that ran a simulator while appearing to
trade. Those three failures shaped every design decision here.
