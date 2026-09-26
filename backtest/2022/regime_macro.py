"""Classify each day into a regime using the user's three macro rules.

RULE 1  NH-NL & 200-day SMA  (structural bias)
  BULL : SPY > 200dma AND A/D at/near all-time high AND NH-NL persistently +ve
  BEAR : SPY < 200dma AND A/D breaking down AND NH-NL persistently -ve

RULE 2  VIX  (entry timing inside a bull)
  In a confirmed bull, a VIX spike is an elevated-premium entry, not a warning.

RULE 3  Credit spreads  (risk-off override)
  A/D breaking down WHILE credit widens -> risk-off; stop selling puts.

Plus the user's execution protocol trigger:
  ad_break_low  = A/D line closed below its prior reaction low -> exit puts
                  within 1-2 sessions.

COVERAGE CAVEAT, measured: the 200-day SMA is only computable from 2022-10-18,
so 199 of 251 days in 2022 have no 200dma. The 2022 bear market is Jan-Oct,
which means Rule 1 cannot be evaluated over the drawdown it is designed to
catch. A 200dma-free variant of each rule is therefore built alongside, using
only measures available on all 753 days, so 2022 is not silently excluded.
"""
import pickle
from collections import defaultdict

BULL, BEAR, FLAT = "BULL", "BEAR", "FLAT"


def load():
    return pickle.load(open("macro.pkl", "rb"))


def classify(m, d, use200=True):
    """Return (regime, reasons). Conservative: needs agreement, not one flag."""
    v = m[d]
    r = []

    above200 = v["spy_above200"] > 0 if v["spy_sma200"] else None
    ad_strong = v["ad_rising"] > 0
    ad_broke = v["ad_break_low"] > 0
    nhnl = v["nhnl_ma10"]
    credit_wide = v["credit_proxy_widening"] > 0

    # --- bear conditions --------------------------------------------------
    bear_votes = 0
    if use200 and above200 is False:
        bear_votes += 1; r.append("spy<200")
    if ad_broke or not ad_strong:
        bear_votes += 1; r.append("ad_weak")
    if nhnl is not None and nhnl < 0:
        bear_votes += 1; r.append("nhnl<0")

    # --- bull conditions --------------------------------------------------
    bull_votes = 0
    if use200 and above200 is True:
        bull_votes += 1; r.append("spy>200")
    if ad_strong and not ad_broke:
        bull_votes += 1; r.append("ad_strong")
    if nhnl is not None and nhnl > 0:
        bull_votes += 1; r.append("nhnl>0")

    need = 3 if use200 else 2
    # Rule 3 override: breadth breaking down WITH credit widening is risk-off
    # regardless of what the 200dma says.
    if ad_broke and credit_wide:
        return BEAR, r + ["RISKOFF(ad_break+credit)"]

    if bull_votes >= need:
        return BULL, r
    if bear_votes >= need:
        return BEAR, r
    return FLAT, r


def report(m, use200, label):
    ds = sorted(m)
    if use200:
        ds = [d for d in ds if m[d]["spy_sma200"]]
    lab = {d: classify(m, d, use200)[0] for d in ds}

    print()
    print("=" * 86)
    print(f"{label}   ({len(ds)} days classifiable)")
    print("=" * 86)

    # regime share by year
    print(f"  {'period':<10}{'days':>6}{'BULL':>8}{'BEAR':>8}{'FLAT':>8}"
          f"   SPY return over period")
    print("  " + "-" * 70)
    for yr in ("2022", "2023", "2024"):
        g = [d for d in ds if d.startswith(yr)]
        if not g:
            continue
        c = defaultdict(int)
        for d in g:
            c[lab[d]] += 1
        p0, p1 = m[g[0]]["spy"], m[g[-1]]["spy"]
        ret = 100 * (p1 / p0 - 1) if (p0 and p1) else 0
        print(f"  {yr:<10}{len(g):>6}{100*c[BULL]/len(g):>7.0f}%"
              f"{100*c[BEAR]/len(g):>7.0f}%{100*c[FLAT]/len(g):>7.0f}%"
              f"{ret:>+22.1f}%")

    # the real test: does the regime label predict the NEXT 10 days of SPY?
    print()
    print("  Forward 10-day SPY return by regime label (the actual test):")
    fwd = defaultdict(list)
    all_ds = sorted(m)
    idx = {d: i for i, d in enumerate(all_ds)}
    for d in ds:
        i = idx[d]
        if i + 10 >= len(all_ds):
            continue
        a, b = m[d]["spy"], m[all_ds[i + 10]]["spy"]
        if a and b:
            fwd[lab[d]].append(100 * (b / a - 1))
    for k in (BULL, FLAT, BEAR):
        g = fwd.get(k, [])
        if not g:
            continue
        up = sum(1 for x in g if x > 0)
        print(f"    {k:<6} n={len(g):>4}  mean {sum(g)/len(g):>+6.2f}%  "
              f"positive {100*up/len(g):>4.0f}%")
    b, r = fwd.get(BULL, []), fwd.get(BEAR, [])
    if b and r:
        sep = sum(b)/len(b) - sum(r)/len(r)
        print(f"    separation BULL - BEAR = {sep:+.2f}pp "
              f"{'(correct sign)' if sep > 0 else '(WRONG SIGN)'}")
    return lab


def main():
    m = load()
    lab_full = report(m, True, "RULE 1 FULL (with 200dma) -- 2023-24 plus Q4 2022 only")
    lab_no200 = report(m, False, "200dma-FREE variant -- all 753 days incl. the 2022 bear")

    pickle.dump({"with200": lab_full, "no200": lab_no200},
                open("regime_labels.pkl", "wb"))
    print()
    print("wrote regime_labels.pkl")


if __name__ == "__main__":
    main()
