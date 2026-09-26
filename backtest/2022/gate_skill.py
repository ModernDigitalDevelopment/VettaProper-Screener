"""Does the gate have SKILL, or is 2023 just a low-volatility year?

A short call is breached by a big rally. In a calm year fewer things move 6%,
so the breach rate falls whether or not the gate is choosing well. The control
is therefore the breach rate of a RANDOM selection from the same universe on
the same dates -- if the gate's rate is no better, it has no skill and the
2023 improvement is simply lower vol.
"""
import pickle
import random
from collections import defaultdict

BREACH = 6.0
HOLD = 9


def universe(year):
    import csv, gzip
    px = defaultdict(dict)
    if year == 2022:
        with gzip.open("/home/user/vps/backtest/data/daily_2022.csv.gz", "rt") as fh:
            for r in csv.DictReader(fh):
                px[r["symbol"]][r["date"]] = float(r["close"])
    t = pickle.load(open("trend.pkl", "rb"))
    for (sym, d), v in t.items():
        px[sym][d] = v["close"]
    return px


def main():
    print("GATE SKILL vs A RANDOM SELECTION -- short-call breach rate")
    print("=" * 80)
    print(f"breach = underlying rallies >= {BREACH:.0f}% within {HOLD} sessions")
    print()
    for year in (2022, 2023):
        px = universe(year)
        recs = pickle.load(open(f"asym_gate_{year}.pkl", "rb"))
        gate = [r for r in recs if r["side"] == "bear_call"]
        gate_rate = sum(1 for r in gate if r["breached"]) / len(gate)

        # random control: same dates, random symbols, same holding period
        dates = defaultdict(list)
        for r in gate:
            dates[r["date"]].append(r["sym"])
        rng = random.Random(5)
        allsyms = [s for s in px if len(px[s]) > 60]
        hits = n = 0
        for d, syms in dates.items():
            for _ in syms:
                for _try in range(6):
                    s = rng.choice(allsyms)
                    ds = sorted(px[s])
                    if d not in px[s]:
                        continue
                    i = ds.index(d)
                    j = min(i + HOLD, len(ds) - 1)
                    if j <= i:
                        continue
                    spot = px[s][d]
                    hi = max(px[s][ds[k]] for k in range(i, j + 1))
                    n += 1
                    if 100 * (hi / spot - 1) >= BREACH:
                        hits += 1
                    break
        rand_rate = hits / n if n else 0
        print(f"  {year}:")
        print(f"    gate-selected bear calls : {100*gate_rate:>5.1f}%  (n={len(gate):,})")
        print(f"    random selection         : {100*rand_rate:>5.1f}%  (n={n:,})")
        edge = rand_rate - gate_rate
        print(f"    gate edge                : {100*edge:>+5.1f}pp  "
              f"{'REAL SKILL' if edge > 0.02 else 'no meaningful skill'}")
        print()


if __name__ == "__main__":
    main()
