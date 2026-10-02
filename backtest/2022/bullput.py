"""The user's bull-put spec, with an optional A/D timing GATE.

BASE SPEC (unchanged in every arm):
  bull puts only | spread <10% | delta 0.30 +/-0.05 | SMA10 > SMA50
  R:R >= 0.20 | 14-day earnings blackout BEFORE AND AFTER | 7-11 DTE
  5% per position | max 2 per sector | exit 80% profit or EOD 2 DTE
  never hold to expiry

GATES TESTED (on/off only -- never a side switch):
  none          control
  ad_ma         market A/D line below its own 20-day average -> stand down
  ad_break      market A/D closed below its prior swing low  -> stand down
  divergence    SPY above 50dma BUT A/D below its 20-day avg -> stand down
                (the specific pattern the user described)
  sector_ad     the SYMBOL'S OWN sector A/D below its 20-day avg -> skip that
                symbol (micro gate, others still tradeable)
  vix           VIX above its own 20-day average -> stand down
  div_or_vix    divergence OR vix elevated
  div_and_vix   divergence AND vix elevated (strictest)

Why an on/off gate is a fair test where the put-vs-call switch was not: a
switch has to be right about direction, so a lagging breadth measure inverts.
A gate only has to identify periods where selling puts is unusually dangerous,
and it is allowed to be wrong by sitting out good days -- that shows up as
lower n, not as inverted P&L.
"""
import json, pickle, sys
from collections import Counter
import spec_engine as E
from run2022 import BASE, metrics

Q = {
    "2022Q1": ("/home/user/db2022/thetadata_options_q1_2022.db", 2022),
    "2022Q2": ("/home/user/db2022/thetadata_options_q2_2022.db", 2022),
    "2022Q3": ("/home/user/db2022/thetadata_options_q3_2022.db", 2022),
    "2022Q4": ("/home/user/db2022/thetadata_options_q4_2022.db", 2022),
    "2023Mar": ("/home/user/db2023/thetadata_options_march_2023.db", 2023),
    "2023Q2": ("/home/user/db2023/thetadata_options_q2_2023.db", 2023),
    "2023Q4": ("/home/user/db2023/thetadata_options_q4_2023.db", 2023),
}

SPEC = dict(BASE)
SPEC.update(
    structure="bull_put",
    trend_mode="s10_50",              # SMA10 > SMA50
    short_delta=0.30, delta_tol=0.05,
    target_dte=9, dte_tol=2,          # 7-11 DTE
    max_rel_spread=0.10,              # spread < 10%
    min_risk_reward=0.20,
    max_pct_per_position=0.05,        # 5% per position
    max_per_sector=2,                 # 2 per sector
    max_open=12,
    max_new_per_day=4,
    earnings_blackout_days=14,        # BEFORE
    blackout_days_after_event=14,     # AND AFTER
    blackout_exdiv=False,
    profit_target=0.80,
    exit_at_dte=2,                    # EOD 2 DTE
    hold_to_expiry=False,
    mid_fill_prob=1.00,
)

_y = {}
def load(year):
    if _y.get("y") == year:
        return
    for d in (E.TREND, E.INDICATORS, E.HVIV, E.EVENTS, E.SECTORS,
              E.SIGNALS, E.SQUEEZE, E.GATE):
        d.clear()
    E.TREND.update(pickle.load(open(
        "trend23.pkl" if year == 2023 else "trend22.pkl", "rb")))
    E.EVENTS.update(pickle.load(open("events.pkl", "rb")))
    E.SECTORS.update(json.load(open("sectors_2022.json")))
    E.SIGNALS.update({k: {"ivrv": 1.0, "ts": 1.0} for k in E.TREND})
    _y["y"] = year


def build_gates():
    """Return name -> {date: blocked} for market gates, plus sector gate map."""
    b = pickle.load(open("breadth_all.pkl", "rb"))
    m = pickle.load(open("macro.pkl", "rb"))
    mk = {d: v for (k, d), v in b.items() if k == "MARKET"}
    gates = {}
    gates["ad_ma"] = {d: v["ad_below_ma20"] == 1 for d, v in mk.items()}
    gates["ad_break"] = {d: v["ad_break_low"] == 1 for d, v in mk.items()}
    gates["divergence"] = {d: v.get("divergence", 0) == 1 for d, v in mk.items()}
    vix = {d: (m[d]["vix"] is not None and m[d]["vix_ma20"] is not None
               and m[d]["vix"] > m[d]["vix_ma20"]) for d in m}
    gates["vix"] = vix
    gates["div_or_vix"] = {d: gates["divergence"].get(d, False) or vix.get(d, False)
                           for d in mk}
    gates["div_and_vix"] = {d: gates["divergence"].get(d, False) and vix.get(d, False)
                            for d in mk}
    sect = {(k, d): v["ad_below_ma20"] == 1 for (k, d), v in b.items()}
    return gates, sect


def run(lab, dbs, gate=None, sector_gate=None):
    E.GATE.clear()
    if gate:
        E.GATE.update({("MARKET", d): bool(x) for d, x in gate.items()})
    if sector_gate:
        E.GATE.update({k: bool(v) for k, v in sector_gate.items()})
    kw = dict(SPEC)
    kw["gate_mode"] = ("sector" if sector_gate else ("market" if gate else ""))
    tr = []
    for db in dbs:
        tr += E.run(db, E.Spec(label=lab, **kw))
    m = metrics(tr)
    ror = (100*sum(t["net_pnl"]/t["max_loss"] for t in tr if t["max_loss"])/len(tr)) if tr else 0
    w = [t["net_pnl"] for t in tr if t["net_pnl"]>0]
    l = [t["net_pnl"] for t in tr if t["net_pnl"]<=0]
    lw = (abs(sum(l)/len(l))/(sum(w)/len(w))) if w and l else 0
    print(f"  {lab:<22} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
          f"L/W={lw:>4.2f} dd={m['dd']:>5.1f}%", flush=True)
    return lab, tr, m, ror, lw


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "2022"
    keys = [k for k in Q if k.startswith(which)] if which != "all" else list(Q)
    gates, sect = build_gates()
    yr = Q[keys[0]][1]
    load(yr)
    dbs = [Q[k][0] for k in keys]
    print()
    print("=" * 96)
    print(f"BULL PUTS + A/D TIMING GATE -- {which}  ({', '.join(keys)})")
    print("=" * 96)
    out = {}
    out["none"] = run("no gate (control)", dbs)
    for g in ("ad_ma", "ad_break", "divergence", "vix",
              "div_or_vix", "div_and_vix"):
        out[g] = run(f"gate: {g}", dbs, gate=gates[g])
    out["sector_ad"] = run("gate: sector A/D", dbs, sector_gate=sect)
    try:
        prev = pickle.load(open("r_bullput.pkl", "rb"))
    except Exception:
        prev = {}
    prev[which] = {k: (v[1], v[2], v[3], v[4]) for k, v in out.items()}
    pickle.dump(prev, open("r_bullput.pkl", "wb"))
    print(f"\nwrote r_bullput.pkl [{which}]")


if __name__ == "__main__":
    main()
