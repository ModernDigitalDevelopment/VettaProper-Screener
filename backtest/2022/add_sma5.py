"""Add sma5 (and the 5/20 gap) to trend22.pkl for the contrarian test.

Built from the same Polygon closes used to repair the indicators, so the price
series is consistent with ind22.pkl. Keys are restricted to those already in
trend22.pkl so nothing new is introduced into the tradeable universe.
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
added = missing = 0
for sym, series in closes.items():
    ds = sorted(series)
    for i in range(20, len(ds)):
        k = (sym, ds[i])
        if k not in trend:
            continue
        s5 = sum(series[x] for x in ds[i - 4:i + 1]) / 5
        s20v = sum(series[x] for x in ds[i - 19:i + 1]) / 20
        trend[k]["sma5"] = s5
        trend[k]["gap5_20"] = 100 * (s5 - s20v) / s20v if s20v else 0.0
        added += 1
missing = sum(1 for v in trend.values() if "sma5" not in v)
pickle.dump(trend, open("trend22.pkl", "wb"))
print(f"sma5/gap5_20 added to {added} rows; {missing} rows still lack it")
g = [v["gap5_20"] for v in trend.values() if "sma5" in v]
g.sort()
print(f"gap5_20 percentiles: p1 {g[len(g)//100]:+.2f}%  "
      f"p50 {g[len(g)//2]:+.2f}%  p99 {g[99*len(g)//100]:+.2f}%")
