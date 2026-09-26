"""Is the bear-call edge real, or is it just 'sell calls in a down year'?

Three questions the headline P&L cannot answer:

1. MONTHLY. 2022 had up months (notably July and November). If bear calls only
   work in down months, the edge is direction, not signal -- and it will invert
   the moment the market does. This is the closest thing to out-of-sample
   available without the 2023 DBs.

2. SIGNIFICANCE. Is the put-vs-call difference in return-on-risk larger than
   what reshuffling the labels would produce by chance? Permutation test, which
   makes no normality assumption -- appropriate for a heavily skewed payoff
   (small wins, rare large losses).

3. CAPACITY. The switch took 173 bull puts and 132 bear calls, yet lost money
   while always-bear-call made $26k. Suspicion: with max_open=12 and one per
   sector, the bull puts crowd out the bear calls. If so, the switch is not
   failing as a signal -- it is failing as an allocator.
"""
import pickle
import random
from collections import defaultdict


def month(d):
    return d[:7]


def load():
    sw = pickle.load(open("r_switch_2022.pkl", "rb"))
    return sw


def q1_monthly(sw):
    print("=" * 92)
    print("1. MONTHLY -- does the call edge survive the UP months of 2022?")
    print("=" * 92)
    put = sw["22_put"][0]
    call = sw["22_call"][0]
    mp, mc = defaultdict(float), defaultdict(float)
    np_, nc = defaultdict(int), defaultdict(int)
    for t in put:
        mp[month(t["entry_date"])] += t["net_pnl"]
        np_[month(t["entry_date"])] += 1
    for t in call:
        mc[month(t["entry_date"])] += t["net_pnl"]
        nc[month(t["entry_date"])] += 1
    months = sorted(set(mp) | set(mc))
    print(f"{'month':<10}{'put n':>7}{'put net':>11}{'call n':>8}{'call net':>11}"
          f"{'better':>9}")
    print("-" * 92)
    pw = cw = 0
    for m in months:
        b = "CALL" if mc[m] > mp[m] else "put"
        if mc[m] > mp[m]:
            cw += 1
        else:
            pw += 1
        print(f"{m:<10}{np_[m]:>7}{mp[m]:>+11,.0f}{nc[m]:>8}{mc[m]:>+11,.0f}{b:>9}")
    print("-" * 92)
    print(f"calls better in {cw} of {len(months)} months, puts in {pw}")
    print()
    return months, mp, mc


def q2_permutation(sw, iters=20000):
    print("=" * 92)
    print("2. SIGNIFICANCE -- permutation test on return-on-risk")
    print("=" * 92)
    put = sw["22_put"][0]
    call = sw["22_call"][0]

    def ror(t):
        return t["net_pnl"] / t["max_loss"] if t["max_loss"] else 0.0

    a = [ror(t) for t in call]
    b = [ror(t) for t in put]
    obs = sum(a) / len(a) - sum(b) / len(b)
    pool = a + b
    na = len(a)
    rng = random.Random(42)
    hits = 0
    for _ in range(iters):
        rng.shuffle(pool)
        d = sum(pool[:na]) / na - sum(pool[na:]) / (len(pool) - na)
        if abs(d) >= abs(obs):
            hits += 1
    p = (hits + 1) / (iters + 1)
    print(f"  mean return-on-risk, bear calls : {100*sum(a)/len(a):+.2f}%  (n={len(a)})")
    print(f"  mean return-on-risk, bull puts  : {100*sum(b)/len(b):+.2f}%  (n={len(b)})")
    print(f"  observed difference             : {100*obs:+.2f}pp")
    print(f"  permutation p-value ({iters:,} shuffles) : {p:.4f}")
    print(f"  -> {'SIGNIFICANT at 0.05' if p < 0.05 else 'NOT significant at 0.05'}")
    print()

    # same test restricted to up months, where direction cannot explain it
    return p


def q3_capacity(sw):
    print("=" * 92)
    print("3. CAPACITY -- are bull puts crowding out bear calls in the switch?")
    print("=" * 92)
    call_only = sw["22_call"][0]
    for rule in ("sma50", "rsi", "dmi"):
        tr = sw[f"22_sw_{rule}"][0]
        bc = [t for t in tr if t["structure"] == "bear_call"]
        # which call trades does always-bear-call take that the switch misses?
        taken = {(t["symbol"], t["entry_date"]) for t in bc}
        missed = [t for t in call_only
                  if (t["symbol"], t["entry_date"]) not in taken]
        mp = sum(t["net_pnl"] for t in missed)
        print(f"  switch({rule:<5}) took {len(bc):>3} calls; "
              f"missed {len(missed):>3} of the always-call set "
              f"worth {mp:>+9,.0f}")
    print()
    print("  If the missed set is strongly positive, the switch is not choosing")
    print("  the wrong side -- it is running out of slots.")
    print()


def main():
    sw = load()
    q1_monthly(sw)
    q2_permutation(sw)
    q3_capacity(sw)


if __name__ == "__main__":
    main()
