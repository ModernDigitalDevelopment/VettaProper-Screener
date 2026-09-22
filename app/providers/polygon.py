"""Polygon.io (now branded 'Massive') market data provider.

Uses the options chain snapshot endpoint, which returns, per contract, in one
call: bid, ask, greeks (incl. delta), IV, open interest and volume. That is
everything the screener needs to build and rank a spread.

    GET /v3/snapshot/options/{underlying}

Rate limits depend on plan. Options Starter is real-time but throttled;
Developer/Advanced raise the ceiling. The client below is async with a
semaphore so you can tune concurrency to your plan without code changes.

API key is read from POLYGON_API_KEY and is NEVER sent to the browser.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime
from typing import Any

import httpx

log = logging.getLogger(__name__)

BASE_URL = os.getenv("POLYGON_BASE_URL", "https://api.polygon.io")


class PolygonError(RuntimeError):
    pass


class PolygonClient:
    def __init__(self, api_key: str | None = None, max_concurrency: int = 8,
                 timeout: float = 20.0):
        self.api_key = api_key or os.getenv("POLYGON_API_KEY", "")
        if not self.api_key:
            raise PolygonError(
                "POLYGON_API_KEY is not set. Put it in .env (never in the frontend)."
            )
        self._sem = asyncio.Semaphore(max_concurrency)
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=BASE_URL, timeout=self._timeout,
            headers={"Authorization": f"Bearer {self.api_key}"},
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
                    wait = 2 ** attempt
                    log.warning("polygon 429, backing off %ss", wait)
                    await asyncio.sleep(wait)
                    continue
                if r.status_code == 403:
                    raise PolygonError(
                        "Polygon returned 403. Your plan may not include real-time "
                        "options data (options snapshots require a paid options plan)."
                    )
                r.raise_for_status()
                return r.json()
        raise PolygonError(f"rate limited repeatedly on {path}")

    # ---- market status ---------------------------------------------------
    async def market_open(self) -> bool:
        try:
            d = await self._get("/v1/marketstatus/now")
            return d.get("market") == "open"
        except Exception:
            return False

    # ---- underlying ------------------------------------------------------
    async def daily_bars(self, symbol: str, start: date, end: date) -> list[dict]:
        """Daily OHLC for trend filters (SMA10/30/50)."""
        d = await self._get(
            f"/v2/aggs/ticker/{symbol}/range/1/day/{start:%Y-%m-%d}/{end:%Y-%m-%d}",
            adjusted="true", sort="asc", limit=50000,
        )
        out = []
        for b in d.get("results", []) or []:
            out.append({
                "date": datetime.utcfromtimestamp(b["t"] / 1000).date().isoformat(),
                "open": b["o"], "high": b["h"], "low": b["l"],
                "close": b["c"], "volume": b.get("v", 0),
            })
        return out

    async def last_price(self, symbol: str) -> float | None:
        try:
            d = await self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
            t = d.get("ticker") or {}
            for k in ("lastTrade", "day", "prevDay"):
                v = (t.get(k) or {}).get("p") or (t.get(k) or {}).get("c")
                if v:
                    return float(v)
        except Exception as e:
            log.debug("last_price %s failed: %s", symbol, e)
        return None

    # ---- options ---------------------------------------------------------
    async def option_chain(self, underlying: str, expiry_gte: date | None = None,
                           expiry_lte: date | None = None,
                           contract_type: str | None = None) -> list[dict]:
        """Full chain snapshot: quotes + greeks + OI in one pass (paginated)."""
        params: dict[str, Any] = {"limit": 250}
        if expiry_gte:
            params["expiration_date.gte"] = expiry_gte.isoformat()
        if expiry_lte:
            params["expiration_date.lte"] = expiry_lte.isoformat()
        if contract_type:
            params["contract_type"] = contract_type

        out: list[dict] = []
        path = f"/v3/snapshot/options/{underlying}"
        cursor = None
        for _ in range(40):                       # hard page cap
            p = dict(params)
            if cursor:
                p["cursor"] = cursor
            d = await self._get(path, **p)
            for c in d.get("results", []) or []:
                row = _normalise_contract(c, underlying)
                if row:
                    out.append(row)
            nxt = d.get("next_url")
            if not nxt:
                break
            cursor = nxt.split("cursor=")[-1].split("&")[0]
        return out


def _normalise_contract(c: dict, underlying: str) -> dict | None:
    det = c.get("details") or {}
    q = c.get("last_quote") or {}
    g = c.get("greeks") or {}
    day = c.get("day") or {}

    bid, ask = q.get("bid"), q.get("ask")
    if bid is None or ask is None:
        return None
    try:
        bid, ask = float(bid), float(ask)
    except (TypeError, ValueError):
        return None
    if ask <= 0 or bid < 0 or ask < bid:
        return None

    strike = det.get("strike_price")
    exp = det.get("expiration_date")
    ctype = (det.get("contract_type") or "").upper()
    if strike is None or not exp or ctype not in ("CALL", "PUT"):
        return None

    return {
        "symbol": underlying,
        "ticker": det.get("ticker"),
        "expiration": exp,
        "strike": float(strike),
        "right": ctype,
        "bid": bid,
        "ask": ask,
        "mid": (bid + ask) / 2.0,
        "delta": float(g["delta"]) if g.get("delta") is not None else None,
        "gamma": float(g["gamma"]) if g.get("gamma") is not None else None,
        "theta": float(g["theta"]) if g.get("theta") is not None else None,
        "vega": float(g["vega"]) if g.get("vega") is not None else None,
        "iv": float(c["implied_volatility"]) if c.get("implied_volatility") is not None else None,
        "open_interest": int(c.get("open_interest") or 0),
        "volume": int(day.get("volume") or 0),
    }
