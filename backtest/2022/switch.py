"""Per-symbol side switching: bull put when the symbol is up, bear call when down.

The switch reads ONLY that symbol's own trend. No SPY, no VIX, no market-wide
input -- because 2022 had two up months inside a down year, and a market-level
switch would have sat out exactly the months that made money.

Three switch rules, all per-symbol:
  sma50  close and sma10 both above/below the 50-day
  rsi    RSI(14) above/below 50
  dmi    +DI above/below -DI

The honest test is not "does it beat bull puts in 2022" -- selling calls in a
down year is trivially good. It is whether the SAME rule also survives 2023,
when bull puts won. A rule that only works in the year it was fitted on is a
description of 2022, not a signal.
"""
import json
import pickle
import sys

import spec_engine as E
from run2022 import BASE, DBS_2022, load, metrics

DBS_2023 = {q: f"/home/user/db/thetadata_options_{q}_2023.db"
            for q in ("q1", "q2", "q3", "q4")}


def load_2023():
    for d in (E.TREND, E.INDICATORS, E.HVIV, E.EVENTS, E.SECTORS, E.SIGNALS):
        d.clear()
    E.TREND.update(pickle.load(open("trend.pkl", "rb")))
    E.INDICATORS.update(pickle.load(open("indicators_slim.pkl", "rb")))
    E.EVENTS.update(pickle.load(open("events.pkl", "rb")))
    E.SECTORS.update(json.load(open("sectors_2022.json")))
    E.SIGNALS.update(pickle.load(open("signals.pkl", "rb")))


def run(name, dbs, **kw):
    d = dict(BASE)
    d.update(kw)
    sp = E.Spec(label=name, **d)
    trades = []
    for db in dbs.values():
        trades += E.run(db, sp)
    m = metrics(trades)
    mix = ""
    if trades:
        bp = sum(1 for t in trades if t["structure"] == "bull_put")
        bc = len(trades) - bp
        mix = f"  [{bp}P/{bc}C]"
    print(f"{name:<36} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} dd={m['dd']:>5.1f}%{mix}")
    return trades, m


def main():
    out = {}
    year = sys.argv[1] if len(sys.argv) > 1 else "both"

    if year in ("2022", "both"):
        load()
        print("=" * 96)
        print("2022  (bear year -- bull puts lost $38,512 here)")
        print("=" * 96)
        out["22_put"] = run("  always bull put", DBS_2022)
        out["22_call"] = run("  always bear call", DBS_2022,
                             structure="bear_call", trend_mode="below50")
        for sm in ("sma50", "rsi", "dmi"):
            out[f"22_sw_{sm}"] = run(f"  SWITCH per-symbol ({sm})", DBS_2022,
                                     structure="auto", trend_mode="auto",
                                     switch_mode=sm)
        print()

    if year in ("2023", "both"):
        load_2023()
        print("=" * 96)
        print("2023  (bull year -- the year the strategy was built on)")
        print("=" * 96)
        out["23_put"] = run("  always bull put", DBS_2023)
        out["23_call"] = run("  always bear call", DBS_2023,
                             structure="bear_call", trend_mode="below50")
        for sm in ("sma50", "rsi", "dmi"):
            out[f"23_sw_{sm}"] = run(f"  SWITCH per-symbol ({sm})", DBS_2023,
                                     structure="auto", trend_mode="auto",
                                     switch_mode=sm)
        print()

    pickle.dump(out, open(f"r_switch_{year}.pkl", "wb"))
    print(f"wrote r_switch_{year}.pkl")


if __name__ == "__main__":
    main()
