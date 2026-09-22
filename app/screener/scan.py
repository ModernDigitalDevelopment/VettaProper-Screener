"""Scan orchestrator: universe -> chains -> candidates -> ranked book.

Every rejected symbol carries a reason. The previous system's biggest failure
mode was silence — it appeared to work while doing nothing. Here, if a scan
returns zero candidates you can see exactly which gate ate them.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Any

from app.core.criteria import Criteria
from app.screener.context import ContextProvider
from app.screener.engine import (build_candidate, event_blackout, select,
                                 trend_ok, vix_ok)
from app.screener.universe import resolve, sector_of

log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    generated_at: str
    criteria: dict[str, Any]
    selected: list[dict]
    all_candidates: list[dict]
    rejections: dict[str, int]
    stats: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


async def run_scan(polygon, criteria: Criteria, today: date | None = None,
                   events: dict[str, list] | None = None,
                   symbols: list[str] | None = None,
                   open_sectors: dict[str, int] | None = None) -> ScanResult:
    t0 = time.time()
    today = today or date.today()
    syms = symbols or resolve(criteria.universe)
    rej: Counter = Counter()
    warnings: list[str] = []

    ctx = ContextProvider(polygon, events=events)

    # 1. trend (skip the fetch entirely when the filter is off)
    if criteria.trend_mode and criteria.trend_mode != "none":
        await ctx.load_trend(syms, today)

    # 2. VIX regime
    vix = await ctx.vix() if (criteria.max_vix or criteria.min_vix) else None
    if not vix_ok(vix, criteria):
        return ScanResult(
            generated_at=today.isoformat(), criteria=criteria.to_dict(),
            selected=[], all_candidates=[], rejections={"vix_regime": len(syms)},
            stats={"vix": vix, "elapsed_s": round(time.time() - t0, 2)},
            warnings=[f"VIX {vix} outside configured regime — no entries today"],
        )

    # 3. pre-filter on cheap gates before spending API calls on chains
    eligible: list[str] = []
    for s in syms:
        reason = event_blackout(s, today, ctx.events, criteria)
        if reason:
            rej[f"event_blackout"] += 1
            continue
        if criteria.trend_mode and criteria.trend_mode != "none":
            if not trend_ok(ctx.trend(s), criteria, criteria.structure):
                rej["trend"] += 1
                continue
        eligible.append(s)

    if not ctx.events:
        warnings.append(
            "No earnings/dividend calendar loaded — the 12-day blackout is NOT "
            "being enforced. This filter was the highest-value one in testing.")

    # 4. chains for survivors
    lo = today + timedelta(days=criteria.target_dte - criteria.dte_tol)
    hi = today + timedelta(days=criteria.target_dte + criteria.dte_tol)
    ctype = {"bull_put": "put", "bear_call": "call"}.get(criteria.structure)

    async def one(sym: str):
        try:
            chain = await polygon.option_chain(sym, expiry_gte=lo, expiry_lte=hi,
                                               contract_type=ctype)
            if not chain:
                return sym, None, "no_chain"
            px = await polygon.last_price(sym)
            cand = build_candidate(sym, sector_of(sym), chain, criteria, today, px)
            return sym, cand, None if cand else "no_valid_spread"
        except Exception as e:
            log.debug("scan %s failed: %s", sym, e)
            return sym, None, "api_error"

    cands = []
    results = await asyncio.gather(*(one(s) for s in eligible))
    for sym, cand, reason in results:
        if cand:
            cands.append(cand)
        else:
            rej[reason or "unknown"] += 1

    # 5. rank + sector cap + sizing
    chosen = select(cands, criteria, open_sectors=open_sectors)

    total_risk = sum(c.total_risk for c in chosen)
    stats = {
        "universe": len(syms),
        "eligible_after_filters": len(eligible),
        "candidates_built": len(cands),
        "selected": len(chosen),
        "total_risk": round(total_risk, 2),
        "total_risk_pct_of_equity": round(100 * total_risk / criteria.equity, 1)
        if criteria.equity else 0,
        "max_profit": round(sum(c.max_profit for c in chosen), 2),
        "vix": vix,
        "elapsed_s": round(time.time() - t0, 2),
    }

    return ScanResult(
        generated_at=today.isoformat(),
        criteria=criteria.to_dict(),
        selected=[c.to_dict() for c in chosen],
        all_candidates=[c.to_dict() for c in sorted(cands, key=lambda x: -x.rank_score)],
        rejections=dict(rej),
        stats=stats,
        warnings=warnings,
    )
