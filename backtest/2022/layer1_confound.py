"""Is the 200dma split skill, or the H1-2022 calendar confound again?

TEST 1 of layer1.py gave above-200dma minus below-200dma = +8.42pp on the
short tenor, p=0.034 -- nominally significant, and the first thing in this
whole programme to clear 0.05. Before reporting that, check the per-quarter
composition, because the pooled split is wildly unbalanced:

    2022Q3   2 above / 131 below
    2022Q4  16 above / 105 below
    2023Q2 140 above /   0 below
    2023Q4 129 above /   7 below

"Above the 200dma" is almost a synonym for "2023", and 2023 was profitable.
"Below" is almost a synonym for "2022 H2", which was not. That is the exact
structure that made the VVIX level gate look brilliant and turned out to be a
calendar rule.

The within-quarter comparison is the discriminating one, and the per-quarter
rows in layer1.py already hint at the answer: BELOW looked BETTER in 4 of the
5 quarters where both sides exist. This script makes that rigorous.
"""
import csv, pickle, random, math
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
B = 10000
random.seed(43)


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


def main():
    ma = spy_ma(200)
    byten = defaultdict(lambda: defaultdict(list))
    for tag in TAGS:
        dd = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        for k, rec in dd.items():
            if k.endswith("|none"):
                byten[k.split("|")[0]][tag] += rec[0]

    print("=" * 96)
    print("A. COMPOSITION -- how unbalanced is the split?")
    print("=" * 96)
    for tn in sorted(byten):
        print(f"\n{tn}")
        print(f"  {'quarter':<10}{'n above':>9}{'n below':>9}"
              f"{'% above':>9}{'qtr RoR':>10}")
        for tag in TAGS:
            tr = [t for t in byten[tn][tag] if t["entry_date"][:10] in ma]
            a = sum(1 for t in tr if ma[t["entry_date"][:10]][0]
                    >= ma[t["entry_date"][:10]][1])
            print(f"  {tag:<10}{a:>9}{len(tr)-a:>9}"
                  f"{100*a/len(tr) if tr else 0:>8.0f}%{ror(tr):>+10.2f}")

    print("\n" + "=" * 96)
    print("B. WITHIN-QUARTER -- the discriminating test")
    print("Only quarters with >=5 trades on BOTH sides can be compared.")
    print("=" * 96)
    for tn in sorted(byten):
        print(f"\n{tn}")
        print(f"  {'quarter':<10}{'n above':>9}{'RoR above':>11}"
              f"{'n below':>9}{'RoR below':>11}{'above-below':>13}")
        diffs = []
        for tag in TAGS:
            tr = [t for t in byten[tn][tag] if t["entry_date"][:10] in ma]
            a = [t for t in tr if ma[t["entry_date"][:10]][0]
                 >= ma[t["entry_date"][:10]][1]]
            b = [t for t in tr if ma[t["entry_date"][:10]][0]
                 < ma[t["entry_date"][:10]][1]]
            if len(a) < 5 or len(b) < 5:
                print(f"  {tag:<10}{len(a):>9}{'--':>11}{len(b):>9}{'--':>11}"
                      f"{'(skip: one side <5)':>13}")
                continue
            d = ror(a) - ror(b)
            diffs.append(d)
            print(f"  {tag:<10}{len(a):>9}{ror(a):>+11.2f}{len(b):>9}"
                  f"{ror(b):>+11.2f}{d:>+13.2f}")
        if diffs:
            pos = sum(1 for d in diffs if d > 0)
            n = len(diffs)
            p = 2*sum(math.comb(n, i)
                      for i in range(max(pos, n-pos), n+1))/2**n
            print(f"  --> above better in {pos}/{n} comparable quarters, "
                  f"mean {sum(diffs)/n:+.2f}pp, sign test p={min(p,1.0):.3f}")

    print("\n" + "=" * 96)
    print("C. STRATIFIED test -- pool the WITHIN-quarter differences only")
    print("Day-blocked bootstrap, quarter held fixed, so composition is")
    print("mathematically removed rather than argued away.")
    print("=" * 96)
    for tn in sorted(byten):
        # build per-quarter day blocks for each side
        qa, qb = {}, {}
        for tag in TAGS:
            tr = [t for t in byten[tn][tag]
                  if t["entry_date"][:10] in ma and t["max_loss"]]
            a, b = defaultdict(list), defaultdict(list)
            for t in tr:
                c, m = ma[t["entry_date"][:10]]
                (a if c >= m else b)[t["entry_date"][:10]].append(
                    t["net_pnl"]/t["max_loss"])
            if len(a) >= 2 and len(b) >= 2:
                qa[tag], qb[tag] = list(a.values()), list(b.values())
        if not qa:
            print(f"\n{tn}: no quarter has both sides; untestable")
            continue
        def stat(resample=False):
            ds = []
            for tag in qa:
                A, Bk = qa[tag], qb[tag]
                if resample:
                    A = [A[random.randrange(len(A))] for _ in range(len(A))]
                    Bk = [Bk[random.randrange(len(Bk))] for _ in range(len(Bk))]
                fa = [v for x in A for v in x]
                fb = [v for x in Bk for v in x]
                if fa and fb:
                    ds.append(sum(fa)/len(fa) - sum(fb)/len(fb))
            return 100*sum(ds)/len(ds) if ds else float("nan")
        obs = stat()
        draws = sorted(stat(True) for _ in range(B))
        p = 2*min(sum(1 for z in draws if z <= 0),
                  sum(1 for z in draws if z >= 0))/B
        print(f"\n{tn}   quarters used: {', '.join(qa)}")
        print(f"  stratified mean (above - below) = {obs:+.2f}pp")
        print(f"  95% CI [{draws[int(.025*B)]:+.2f}, {draws[int(.975*B)]:+.2f}]"
              f"   p={min(p,1.0):.3f}  "
              f"{'SIGNIFICANT' if min(p,1.0) < 0.05 else 'NOT significant'}")


if __name__ == "__main__":
    main()
