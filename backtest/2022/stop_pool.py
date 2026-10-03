"""Pool the per-quarter stop-loss runs into one table.

Each r_stop_<TAG>.pkl maps "<tenor>|<stop>" -> (trades, metrics, ror, lw).
Pooling is done on the TRADES, not by averaging the per-quarter summary
statistics, because quarters have very different trade counts and averaging
percentages across unequal n is a weighted-average error.
"""
import glob, pickle, re
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
STOPS = ["none", "0.5", "1.0", "1.5", "2.0"]


def agg(trades):
    n = len(trades)
    if not n:
        return None
    w = [t["net_pnl"] for t in trades if t["net_pnl"] > 0]
    l = [t["net_pnl"] for t in trades if t["net_pnl"] <= 0]
    net = sum(t["net_pnl"] for t in trades)
    gp, gl = sum(w), abs(sum(l))
    ror = 100 * sum(t["net_pnl"] / t["max_loss"]
                    for t in trades if t["max_loss"]) / n
    lw = (gl / len(l)) / (gp / len(w)) if w and l else float("nan")
    return dict(n=n, win=100 * len(w) / n, net=net,
                pf=gp / gl if gl else float("inf"), ror=ror, lw=lw)


def main():
    data = {}
    for tag in TAGS:
        try:
            data[tag] = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        except FileNotFoundError:
            pass
    print("loaded:", ", ".join(data))
    tenors = sorted({k.split("|")[0] for d in data.values() for k in d})

    for tenor in tenors:
        print("\n" + "=" * 100)
        print(f"TENOR: {tenor}")
        print("=" * 100)
        # per-quarter net, to show consistency rather than just the pooled sum
        print(f"{'stop':<8}" + "".join(f"{t:>11}" for t in data) +
              f"{'| pooled n':>11}{'win%':>7}{'net':>11}{'pf':>6}"
              f"{'ror%':>8}{'L/W':>6}{'qtrs+':>7}")
        for s in STOPS:
            key = f"{tenor}|{s}"
            cells, allt, wins = [], [], 0
            for tag, d in data.items():
                rec = d.get(key)
                if rec is None:
                    cells.append(f"{'--':>11}"); continue
                tr = rec[0]
                allt += tr
                q = sum(t["net_pnl"] for t in tr)
                wins += q > 0
                cells.append(f"{q:>+11,.0f}")
            a = agg(allt)
            if a is None:
                continue
            print(f"{s:<8}" + "".join(cells) +
                  f"{a['n']:>11}{a['win']:>7.1f}{a['net']:>+11,.0f}"
                  f"{a['pf']:>6.2f}{a['ror']:>+8.2f}{a['lw']:>6.2f}"
                  f"{wins:>4}/{len(data)}")


if __name__ == "__main__":
    main()
