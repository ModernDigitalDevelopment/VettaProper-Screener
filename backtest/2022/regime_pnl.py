"""Does the macro regime label improve SPREAD SELLING? (not SPY forecasting)

The forward-SPY test came back wrong-signed: days labelled BEAR preceded
BETTER 10-day SPY returns than days labelled BULL. That is the signature of a
lagging trend filter -- by the time breadth has broken and NH-NL has gone
negative, the sell-off is well advanced and the next move is often a bounce.

But "wrong sign for forecasting SPY direction" does NOT automatically mean
useless for credit spreads, because:
  - a put seller loses on a FALL, and cares about the LEFT TAIL, not the mean
  - a bear-call seller wants the absence of a rally, not a decline
So the correct test is not the mean forward return, it is the distribution:
how often does a large adverse move follow each label?

Tested here for each regime label:
  put_blowup   P(SPY falls > 3% in the next 10 days)   -- kills a bull put
  call_blowup  P(SPY rises > 3% in the next 10 days)   -- kills a bear call
  realised vol of the forward window

If the labels separate the TAILS even with the means inverted, the macro
overlay is still usable -- just as a risk filter rather than a direction call.
"""
import pickle
import statistics
from collections import defaultdict

HZ = 10
THRESH = 3.0


def main():
    m = pickle.load(open("macro.pkl", "rb"))
    labs = pickle.load(open("regime_labels.pkl", "rb"))
    ds = sorted(m)
    idx = {d: i for i, d in enumerate(ds)}

    for variant in ("no200", "with200"):
        lab = labs[variant]
        print()
        print("=" * 90)
        print(f"TAIL ANALYSIS -- {variant}  (horizon {HZ} days, threshold {THRESH}%)")
        print("=" * 90)
        buckets = defaultdict(list)
        for d, k in lab.items():
            i = idx.get(d)
            if i is None or i + HZ >= len(ds):
                continue
            a = m[d]["spy"]
            if not a:
                continue
            path = [m[ds[j]]["spy"] for j in range(i, i + HZ + 1)]
            path = [p for p in path if p]
            if len(path) < HZ:
                continue
            fwd = 100 * (path[-1] / a - 1)
            mn = 100 * (min(path) / a - 1)      # worst drawdown in window
            mx = 100 * (max(path) / a - 1)      # best rally in window
            buckets[k].append((fwd, mn, mx))

        print(f"  {'label':<7}{'n':>5}{'mean fwd':>10}{'P(dip>3%)':>11}"
              f"{'P(rally>3%)':>13}{'med worst':>11}{'med best':>10}")
        print("  " + "-" * 78)
        res = {}
        for k in ("BULL", "FLAT", "BEAR"):
            g = buckets.get(k, [])
            if len(g) < 20:
                continue
            n = len(g)
            dip = sum(1 for f, lo, hi in g if lo <= -THRESH) / n
            rally = sum(1 for f, lo, hi in g if hi >= THRESH) / n
            res[k] = (dip, rally)
            print(f"  {k:<7}{n:>5}{sum(f for f,_,_ in g)/n:>+9.2f}%"
                  f"{100*dip:>10.0f}%{100*rally:>12.0f}%"
                  f"{statistics.median([lo for _,lo,_ in g]):>+10.1f}%"
                  f"{statistics.median([hi for _,_,hi in g]):>+9.1f}%")

        if "BULL" in res and "BEAR" in res:
            bd, br = res["BULL"]
            rd, rr = res["BEAR"]
            print()
            print(f"  Put-seller risk  P(dip>3%):   BULL {100*bd:.0f}%  "
                  f"vs BEAR {100*rd:.0f}%   -> {'USEFUL' if rd > bd else 'no help'}")
            print(f"  Call-seller risk P(rally>3%): BULL {100*br:.0f}%  "
                  f"vs BEAR {100*rr:.0f}%   -> "
                  f"{'USEFUL' if br > rr else 'no help'}")
            print()
            print("  Interpretation: a macro overlay is worth having if BEAR days")
            print("  carry more dip risk (so stop selling puts) AND BULL days carry")
            print("  more rally risk (so stop selling calls). Both must hold.")


if __name__ == "__main__":
    main()
