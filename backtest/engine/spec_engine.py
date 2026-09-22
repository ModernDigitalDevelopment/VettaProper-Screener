"""Backtest of Neil's exact specification.

Rules implemented:
  * Universe-wide scan, SECTOR DIVERSIFIED (max N per sector, max 1 per symbol)
  * Position size capped at 5% of account equity (max_loss <= 0.05 * equity)
  * Entry requires IV/RV >= 1.2
  * Short-leg relative bid/ask spread <= 10%
  * Fills at MIDPOINT 95% of the time (5% of attempts cross the spread)
  * 10 DTE target
  * Exit: 80% of max profit, OR 1 day before expiry, OR hold to expiration
  * Structures: BULL PUT spread or IRON CONDOR
  * Short delta variants: 0.20 / 0.30 / 0.40
"""
from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any

SIGNALS: dict[tuple[str, str], dict] = {}
TREND: dict[tuple[str, str], dict] = {}
EVENTS: dict[str, list] = {}
VIX: dict[str, float] = {}


def _has_event(symbol: str, d0: str, days: int, types: tuple[str, ...]) -> bool:
    """True if an event of the given types falls within [d0, d0+days]."""
    if not types or days <= 0:
        return False
    a = datetime.strptime(d0[:10], "%Y-%m-%d").date()
    b = a + timedelta(days=days)
    for ds, tp in EVENTS.get(symbol, ()):  # pre-sorted
        if tp not in types:
            continue
        dd = datetime.strptime(ds, "%Y-%m-%d").date()
        if dd > b:
            break
        if a <= dd:
            return True
    return False
SECTORS: dict[str, str] = {}


@dataclass(frozen=True)
class Spec:
    # structure
    structure: str = "bull_put"      # bull_put | iron_condor
    short_delta: float = 0.20
    delta_tol: float = 0.05
    width: float = 5.0
    width_tol: float = 5.1           # accept a wide range, prefer nearest

    # entry gates
    target_dte: int = 10
    dte_tol: int = 3
    min_ivrv: float = 1.2
    max_rel_spread: float = 0.10
    min_credit: float = 0.10

    # fills
    mid_fill_prob: float = 0.95      # 95% of fills at mid, else cross

    # exit
    profit_target: float = 0.80      # close at 80% of max profit
    exit_days_before_expiry: int = 1  # or hold to expiry if None
    hold_to_expiry: bool = False

    # portfolio / risk
    equity: float = 50_000.0
    max_pct_per_position: float = 0.05   # 5% of equity at risk
    max_per_sector: int = 2
    max_open: int = 12
    max_new_per_day: int = 4
    commission_per_contract_leg: float = 0.65

    min_risk_reward: float = 0.0     # credit / (width - credit) >= x
    max_vix: float = 0.0             # only enter when VIX proxy below this
    min_vix: float = 0.0
    earnings_blackout_days: int = 0   # skip if earnings within N days of entry
    blackout_exdiv: bool = False      # also blackout ex-dividend dates
    require_trend: bool = False      # legacy flag: price>50SMA AND 10SMA>50SMA
    trend_mode: str = ""             # "" | s10_50 | s10_30 | below50 | none
    min_max_loss_per_ct: float = 25.0   # reject artifact structures with ~no risk
    max_contracts: int = 20             # hard cap regardless of sizing math
    rank_mode: str = "cw"            # "cw" (credit/width, legacy) | "score" (fitted delta x rr)
    seed: int = 7
    label: str = "spec"


# Ranking surface fitted by OLS on 2,129 unranked candidate trades
# (bull puts, s10_50 trend, 12d earnings+ex-div blackout, no IV/RV).
# Target = return on risk (net P&L / max loss). R2 = 0.063.
# Interpretation: risk-reward is the dominant positive driver; delta carries a
# penalty; the negative interaction means high delta erodes the R:R benefit.
RANK_COEF = {
    "const":    0.1408,
    "rr":       1.1350,
    "rr2":      0.2034,
    "delta":   -1.2623,
    "delta2":   2.3618,
    "rr_delta": -2.5379,
}


def rank_score(p) -> float:
    """Expected return-on-risk for a candidate spread. Higher is better."""
    risk = p.width - p.credit
    if risk <= 0:
        return -9.99
    rr = p.credit / risk
    dl = abs(p.delta_at_entry or 0.0)
    c = RANK_COEF
    return (c["const"]
            + c["rr"] * rr
            + c["rr2"] * rr * rr
            + c["delta"] * dl
            + c["delta2"] * dl * dl
            + c["rr_delta"] * rr * dl)


