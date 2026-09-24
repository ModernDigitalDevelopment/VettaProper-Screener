"""Compute the full indicator suite from the Vetta screener against our price data.

Ports the indicator definitions from
  research/Vetta-Prop-Screener/screener_engine/screener_engine.py
using the documented defaults in indicator_params.py, so any result here is
comparable to what the live site would have produced.

Output: indicators.pkl  ->  (symbol, date) -> {indicator: value}
"""
import pickle
import sqlite3
from collections import defaultdict

import numpy as np
import pandas as pd

DB = ("/home/user/archives/vetta_system/Vetta Options Trading System w:o data bases/"
      "databases/Options Databases/ib_screener_cache.db")


def wilder(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1 / n, adjust=False).mean()


def compute(df: pd.DataFrame) -> pd.DataFrame:
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    out = pd.DataFrame(index=df.index)
    out["close"] = c

    # --- SMA trend (screener default 30/180; we also keep 10/30/50) --------
    for p in (10, 20, 30, 50, 180):
        out[f"sma{p}"] = c.rolling(p).mean()
    out["sma30_slope"] = (out.sma30 - out.sma30.shift(10)) / out.sma30.shift(10) * 100
    out["sma180_slope"] = (out.sma180 - out.sma180.shift(20)) / out.sma180.shift(20) * 100

    # --- ATR --------------------------------------------------------------
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    out["atr14"] = wilder(tr, 14)
    out["atr20"] = wilder(tr, 20)
    out["atr_pct"] = out.atr14 / c * 100

    # --- ADX / DMI (Wilder, period 14) ------------------------------------
    up, dn = h.diff(), -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr_w = wilder(tr, 14)
    plus_di = 100 * wilder(pd.Series(plus_dm, index=df.index), 14) / atr_w
    minus_di = 100 * wilder(pd.Series(minus_dm, index=df.index), 14) / atr_w
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    out["adx14"] = wilder(dx.fillna(0), 14)
    out["plus_di"] = plus_di
    out["minus_di"] = minus_di

    # --- Bollinger (20, 2σ) ------------------------------------------------
    m20, s20 = c.rolling(20).mean(), c.rolling(20).std()
    out["bb_upper"], out["bb_lower"] = m20 + 2 * s20, m20 - 2 * s20
    out["bb_width"] = (out.bb_upper - out.bb_lower) / m20 * 100
    out["bb_pctb"] = (c - out.bb_lower) / (out.bb_upper - out.bb_lower)

    # --- Keltner + squeeze (20, 1.5x ATR) ---------------------------------
    ema20 = c.ewm(span=20, adjust=False).mean()
    kc_u, kc_l = ema20 + 1.5 * out.atr20, ema20 - 1.5 * out.atr20
    out["kc_squeeze"] = ((out.bb_upper < kc_u) & (out.bb_lower > kc_l)).astype(int)

    # --- RSI (14) ----------------------------------------------------------
    d = c.diff()
    out["rsi14"] = 100 - 100 / (1 + wilder(d.clip(lower=0), 14) /
                                wilder(-d.clip(upper=0), 14).replace(0, np.nan))

    # --- MACD (12/26/9) ----------------------------------------------------
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    sig = macd.ewm(span=9, adjust=False).mean()
    out["macd"], out["macd_signal"], out["macd_hist"] = macd, sig, macd - sig

    # --- Stochastic (14,3) -------------------------------------------------
    ll, hh = l.rolling(14).min(), h.rolling(14).max()
    k = 100 * (c - ll) / (hh - ll).replace(0, np.nan)
    out["stoch_k"], out["stoch_d"] = k, k.rolling(3).mean()

    # --- Historical volatility (30/60) -------------------------------------
    r = np.log(c / c.shift())
    out["hv30"] = r.rolling(30).std() * np.sqrt(252) * 100
    out["hv60"] = r.rolling(60).std() * np.sqrt(252) * 100
    out["hv_ratio"] = out.hv30 / out.hv60

    # --- Volume ------------------------------------------------------------
    out["vol_ratio"] = v / v.rolling(20).mean()

    out["ret"] = c.pct_change()
    return out


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT symbol, bar_date, open, high, low, close, volume "
        "FROM price_bars ORDER BY symbol, bar_date").fetchall()
    con.close()

    by_sym = defaultdict(list)
    for r in rows:
        by_sym[r[0]].append(r[1:])
    print(f"{len(by_sym)} symbols, {len(rows):,} bars")

    # SPY returns for correlation
    spy = None
    if "SPY" in by_sym:
        d = pd.DataFrame(by_sym["SPY"], columns=["date", "open", "high", "low", "close", "volume"])
        d = d.set_index("date")
        spy = d["close"].pct_change()

    out = {}
    for i, (sym, recs) in enumerate(by_sym.items()):
        if len(recs) < 200:
            continue
        df = pd.DataFrame(recs, columns=["date", "open", "high", "low", "close", "volume"])
        df = df.set_index("date")
        try:
            ind = compute(df)
        except Exception as e:
            print(f"  {sym} failed: {e}")
            continue
        if spy is not None:
            ind["spy_corr"] = ind["ret"].rolling(60).corr(spy.reindex(ind.index))
        for d, row in ind.iterrows():
            rec = {k: (None if pd.isna(x) else float(x)) for k, x in row.items()}
            out[(sym, str(d)[:10])] = rec
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(by_sym)}")

    pickle.dump(out, open("indicators.pkl", "wb"))
    print(f"wrote {len(out):,} (symbol,date) indicator rows")


if __name__ == "__main__":
    main()
