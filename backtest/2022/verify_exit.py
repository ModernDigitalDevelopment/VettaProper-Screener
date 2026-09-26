"""Does FIXING the missed-exit bug change the result? Q2 both years.

The bug: close_debit() returns None when any leg lacks a quote, and the old
code then skipped the entire exit block, so a position past its exit_at_dte
cutoff drifted to expiry. Measured: all 44 EXPIRED trades in the tuned 2023
condor run had run their FULL dte despite exit_at_dte=1.

This matters because expiry is the worst outcome in the whole dataset
(-40% RoR for condors) while an EOD exit is the best (+10% to +40%).

The patch does not change fills -- a desk cannot fill without a quote either.
It only records how often the exit is missed, so the frequency is visible.
Re-running confirms whether the earlier numbers were distorted.
"""
import json, pickle
import spec_engine as E
from run2022 import BASE, metrics

Q2_22 = {"q2": "/home/user/db2022/thetadata_options_q2_2022.db"}
Q2_23 = {"q2": "/home/user/db2023/thetadata_options_q2_2023.db"}

SPEC = dict(BASE)
SPEC.update(structure="iron_condor", trend_mode="none", max_rel_spread=0.20,
            max_pct_per_position=0.05, max_per_sector=2, min_risk_reward=0.20,
            target_dte=10, dte_tol=2, short_delta=0.40, delta_tol=0.05,
            profit_target=0.80, exit_at_dte=2, hold_to_expiry=False,
            earnings_blackout_days=14, blackout_exdiv=True, mid_fill_prob=1.00)


def load(year):
    for d in (E.TREND, E.INDICATORS, E.HVIV, E.EVENTS, E.SECTORS,
              E.SIGNALS, E.SQUEEZE):
        d.clear()
    E.TREND.update(pickle.load(open(
        "trend23.pkl" if year == 2023 else "trend22.pkl", "rb")))
    E.EVENTS.update(pickle.load(open("events.pkl", "rb")))
    E.SECTORS.update(json.load(open("sectors_2022.json")))
    E.SIGNALS.update({k: {"ivrv": 1.0, "ts": 1.0} for k in E.TREND})


def run(lab, dbs, **ov):
    kw = dict(SPEC); kw.update(ov)
    tr = []
    for db in dbs.values():
        tr += E.run(db, E.Spec(label=lab, **kw))
    m = metrics(tr)
    ror = (100*sum(t["net_pnl"]/t["max_loss"] for t in tr if t["max_loss"])/len(tr)) if tr else 0
    from collections import Counter
    c = Counter(t["exit_reason"] for t in tr)
    expired = c.get("EXPIRED", 0)
    print(f"  {lab:<30} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
          f"expired={100*expired/len(tr) if tr else 0:>4.0f}%", flush=True)
    return lab, tr, m, ror


out = {}
for yr, dbs in ((2022, Q2_22), (2023, Q2_23)):
    load(yr)
    print()
    print("=" * 92)
    print(f"EXIT-DISCIPLINE TEST -- Q2 {yr}, condor 10DTE d0.40")
    print("=" * 92)
    out[f"{yr}_2dte"] = run(f"{yr} exit 2 DTE", dbs, exit_at_dte=2)
    out[f"{yr}_3dte"] = run(f"{yr} exit 3 DTE", dbs, exit_at_dte=3)
    out[f"{yr}_4dte"] = run(f"{yr} exit 4 DTE", dbs, exit_at_dte=4)
    out[f"{yr}_5dte"] = run(f"{yr} exit 5 DTE", dbs, exit_at_dte=5)
    out[f"{yr}_hold"] = run(f"{yr} hold to expiry", dbs,
                            exit_at_dte=-1, hold_to_expiry=True)
    # 2-leg comparison: same exit, half the legs -> better quote availability
    out[f"{yr}_vert"] = run(f"{yr} VERTICAL put, exit 2 DTE", dbs,
                            structure="bull_put", exit_at_dte=2)

pickle.dump({k: (v[1], v[2], v[3]) for k, v in out.items()},
            open("r_exitfix.pkl", "wb"))
print("\nwrote r_exitfix.pkl")
