"""Validate the one endogenous rule that looked good: pause after N losses.

mine_reentry.py found, on the LONG tenor only:
    pause after 3 straight losses -> net/dd 0.70 vs 0.23 control,
    skipped trades earned -14.90% RoR, random-null percentile 0.94.

Four reasons to distrust it before reporting:

1. BEST-OF-9. Nine rules were scanned. 0.94 uncorrected is ~nothing after
   correction. Fixed here with a max-statistic null over all 9 rules.
2. OPPOSITE SIGN ON THE SHORT TENOR (percentile 0.01, i.e. far WORSE than
   random). A mechanism that helps one tenor and hurts the other is not a
   mechanism.
3. A tie-breaking bug in my own first pass: `sorted(hist)` sorts
   (exit_date, net_pnl) tuples, so same-day closes get ordered by P&L --
   losses first. That biases "last N were all losses" toward firing. Fixed
   here by sorting on exit_date only, stable.
4. PER-QUARTER stability -- if it is one quarter it is the H1-2022 confound
   in yet another costume.
"""
import pickle, random, math
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
B = 4000
random.seed(59)


def dd_of(ts):
    eq = peak = dd = 0.0
    for t in sorted(ts, key=lambda x: x["exit_date"][:10]):
        eq += t["net_pnl"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return eq, dd


def ror(ts):
    return (100*sum(t["net_pnl"]/t["max_loss"] for t in ts)/len(ts)
            if ts else float("nan"))


def simulate(trades, n):
    """Pause after n consecutive losing closes; resume on next winning close.

    FIX vs first pass: history is sorted by exit_date ONLY (stable), so
    same-day closes keep insertion order instead of being reordered
    losses-first.
    """
    ordered = sorted(trades, key=lambda t: (t["entry_date"][:10], t["symbol"]))
    closed = []
    taken, skipped = [], []
    for t in ordered:
        ed = t["entry_date"][:10]
        hist = sorted([c for c in closed if c[0] < ed], key=lambda c: c[0])
        ok = True
        if len(hist) >= n:
            ok = not all(p <= 0 for _, p in hist[-n:])
        (taken if ok else skipped).append(t)
        if ok:
            closed.append((t["exit_date"][:10], t["net_pnl"]))
    return taken, skipped


def main():
    byten = defaultdict(lambda: defaultdict(list))
    for tag in TAGS:
        d = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        for k, rec in d.items():
            if k.endswith("|none"):
                byten[k.split("|")[0]][tag] += rec[0]

    NS = [2, 3, 4, 5]
    for tenor in sorted(byten):
        trades = [t for tag in TAGS for t in byten[tenor][tag]]
        bn, bd = dd_of(trades)
        print("\n" + "=" * 100)
        print(f"{tenor}   control net {bn:+,.0f} dd {bd:,.0f} "
              f"net/dd {bn/bd if bd else 0:+.2f}")
        print("=" * 100)
        days = defaultdict(list)
        for t in trades:
            days[t["entry_date"][:10]].append(t)
        alld = sorted(days)

        print(f"{'rule':<14}{'taken':>7}{'skip%':>7}{'net':>11}{'dd':>10}"
              f"{'net/dd':>8}{'skipRoR':>9}")
        res = {}
        for n in NS:
            tk, sk = simulate(trades, n)
            net, d = dd_of(tk)
            res[n] = (net, d, tk, sk)
            print(f"{f'streak {n}':<14}{len(tk):>7}"
                  f"{100*len(sk)/len(trades):>6.0f}%{net:>+11,.0f}"
                  f"{d:>10,.0f}{(net/d if d else 0):>8.2f}"
                  f"{ror(sk) if sk else float('nan'):>+9.2f}")

        # ---- max-statistic null over the rules scanned ---------------
        print(f"\n  max-statistic null (corrects for scanning {len(NS)} rules),"
              f" criterion = net/dd")
        obs_best_n = max(res, key=lambda n: (res[n][0]/res[n][1]
                                             if res[n][1] else -9))
        obs_best = (res[obs_best_n][0]/res[obs_best_n][1]
                    if res[obs_best_n][1] else float("nan"))
        counts = {n: len({t["entry_date"][:10] for t in res[n][3]})
                  for n in NS}
        nullmax = []
        for _ in range(B):
            m = -9e9
            for n in NS:
                k = min(counts[n], len(alld))
                if k == 0:
                    continue
                sk = set(random.sample(alld, k))
                keep = [t for dd_ in alld if dd_ not in sk for t in days[dd_]]
                if not keep:
                    continue
                nn, ddv = dd_of(keep)
                if ddv:
                    m = max(m, nn/ddv)
            nullmax.append(m)
        nullmax.sort()
        p = sum(1 for z in nullmax if z >= obs_best)/B
        print(f"  best = streak {obs_best_n}, net/dd {obs_best:+.2f}")
        print(f"  null max mean {sum(nullmax)/B:+.2f}, "
              f"p95 {nullmax[int(.95*B)]:+.2f}")
        print(f"  CORRECTED p = {p:.3f}   "
              f"{'SIGNIFICANT' if p < 0.05 else 'NOT significant'}")

        # ---- per-quarter stability -----------------------------------
        print(f"\n  per-quarter, streak {obs_best_n} vs control (net):")
        print(f"  {'quarter':<10}{'ctrl net':>11}{'rule net':>11}"
              f"{'delta':>11}{'skipped':>9}")
        wins = tot = 0
        for tag in TAGS:
            qt = byten[tenor][tag]
            if len(qt) < 8:
                continue
            cn, _ = dd_of(qt)
            tk, sk = simulate(qt, obs_best_n)
            rn, _ = dd_of(tk)
            wins += rn > cn
            tot += 1
            print(f"  {tag:<10}{cn:>+11,.0f}{rn:>+11,.0f}"
                  f"{rn-cn:>+11,.0f}{len(sk):>9}")
        if tot:
            pb = 2*sum(math.comb(tot, i)
                       for i in range(max(wins, tot-wins), tot+1))/2**tot
            print(f"  rule better in {wins}/{tot} quarters, "
                  f"sign test p={min(pb,1.0):.3f}")


if __name__ == "__main__":
    main()