def _d(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


@dataclass
class Pos:
    symbol: str
    sector: str
    expiration: str
    entry_date: str
    structure: str
    contracts: int
    width: float
    credit: float          # per share, net
    legs: dict             # strikes
    dte_at_entry: int
    delta_at_entry: float
    ivrv: float
    exit_date: str | None = None
    exit_debit: float | None = None
    exit_reason: str | None = None

    @property
    def max_loss_per_ct(self) -> float:
        return (self.width - self.credit) * 100

    def result(self, spec: Spec) -> dict[str, Any]:
        nlegs = 2 if self.structure == "bull_put" else 4
        comm = spec.commission_per_contract_leg * nlegs * self.contracts * 2
        gross = (self.credit - (self.exit_debit or 0.0)) * 100 * self.contracts
        return {
            "symbol": self.symbol, "sector": self.sector,
            "structure": self.structure,
            "entry_date": self.entry_date, "exit_date": self.exit_date,
            "exit_reason": self.exit_reason,
            "contracts": self.contracts, "width": self.width,
            "credit": self.credit, "exit_debit": self.exit_debit,
            "gross_pnl": gross, "commission": comm,
            "net_pnl": gross - comm,
            "max_loss": self.max_loss_per_ct * self.contracts,
            "dte_at_entry": self.dte_at_entry,
            "delta_at_entry": self.delta_at_entry,
            "ivrv": self.ivrv,
        }


class Book:
    def __init__(self, db: str):
        self.con = sqlite3.connect(db)
        self.con.row_factory = sqlite3.Row
        self.dates = [r[0] for r in self.con.execute(
            "select distinct trade_date from option_eod order by trade_date")]

    def day(self, td: str):
        cur = self.con.execute(
            """select symbol,trade_date,expiration,strike,right,bid,ask,bid_size,ask_size,
                      volume,delta,implied_vol,underlying_price
               from option_eod where trade_date=? and bid>0 and ask>0 and delta is not null""",
            (td,))
        out: dict[str, list] = {}
        for r in cur:
            out.setdefault(r["symbol"], []).append(r)
        return out

    def q(self, sym, td, exp, strike, right):
        return self.con.execute(
            """select bid,ask,underlying_price from option_eod
               where symbol=? and trade_date=? and expiration=? and strike=? and right=?""",
            (sym, td, exp, strike, right)).fetchone()


def _fill_price(bid: float, ask: float, side: str, at_mid: bool) -> float:
    """side='sell' receives; side='buy' pays."""
    if at_mid:
        return (bid + ask) / 2.0
    return bid if side == "sell" else ask


def build(rows, spec: Spec, today: date, rng: random.Random):
    """Construct a bull put or iron condor for one symbol."""
    sym = str(rows[0]["symbol"])
    sig = SIGNALS.get((sym, rows[0]["trade_date"]))
    if not sig or (sig.get("ivrv") or 0) < spec.min_ivrv:
        return None
    if spec.max_vix > 0 or spec.min_vix > 0:
        v = VIX.get(rows[0]["trade_date"])
        if v is None:
            return None
        if spec.max_vix > 0 and v > spec.max_vix:
            return None
        if spec.min_vix > 0 and v < spec.min_vix:
            return None
    if spec.earnings_blackout_days > 0:
        types = ("EARNINGS", "EX_DIV") if spec.blackout_exdiv else ("EARNINGS",)
        if _has_event(sym, rows[0]["trade_date"], spec.earnings_blackout_days, types):
            return None
    mode = spec.trend_mode or ("s10_50" if spec.require_trend else "")
    if mode and mode != "none":
        tr = TREND.get((sym, rows[0]["trade_date"]))
        if not tr:
            return None
        px, s10 = tr["close"], tr["sma10"]
        s30, s50 = tr.get("sma30"), tr["sma50"]
        if mode == "s10_50":
            if not (px > s50 and s10 > s50):
                return None
        elif mode == "s10_30":
            if s30 is None or not (px > s50 and s10 > s30):
                return None
        elif mode == "below50":
            if not (px < s50):
                return None
        else:
            raise ValueError(f"unknown trend_mode {mode}")

    by_exp: dict[str, list] = {}
    for r in rows:
        by_exp.setdefault(r["expiration"], []).append(r)
    exp, dte = None, None
    for e in by_exp:
        try:
            k = (_d(e) - today).days
        except Exception:
            continue
        if k < 2:
            continue
        if abs(k - spec.target_dte) <= spec.dte_tol:
            if dte is None or abs(k - spec.target_dte) < abs(dte - spec.target_dte):
                exp, dte = e, k
    if exp is None:
        return None
    chain = by_exp[exp]

    def pick_short(right: str):
        best = None
        for r in chain:
            if r["right"] != right:
                continue
            ad = abs(float(r["delta"] or 0))
            if abs(ad - spec.short_delta) > spec.delta_tol:
                continue
            b, a = float(r["bid"]), float(r["ask"])
            m = (a + b) / 2
            if m <= 0 or (a - b) / m > spec.max_rel_spread:
                continue
            d = abs(ad - spec.short_delta)
            if best is None or d < best[0]:
                best = (d, r)
        return best[1] if best else None

    def pick_long(right: str, short_strike: float):
        best = None
        for r in chain:
            if r["right"] != right:
                continue
            k = float(r["strike"])
            w = (short_strike - k) if right == "PUT" else (k - short_strike)
            if w <= 0 or float(r["ask"]) <= 0:
                continue
            d = abs(w - spec.width)
            if d > spec.width_tol:
                continue
            if best is None or d < best[0]:
                best = (d, r, w)
        return (best[1], best[2]) if best else None

    at_mid = rng.random() < spec.mid_fill_prob
    legs: dict[str, Any] = {}
    credit = 0.0
    widths = []

    ps = pick_short("PUT")
    if ps is None:
        return None
    pl = pick_long("PUT", float(ps["strike"]))
    if pl is None:
        return None
    pl_row, pw = pl
    credit += _fill_price(float(ps["bid"]), float(ps["ask"]), "sell", at_mid)
    credit -= _fill_price(float(pl_row["bid"]), float(pl_row["ask"]), "buy", at_mid)
    legs["put_short"] = float(ps["strike"]); legs["put_long"] = float(pl_row["strike"])
    widths.append(pw)
    delta_entry = abs(float(ps["delta"] or 0))

    if spec.structure == "iron_condor":
        cs = pick_short("CALL")
        if cs is None:
            return None
        cl = pick_long("CALL", float(cs["strike"]))
        if cl is None:
            return None
        cl_row, cw = cl
        credit += _fill_price(float(cs["bid"]), float(cs["ask"]), "sell", at_mid)
        credit -= _fill_price(float(cl_row["bid"]), float(cl_row["ask"]), "buy", at_mid)
        legs["call_short"] = float(cs["strike"]); legs["call_long"] = float(cl_row["strike"])
        widths.append(cw)

    width = max(widths)   # condor max loss is the wider wing
    if credit < spec.min_credit or credit >= width:
        return None
    # An implied max loss at/near zero is a quote artifact, not a real trade.
    if (width - credit) * 100 < spec.min_max_loss_per_ct:
        return None
    # risk/reward = net credit / capital at risk
    if spec.min_risk_reward > 0:
        risk = width - credit
        if risk <= 0 or (credit / risk) < spec.min_risk_reward:
            return None

    return Pos(symbol=sym, sector=SECTORS.get(sym, "UNKNOWN"), expiration=exp,
               entry_date=rows[0]["trade_date"], structure=spec.structure,
               contracts=1, width=width, credit=credit, legs=legs,
               dte_at_entry=dte, delta_at_entry=delta_entry,
               ivrv=float(sig.get("ivrv") or 0))


def close_debit(bk: Book, p: Pos, td: str, at_mid: bool) -> float | None:
    """Cost to close: buy back shorts, sell longs."""
    tot = 0.0
    qs = bk.q(p.symbol, td, p.expiration, p.legs["put_short"], "PUT")
    ql = bk.q(p.symbol, td, p.expiration, p.legs["put_long"], "PUT")
    if not qs or not ql:
        return None
    tot += _fill_price(float(qs["bid"]), float(qs["ask"]), "buy", at_mid)
    tot -= _fill_price(float(ql["bid"]), float(ql["ask"]), "sell", at_mid)
    if p.structure == "iron_condor":
        cs = bk.q(p.symbol, td, p.expiration, p.legs["call_short"], "CALL")
        cl = bk.q(p.symbol, td, p.expiration, p.legs["call_long"], "CALL")
        if not cs or not cl:
            return None
        tot += _fill_price(float(cs["bid"]), float(cs["ask"]), "buy", at_mid)
        tot -= _fill_price(float(cl["bid"]), float(cl["ask"]), "sell", at_mid)
    return max(0.0, tot)


def intrinsic_at_expiry(p: Pos, spot: float) -> float:
    """Settlement debit if held to expiration."""
    d = 0.0
    ps, pl = p.legs["put_short"], p.legs["put_long"]
    d += max(0.0, ps - spot) - max(0.0, pl - spot)
    if p.structure == "iron_condor":
        cs, cl = p.legs["call_short"], p.legs["call_long"]
        d += max(0.0, spot - cs) - max(0.0, spot - cl)
    return max(0.0, d)


def run(db: str, spec: Spec) -> list[dict]:
    bk = Book(db)
    rng = random.Random(spec.seed)
    open_pos: list[Pos] = []
    closed: list[dict] = []
    last_spot: dict[str, float] = {}

    for td in bk.dates:
        today = _d(td)
        snap = bk.day(td)
        for sym, rows in snap.items():
            last_spot[sym] = float(rows[0]["underlying_price"] or 0)

        # ---------- exits first
        still = []
        for p in open_pos:
            dte = (_d(p.expiration) - today).days
            at_mid = rng.random() < spec.mid_fill_prob

            # expiry settlement
            if dte <= 0:
                spot = last_spot.get(p.symbol, 0.0)
                dbt = intrinsic_at_expiry(p, spot) if spot else p.credit
                p.exit_date, p.exit_debit, p.exit_reason = td, dbt, "EXPIRED"
                closed.append(p.result(spec)); continue

            dbt = close_debit(bk, p, td, at_mid)
            if dbt is None:
                still.append(p); continue

            reason = None
            # 80% of max profit == debit <= 20% of credit
            if dbt <= p.credit * (1.0 - spec.profit_target):
                reason = "TAKE_PROFIT"
            elif (not spec.hold_to_expiry) and dte <= spec.exit_days_before_expiry:
                reason = "PRE_EXPIRY_EXIT"

            if reason:
                p.exit_date, p.exit_debit, p.exit_reason = td, dbt, reason
                closed.append(p.result(spec))
            else:
                still.append(p)
        open_pos = still

        # ---------- entries
        if len(open_pos) >= spec.max_open:
            continue
        held = {p.symbol for p in open_pos}
        sect = {}
        for p in open_pos:
            sect[p.sector] = sect.get(p.sector, 0) + 1

        cands = []
        for sym, rows in snap.items():
            if sym in held:
                continue
            pos = build(rows, spec, today, rng)
            if pos:
                cands.append(pos)
        # rank candidates: legacy credit/width, or fitted delta x risk-reward score
        if spec.rank_mode == "score":
            cands.sort(key=lambda p: -rank_score(p))
        else:
            cands.sort(key=lambda p: -(p.credit / p.width))

        new = 0
        for pos in cands:
            if new >= spec.max_new_per_day or len(open_pos) >= spec.max_open:
                break
            if sect.get(pos.sector, 0) >= spec.max_per_sector:
                continue
            # 5% position sizing
            cap = spec.equity * spec.max_pct_per_position
            if pos.max_loss_per_ct < spec.min_max_loss_per_ct:
                continue
            n = int(cap // pos.max_loss_per_ct)
            n = min(n, spec.max_contracts)
            if n < 1:
                continue
            pos.contracts = n
            open_pos.append(pos)
            sect[pos.sector] = sect.get(pos.sector, 0) + 1
            new += 1

    # force close remainder
    if bk.dates:
        td = bk.dates[-1]
        for p in open_pos:
            dbt = close_debit(bk, p, td, True)
            if dbt is None:
                spot = last_spot.get(p.symbol, 0.0)
                dbt = intrinsic_at_expiry(p, spot) if spot else p.credit
            p.exit_date, p.exit_debit, p.exit_reason = td, dbt, "FORCE_CLOSE"
            closed.append(p.result(spec))
    return closed


def report(trades: list[dict], name: str):
    import statistics
    if not trades:
        print(f"{name:42} no trades"); return None
    p = [t["net_pnl"] for t in trades]
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    eq, peak, mdd = 0.0, 0.0, 0.0
    for t in sorted(trades, key=lambda x: x["exit_date"]):
        eq += t["net_pnl"]; peak = max(peak, eq); mdd = max(mdd, peak - eq)
    pf = (sum(w) / abs(sum(l))) if l else float("inf")
    print(f"{name:42} n={len(p):4} win={len(w)/len(p)*100:5.1f}% "
          f"exp=${sum(p)/len(p):+8.2f} net=${sum(p):+9.0f} pf={pf:5.2f} maxDD=${mdd:,.0f}")
    return {"n": len(p), "win": len(w)/len(p)*100, "exp": sum(p)/len(p),
            "net": sum(p), "pf": pf, "mdd": mdd,
            "avg_win": statistics.mean(w) if w else 0,
            "avg_loss": statistics.mean(l) if l else 0,
            "worst": min(p), "trades": trades}
