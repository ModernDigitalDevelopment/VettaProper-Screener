"""Vetta Proper Screener — FastAPI application."""
from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("vps")

from app.brokers.alpaca import AlpacaBroker          # noqa: E402
from app.brokers.base import OrderLeg, OrderRequest  # noqa: E402
from app.brokers.ibkr import IBKRBroker              # noqa: E402
from app.core.criteria import Criteria, PRESETS      # noqa: E402
from app.providers import factory                   # noqa: E402
from app.providers.polygon import PolygonError       # noqa: E402
from app.screener.events import load_events          # noqa: E402
from app.screener.scan import run_scan               # noqa: E402
from app.screener.universe import UNIVERSES, resolve, sector_of  # noqa: E402

ROOT = Path(__file__).parent.parent
WEB = ROOT / "web"

app = FastAPI(title="Vetta Proper Screener", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
if (WEB / "static").exists():
    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    criteria: dict[str, Any] | None = None
    preset: str | None = None
    symbols: list[str] | None = None
    provider: str | None = None        # polygon | alpaca | ibkr
    # sector -> count of positions ALREADY open, so caps apply against the
    # live book and not just today's entries. Get it from /api/reconcile.
    open_sectors: dict[str, int] | None = None


class OrderSubmit(BaseModel):
    broker: str                 # alpaca | ibkr
    symbol: str
    structure: str
    quantity: int
    limit_price: float
    legs: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

def _page(name: str) -> HTMLResponse:
    p = WEB / "templates" / name
    if not p.exists():
        raise HTTPException(404, f"{name} not found")
    return HTMLResponse(p.read_text())


@app.get("/", response_class=HTMLResponse)
async def index():
    return _page("index.html")


@app.get("/research", response_class=HTMLResponse)
async def research():
    return _page("research.html")


# ---------------------------------------------------------------------------
# api
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "data_provider": os.getenv("DATA_PROVIDER", "polygon"),
        "polygon_configured": bool(os.getenv("POLYGON_API_KEY")),
        "alpaca_configured": bool(os.getenv("APCA_API_KEY_ID")),
        "ibkr_configured": bool(os.getenv("IBKR_GATEWAY_URL")),
        "alpaca_armed": os.getenv("VPS_ALPACA_LIVE") == "1",
        "ibkr_armed": os.getenv("VPS_IBKR_LIVE") == "1",
    }


@app.get("/api/criteria/defaults")
async def criteria_defaults():
    return {
        "defaults": Criteria().to_dict(),
        "presets": PRESETS,
        "universes": UNIVERSES,
    }


@app.get("/api/universe")
async def universe():
    syms = resolve(None)
    return {"count": len(syms),
            "symbols": [{"symbol": s, "sector": sector_of(s)} for s in syms]}


@app.post("/api/scan")
async def scan(req: ScanRequest):
    if req.preset:
        if req.preset not in PRESETS:
            raise HTTPException(400, f"unknown preset {req.preset}")
        base = dict(PRESETS[req.preset]["criteria"])
        base.update(req.criteria or {})
        crit = Criteria.from_dict(base)
    else:
        crit = Criteria.from_dict(req.criteria or {})

    name = req.provider or os.getenv("DATA_PROVIDER", "polygon")
    if name == "ibkr" and not req.symbols:
        raise HTTPException(
            400,
            "IBKR has no bulk chain endpoint — scanning the full universe would "
            "take thousands of calls. Pass an explicit `symbols` watchlist, or "
            "use polygon/alpaca for full scans. See docs/BROKERS.md.")
    try:
        async with factory.make(name) as data:
            result = await run_scan(data, crit, today=date.today(),
                                    events=load_events(), symbols=req.symbols,
                                    open_sectors=req.open_sectors)
    except (PolygonError, RuntimeError) as e:
        raise HTTPException(503, str(e))
    result.stats["provider"] = name
    return JSONResponse(result.to_dict())


@app.get("/api/providers")
async def providers():
    return {"active": os.getenv("DATA_PROVIDER", "polygon"),
            "providers": factory.available()}


