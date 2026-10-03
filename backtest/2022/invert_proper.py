"""The inversion hypothesis, tested with the errors removed.

Two problems with the first pass (micro_invert.py):

1. TEST A's sign test was INVALID. It treated 8-10 configs as independent
   trials, but their armed-day sets overlap with Jaccard 0.50-0.80 -- the
   21-day family in particular is one test wearing six hats (union of all 12
   configs is only 134 days). A sign test on correlated trials massively
   understates p. Retracted.

2. Picking the configs that came out positive IS the selection effect. The
   honest version takes a MAX-STATISTIC across all configs and permutes, so
   the null knows we looked at twelve.

Replaced with two tests that have real power:

TEST 1 -- the ECONOMIC hypothesis, directly, on all 912 trades.
  The inversion claim reduces to: bull puts entered when vol-of-vol is
  elevated do BETTER. That does not need the micro signal at all, and tested
  on every trade it has ~30x the sample size of the signal-day subsets.
  VVIX is demeaned WITHIN QUARTER, so the H1-2022 composition confound that
  killed the level gate cannot operate. Spearman-style rank correlation plus
  within-quarter tercile split.

TEST 2 -- the micro signal as an entry trigger, with a max-statistic
  permutation that corrects for having scanned 12 configs. Entry days are
  permuted in day-blocks within quarter.
"""
import csv, datetime as dt, math, pickle, random
from collections import defaultdict
import micro_sig as M

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
ALLCFG = [(vl, vp, w) for vl in (21, 63) for vp in (0.80, 0.90)
          for w in (5, 10, 20)]
B = 10000
random.seed(31)


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


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0]*len(v)
        i = 0
        while i < len(order):
            j = i
            while j+1 < len(order) and v[order[j+1]] == v[order[i]]:
                j += 1
            avg = (i+j)/2 + 1
            for k in range(i, j+1):
                r[order[k]] = avg
            i = j+1
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx)/n, sum(ry)/n
    num = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a-mx)**2 for a in rx)*sum((b-my)**2 for b in ry))
    return num/den if den else 0.0


