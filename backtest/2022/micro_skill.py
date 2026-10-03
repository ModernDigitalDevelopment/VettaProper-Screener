"""Does the micro gate block the RIGHT days, or just some days?

The overlap table showed the gate's blocked trades were, for the long tenor,
far BETTER than the trades it kept (+8 to +19% RoR vs +0.6%). That is the
wrong direction for a protective gate. But a raw comparison is not enough,
because the gate fires on high-VVIX days and high VVIX means fat credits --
so the blocked set is not a random sample of days.

The honest control is the one used earlier in this programme for the A/D
gates: does blocking THESE days beat blocking the same NUMBER of days chosen
at random? Random blocks are drawn with per-day blocking preserved (whole
entry days in or out, never individual trades) so the comparison respects the
same correlation structure.

Reported per config and tenor:
  observed  - net of the kept book under the real gate
  null mean - mean net of the kept book over `B` random day-sets of equal size
  pctile    - where the observed sits in the null distribution
              (high = the gate picked better-than-random days to skip)
"""
import pickle, random
from collections import defaultdict
import micro_sig as M

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
CFGS = [(21, 0.80, 5), (21, 0.80, 10), (21, 0.90, 5), (63, 0.80, 10)]
HOLD = 5
B = 5000
random.seed(13)


def blocked_days(fire, hold):
    ds = sorted(fire)
    out = set()
    for i, d in enumerate(ds):
        if fire[d]:
            for k in range(1, hold + 1):
                if i + k < len(ds):
                    out.add(ds[i + k])
    return out


def main():
    byten = defaultdict(list)
    for tag in TAGS:
        d = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        for k, rec in d.items():
            if k.endswith("|none"):
                for t in rec[0]:
                    byten[k.split("|")[0]].append(t)

    for tenor, trades in sorted(byten.items()):
        days = defaultdict(list)
        for t in trades:
            days[t["entry_date"][:10]].append(t)
        alld = sorted(days)
        full = sum(t["net_pnl"] for t in trades)
        print("\n" + "=" * 92)
        print(f"{tenor}   {len(trades)} trades on {len(alld)} entry days, "
              f"ungated net {full:+,.0f}")
        print("=" * 92)
        print(f"{'cfg':<14}{'blkdays':>8}{'kept net':>12}{'null mean':>12}"
              f"{'null p05':>11}{'null p95':>11}{'pctile':>8}")
        for vlook, vpct, w in CFGS:
            fire, _ = M.build(vlook, vpct, w)
            blk = blocked_days(fire, HOLD) & set(alld)
            if not blk:
                print(f"{f'{vlook}/{vpct}/{w}':<14}{0:>8}"
                      f"{'(blocks nothing)':>12}")
                continue
            obs = sum(t["net_pnl"] for d in alld if d not in blk
                      for t in days[d])
            k = len(blk)
            nulls = []
            for _ in range(B):
                skip = set(random.sample(alld, k))
                nulls.append(sum(t["net_pnl"] for d in alld if d not in skip
                                 for t in days[d]))
            nulls.sort()
            pc = sum(1 for x in nulls if x <= obs) / B
            print(f"{f'{vlook}/{vpct}/{w}':<14}{k:>8}{obs:>+12,.0f}"
                  f"{sum(nulls)/B:>+12,.0f}{nulls[int(.05*B)]:>+11,.0f}"
                  f"{nulls[int(.95*B)]:>+11,.0f}{pc:>8.2f}")
        print("  pctile ~0.50 = indistinguishable from skipping random days")
        print("  pctile <0.05 = the gate skipped days that were BETTER than "
              "average (it hurt)")


if __name__ == "__main__":
    main()
