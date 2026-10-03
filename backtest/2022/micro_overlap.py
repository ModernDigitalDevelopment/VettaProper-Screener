"""How much of the bull-put book does the micro signal actually touch?

His recommendation for this book, verbatim: "use the short-window signal to
stop opening new trades for 5 days rather than to short."

Before spending a backtest on that, measure the mechanical reach: how many of
our actual entry days fall inside a 5-day block window, and what did the
trades opened on those days do? If the gate touches almost nothing, the
backtest result is predetermined and the credits are better spent elsewhere.

Uses the no-stop control arms from the stop-loss runs as the trade population,
since those are the most recently validated bull-put runs.
"""
import pickle
from collections import defaultdict
import micro_sig as M

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
CFGS = [(21, 0.80, 5), (21, 0.80, 10), (63, 0.80, 10), (63, 0.90, 5)]
HOLD = 5


def blocked_days(fire, hold):
    """Days on which new entries are suppressed.

    micro.py convention: signal at close of t -> position from t+1 for `hold`
    days. Same convention here: a fire on t blocks entries on t+1 .. t+hold.
    """
    ds = sorted(fire)
    idx = {d: i for i, d in enumerate(ds)}
    out = set()
    for d in ds:
        if fire[d]:
            i = idx[d]
            for k in range(1, hold + 1):
                if i + k < len(ds):
                    out.add(ds[i + k])
    return out


def main():
    trades = []
    for tag in TAGS:
        d = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        for k, rec in d.items():
            if k.endswith("|none"):
                tenor = k.split("|")[0]
                for t in rec[0]:
                    trades.append((tenor, t))
    print(f"bull-put trades in population: {len(trades)}")
    entry_days = sorted({t["entry_date"][:10] for _, t in trades})
    print(f"distinct entry days: {len(entry_days)} "
          f"({entry_days[0]} .. {entry_days[-1]})\n")

    for vlook, vpct, w in CFGS:
        fire, _ = M.build(vlook, vpct, w)
        blk = blocked_days(fire, HOLD)
        hit = [d for d in entry_days if d in blk]
        print("=" * 84)
        print(f"cfg {vlook}/{vpct}/{w}  hold={HOLD}d   "
              f"fire-days={sum(fire.values())}  blocked-days={len(blk)}")
        print(f"  our entry days blocked: {len(hit)} of {len(entry_days)} "
              f"({100*len(hit)/len(entry_days):.1f}%)")
        if hit:
            print(f"  dates: {', '.join(hit[:12])}"
                  f"{' ...' if len(hit) > 12 else ''}")
        for tenor in sorted({tn for tn, _ in trades}):
            sub = [t for tn, t in trades if tn == tenor]
            inb = [t for t in sub if t["entry_date"][:10] in blk]
            out = [t for t in sub if t["entry_date"][:10] not in blk]
            def s(ts):
                if not ts:
                    return "n=0"
                n = len(ts)
                ror = 100*sum(t["net_pnl"]/t["max_loss"]
                              for t in ts if t["max_loss"])/n
                return (f"n={n:>4} ror={ror:>+7.2f}% "
                        f"net={sum(t['net_pnl'] for t in ts):>+9,.0f}")
            print(f"    {tenor:<26} BLOCKED {s(inb)}")
            print(f"    {'':<26} KEPT    {s(out)}")


if __name__ == "__main__":
    main()
