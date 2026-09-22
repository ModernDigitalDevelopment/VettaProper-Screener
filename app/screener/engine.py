"""Live screener.

CRITICAL: the gate order here is identical to the backtest engine
(backtest/engine/spec_engine.py). If you change one, change both, or live
results stop matching tested results. The parity test in tests/ enforces this.

Gate order:
    IV/RV (optional, off) -> VIX regime -> earnings/ex-div blackout
    -> trend -> expiry window -> short leg (delta + liquidity)
    -> long leg (width) -> credit -> max-loss sanity -> risk:reward
    -> rank -> sector cap -> sizing
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Iterable

from app.core.criteria import Criteria
from app.core.ranking import score as rank_key, explain

log = logging.getLogger(__name__)


@dataclass
class Leg:
    action: str          # SELL | BUY
    right: str           # PUT | CALL
    strike: float
    expiration: str
    ticker: str | None = None
    bid: float = 0.0
    ask: float = 0.0
    delta: float | None = None

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


@dataclass
class Candidate:
    symbol: str
    sector: str
    structure: str
    expiration: str
    dte: int
    legs: list[Leg]
    credit: float
    width: float
    short_delta: float
    underlying_price: float | None = None

    # populated by rank()
    rank_score: float = 0.0
    rank_explanation: str = ""

    # populated by size()
    contracts: int = 0
    max_loss_per_contract: float = 0.0
    total_risk: float = 0.0
    max_profit: float = 0.0
    commission: float = 0.0

    notes: list[str] = field(default_factory=list)

    @property
    def risk_reward(self) -> float:
        r = self.width - self.credit
        return self.credit / r if r > 0 else 0.0

    @property
    def return_on_risk(self) -> float:
        return self.risk_reward

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["risk_reward"] = round(self.risk_reward, 4)
        d["breakeven"] = self.breakeven()
        return d

    def breakeven(self) -> float | None:
        shorts = [l for l in self.legs if l.action == "SELL"]
        if not shorts:
            return None
        s = shorts[0]
        return (s.strike - self.credit) if s.right == "PUT" else (s.strike + self.credit)


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------

def _rel_spread(bid: float, ask: float) -> float:
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 9.99
    return (ask - bid) / mid


def passes_liquidity(row: dict, c: Criteria) -> bool:
    if _rel_spread(row["bid"], row["ask"]) > c.max_rel_spread:
        return False
    if row.get("open_interest", 0) < c.min_open_interest:
        return False
    if c.min_volume and row.get("volume", 0) < c.min_volume:
        return False
    return True


def event_blackout(symbol: str, today: date, events: dict[str, list], c: Criteria) -> str | None:
    """Return a reason string if blacked out, else None."""
    if not c.earnings_blackout_days:
        return None
    types = {"EARNINGS", "EX_DIV"} if c.blackout_exdiv else {"EARNINGS"}
    horizon = c.earnings_blackout_days
    for ev_date, ev_type in events.get(symbol, []):
        if ev_type not in types:
            continue
        d = ev_date if isinstance(ev_date, date) else datetime.strptime(str(ev_date)[:10], "%Y-%m-%d").date()
        delta_days = (d - today).days
        if 0 <= delta_days <= horizon:
            return f"{ev_type} in {delta_days}d"
    return None


def trend_ok(bars: dict[str, float] | None, c: Criteria, structure: str) -> bool:
    mode = c.trend_mode
    if not mode or mode == "none":
        return True
    if not bars:
        return False
    px, s10 = bars.get("close"), bars.get("sma10")
    s30, s50 = bars.get("sma30"), bars.get("sma50")
    if px is None or s10 is None or s50 is None:
        return False
    if mode == "s10_50":
        return px > s50 and s10 > s50
    if mode == "s10_30":
        return s30 is not None and px > s50 and s10 > s30
    if mode == "below50":
        return px < s50
    raise ValueError(f"unknown trend_mode {mode!r}")


def vix_ok(vix: float | None, c: Criteria) -> bool:
    if vix is None:
        return True
    if c.max_vix and vix > c.max_vix:
        return False
    if c.min_vix and vix < c.min_vix:
        return False
    return True


# ---------------------------------------------------------------------------
# construction
# ---------------------------------------------------------------------------

def _pick_short(chain: list[dict], right: str, c: Criteria) -> dict | None:
    lo, hi = c.short_delta - c.delta_tol, c.short_delta + c.delta_tol
    best, best_d = None, 9.99
    for row in chain:
        if row["right"] != right or row.get("delta") is None:
            continue
        d = abs(row["delta"])
        if not (lo <= d <= hi):
            continue
        if not passes_liquidity(row, c):
            continue
        diff = abs(d - c.short_delta)
        if diff < best_d:
            best, best_d = row, diff
    return best


def _pick_long(chain: list[dict], right: str, short_strike: float, c: Criteria) -> dict | None:
    """Protective leg: further OTM by ~width."""
    want = short_strike - c.width if right == "PUT" else short_strike + c.width
    best, best_d = None, 9.99e9
    for row in chain:
        if row["right"] != right:
            continue
        s = row["strike"]
        if right == "PUT" and s >= short_strike:
            continue
        if right == "CALL" and s <= short_strike:
            continue
        if abs(s - want) > c.width_tol:
            continue
        if _rel_spread(row["bid"], row["ask"]) > max(c.max_rel_spread * 2, 0.25):
            continue
        diff = abs(s - want)
        if diff < best_d:
            best, best_d = row, diff
    return best


def build_candidate(symbol: str, sector: str, chain: list[dict], c: Criteria,
                    today: date, underlying_price: float | None = None) -> Candidate | None:
    """Build the best spread for one symbol/expiry, or None."""
    # expiry window
    lo_dte, hi_dte = c.target_dte - c.dte_tol, c.target_dte + c.dte_tol
    by_exp: dict[str, list[dict]] = {}
    for row in chain:
        exp = datetime.strptime(row["expiration"][:10], "%Y-%m-%d").date()
        dte = (exp - today).days
        if lo_dte <= dte <= hi_dte:
            by_exp.setdefault(row["expiration"], []).append(row)
    if not by_exp:
        return None

    best: Candidate | None = None
    for exp, rows in by_exp.items():
        dte = (datetime.strptime(exp[:10], "%Y-%m-%d").date() - today).days
        cand = _build_one(symbol, sector, rows, c, exp, dte, underlying_price)
        if cand and (best is None or cand.rank_score > best.rank_score):
            best = cand
    return best


def _build_one(symbol, sector, rows, c: Criteria, exp: str, dte: int,
               underlying_price) -> Candidate | None:
    legs: list[Leg] = []
    credit = 0.0
    widths: list[float] = []

    def add_vertical(right: str) -> bool:
        nonlocal credit
        s = _pick_short(rows, right, c)
        if not s:
            return False
        l = _pick_long(rows, right, s["strike"], c)
        if not l:
            return False
        credit_leg = s["bid"] - l["ask"]          # conservative: cross the spread
        mid_leg = s["mid"] - l["mid"]
        credit += mid_leg                          # quote at mid, execute with limits
        widths.append(abs(s["strike"] - l["strike"]))
        legs.append(Leg("SELL", right, s["strike"], exp, s.get("ticker"),
                        s["bid"], s["ask"], s.get("delta")))
        legs.append(Leg("BUY", right, l["strike"], exp, l.get("ticker"),
                        l["bid"], l["ask"], l.get("delta")))
        return credit_leg is not None

    if c.structure == "bull_put":
        if not add_vertical("PUT"):
            return None
    elif c.structure == "bear_call":
        if not add_vertical("CALL"):
            return None
    elif c.structure == "iron_condor":
        if not add_vertical("PUT"):
            return None
        if not add_vertical("CALL"):
            return None
    else:
        raise ValueError(f"unknown structure {c.structure!r}")

    width = max(widths)
    if credit < c.min_credit or credit >= width:
        return None
    # a max loss at/near zero is a quote artifact, not a tradable structure
    if (width - credit) * 100 < c.min_max_loss_per_ct:
        return None
    if c.min_risk_reward > 0:
        risk = width - credit
        if risk <= 0 or (credit / risk) < c.min_risk_reward:
            return None

    shorts = [l for l in legs if l.action == "SELL"]
    sd = max(abs(l.delta or 0.0) for l in shorts)

    cand = Candidate(
        symbol=symbol, sector=sector, structure=c.structure, expiration=exp,
        dte=dte, legs=legs, credit=round(credit, 4), width=width,
        short_delta=round(sd, 4), underlying_price=underlying_price,
    )
    cand.rank_score = rank_key(cand.credit, cand.width, cand.short_delta, c.rank_mode)
    cand.rank_explanation = explain(cand.credit, cand.width, cand.short_delta).as_text()
    return cand


# ---------------------------------------------------------------------------
# portfolio selection
# ---------------------------------------------------------------------------

def size_candidate(cand: Candidate, c: Criteria) -> Candidate:
    max_loss_ct = (cand.width - cand.credit) * 100.0
    cand.max_loss_per_contract = round(max_loss_ct, 2)
    cap = c.equity * c.max_pct_per_position
    n = int(cap // max_loss_ct) if max_loss_ct > 0 else 0
    n = min(n, c.max_contracts)
    cand.contracts = max(n, 0)
    cand.total_risk = round(max_loss_ct * cand.contracts, 2)
    cand.max_profit = round(cand.credit * 100 * cand.contracts, 2)
    cand.commission = round(len(cand.legs) * c.commission_per_contract_leg * cand.contracts, 2)
    return cand


def select(cands: Iterable[Candidate], c: Criteria,
           open_sectors: dict[str, int] | None = None) -> list[Candidate]:
    """Rank, apply sector caps and sizing. Returns the accepted book."""
    sect = dict(open_sectors or {})
    ordered = sorted(cands, key=lambda x: -x.rank_score)
    out: list[Candidate] = []
    for cand in ordered:
        if len(out) >= c.max_new_per_day:
            break
        if sect.get(cand.sector, 0) >= c.max_per_sector:
            cand.notes.append(f"skipped: sector cap ({cand.sector})")
            continue
        size_candidate(cand, c)
        if cand.contracts < 1:
            cand.notes.append("skipped: position size rounds to 0 contracts")
            continue
        out.append(cand)
        sect[cand.sector] = sect.get(cand.sector, 0) + 1
    return out