def _broker(name: str):
    if name == "alpaca":
        return AlpacaBroker()
    if name == "ibkr":
        return IBKRBroker()
    raise HTTPException(400, f"unknown broker {name!r}")


@app.get("/api/broker/{name}/account")
async def broker_account(name: str):
    b = _broker(name)
    try:
        return await b.account()
    except Exception as e:
        return JSONResponse({"broker": name, "error": str(e)[:400],
                             "armed": not b.dry_run}, status_code=200)


@app.get("/api/broker/{name}/positions")
async def broker_positions(name: str):
    b = _broker(name)
    try:
        return {"positions": await b.positions()}
    except Exception as e:
        raise HTTPException(503, str(e)[:400])


@app.post("/api/order")
async def submit_order(o: OrderSubmit):
    b = _broker(o.broker)
    legs = [OrderLeg(action=l["action"], right=l["right"], strike=float(l["strike"]),
                     expiration=l["expiration"], symbol=o.symbol,
                     ratio=int(l.get("ratio", 1)))
            for l in o.legs]
    req = OrderRequest(symbol=o.symbol, legs=legs, quantity=o.quantity,
                       limit_price=o.limit_price, structure=o.structure)
    res = await b.submit(req)
    return res.to_dict()


@app.get("/api/backtest/results")
async def backtest_results():
    import json
    p = ROOT / "backtest" / "results" / "screener_runs.json"
    if not p.exists():
        raise HTTPException(404, "no backtest results bundled")
    return json.loads(p.read_text())


# ---------------------------------------------------------------------------
# IBKR session management
#
# The gateway session expires and needs a human 2FA step to renew. These
# endpoints make that state visible instead of letting scans fail mysteriously.
# ---------------------------------------------------------------------------

@app.get("/api/ibkr/status")
async def ibkr_status():
    from app.brokers.ibkr import IBKRBroker
    b = IBKRBroker()
    st = await b.auth_status()
    st["gateway_url"] = b.gateway_url
    st["armed"] = not b.dry_run
    if not st.get("reachable"):
        st["remedy"] = ("Start the Client Portal Gateway: ./bin/run.sh root/conf.yaml, "
                        "then open it in a browser and log in.")
    elif not st.get("authenticated"):
        st["remedy"] = f"Open {b.gateway_url} in a browser and log in (2FA required)."
    return st


@app.post("/api/ibkr/keepalive")
async def ibkr_keepalive():
    """Ping the gateway. Call every few minutes to hold the session open."""
    from app.providers.ibkr_data import IBKRDataClient
    c = IBKRDataClient()
    import httpx
    try:
        async with httpx.AsyncClient(base_url=f"{c.gateway_url}/v1/api",
                                     timeout=10.0, verify=c.verify_ssl) as cli:
            r = await cli.post("/tickle")
            ok = r.status_code == 200
            body = r.json() if ok and r.content else {}
        return {"ok": ok,
                "session": body.get("session"),
                "authenticated": (body.get("iserver") or {})
                                 .get("authStatus", {}).get("authenticated")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/reconcile/{broker_name}")
async def reconcile(broker_name: str):
    """Compare what the broker holds against what we think we hold.

    The predecessor system's dashboard showed positions that did not exist.
    This endpoint exists so that can never be true here silently.
    """
    b = _broker(broker_name)
    try:
        pos = await b.positions()
    except Exception as e:
        return {"broker": broker_name, "error": str(e)[:400],
                "broker_positions": None}
    by_sector: dict[str, int] = {}
    for p in pos:
        sym = (p.get("symbol") or p.get("ticker") or "")[:6].strip()
        s = sector_of(sym)
        by_sector[s] = by_sector.get(s, 0) + 1
    return {
        "broker": broker_name,
        "position_count": len(pos),
        "by_sector": by_sector,
        "positions": pos,
        "note": "Feed by_sector into /api/scan as open_sectors to respect "
                "per-sector caps against positions you already hold.",
    }


@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import FileResponse
    return FileResponse(WEB / "static" / "favicon.ico")
