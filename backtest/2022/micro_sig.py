"""Reproduce the micro-VVIX + short-term A/D divergence signal on OUR data.

Source: user's micro.py. Signal, verbatim from that script:

    p    = rolling percentile of VVIX over `vlook` days
    sh   = SPX >= its rolling `w`-day max        (price makes a new w-day high)
    ah   = A/D line >= its rolling `w`-day max   (breadth confirms)
    armed= (sh & ~ah) held for K+1 days          (unconfirmed high, K=3)
    fire = (p >= vpct) & armed

Two things differ from his run and must be stated:

1. His A/D is NYSE advance/decline (official to 2020-02, reconstructed after).
   Ours is built from the 494-symbol Polygon universe -- an S&P-ish large-cap
   set. A large-cap A/D line is NOT the NYSE line; it misses the small caps and
   the non-operating companies that dominate NYSE breadth. So this is a
   replication on a different breadth series, not a reproduction.
2. Our breadth only spans 2022-01-04..2024-12-31, so his full 2007-2026 window
   cannot be rechecked here. What CAN be checked is the claim that matters
   most to us: "the rule fired zero times in 2022."

His own A/D is normalised per-sector in our pickle (ad_line is a cumulative
sum of net-advance PERCENT), which is monotone-equivalent to a raw cumulative
A/D for the purpose of a rolling-max comparison, so the divergence test
carries over unchanged.
"""
import csv, datetime as dt, pickle

VVIX_CSV = "vvix_cboe.csv"


def load_vvix():
    out = {}
    for r in csv.DictReader(open(VVIX_CSV)):
        try:
            d = dt.datetime.strptime(r["DATE"], "%m/%d/%Y").date()
            v = float(r["VVIX"])
        except Exception:
            continue
        if v > 20:                      # his filter: drops bad early prints
            out[d.isoformat()] = v
    return out


def load_spx():
    """SPY adjusted close, from Yahoo -- the same source micro.py uses.

    The Polygon daily file was used first but only covers 2022, which made the
    2023/2024 firing counts read as a spurious zero. Fixed by pulling the full
    2021-2025 series so every year in our breadth window is testable.
    """
    out = {}
    for r in csv.DictReader(open("spy_yahoo.csv")):
        out[r["date"]] = float(r["close"])
    return out


def pctile(window, v):
    return sum(1 for x in window if v >= x) / len(window)


def rolling_max_flag(series, dates, w):
    """True on day i if series[i] >= max(series[i-w+1 .. i])."""
    flag = {}
    for i, d in enumerate(dates):
        lo = max(0, i - w + 1)
        flag[d] = series[d] >= max(series[x] for x in dates[lo:i + 1])
    return flag


def build(vlook, vpct, w, K=3):
    vv = load_vvix()
    spx = load_spx()
    b = pickle.load(open("breadth_all.pkl", "rb"))
    ad = {d: b[("MARKET", d)]["ad_line"] for (s, d) in b if s == "MARKET"}

    dates = sorted(set(vv) & set(ad) & set(spx))   # common trading days

    shi = rolling_max_flag(spx, dates, w)
    ahi = rolling_max_flag(ad, dates, w)

    # VVIX percentile needs a trailing window from the FULL vvix history,
    # not just the common dates, or the early percentiles are wrong.
    vd = sorted(vv)
    vidx = {d: i for i, d in enumerate(vd)}

    fire, detail = {}, []
    for i, d in enumerate(dates):
        j = vidx[d]
        if j < vlook // 2:
            continue
        win = [vv[x] for x in vd[max(0, j - vlook + 1):j + 1]]
        p = pctile(win, vv[d])
        # armed: unconfirmed new high within the last K+1 days
        armed = any(shi[x] and not ahi[x] for x in dates[max(0, i - K):i + 1])
        f = (p >= vpct) and armed
        fire[d] = f
        detail.append((d, vv[d], p, shi[d], ahi[d], armed, f))
    return fire, detail


def onsets(fire):
    ds = sorted(fire)
    return [d for i, d in enumerate(ds)
            if fire[d] and not (i and fire[ds[i - 1]])]


if __name__ == "__main__":
    print("Replication of micro.py signal on OUR breadth (2022-2024 only)")
    print("NOTE: our A/D is a 494-name large-cap line, not NYSE breadth.\n")
    print(f"{'cfg':<16}{'days':>6}{'fire':>7}{'onsets':>8}"
          f"{'2022 on':>9}{'2023 on':>9}{'2024 on':>9}")
    for vlook in (21, 63):
        for vpct in (0.80, 0.90):
            for w in (5, 10, 20):
                fire, det = build(vlook, vpct, w)
                if not fire:
                    continue
                ons = onsets(fire)
                c = {y: sum(1 for d in ons if d[:4] == str(y))
                     for y in (2022, 2023, 2024)}
                print(f"{f'{vlook}/{vpct}/{w}':<16}{len(fire):>6}"
                      f"{sum(fire.values()):>7}{len(ons):>8}"
                      f"{c[2022]:>9}{c[2023]:>9}{c[2024]:>9}")
