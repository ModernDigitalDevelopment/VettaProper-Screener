"""Broker abstraction.

One interface, two implementations (Alpaca, IBKR). The screener never talks to
a broker directly — it emits an OrderRequest and the adapter translates.

Safety model, carried over from the audit of the previous system:
  * Every adapter starts in DRY_RUN. Live submission requires an explicit
    environment flag per broker. There is no "enable trading" checkbox in the
    UI, on purpose.
  * Every order carries a deterministic client_order_id (SHA-256 of the
    economic terms). Resubmitting the same spread on the same day cannot
    double-fill.
  * submit() returns SENT_UNKNOWN rather than raising if the network call
    fails after the request left the process. An ambiguous send is NOT a
    failure and must never be blindly retried.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import date
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class OrderState(str, Enum):
    DRY_RUN = "DRY_RUN"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SENT_UNKNOWN = "SENT_UNKNOWN"     # left the process, outcome unconfirmed
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


@dataclass
class OrderLeg:
    action: str          # SELL | BUY
    right: str           # PUT | CALL
    strike: float
    expiration: str      # YYYY-MM-DD
    symbol: str
    ratio: int = 1
    occ_symbol: str | None = None


@dataclass
class OrderRequest:
    symbol: str
    legs: list[OrderLeg]
    quantity: int
    limit_price: float           # net credit, positive = we receive
    structure: str = "bull_put"
    time_in_force: str = "day"
    account: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def client_order_id(self, trade_date: date | None = None) -> str:
        """Deterministic id — same economic order on same day = same id."""
        d = (trade_date or date.today()).isoformat()
        payload = {
            "d": d, "s": self.symbol, "q": self.quantity,
            "p": round(self.limit_price, 2), "st": self.structure,
            "legs": sorted(
                [[l.action, l.right, l.strike, l.expiration, l.ratio] for l in self.legs],
                key=lambda x: (x[1], x[2]),
            ),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "vps-" + hashlib.sha256(raw.encode()).hexdigest()[:24]


@dataclass
class OrderResult:
    state: OrderState
    client_order_id: str
    broker_order_id: str | None = None
    message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        d["state"] = self.state.value
        return d


def occ_symbol(underlying: str, expiration: str, right: str, strike: float) -> str:
    """OCC-21: AAPL  260122P00180000"""
    y, m, dd = expiration[2:4], expiration[5:7], expiration[8:10]
    cp = "C" if right.upper().startswith("C") else "P"
    mills = int(round(float(strike) * 1000))
    return f"{underlying.upper():<6}".replace(" ", "") + f"{y}{m}{dd}{cp}{mills:08d}"


class Broker(ABC):
    name: str = "base"
    #: env var that must equal "1" for this adapter to place real orders
    live_flag_env: str = "VPS_NEVER_LIVE"

    def __init__(self, dry_run: bool | None = None):
        env_live = os.getenv(self.live_flag_env, "0") == "1"
        self.dry_run = (not env_live) if dry_run is None else dry_run
        if not self.dry_run:
            log.warning("%s adapter is LIVE (%s=1)", self.name, self.live_flag_env)

    @abstractmethod
    async def account(self) -> dict[str, Any]: ...

    @abstractmethod
    async def positions(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def submit(self, req: OrderRequest) -> OrderResult: ...

    def _dry(self, req: OrderRequest, note: str = "") -> OrderResult:
        coid = req.client_order_id()
        msg = f"DRY RUN — not sent. Set {self.live_flag_env}=1 to arm."
        if note:
            msg += f" ({note})"
        log.info("[%s] %s %s x%d @ %.2f -> %s",
                 self.name, req.structure, req.symbol, req.quantity,
                 req.limit_price, msg)
        return OrderResult(OrderState.DRY_RUN, coid, message=msg,
                           raw={"request": asdict(req)})
