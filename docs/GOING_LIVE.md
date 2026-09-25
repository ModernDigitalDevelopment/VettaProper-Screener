# Making the screener live

"Live" means three separate things. Do them in order — each one is useful on
its own, and stopping after step 1 or 2 is a perfectly sensible place to be.

| Stage | What it means | Risk |
|---|---|---|
| **1. Live data** | Real option chains instead of nothing | None |
| **2. Hosted** | Reachable from a URL, not just your laptop | None |
| **3. Armed** | Orders actually reach a broker | Real money |

---

## Stage 1 — live data (10 minutes, no risk)

```bash
git clone https://github.com/ModernDigitalDevelopment/VettaProper-Screener.git
cd VettaProper-Screener

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# paste your key on the POLYGON_API_KEY= line

python check_config.py --live
```

`check_config.py --live` is the gate. It verifies the three things that
actually break:

1. The key authenticates (401 = wrong key)
2. Your plan includes **options** (403 = stocks-only plan)
3. Chains return **with greeks** — without delta, strike targeting cannot work
   at all, and this fails silently otherwise

Only when that passes:

```bash
uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000>, pick **ADX Trend Strength**, hit Run Screener.

**You are now live on data.** Nothing can send an order — both broker adapters
are hard-wired to dry run until an environment variable says otherwise.

### If you would rather not pay Polygon

Alpaca's option snapshots include greeks and open interest, one call per
underlying, free with a funded account:

```bash
DATA_PROVIDER=alpaca
APCA_API_KEY_ID=...
APCA_API_SECRET_KEY=...
ALPACA_OPTIONS_FEED=indicative    # or 'opra' for real-time
```

`indicative` is 15-minute delayed. Fine for scanning 7–11 DTE spreads, not for
execution pricing. Real-time needs the OPRA agreement accepted in the Alpaca
dashboard.

---

## Stage 2 — hosting

**This is a Python/FastAPI app.** It needs a real host — it cannot go on
Cloudflare Pages or any static/serverless-only platform.

### Option A — fly.io (recommended, ~$2–5/month)

```bash
fly launch --no-deploy          # fly.toml is already in the repo
fly secrets set POLYGON_API_KEY=your_key_here
fly deploy
```

Secrets live in Fly's store, never in the image or in git.

`fly.toml` ships with `min_machines_running = 0`, so the machine suspends when
idle and costs almost nothing. First request after idle takes a few seconds.
Set it to `1` if you want it always warm.

### Option B — Docker anywhere

```bash
docker compose up -d           # reads your local .env
```

Works on any VPS. This is also the **only** option if you want IBKR, because
IBKR needs the Client Portal Gateway running alongside the app (commented out
in `docker-compose.yml`).

### Option C — Railway / Render

Connect the GitHub repo, set `POLYGON_API_KEY` in their dashboard, deploy. Both
auto-detect the Dockerfile. Simplest if you dislike CLIs.

### Put it behind auth

The screener shows your positions and account. Do not leave it open to the
internet. On Fly:

```bash
fly ips list                   # then restrict, or front it with Cloudflare Access
```

Cheapest good answer: Cloudflare Access in front of the hostname, restricted to
your email. Free for small teams.

---

## Stage 3 — arming (real orders)

**Do not do this yet.** The recommended sequence:

1. Run the screener daily for **two weeks** without arming. Watch what it picks.
2. Paper trade for **a full quarter**, logging fill rate and price-vs-mid.
3. Compare against `docs/BACKTEST.md`.
4. Wait for the 2022 out-of-sample result.

### Paper trading on Alpaca

```bash
APCA_API_KEY_ID=...
APCA_API_SECRET_KEY=...
APCA_API_BASE_URL=https://paper-api.alpaca.markets
VPS_ALPACA_LIVE=1        # arms the adapter — paper account, fake money
```

Even here, check your **options level is 3**. Spreads are rejected below that,
regardless of what this app does. `check_config.py --live` reports it.

### Real money

Change the base URL **and** keep the arming flag:

```bash
APCA_API_BASE_URL=https://api.alpaca.markets
VPS_ALPACA_LIVE=1
```

Both are required. Changing only the URL leaves you in dry run — deliberately.

### Why arming is an environment variable, not a button

The predecessor system had `broker_execution_enabled = False` hardcoded while
its dashboard looked fully operational. It ran a simulator with synthetic fills
for months and showed positions that did not exist.

The fix is not to make enabling easier — it is to make the armed/disarmed state
impossible to misread. The header pill reads `Dry run` or `ARMED`, driven by the
same variable the adapters read. One source of truth, and changing it requires
server access.

---

## Daily operation

Full procedure in [`HOWTO_TRADE.md`](HOWTO_TRADE.md). The short version:

```
GET  /api/reconcile/alpaca     → what do I hold? (feeds the sector cap)
POST /api/scan                 → with open_sectors from the line above
                                 take the ranked list top-down
```

**Pass `open_sectors` every time.** The sector cap is portfolio-wide, and
without it the screener only sees today's entries — so it will hand you a
second TECH spread while you already hold one.

One scan per day. The backtest used a single daily snapshot; scanning
repeatedly and picking your moment is a different, untested strategy.

---

## What "live" does not mean

- **Not automated.** There is no scheduler. You run the scan and you place the
  orders. That is deliberate — the predecessor's automation was where the
  silent failures lived.
- **Not validated out-of-sample.** Every number comes from 7 months of 2023, a
  falling-volatility recovery year. 2022 is the real test.
- **Not a guarantee.** 94% of backtest profit came from three months.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `POLYGON_API_KEY is not set` but it is in `.env` | A blank-but-set shell variable. Run `unset POLYGON_API_KEY`. |
| 403 from Polygon | Plan lacks options data |
| Chain returns, no greeks | Options entitlement missing — screener needs delta |
| Scan returns nothing | Check the `rejections` block in the response; it names the gate that ate everything |
| `no_indicator_data` rejections | Fewer than 50 daily bars — usually a recent listing |
| Alpaca rejects the order | Options level below 3 |
| IBKR "not authenticated" | Gateway session expired; log in via browser (2FA) |

Every scan response includes a `rejections` breakdown. If a scan comes back
empty, that tells you which filter was responsible rather than leaving you
guessing.
