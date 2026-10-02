"""Build a vol-of-vol series as a VVIX stand-in, with the limitation explicit.

VVIX IS NOT IN THIS DATASET. Checked: 0 rows for VVIX / ^VVIX in the option
DBs, no VVIX file anywhere, and vix.json holds the VIX index only.

What is built instead: 20-day realised volatility of the VIX index itself,
annualised. That is vol-OF-vol, the same economic quantity VVIX prices, but:
  - realised, not implied (VVIX is forward-looking; this is backward-looking)
  - different scale: this medians 88 vs VVIX's ~95-100 historically

So a literal "VVIX > 100" rule CANNOT be mapped onto it without inventing the
mapping. Instead the gate is expressed as a PERCENTILE of the series' own
trailing distribution, which is threshold-free and transfers across scales.
The 70th/80th/90th percentiles are tested so the sensitivity is visible.

Sanity: the series peaks 2024-08-13..20 (the yen-carry unwind), which is the
correct event for a vol-of-vol spike.
"""
import json, math, pickle, statistics

v = json.load(open("/home/user/vps/backtest/data/vix.json"))
ks = sorted(v)
out = {}
series = []
for i in range(21, len(ks)):
    w = [v[ks[j]] for j in range(i - 20, i + 1)]
    lr = [math.log(w[j] / w[j - 1]) for j in range(1, len(w)) if w[j - 1] > 0]
    vv = statistics.pstdev(lr) * math.sqrt(252) * 100
    series.append(vv)
    # percentile against its own trailing 252-day history (no lookahead)
    hist = series[-252:]
    pct = 100 * sum(1 for x in hist if x <= vv) / len(hist)
    out[ks[i]] = {"volvol": vv, "pctile": pct, "vix": v[ks[i]]}

pickle.dump(out, open("volvol.pkl", "wb"))
ds = sorted(out)
print(f"volvol.pkl: {len(out)} days {ds[0]}..{ds[-1]}")
for p in (70, 80, 90):
    n = sum(1 for d in ds if out[d]["pctile"] >= p)
    print(f"  pctile >= {p}: {n} days ({100*n/len(ds):.1f}%)")
for yr in ("2022", "2023"):
    g = [d for d in ds if d.startswith(yr)]
    for p in (80,):
        n = sum(1 for d in g if out[d]["pctile"] >= p)
        print(f"  {yr} pctile>={p}: {n} of {len(g)} days ({100*n/len(g):.0f}%)")
