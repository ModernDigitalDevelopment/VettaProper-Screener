"""Is the pooled stop-loss ranking signal or noise?

Two concerns:

1. BEST-OF-5 SELECTION. Five stop levels were tried per tenor. Picking the
   best and quoting its net is a multiple-comparison error. Corrected here by
   asking how often the BEST of 5 random relabelings beats the observed best.

2. NON-MONOTONICITY. In Q2 2022 the ordering by L/W was clean and monotonic
   (0.5<1.0<1.5<2.0<none). Pooled, the long tenor has 1.0x WORSE than both
   0.5x and 1.5x. There is no mechanism that makes a mid stop worse than both
   a tighter and a looser one, so a non-monotone ordering is direct evidence
   the differences are sampling noise rather than a real dose-response.

Test: day-block bootstrap on return-on-risk. Trades are blocked by entry date
because positions opened the same day share the same market shock; treating
them as independent would understate the standard error.
"""
import pickle, random
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
STOPS = ["none", "0.5", "1.0", "1.5", "2.0"]
B = 4000
random.seed(7)


def blocks(trades):
    """Group RoR values by entry day -> list of lists."""
    d = defaultdict(list)
    for t in trades:
        if t.get("max_loss"):
            d[t["entry_date"][:10]].append(t["net_pnl"] / t["max_loss"])
    return list(d.values())


def boot_mean(blks):
    k = len(blks)
    pick = [blks[random.randrange(k)] for _ in range(k)]
    flat = [v for b in pick for v in b]
    return sum(flat) / len(flat) if flat else 0.0


def main():
    data = {t: pickle.load(open(f"r_stop_{t}.pkl", "rb")) for t in TAGS}
    tenors = sorted({k.split("|")[0] for d in data.values() for k in d})

    for tenor in tenors:
        print("\n" + "=" * 92)
        print(f"TENOR: {tenor}   day-block bootstrap on RoR, B={B}")
        print("=" * 92)
        arms = {}
        for s in STOPS:
            allt = []
            for tag in TAGS:
                rec = data[tag].get(f"{tenor}|{s}")
                if rec:
                    allt += rec[0]
            arms[s] = blocks(allt)

        ctrl = arms["none"]
        obs_c = sum(v for b in ctrl for v in b) / sum(len(b) for b in ctrl)
        print(f"{'stop':<8}{'mean RoR%':>11}{'95% CI':>22}"
              f"{'vs none':>10}{'p(>none)':>10}")
        for s in STOPS:
            blks = arms[s]
            flat = [v for b in blks for v in b]
            obs = sum(flat) / len(flat)
            draws = sorted(boot_mean(blks) for _ in range(B))
            lo, hi = draws[int(.025 * B)], draws[int(.975 * B)]
            # paired-ish: bootstrap the difference by resampling days jointly
            # is not possible (different trade sets), so use independent draws
            d2 = [boot_mean(ctrl) for _ in range(B)]
            p = sum(1 for a, b in zip(draws, sorted(d2)) if a <= b) / B
            tag = "(control)" if s == "none" else f"{100*(obs-obs_c):+.0f}bp"
            print(f"{s:<8}{100*obs:>+11.2f}{f'[{100*lo:+.2f}, {100*hi:+.2f}]':>22}"
                  f"{tag:>10}{'' if s=='none' else f'{p:>10.3f}'}")

        # ---- best-of-5 correction -------------------------------------
        # Null: stop level is irrelevant; any spread among the 5 arms is
        # noise. Approximate by bootstrapping each arm and recording the
        # max-minus-control gap under resampling of the CONTROL alone.
        best = max(STOPS[1:], key=lambda s:
                   sum(v for b in arms[s] for v in b) / sum(len(b) for b in arms[s]))
        bo = sum(v for b in arms[best] for v in b) / sum(len(b) for b in arms[best])
        gap = bo - obs_c
        null_gaps = []
        for _ in range(B):
            draws5 = [boot_mean(ctrl) for _ in range(4)]
            null_gaps.append(max(draws5) - boot_mean(ctrl))
        pcorr = sum(1 for g in null_gaps if g >= gap) / B
        print(f"\nbest arm = {best}x, gap vs control = {100*gap:+.2f}pp RoR")
        print(f"best-of-4 corrected p = {pcorr:.3f}"
              f"   {'NOT significant' if pcorr > 0.05 else 'significant'}")

        # ---- monotonicity ---------------------------------------------
        order = [sum(v for b in arms[s] for v in b) /
                 sum(len(b) for b in arms[s]) for s in STOPS[1:]]
        mono = all(a <= b for a, b in zip(order, order[1:])) or \
               all(a >= b for a, b in zip(order, order[1:]))
        print(f"dose-response monotone across 0.5/1.0/1.5/2.0: {mono}"
              f"   ({', '.join(f'{100*o:+.2f}' for o in order)})")


if __name__ == "__main__":
    main()
