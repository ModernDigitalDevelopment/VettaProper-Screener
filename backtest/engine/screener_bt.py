"""Screener backtest: fitted delta x risk-reward ranking.

User spec:
  - rank by delta / risk-reward correlation
  - 5% and 10% per position
  - 2 per sector
  - earnings AND dividend blackout within 12 days
  - NO IV/RV anywhere
"""
import json
import pickle
from concurrent.futures import ProcessPoolExecutor

import spec_engine as E
from dbs import DBS

BASE = dict(
    structure="bull_put",
    short_delta=0.30, delta_tol=0.20,       # wide net; ranking does the picking
    width=5.0, width_tol=5.1,
    target_dte=9, dte_tol=2,
    min_ivrv=0.0,                            # NO IV/RV
    max_rel_spread=0.10,
    min_credit=0.10,
    mid_fill_prob=0.95,
    profit_target=0.80,
    exit_days_before_expiry=0,
    hold_to_expiry=False,
    equity=50_000.0,
    max_per_sector=2,                        # 2 per sector
    max_open=12,
    max_new_per_day=4,
    earnings_blackout_days=12,               # earnings + dividend, 12 days
    blackout_exdiv=True,
    trend_mode="s10_50",
    min_risk_reward=0.0,
)


def load_lookups():
    E.SIGNALS.update(pickle.load(open("signals.pkl", "rb")))
    E.TREND.update(pickle.load(open("trend2.pkl", "rb")))
    E.EVENTS.update(pickle.load(open("events.pkl", "rb")))
    E.VIX.update(pickle.load(open("vix.pkl", "rb")))
    E.SECTORS.update(json.load(open("sectors.json")))


def one(args):
    label, kw = args
    load_lookups()
    spec = E.Spec(label=label, **kw)
    trades = []
    for db in DBS.values():
        trades += E.run(db, spec)
    return label, trades


def metrics(trades, equity=50_000.0):
    if not trades:
        return None
    n = len(trades)
    net = sum(t["net_pnl"] for t in trades)
    wins = [t for t in trades if t["net_pnl"] > 0]
    gp = sum(t["net_pnl"] for t in wins)
    gl = -sum(t["net_pnl"] for t in trades if t["net_pnl"] <= 0)
    # peak concurrent capital at risk
    ev = []
    for t in trades:
        ev.append((t["entry_date"], t["max_loss"]))
        ev.append((t["exit_date"], -t["max_loss"]))
    ev.sort()
    cur = peak = 0.0
    for _, v in ev:
        cur += v
        peak = max(peak, cur)
    # drawdown on cumulative net
    cum = 0.0
    hi = 0.0
    dd = 0.0
    for t in sorted(trades, key=lambda x: x["exit_date"]):
        cum += t["net_pnl"]
        hi = max(hi, cum)
        dd = max(dd, hi - cum)
    return dict(
        n=n,
        win=round(100 * len(wins) / n, 1),
        exp=round(net / n, 2),
        net=round(net),
        pf=round(gp / gl, 2) if gl > 0 else 99.0,
        peak_risk_pct=round(100 * peak / equity),
        dd=round(dd),
        dd_pct=round(100 * dd / equity, 1),
        worst=round(min(t["net_pnl"] for t in trades)),
    )


def main():
    jobs = []
    for pct in (0.05, 0.10):
        for rank in ("cw", "score"):
            kw = dict(BASE, max_pct_per_position=pct, rank_mode=rank)
            jobs.append((f"{int(pct*100)}%|{rank}", kw))

    out = {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        for label, trades in ex.map(one, jobs):
            out[label] = trades
            m = metrics(trades)
            print(f"{label:<14} {m}")

    pickle.dump(out, open("screener_trades.pkl", "wb"))
    print("\nsaved screener_trades.pkl")


if __name__ == "__main__":
    main()
