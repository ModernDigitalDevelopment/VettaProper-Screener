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
from app.providers.polygon import PolygonClient, PolygonError  # noqa: E402
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
        "polygon_configured": bool(os.getenv("POLYGON_API_KEY")),
        "alpaca_configured": bool(os.getenv("APCA_API_KEY_ID")),
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

    try:
        async with PolygonClient() as poly:
            result = await run_scan(poly, crit, today=date.today(),
                                    events=load_events(), symbols=req.symbols)
    except PolygonError as e:
        raise HTTPException(503, str(e))
    return JSONResponse(result.to_dict())


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
    p = ROOT / "backtest" / "results" / "summary.json"
    if not p.exists():
        raise HTTPException(404, "no backtest results bundled")
    return json.loads(p.read_text())


@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import FileResponse
    return FileResponse(WEB / "static" / "favicon.ico")
