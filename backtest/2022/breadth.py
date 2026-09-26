"""Advance/decline breadth, market-wide and per-sector, for 2022.

Rationale: every one of the seven tests measured price momentum on a single
symbol. Breadth is a different kind of information -- how many names are
participating -- so it is not guaranteed to be another disguised direction bet
the way ADX/DMI turned out to be.

Built from 494 symbols x 251 days of real Polygon OHLC.

Measures per day, computed market-wide AND per sector:
  ad_diff    advances - declines
  ad_ratio   advances / declines
  ad_pct     advances / (advances + declines)      <- scale-free, comparable
  ad_line    cumulative sum of ad_diff            <- the classic A/D line
  ad_line_ma ad_line vs its own 10/20-day average <- is breadth improving?
  pct_above  share of names above their own 50-day SMA
  mcclellan  19/39-day EMA spread of ad_pct (McClellan Oscillator, normalised)
  ad_thrust  10-day average of ad_pct             <- Zweig-style thrust

The key design choice: SECTOR-RELATIVE breadth. The user's point is that the
market is not linear, so a single market-wide number is too coarse. For each
symbol we can ask "is MY sector's breadth improving, and is it better or worse
than the market's?" That is a micro signal with a macro denominator.
"""
import csv
import gzip
import json
import pickle
from collections import defaultdict

DAILY = "/home/user/vps/backtest/data/daily_2022.csv.gz"
SECTORS = "/home/user/webapp/bt/sectors_2022.json"


def ema(vals, n):
    if not vals:
        return []
    a = 2.0 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(out[-1] + a * (v - out[-1]))
    return out


def load():
    rows = defaultdict(dict)          # sym -> date -> close
    with gzip.open(DAILY, "rt") as fh:
        for r in csv.DictReader(fh):
            rows[r["symbol"]][r["date"]] = float(r["close"])
    sec = json.load(open(SECTORS))
    return rows, sec


def build():
    closes, sec = load()
    dates = sorted({d for v in closes.values() for d in v})

    # --- per-day advance/decline tallies, market and by sector -----------
    # An "advance" is close > prior close for that symbol. Symbols missing
    # either day are skipped rather than counted as unchanged, which would
    # bias ad_pct toward 0.5.
    tally = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # scope->date->[adv,dec]
    above50 = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # scope->date->[above,tot]

    for sym, series in closes.items():
        ds = sorted(series)
        scope = sec.get(sym, "UNKNOWN")
        # ETF buckets are not real sectors; keep them out of breadth entirely
        # or they double-count the very thing being measured.
        is_etf = scope.startswith("ETF_")
        for i in range(1, len(ds)):
            d, p = ds[i], ds[i - 1]
            up = series[d] > series[p]
            if not is_etf:
                tally["MARKET"][d][0 if up else 1] += 1
                tally[scope][d][0 if up else 1] += 1
        # share above own 50-day SMA
        for i in range(50, len(ds)):
            d = ds[i]
            s50 = sum(series[x] for x in ds[i - 49:i + 1]) / 50
            if not is_etf:
                above50["MARKET"][d][1] += 1
                above50[scope][d][1] += 1
                if series[d] > s50:
                    above50["MARKET"][d][0] += 1
                    above50[scope][d][0] += 1

    scopes = sorted(tally)
    out = {}          # (scope, date) -> metrics

    for scope in scopes:
        ds = sorted(tally[scope])
        pcts, line, cum = [], [], 0.0
        for d in ds:
            adv, dec = tally[scope][d]
            tot = adv + dec
            pct = adv / tot if tot else 0.5
            cum += (adv - dec)
            pcts.append(pct)
            line.append(cum)

        # McClellan: 19/39 EMA spread of the advance percentage, x1000 so the
        # numbers are readable. Using ad_pct rather than raw adv-dec makes it
        # comparable between a 70-name sector and the 460-name market.
        e19, e39 = ema(pcts, 19), ema(pcts, 39)
        mcc = [1000 * (a - b) for a, b in zip(e19, e39)]

        for i, d in enumerate(ds):
            adv, dec = tally[scope][d]
            ab, tot_ab = above50[scope].get(d, [0, 0])
            lo = max(0, i - 9)
            thrust = sum(pcts[lo:i + 1]) / (i + 1 - lo)
            l20 = max(0, i - 19)
            line_ma = sum(line[l20:i + 1]) / (i + 1 - l20)
            out[(scope, d)] = {
                "adv": adv, "dec": dec, "n": adv + dec,
                "ad_pct": pcts[i],
                "ad_diff": adv - dec,
                "ad_ratio": adv / dec if dec else float(adv or 1),
                "ad_line": line[i],
                "ad_line_ma20": line_ma,
                "ad_line_rising": 1.0 if line[i] > line_ma else 0.0,
                "mcclellan": mcc[i],
                "ad_thrust10": thrust,
                "pct_above50": (100.0 * ab / tot_ab) if tot_ab else 50.0,
            }

    pickle.dump(out, open("breadth22.pkl", "wb"))
    print(f"scopes : {len(scopes)}  ({', '.join(scopes[:6])} ...)")
    print(f"rows   : {len(out)}")

    # --- sanity: does market breadth match what we know about 2022? ------
    mk = {d: v for (s, d), v in out.items() if s == "MARKET"}
    ds = sorted(mk)
    print()
    print("sanity check -- monthly mean advance % (2022 was a down year):")
    mon = defaultdict(list)
    for d in ds:
        mon[d[:7]].append(mk[d]["ad_pct"])
    for m in sorted(mon):
        v = 100 * sum(mon[m]) / len(mon[m])
        bar = "#" * int(abs(v - 50) * 2)
        print(f"  {m}  {v:>5.1f}%  {'+' if v > 50 else '-'}{bar}")
    print()
    print(f"A/D line start {mk[ds[0]]['ad_line']:>+8.0f} "
          f"end {mk[ds[-1]]['ad_line']:>+8.0f}  (should be strongly negative)")
    lo = min(ds, key=lambda d: mk[d]["ad_line"])
    print(f"A/D line trough: {lo}  ({mk[lo]['ad_line']:+.0f})")
    print(f"pct_above50 range: {min(mk[d]['pct_above50'] for d in ds):.0f}% "
          f".. {max(mk[d]['pct_above50'] for d in ds):.0f}%")


if __name__ == "__main__":
    build()
