"""A+C got to PF 0.93 / RoR -1.04%. What closes the last gap to 1.00?

The sizing sweep proved sizing does NOT change expectancy -- mean return-on-risk
is identical (-1.04%) at every position size. Sizing controls survival, not
edge. So profitability has to come from selection or exits.

A+C is close: PF 0.93, mean RoR -1.04%, loss/win 2.29x (from 3.47x). The gap is
small enough that a genuinely better exit or a modest credit filter might close
it. Tested here, all stacked on A+C:

  profit target     take profit earlier (80% is the current default)
  exit DTE          is 2 the right gamma cutoff, or 3/4?
  min credit        skip the thinnest premium, which pays worst per unit risk
  min R:R           tighten the 0.20 floor
  width             does a wider spread pay better per dollar risked?

IMPORTANT: this is a search over ~14 configs on one year. Anything that wins
here is a HYPOTHESIS, not a finding -- it needs 2023 to confirm. Recording that
up front so the result is not over-read later.
"""
import pickle

import spec_engine as E
from run2022 import BASE, DBS_2022, load, metrics

AC = dict(require_hv_gt_iv=True, exit_at_dte=2)


def run(label, **ov):
    kw = dict(BASE)
    kw.update(AC)
    kw.update(ov)
    sp = E.Spec(label=label, **kw)
    tr = []
    for db in DBS_2022.values():
        tr += E.run(db, sp)
    m = metrics(tr)
    ror = (100 * sum(t["net_pnl"] / t["max_loss"] for t in tr if t["max_loss"])
           / len(tr)) if tr else 0.0
    print(f"  {label:<34} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+8,.0f} pf={m['pf']:>4.2f} "
          f"ror={ror:>+6.2f}% dd={m['dd']:>5.1f}%", flush=True)
    return label, tr, m, ror


def main():
    load()
    out = {}
    print("=" * 94)
    print("A+C VARIANTS  (HV>IV + exit 2 DTE, 7.5% sizing throughout)")
    print("baseline A+C: PF 0.93, RoR -1.04%")
    print("=" * 94)

    print("\nprofit target")
    for pt in (0.80, 0.65, 0.50, 0.40):
        out[f"pt{pt}"] = run(f"profit target {pt:.0%}", profit_target=pt)

    print("\ngamma exit cutoff")
    for dte in (1, 2, 3, 4):
        out[f"dte{dte}"] = run(f"exit at {dte} DTE", exit_at_dte=dte)

    print("\nminimum credit")
    for mc in (0.10, 0.25, 0.40, 0.60):
        out[f"mc{mc}"] = run(f"min credit ${mc:.2f}", min_credit=mc)

    print("\nminimum risk/reward")
    for rr in (0.20, 0.25, 0.30, 0.40):
        out[f"rr{rr}"] = run(f"min R:R {rr:.2f}", min_risk_reward=rr)

    pickle.dump({k: (v[1], v[2], v[3]) for k, v in out.items()},
                open("r22_stack2.pkl", "wb"))

    print()
    print("=" * 94)
    print("RANKED BY MEAN RETURN-ON-RISK  (size-independent measure of edge)")
    print("=" * 94)
    for k, v in sorted(out.items(), key=lambda x: -x[1][3])[:10]:
        m = v[2]
        flag = "  <-- POSITIVE" if v[3] > 0 else ""
        print(f"  {v[0]:<34} ror={v[3]:>+6.2f}%  pf={m['pf']:>4.2f}  "
              f"n={m['n']:>4}{flag}")
    print()
    print("  Reminder: ~16 configs searched on one year. A winner here is a")
    print("  hypothesis requiring 2023 confirmation, not a finding.")


if __name__ == "__main__":
    main()
