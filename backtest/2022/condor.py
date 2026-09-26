"""Iron condors, 2022 and 2023. The first structure needing no direction call.

Grid, as specified:
  DTE           10, 20, 30  (+/-2)
  short delta   0.30, 0.40, 0.50  (+/-0.05)
  event block   with (14-day earnings + ex-div) and without
  exit          EOD at 2 DTE, or 80% profit target
  spreads       < 20% relative bid/ask
= 18 configs per year, 36 total.

Why a condor is worth testing after nine failed direction filters: it sells
both sides at once, so it never needs to know which way the market goes. The
structural finding that survived both years -- premium harvesting with a tight
gamma exit -- is preserved, while the part that kept breaking (side selection)
is removed entirely.

DELTA 0.50 CAVEAT, measured before running: at delta 0.50 the short put and
short call converge on the same ATM strike (124 of 125 sampled pairs had
call_short <= put_short). That is a short straddle with inverted wings, not a
condor, and its max loss is not the wider wing. The engine now REJECTS those
rather than mis-pricing them, so delta-0.50 rows will show reduced n -- that is
correct behaviour, not missing data.

2023 coverage is March + Q2 + Q4 only (no Jan/Feb, no Q3), so 2022 is also
reported on matching months for a like-for-like read.
"""
import json
import pickle
import statistics
import sys

import spec_engine as E
from run2022 import BASE, metrics

DBS_2022 = {q: f"/home/user/db2022/thetadata_options_{q}_2022.db"
            for q in ("q1", "q2", "q3", "q4")}
DBS_2023 = {
    "march": "/home/user/db2023/thetadata_options_march_2023.db",
    "q2": "/home/user/db2023/thetadata_options_q2_2023.db",
    "q4": "/home/user/db2023/thetadata_options_q4_2023.db",
}
# 2022 months matching the 2023 sample
DBS_2022_MATCH = {"march": DBS_2022["q1"], "q2": DBS_2022["q2"],
                  "q4": DBS_2022["q4"]}

SPEC = dict(BASE)
SPEC.update(
    structure="iron_condor",
    trend_mode="none",          # no direction call at all -- the whole point
    max_rel_spread=0.20,        # spreads < 20%
    max_pct_per_position=0.05,
    max_per_sector=1,
    min_risk_reward=0.20,
    profit_target=0.80,
    exit_at_dte=2,              # EOD 2 DTE before expiry
    hold_to_expiry=False,
    mid_fill_prob=1.00,
)


def load(year):
    for d in (E.TREND, E.INDICATORS, E.HVIV, E.EVENTS, E.SECTORS, E.SIGNALS):
        d.clear()
    E.TREND.update(pickle.load(open(
        "trend23.pkl" if year == 2023 else "trend22.pkl", "rb")))
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
    ror = (100 * sum(t["net_pnl"] / t["max_loss"]
                     for t in tr if t["max_loss"]) / len(tr)) if tr else 0.0
    dl = [t["delta_at_entry"] for t in tr if t.get("delta_at_entry")]
    print(f"  {label:<34} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
          f"dd={m['dd']:>6.1f}%", flush=True)
    return label, tr, m, ror


def grid(year, dbs, tag):
    load(year)
    out = {}
    print()
    print("=" * 98)
    print(f"IRON CONDORS -- {tag}")
    print("=" * 98)
    for blk, blab in ((True, "block"), (False, "noblk")):
        for dte in (10, 20, 30):
            for dl in (0.30, 0.40, 0.50):
                lab = f"{dte}DTE d{dl:.2f} {blab}"
                key = f"{tag}_{dte}_{int(dl*100)}_{blab}"
                out[key] = run(lab, dbs,
                               target_dte=dte, dte_tol=2,
                               short_delta=dl, delta_tol=0.05,
                               earnings_blackout_days=14 if blk else 0,
                               blackout_exdiv=blk)
    return out


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out = {}
    if which in ("2022", "all"):
        out.update(grid(2022, DBS_2022, "2022 FULL YEAR"))
        pickle.dump(out, open("r_condor.pkl", "wb"))
    if which in ("2023", "all"):
        out.update(grid(2023, DBS_2023, "2023 (Mar+Q2+Q4)"))
        pickle.dump(out, open("r_condor.pkl", "wb"))
    if which in ("match", "all"):
        out.update(grid(2022, DBS_2022_MATCH, "2022 MATCHED MONTHS"))
        pickle.dump(out, open("r_condor.pkl", "wb"))
    print("\nwrote r_condor.pkl")


if __name__ == "__main__":
    main()
