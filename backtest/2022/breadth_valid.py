"""Is the winning breadth rule real, or the best of 36 lottery tickets?

36 rule/lag combinations were tested. With that many tries, the top result is
expected to look good even if every rule is worthless. Four checks:

1. MULTIPLE COMPARISONS. How often does the BEST of 36 random rules beat
   always-call by as much as our winner? Uses random side-assignment with the
   same per-day autocorrelation structure, so it is a like-for-like null.

2. LAG STABILITY. A real signal degrades smoothly as it is lagged. A fitted one
   jumps around. Our winner is best at lag 5, which is suspicious -- why would
   week-old breadth beat today's?

3. TIME SPLIT. First half vs second half of 2022. A rule fitted to the October
   bottom will show all its edge in H2.

4. MONTHLY CONSISTENCY. Does it beat always-call in most months, or is it one
   or two months again (the April problem from the bear-call test)?
"""
import pickle
import random
import statistics
from collections import defaultdict

BEST = ("SECTOR", "pct_above50", None, "MARKET", 5)     # the winner
LABEL = "sector %above50 > market, lag 5"


def load():
    pool = pickle.load(open("pool22.pkl", "rb"))
    br = pickle.load(open("breadth22.pkl", "rb"))
    sec = __import__("json").load(open("sectors_2022.json"))
    puts = {(t["symbol"], t["entry_date"]): t for t in pool["bull_put"]}
    calls = {(t["symbol"], t["entry_date"]): t for t in pool["bear_call"]}
    return puts, calls, br, sec


def main():
    puts, calls, br, sec = load()
    both = sorted(set(puts) & set(calls))
    dates = sorted({d for (s, d) in br if s == "MARKET"})
    di = {d: i for i, d in enumerate(dates)}

    def bval(scope, d, key, lag):
        i = di.get(d)
        if i is None or i - lag < 0:
            return None
        v = br.get((scope, dates[i - lag]))
        return v[key] if v else None

    scope, key, thr, relto, lag = BEST
    picks, decisions = [], {}
    for k in both:
        sym, d = k
        sc = sec.get(sym, "UNKNOWN")
        v = bval(sc, d, key, lag)
        m = bval(relto, d, key, lag)
        if v is None or m is None:
            continue
        bull = v > m
        decisions[k] = bull
        picks.append(puts[k] if bull else calls[k])

    net = sum(t["net_pnl"] for t in picks)
    call_net = sum(calls[k]["net_pnl"] for k in decisions)
    put_net = sum(puts[k]["net_pnl"] for k in decisions)
    nbull = sum(1 for v in decisions.values() if v)
    print(f"RULE: {LABEL}")
    print(f"  decided {len(decisions)} trades: {nbull} puts, "
          f"{len(decisions)-nbull} calls")
    print(f"  rule net      {net:>+10,.0f}")
    print(f"  always-call   {call_net:>+10,.0f}")
    print(f"  always-put    {put_net:>+10,.0f}")
    print(f"  edge vs call  {net-call_net:>+10,.0f}")
    print()

    # ---- 1. multiple comparisons ------------------------------------------
    print("=" * 74)
    print("1. MULTIPLE COMPARISONS -- best of 36 random rules")
    print("=" * 74)
    ks = list(decisions)
    rng = random.Random(11)
    # Null preserves the daily clustering: assign a random side PER DAY, not
    # per trade, because breadth is a daily variable and real rules therefore
    # make correlated choices within a day.
    bests = []
    for _ in range(2000):
        best = -1e18
        for _r in range(36):
            daymap = {}
            tot = 0.0
            for k in ks:
                d = k[1]
                if d not in daymap:
                    daymap[d] = rng.random() < (nbull / len(ks))
                tot += (puts[k] if daymap[d] else calls[k])["net_pnl"]
            best = max(best, tot)
        bests.append(best)
    obs = net
    hits = sum(1 for b in bests if b >= obs)
    print(f"  observed best rule            {obs:>+10,.0f}")
    print(f"  null: best-of-36 mean         {statistics.mean(bests):>+10,.0f}")
    print(f"  null: best-of-36 95th pct     {sorted(bests)[1899]:>+10,.0f}")
    print(f"  p(best-of-36 null >= observed) = {(hits+1)/2001:.4f}")
    print(f"  -> {'survives' if (hits+1)/2001 < 0.05 else 'DOES NOT survive'} "
          f"multiple-comparison correction")
    print()

    # ---- 2. lag stability --------------------------------------------------
    print("=" * 74)
    print("2. LAG STABILITY -- a real signal decays smoothly")
    print("=" * 74)
    for L in range(0, 11):
        pk = []
        for k in both:
            v = bval(sec.get(k[0], "UNKNOWN"), k[1], key, L)
            m = bval("MARKET", k[1], key, L)
            if v is None or m is None:
                continue
            pk.append(puts[k] if v > m else calls[k])
        n = sum(t["net_pnl"] for t in pk)
        bar = "#" * max(0, int((n + 60000) / 4000))
        print(f"  lag {L:>2}  n={len(pk):>4}  {n:>+10,.0f}  {bar}")
    print()

    # ---- 3. time split ----------------------------------------------------
    print("=" * 74)
    print("3. TIME SPLIT -- H1 vs H2 2022")
    print("=" * 74)
    for lab, lo, hi in (("H1 (Jan-Jun)", "2022-01", "2022-07"),
                        ("H2 (Jul-Dec)", "2022-07", "2023-01")):
        sub = [k for k in decisions if lo <= k[1][:7] < hi]
        if not sub:
            continue
        rn = sum((puts[k] if decisions[k] else calls[k])["net_pnl"] for k in sub)
        cn = sum(calls[k]["net_pnl"] for k in sub)
        pn = sum(puts[k]["net_pnl"] for k in sub)
        print(f"  {lab}  n={len(sub):>4}  rule {rn:>+9,.0f}  "
              f"call {cn:>+9,.0f}  put {pn:>+9,.0f}  edge {rn-cn:>+9,.0f}")
    print()

    # ---- 4. monthly consistency -------------------------------------------
    print("=" * 74)
    print("4. MONTHLY CONSISTENCY -- or is it one month again?")
    print("=" * 74)
    mon = defaultdict(lambda: [0.0, 0.0, 0])
    for k, bull in decisions.items():
        m = k[1][:7]
        mon[m][0] += (puts[k] if bull else calls[k])["net_pnl"]
        mon[m][1] += calls[k]["net_pnl"]
        mon[m][2] += 1
    winm = 0
    print(f"  {'month':<9}{'n':>5}{'rule':>10}{'always-call':>13}{'edge':>10}")
    print("  " + "-" * 49)
    for m in sorted(mon):
        r, c, n = mon[m]
        if r > c:
            winm += 1
        print(f"  {m:<9}{n:>5}{r:>+10,.0f}{c:>+13,.0f}{r-c:>+10,.0f}")
    print("  " + "-" * 49)
    print(f"  rule beat always-call in {winm} of {len(mon)} months")
    tot = sum(v[0] - v[1] for v in mon.values())
    bestm = max(mon.items(), key=lambda x: x[1][0] - x[1][1])
    print(f"  total edge {tot:>+,.0f}; biggest month {bestm[0]} "
          f"{bestm[1][0]-bestm[1][1]:>+,.0f} "
          f"= {100*(bestm[1][0]-bestm[1][1])/tot if tot else 0:.0f}% of edge")


if __name__ == "__main__":
    main()
