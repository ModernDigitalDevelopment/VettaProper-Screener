"""Sector + market A/D breadth for 2022-2024, with DIVERGENCE measures.

The user's hypothesis is specific and worth building precisely:
  "if the S&P 500 AD line starts to collapse while the S&P SMA is still
   trending up we exit all bull puts and wait for a reversal"

That is a DIVERGENCE: price still rising, breadth already failing. It is the
institutional-distribution pattern -- mega-caps hold the index up while the
median stock is already being sold. Critically this is NOT the same as a
direction signal: it is a one-sided ON/OFF gate for a put-selling book, so it
cannot invert the way a put-vs-call switch does.

Built per scope (market + 12 sectors):
  ad_line        cumulative advances-declines
  ad_ma10/20     its own moving averages
  ad_slope10     10-day change in the A/D line, normalised by universe size
  ad_break_low   closed below its prior 20-day swing low
  pct_above50    share of names above their own 50-day SMA
  thrust10       10-day mean advance share

DIVERGENCE (the new part), market scope:
  div_price_up_breadth_down   SPY above its 50dma AND A/D line below its 20-day
                              average -> price holding while breadth fails
  div_strength                how far apart they are, in normalised units
"""
import csv, gzip, json, pickle
from collections import defaultdict

SECTORS = json.load(open("sectors_2022.json"))
ETFS = {"SPY","QQQ","IWM","TLT","XLF","XLE","XLK","XLV","DIA","MDY",
        "HYG","LQD","JNK","GLD","SLV","EEM","EFA","VXX","UVXY"}


def load_closes():
    px = defaultdict(dict)
    with gzip.open("/home/user/vps/backtest/data/daily_2022.csv.gz", "rt") as fh:
        for r in csv.DictReader(fh):
            px[r["symbol"]][r["date"]] = float(r["close"])
    t = pickle.load(open("trend.pkl", "rb"))
    for (s, d), v in t.items():
        px[s][d] = v["close"]
    return px


def main():
    px = load_closes()
    names = [s for s in px if s not in ETFS and len(px[s]) > 60]
    dates = sorted({d for s in names for d in px[s]})
    print(f"universe {len(names)} names, {len(dates)} sessions "
          f"{dates[0]}..{dates[-1]}")

    # rolling state per scope
    scopes = sorted(set(SECTORS.get(s, "UNKNOWN") for s in names)
                    - {x for x in set(SECTORS.values()) if x.startswith("ETF_")})
    scopes = [s for s in scopes if not s.startswith("ETF_")] + ["MARKET"]

    prev = {}
    hist = defaultdict(list)          # scope -> ad_line series
    above_hist = defaultdict(list)
    pct_hist = defaultdict(list)
    cum = defaultdict(float)
    spy = px.get("SPY", {})
    spy_series = []
    out = {}

    for d in dates:
        # per-scope tallies
        adv = defaultdict(int); dec = defaultdict(int)
        ab = defaultdict(int); tot = defaultdict(int)
        for s in names:
            c = px[s].get(d)
            if c is None:
                continue
            sc = SECTORS.get(s, "UNKNOWN")
            if sc.startswith("ETF_"):
                continue
            p = prev.get(s)
            if p is not None:
                for k in (sc, "MARKET"):
                    if c > p: adv[k] += 1
                    elif c < p: dec[k] += 1
            prev[s] = c
            # 50-day SMA membership
            ds = sorted(px[s])
            # cheap: maintain a per-symbol rolling list
            h = hist[("px", s)]
            h.append(c)
            if len(h) > 50:
                h.pop(0)
            if len(h) == 50:
                s50 = sum(h) / 50
                for k in (sc, "MARKET"):
                    tot[k] += 1
                    if c > s50:
                        ab[k] += 1

        sc_ = spy.get(d)
        if sc_ is not None:
            spy_series.append(sc_)
        s50_spy = sum(spy_series[-50:]) / 50 if len(spy_series) >= 50 else None

        for k in scopes:
            a, dd = adv[k], dec[k]
            n = a + dd
            if n == 0:
                continue
            cum[k] += (a - dd) / n * 100        # normalised so sectors compare
            ser = hist[k]; ser.append(cum[k])
            pct = 100 * ab[k] / tot[k] if tot[k] else 50.0
            pct_hist[k].append(pct)
            thr = sum(pct_hist[k][-10:]) / len(pct_hist[k][-10:])
            ma10 = sum(ser[-10:]) / len(ser[-10:])
            ma20 = sum(ser[-20:]) / len(ser[-20:])
            slope = (ser[-1] - ser[-11]) if len(ser) > 10 else 0.0
            swing = min(ser[-23:-3]) if len(ser) > 23 else None
            out[(k, d)] = {
                "ad_line": cum[k], "ad_ma10": ma10, "ad_ma20": ma20,
                "ad_slope10": slope,
                "ad_below_ma20": 1 if cum[k] < ma20 else 0,
                "ad_break_low": 1 if (swing is not None and cum[k] < swing) else 0,
                "pct_above50": pct, "thrust10": thr,
                "adv": a, "dec": dd,
            }

        # --- the divergence the user described, market scope ---------------
        mk = out.get(("MARKET", d))
        if mk and s50_spy and sc_:
            price_up = sc_ > s50_spy
            breadth_fail = mk["ad_below_ma20"] == 1
            mk["spy_above50"] = 1 if price_up else 0
            mk["divergence"] = 1 if (price_up and breadth_fail) else 0
            # strength: SPY % above its 50dma minus normalised A/D distance
            mk["div_strength"] = (100*(sc_/s50_spy - 1)) - (mk["ad_line"] - mk["ad_ma20"])

    pickle.dump(out, open("breadth_all.pkl", "wb"))
    ds = sorted({d for _, d in out})
    print(f"breadth_all.pkl: {len(out)} rows, {len(scopes)} scopes, "
          f"{ds[0]}..{ds[-1]}")
    mk = {d: v for (k, d), v in out.items() if k == "MARKET"}
    for yr in ("2022", "2023", "2024"):
        g = [d for d in sorted(mk) if d.startswith(yr)]
        if not g: continue
        dv = sum(mk[d].get("divergence", 0) for d in g)
        bl = sum(mk[d]["ad_break_low"] for d in g)
        print(f"  {yr}: divergence on {dv:>3} of {len(g)} days "
              f"({100*dv/len(g):>4.1f}%), A/D breaks {bl}")


if __name__ == "__main__":
    main()
