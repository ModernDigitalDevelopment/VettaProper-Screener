"""Alpaca adapter — multi-leg options via the mleg order class.

Alpaca supports native multi-leg options orders (up to 4 legs) on paper and
live, provided the account has the appropriate options trading level. A credit
spread submits as ONE order, which is what you want: no legging risk.

Arming: set VPS_ALPACA_LIVE=1. Without it every submit is a dry run.
Paper vs live is chosen by APCA_API_BASE_URL.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.brokers.base import (Broker, OrderRequest, OrderResult, OrderState,
                              occ_symbol)

log = logging.getLogger(__name__)

PAPER_URL = "https://paper-api.alpaca.markets"


class AlpacaBroker(Broker):
    name = "alpaca"
    live_flag_env = "VPS_ALPACA_LIVE"

    def __init__(self, key: str | None = None, secret: str | None = None,
                 base_url: str | None = None, dry_run: bool | None = None):
        super().__init__(dry_run=dry_run)
        self.key = key or os.getenv("APCA_API_KEY_ID", "")
        self.secret = secret or os.getenv("APCA_API_SECRET_KEY", "")
        self.base_url = (base_url or os.getenv("APCA_API_BASE_URL") or PAPER_URL).rstrip("/")
        self.is_paper = "paper" in self.base_url

    @property
    def configured(self) -> bool:
        return bool(self.key and self.secret)

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.key,
            "APCA-API-SECRET-KEY": self.secret,
            "Content-Type": "application/json",
        }

    async def _req(self, method: str, path: str, **kw) -> Any:
        if not self.configured:
            raise RuntimeError("Alpaca keys not configured (APCA_API_KEY_ID / APCA_API_SECRET_KEY)")
        async with httpx.AsyncClient(base_url=self.base_url, timeout=20.0,
                                     headers=self._headers()) as cli:
            r = await cli.request(method, path, **kw)
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"{r.status_code}: {r.text[:400]}", request=r.request, response=r)
            return r.json() if r.content else {}

    async def account(self) -> dict[str, Any]:
        a = await self._req("GET", "/v2/account")
        return {
            "broker": "alpaca",
            "paper": self.is_paper,
            "account_number": a.get("account_number"),
            "equity": float(a.get("equity") or 0),
            "buying_power": float(a.get("buying_power") or 0),
            "options_level": a.get("options_trading_level"),
            "status": a.get("status"),
            "armed": not self.dry_run,
        }

    async def positions(self) -> list[dict[str, Any]]:
        rows = await self._req("GET", "/v2/positions")
        return [r for r in rows if (r.get("asset_class") == "us_option"
                                    or len(r.get("symbol", "")) > 10)]

    async def submit(self, req: OrderRequest) -> OrderResult:
        coid = req.client_order_id()
        legs = []
        for l in req.legs:
            legs.append({
                "symbol": l.occ_symbol or occ_symbol(l.symbol, l.expiration, l.right, l.strike),
                "side": "sell" if l.action.upper() == "SELL" else "buy",
                "ratio_qty": str(l.ratio),
                "position_intent": ("sell_to_open" if l.action.upper() == "SELL"
                                    else "buy_to_open"),
            })

        # Credit spread: we RECEIVE money, so the net limit is submitted as a
        # negative price on a sell-side mleg order in Alpaca's convention.
        payload = {
            "order_class": "mleg",
            "qty": str(req.quantity),
            "type": "limit",
            "limit_price": str(round(abs(req.limit_price), 2)),
            "time_in_force": req.time_in_force,
            "client_order_id": coid,
            "legs": legs,
        }

        if self.dry_run:
            return self._dry(req, note=f"{len(legs)} legs, paper={self.is_paper}")

        try:
            resp = await self._req("POST", "/v2/orders", json=payload)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else 0
            if code and 400 <= code < 500:
                # broker refused it — definitively not working
                return OrderResult(OrderState.REJECTED, coid, message=str(e)[:400])
            return OrderResult(OrderState.SENT_UNKNOWN, coid, message=str(e)[:400])
        except Exception as e:
            # request may or may not have landed — never auto-retry this
            return OrderResult(OrderState.SENT_UNKNOWN, coid, message=repr(e)[:400])

        return OrderResult(OrderState.ACCEPTED, coid,
                           broker_order_id=resp.get("id"),
                           message="accepted", raw=resp)
