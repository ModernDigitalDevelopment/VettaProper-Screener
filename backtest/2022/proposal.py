"""THE PROPOSAL, run exactly as specified, on every quarter available.

STRUCTURE     iron condor
SHORT DELTA   0.35 +/- 0.05
ENTRY DTE     10 +/- 2
SIZING        2% of equity, cap 10 contracts
CAPS          10 open, 1/sector, 3 new/day
EVENTS        block 14 days BEFORE and AFTER earnings + ex-div
EXIT          80% profit OR 3 DTE mandatory; never hold to expiry
SPREAD        relative bid/ask < 20%
R:R           credit/max-loss >= 0.20

Run per quarter so partial results survive an interruption. 2022 has all four
quarters; 2023 has March, Q2 and Q4 only (no Jan/Feb, no Q3).
"""
import json, pickle, sys
from collections import Counter, defaultdict
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
    structure="iron_condor",
    trend_mode="none",
    short_delta=0.35, delta_tol=0.05,
    target_dte=10, dte_tol=2,
    width=5.0, width_tol=5.1,
    max_rel_spread=0.20,
    min_risk_reward=0.20,
    max_pct_per_position=0.02,          # 2% of equity
    max_contracts=10,                   # hard cap
    max_open=10,
    max_per_sector=1,
    max_new_per_day=3,
    earnings_blackout_days=14,          # 14 days BEFORE
    blackout_days_after_event=14,       # 14 days AFTER
    blackout_exdiv=True,                # earnings + ex-div
    profit_target=0.80,
    exit_at_dte=3,                      # mandatory 3-DTE exit
    hold_to_expiry=False,
    mid_fill_prob=1.00,
    rank_mode="cw",                     # rank by credit/width
)

_cache = {}
def load(year):
    if _cache.get("y") == year:
        return
    for d in (E.TREND, E.INDICATORS, E.HVIV, E.EVENTS, E.SECTORS,
              E.SIGNALS, E.SQUEEZE):
        d.clear()
    E.TREND.update(pickle.load(open(
        "trend23.pkl" if year == 2023 else "trend22.pkl", "rb")))
    E.EVENTS.update(pickle.load(open("events.pkl", "rb")))
    E.SECTORS.update(json.load(open("sectors_2022.json")))
    E.SIGNALS.update({k: {"ivrv": 1.0, "ts": 1.0} for k in E.TREND})
    _cache["y"] = year


def main():
    keys = sys.argv[1:] or list(Q)
    try:
        out = pickle.load(open("r_proposal.pkl", "rb"))
    except Exception:
        out = {}
    for k in keys:
        db, yr = Q[k]
        load(yr)
        tr = E.run(db, E.Spec(label=k, **SPEC))
        m = metrics(tr)
        ror = (100*sum(t["net_pnl"]/t["max_loss"] for t in tr if t["max_loss"])/len(tr)) if tr else 0
        w = [t["net_pnl"] for t in tr if t["net_pnl"] > 0]
        l = [t["net_pnl"] for t in tr if t["net_pnl"] <= 0]
        lw = (abs(sum(l)/len(l))/(sum(w)/len(w))) if w and l else 0
        c = Counter(t["exit_reason"] for t in tr)
        exp = 100*c.get("EXPIRED", 0)/len(tr) if tr else 0
        print(f"  {k:<9} n={m['n']:>4} win={m['win']:>5.1f}% "
              f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
              f"L/W={lw:>4.2f} dd={m['dd']:>5.1f}% expired={exp:>4.1f}%",
              flush=True)
        out[k] = (tr, m, ror, lw)
        pickle.dump(out, open("r_proposal.pkl", "wb"))


if __name__ == "__main__":
    main()
