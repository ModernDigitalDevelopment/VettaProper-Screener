"""Settle the exit-discipline question properly. My earlier claim was wrong.

WHAT I PREVIOUSLY TOLD THE USER (and wrote into GRIND_QUARTERS / the stop-loss
docs): "Expiry carries -29% to -40% RoR vs +10% for an EOD exit, so exit
discipline is the single largest edge in the data."

THAT IS BACKWARDS on this population. Measured on the clean six-quarter
no-stop arms:
    long  : EXPIRED +23.58% vs TIME-EXITED -22.14%
    short : EXPIRED +11.82% vs TIME-EXITED -24.39%

But NEITHER number is usable, because the comparison is circular in BOTH
directions. The diagnosis:

  mean debit-to-close at exit, long tenor
      EOD_EXIT_DTE15 : 2.076   (vs credit 1.274 -> ratio 1.63, deep losers)
      EXPIRED        : 0.488   (vs credit 1.273 -> ratio 0.38, winners)

A position only reaches EXPIRED when a leg has no quote. A short put with no
bid is a put nobody will pay for -- i.e. one that has gone deep OTM and is
already worthless. So "EXPIRED" is a proxy for "finished OTM", which is the
outcome. Conditioning on it selects winners by construction.

Equally, "EOD_EXIT" fires on positions still carrying real value at the DTE
cutoff, which skews to losers.

So exit_reason CANNOT be used to measure exit policy. The only legitimate test
is a COUNTERFACTUAL on the same positions: hold the entry set fixed and vary
the exit RULE in the engine, which is exactly what the stop-loss runs did.
Those are the numbers to trust.

This script does the one honest comparison available without a new engine run:
compare the SPEC'd exit rules against each other across the arms we have,
matched on identical entries.
"""
import pickle, random
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
B = 10000
random.seed(71)


def key(t):
    return (t["symbol"], t["entry_date"][:10], round(t.get("credit", 0), 4))


def main():
    print("=" * 94)
    print("EXIT POLICY, measured the only legitimate way:")
    print("same entries, different SPEC'd exit rule.")
    print("=" * 94)

    # longdte pickles used exit_at_dte 10/12/15 on identical specs
    import glob
    files = sorted(glob.glob("r_longdte*.pkl"))
    print(f"\nlong-DTE runs available: {files}")
    pop = defaultdict(lambda: defaultdict(list))
    for f in files:
        try:
            d = pickle.load(open(f, "rb"))
        except Exception:
            continue
        for lab, rec in d.items():
            ts = None
            if isinstance(rec, tuple):
                for p in rec:
                    if isinstance(p, list):
                        ts = p
                        break
            elif isinstance(rec, list):
                ts = rec
            if not ts:
                continue
            for t in ts:
                if isinstance(t, dict) and t.get("structure") == "bull_put":
                    pop[lab][key(t)] = t

    labs = sorted(pop, key=lambda l: -len(pop[l]))
    print(f"\n{'label':<46}{'n':>6}{'RoR':>9}{'net':>11}")
    for l in labs:
        ts = list(pop[l].values())
        r = 100*sum(t["net_pnl"]/t["max_loss"] for t in ts)/len(ts)
        print(f"{l[:45]:<46}{len(ts):>6}{r:>+9.2f}"
              f"{sum(t['net_pnl'] for t in ts):>+11,.0f}")

    # paired comparison between exit-DTE variants on matched entries
    cand = [l for l in labs if "exit" in l.lower() or "dte" in l.lower()]
    print(f"\nPaired exit-rule comparisons (matched entries only):")
    done = set()
    for a in cand:
        for b in cand:
            if a >= b or (a, b) in done:
                continue
            done.add((a, b))
            common = set(pop[a]) & set(pop[b])
            if len(common) < 25:
                continue
            da = defaultdict(list)
            for k in common:
                d_ = (pop[a][k]["net_pnl"]/pop[a][k]["max_loss"]
                      - pop[b][k]["net_pnl"]/pop[b][k]["max_loss"])
                da[k[1]].append(d_)
            blks = list(da.values())
            flat = [v for x in blks for v in x]
            obs = 100*sum(flat)/len(flat)
            draws = []
            for _ in range(B):
                pk = [blks[random.randrange(len(blks))]
                      for _ in range(len(blks))]
                fl = [v for x in pk for v in x]
                draws.append(100*sum(fl)/len(fl))
            draws.sort()
            p = 2*min(sum(1 for z in draws if z <= 0),
                      sum(1 for z in draws if z >= 0))/B
            print(f"  {a[:30]:<32} vs {b[:30]:<32}")
            print(f"    matched={len(common):>4}  diff={obs:>+7.2f}pp  "
                  f"95% CI [{draws[int(.025*B)]:+.2f},{draws[int(.975*B)]:+.2f}]"
                  f"  p={min(p,1.0):.3f}")


if __name__ == "__main__":
    main()
