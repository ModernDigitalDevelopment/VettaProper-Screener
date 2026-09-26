"""Bear calls on 2022, with parameters identical to the bull puts.

Same delta (0.25 +/- 0.05), same R:R floor (0.20), same width, same DTE window,
same 14-day earnings blackout, same sizing, same 1-per-sector cap. The ONLY
change is which side of the market the spread is sold on, plus a trend gate
that points down instead of up.

Three questions, in order:
  1. Does a bear call make money in 2022 at all? (if no, switching is moot)
  2. Which entry gate is best for the short side?
  3. Does a per-symbol switch beat always-puts and always-calls?
"""
import pickle
import sys

import spec_engine as E
from run2022 import BASE, DBS_2022, load, metrics

BLANK = " " * 34


def spec(label='x', **kw):
    d = dict(BASE)
    d.update(kw)
    return E.Spec(label=label, **d)


def run(name, sp):
    trades = []
    for db in DBS_2022.values():
        trades += E.run(db, sp)
    m = metrics(trades)
    print(f"{name:<34} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} dd={m['dd']:>5.1f}%")
    return trades, m


def main():
    load()
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out = {}

    print("=" * 88)
    print("BEAR CALLS 2022 -- identical parameters, inverted side")
    print("=" * 88)
    print()

    # Reference: the bull put baseline we are trying to beat.
    print("reference (bull puts, unchanged spec)")
    out["bull_put_base"] = run("  bull puts, s10_50 trend", spec())
    print()

    print("bear calls, varying the entry gate")
    # no trend filter at all -- pure delta/RR selection on the call side
    out["bc_none"] = run("  bear call, no trend gate",
                         spec(structure="bear_call", trend_mode="none"))
    # mirror of the bull-put gate: price below the 50
    out["bc_below50"] = run("  bear call, price < 50 SMA",
                            spec(structure="bear_call", trend_mode="below50"))
    print()

    print("bear calls + per-symbol momentum gates")
    out["bc_rsi50"] = run("  bear call, <50 SMA, RSI<50",
                          spec(structure="bear_call", trend_mode="below50",
                               rsi_lo2=0.0, rsi_hi2=50.0))
    out["bc_rsi40"] = run("  bear call, <50 SMA, RSI<40",
                          spec(structure="bear_call", trend_mode="below50",
                               rsi_lo2=0.0, rsi_hi2=40.0))
    out["bc_adx25"] = run("  bear call, <50 SMA, ADX>=25",
                          spec(structure="bear_call", trend_mode="below50",
                               min_adx=25.0))
    out["bc_hviv"] = run("  bear call, <50 SMA, HV>IV",
                         spec(structure="bear_call", trend_mode="below50",
                              require_hv_gt_iv=True))
    print()

    pickle.dump(out, open("r22_bearcall.pkl", "wb"))
    print("wrote r22_bearcall.pkl")


if __name__ == "__main__":
    main()
