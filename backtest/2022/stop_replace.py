"""Why does a thinner per-trade tail NOT produce a thinner portfolio drawdown?

Hypothesis: the stop frees capital mid-drawdown and the engine immediately
redeploys it. Those REPLACEMENT trades are opened into the same falling market
that triggered the stop, so they inherit the same adverse move. The tail saved
on the stopped position is handed straight back by its replacement.

Test: split the stop arm's trades into
  MATCHED   - positions the control also took (the stop's true effect)
  EXTRA     - positions only the stop arm could afford (the redeployment)
and compare their economics. If EXTRA is materially worse than MATCHED, the
redeployment is the leak, and the fix is to NOT redeploy freed capital rather
than to abandon the stop.
"""
import pickle
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
STOPS = ["0.5", "1.0", "1.5", "2.0"]


def key(t):
    return (t["symbol"], t["entry_date"][:10], round(t.get("short_strike", 0), 2))


def summ(ts):
    if not ts:
        return "        --"
    n = len(ts)
    ror = 100 * sum(t["net_pnl"] / t["max_loss"] for t in ts if t["max_loss"]) / n
    net = sum(t["net_pnl"] for t in ts)
    win = 100 * sum(1 for t in ts if t["net_pnl"] > 0) / n
    return f"n={n:>4} win={win:>5.1f}% ror={ror:>+7.2f}% net={net:>+9,.0f}"


def main():
    data = {t: pickle.load(open(f"r_stop_{t}.pkl", "rb")) for t in TAGS}
    tenors = sorted({k.split("|")[0] for d in data.values() for k in d})
    for tenor in tenors:
        print("\n" + "=" * 100)
        print(f"{tenor}   MATCHED (stop's real effect) vs EXTRA (redeployed capital)")
        print("=" * 100)
        ck = set()
        for tag in TAGS:
            rec = data[tag].get(f"{tenor}|none")
            if rec:
                ck |= {key(t) for t in rec[0]}
        for s in STOPS:
            arm = []
            for tag in TAGS:
                rec = data[tag].get(f"{tenor}|{s}")
                if rec:
                    arm += rec[0]
            m = [t for t in arm if key(t) in ck]
            x = [t for t in arm if key(t) not in ck]
            print(f"  {s}x  MATCHED  {summ(m)}")
            print(f"       EXTRA    {summ(x)}")
            # how many of the EXTRA trades were themselves stopped out?
            sx = sum(1 for t in x if str(t.get("exit_reason","")).startswith("STOP"))
            print(f"       -> of the {len(x)} redeployed, {sx} were themselves stopped"
                  f" ({100*sx/len(x):.0f}%)" if x else "")


if __name__ == "__main__":
    main()
