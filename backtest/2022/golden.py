"""Golden-cross side selection + VXX hedge overlay. 2022.

RULE: sma50 > sma200 -> bull put;  sma50 < sma200 -> bear call.  Per symbol.
Standardised elsewhere: spreads <10%, 9+/-2 DTE, delta 0.20-0.30, R:R >= 0.20,
14-day earnings gate, 5%/position, 1/sector, 80% PT or EOD 2 DTE.

Two variants, because a TRUE 200-session average only exists from 2022-10-18:
  full      includes shortened-warm-up rows (flagged sma200_true=0)
  true200   restricted to rows with a genuine 200-session window
"""
import pickle
import sys
import spec_engine as E
from run2022 import BASE, DBS_2022, load, metrics

SPEC = dict(BASE)
SPEC.update(
    max_rel_spread=0.10, max_pct_per_position=0.05, max_per_sector=1,
    min_risk_reward=0.20, short_delta=0.25, delta_tol=0.05,
    earnings_blackout_days=14, target_dte=9, dte_tol=2,
    profit_target=0.80, exit_at_dte=2, trend_mode="golden",
)


def run(label, **ov):
    kw = dict(SPEC); kw.update(ov)
    sp = E.Spec(label=label, **kw)
    tr = []
    for db in DBS_2022.values():
        tr += E.run(db, sp)
    m = metrics(tr)
    ror = (100*sum(t["net_pnl"]/t["max_loss"] for t in tr if t["max_loss"])/len(tr)) if tr else 0.0
    bp = sum(1 for t in tr if t["structure"] == "bull_put")
    print(f"  {label:<34} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+8,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
          f"dd={m['dd']:>5.1f}%  [{bp}P/{len(tr)-bp}C]", flush=True)
    return label, tr, m, ror


def main():
    load()
    out = {}
    print("=" * 96)
    print("GOLDEN CROSS SIDE SELECTION -- 2022 full year")
    print("sma50 > sma200 -> bull put | sma50 < sma200 -> bear call")
    print("=" * 96)
    out["full"] = run("golden, all rows (warm-up flagged)")
    out["true"] = run("golden, TRUE 200d only", require_true_sma200=True)
    print()
    print("  benchmarks")
    out["put"] = run("always bull put, no gate",
                     trend_mode="none", structure="bull_put")
    out["call"] = run("always bear call, no gate",
                      trend_mode="none", structure="bear_call")
    pickle.dump({k: (v[1], v[2], v[3]) for k, v in out.items()},
                open("r22_golden.pkl", "wb"))
    print()
    print("=" * 96)
    print("WITH THE VXX HEDGE OVERLAID (1% of equity per cycle = -$4,313)")
    print("=" * 96)
    hedge = -4_313
    for k in ("full", "true", "put", "call"):
        net = out[k][2]["net"]
        print(f"  {out[k][0]:<34} naked {net:>+9,.0f}   hedged {net+hedge:>+9,.0f}")
    print()
    print("  The hedge is a flat cost here; it did not pay off in 2022 even")
    print("  though 2022 was a bear market. See vxx_hedge.py for why.")


if __name__ == "__main__":
    main()
