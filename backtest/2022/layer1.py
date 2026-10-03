"""Layer 1 of the proposed overlay, tested on the bull-put book.

His Layer 1: "S&P above its 200-day average: 100% long. Below: 50% long."
Translated to this book, that is his explicit recommendation:

  "Below the 200-day: cut new position size in half, or move to iron condors."

This is the ONLY part of his proposal testable without the raw NYSE A/D files
(which were not in the upload -- analysis.py needs NYSE_advn.csv,
NYSE_decln.csv, ad_recon.csv and vvix.csv, none present). Layer 2 needs the
A/D line. Layer 1 needs only SPY and its 200dma, which we have.

Two things are measured, and they are different questions:

1. HALVING SIZE below the 200dma. This cannot change expectancy -- it is a
   linear scaling of each trade's P&L -- so it can only change the
   return/drawdown ratio. Measured as net/dd, the risk-equalised comparison.
   Reported because the earlier "stack" ablation already established sizing
   does not alter per-trade edge, and this is a direct re-test of that on a
   rule he proposed independently.

2. The REGIME SPLIT itself: do bull puts entered below SPY's 200dma actually
   perform worse? If they do not, the premise of Layer 1 fails and the
   sizing question is moot. This is the real test.

SPY's 200dma is computed from spy_yahoo.csv (5,463 days from 2005), so unlike
the per-symbol sma200 in trend22.pkl -- which only becomes available
2022-03-15 -- it covers every trading day in the book.
"""
import csv, pickle, random, math
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
B = 10000
random.seed(37)


def spy_ma(window=200):
    rows = [(r["date"], float(r["close"]))
            for r in csv.DictReader(open("spy_yahoo.csv"))]
    rows.sort()
    out = {}
    for i, (d, c) in enumerate(rows):
        if i + 1 >= window:
            w = [x[1] for x in rows[i + 1 - window:i + 1]]
            out[d] = (c, sum(w) / window)
    return out


def ror(ts):
    return (100*sum(t["net_pnl"]/t["max_loss"] for t in ts if t["max_loss"])
            / len(ts)) if ts else float("nan")


def dd_of(trades, scale=None):
    """Peak-to-trough on the realised curve, ordered by exit date."""
    ev = sorted(trades, key=lambda t: t["exit_date"])
    eq = peak = dd = 0.0
    for t in ev:
        s = 1.0 if scale is None else scale(t)
        eq += t["net_pnl"] * s
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return eq, dd


def main():
    ma = spy_ma(200)
    byten = defaultdict(lambda: defaultdict(list))
    for tag in TAGS:
        dd = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        for k, rec in dd.items():
            if k.endswith("|none"):
                byten[k.split("|")[0]][tag] += rec[0]

    print("=" * 96)
    print("TEST 1 -- do bull puts entered BELOW SPY's 200dma do worse?")
    print("This is the premise of Layer 1. If it fails, the sizing rule is moot.")
    print("=" * 96)
    for tn in sorted(byten):
        allt = [t for tag in TAGS for t in byten[tn][tag]]
        have = [t for t in allt if t["entry_date"][:10] in ma]
        below = [t for t in have if ma[t["entry_date"][:10]][0]
                 < ma[t["entry_date"][:10]][1]]
        above = [t for t in have if ma[t["entry_date"][:10]][0]
                 >= ma[t["entry_date"][:10]][1]]
        print(f"\n{tn}   {len(have)}/{len(allt)} trades have 200dma coverage")
        print(f"  ABOVE 200dma  n={len(above):>4} RoR={ror(above):>+7.2f}% "
              f"net={sum(t['net_pnl'] for t in above):>+10,.0f}")
        print(f"  BELOW 200dma  n={len(below):>4} RoR={ror(below):>+7.2f}% "
              f"net={sum(t['net_pnl'] for t in below):>+10,.0f}")
        if above and below:
            gap = ror(above) - ror(below)
            # day-blocked bootstrap of the gap
            da, db = defaultdict(list), defaultdict(list)
            for t in above:
                da[t["entry_date"][:10]].append(t["net_pnl"]/t["max_loss"])
            for t in below:
                db[t["entry_date"][:10]].append(t["net_pnl"]/t["max_loss"])
            ba, bb = list(da.values()), list(db.values())
            draws = []
            for _ in range(B):
                pa = [ba[random.randrange(len(ba))] for _ in range(len(ba))]
                pb = [bb[random.randrange(len(bb))] for _ in range(len(bb))]
                fa = [v for b in pa for v in b]
                fb = [v for b in pb for v in b]
                draws.append(100*(sum(fa)/len(fa) - sum(fb)/len(fb)))
            draws.sort()
            p = 2*min(sum(1 for z in draws if z <= 0),
                      sum(1 for z in draws if z >= 0))/B
            print(f"  gap (above - below) = {gap:+.2f}pp  "
                  f"95% CI [{draws[int(.025*B)]:+.2f}, {draws[int(.975*B)]:+.2f}]  "
                  f"p={min(p,1.0):.3f}")
        # per quarter, to expose composition
        print(f"  {'quarter':<10}{'n above':>9}{'RoR':>9}{'n below':>9}{'RoR':>9}")
        for tag in TAGS:
            tr = [t for t in byten[tn][tag] if t["entry_date"][:10] in ma]
            a = [t for t in tr if ma[t["entry_date"][:10]][0]
                 >= ma[t["entry_date"][:10]][1]]
            b = [t for t in tr if ma[t["entry_date"][:10]][0]
                 < ma[t["entry_date"][:10]][1]]
            print(f"  {tag:<10}{len(a):>9}"
                  f"{(f'{ror(a):+.2f}' if a else '--'):>9}{len(b):>9}"
                  f"{(f'{ror(b):+.2f}' if b else '--'):>9}")

    print("\n" + "=" * 96)
    print("TEST 2 -- HALVING size below the 200dma: net, drawdown, net/dd")
    print("Sizing cannot change expectancy, only the return/risk ratio.")
    print("=" * 96)
    for tn in sorted(byten):
        allt = [t for tag in TAGS for t in byten[tn][tag]
                if t["entry_date"][:10] in ma]
        def half(t):
            c, m = ma[t["entry_date"][:10]]
            return 0.5 if c < m else 1.0
        def zero(t):
            c, m = ma[t["entry_date"][:10]]
            return 0.0 if c < m else 1.0
        print(f"\n{tn}")
        print(f"  {'rule':<28}{'net':>12}{'peak dd':>11}{'net/dd':>9}")
        for name, sc in (("full size always", None),
                         ("half below 200dma (his L1)", half),
                         ("flat below 200dma", zero)):
            net, d = dd_of(allt, sc)
            print(f"  {name:<28}{net:>+12,.0f}{d:>11,.0f}"
                  f"{(net/d if d else float('nan')):>9.2f}")


if __name__ == "__main__":
    main()
