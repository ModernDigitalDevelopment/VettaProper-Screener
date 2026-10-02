"""Bull puts at 35-45 DTE, exit 10-15 DTE, with a vol-of-vol cash gate.

Q2 2023 only, to keep the cost down.

BASE (the user's best bull-put spec, unchanged):
  bull puts | spread <10% | delta 0.30 +/-0.05 | SMA10 > SMA50 | R:R >= 0.20
  14-day earnings blackout BEFORE AND AFTER | 5%/position | max 2 per sector
  80% profit target | never hold to expiry

CHANGED, as requested:
  entry DTE   40 +/- 5   (35-45, was 7-11)
  exit        at 12 DTE  (10-15 band, was 2 DTE)

VVIX CAVEAT -- this is the one thing I could not do as asked. VVIX is NOT in
this dataset: 0 rows for VVIX/^VVIX in the option DBs, no VVIX file, and
vix.json carries the VIX index only. Rather than invent a series, the gate uses
20-day realised volatility OF the VIX index -- the same economic quantity VVIX
prices, but realised rather than implied, and on a different scale (medians 88
vs VVIX's ~95-100). A literal ">100" threshold therefore cannot be mapped onto
it honestly, so the gate is expressed as a PERCENTILE of its own trailing
252-day distribution. The 70th/80th/90th are all run so the sensitivity is
visible rather than hidden in one arbitrary cut.
"""
import json, pickle, sys
import spec_engine as E
from run2022 import BASE, metrics

DB = "/home/user/db2023/thetadata_options_q2_2023.db"

SPEC = dict(BASE)
SPEC.update(
    structure="bull_put",
    trend_mode="s10_50",
    short_delta=0.30, delta_tol=0.05,
    max_rel_spread=0.10,
    min_risk_reward=0.20,
    max_pct_per_position=0.05,
    max_per_sector=2,
    max_open=12,
    max_new_per_day=4,
    earnings_blackout_days=14,
    blackout_days_after_event=14,
    blackout_exdiv=False,
    profit_target=0.80,
    hold_to_expiry=False,
    mid_fill_prob=1.00,
)


def load():
    for d in (E.TREND, E.INDICATORS, E.HVIV, E.EVENTS, E.SECTORS,
              E.SIGNALS, E.SQUEEZE, E.GATE):
        d.clear()
    E.TREND.update(pickle.load(open("trend23.pkl", "rb")))
    E.EVENTS.update(pickle.load(open("events.pkl", "rb")))
    E.SECTORS.update(json.load(open("sectors_2022.json")))
    E.SIGNALS.update({k: {"ivrv": 1.0, "ts": 1.0} for k in E.TREND})


def run(lab, gate_pct=None, **ov):
    E.GATE.clear()
    gm = ""
    if gate_pct is not None:
        vv = pickle.load(open("volvol.pkl", "rb"))
        E.GATE.update({("MARKET", d): (v["pctile"] >= gate_pct)
                       for d, v in vv.items()})
        gm = "market"
    kw = dict(SPEC); kw.update(ov); kw["gate_mode"] = gm
    tr = E.run(DB, E.Spec(label=lab, **kw))
    m = metrics(tr)
    ror = (100*sum(t["net_pnl"]/t["max_loss"] for t in tr if t["max_loss"])/len(tr)) if tr else 0
    w = [t["net_pnl"] for t in tr if t["net_pnl"]>0]
    l = [t["net_pnl"] for t in tr if t["net_pnl"]<=0]
    lw = (abs(sum(l)/len(l))/(sum(w)/len(w))) if w and l else 0
    from collections import Counter
    c = Counter(t["exit_reason"] for t in tr)
    exp = 100*c.get("EXPIRED",0)/len(tr) if tr else 0
    print(f"  {lab:<34} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
          f"L/W={lw:>4.2f} dd={m['dd']:>5.1f}% exp={exp:>4.1f}%", flush=True)
    return lab, tr, m, ror, lw


def main():
    load()
    out = {}
    print("=" * 104)
    print("Q2 2023 -- BULL PUTS, 35-45 DTE ENTRY / 10-15 DTE EXIT")
    print("=" * 104)
    print("\nreference: the short-dated spec")
    out["short"] = run("7-11 DTE entry, exit 2 DTE",
                       target_dte=9, dte_tol=2, exit_at_dte=2)
    print("\nthe requested change")
    out["long12"] = run("35-45 DTE entry, exit 12 DTE",
                        target_dte=40, dte_tol=5, exit_at_dte=12)
    out["long10"] = run("35-45 DTE entry, exit 10 DTE",
                        target_dte=40, dte_tol=5, exit_at_dte=10)
    out["long15"] = run("35-45 DTE entry, exit 15 DTE",
                        target_dte=40, dte_tol=5, exit_at_dte=15)
    print("\n+ vol-of-vol cash gate (percentile of its own trailing year)")
    for p in (70, 80, 90):
        out[f"g{p}"] = run(f"35-45 DTE, exit 12, gate p{p}",
                           gate_pct=p, target_dte=40, dte_tol=5, exit_at_dte=12)
    pickle.dump({k: (v[1], v[2], v[3], v[4]) for k, v in out.items()},
                open("r_longdte.pkl", "wb"))
    print("\nwrote r_longdte.pkl")


if __name__ == "__main__":
    main()
