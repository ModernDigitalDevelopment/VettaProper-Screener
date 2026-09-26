"""The asymmetric spec's GATE on 2023, without option prices.

WHY THIS IS NOT THE FULL TEST, stated plainly: the 2023 option databases were
deleted to make room for the 2022 extraction, and without bid/ask/delta a
spread cannot be priced. No P&L figure for 2023 is possible from what is on
disk. Re-running the +$64,854 result requires re-uploading those DBs.

WHAT IS POSSIBLE, and it is still decisive: the asym spec is a SIDE-SELECTION
rule plus a fixed structure. The side choice depends only on closes --
  bear call when sma5 < sma20
  bull put  when sma5 > sma20 and the last two closes were down
-- all of which exist for 2023. So the gate can be replayed exactly, and for
each selection the SUBSEQUENT UNDERLYING MOVE can be measured over the
holding period the spec would have used (9 DTE for calls, 5 for puts).

That answers the question that actually matters: in a bull year, does this
gate keep putting on bear calls into rallies? A short call at delta 0.25 is
breached by roughly a +4-6% move in the underlying over 9 days, so the
adverse-move rate is a direct proxy for whether the spec survives 2023.

The same replay is run on 2022 as a control, where the true P&L is known to be
+$64,854. If the 2022 adverse rate is low and the 2023 rate is high, the spec
is regime-dependent and the 2022 result does not generalise.
"""
import pickle
from collections import defaultdict

# a 0.25-delta short strike sits roughly this far OTM at ~9 DTE (measured
# from the 2022 chains: delta 0.20-0.25 -> median 7.3% OTM, 0.25-0.30 -> 5.6%)
BREACH_MOVE = 6.0
CALL_HOLD = 9
PUT_HOLD = 5


def closes_for(year):
    """Daily closes per symbol for the given year, plus 60 prior sessions."""
    import csv
    import gzip
    px = defaultdict(dict)
    if year == 2022:
        with gzip.open("/home/user/vps/backtest/data/daily_2022.csv.gz", "rt") as fh:
            for r in csv.DictReader(fh):
                px[r["symbol"]][r["date"]] = float(r["close"])
    t = pickle.load(open("trend.pkl", "rb"))
    for (sym, d), v in t.items():
        px[sym][d] = v["close"]
    return px


def replay(px, year):
    """Replay the asym gate; return per-selection forward-move records."""
    recs = []
    for sym, series in px.items():
        ds = sorted(series)
        for i in range(20, len(ds)):
            d = ds[i]
            if not d.startswith(str(year)):
                continue
            w = [series[x] for x in ds[:i + 1]]
            s5 = sum(w[-5:]) / 5
            s20 = sum(w[-20:]) / 20
            spot = w[-1]

            side = None
            if s5 < s20:
                side = "bear_call"
                hold = CALL_HOLD
            elif s5 > s20:
                d0, d1, d2 = w[-1], w[-2], w[-3]
                if d0 < d1 and d1 < d2:
                    side = "bull_put"
                    hold = PUT_HOLD
            if side is None:
                continue

            j = min(i + hold, len(ds) - 1)
            if j <= i:
                continue
            path = w[i - i:]            # not used; keep explicit below
            fwd = [series[ds[k]] for k in range(i, j + 1)]
            end = fwd[-1]
            hi = max(fwd)
            lo = min(fwd)
            # adverse excursion for the side taken
            if side == "bear_call":
                adverse = 100 * (hi / spot - 1)      # rally hurts a short call
            else:
                adverse = 100 * (1 - lo / spot)      # drop hurts a short put
            recs.append({
                "sym": sym, "date": d, "side": side,
                "ret": 100 * (end / spot - 1),
                "adverse": adverse,
                "breached": adverse >= BREACH_MOVE,
            })
    return recs


def report(recs, label):
    print()
    print("=" * 88)
    print(label)
    print("=" * 88)
    by = defaultdict(list)
    for r in recs:
        by[r["side"]].append(r)
    print(f"  {'side':<11}{'n':>7}{'share':>8}{'mean adverse':>14}"
          f"{'breach rate':>13}{'mean fwd ret':>14}")
    print("  " + "-" * 70)
    tot = len(recs)
    for side in ("bear_call", "bull_put"):
        g = by.get(side, [])
        if not g:
            continue
        n = len(g)
        adv = sum(r["adverse"] for r in g) / n
        br = sum(1 for r in g if r["breached"]) / n
        fr = sum(r["ret"] for r in g) / n
        print(f"  {side:<11}{n:>7}{100*n/tot:>7.0f}%{adv:>13.2f}%"
              f"{100*br:>12.1f}%{fr:>+13.2f}%")
    allbr = sum(1 for r in recs if r["breached"]) / tot
    print(f"  {'ALL':<11}{tot:>7}{100:>7.0f}%"
          f"{sum(r['adverse'] for r in recs)/tot:>13.2f}%"
          f"{100*allbr:>12.1f}%"
          f"{sum(r['ret'] for r in recs)/tot:>+13.2f}%")
    return {"n": tot, "breach": allbr,
            "by": {s: (len(g), sum(1 for r in g if r["breached"]) / len(g))
                   for s, g in by.items() if g}}


def main():
    print("NOTE: 2023 option DBs were deleted; no 2023 P&L is computable.")
    print("This replays the SIDE-SELECTION gate and measures the adverse move")
    print(f"in the underlying. A ~{BREACH_MOVE:.0f}% adverse move breaches a "
          f"0.25-delta short strike.")

    out = {}
    for year in (2022, 2023):
        px = closes_for(year)
        recs = replay(px, year)
        out[year] = report(recs, f"ASYM GATE REPLAY -- {year} "
                                 f"({'known P&L +$64,854' if year == 2022 else 'P&L UNKNOWN'})")
        pickle.dump(recs, open(f"asym_gate_{year}.pkl", "wb"))

    print()
    print("=" * 88)
    print("VERDICT")
    print("=" * 88)
    a, b = out[2022], out[2023]
    print(f"  2022 breach rate {100*a['breach']:.1f}%   "
          f"2023 breach rate {100*b['breach']:.1f}%")
    for s in ("bear_call", "bull_put"):
        if s in a["by"] and s in b["by"]:
            n1, r1 = a["by"][s]
            n2, r2 = b["by"][s]
            print(f"  {s:<11} 2022 {100*r1:>5.1f}% (n={n1:>6})   "
                  f"2023 {100*r2:>5.1f}% (n={n2:>6})   "
                  f"delta {100*(r2-r1):+.1f}pp")
    print()
    if b["breach"] > a["breach"] * 1.15:
        print("  -> 2023 is materially WORSE. The spec is regime-dependent and")
        print("     the 2022 result should not be expected to repeat.")
    elif b["breach"] < a["breach"] * 0.85:
        print("  -> 2023 is materially BETTER. Encouraging, but a P&L test is")
        print("     still required before believing it.")
    else:
        print("  -> comparable. Neither confirms nor refutes; needs real prices.")


if __name__ == "__main__":
    main()
