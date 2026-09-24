# Broker integration

## Safety model

Both adapters start in **DRY RUN**. A dry run builds the full order payload,
logs it, returns a deterministic client order id — and sends nothing.

Live submission requires an environment variable set to exactly `1`:

```bash
VPS_ALPACA_LIVE=1     # arms Alpaca
VPS_IBKR_LIVE=1       # arms IBKR
```

There is deliberately **no UI control for this**. Arming requires server access.

### Why arming is an env var and not a button

The predecessor system had `broker_execution_enabled = False` hardcoded in
policy, with a UI that looked fully operational. It ran a simulator with
synthetic fills for months. The dashboard showed positions, P&L, and fills that
did not exist.

The lesson taken from that is not "make it easier to enable trading" — it is
**make the armed/disarmed state impossible to misread**. The header pill reads
`Dry run` or `ARMED`, driven by the same env var the adapters read. There is one
source of truth.

### Idempotency

Every order carries a `client_order_id` derived from SHA-256 of its economic
terms: date, symbol, quantity, limit price, structure, and sorted legs.

```
vps-8cf6b7949caad8a74917179e
```

The same spread, same day, same size produces the same id — so a double-click or
a retry cannot double-fill. Changing quantity or price produces a different id,
because it is a genuinely different order.

### SENT_UNKNOWN

If a network call fails *after* the request has left the process, the adapter
returns `SENT_UNKNOWN`, not `REJECTED`.

An ambiguous send is not a failure. Treating it as one and retrying is how
duplicate positions get created. `SENT_UNKNOWN` requires a human to check the
broker before acting.

---

## Alpaca

**Works from any deployment, including serverless.**

Alpaca supports native multi-leg options orders (`order_class: "mleg"`, up to 4
legs). A credit spread submits as one atomic order — no legging risk.

### Setup

1. Create a paper account at <https://alpaca.markets>
2. Enable options trading and request the level you need
   (Level 2 covers long options; **spreads require Level 3**)
3. Generate API keys
4. Put them in `.env`:

```bash
APCA_API_KEY_ID=PK...
APCA_API_SECRET_KEY=...
APCA_API_BASE_URL=https://paper-api.alpaca.markets
```

Verify with `GET /api/broker/alpaca/account` — the response includes
`options_level`. If it is below 3, spread orders will be rejected by Alpaca
regardless of what this app does.

### Going live

Change `APCA_API_BASE_URL` to `https://api.alpaca.markets` **and** set
`VPS_ALPACA_LIVE=1`. Both are required. Changing only the URL leaves the
adapter in dry run.

---

## Interactive Brokers

**Read this before planning around IBKR.**

IBKR's Web API is not a plain cloud REST API. Authenticated trading requires a
session established through the **Client Portal Gateway** — a Java process that
runs alongside your application and holds the login. OAuth consumer
registration, which would remove the gateway requirement, is generally not
available for individual IBKR Pro accounts.

### What this means practically

| | Alpaca | IBKR |
|---|---|---|
| Serverless / static hosting | ✅ | ❌ |
| Needs a companion process | No | **Yes** (gateway) |
| Session expiry | No | **Yes** — periodic re-auth |
| 2FA on re-auth | No | **Yes, human required** |
| Unattended overnight operation | ✅ | ⚠️ Fragile |

**You cannot run IBKR from a Cloudflare Worker, Vercel function, or any
serverless deployment.** IBKR requires a persistent host — a VPS, a container
running both processes, or your own machine.

### Setup

1. Download the Client Portal Gateway from IBKR
2. Run it: `./bin/run.sh root/conf.yaml`
3. Open `https://localhost:5000` and log in (2FA required)
4. Configure:

```bash
IBKR_GATEWAY_URL=https://localhost:5000
IBKR_ACCOUNT_ID=U1234567
IBKR_VERIFY_SSL=0      # the gateway ships a self-signed cert
```

Check status with `GET /api/broker/ibkr/account`. If the gateway is unreachable
or unauthenticated, the adapter says so explicitly rather than failing silently.

### Combo orders

IBKR spreads use a `conidex` string mapping contract ids to ratios:

