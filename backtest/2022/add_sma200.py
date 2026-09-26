"""Add sma50/sma200 per symbol for the golden-cross side-selection rule.

WARM-UP PROBLEM, stated explicitly: the 2022 daily file starts 2022-01-03, so
a TRUE 200-session average does not exist until 2022-10-18. Testing the rule
only from October would leave ~35 tradeable days in a year whose whole point
is the bear market.

Two fields are therefore written per row:
  sma200        average over min(200, available) sessions
  sma200_true   1 if the full 200 sessions were available, else 0

Any test can then run twice -- full period with flagged rows, and the
true-200-only subset -- and the two can be compared instead of one being
quietly presented as the other.
"""
import csv
import gzip
import pickle
from collections import defaultdict

closes = defaultdict(dict)
with gzip.open("/home/user/vps/backtest/data/daily_2022.csv.gz", "rt") as fh:
    for r in csv.DictReader(fh):
        closes[r["symbol"]][r["date"]] = float(r["close"])

trend = pickle.load(open("trend22.pkl", "rb"))
n = full = 0
for sym, s in closes.items():
    ds = sorted(s)
    for i, d in enumerate(ds):
        k = (sym, d)
        if k not in trend:
            continue
        w = [s[x] for x in ds[:i + 1]]
        if len(w) < 50:
            continue
        n200 = min(200, len(w))
        trend[k]["sma50"] = sum(w[-50:]) / 50
        trend[k]["sma200"] = sum(w[-n200:]) / n200
        trend[k]["sma200_true"] = 1 if n200 == 200 else 0
        trend[k]["golden"] = 1 if trend[k]["sma50"] > trend[k]["sma200"] else 0
        n += 1
        full += trend[k]["sma200_true"]

pickle.dump(trend, open("trend22.pkl", "wb"))
print(f"sma200 written to {n} rows; {full} ({100*full/n:.0f}%) have a TRUE 200d window")
gold = sum(1 for v in trend.values() if v.get("golden") == 1)
tot = sum(1 for v in trend.values() if "golden" in v)
print(f"golden cross (sma50>sma200) on {gold} of {tot} rows = {100*gold/tot:.1f}%")
# monthly share, to sanity-check against 2022 history
from collections import defaultdict as dd
mon = dd(lambda: [0, 0])
for (sym, d), v in trend.items():
    if "golden" in v:
        mon[d[:7]][0] += v["golden"]; mon[d[:7]][1] += 1
print()
print("golden-cross share by month (should collapse through 2022):")
for m in sorted(mon):
    g, t = mon[m]
    print(f"  {m}  {100*g/t:>5.1f}%  {'#' * int(g/t*40)}")
