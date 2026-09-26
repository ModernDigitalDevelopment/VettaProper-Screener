"""Build kc_squeeze for 2022 and 2023 from real high/low.

The Keltner squeeze is Bollinger(20,2sigma) contained INSIDE Keltner(20,1.5xATR)
-- volatility compressed into a range. Theoretically suited to condors, which
want the underlying to stay put.

Needs a true ATR, so real high/low is required. The 2022 daily CSV has it;
2023 does not (trend.pkl carries closes only), so 2023 ATR is approximated from
close-to-close range with the approximation FLAGGED per row rather than hidden.

Prior measurement context, for honesty: the 6.5pp tercile separation in
docs/INDICATORS.md was measured on 2,129 BULL PUT trades, not condors, and
kc_squeeze is binary so a tercile split on it is loose. It is a reasonable
hypothesis for condors, not an established result.
"""
import csv
import gzip
import pickle
from collections import defaultdict


def ema(vals, n):
    a = 2.0 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(out[-1] + a * (v - out[-1]))
    return out


def wilder(v, n):
    out = [float(v[0])]
    a = 1.0 / n
    for x in v[1:]:
        out.append(out[-1] + a * (float(x) - out[-1]))
    return out


def stdev(w):
    m = sum(w) / len(w)
    return (sum((x - m) ** 2 for x in w) / len(w)) ** 0.5


# ---- 2022: real high/low ------------------------------------------------
hi22, lo22, c22 = defaultdict(dict), defaultdict(dict), defaultdict(dict)
with gzip.open("/home/user/vps/backtest/data/daily_2022.csv.gz", "rt") as fh:
    for r in csv.DictReader(fh):
        s, d = r["symbol"], r["date"]
        hi22[s][d] = float(r["high"]); lo22[s][d] = float(r["low"])
        c22[s][d] = float(r["close"])

# ---- 2023: closes only, range approximated -----------------------------
t = pickle.load(open("trend.pkl", "rb"))
c23 = defaultdict(dict)
for (s, d), v in t.items():
    if d >= "2022-06-01":
        c23[s][d] = v["close"]

out = {}
approx = exact = 0

for src, closes, his, los, is_real in (
        ("2022", c22, hi22, lo22, True),
        ("2023", c23, None, None, False)):
    for sym, series in closes.items():
        ds = sorted(series)
        if len(ds) < 60:
            continue
        c = [series[d] for d in ds]
        if is_real:
            h = [his[sym][d] for d in ds]
            l = [los[sym][d] for d in ds]
        else:
            # proxy: synthesise a range from |close-to-close| moves. This
            # understates true range, so ATR is biased LOW and the squeeze
            # will fire slightly more often. Flagged per row.
            h, l = [], []
            for i, x in enumerate(c):
                mv = abs(x - c[i - 1]) if i else 0.0
                h.append(x + mv / 2); l.append(x - mv / 2)
        tr = [h[0] - l[0]]
        for i in range(1, len(c)):
            tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
        atr = wilder(tr, 20)
        e20 = ema(c, 20)
        for i in range(25, len(ds)):
            d = ds[i]
            if not d.startswith(src):
                continue
            w = c[i - 19:i + 1]
            m20 = sum(w) / 20
            sd = stdev(w)
            bb_u, bb_l = m20 + 2 * sd, m20 - 2 * sd
            kc_u, kc_l = e20[i] + 1.5 * atr[i], e20[i] - 1.5 * atr[i]
            sq = 1 if (bb_u < kc_u and bb_l > kc_l) else 0
            out[(sym, d)] = {
                "kc_squeeze": sq,
                "bb_width": (bb_u - bb_l) / m20 * 100 if m20 else 0.0,
                "atr20_pct": 100 * atr[i] / c[i] if c[i] else 0.0,
                "squeeze_exact": 1 if is_real else 0,
            }
            if is_real:
                exact += 1
            else:
                approx += 1

pickle.dump(out, open("squeeze.pkl", "wb"))
print(f"squeeze.pkl: {len(out)} rows  ({exact} exact 2022, {approx} approx 2023)")
for yr in ("2022", "2023"):
    g = [v for (s, d), v in out.items() if d.startswith(yr)]
    if g:
        sq = sum(v["kc_squeeze"] for v in g)
        print(f"  {yr}: squeeze on {sq} of {len(g)} = {100*sq/len(g):.1f}%")
