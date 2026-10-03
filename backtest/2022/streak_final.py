"""Last check on the pause-after-N-losses rule, short tenor.

After fixing the tie-break bug, the picture changed completely:
  LONG tenor: the apparent +0.70 net/dd became -0.89. The original result was
              an artifact of sorting (exit_date, pnl) tuples, which put
              same-day losses first and made "last N all losses" fire too
              often. DEAD.
  SHORT tenor: streak-3 improves net in 5 of 6 quarters (+$5,590 in Q2 2022,
              +$12,775 in Q3 2022) and lifts net/dd from -0.49 to -0.26.
              Corrected p=0.881 on net/dd, but net/dd is the WRONG criterion
              for a rule that skips 91% of trades -- it rewards doing nothing.

The real question for the short tenor: the rule skips 91% of trades. Is that
a signal, or is "trade almost never" trivially better than "trade a losing
strategy"? Those are very different conclusions for the user.

Test: compare against a null that skips the same 91% AT RANDOM, scored on the
metric that matters for a mostly-off rule -- mean RoR of the trades TAKEN. If
the rule's taken-trades beat random taken-trades, the timing is informative.
If not, the gain is just reduced exposure to a negative-expectancy book, which
you achieve more honestly by not trading it.
"""
import pickle, random, math
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
B = 5000
random.seed(61)


def ror(ts):
    return (100*sum(t["net_pnl"]/t["max_loss"] for t in ts)/len(ts)
            if ts else float("nan"))


def simulate(trades, n):
    ordered = sorted(trades, key=lambda t: (t["entry_date"][:10], t["symbol"]))
    closed, taken, skipped = [], [], []
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

    tenor = "short 7-11 DTE, exit 2"
    trades = [t for tag in TAGS for t in byten[tenor][tag]]
    print(f"{tenor}: {len(trades)} trades, all-trade RoR {ror(trades):+.2f}%")
    print()
    print("Does the rule's TAKEN set beat a random set of the same size?")
    print("=" * 88)
    print(f"{'rule':<12}{'taken':>7}{'taken RoR':>11}{'null mean':>11}"
          f"{'null p95':>10}{'pctile':>8}  verdict")
    for n in (2, 3, 4):
        tk, sk = simulate(trades, n)
        k = len(tk)
        obs = ror(tk)
        nulls = sorted(ror(random.sample(trades, k)) for _ in range(B))
        pc = sum(1 for z in nulls if z <= obs)/B
        print(f"{f'streak {n}':<12}{k:>7}{obs:>+11.2f}"
              f"{sum(nulls)/B:>+11.2f}{nulls[int(.95*B)]:>+10.2f}{pc:>8.2f}"
              f"  {'informative' if pc > 0.95 else 'NOT informative'}")

    # Decomposition: how much of the net improvement is just fewer trades?
    print()
    print("=" * 88)
    print("Decomposition: is the gain TIMING, or just less exposure?")
    print("=" * 88)
    print(f"{'rule':<12}{'taken':>7}{'net':>11}{'expected net':>14}"
          f"{'timing alpha':>14}")
    print("  expected net = (all-trade mean $ per trade) x (trades taken)")
    mean_d = sum(t["net_pnl"] for t in trades)/len(trades)
    for n in (2, 3, 4):
        tk, _ = simulate(trades, n)
        net = sum(t["net_pnl"] for t in tk)
        exp = mean_d*len(tk)
        print(f"{f'streak {n}':<12}{len(tk):>7}{net:>+11,.0f}"
              f"{exp:>+14,.0f}{net-exp:>+14,.0f}")
    print()
    print("If 'timing alpha' is small relative to net, the rule is not")
    print("picking better trades -- it is simply taking fewer of them.")


if __name__ == "__main__":
    main()
