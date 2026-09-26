"""Build trend23.pkl (+ hviv23) for the asym spec on 2023.

Price source: trend.pkl closes (369 symbols, 2022-03-15..2024-12-31). Using the
existing series rather than the option DBs' underlying_price avoids repeating
the 2022 mistake where MIN/MAX of a repeated underlying collapsed high==low.
Only closes are needed here: the asym gate uses sma5/sma20 and two down days.

Warm-up is NOT a problem for 2023 -- trend.pkl starts 2022-03-15, so every
2023 date has 200+ prior sessions for any average the spec needs.
"""
import pickle
from collections import defaultdict

t = pickle.load(open("trend.pkl", "rb"))
px = defaultdict(dict)
for (sym, d), v in t.items():
    px[sym][d] = v["close"]

out = {}
for sym, s in px.items():
    ds = sorted(s)
    for i in range(50, len(ds)):
        d = ds[i]
        if not d.startswith("2023"):
            continue
        w = [s[x] for x in ds[:i + 1]]
        s5 = sum(w[-5:]) / 5
        s10 = sum(w[-10:]) / 10
        s20 = sum(w[-20:]) / 20
        s30 = sum(w[-30:]) / 30
        s50 = sum(w[-50:]) / 50
        s200 = sum(w[-200:]) / 200 if len(w) >= 200 else None
        d0, d1, d2 = w[-1], w[-2], w[-3]
        above = 0
        for j in range(i, max(9, i - 60), -1):
            ww = [s[x] for x in ds[:j + 1]]
            a10 = sum(ww[-10:]) / 10
            a50 = sum(ww[-50:]) / 50 if len(ww) >= 50 else a10
            if a10 > a50:
                above += 1
            else:
                break
        out[(sym, d)] = {
            "close": d0, "sma5": s5, "sma10": s10, "sma20": s20,
            "sma30": s30, "sma50": s50,
            "sma200": s200 if s200 else s50,
            "sma200_true": 1 if s200 else 0,
            "golden": 1 if (s200 and s50 > s200) else 0,
            "stretch10": 100 * (s10 - s50) / s50 if s50 else 0.0,
            "stretch20": 100 * (s20 - s50) / s50 if s50 else 0.0,
            "gap5_20": 100 * (s5 - s20) / s20 if s20 else 0.0,
            "days_above": above,
            "max_stretch": 0.0, "mean_stretch": 0.0, "stretch_slope": 0.0,
            "down1": 1 if d0 < d1 else 0,
            "down2": 1 if (d0 < d1 and d1 < d2) else 0,
        }

pickle.dump(out, open("trend23.pkl", "wb"))
ds = sorted({d for _, d in out})
print(f"trend23: {len(out)} rows, {len({s for s,_ in out})} symbols")
print(f"  {ds[0]} .. {ds[-1]}  ({len(ds)} sessions)")
tr = sum(1 for v in out.values() if v["sma200_true"])
print(f"  rows with a TRUE 200d window: {tr} ({100*tr/len(out):.0f}%)")
bc = sum(1 for v in out.values() if v["sma5"] < v["sma20"])
print(f"  sma5 < sma20 (would be bear call): {100*bc/len(out):.1f}%")
d2 = sum(1 for v in out.values() if v["sma5"] > v["sma20"] and v["down2"])
print(f"  sma5 > sma20 + 2 down days (bull put): {100*d2/len(out):.1f}%")
