"""Extend trend22/ind22 back to 2022-01-03 so Q1 is testable.

The original build derived its price series from the option DBs, whose earliest
usable date after the 50-day SMA warm-up was 2022-03-16. That silently made all
of January, February and the first half of March untradeable -- which is why
the A/D breach test found zero open positions on every Q1 breach day.

Polygon daily bars start 2022-01-03, but a 50-day SMA still needs 50 prior
sessions. Rather than fabricate them, this uses the 2021 tail that the file
does NOT have -- so the honest earliest date with a true 50-day SMA is
~2022-03-16 anyway.

WORKAROUND: compute the SMAs with a MINIMUM window instead, flagged per row,
so early-2022 rows carry a shorter-window average and are marked as such
(sma_window). Any test using Q1 can then choose to include or exclude them
rather than being silently blocked.
"""
import csv
import gzip
import pickle
from collections import defaultdict

closes = defaultdict(dict)
hilo = defaultdict(dict)
with gzip.open("/home/user/vps/backtest/data/daily_2022.csv.gz", "rt") as fh:
    for r in csv.DictReader(fh):
        closes[r["symbol"]][r["date"]] = float(r["close"])
        hilo[r["symbol"]][r["date"]] = (float(r["high"]), float(r["low"]))

trend = pickle.load(open("trend22.pkl", "rb"))
before = len(trend)
added = 0

for sym, s in closes.items():
    ds = sorted(s)
    for i, d in enumerate(ds):
        k = (sym, d)
        if k in trend:
            continue
        # need at least 20 sessions for a meaningful short SMA
        if i < 20:
            continue
        w = [s[x] for x in ds[:i + 1]]
        n50 = min(50, len(w))
        s5 = sum(w[-5:]) / 5
        s10 = sum(w[-10:]) / 10
        s20 = sum(w[-20:]) / 20
        s30 = sum(w[-min(30, len(w)):]) / min(30, len(w))
        s50 = sum(w[-n50:]) / n50
        above = 0
        for j in range(i, max(-1, i - 60), -1):
            ww = [s[x] for x in ds[:j + 1]]
            if len(ww) < 10:
                break
            a10 = sum(ww[-10:]) / 10
            a50 = sum(ww[-min(50, len(ww)):]) / min(50, len(ww))
            if a10 > a50:
                above += 1
            else:
                break
        d0 = w[-1]; d1 = w[-2] if len(w) > 1 else d0; d2 = w[-3] if len(w) > 2 else d1
        trend[k] = {
            "close": d0, "sma5": s5, "sma10": s10, "sma20": s20,
            "sma30": s30, "sma50": s50,
            "stretch10": 100 * (s10 - s50) / s50 if s50 else 0.0,
            "stretch20": 100 * (s20 - s50) / s50 if s50 else 0.0,
            "gap5_20": 100 * (s5 - s20) / s20 if s20 else 0.0,
            "days_above": above,
            "max_stretch": 0.0, "mean_stretch": 0.0, "stretch_slope": 0.0,
            "down1": 1 if d0 < d1 else 0,
            "down2": 1 if (d0 < d1 and d1 < d2) else 0,
            "sma_window": n50,          # <50 means a shortened warm-up
        }
        added += 1

pickle.dump(trend, open("trend22.pkl", "wb"))
ds = sorted({d for _, d in trend})
short = sum(1 for v in trend.values() if v.get("sma_window", 50) < 50)
print(f"trend22: {before} -> {len(trend)} rows (+{added})")
print(f"date range now {ds[0]} .. {ds[-1]}")
print(f"rows with a shortened SMA window (<50d): {short}")