```
265598/-1,265599/1      # sell one, buy one
```

The adapter resolves conids via `/iserver/secdef/info`. If IBKR returns a
confirmation prompt (margin warnings, etc.), the adapter surfaces it as
`SENT_UNKNOWN` and does **not** auto-confirm. Auto-confirming broker warnings
is how unintended orders get placed.

---

## Recommendation

Start with **Alpaca paper**. It deploys anywhere, needs no companion process,
and supports native multi-leg orders.

Add IBKR when you need it for better fills or an existing account, and accept
that it constrains where the app can run. A sensible pattern is to keep the
screener serverless and run a small IBKR executor on a VPS that pulls signals
from it.

---

# Market data providers

Three sources, one interface. Switch with `DATA_PROVIDER` or the UI dropdown.

| | Polygon | Alpaca | IBKR |
|---|---|---|---|
| Whole chain in one call | ✅ | ✅ | ❌ |
| Greeks | ✅ | ✅ (computed) | ✅ (needs subscription) |
| Cost | Paid options plan | Free with funded account | Data subscriptions |
| Real-time | ✅ | Needs OPRA agreement | ✅ |
| Full-universe scan | ✅ | ✅ | ❌ blocked |
| Needs companion process | No | No | **Yes** |

## Alpaca data — yes, this is feasible

You weren't sure this was possible. It is, and it may be your best option.

`GET /v1beta1/options/snapshots/{underlying}` returns quotes, greeks and open
interest for a whole underlying in one call — the same shape as Polygon, so it
drops into the screener unchanged.

```bash
DATA_PROVIDER=alpaca
ALPACA_OPTIONS_FEED=indicative   # or 'opra' for real-time
```

Two caveats:

1. **Real-time needs the OPRA agreement** accepted in the Alpaca dashboard.
   Without it you get 15-minute delayed data. For scanning 7–11 DTE spreads
   that is acceptable; for execution pricing it is not.
2. **Greeks are computed by Alpaca**, not exchange-provided. Fine for delta
   targeting, but they will not match IBKR tick-for-tick.

Using Alpaca data means the quotes come from the venue you are trading on,
which removes a paid dependency and eliminates data-vs-execution mismatch.

## IBKR data — works, but know the constraint

The hard limitation is structural: **IBKR has no bulk chain endpoint.**

Polygon or Alpaca: one call returns AAPL's whole chain.
IBKR: resolve underlying conid → list strikes → resolve each strike to a conid
→ request market data per conid. For 365 symbols that is thousands of calls.

The app therefore **blocks full-universe scans on IBKR** and returns a 400
explaining why. Pass an explicit watchlist instead:

```json
POST /api/scan
{ "provider": "ibkr", "symbols": ["AAPL","MSFT","NVDA"], "criteria": {...} }
```

### Snapshot priming

IBKR's REST snapshot endpoint is streaming-first: the first call for a contract
primes a subscription and often returns empty. This is documented IBKR
behaviour, not a bug. `_snapshot_with_priming()` polls until fields appear.

### Session management

The gateway session expires and renewal requires human 2FA.

- `GET /api/ibkr/status` — reachable? authenticated? includes a remedy string
- `POST /api/ibkr/keepalive` — ping to hold the session open

Call keepalive every few minutes during market hours. The UI checks status
automatically when you select IBKR and shows a red banner if the session is
down, so a scan never fails mysteriously.

## Recommended setup

**Polygon or Alpaca for scanning, IBKR for execution.**

Scanning needs breadth and cheap bulk access. Execution needs the venue you
actually trade on. Using IBKR for both means either a very slow scan or a very
small universe.

If you have Alpaca keys already, try `DATA_PROVIDER=alpaca` first — it removes
the Polygon subscription from your critical path.

## Reconciliation

`GET /api/reconcile/{broker}` returns what the broker actually holds, grouped by
sector. Feed `by_sector` into `/api/scan` as `open_sectors` so per-sector caps
account for positions you already have.

The predecessor system's dashboard displayed positions that did not exist. This
endpoint is here so that cannot silently happen again.
