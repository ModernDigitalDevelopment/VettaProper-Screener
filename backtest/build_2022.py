"""Collapse 2022 Polygon minute bars to daily OHLCV, then compute indicators.

Two passes, both memory-bounded — the first version of this script held every
symbol's full series in RAM and was OOM-killed on a 2GB box.

Pass 1: stream each day's minute file, aggregate to one row per symbol,
        append straight to daily_2022.csv. Peak memory = one day of symbols.
Pass 2: read daily_2022.csv symbol-by-symbol (it is sorted by symbol), compute
        indicators, write out. Peak memory = one symbol's year.

Daily bars use the REGULAR SESSION ONLY (09:30-16:00 ET). Polygon minute files
include pre/post market bars; including them would distort open/high/low/volume
relative to how the 2023 data was built.
"""
import csv
import gzip
import os
import pickle
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SRC = Path("stocks_minute_filtered")
RAW = "daily_2022_unsorted.csv"
DAILY = "daily_2022.csv"

DST_START = datetime(2022, 3, 13).date()
DST_END = datetime(2022, 11, 6).date()


def log(msg):
    print(msg, flush=True)


def session_bounds(day):
    """(lo_ns, hi_ns) for 09:30-15:59 ET on this date."""
    off = -4 if DST_START <= day < DST_END else -5
    tz = timezone(timedelta(hours=off))
    lo = datetime(day.year, day.month, day.day, 9, 30, tzinfo=tz)
    hi = datetime(day.year, day.month, day.day, 16, 0, tzinfo=tz)
    return int(lo.timestamp() * 1e9), int(hi.timestamp() * 1e9)


def pass1():
    files = sorted(SRC.glob("*.csv.gz"))
    log(f"pass 1: collapsing {len(files)} minute files to daily bars")
    rows = 0
    with open(RAW, "w", newline="") as out:
        w = csv.writer(out)
        for i, f in enumerate(files):
            day = datetime.strptime(f.name[:10], "%Y-%m-%d").date()
            lo_ns, hi_ns = session_bounds(day)
            agg = {}
            with gzip.open(f, "rt", newline="") as fh:
                for r in csv.reader(fh):
                    try:
                        ns = int(r[6])
                    except (ValueError, IndexError):
                        continue            # header or malformed
                    if ns < lo_ns or ns >= hi_ns:
                        continue
                    try:
                        sym = r[0]
                        v = int(r[1])
                        o, c = float(r[2]), float(r[3])
                        h, l = float(r[4]), float(r[5])
                    except (ValueError, IndexError):
                        continue
                    a = agg.get(sym)
                    if a is None:
                        agg[sym] = [ns, o, h, l, ns, c, v]
                    else:
                        if ns < a[0]:
                            a[0], a[1] = ns, o
                        if h > a[2]:
                            a[2] = h
                        if l < a[3]:
                            a[3] = l
                        if ns > a[4]:
                            a[4], a[5] = ns, c
                        a[6] += v
            ds = day.isoformat()
            for sym, a in agg.items():
                w.writerow([sym, ds, f"{a[1]:.4f}", f"{a[2]:.4f}",
                            f"{a[3]:.4f}", f"{a[5]:.4f}", a[6]])
                rows += 1
            del agg
            if (i + 1) % 25 == 0:
                log(f"  {i+1}/{len(files)} days, {rows:,} bars")
    log(f"pass 1 done: {rows:,} daily bars -> {RAW}")


def sort_by_symbol():
    """External sort so pass 2 can stream one symbol at a time."""
    log("sorting by symbol,date")
    os.environ["LC_ALL"] = "C"
    rc = os.system(f"sort -t, -k1,1 -k2,2 -S 200M -o {DAILY}.body {RAW}")
    if rc != 0:
        raise RuntimeError(f"sort failed rc={rc}")
    with open(DAILY, "w") as out:
        out.write("symbol,date,open,high,low,close,volume\n")
        with open(f"{DAILY}.body") as body:
            for line in body:
                out.write(line)
    os.remove(f"{DAILY}.body")
    os.remove(RAW)
    log(f"sorted -> {DAILY}")


def wilder(vals, n):
    if not vals:
        return []
    out = [float(vals[0])]
    a = 1.0 / n
    for v in vals[1:]:
        out.append(out[-1] + a * (float(v) - out[-1]))
    return out


def indicators_for(bars, period=14):
    """bars: [(date,o,h,l,c,v)] ascending -> {date: {...}}"""
    n = len(bars)
    if n < 60:
        return {}
    h = [b[2] for b in bars]
    l = [b[3] for b in bars]
    c = [b[4] for b in bars]

    tr = [h[0] - l[0]]
    for i in range(1, n):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    atr = wilder(tr, period)

    pdm, mdm = [0.0], [0.0]
    for i in range(1, n):
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
    sp, sm = wilder(pdm, period), wilder(mdm, period)
    pdi = [100 * s / a if a else 0.0 for s, a in zip(sp, atr)]
    mdi = [100 * s / a if a else 0.0 for s, a in zip(sm, atr)]
    dx = [100 * abs(p - m) / (p + m) if (p + m) else 0.0
          for p, m in zip(pdi, mdi)]
    adx = wilder(dx, period)

    gains = [max(c[i] - c[i - 1], 0.0) for i in range(1, n)]
    losses = [max(c[i - 1] - c[i], 0.0) for i in range(1, n)]
    ag, al = wilder(gains, period), wilder(losses, period)

    out = {}
    for i in range(50, n):
        w = c[: i + 1]
        g, lo = ag[i - 1], al[i - 1]
        out[bars[i][0]] = {
            "close": c[i],
            "sma10": sum(w[-10:]) / 10,
            "sma30": sum(w[-30:]) / 30,
            "sma50": sum(w[-50:]) / 50,
            "adx14": adx[i],
            "plus_di": pdi[i],
            "minus_di": mdi[i],
            "rsi14": 100.0 if lo == 0 else 100 - 100 / (1 + g / lo),
            "atr_pct": 100 * atr[i] / c[i] if c[i] else None,
        }
    return out


def pass2():
    log("pass 2: computing indicators")
    trend, ind = {}, {}
    nsym = skipped = 0
    cur, bars = None, []

    def flush():
        nonlocal nsym, skipped
        if not bars:
            return
        vals = indicators_for(bars)
        if not vals:
            skipped += 1
            return
        nsym += 1
        for d, v in vals.items():
            trend[(cur, d)] = {"close": v["close"], "sma10": v["sma10"],
                               "sma30": v["sma30"], "sma50": v["sma50"]}
            ind[(cur, d)] = {"adx14": v["adx14"], "rsi14": v["rsi14"],
                             "plus_di": v["plus_di"],
                             "minus_di": v["minus_di"],
                             "atr_pct": v["atr_pct"]}

    with open(DAILY, newline="") as f:
        rd = csv.reader(f)
        next(rd, None)
        for r in rd:
            sym = r[0]
            if sym != cur:
                flush()
                cur, bars = sym, []
            bars.append((r[1], float(r[2]), float(r[3]), float(r[4]),
                         float(r[5]), int(r[6])))
        flush()

    pickle.dump(trend, open("trend_2022.pkl", "wb"), protocol=5)
    pickle.dump(ind, open("indicators_2022.pkl", "wb"), protocol=5)
    log(f"trend_2022.pkl:      {len(trend):,} rows")
    log(f"indicators_2022.pkl: {len(ind):,} rows")
    log(f"symbols with indicators: {nsym}, skipped (<60 bars): {skipped}")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "1"):
        pass1()
        sort_by_symbol()
    if what in ("all", "2"):
        pass2()
    log("done")
