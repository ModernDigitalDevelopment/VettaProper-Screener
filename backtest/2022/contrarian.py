"""Contrarian mean-reversion test, Q2 2022 only.

User's spec, held exactly:
  spreads <10% relative bid/ask, 5% per position, 1 per sector,
  R:R >= 0.20, delta 0.20-0.30, 14-day earnings gate.

Trend gate is INVERTED versus everything tested so far:
  5 SMA >= +X% over  20 SMA  ->  BEAR CALL   (stretched up, sell the rally)
  5 SMA <= -X% under 20 SMA  ->  BULL PUT    (washed out, sell the panic)

This is the first non-trend-following idea tested, and it is the first that
is not structurally a direction bet: it keys on the SIZE of a dislocation,
not its sign. Both sides can fire in the same week.

Delta note: the user asked for 0.20-0.30, which is short_delta 0.25 with
delta_tol 0.05 -- identical to the existing runs, so this is comparable.

Threshold note: +/-10% sits at the 1st/99th percentile of the Q2 distribution
(1.25% of symbol-days above +10%, 5.67% below -10%). The requested 10% is run
first, then a sweep, because 10% may be too rare to conclude from.
"""
import pickle

import spec_engine as E
from run2022 import BASE, load, metrics

Q2 = {"q2": "/home/user/db2022/thetadata_options_q2_2022.db"}

BASE_C = dict(BASE)
BASE_C.update(
    max_rel_spread=0.10,          # spreads < 10%
    max_pct_per_position=0.05,    # 5% per position
    max_per_sector=1,             # 1 per sector
    min_risk_reward=0.20,         # R:R >= 0.20
    short_delta=0.25, delta_tol=0.05,   # delta 0.20-0.30
    earnings_blackout_days=14,    # 14-day earnings gate
    trend_mode="revert",          # the new gate
)


def run(label, **ov):
    kw = dict(BASE_C)
    kw.update(ov)
    sp = E.Spec(label=label, **kw)
    tr = []
    for db in Q2.values():
        tr += E.run(db, sp)
    m = metrics(tr)
    ror = (100 * sum(t["net_pnl"] / t["max_loss"] for t in tr if t["max_loss"])
           / len(tr)) if tr else 0.0
    bp = sum(1 for t in tr if t["structure"] == "bull_put")
    bc = len(tr) - bp
    print(f"  {label:<32} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+8,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
          f"dd={m['dd']:>5.1f}%  [{bp}P/{bc}C]", flush=True)
    return label, tr, m, ror


def main():
    load()
    out = {}

    print("=" * 96)
    print("CONTRARIAN MEAN-REVERSION -- Q2 2022 ONLY (Apr-Jun)")
    print("5SMA stretched ABOVE 20SMA -> bear call;  BELOW -> bull put")
    print("=" * 96)

    print("\nrequested threshold")
    out["r10"] = run("+/-10% (as specified)", revert_pct=10.0)

    print("\nthreshold sweep -- is 10% the right number?")
    for t in (3.0, 4.0, 5.0, 7.0, 15.0):
        out[f"r{int(t)}"] = run(f"+/-{t:.0f}%", revert_pct=t)

    print("\nbenchmarks on the same quarter")
    out["tf"] = run("trend-FOLLOWING (s10_50, puts)",
                    trend_mode="s10_50", structure="bull_put")
    out["put"] = run("always bull put, no gate",
                     trend_mode="none", structure="bull_put")
    out["call"] = run("always bear call, no gate",
                      trend_mode="none", structure="bear_call")

    pickle.dump({k: (v[1], v[2], v[3]) for k, v in out.items()},
                open("r22_contrarian.pkl", "wb"))

    print()
    print("=" * 96)
    print("RANKED BY MEAN RETURN-ON-RISK (size-independent)")
    print("=" * 96)
    for k, v in sorted(out.items(), key=lambda x: -x[1][3]):
        m = v[2]
        if not m["n"]:
            continue
        flag = "  <-- POSITIVE" if v[3] > 0 else ""
        print(f"  {v[0]:<32} ror={v[3]:>+6.2f}%  pf={m['pf']:>4.2f}  "
              f"n={m['n']:>4}{flag}")
    print()
    print("  One quarter only. Small n on the wide thresholds -- treat any")
    print("  winner as a hypothesis to test on the other three quarters.")


if __name__ == "__main__":
    main()
