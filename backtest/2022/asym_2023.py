"""The asymmetric spec on 2023. Spec FROZEN from the 2022 fit.

No parameter is re-tuned. Any change would convert an out-of-sample test into
an in-sample one.

BEAR CALL   5SMA < 20SMA, 9+/-2 DTE, exit 80% PT or EOD 2 DTE
BULL PUT    5SMA > 20SMA + 2 down closes, 5+/-1 DTE, exit 80% PT or EOD 1 DTE
Shared      spreads <10%, 5%/position, 1/sector, R:R >= 0.25, 14-day earnings
            gate. Two delta arms, as in the 2022 run: no cap, and 0.20-0.30.

COVERAGE CAVEAT: the supplied 2023 data is March, Q2 and Q4 only -- there is no
January/February and no Q3. That is 7 of 12 months. 2023 P&L here is therefore
NOT directly comparable to the full-year 2022 figure of +$64,854; the 2022
numbers are re-stated on the matching months for a like-for-like read.
"""
import pickle
import statistics
import spec_engine as E
from run2022 import BASE, metrics

DBS_2023 = {
    "march": "/home/user/db2023/thetadata_options_march_2023.db",
    "q2": "/home/user/db2023/thetadata_options_q2_2023.db",
    "q4": "/home/user/db2023/thetadata_options_q4_2023.db",
}
DBS_2022 = {q: f"/home/user/db2022/thetadata_options_{q}_2022.db"
            for q in ("q1", "q2", "q3", "q4")}

SPEC = dict(BASE)
SPEC.update(
    max_rel_spread=0.10, max_pct_per_position=0.05, max_per_sector=1,
    min_risk_reward=0.25, no_delta=True, earnings_blackout_days=14,
    trend_mode="asym",
    target_dte=9, dte_tol=2, exit_at_dte=2,
    put_dte=5, put_dte_tol=1, put_exit_dte=1, put_require_down=2,
    profit_target=0.80, hold_to_expiry=False,
)


def load(year):
    for d in (E.TREND, E.INDICATORS, E.HVIV, E.EVENTS, E.SECTORS, E.SIGNALS):
        d.clear()
    import json
    f = "trend23.pkl" if year == 2023 else "trend22.pkl"
    E.TREND.update(pickle.load(open(f, "rb")))
    E.EVENTS.update(pickle.load(open("events.pkl", "rb")))
    E.SECTORS.update(json.load(open("sectors_2022.json")))
    E.SIGNALS.update({k: {"ivrv": 1.0, "ts": 1.0} for k in E.TREND})


def run(label, dbs, **ov):
    kw = dict(SPEC); kw.update(ov)
    sp = E.Spec(label=label, **kw)
    tr = []
    for db in dbs.values():
        tr += E.run(db, sp)
    m = metrics(tr)
    ror = (100*sum(t["net_pnl"]/t["max_loss"] for t in tr if t["max_loss"])/len(tr)) if tr else 0.0
    bp = sum(1 for t in tr if t["structure"] == "bull_put")
    dl = [t["delta_at_entry"] for t in tr if t.get("delta_at_entry")]
    print(f"  {label:<32} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
          f"dd={m['dd']:>5.1f}% [{bp}P/{len(tr)-bp}C] "
          f"d{statistics.median(dl) if dl else 0:.2f}", flush=True)
    return label, tr, m, ror


def main():
    out = {}
    print("=" * 104)
    print("ASYMMETRIC SPEC ON 2023 -- frozen from the 2022 fit")
    print("data supplied: March + Q2 + Q4 2023 (no Jan/Feb, no Q3)")
    print("=" * 104)
    load(2023)
    out["23_nocap"] = run("2023 no delta cap", DBS_2023)
    out["23_d25"] = run("2023 delta 0.20-0.30", DBS_2023,
                        no_delta=False, short_delta=0.25, delta_tol=0.05)
    print()
    print("  2023 benchmarks (same exits, no side gate)")
    out["23_put"] = run("2023 always bull put", DBS_2023,
                        trend_mode="none", structure="bull_put")
    out["23_call"] = run("2023 always bear call", DBS_2023,
                         trend_mode="none", structure="bear_call")

    print()
    print("=" * 104)
    print("2022 RESTATED on the matching months (Mar + Q2 + Q4) for like-for-like")
    print("=" * 104)
    load(2022)
    m22 = {"march": DBS_2022["q1"], "q2": DBS_2022["q2"], "q4": DBS_2022["q4"]}
    out["22_nocap"] = run("2022 no delta cap (Mar+Q2+Q4)", m22)
    out["22_d25"] = run("2022 delta 0.20-0.30 (Mar+Q2+Q4)", m22,
                        no_delta=False, short_delta=0.25, delta_tol=0.05)

    pickle.dump({k: (v[1], v[2], v[3]) for k, v in out.items()},
                open("r23_asym.pkl", "wb"))
    print("\nwrote r23_asym.pkl")


if __name__ == "__main__":
    main()
