"""Is the VVIX level gate skill, or is it just "don't trade H1 2022"?

The screen looked excellent (percentiles 0.93-1.00). But panel 1 showed the
gate blocks 100% of Q1 2022 and 89% of Q2 2022 entry days -- and those are
exactly the two losing quarters. A rule that deletes the bad quarters wholesale
will always look brilliant in a pooled test. That is a CALENDAR effect wearing
a VVIX costume, and it is not tradeable knowledge: it says "2022 H1 was bad",
which we already knew, with hindsight.

The discriminating test is WITHIN-QUARTER. Inside a single quarter the macro
regime is roughly fixed, so if VVIX carries information the high-VVIX entry
days should still underperform the low-VVIX days of that same quarter. If the
effect vanishes within quarters, the pooled result was pure composition.

Three tests here:

1. WITHIN-QUARTER split at each quarter's own VVIX MEDIAN. Equal-sized halves,
   so composition cannot drive it.
2. Per-quarter random-null percentile for the fixed VVIX>100 gate, so each
   quarter is judged against its own trades only.
3. A direct composition check: what fraction of the pooled gate's benefit is
   explained purely by how many days it removes from each quarter?
"""
import csv, datetime as dt, pickle, random
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
B = 5000
random.seed(23)


def load_vvix():
    out = {}
    for r in csv.DictReader(open("vvix_cboe.csv")):
        try:
            d = dt.datetime.strptime(r["DATE"], "%m/%d/%Y").date()
            v = float(r["VVIX"])
        except Exception:
            continue
        if v > 20:
            out[d.isoformat()] = v
    return out


def ror(ts):
    return (100*sum(t["net_pnl"]/t["max_loss"] for t in ts if t["max_loss"])
            / len(ts)) if ts else float("nan")


def main():
    vv = load_vvix()
    data = defaultdict(lambda: defaultdict(list))   # tenor -> tag -> trades
    for tag in TAGS:
        d = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        for k, rec in d.items():
            if k.endswith("|none"):
                data[k.split("|")[0]][tag] += rec[0]

    for tenor in sorted(data):
        print("\n" + "=" * 98)
        print(f"TEST 1 -- WITHIN-QUARTER split at that quarter's own VVIX median")
        print(f"{tenor}")
        print("=" * 98)
        print(f"{'quarter':<10}{'median':>8}{'n hi':>6}{'n lo':>6}"
              f"{'hi RoR':>9}{'lo RoR':>9}{'lo-hi':>9}"
              f"{'hi net':>10}{'lo net':>10}")
        diffs = []
        for tag in TAGS:
            tr = [t for t in data[tenor][tag] if t["entry_date"][:10] in vv]
            if len(tr) < 8:
                continue
            vs = sorted(vv[t["entry_date"][:10]] for t in tr)
            med = vs[len(vs)//2]
            hi = [t for t in tr if vv[t["entry_date"][:10]] > med]
            lo = [t for t in tr if vv[t["entry_date"][:10]] <= med]
            if not hi or not lo:
                continue
            d_ = ror(lo) - ror(hi)
            diffs.append((tag, d_))
            print(f"{tag:<10}{med:>8.0f}{len(hi):>6}{len(lo):>6}"
                  f"{ror(hi):>+9.2f}{ror(lo):>+9.2f}{d_:>+9.2f}"
                  f"{sum(t['net_pnl'] for t in hi):>+10,.0f}"
                  f"{sum(t['net_pnl'] for t in lo):>+10,.0f}")
        if diffs:
            pos = sum(1 for _, d_ in diffs if d_ > 0)
            mean = sum(d_ for _, d_ in diffs)/len(diffs)
            print(f"  low-VVIX half better in {pos}/{len(diffs)} quarters, "
                  f"mean advantage {mean:+.2f}pp RoR")
            # sign test, two-sided
            n = len(diffs)
            from math import comb
            p = 2*sum(comb(n, i) for i in range(pos, n+1))/2**n
            print(f"  sign test p = {min(p,1.0):.3f}"
                  f"  ({'significant' if p < 0.05 else 'NOT significant'})")

    # ---- TEST 2: per-quarter null for the fixed VVIX>100 gate ------------
    for tenor in sorted(data):
        print("\n" + "=" * 98)
        print(f"TEST 2 -- VVIX>100 gate judged WITHIN each quarter")
        print(f"{tenor}")
        print("=" * 98)
        print(f"{'quarter':<10}{'blocked':>9}{'of days':>9}{'kept net':>12}"
              f"{'null mean':>12}{'pctile':>8}  note")
        for tag in TAGS:
            tr = [t for t in data[tenor][tag] if t["entry_date"][:10] in vv]
            days = defaultdict(list)
            for t in tr:
                days[t["entry_date"][:10]].append(t)
            alld = sorted(days)
            blk = [d for d in alld if vv[d] > 100]
            if not alld:
                continue
            if not blk or len(blk) == len(alld):
                print(f"{tag:<10}{len(blk):>9}{len(alld):>9}"
                      f"{'':>12}{'':>12}{'':>8}  "
                      f"{'DEGENERATE: blocks everything' if blk else 'blocks nothing'}")
                continue
            obs = sum(t["net_pnl"] for d in alld if d not in blk
                      for t in days[d])
            nulls = []
            for _ in range(B):
                skip = set(random.sample(alld, len(blk)))
                nulls.append(sum(t["net_pnl"] for d in alld if d not in skip
                                 for t in days[d]))
            nulls.sort()
            pc = sum(1 for z in nulls if z <= obs)/B
            print(f"{tag:<10}{len(blk):>9}{len(alld):>9}{obs:>+12,.0f}"
                  f"{sum(nulls)/B:>+12,.0f}{pc:>8.2f}")

    # ---- TEST 3: composition accounting ---------------------------------
    print("\n" + "=" * 98)
    print("TEST 3 -- how much of the pooled gain is just removing bad quarters?")
    print("=" * 98)
    for tenor in sorted(data):
        alltr = [t for tag in TAGS for t in data[tenor][tag]
                 if t["entry_date"][:10] in vv]
        full = sum(t["net_pnl"] for t in alltr)
        kept = [t for t in alltr if vv[t["entry_date"][:10]] <= 100]
        gain = sum(t["net_pnl"] for t in kept) - full
        print(f"\n{tenor}: gate lifts net by {gain:+,.0f}")
        print(f"  {'quarter':<10}{'removed net':>14}{'share of lift':>15}")
        for tag in TAGS:
            rem = [t for t in data[tenor][tag]
                   if t["entry_date"][:10] in vv
                   and vv[t["entry_date"][:10]] > 100]
            r = -sum(t["net_pnl"] for t in rem)
            print(f"  {tag:<10}{-r:>+14,.0f}{100*r/gain if gain else 0:>14.0f}%")
        h1 = sum(-t["net_pnl"] for tag in ("2022Q1", "2022Q2")
                 for t in data[tenor][tag]
                 if t["entry_date"][:10] in vv
                 and vv[t["entry_date"][:10]] > 100)
        print(f"  --> H1 2022 alone accounts for "
              f"{100*h1/gain if gain else 0:.0f}% of the lift")


if __name__ == "__main__":
    main()