def main():
    vv = load_vvix()
    byten = defaultdict(lambda: defaultdict(list))
    for tag in TAGS:
        dd = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        for k, rec in dd.items():
            if k.endswith("|none"):
                byten[k.split("|")[0]][tag] += rec[0]

    print("=" * 98)
    print("TEST 1 -- does ELEVATED VVIX AT ENTRY predict BETTER bull puts?")
    print("All trades. VVIX demeaned within quarter, so composition is out.")
    print("This is the inversion hypothesis in its most powerful form.")
    print("=" * 98)
    for tn in sorted(byten):
        xs, ys = [], []
        for tag in TAGS:
            tr = [t for t in byten[tn][tag]
                  if t["entry_date"][:10] in vv and t["max_loss"]]
            if len(tr) < 8:
                continue
            vs = [vv[t["entry_date"][:10]] for t in tr]
            mu = sum(vs)/len(vs)
            for t, v in zip(tr, vs):
                xs.append(v - mu)                       # within-quarter VVIX
                ys.append(100*t["net_pnl"]/t["max_loss"])
        rho = spearman(xs, ys)
        n = len(xs)
        # permutation null on rho, shuffling y
        null = []
        yy = list(ys)
        for _ in range(2000):
            random.shuffle(yy)
            null.append(spearman(xs, yy))
        null.sort()
        p = 2*min(sum(1 for z in null if z <= rho),
                  sum(1 for z in null if z >= rho))/len(null)
        print(f"\n{tn}   n={n}")
        print(f"  Spearman rho(VVIX_demeaned, RoR) = {rho:+.4f}   "
              f"two-sided p = {min(p,1.0):.3f}")
        print(f"  (positive rho would SUPPORT the inversion: "
              f"higher VVIX -> better bull puts)")
        # within-quarter terciles
        print(f"  {'quarter':<10}{'lowV RoR':>10}{'midV RoR':>10}"
              f"{'highV RoR':>11}{'high-low':>10}")
        wins = 0
        tot = 0
        for tag in TAGS:
            tr = [t for t in byten[tn][tag]
                  if t["entry_date"][:10] in vv and t["max_loss"]]
            if len(tr) < 9:
                continue
            tr.sort(key=lambda t: vv[t["entry_date"][:10]])
            k = len(tr)//3
            lo, mid, hi = tr[:k], tr[k:2*k], tr[2*k:]
            d = ror(hi)-ror(lo)
            wins += d > 0
            tot += 1
            print(f"  {tag:<10}{ror(lo):>+10.2f}{ror(mid):>+10.2f}"
                  f"{ror(hi):>+11.2f}{d:>+10.2f}")
        if tot:
            pb = 2*sum(math.comb(tot, i)
                       for i in range(max(wins, tot-wins), tot+1))/2**tot
            print(f"  high-VVIX tercile better in {wins}/{tot} quarters, "
                  f"sign test p={min(pb,1.0):.3f}")

    print("\n" + "=" * 98)
    print("TEST 2 -- micro signal as ENTRY trigger, max-statistic corrected")
    print("Null knows we scanned 12 configs. Day-blocks permuted in-quarter.")
    print("=" * 98)
    armed = {}
    for c in ALLCFG:
        f, _ = M.build(*c)
        ds = sorted(f)
        s = set()
        for i, d in enumerate(ds):
            if f[d]:
                for kk in range(1, 6):
                    if i+kk < len(ds):
                        s.add(ds[i+kk])
        armed[c] = s

    for tn in sorted(byten):
        qdays = {}
        for tag in TAGS:
            dd = defaultdict(list)
            for t in byten[tn][tag]:
                if t["max_loss"]:
                    dd[t["entry_date"][:10]].append(t)
            qdays[tag] = dd
        allt = [t for tag in TAGS for ts in qdays[tag].values() for t in ts]
        base = ror(allt)

        def stat_for(sel_by_q):
            ts = [t for tag in TAGS for d, tl in qdays[tag].items()
                  if d in sel_by_q[tag] for t in tl]
            return ror(ts) if len(ts) >= 10 else None

        obs = {}
        for c in ALLCFG:
            sel = {tag: {d for d in qdays[tag] if d in armed[c]}
                   for tag in TAGS}
            v = stat_for(sel)
            if v is not None:
                obs[c] = v - base
        if not obs:
            print(f"\n{tn}: no config reaches 10 trades; untestable")
            continue
        bestc = max(obs, key=lambda c: obs[c])
        bestv = obs[bestc]
        # null: same per-quarter counts, random days
        counts = {c: {tag: len([d for d in qdays[tag] if d in armed[c]])
                      for tag in TAGS} for c in ALLCFG}
        nullmax = []
        for _ in range(B):
            m = -1e9
            for c in obs:
                sel = {}
                for tag in TAGS:
                    dl = list(qdays[tag])
                    k = min(counts[c][tag], len(dl))
                    sel[tag] = set(random.sample(dl, k)) if k else set()
                v = stat_for(sel)
                if v is not None:
                    m = max(m, v - base)
            nullmax.append(m)
        nullmax.sort()
        p = sum(1 for z in nullmax if z >= bestv)/B
        print(f"\n{tn}   all-days RoR {base:+.2f}%, {len(obs)} testable configs")
        print(f"  best config {bestc[0]}/{bestc[1]}/{bestc[2]}: "
              f"{bestv:+.2f}pp vs all-days")
        print(f"  max-statistic null mean {sum(nullmax)/B:+.2f}pp, "
              f"p95 {nullmax[int(.95*B)]:+.2f}pp")
        print(f"  corrected p = {p:.3f}   "
              f"{'SIGNIFICANT' if p < 0.05 else 'NOT significant'}")


if __name__ == "__main__":
    main()
