"""Does the stop do the one job a stop is supposed to do -- cut the left tail?

The paired test showed no significant change in MEAN return-on-risk. That is
not the same as "a stop is useless": a stop trades a worse average (you pay to
exit losers that would have recovered) for a thinner left tail. So measure the
tail directly, on MATCHED trades only, so the capacity effect of freed slots
cannot contaminate the comparison.

  worst    - minimum single-trade RoR
  p05/p01  - 5th / 1st percentile of the RoR distribution
  CVaR5    - mean of the worst 5% (actual tail mass, not just a quantile)
  >1x      - share of trades losing more than the credit collected

A Q2-2022-only panel is included because Q2 is where the headline improvement
appeared, and the question is whether that was the stop working or that
quarter's particular path.
"""
import pickle
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
STOPS = ["none", "0.5", "1.0", "1.5", "2.0"]


def key(t):
    return (t["symbol"], t["entry_date"][:10], round(t.get("short_strike", 0), 2))


def load(tenor, stop, data, tags):
    out = {}
    for tag in tags:
        rec = data[tag].get(f"{tenor}|{stop}")
        if not rec:
            continue
        for t in rec[0]:
            if t.get("max_loss"):
                out[key(t)] = t["net_pnl"] / t["max_loss"]
    return out


def pct(xs, q):
    s = sorted(xs)
    return s[max(0, min(len(s) - 1, int(q * len(s))))]


def panel(title, tenor, data, tags):
    print("\n" + "=" * 94)
    print(f"{title}   {tenor}")
    print("=" * 94)
    ctrl = load(tenor, "none", data, tags)
    print(f"{'stop':<6}{'n(matched)':>11}{'mean':>8}{'worst':>9}{'p01':>8}"
          f"{'p05':>8}{'CVaR5':>9}{'>1x loss':>10}")
    for s in STOPS:
        arm = load(tenor, s, data, tags)
        common = sorted(set(ctrl) & set(arm)) if s != "none" else sorted(ctrl)
        v = [arm[k] if s != "none" else ctrl[k] for k in common]
        if not v:
            continue
        sv = sorted(v)
        tail = sv[:max(1, len(sv) // 20)]
        print(f"{s:<6}{len(v):>11}{100*sum(v)/len(v):>+8.2f}{100*min(v):>+9.1f}"
              f"{100*pct(v,.01):>+8.1f}{100*pct(v,.05):>+8.1f}"
              f"{100*sum(tail)/len(tail):>+9.1f}"
              f"{100*sum(1 for x in v if x < -0.5)/len(v):>9.1f}%")


def main():
    data = {t: pickle.load(open(f"r_stop_{t}.pkl", "rb")) for t in TAGS}
    tenors = sorted({k.split("|")[0] for d in data.values() for k in d})
    for tenor in tenors:
        panel("ALL SIX QUARTERS (matched)", tenor, data, TAGS)
    for tenor in tenors:
        panel("Q2 2022 ONLY (matched)", tenor, data, ["2022Q2"])


if __name__ == "__main__":
    main()
