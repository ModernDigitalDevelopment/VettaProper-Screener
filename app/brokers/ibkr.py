"""Interactive Brokers adapter — Client Portal Web API.

READ THIS BEFORE DEPLOYING:

IBKR's Web API is not a plain cloud REST API like Alpaca's. Authenticated
trading requires a session established through the Client Portal Gateway, a
Java process that runs alongside your app and holds the login. For individual
IBKR Pro accounts, OAuth consumer registration (which would remove the gateway
requirement) is generally not available.

Practical consequence for this project:

    Alpaca works from a serverless / static deployment. IBKR does not.

To trade IBKR you must run this app on a host where you can also run the
gateway (a VPS, a container with both processes, or your own machine), and
re-authenticate it periodically — the session expires and IBKR requires a
human 2FA step to re-establish it. There is no way around that from code.

This adapter therefore talks to a gateway URL you supply (IBKR_GATEWAY_URL,
default https://localhost:5000). If the gateway is not reachable or not
authenticated, every call fails loudly rather than silently doing nothing —
that silent-failure pattern is exactly what hid the defects in the previous
system.

Arming: set VPS_IBKR_LIVE=1.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.brokers.base import Broker, OrderRequest, OrderResult, OrderState

log = logging.getLogger(__name__)


class IBKRNotReady(RuntimeError):
    pass


class IBKRBroker(Broker):
    name = "ibkr"
    live_flag_env = "VPS_IBKR_LIVE"

    def __init__(self, gateway_url: str | None = None, account_id: str | None = None,
                 dry_run: bool | None = None, verify_ssl: bool | None = None):
        super().__init__(dry_run=dry_run)
        self.gateway_url = (gateway_url or os.getenv("IBKR_GATEWAY_URL")
                            or "https://localhost:5000").rstrip("/")
        self.account_id = account_id or os.getenv("IBKR_ACCOUNT_ID", "")
        # the gateway ships a self-signed cert by default
        self.verify_ssl = (os.getenv("IBKR_VERIFY_SSL", "0") == "1"
                           if verify_ssl is None else verify_ssl)

    @property
    def configured(self) -> bool:
        return bool(self.gateway_url)

    async def _req(self, method: str, path: str, **kw) -> Any:
        async with httpx.AsyncClient(base_url=self.gateway_url, timeout=20.0,
                                     verify=self.verify_ssl) as cli:
            try:
                r = await cli.request(method, f"/v1/api{path}", **kw)
            except httpx.ConnectError as e:
                raise IBKRNotReady(
                    f"Cannot reach IBKR Client Portal Gateway at {self.gateway_url}. "
                    "The gateway must be running and authenticated. "
                    "See docs/BROKERS.md."
                ) from e
            if r.status_code == 401:
                raise IBKRNotReady(
                    "IBKR gateway reachable but NOT authenticated. Open "
                    f"{self.gateway_url} in a browser and log in (2FA required)."
                )
            r.raise_for_status()
            return r.json() if r.content else {}

    async def auth_status(self) -> dict[str, Any]:
        try:
            d = await self._req("POST", "/iserver/auth/status")
            return {
                "reachable": True,
                "authenticated": bool(d.get("authenticated")),
                "connected": bool(d.get("connected")),
                "competing": bool(d.get("competing")),
                "message": d.get("message", ""),
            }
        except IBKRNotReady as e:
            return {"reachable": False, "authenticated": False, "message": str(e)}

    async def account(self) -> dict[str, Any]:
        st = await self.auth_status()
        if not st.get("authenticated"):
            return {"broker": "ibkr", "armed": False, **st}
        accts = await self._req("GET", "/portfolio/accounts")
        acct = self.account_id or (accts[0]["accountId"] if accts else None)
        summary = await self._req("GET", f"/portfolio/{acct}/summary") if acct else {}
        return {
            "broker": "ibkr",
            "account_id": acct,
            "equity": float((summary.get("netliquidation") or {}).get("amount") or 0),
            "buying_power": float((summary.get("buyingpower") or {}).get("amount") or 0),
            "armed": not self.dry_run,
            **st,
        }

    async def positions(self) -> list[dict[str, Any]]:
        acct = self.account_id
        if not acct:
            accts = await self._req("GET", "/portfolio/accounts")
            acct = accts[0]["accountId"] if accts else None
        if not acct:
            return []
        rows = await self._req("GET", f"/portfolio/{acct}/positions/0")
        return [r for r in rows if r.get("assetClass") == "OPT"]

    async def resolve_conid(self, symbol: str, expiration: str, right: str,
                            strike: float) -> int | None:
        """Map an option leg to an IBKR contract id."""
        secdef = await self._req("GET", "/iserver/secdef/search",
                                 params={"symbol": symbol, "secType": "STK"})
        if not secdef:
            return None
        underlying_conid = secdef[0].get("conid")
        month = expiration[:7].replace("-", "")  # YYYYMM
        info = await self._req("GET", "/iserver/secdef/info", params={
            "conid": underlying_conid, "sectype": "OPT", "month": month,
            "strike": strike, "right": "P" if right.upper().startswith("P") else "C",
        })
        for row in info or []:
            if str(row.get("maturityDate", "")) == expiration.replace("-", ""):
                return int(row["conid"])
        return int(info[0]["conid"]) if info else None

    async def submit(self, req: OrderRequest) -> OrderResult:
        coid = req.client_order_id()
        if self.dry_run:
            return self._dry(req, note="IBKR requires an authenticated gateway")

        st = await self.auth_status()
        if not st.get("authenticated"):
            return OrderResult(OrderState.REJECTED, coid,
                               message=st.get("message", "gateway not authenticated"))

        # IBKR combo orders use a conid list with ratios, e.g. "conid1/-1,conid2/1"
        parts = []
        for l in req.legs:
            conid = l.occ_symbol or await self.resolve_conid(
                l.symbol, l.expiration, l.right, l.strike)
            if not conid:
                return OrderResult(OrderState.REJECTED, coid,
                                   message=f"could not resolve conid for {l.symbol} "
                                           f"{l.expiration} {l.right} {l.strike}")
            sign = -1 if l.action.upper() == "SELL" else 1
            parts.append(f"{conid}/{sign * l.ratio}")
        combo = ",".join(parts)

        acct = self.account_id
        if not acct:
            accts = await self._req("GET", "/portfolio/accounts")
            acct = accts[0]["accountId"] if accts else None

        payload = {"orders": [{
            "conidex": combo,
            "orderType": "LMT",
            "side": "SELL",                      # net credit
            "quantity": req.quantity,
            "price": round(abs(req.limit_price), 2),
            "tif": req.time_in_force.upper(),
            "cOID": coid,
        }]}

        try:
            resp = await self._req("POST", f"/iserver/account/{acct}/orders", json=payload)
        except IBKRNotReady as e:
            return OrderResult(OrderState.REJECTED, coid, message=str(e))
        except Exception as e:
            return OrderResult(OrderState.SENT_UNKNOWN, coid, message=repr(e)[:400])

        first = resp[0] if isinstance(resp, list) and resp else {}
        if "id" in first and "message" in first:
            # IBKR is asking us to confirm a warning; surface it, do not auto-confirm
            return OrderResult(OrderState.SENT_UNKNOWN, coid,
                               message=f"IBKR confirmation required: {first.get('message')}",
                               raw=first)
        return OrderResult(OrderState.ACCEPTED, coid,
                           broker_order_id=str(first.get("order_id") or ""),
                           message="accepted", raw=first)
