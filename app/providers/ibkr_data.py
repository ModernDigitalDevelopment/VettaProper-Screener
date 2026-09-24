"""IBKR market data provider — Client Portal Web API.

Implements the same interface as PolygonClient so the screener can run against
either without code changes:

    option_chain(underlying, expiry_gte, expiry_lte, contract_type) -> list[dict]
    daily_bars(symbol, start, end) -> list[dict]
    last_price(symbol) -> float | None
    market_open() -> bool

IMPORTANT DIFFERENCES FROM POLYGON — read before relying on this:

1. No bulk chain snapshot. Polygon returns a whole chain in one call. IBKR
   requires: resolve underlying conid -> list strikes for a month -> resolve
   each strike to a conid -> request market data per conid. For a 365-symbol
   universe that is thousands of calls per scan.

2. Market data is streaming-first. The REST /iserver/marketdata/snapshot
   endpoint primes a subscription; the FIRST call for a contract often returns
   empty and must be repeated. This is documented IBKR behaviour, not a bug.
   _snapshot_with_priming() handles it.

3. Greeks require a market data subscription. Fields 7308 (delta) etc. return
   nothing without the relevant options data subscription on the account.

4. Rate limits are strict and enforced by disconnection rather than 429s.
   Default concurrency here is deliberately low.

PRACTICAL GUIDANCE: use Polygon for scanning the full universe and IBKR for
execution and account state. Use IBKR data when you want quotes from the venue
you are actually trading on, or on a reduced watchlist.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any

import httpx

log = logging.getLogger(__name__)

# IBKR market data field codes
F_LAST = "31"
F_BID = "84"
F_ASK = "86"
F_VOLUME = "87"
F_OPEN_INTEREST = "7638"
F_IMPLIED_VOL = "7633"
F_DELTA = "7308"
F_GAMMA = "7309"
F_VEGA = "7310"
F_THETA = "7311"
F_UNDERLYING = "7639"

OPT_FIELDS = ",".join([F_BID, F_ASK, F_LAST, F_VOLUME, F_OPEN_INTEREST,
                       F_IMPLIED_VOL, F_DELTA, F_GAMMA, F_VEGA, F_THETA])


class IBKRDataError(RuntimeError):
    pass


class IBKRNotAuthenticated(IBKRDataError):
    pass


def _f(v: Any) -> float | None:
    """IBKR returns numbers as strings, sometimes prefixed with C/H markers."""
    if v is None:
        return None
    s = str(v).strip()
    # IBKR prefixes some values: 'C' = previous close, 'H' = halted
    for pfx in ("C", "H"):
        if s.startswith(pfx):
            s = s[1:]
    s = s.replace(",", "")
    if not s or s in ("-", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


class IBKRDataClient:
    """Market data via the IBKR Client Portal Gateway."""

    def __init__(self, gateway_url: str | None = None, max_concurrency: int = 4,
                 timeout: float = 20.0, verify_ssl: bool | None = None):
        self.gateway_url = (gateway_url or os.getenv("IBKR_GATEWAY_URL")
                            or "https://localhost:5000").rstrip("/")
        self.verify_ssl = (os.getenv("IBKR_VERIFY_SSL", "0") == "1"
                           if verify_ssl is None else verify_ssl)
        self._sem = asyncio.Semaphore(max_concurrency)
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._conid_cache: dict[str, int] = {}

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=f"{self.gateway_url}/v1/api",
            timeout=self._timeout, verify=self.verify_ssl,
        )
        st = await self.auth_status()
        if not st.get("authenticated"):
            raise IBKRNotAuthenticated(st.get("message", "gateway not authenticated"))
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.aclose()

    async def _get(self, path: str, **params) -> Any:
        assert self._client, "use as async context manager"
        async with self._sem:
            try:
                r = await self._client.get(path, params=params)
            except httpx.ConnectError as e:
                raise IBKRDataError(
                    f"Cannot reach IBKR gateway at {self.gateway_url}. "
                    "It must be running and authenticated. See docs/BROKERS.md."
                ) from e
            if r.status_code == 401:
                raise IBKRNotAuthenticated("IBKR session expired — log in again.")
            r.raise_for_status()
            return r.json() if r.content else {}

    async def auth_status(self) -> dict[str, Any]:
        assert self._client
        try:
            r = await self._client.post("/iserver/auth/status")
            if r.status_code == 401:
                return {"reachable": True, "authenticated": False,
                        "message": "not authenticated — log in at the gateway"}
            r.raise_for_status()
            d = r.json()
            return {"reachable": True,
                    "authenticated": bool(d.get("authenticated")),
                    "connected": bool(d.get("connected")),
                    "competing": bool(d.get("competing")),
                    "message": d.get("message", "")}
        except httpx.ConnectError:
            return {"reachable": False, "authenticated": False,
                    "message": f"gateway unreachable at {self.gateway_url}"}

    async def keepalive(self) -> bool:
        """Ping to keep the brokerage session from timing out."""
        assert self._client
        try:
            r = await self._client.post("/tickle")
            return r.status_code == 200
        except Exception:
            return False

    async def market_open(self) -> bool:
        try:
            d = await self._get("/iserver/marketdata/snapshot",
                                conids="265598", fields=F_LAST)  # AAPL probe
            return bool(d)
        except Exception:
            return False

    # ---- contract resolution --------------------------------------------

    async def underlying_conid(self, symbol: str) -> int | None:
        if symbol in self._conid_cache:
            return self._conid_cache[symbol]
        rows = await self._get("/iserver/secdef/search", symbol=symbol, secType="STK")
        for row in rows or []:
            if (row.get("symbol") or "").upper() == symbol.upper():
                cid = int(row["conid"])
                self._conid_cache[symbol] = cid
                return cid
        if rows:
            cid = int(rows[0]["conid"])
            self._conid_cache[symbol] = cid
            return cid
        return None

    async def option_strikes(self, conid: int, month: str,
                             exchange: str = "SMART") -> dict[str, list[float]]:
        """month is YYYYMM -> {'call': [...], 'put': [...]}"""
        d = await self._get("/iserver/secdef/strikes", conid=str(conid),
                            sectype="OPT", month=month, exchange=exchange)
        return {"call": [float(x) for x in (d.get("call") or [])],
                "put": [float(x) for x in (d.get("put") or [])]}

    async def option_conid(self, underlying_conid: int, month: str, strike: float,
                           right: str, expiration: str) -> int | None:
        rows = await self._get("/iserver/secdef/info", conid=str(underlying_conid),
                               sectype="OPT", month=month, strike=str(strike),
                               right="P" if right.upper().startswith("P") else "C")
        target = expiration.replace("-", "")
        for row in rows or []:
            if str(row.get("maturityDate", "")) == target:
                return int(row["conid"])
        return None

    # ---- market data -----------------------------------------------------

    async def _snapshot_with_priming(self, conids: list[int], fields: str,
                                     attempts: int = 3,
                                     delay: float = 1.2) -> dict[int, dict]:
        """IBKR's first snapshot call primes the subscription and may be empty.

        This is expected behaviour, not an error. We poll until fields appear.
        """
        want = set(conids)
        out: dict[int, dict] = {}
        for i in range(attempts):
            rows = await self._get("/iserver/marketdata/snapshot",
                                   conids=",".join(str(c) for c in conids),
                                   fields=fields)
            for row in rows or []:
                cid = int(row.get("conid") or 0)
                if cid and (F_BID in row or F_LAST in row):
                    out[cid] = row
            if want <= set(out):
                break
            if i < attempts - 1:
                await asyncio.sleep(delay)
        return out

    async def last_price(self, symbol: str) -> float | None:
        cid = await self.underlying_conid(symbol)
        if not cid:
            return None
        snap = await self._snapshot_with_priming([cid], F_LAST)
        row = snap.get(cid) or {}
        return _f(row.get(F_LAST))

    async def daily_bars(self, symbol: str, start: date, end: date) -> list[dict]:
        cid = await self.underlying_conid(symbol)
        if not cid:
            return []
        days = max((end - start).days, 1)
        period = f"{min(days, 365)}d"
        d = await self._get("/iserver/marketdata/history", conid=str(cid),
                            period=period, bar="1d", outsideRth="false")
        out = []
        for b in d.get("data", []) or []:
            ts = datetime.utcfromtimestamp(b["t"] / 1000).date()
            if start <= ts <= end:
                out.append({"date": ts.isoformat(), "open": b.get("o"),
                            "high": b.get("h"), "low": b.get("l"),
                            "close": b.get("c"), "volume": b.get("v", 0)})
        out.sort(key=lambda x: x["date"])
        return out

    async def option_chain(self, underlying: str, expiry_gte: date | None = None,
                           expiry_lte: date | None = None,
                           contract_type: str | None = None,
                           strike_window_pct: float = 0.18,
                           max_strikes: int = 24) -> list[dict]:
        """Build a chain slice.

        Unlike Polygon this cannot fetch a full chain cheaply, so it fetches a
        window around spot — which is all a delta-targeted screener needs.
        """
        ucid = await self.underlying_conid(underlying)
        if not ucid:
            return []
        spot = await self.last_price(underlying)
        if not spot:
            return []

        expiry_gte = expiry_gte or date.today()
        expiry_lte = expiry_lte or (expiry_gte + timedelta(days=21))

        months = sorted({d.strftime("%Y%m") for d in (expiry_gte, expiry_lte)})
        rights = ([contract_type.upper()[:4]] if contract_type
                  else ["PUT", "CALL"])
        rights = ["PUT" if r.startswith("P") else "CALL" for r in rights]

        lo, hi = spot * (1 - strike_window_pct), spot * (1 + strike_window_pct)

        # 1. candidate (expiration, strike, right) triples
        wanted: list[tuple[str, float, str]] = []
        for month in months:
            try:
                strikes = await self.option_strikes(ucid, month)
            except Exception as e:
                log.debug("strikes %s %s failed: %s", underlying, month, e)
                continue
            for right in rights:
                key = "put" if right == "PUT" else "call"
                inwin = [s for s in strikes.get(key, []) if lo <= s <= hi]
                inwin.sort(key=lambda s: abs(s - spot))
                for s in inwin[:max_strikes]:
                    wanted.append((month, s, right))

        if not wanted:
            return []

        # 2. resolve conids (this is the expensive part)
        async def resolve(month: str, strike: float, right: str):
            try:
                rows = await self._get("/iserver/secdef/info", conid=str(ucid),
                                       sectype="OPT", month=month,
                                       strike=str(strike),
                                       right="P" if right == "PUT" else "C")
            except Exception:
                return []
            out = []
            for row in rows or []:
                md = str(row.get("maturityDate") or "")
                if len(md) != 8:
                    continue
                exp = f"{md[:4]}-{md[4:6]}-{md[6:]}"
                ed = datetime.strptime(exp, "%Y-%m-%d").date()
                if expiry_gte <= ed <= expiry_lte:
                    out.append((int(row["conid"]), exp, strike, right))
            return out

        resolved: list[tuple[int, str, float, str]] = []
        for batch in _chunks(wanted, 8):
            for group in await asyncio.gather(*(resolve(*w) for w in batch)):
                resolved.extend(group)
        if not resolved:
            return []

        # 3. quotes + greeks, batched
        meta = {cid: (exp, strike, right) for cid, exp, strike, right in resolved}
        quotes: dict[int, dict] = {}
        for batch in _chunks([c for c, *_ in resolved], 20):
            quotes.update(await self._snapshot_with_priming(batch, OPT_FIELDS))

        # 4. normalise to the Polygon row shape
        out = []
        for cid, row in quotes.items():
            exp, strike, right = meta[cid]
            bid, ask = _f(row.get(F_BID)), _f(row.get(F_ASK))
            if bid is None or ask is None or ask <= 0 or ask < bid:
                continue
            delta = _f(row.get(F_DELTA))
            out.append({
                "symbol": underlying, "ticker": str(cid), "conid": cid,
                "expiration": exp, "strike": float(strike), "right": right,
                "bid": bid, "ask": ask, "mid": (bid + ask) / 2.0,
                "delta": delta,
                "gamma": _f(row.get(F_GAMMA)), "theta": _f(row.get(F_THETA)),
                "vega": _f(row.get(F_VEGA)), "iv": _f(row.get(F_IMPLIED_VOL)),
                "open_interest": int(_f(row.get(F_OPEN_INTEREST)) or 0),
                "volume": int(_f(row.get(F_VOLUME)) or 0),
            })
        return out


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
