"""BROKEN for ADX/DMI/stochastics/ATR -- superseded by rebuild_ind22.py.

The load_ohlc() below takes MIN/MAX of the option table's underlying_price to
approximate a daily high/low. ThetaData repeats ONE underlying price on every
option row of a symbol-day, so MIN == MAX == close on all 21,876 symbol-days.
True range collapses to |close change| and, because Wilder smoothing is linear,
+DI comes out algebraically identical to RSI.

The trend/SMA and HV/IV outputs are unaffected (they only use close).
For indicators, use rebuild_ind22.py, which reads real Polygon high/low.
"""

"""Build every signal the 2022 tests need, from option-DB underlying prices.

Using underlying_price out of the option rows (rather than the separate Polygon
stock file) guarantees the price series and the option quotes come from the same
vendor on the same timestamp. A mismatch there would put the trend filter and
the strike selection on slightly different prices.

Outputs (all keyed (symbol, trade_date)):
  trend22.pkl   close, sma10, sma20, sma30, sma50
                + smooth-trend fields: days_above, max_stretch_pct, mean_stretch
  ind22.pkl     adx14, plus_di, minus_di, rsi14, stoch_k, stoch_d, atr_pct
  hviv22.pkl    hv20, hv30, atm_iv, hv_minus_iv
"""
import pickle
import sqlite3
from collections import defaultdict

DBS = [f"/home/user/db2022/thetadata_options_{q}_2022.db" for q in
       ("q1", "q2", "q3", "q4")]


def wilder(v, n):
    if not v:
        return []
    out = [float(v[0])]
    a = 1.0 / n
    for x in v[1:]:
        out.append(out[-1] + a * (float(x) - out[-1]))
    return out


def load_ohlc():
    """Daily OHLC per symbol from the option table's underlying price.

    ThetaData stores one underlying_price per option row; high/low across a
    day's rows approximates the underlying's intraday range closely enough for
    ATR/ADX/stochastics, and close is taken from the last row of the day.
    """
    bars = defaultdict(dict)
    for db in DBS:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        q = """SELECT symbol, trade_date,
                      MIN(underlying_price), MAX(underlying_price),
                      AVG(underlying_price), COUNT(*)
               FROM option_eod WHERE underlying_price > 0
               GROUP BY symbol, trade_date"""
        for sym, d, lo, hi, avg, n in c.execute(q):
            bars[sym][d] = (float(lo), float(hi), float(avg))
        c.close()
        print(f"  {db.split('_')[-1]}: {len(bars)} symbols", flush=True)
    return bars


def main():
    bars = load_ohlc()
    trend, ind, hviv = {}, {}, {}

    for sym, days in bars.items():
        ds = sorted(days)
        if len(ds) < 60:
            continue
        lo = [days[d][0] for d in ds]
        hi = [days[d][1] for d in ds]
        c = [days[d][2] for d in ds]
        n = len(ds)

        # --- ATR / ADX / DMI ---------------------------------------------
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

        # --- RSI ----------------------------------------------------------
        gains = [max(c[i] - c[i - 1], 0.0) for i in range(1, n)]
        losses = [max(c[i - 1] - c[i], 0.0) for i in range(1, n)]
        ag, al = wilder(gains, 14), wilder(losses, 14)

        # --- rolling SMAs and smooth-trend state --------------------------
        above = 0                      # consecutive days sma10 > sma50
        stretch_hist = []              # (sma10-sma50)/sma50 while above

        for i in range(50, n):
            w = c[: i + 1]
            s10 = sum(w[-10:]) / 10
            s20 = sum(w[-20:]) / 20
            s30 = sum(w[-30:]) / 30
            s50 = sum(w[-50:]) / 50

            st10 = (s10 - s50) / s50 * 100 if s50 else 0.0
            st20 = (s20 - s50) / s50 * 100 if s50 else 0.0

            if s10 > s50:
                above += 1
                stretch_hist.append(st10)
            else:
                above = 0
                stretch_hist = []

            look = stretch_hist[-20:]
            trend[(sym, ds[i])] = {
                "close": c[i], "sma10": s10, "sma20": s20,
                "sma30": s30, "sma50": s50,
                "stretch10": st10, "stretch20": st20,
                "days_above": above,
                "max_stretch": max(look) if look else 0.0,
                "mean_stretch": sum(look) / len(look) if look else 0.0,
                # slope of the stretch: rising fast = spike, flat = smooth
                "stretch_slope": (look[-1] - look[0]) / len(look) if len(look) > 1 else 0.0,
            }

            g, l = ag[i - 1], al[i - 1]
            # Stochastic %K(14) and %D(3)
            hh = max(hi[i - 13:i + 1])
            ll = min(lo[i - 13:i + 1])
            k = 100 * (c[i] - ll) / (hh - ll) if hh > ll else 50.0
            ks = []
            for j in (i, i - 1, i - 2):
                h2 = max(hi[j - 13:j + 1])
                l2 = min(lo[j - 13:j + 1])
                ks.append(100 * (c[j] - l2) / (h2 - l2) if h2 > l2 else 50.0)

            ind[(sym, ds[i])] = {
                "adx14": adx[i], "plus_di": pdi[i], "minus_di": mdi[i],
                "rsi14": 100.0 if l == 0 else 100 - 100 / (1 + g / l),
                "stoch_k": k, "stoch_d": sum(ks) / 3,
                "atr_pct": 100 * atr[i] / c[i] if c[i] else 0.0,
            }

            # --- realised vol (annualised, %) -----------------------------
            import math
            def rv(win):
                seg = c[max(0, i - win):i + 1]
                r = [math.log(seg[j] / seg[j - 1]) for j in range(1, len(seg))
                     if seg[j - 1] > 0 and seg[j] > 0]
                if len(r) < 5:
                    return None
                mu = sum(r) / len(r)
                var = sum((x - mu) ** 2 for x in r) / (len(r) - 1)
                return 100 * math.sqrt(var) * math.sqrt(252)

            hviv[(sym, ds[i])] = {"hv20": rv(20), "hv30": rv(30)}

    print(f"trend22 {len(trend):,} | ind22 {len(ind):,} | hv {len(hviv):,}")

    # --- ATM implied vol, to compare against HV ---------------------------
    atm = {}
    for db in DBS:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        q = """SELECT symbol, trade_date, AVG(implied_vol)
               FROM option_eod
               WHERE implied_vol > 0
                 AND ABS(strike - underlying_price) / underlying_price < 0.03
               GROUP BY symbol, trade_date"""
        for sym, d, iv in c.execute(q):
            atm[(sym, d)] = float(iv) * 100      # to %
        c.close()
    print(f"atm iv: {len(atm):,}")

    for k in hviv:
        iv = atm.get(k)
        hviv[k]["atm_iv"] = iv
        hv = hviv[k].get("hv30")
        hviv[k]["hv_minus_iv"] = (hv - iv) if (hv is not None and iv) else None

    pickle.dump(trend, open("trend22.pkl", "wb"), protocol=5)
    pickle.dump(ind, open("ind22.pkl", "wb"), protocol=5)
    pickle.dump(hviv, open("hviv22.pkl", "wb"), protocol=5)
    print("written")


if __name__ == "__main__":
    main()
