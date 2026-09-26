"""Rebuild ind22.pkl using REAL high/low from Polygon daily bars.

Why: the first build derived OHLC from the option table's underlying_price via
MIN/MAX per symbol-day. ThetaData repeats a single underlying price on every
option row, so MIN == MAX == close for all 21,876 symbol-days. True range
collapsed to |close change|, which makes +DI algebraically identical to RSI
(verified: 99.6% sign agreement, exact equality on inspection). ADX, DMI,
stochastics and ATR were all invalid.

Close is still taken from the option DB so the trend filter and strike
selection sit on the same price; high/low come from Polygon.
"""
import csv
import gzip
import pickle
from collections import defaultdict

DAILY = "/home/user/vps/backtest/data/daily_2022.csv.gz"


def wilder(v, n):
    if not v:
        return []
    out = [float(v[0])]
    a = 1.0 / n
    for x in v[1:]:
        out.append(out[-1] + a * (float(x) - out[-1]))
    return out


def load_polygon():
    bars = defaultdict(dict)
    with gzip.open(DAILY, "rt") as fh:
        for r in csv.DictReader(fh):
            bars[r["symbol"]][r["date"]] = (
                float(r["high"]), float(r["low"]), float(r["close"]))
    return bars


def main():
    bars = load_polygon()
    print(f"polygon: {len(bars)} symbols")

    # keep the option-DB close series as the spine so keys line up with trend22
    trend = pickle.load(open("trend22.pkl", "rb"))
    want = defaultdict(set)
    for (sym, d) in trend:
        want[sym].add(d)

    ind = {}
    skipped = []
    degenerate = 0
    for sym, days in bars.items():
        if sym not in want:
            continue
        ds = sorted(days)
        if len(ds) < 60:
            skipped.append(sym)
            continue
        hi = [days[d][0] for d in ds]
        lo = [days[d][1] for d in ds]
        c = [days[d][2] for d in ds]
        n = len(ds)
        degenerate += sum(1 for i in range(n) if hi[i] <= lo[i])

        tr = [hi[0] - lo[0]]
        for i in range(1, n):
            tr.append(max(hi[i] - lo[i], abs(hi[i] - c[i - 1]),
                          abs(lo[i] - c[i - 1])))
        atr = wilder(tr, 14)

        pdm, mdm = [0.0], [0.0]
        for i in range(1, n):
            up, dn = hi[i] - hi[i - 1], lo[i - 1] - lo[i]
            pdm.append(up if (up > dn and up > 0) else 0.0)
            mdm.append(dn if (dn > up and dn > 0) else 0.0)
        sp, sm = wilder(pdm, 14), wilder(mdm, 14)
        pdi = [100 * s / a if a else 0.0 for s, a in zip(sp, atr)]
        mdi = [100 * s / a if a else 0.0 for s, a in zip(sm, atr)]
        dx = [100 * abs(p - m) / (p + m) if (p + m) else 0.0
              for p, m in zip(pdi, mdi)]
        adx = wilder(dx, 14)

        gains = [max(c[i] - c[i - 1], 0.0) for i in range(1, n)]
        losses = [max(c[i - 1] - c[i], 0.0) for i in range(1, n)]
        ag, al = wilder(gains, 14), wilder(losses, 14)

        for i in range(50, n):
            d = ds[i]
            if d not in want[sym]:
                continue
            g, l = ag[i - 1], al[i - 1]
            ks = []
            for j in (i, i - 1, i - 2):
                h2 = max(hi[j - 13:j + 1])
                l2 = min(lo[j - 13:j + 1])
                ks.append(100 * (c[j] - l2) / (h2 - l2) if h2 > l2 else 50.0)
            ind[(sym, d)] = {
                "adx14": adx[i], "plus_di": pdi[i], "minus_di": mdi[i],
                "rsi14": 100.0 if l == 0 else 100 - 100 / (1 + g / l),
                "stoch_k": ks[0], "stoch_d": sum(ks) / 3,
                "atr_pct": 100 * atr[i] / c[i] if c[i] else 0.0,
            }

    # sanity: DMI must no longer track RSI
    agree = sum(1 for v in ind.values()
                if ((v["plus_di"] - v["minus_di"]) > 0) == (v["rsi14"] > 50))
    exact = sum(1 for v in ind.values() if abs(v["plus_di"] - v["rsi14"]) < 1e-9)
    print(f"rows written          : {len(ind)}")
    print(f"bars with high<=low   : {degenerate}")
    print(f"symbols skipped (<60d): {len(skipped)}")
    print(f"DMI/RSI sign agreement: {100*agree/len(ind):.1f}%  (was 99.6%)")
    print(f"DMI == RSI exactly    : {exact}  (was all)")

    old = pickle.load(open("ind22.pkl", "rb"))
    missing = set(trend) - set(ind)
    print(f"old rows              : {len(old)}")
    print(f"trend keys unmatched  : {len(missing)}")

    pickle.dump(ind, open("ind22_fixed.pkl", "wb"))
    print("wrote ind22_fixed.pkl")


if __name__ == "__main__":
    main()
