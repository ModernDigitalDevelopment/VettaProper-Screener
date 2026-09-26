"""The asymmetric spec on Q1/Q3/Q4 2022 -- out of sample vs the Q2 fit.

Q2 was a relentless downtrend, which is the ideal tape for selling
near-the-money calls. The decisive question is Q4, which contains the October
reversal and the November rally: if a delta-0.49 short call program survives a
sharp rally it is a real edge; if it blows up there, Q2 was an artifact.

Q1 and Q3 are included so the comparison is four quarters, not a cherry-pick.

The spec is FROZEN at exactly what was run on Q2 -- no re-tuning per quarter.
Any parameter change here would turn out-of-sample into in-sample.
"""
import pickle
import statistics
import sys

import spec_engine as E
from run2022 import BASE, load, metrics

DBS = {q: f"/home/user/db2022/thetadata_options_{q}_2022.db"
       for q in ("q1", "q2", "q3", "q4")}

# frozen, identical to asym.py
SPEC = dict(BASE)
SPEC.update(
    max_rel_spread=0.10, max_pct_per_position=0.05, max_per_sector=1,
    min_risk_reward=0.25, no_delta=True, earnings_blackout_days=14,
    trend_mode="asym",
    target_dte=9, dte_tol=2, exit_at_dte=2,
    put_dte=5, put_dte_tol=1, put_exit_dte=1, put_require_down=2,
    profit_target=0.80, hold_to_expiry=False,
)


def run(label, dbs, **ov):
    kw = dict(SPEC); kw.update(ov)
    sp = E.Spec(label=label, **kw)
    tr = []
    for db in dbs:
        tr += E.run(db, sp)
    m = metrics(tr)
    ror = (100*sum(t["net_pnl"]/t["max_loss"] for t in tr if t["max_loss"])/len(tr)) if tr else 0.0
    bp = sum(1 for t in tr if t["structure"] == "bull_put")
    dl = [t["delta_at_entry"] for t in tr if t.get("delta_at_entry")]
    print(f"  {label:<26} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
          f"dd={m['dd']:>5.1f}%  [{bp}P/{len(tr)-bp}C] "
          f"d{statistics.median(dl) if dl else 0:.2f}", flush=True)
    return label, tr, m, ror


def main():
    load()
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out = {}
    print("=" * 104)
    print("ASYMMETRIC SPEC -- FROZEN from Q2, applied to each quarter of 2022")
    print("no re-tuning; 'd' column is median delta actually selected")
    print("=" * 104)
    print()
    qs = ["q1", "q3", "q4"] if which == "oos" else ["q1", "q2", "q3", "q4"]
    for q in qs:
        out[q] = run(f"{q.upper()} 2022", [DBS[q]])

    print()
    print("  delta-capped control (0.20-0.30) on the same quarters")
    for q in qs:
        out[f"{q}_d25"] = run(f"{q.upper()} delta 0.20-0.30", [DBS[q]],
                              no_delta=False, short_delta=0.25, delta_tol=0.05)

    pickle.dump({k: (v[1], v[2], v[3]) for k, v in out.items()},
                open("r22_asym_oos.pkl", "wb"))
    print("\nwrote r22_asym_oos.pkl")


if __name__ == "__main__":
    main()
