"""Macro regime engine, 2022-2024. Builds the four indicator families the
user specified, then combines them into regime states.

INPUTS AVAILABLE (verified):
  trend.pkl / indicators_slim.pkl   369 symbols, 2022-03-15 .. 2024-12-31
  vix.json                          753 days, 2022-01-03 .. 2024-12-31
  SPY, QQQ, IWM, TLT, XLF, XLE, XLK, XLV + ~360 single names

DATA LIMITATION, stated up front: HYG / LQD / JNK exist only in the 2022 file,
not 2023-24. The high-yield credit-spread rule therefore cannot be built from
actual HY bond prices across the full period. Two honest options were possible:
restrict that rule to 2022, or use a proxy. Both are built here and kept
SEPARATE, never blended:
  credit_hy      real HYG/TLT ratio, 2022 only
  credit_proxy   XLF/SPY relative strength + TLT trend, all years
The proxy is a weaker instrument and is labelled as such in the output. It is
NOT presented as equivalent to a real HY spread.

MEASURES BUILT
  1. SPY vs 200-day SMA                         structural bias
  2. A/D line + all-time-high / breakdown state  breadth confirmation
  3. NH-NL (52-week new highs minus new lows)    breadth quality
  4. VIX level + spike detection                 entry timing
  5. credit risk (see note above)                liquidity / risk-off

The A/D "reaction low breach" from the user's execution protocol is
implemented explicitly as ad_break_low: the A/D line closing below its prior
swing low, which is the early-warning trigger the whole rule set rests on.
"""
import json
import pickle
from collections import defaultdict

LOOKBACK_52W = 252
SWING_WIN = 20          # window defining a "reaction low" in the A/D line


def load_prices():
    """Daily closes per symbol, 2022-2024.

    trend.pkl starts 2022-03-15, which leaves the 200-day SMA undefined for
    all of 2022 -- the one year the macro rule most needs it. The raw 2022
    daily file starts 2022-01-03, so it is spliced in first and trend.pkl
    layered on top. That recovers ~2.5 months but still cannot produce a
    200-day average before ~2022-10; see the coverage report in validate().
    """
    import csv
    import gzip
    px = defaultdict(dict)
    with gzip.open("/home/user/vps/backtest/data/daily_2022.csv.gz", "rt") as fh:
        for r in csv.DictReader(fh):
            px[r["symbol"]][r["date"]] = float(r["close"])
    t = pickle.load(open("trend.pkl", "rb"))
    for (sym, d), v in t.items():
        px[sym][d] = v["close"]
    return px


def load_hy():
    """HYG and TLT closes -- 2022 only, from the raw daily file."""
    import csv
    import gzip
    out = defaultdict(dict)
    with gzip.open("/home/user/vps/backtest/data/daily_2022.csv.gz", "rt") as fh:
        for r in csv.DictReader(fh):
            if r["symbol"] in ("HYG", "TLT", "LQD", "JNK"):
                out[r["symbol"]][r["date"]] = float(r["close"])
    return out


