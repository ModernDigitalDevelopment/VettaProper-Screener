"""Data provider selection.

All three providers expose the same interface, so the screener is agnostic:

    option_chain(underlying, expiry_gte, expiry_lte, contract_type) -> list[dict]
    daily_bars(symbol, start, end) -> list[dict]
    last_price(symbol) -> float | None
    market_open() -> bool

Choosing between them:

    polygon   Best for scanning. One call per underlying returns the whole
              chain with greeks. Requires a paid OPTIONS plan.

    alpaca    Also one call per underlying with greeks and OI. Free with a
              funded account. Real-time needs OPRA agreement accepted,
              otherwise 15-minute delayed. Good default if you have keys.

    ibkr      Quotes from the venue you trade on, but NO bulk chain endpoint —
              thousands of calls to scan a large universe. Requires the Client
              Portal Gateway running and authenticated. Use for a watchlist or
              for pre-trade price confirmation, not full-universe scans.

DATA_PROVIDER=polygon|alpaca|ibkr  (default: polygon, falls back to alpaca)
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

PROVIDERS = {
    "polygon": {
        "label": "Polygon.io / Massive",
        "bulk_chain": True,
        "greeks": True,
        "notes": "Requires paid options plan. Best for full-universe scans.",
    },
    "alpaca": {
        "label": "Alpaca Market Data",
        "bulk_chain": True,
        "greeks": True,
        "notes": "Free with funded account. Needs OPRA agreement for real-time.",
    },
    "ibkr": {
        "label": "Interactive Brokers",
        "bulk_chain": False,
        "greeks": True,
        "notes": "No bulk chain endpoint — slow for large universes. "
                 "Needs Client Portal Gateway authenticated.",
    },
}


def available() -> dict[str, dict]:
    """Which providers are configured on this deployment."""
    out = {}
    for name, meta in PROVIDERS.items():
        if name == "polygon":
            ok = bool(os.getenv("POLYGON_API_KEY"))
        elif name == "alpaca":
            ok = bool(os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"))
        else:
            ok = bool(os.getenv("IBKR_GATEWAY_URL"))
        out[name] = {**meta, "configured": ok}
    return out


def make(name: str | None = None):
    """Return an un-entered async context manager for the chosen provider."""
    name = (name or os.getenv("DATA_PROVIDER") or "polygon").lower()

    if name == "polygon":
        from app.providers.polygon import PolygonClient
        if not os.getenv("POLYGON_API_KEY"):
            if os.getenv("APCA_API_KEY_ID"):
                log.warning("POLYGON_API_KEY unset — falling back to Alpaca data")
                return make("alpaca")
            raise RuntimeError("POLYGON_API_KEY is not set and no fallback configured")
        return PolygonClient()

    if name == "alpaca":
        from app.providers.alpaca_data import AlpacaDataClient
        return AlpacaDataClient()

    if name == "ibkr":
        from app.providers.ibkr_data import IBKRDataClient
        return IBKRDataClient()

    raise ValueError(f"unknown data provider {name!r}; have {list(PROVIDERS)}")
