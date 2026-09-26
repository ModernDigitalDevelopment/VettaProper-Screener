"""Contrarian test with the user's full exit spec: 10 DTE, 80% PT, expiry-day exit.

Adds to contrarian.py:
  target_dte 10 (+/-2)
  profit_target 0.80          (already the default, stated for clarity)
  exit_friday_open=True       close ON the expiration date, not at settlement

DATA CAVEAT on the expiry-day exit: ThetaData EOD stores ONE quote snapshot per
contract-day, so "sell at the open on expiry day" is not directly observable.
The run uses the expiry-day EOD bid/ask instead. That is a CONSERVATIVE proxy:
by the close, more of the day's adverse move is already priced in, so a real
open exit should do no worse than this. Improvements shown are a lower bound.

Also re-runs the threshold sweep, because changing DTE changes which
dislocations are tradeable.
"""
import pickle
import spec_engine as E
from run2022 import BASE, load, metrics

Q2 = {"q2": "/home/user/db2022/thetadata_options_q2_2022.db"}

BASE_C = dict(BASE)
BASE_C.update(
    max_rel_spread=0.10, max_pct_per_position=0.05, max_per_sector=1,
    min_risk_reward=0.20, short_delta=0.25, delta_tol=0.05,
    earnings_blackout_days=14, trend_mode="revert",
    target_dte=10, dte_tol=2,        # 10 DTE
    profit_target=0.80,              # 80% profit target
    exit_friday_open=True,           # exit on expiry day
    hold_to_expiry=True,             # don't pre-empt with the generic exit
)


def run(label, **ov):
    kw = dict(BASE_C); kw.update(ov)
    sp = E.Spec(label=label, **kw)
    tr = []
    for db in Q2.values():
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
    print("="*98)
    print("CONTRARIAN + 10 DTE + 80% PT + EXPIRY-DAY EXIT -- Q2 2022")
    print("="*98)
    print("\nrequested threshold")
    out["r10"] = run("+/-10% (as specified)", revert_pct=10.0)
    print("\nthreshold sweep")
    for t in (3.0, 4.0, 5.0, 7.0):
        out[f"r{int(t)}"] = run(f"+/-{t:.0f}%", revert_pct=t)
    print("\nexit comparison at the best threshold (+/-3%)")
    out["r3_settle"] = run("+/-3%, settle at expiry",
                           revert_pct=3.0, exit_friday_open=False,
                           hold_to_expiry=False)
    out["r3_gamma2"] = run("+/-3%, gamma exit 2 DTE",
                           revert_pct=3.0, exit_friday_open=False,
                           hold_to_expiry=False, exit_at_dte=2)
    print("\nbenchmarks, same exits")
    out["call"] = run("always bear call", trend_mode="none",
                      structure="bear_call")
    out["put"] = run("always bull put", trend_mode="none",
                     structure="bull_put")
    pickle.dump({k: (v[1], v[2], v[3]) for k, v in out.items()},
                open("r22_contrarian2.pkl", "wb"))
    print()
    print("="*98)
    print("RANKED BY MEAN RETURN-ON-RISK")
    print("="*98)
    for k, v in sorted(out.items(), key=lambda x: -x[1][3]):
        if not v[2]["n"]:
            continue
        print(f"  {v[0]:<34} ror={v[3]:>+6.2f}%  pf={v[2]['pf']:>4.2f}  "
              f"n={v[2]['n']:>4}{'  <-- POSITIVE' if v[3] > 0 else ''}")


if __name__ == "__main__":
    main()
