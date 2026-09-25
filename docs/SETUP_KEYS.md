# Where to put your API keys

## Quick version

```bash
cd VettaProper-Screener
cp .env.example .env
nano .env            # paste your key next to POLYGON_API_KEY=
python check_config.py --live
```

`.env` is gitignored. It never reaches GitHub.

---

## The file

Create `.env` in the project root (same folder as `README.md`):

```bash
# Market data
POLYGON_API_KEY=paste_your_polygon_key_here
DATA_PROVIDER=polygon

# Alpaca — data AND execution, paper by default
APCA_API_KEY_ID=
APCA_API_SECRET_KEY=
APCA_API_BASE_URL=https://paper-api.alpaca.markets

# IBKR — execution (needs the Client Portal Gateway running)
IBKR_GATEWAY_URL=https://localhost:5000
IBKR_ACCOUNT_ID=
IBKR_VERIFY_SSL=0

# Arming flags — leave at 0 until you have paper traded
VPS_ALPACA_LIVE=0
VPS_IBKR_LIVE=0
```

Only `POLYGON_API_KEY` is needed to pull live data.

## Polygon has one key, not a key/secret pair

Polygon (rebranded **Massive** in 2026) issues a single API key, sent as a
bearer token. If you are looking for a separate "secret", there isn't one —
the single key is the credential. Alpaca is the one that uses a key + secret
pair.

**Your plan must include options.** A stocks-only plan returns 403 on the
options snapshot endpoint. `check_config.py --live` reports this explicitly.

## Verify it

```bash
python check_config.py           # config only, no network
python check_config.py --live    # one real call per provider
```

The live check confirms Polygon returns option contracts **with greeks** — the
screener cannot target strikes by delta without them.

Output masks secrets (first 6 characters only).

---

## Production deployment

Do not ship a `.env` file to a server. Use the platform's secret store:

```bash
# systemd
sudo systemctl edit vetta-screener
#   [Service]
#   Environment="POLYGON_API_KEY=..."

# Docker
docker run -e POLYGON_API_KEY=... ...

# Fly / Railway / Render
fly secrets set POLYGON_API_KEY=...
```

Real environment variables take precedence over `.env`.

---

## If a key leaks

1. **Revoke it first** in the Polygon dashboard. Do not start with git history.
2. Issue a new key.
3. Then clean history if it was committed (`git filter-repo`), and remember
   that anyone who already cloned the repo still has the old key — which is
   why step 1 comes first.

---

## Troubleshooting

**"POLYGON_API_KEY is not set" but it is in .env**

Most likely an empty-but-set shell variable. This used to silently defeat
`.env` because `python-dotenv` does not overwrite existing variables — even
empty ones. The app now deletes blank values before loading `.env`, so this is
handled, but you can confirm with:

```bash
echo "[${POLYGON_API_KEY}]"     # prints [] if set-but-empty
unset POLYGON_API_KEY
```

**403 from Polygon** — plan does not include options data.

**Chain returns but no greeks** — greeks require the options entitlement. The
screener needs delta.

**Empty chain** — market closed, or no expiries in the 7-11 DTE window.
