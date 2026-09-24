"""Alpaca market data provider.

You asked whether this was feasible — it is, and it is a better fit than IBKR
data for this use case.

Alpaca's option chain endpoint returns quotes AND greeks AND open interest for
a whole underlying in one call, with strike/expiry filters:

    GET https://data.alpaca.markets/v1beta1/options/snapshots/{underlying}

That is the same shape as Polygon, so it drops straight into the screener.

What to know:

1. Free with a funded account. Options data is included with brokerage
   accounts — no separate data subscription, unlike IBKR.
2. OPRA feed requires agreement acceptance in the Alpaca dashboard. Without it
   you get 15-minute delayed data (`feed=indicative`), which is fine for
   scanning 7-11 DTE spreads but not for execution pricing.
3. Greeks are computed by Alpaca, not exchange-provided. They are close enough
   for delta targeting but will not tick-for-tick match IBKR's.
4. Paper and live accounts use the SAME data endpoint and the same keys.

RECOMMENDATION: if you already have Alpaca keys, use this as your primary data
source and keep Polygon as a fallback. It removes a paid dependency and the
data comes from the venue you are trading on.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any

import httpx

log = logging.getLogger(__name__)

DATA_URL = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")


class AlpacaDataError(RuntimeError):
    pass


class AlpacaDataClient:
    """Same interface as PolygonClient."""

    def __init__(self, key: str | None = None, secret: str | None = None,
                 feed: str | None = None, max_concurrency: int = 8,
                 timeout: float = 20.0):
        self.key = key or os.getenv("APCA_API_KEY_ID", "")
        self.secret = secret or os.getenv("APCA_API_SECRET_KEY", "")
        if not (self.key and self.secret):
            raise AlpacaDataError(
                "Alpaca keys not set (APCA_API_KEY_ID / APCA_API_SECRET_KEY)")
        # 'opra' = real-time (requires agreement), 'indicative' = 15min delayed
        self.feed = feed or os.getenv("ALPACA_OPTIONS_FEED", "indicative")
        self._sem = asyncio.Semaphore(max_concurrency)
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=DATA_URL, timeout=self._timeout,
            headers={"APCA-API-KEY-ID": self.key,
                     "APCA-API-SECRET-KEY": self.secret},
        )
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.aclose()

    async def _get(self, path: str, **params) -> dict[str, Any]:
        assert self._client, "use as async context manager"
        async with self._sem:
            for attempt in range(4):
                r = await self._client.get(path, params=params)
                if r.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if r.status_code == 403:
                    raise AlpacaDataError(
                        "Alpaca returned 403. For real-time options data you must "
                        "accept the OPRA agreement in the Alpaca dashboard, or set "
                        "ALPACA_OPTIONS_FEED=indicative for delayed data.")
                r.raise_for_status()
                return r.json()
        raise AlpacaDataError(f"rate limited repeatedly on {path}")

    async def market_open(self) -> bool:
        try:
            base = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
            async with httpx.AsyncClient(
                    base_url=base, timeout=10.0,
                    headers={"APCA-API-KEY-ID": self.key,
                             "APCA-API-SECRET-KEY": self.secret}) as cli:
                r = await cli.get("/v2/clock")
                r.raise_for_status()
                return bool(r.json().get("is_open"))
        except Exception:
            return False

    async def daily_bars(self, symbol: str, start: date, end: date) -> list[dict]:
        out: list[dict] = []
        page: str | None = None
        for _ in range(20):
            p: dict[str, Any] = {
                "symbols": symbol, "timeframe": "1Day",
                "start": start.isoformat(), "end": end.isoformat(),
                "adjustment": "split", "limit": 10000, "feed": "iex",
            }
            if page:
                p["page_token"] = page
            d = await self._get("/v2/stocks/bars", **p)
            for b in (d.get("bars") or {}).get(symbol, []) or []:
                out.append({
                    "date": b["t"][:10], "open": b["o"], "high": b["h"],
                    "low": b["l"], "close": b["c"], "volume": b.get("v", 0),
                })
            page = d.get("next_page_token")
            if not page:
                break
        out.sort(key=lambda x: x["date"])
        return out

    async def last_price(self, symbol: str) -> float | None:
        try:
            d = await self._get(f"/v2/stocks/{symbol}/trades/latest", feed="iex")
            return float((d.get("trade") or {}).get("p") or 0) or None
        except Exception as e:
            log.debug("last_price %s: %s", symbol, e)
            return None

    async def option_chain(self, underlying: str, expiry_gte: date | None = None,
                           expiry_lte: date | None = None,
                           contract_type: str | None = None) -> list[dict]:
        """Snapshot with quotes + greeks + OI, one call per underlying."""
        params: dict[str, Any] = {"limit": 1000, "feed": self.feed}
        if expiry_gte:
            params["expiration_date_gte"] = expiry_gte.isoformat()
        if expiry_lte:
            params["expiration_date_lte"] = expiry_lte.isoformat()
        if contract_type:
            params["type"] = "put" if contract_type.lower().startswith("p") else "call"

        out: list[dict] = []
        page: str | None = None
        for _ in range(20):
            p = dict(params)
            if page:
                p["page_token"] = page
            d = await self._get(f"/v1beta1/options/snapshots/{underlying}", **p)
            for occ, snap in (d.get("snapshots") or {}).items():
                row = _normalise(occ, snap, underlying)
                if row:
                    out.append(row)
            page = d.get("next_page_token")
            if not page:
                break
        return out


def _parse_occ(occ: str) -> tuple[str, str, float] | None:
    """AAPL260122P00180000 -> ('2026-01-22', 'PUT', 180.0)"""
    if len(occ) < 15:
        return None
    tail = occ[-15:]
    y, m, d = tail[0:2], tail[2:4], tail[4:6]
    cp = tail[6].upper()
    try:
        strike = int(tail[7:]) / 1000.0
    except ValueError:
        return None
    if cp not in ("C", "P"):
        return None
    return f"20{y}-{m}-{d}", ("CALL" if cp == "C" else "PUT"), strike


def _normalise(occ: str, snap: dict, underlying: str) -> dict | None:
    parsed = _parse_occ(occ)
    if not parsed:
        return None
    exp, right, strike = parsed

    q = snap.get("latestQuote") or {}
    bid, ask = q.get("bp"), q.get("ap")
    if bid is None or ask is None:
        return None
    try:
        bid, ask = float(bid), float(ask)
    except (TypeError, ValueError):
        return None
    if ask <= 0 or bid < 0 or ask < bid:
        return None

    g = snap.get("greeks") or {}
    t = snap.get("latestTrade") or {}
    return {
        "symbol": underlying, "ticker": occ, "expiration": exp,
        "strike": strike, "right": right,
        "bid": bid, "ask": ask, "mid": (bid + ask) / 2.0,
        "delta": float(g["delta"]) if g.get("delta") is not None else None,
        "gamma": float(g["gamma"]) if g.get("gamma") is not None else None,
        "theta": float(g["theta"]) if g.get("theta") is not None else None,
        "vega": float(g["vega"]) if g.get("vega") is not None else None,
        "iv": float(snap["impliedVolatility"]) if snap.get("impliedVolatility") is not None else None,
        "open_interest": int(snap.get("openInterest") or 0),
        "volume": int(t.get("s") or 0),
    }
