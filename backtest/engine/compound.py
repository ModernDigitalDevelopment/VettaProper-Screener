"""Compounding backtest: position size scales with realised equity.

The original runs used a FIXED $50,000 base all year:
    cap = 50_000 * pct

That understates a winning strategy (you never size up) and overstates a
losing one (you never size down). This re-runs with equity marked to realised
P&L, so contracts scale with the account.

IMPORTANT: equity is updated only when a trade CLOSES, not when it opens.
Unrealised profit is not tradable capital. Doing otherwise would let the
backtest size off money it had not actually made.
"""
import json
import pickle
from collections import defaultdict

import spec_engine as E
from dbs import DBS


def load():
    E.SIGNALS.update(pickle.load(open("signals.pkl", "rb")))
    E.TREND.update(pickle.load(open("trend2.pkl", "rb")))
    E.EVENTS.update(pickle.load(open("events.pkl", "rb")))
    E.VIX.update(pickle.load(open("vix.pkl", "rb")))
    E.SECTORS.update(json.load(open("sectors.json")))


def compound(trades, start_equity=50_000.0, pct=0.05, max_contracts=20,
             min_max_loss=25.0):
    """Re-size an executed trade sequence against a compounding account.

    Each trade's per-contract economics are held constant (same spread, same
    fill) and only the CONTRACT COUNT is recomputed against live equity. This
    isolates the effect of compounding from any change in selection.
    """
    seq = sorted(trades, key=lambda t: (t["entry_date"], t["symbol"]))
    equity = start_equity
    peak = equity
    max_dd = 0.0

    # pending[exit_date] -> list of realised pnl to credit on that date
    pending = defaultdict(list)
    out = []
    open_risk = 0.0
    peak_risk = 0.0
    risk_at_peak_equity = 0.0

    # process chronologically, crediting closes before sizing new opens
    dates = sorted({t["entry_date"] for t in seq} | {t["exit_date"] for t in seq})
    by_entry = defaultdict(list)
    for t in seq:
        by_entry[t["entry_date"]].append(t)

    live = []   # (exit_date, scaled_pnl, risk)

    for d in dates:
        # 1. close anything expiring/exiting today -> realise P&L into equity
        still = []
        for exit_d, pnl, risk in live:
            if exit_d <= d:
                equity += pnl
                open_risk -= risk
            else:
                still.append((exit_d, pnl, risk))
        live = still

        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

        # 2. size and open today's trades against CURRENT equity
        for t in by_entry.get(d, []):
            ml_ct = t["max_loss"] / t["contracts"]      # per-contract max loss
            if ml_ct < min_max_loss:
                continue
            cap = equity * pct
            n = int(cap // ml_ct)
            n = min(n, max_contracts)
            if n < 1:
                continue
            scale = n / t["contracts"]
            pnl = t["net_pnl"] * scale
            risk = ml_ct * n
            live.append((t["exit_date"], pnl, risk))
            open_risk += risk
            peak_risk = max(peak_risk, open_risk)
            out.append({**t, "contracts": n, "net_pnl": pnl,
                        "max_loss": risk, "equity_at_entry": equity})

    # close stragglers
    for _, pnl, _ in live:
        equity += pnl
    peak = max(peak, equity)
    max_dd = max(max_dd, peak - equity)

    return out, dict(
        start=start_equity,
        final=equity,
        profit=equity - start_equity,
        return_pct=100 * (equity - start_equity) / start_equity,
        max_dd=max_dd,
        max_dd_pct=100 * max_dd / peak if peak else 0,
        peak_risk=peak_risk,
        peak_risk_pct_of_start=100 * peak_risk / start_equity,
        n=len(out),
    )


def summarise(trades, label, m):
    wins = [t for t in trades if t["net_pnl"] > 0]
    gp = sum(t["net_pnl"] for t in wins)
    gl = -sum(t["net_pnl"] for t in trades if t["net_pnl"] <= 0)
    pf = gp / gl if gl > 0 else 99
    print(f"{label:<28} n={m['n']:>4} win={100*len(wins)/len(trades):>5.1f}% "
          f"final=${m['final']:>10,.0f} ret={m['return_pct']:>7.1f}% "
          f"PF={pf:>5.2f} maxDD={m['max_dd_pct']:>5.1f}% "
          f"peakRisk={m['peak_risk_pct_of_start']:>4.0f}%")
    return pf


def period_of(d):
    m = int(d[5:7])
    return "mar" if m == 3 else ("q2" if m in (4, 5, 6) else "q4")


def compound_by_period(trades, **kw):
    """Compound within each contiguous database period separately.

    The three ThetaData databases (Mar, Apr-Jun, Oct-Dec) are separate
    sequences. Merging them into one timeline makes trades from different
    periods look concurrent, which inflates peak capital at risk to
    impossible levels (>100% of the account). Compounding per period and
    chaining the equity forward is the honest treatment.
    """
    groups = defaultdict(list)
    for t in trades:
        groups[period_of(t["entry_date"])].append(t)

    equity = kw.pop("start_equity", 50_000.0)
    start = equity
    all_out, peak_risk_pct, dds = [], 0.0, []
    for p in ("mar", "q2", "q4"):
        if p not in groups:
            continue
        out, m = compound(groups[p], start_equity=equity, **kw)
        all_out += out
        equity = m["final"]
        peak_risk_pct = max(peak_risk_pct, 100 * m["peak_risk"] / m["start"])
        dds.append(m["max_dd_pct"])
    return all_out, dict(
        start=start, final=equity, profit=equity - start,
        return_pct=100 * (equity - start) / start,
        max_dd_pct=max(dds) if dds else 0,
        peak_risk_pct_of_start=peak_risk_pct,
        n=len(all_out),
    )


if __name__ == "__main__":
    tune = pickle.load(open("screener_tune.pkl", "rb"))
    base = tune["5%|score|rr.2|1sec"]

    print("FIXED vs COMPOUNDING — recommended configuration")
    print("=" * 118)
    fixed_net = sum(t["net_pnl"] for t in base)
    print(f"{'fixed $50k base (5%)':<28} n={len(base):>4} "
          f"win={100*sum(1 for t in base if t['net_pnl']>0)/len(base):>5.1f}% "
          f"final=${50000+fixed_net:>10,.0f} ret={100*fixed_net/50000:>7.1f}%")
    print()

    results = {}
    for pct in (0.05, 0.075, 0.10):
        tr, m = compound(base, pct=pct)
        summarise(tr, f"compounding {pct*100:g}%", m)
        results[f"{pct*100:g}%"] = m

    print()
    print("Same, with the contract cap lifted (20 -> 100):")
    for pct in (0.05, 0.10):
        tr, m = compound(base, pct=pct, max_contracts=100)
        summarise(tr, f"compounding {pct*100:g}% cap100", m)

    json.dump(results, open("compound_results.json", "w"), indent=1)
