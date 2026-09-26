"""Dial in the 10 DTE / delta 0.40 condor. Q2 2022 and Q2 2023 only.

Changes from the grid, as specified:
  5% per position  (unchanged)
  2 positions per SECTOR  (was 1)
  exit at 80% profit OR EOD 1 DTE -- the day BEFORE expiry (was 2 DTE)
  + Keltner squeeze arm

Squeeze context, stated rather than assumed: the 6.5pp tercile separation in
docs/INDICATORS.md is real but was measured on 2,129 BULL PUT trades, not
condors, and kc_squeeze is binary so a tercile split on it is loose. It is a
plausible hypothesis here, not an established result.

SQUEEZE DATA CAVEAT: the squeeze needs a true ATR. 2022 uses real high/low.
2023 has closes only, so its range is synthesised from close-to-close moves,
which biases ATR LOW, narrows the Keltner channel and therefore makes the
squeeze fire LESS often (measured: 7.3% of 2022 rows vs 1.7% of 2023 rows;
median ATR20 3.06% vs 1.89%). The 2023 squeeze arm will have a small n for
that reason, and its rate is NOT comparable to 2022's.
"""
import json
import pickle
import statistics

import spec_engine as E
from run2022 import BASE, metrics

Q2_2022 = {"q2": "/home/user/db2022/thetadata_options_q2_2022.db"}
Q2_2023 = {"q2": "/home/user/db2023/thetadata_options_q2_2023.db"}

SPEC = dict(BASE)
SPEC.update(
    structure="iron_condor",
    trend_mode="none",
    max_rel_spread=0.20,
    max_pct_per_position=0.05,     # 5% per position
    max_per_sector=2,              # 2 per sector
    min_risk_reward=0.20,
    target_dte=10, dte_tol=2,
    short_delta=0.40, delta_tol=0.05,
    profit_target=0.80,
    exit_at_dte=1,                 # EOD the day BEFORE expiry
    hold_to_expiry=False,
    earnings_blackout_days=14,
    blackout_exdiv=True,
    mid_fill_prob=1.00,
)


def load(year):
    for d in (E.TREND, E.INDICATORS, E.HVIV, E.EVENTS,
              E.SECTORS, E.SIGNALS, E.SQUEEZE):
        d.clear()
    E.TREND.update(pickle.load(open(
        "trend23.pkl" if year == 2023 else "trend22.pkl", "rb")))
    E.EVENTS.update(pickle.load(open("events.pkl", "rb")))
    E.SECTORS.update(json.load(open("sectors_2022.json")))
    E.SQUEEZE.update(pickle.load(open("squeeze.pkl", "rb")))
    E.SIGNALS.update({k: {"ivrv": 1.0, "ts": 1.0} for k in E.TREND})


def run(label, dbs, **ov):
    kw = dict(SPEC); kw.update(ov)
    sp = E.Spec(label=label, **kw)
    tr = []
    for db in dbs.values():
        tr += E.run(db, sp)
    m = metrics(tr)
    ror = (100 * sum(t["net_pnl"] / t["max_loss"]
                     for t in tr if t["max_loss"]) / len(tr)) if tr else 0.0
    print(f"  {label:<36} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
          f"dd={m['dd']:>6.1f}%", flush=True)
    return label, tr, m, ror


def main():
    out = {}
    for year, dbs in ((2022, Q2_2022), (2023, Q2_2023)):
        load(year)
        print()
        print("=" * 100)
        print(f"CONDOR TUNE -- Q2 {year}   10 DTE, delta 0.40, 5%/pos, "
              f"2/sector, exit 80% or EOD 1 DTE")
        print("=" * 100)
        out[f"{year}_base"] = run(f"{year} tuned base", dbs)
        out[f"{year}_sq"] = run(f"{year} + Keltner squeeze", dbs,
                                require_squeeze=True)
        print("  references")
        out[f"{year}_1sec"] = run(f"{year} 1/sector (old cap)", dbs,
                                  max_per_sector=1)
        out[f"{year}_2dte"] = run(f"{year} exit 2 DTE (old exit)", dbs,
                                  exit_at_dte=2)
        out[f"{year}_noblk"] = run(f"{year} no event block", dbs,
                                   earnings_blackout_days=0,
                                   blackout_exdiv=False)
    pickle.dump({k: (v[1], v[2], v[3]) for k, v in out.items()},
                open("r_condor_tune.pkl", "wb"))
    print("\nwrote r_condor_tune.pkl")


if __name__ == "__main__":
    main()
