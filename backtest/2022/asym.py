"""Asymmetric per-side spec, Q2 2022.

Shared:  spreads <10%, 5%/position, 1/sector, R:R >= 0.25,
         NO delta parameter, 14-day earnings gate.

BEAR CALL leg   5 SMA under 20 SMA
                9 DTE +/- 2
                exit at 80% profit or EOD 2 DTE

BULL PUT leg    5 SMA over 20 SMA AND the last two closes were down
                5 DTE +/- 1
                exit at 80% profit or EOD 1 DTE (day before expiry)

Rationale for the asymmetry, from the Q2 contrarian run: calls sold into
downtrends won 100% of the time while puts sold into dislocations won 57%.
This spec keeps the call leg trend-following and makes the put leg a
pullback-in-uptrend entry with a much shorter tenor, so it carries less
exposure through the move it is betting against.

"No delta parameter" is implemented as literally no delta constraint: any OTM
strike clearing the spread filter is eligible and the richest premium wins,
with the R:R >= 0.25 floor doing the risk work. The delta actually selected is
reported below, because "no delta limit" and "no idea what delta we got" are
different things.
"""
import pickle
import statistics
import spec_engine as E
from run2022 import BASE, load, metrics

Q2 = {"q2": "/home/user/db2022/thetadata_options_q2_2022.db"}

SPEC = dict(BASE)
SPEC.update(
    max_rel_spread=0.10,
    max_pct_per_position=0.05,
    max_per_sector=1,
    min_risk_reward=0.25,
    no_delta=True,
    earnings_blackout_days=14,
    trend_mode="asym",
    target_dte=9, dte_tol=2,          # call leg
    exit_at_dte=2,                    # call leg exit
    put_dte=5, put_dte_tol=1,         # put leg
    put_exit_dte=1,                   # put leg exit
    put_require_down=2,
    profit_target=0.80,
    hold_to_expiry=False,
)


def run(label, **ov):
    kw = dict(SPEC); kw.update(ov)
    sp = E.Spec(label=label, **kw)
    tr = []
    for db in Q2.values():
        tr += E.run(db, sp)
    m = metrics(tr)
    ror = (100*sum(t["net_pnl"]/t["max_loss"] for t in tr if t["max_loss"])/len(tr)) if tr else 0.0
    bp = sum(1 for t in tr if t["structure"] == "bull_put")
    print(f"  {label:<36} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+8,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
          f"dd={m['dd']:>5.1f}%  [{bp}P/{len(tr)-bp}C]", flush=True)
    return label, tr, m, ror


def side_detail(tr, name):
    print(f"\n  {name} -- by side")
    for side in ("bull_put", "bear_call"):
        g = [t for t in tr if t["structure"] == side]
        if not g:
            print(f"    {side:<11} (none)")
            continue
        w = sum(1 for t in g if t["net_pnl"] > 0)
        ror = 100*sum(t["net_pnl"]/t["max_loss"] for t in g if t["max_loss"])/len(g)
        dl = [t["delta_at_entry"] for t in g if t.get("delta_at_entry")]
        dd = [t["dte_at_entry"] for t in g]
        print(f"    {side:<11} n={len(g):>3} win={100*w/len(g):>5.1f}% "
              f"net={sum(t['net_pnl'] for t in g):>+8,.0f} ror={ror:>+6.1f}% "
              f"| delta med {statistics.median(dl) if dl else 0:.3f} "
              f"| dte med {statistics.median(dd):.0f}")


def main():
    load()
    out = {}
    print("=" * 100)
    print("ASYMMETRIC SPEC -- Q2 2022 (Apr-Jun)")
    print("call: 5<20 SMA, 9+/-2 DTE, exit 2 DTE | put: 5>20 SMA + 2 down days,")
    print("5+/-1 DTE, exit 1 DTE | R:R>=0.25, no delta cap, 5%/pos, 1/sector")
    print("=" * 100)
    print("\nas specified")
    out["spec"] = run("full asymmetric spec")
    side_detail(out["spec"][1], "full asymmetric spec")

    print("\n\nisolate each leg")
    out["call"] = run("call leg only", structure="bear_call")
    out["put"] = run("put leg only", structure="bull_put")

    print("\nsensitivity: down-day requirement on the put leg")
    out["d1"] = run("put needs 1 down day", put_require_down=1)
    out["d0"] = run("put needs 0 down days", put_require_down=0)

    print("\nsensitivity: does the no-delta rule hurt?")
    out["d25"] = run("same, delta 0.20-0.30", no_delta=False,
                     short_delta=0.25, delta_tol=0.05)

    print("\nreference: R:R floor at 0.20")
    out["rr20"] = run("same, R:R >= 0.20", min_risk_reward=0.20)

    pickle.dump({k: (v[1], v[2], v[3]) for k, v in out.items()},
                open("r22_asym.pkl", "wb"))

    print()
    print("=" * 100)
    print("RANKED BY MEAN RETURN-ON-RISK")
    print("=" * 100)
    for k, v in sorted(out.items(), key=lambda x: -x[1][3]):
        if not v[2]["n"]:
            continue
        print(f"  {v[0]:<36} ror={v[3]:>+6.2f}%  pf={v[2]['pf']:>4.2f}  "
              f"n={v[2]['n']:>4}{'  <-- POSITIVE' if v[3] > 0 else ''}")


if __name__ == "__main__":
    main()
