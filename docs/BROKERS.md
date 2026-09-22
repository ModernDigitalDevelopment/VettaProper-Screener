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
