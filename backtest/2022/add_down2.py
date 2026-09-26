"""Add consecutive-down-day counts to trend22.pkl.

down1 / down2 = the stock closed lower on the last 1 / 2 consecutive sessions
as of (and including) the trade date. Used by the asymmetric spec's bull-put
leg: uptrend by SMA, but entered only after a two-day pullback.
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
n = 0
for sym, s in closes.items():
    ds = sorted(s)
    for i in range(2, len(ds)):
        k = (sym, ds[i])
        if k not in trend:
            continue
        d0, d1, d2 = s[ds[i]], s[ds[i - 1]], s[ds[i - 2]]
        trend[k]["down1"] = 1 if d0 < d1 else 0
        trend[k]["down2"] = 1 if (d0 < d1 and d1 < d2) else 0
        n += 1
pickle.dump(trend, open("trend22.pkl", "wb"))
miss = sum(1 for v in trend.values() if "down2" not in v)
d2 = sum(v.get("down2", 0) for v in trend.values())
print(f"down1/down2 on {n} rows; {miss} missing")
print(f"two-down-days frequency: {d2} of {len(trend)} = {100*d2/len(trend):.1f}%")
