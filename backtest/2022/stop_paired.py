"""Paired test: same trade, with and without the stop.

The previous script's p(>none) column was WRONG -- it compared two independent
sorted bootstrap distributions element-wise, which is a quantile comparison,
not a hypothesis test. Discarded.

The correct test exploits that a stop only changes the EXIT of a position that
would have been opened anyway. So match trades between the control arm and the
stop arm on (symbol, entry_date, short_strike) and look at the PAIRED
difference in return-on-risk. Unmatched trades -- the extra positions a stop
enables by freeing capital early -- are reported separately, since those are a
capacity effect, not a stop effect, and mixing them in confounds the two.

Bootstrap is blocked by entry day: same-day positions share one market shock.
"""
import pickle, random
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
STOPS = ["0.5", "1.0", "1.5", "2.0"]
B = 10000
random.seed(11)


def key(t):
    return (t["symbol"], t["entry_date"][:10], round(t.get("short_strike", 0), 2))


def load(tenor, stop, data):
    out = {}
    for tag in TAGS:
        rec = data[tag].get(f"{tenor}|{stop}")
        if not rec:
            continue
        for t in rec[0]:
            if t.get("max_loss"):
                out[key(t)] = t["net_pnl"] / t["max_loss"]
    return out


def main():
    data = {t: pickle.load(open(f"r_stop_{t}.pkl", "rb")) for t in TAGS}
    tenors = sorted({k.split("|")[0] for d in data.values() for k in d})

    for tenor in tenors:
        print("\n" + "=" * 96)
        print(f"PAIRED  {tenor}   day-blocked bootstrap of the difference, B={B}")
        print("=" * 96)
        ctrl = load(tenor, "none", data)
        print(f"{'stop':<6}{'matched':>9}{'ctrl RoR':>10}{'stop RoR':>10}"
              f"{'diff pp':>9}{'95% CI':>20}{'p':>8}{'unmatched':>11}")
        results = {}
        for s in STOPS:
            arm = load(tenor, s, data)
            common = set(ctrl) & set(arm)
            if not common:
                continue
            byday = defaultdict(list)
            for k in common:
                byday[k[1]].append(arm[k] - ctrl[k])
            blks = list(byday.values())
            flat = [v for b in blks for v in b]
            obs = sum(flat) / len(flat)
            draws = []
            for _ in range(B):
                pick = [blks[random.randrange(len(blks))] for _ in range(len(blks))]
                f = [v for b in pick for v in b]
                draws.append(sum(f) / len(f))
            draws.sort()
            lo, hi = draws[int(.025*B)], draws[int(.975*B)]
            # two-sided p: fraction of draws on the far side of zero, doubled
            p = 2 * min(sum(1 for d in draws if d <= 0),
                        sum(1 for d in draws if d >= 0)) / B
            cm = sum(ctrl[k] for k in common)/len(common)
            am = sum(arm[k] for k in common)/len(common)
            results[s] = (obs, p)
            print(f"{s:<6}{len(common):>9}{100*cm:>+10.2f}{100*am:>+10.2f}"
                  f"{100*obs:>+9.2f}{f'[{100*lo:+.2f},{100*hi:+.2f}]':>20}"
                  f"{min(p,1.0):>8.3f}{len(arm)-len(common):>11}")

        # Bonferroni over the 4 stop levels tried
        print(f"\nBonferroni threshold for 4 arms: p < {0.05/4:.4f}")
        for s, (o, p) in results.items():
            verdict = "SIGNIFICANT" if p < 0.05/4 else "not significant"
            print(f"  {s}x: diff {100*o:+.2f}pp, p={min(p,1.0):.3f}  -> {verdict}")


if __name__ == "__main__":
    main()