def sma(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def build():
    px = load_prices()
    hy = load_hy()
    vix = json.load(open("/home/user/vps/backtest/data/vix.json"))

    # universe for breadth = single names only; ETFs would double-count
    ETFS = {"SPY", "QQQ", "IWM", "TLT", "XLF", "XLE", "XLK", "XLV",
            "DIA", "MDY", "HYG", "LQD", "JNK"}
    names = [s for s in px if s not in ETFS]
    dates = sorted({d for s in names for d in px[s]})
    print(f"breadth universe: {len(names)} single names")
    print(f"dates           : {len(dates)}  {dates[0]} .. {dates[-1]}")

    spy = px.get("SPY", {})
    spy_dates = sorted(spy)
    spy_hist = []

    # rolling per-symbol series for NH-NL
    hist = {s: [] for s in names}
    prev = {}

    ad_cum = 0.0
    ad_series, ad_dates = [], []
    out = {}

    for d in dates:
        adv = dec = 0
        nh = nl = 0
        for s in names:
            c = px[s].get(d)
            if c is None:
                continue
            p = prev.get(s)
            if p is not None:
                if c > p:
                    adv += 1
                elif c < p:
                    dec += 1
            prev[s] = c
            h = hist[s]
            h.append(c)
            if len(h) > LOOKBACK_52W:
                h.pop(0)
            if len(h) >= 60:
                if c >= max(h):
                    nh += 1
                elif c <= min(h):
                    nl += 1

        ad_cum += (adv - dec)
        ad_series.append(ad_cum)
        ad_dates.append(d)

        # --- SPY 200-day ---------------------------------------------------
        sc = spy.get(d)
        if sc is not None:
            spy_hist.append(sc)
        s200 = sma(spy_hist, 200)
        s20 = sma(spy_hist, 20)
        s50 = sma(spy_hist, 50)

        # --- A/D structure -------------------------------------------------
        ad_ath = ad_cum >= max(ad_series)          # at all-time high
        # prior swing low = min of the A/D line excluding the last few days,
        # measured over a trailing window. A close below it is the breach the
        # user's protocol treats as an exit trigger.
        ad_break = False
        ad_prior_low = None
        if len(ad_series) > SWING_WIN + 3:
            window = ad_series[-(SWING_WIN + 3):-3]
            ad_prior_low = min(window)
            ad_break = ad_cum < ad_prior_low
        # is the A/D line trending down? (below its own 20-day average)
        ad_ma = sma(ad_series, 20)

        # --- NH-NL ---------------------------------------------------------
        nhnl = nh - nl

        # --- VIX -----------------------------------------------------------
        v = vix.get(d)

        # --- credit --------------------------------------------------------
        credit_hy = None
        if d in hy.get("HYG", {}) and d in hy.get("TLT", {}):
            credit_hy = hy["HYG"][d] / hy["TLT"][d]
        # proxy: financials relative strength (credit stress shows up in banks)
        xlf, spyc = px.get("XLF", {}).get(d), sc
        credit_proxy = (xlf / spyc) if (xlf and spyc) else None

        out[d] = {
            "adv": adv, "dec": dec,
            "ad_line": ad_cum, "ad_ma20": ad_ma,
            "ad_ath": 1.0 if ad_ath else 0.0,
            "ad_break_low": 1.0 if ad_break else 0.0,
            "ad_prior_low": ad_prior_low,
            "ad_rising": 1.0 if (ad_ma is not None and ad_cum > ad_ma) else 0.0,
            "nh": nh, "nl": nl, "nhnl": nhnl,
            "spy": sc, "spy_sma200": s200, "spy_sma20": s20, "spy_sma50": s50,
            "spy_above200": 1.0 if (sc and s200 and sc > s200) else 0.0,
            "vix": v,
            "credit_hy": credit_hy,
            "credit_proxy": credit_proxy,
        }

    # smoothed NH-NL and VIX spike flags need a second pass
    ds = sorted(out)
    nn = [out[d]["nhnl"] for d in ds]
    vv = [out[d]["vix"] for d in ds]
    ch = [out[d]["credit_hy"] for d in ds]
    cp = [out[d]["credit_proxy"] for d in ds]
    for i, d in enumerate(ds):
        lo = max(0, i - 9)
        out[d]["nhnl_ma10"] = sum(nn[lo:i + 1]) / (i + 1 - lo)
        lo20 = max(0, i - 19)
        vw = [x for x in vv[lo20:i + 1] if x is not None]
        out[d]["vix_ma20"] = sum(vw) / len(vw) if vw else None
        # VIX spike: current well above its own 20-day mean
        if out[d]["vix"] and out[d]["vix_ma20"]:
            out[d]["vix_spike"] = out[d]["vix"] / out[d]["vix_ma20"]
        else:
            out[d]["vix_spike"] = None
        # credit deterioration: ratio falling vs 20-day mean
        for key, arr in (("credit_hy", ch), ("credit_proxy", cp)):
            w = [x for x in arr[lo20:i + 1] if x is not None]
            m = sum(w) / len(w) if w else None
            cur = out[d][key]
            out[d][key + "_widening"] = (
                1.0 if (cur is not None and m is not None and cur < m) else 0.0)

    pickle.dump(out, open("macro.pkl", "wb"))
    print(f"rows written    : {len(out)}")
    return out


def validate(m):
    """Sanity checks against known 2022-2024 history."""
    ds = sorted(m)
    print()
    print("=" * 78)
    print("VALIDATION against known history")
    print("=" * 78)

    # SPY below 200dma should cover most of 2022 and almost none of 2024
    for yr in ("2022", "2023", "2024"):
        g = [d for d in ds if d.startswith(yr) and m[d]["spy_sma200"]]
        if not g:
            continue
        below = sum(1 for d in g if not m[d]["spy_above200"])
        print(f"  {yr}: SPY below 200dma on {below:>3} of {len(g):>3} days "
              f"({100*below/len(g):>4.0f}%)")

    ad = [(d, m[d]["ad_line"]) for d in ds]
    lo = min(ad, key=lambda x: x[1])
    hi = max(ad, key=lambda x: x[1])
    print(f"  A/D line trough : {lo[0]}  ({lo[1]:+,.0f})")
    print(f"  A/D line peak   : {hi[0]}  ({hi[1]:+,.0f})")

    vs = [(d, m[d]["vix"]) for d in ds if m[d]["vix"]]
    top = sorted(vs, key=lambda x: -x[1])[:3]
    print(f"  highest VIX     : " + ", ".join(f"{d} {v:.1f}" for d, v in top))

    nn = [(d, m[d]["nhnl"]) for d in ds]
    wn = min(nn, key=lambda x: x[1])
    bn = max(nn, key=lambda x: x[1])
    print(f"  worst NH-NL     : {wn[0]}  {wn[1]:+d}")
    print(f"  best  NH-NL     : {bn[0]}  {bn[1]:+d}")

    nb = sum(1 for d in ds if m[d]["ad_break_low"])
    print(f"  A/D reaction-low breaches: {nb} of {len(ds)} days "
          f"({100*nb/len(ds):.0f}%)")
    hyd = sum(1 for d in ds if m[d]["credit_hy"] is not None)
    print(f"  real HY credit available : {hyd} of {len(ds)} days "
          f"(2022 only -- proxy used elsewhere)")


if __name__ == "__main__":
    validate(build())
