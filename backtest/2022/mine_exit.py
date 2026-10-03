"""Mine the exit dimension across EVERY bull-put trade we have.

The user's question is exit and re-entry timing. Eleven entry/regime gates
have failed. But the meta-analysis and the missed-exit bug both pointed at
EXIT DISCIPLINE as the largest measured effect in the data, and that has never
been mined as carefully as the entry side.

Pools every bull_put trade from every result pickle, deduplicated, so this is
the largest bull-put sample assembled in the programme.

Questions:
 1. What does each exit_reason actually earn? (the raw economics)
 2. Holding period vs outcome -- is there a point of diminishing returns?
 3. Does the profit target matter, and where?
 4. Time-to-profit: when do winners become winners? (informs early exit)
 5. Does delta at entry interact with exit outcome?
"""
import pickle, glob, math
from collections import defaultdict

def load_all():
    """Every bull_put trade from every pickle, deduplicated."""
    seen = {}
    for f in sorted(glob.glob("r_*.pkl")):
        try:
            d = pickle.load(open(f, "rb"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for lab, rec in d.items():
            trades = None
            if isinstance(rec, tuple):
                for part in rec:
                    if isinstance(part, list):
                        trades = part
                        break
            elif isinstance(rec, list):
                trades = rec
            if not trades:
                continue
            for t in trades:
                if not isinstance(t, dict):
                    continue
                if t.get("structure") != "bull_put":
                    continue
                if not t.get("max_loss"):
                    continue
                # identity: same position = same symbol/entry/exit/strikewidth
                k = (t["symbol"], t["entry_date"][:10], t["exit_date"][:10],
                     round(t.get("credit", 0), 4), round(t["max_loss"], 2),
                     t.get("dte_at_entry"))
                seen.setdefault(k, (f, lab, t))
    return seen


def ror(ts):
    return (100*sum(t["net_pnl"]/t["max_loss"] for t in ts)/len(ts)
            if ts else float("nan"))


def hold_days(t):
    import datetime as dt
    a = dt.date.fromisoformat(t["entry_date"][:10])
    b = dt.date.fromisoformat(t["exit_date"][:10])
    return (b - a).days


def main():
    seen = load_all()
    trades = [v[2] for v in seen.values()]
    print(f"unique bull-put trades pooled: {len(trades)}")
    yrs = defaultdict(int)
    for t in trades:
        yrs[t["entry_date"][:7]] += 1
    print(f"months covered: {len(yrs)}  "
          f"({min(yrs)} .. {max(yrs)})")

    # ---- 1. exit reason economics ----------------------------------
    print("\n" + "=" * 92)
    print("1. WHAT EACH EXIT ROUTE EARNS")
    print("=" * 92)
    by = defaultdict(list)
    for t in trades:
        by[str(t.get("exit_reason", "?"))].append(t)
    print(f"{'exit_reason':<16}{'n':>6}{'share':>8}{'win%':>7}"
          f"{'mean RoR':>10}{'median':>9}{'p05':>8}{'net':>12}")
    for r, ts in sorted(by.items(), key=lambda kv: -len(kv[1])):
        rs = sorted(100*t["net_pnl"]/t["max_loss"] for t in ts)
        print(f"{r:<16}{len(ts):>6}{100*len(ts)/len(trades):>7.1f}%"
              f"{100*sum(1 for t in ts if t['net_pnl']>0)/len(ts):>6.1f}%"
              f"{ror(ts):>+10.2f}{rs[len(rs)//2]:>+9.2f}"
              f"{rs[max(0,int(.05*len(rs)))]:>+8.1f}"
              f"{sum(t['net_pnl'] for t in ts):>+12,.0f}")

    # ---- 2. holding period ----------------------------------------
    print("\n" + "=" * 92)
    print("2. HOLDING PERIOD vs OUTCOME (all exits)")
    print("=" * 92)
    buckets = [(0,1),(2,3),(4,6),(7,10),(11,15),(16,25),(26,40),(41,99)]
    print(f"{'days held':<12}{'n':>6}{'win%':>7}{'mean RoR':>10}"
          f"{'median':>9}{'p05':>8}{'RoR/day':>9}")
    for lo, hi in buckets:
        ts = [t for t in trades if lo <= hold_days(t) <= hi]
        if len(ts) < 10:
            continue
        rs = sorted(100*t["net_pnl"]/t["max_loss"] for t in ts)
        mh = sum(hold_days(t) for t in ts)/len(ts)
        print(f"{f'{lo}-{hi}':<12}{len(ts):>6}"
              f"{100*sum(1 for t in ts if t['net_pnl']>0)/len(ts):>6.1f}%"
              f"{ror(ts):>+10.2f}{rs[len(rs)//2]:>+9.2f}"
              f"{rs[max(0,int(.05*len(rs)))]:>+8.1f}"
              f"{ror(ts)/mh if mh else 0:>+9.3f}")

    # ---- 3. DTE at entry ------------------------------------------
    print("\n" + "=" * 92)
    print("3. DTE AT ENTRY vs OUTCOME")
    print("=" * 92)
    print(f"{'dte entry':<12}{'n':>6}{'win%':>7}{'mean RoR':>10}"
          f"{'median':>9}{'p05':>8}{'avg hold':>10}")
    for lo, hi in [(0,5),(6,8),(9,11),(12,20),(21,30),(31,45),(46,99)]:
        ts = [t for t in trades if lo <= (t.get("dte_at_entry") or 0) <= hi]
        if len(ts) < 10:
            continue
        rs = sorted(100*t["net_pnl"]/t["max_loss"] for t in ts)
        print(f"{f'{lo}-{hi}':<12}{len(ts):>6}"
              f"{100*sum(1 for t in ts if t['net_pnl']>0)/len(ts):>6.1f}%"
              f"{ror(ts):>+10.2f}{rs[len(rs)//2]:>+9.2f}"
              f"{rs[max(0,int(.05*len(rs)))]:>+8.1f}"
              f"{sum(hold_days(t) for t in ts)/len(ts):>10.1f}")

    # ---- 4. fraction of DTE held ----------------------------------
    print("\n" + "=" * 92)
    print("4. FRACTION OF LIFE HELD  (hold_days / dte_at_entry)")
    print("The exit-discipline question in scale-free form: is there a")
    print("point past which holding stops paying?")
    print("=" * 92)
    print(f"{'held frac':<14}{'n':>6}{'win%':>7}{'mean RoR':>10}"
          f"{'median':>9}{'p05':>8}{'net':>12}")
    for lo, hi in [(0,.2),(.2,.4),(.4,.6),(.6,.8),(.8,1.0),(1.0,9)]:
        ts = []
        for t in trades:
            d = t.get("dte_at_entry") or 0
            if d <= 0:
                continue
            fr = hold_days(t)/d
            if lo <= fr < hi:
                ts.append(t)
        if len(ts) < 10:
            continue
        rs = sorted(100*t["net_pnl"]/t["max_loss"] for t in ts)
        print(f"{f'{lo:.1f}-{hi:.1f}':<14}{len(ts):>6}"
              f"{100*sum(1 for t in ts if t['net_pnl']>0)/len(ts):>6.1f}%"
              f"{ror(ts):>+10.2f}{rs[len(rs)//2]:>+9.2f}"
              f"{rs[max(0,int(.05*len(rs)))]:>+8.1f}"
              f"{sum(t['net_pnl'] for t in ts):>+12,.0f}")

    # ---- 5. delta at entry ----------------------------------------
    print("\n" + "=" * 92)
    print("5. DELTA AT ENTRY vs OUTCOME")
    print("=" * 92)
    print(f"{'delta':<12}{'n':>6}{'win%':>7}{'mean RoR':>10}"
          f"{'median':>9}{'p05':>8}{'credit/width':>13}")
    for lo, hi in [(0,.20),(.20,.26),(.26,.34),(.34,.42),(.42,.60)]:
        ts = [t for t in trades
              if lo <= abs(t.get("delta_at_entry") or 0) < hi]
        if len(ts) < 10:
            continue
        rs = sorted(100*t["net_pnl"]/t["max_loss"] for t in ts)
        cw = [t["credit"]/t["width"] for t in ts
              if t.get("width") and t.get("credit")]
        print(f"{f'{lo:.2f}-{hi:.2f}':<12}{len(ts):>6}"
              f"{100*sum(1 for t in ts if t['net_pnl']>0)/len(ts):>6.1f}%"
              f"{ror(ts):>+10.2f}{rs[len(rs)//2]:>+9.2f}"
              f"{rs[max(0,int(.05*len(rs)))]:>+8.1f}"
              f"{sum(cw)/len(cw) if cw else 0:>13.3f}")

    pickle.dump(trades, open("pooled_bullputs.pkl", "wb"))
    print(f"\nwrote pooled_bullputs.pkl ({len(trades)} trades)")


if __name__ == "__main__":
    main()
