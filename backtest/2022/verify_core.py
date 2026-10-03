"""Verify the ONLY two levers that survived scrutiny, cleanly.

Twelve entry/regime/endogenous gates have now failed. Two things did survive,
and both are EXIT mechanics rather than timing:

  A. TIME-BASED EXIT before expiry (the missed-exit bug finding)
  B. CREDIT-MULTIPLE STOP, tail control (the stop-loss finding)

Both were measured in different runs with different samples. This re-verifies
them on ONE consistent population with the same statistics, so the system
outline rests on numbers that were all computed the same way.

A is tested by comparing EXPIRED trades against time-exited trades. That is
outcome-conditioned in the sense that exit_reason is an outcome -- BUT here it
is legitimate, because the engine's exit_at_dte is set by SPEC, not by the
trade's P&L: a trade EXPIRES only when quotes were missing, which is a data
property, not a performance property. The confound to check is whether
missing-quote days are systematically different, so illiquidity is proxied by
credit/width and reported alongside.
"""
import pickle, random, math
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
B = 10000
random.seed(67)


def ror(ts):
    return (100*sum(t["net_pnl"]/t["max_loss"] for t in ts)/len(ts)
            if ts else float("nan"))


def boot_diff(a, b):
    """Day-blocked bootstrap of mean RoR difference a - b."""
    da, db = defaultdict(list), defaultdict(list)
    for t in a:
        da[t["entry_date"][:10]].append(t["net_pnl"]/t["max_loss"])
    for t in b:
        db[t["entry_date"][:10]].append(t["net_pnl"]/t["max_loss"])
    ba, bb = list(da.values()), list(db.values())
    if not ba or not bb:
        return None
    draws = []
    for _ in range(B):
        pa = [ba[random.randrange(len(ba))] for _ in range(len(ba))]
        pb = [bb[random.randrange(len(bb))] for _ in range(len(bb))]
        fa = [v for x in pa for v in x]
        fb = [v for x in pb for v in x]
        draws.append(100*(sum(fa)/len(fa) - sum(fb)/len(fb)))
    draws.sort()
    obs = 100*(sum(t["net_pnl"]/t["max_loss"] for t in a)/len(a)
               - sum(t["net_pnl"]/t["max_loss"] for t in b)/len(b))
    p = 2*min(sum(1 for z in draws if z <= 0),
              sum(1 for z in draws if z >= 0))/B
    return obs, draws[int(.025*B)], draws[int(.975*B)], min(p, 1.0)


def main():
    pop = defaultdict(lambda: defaultdict(list))
    for tag in TAGS:
        d = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        for k, rec in d.items():
            tenor, arm = k.split("|")
            pop[tenor][arm] += rec[0]

    # ---------- A. time exit vs expiry -----------------------------
    print("=" * 96)
    print("A. TIME-BASED EXIT vs LETTING IT EXPIRE")
    print("=" * 96)
    for tenor in sorted(pop):
        tr = pop[tenor]["none"]
        exp = [t for t in tr if t.get("exit_reason") == "EXPIRED"]
        tim = [t for t in tr
               if str(t.get("exit_reason", "")).startswith("EOD_EXIT")]
        print(f"\n{tenor}")
        for nm, ts in (("EXPIRED (quote missing)", exp),
                       ("TIME-EXITED (as specced)", tim)):
            if not ts:
                print(f"  {nm:<28} n=0")
                continue
            rs = sorted(100*t["net_pnl"]/t["max_loss"] for t in ts)
            cw = [t["credit"]/t["width"] for t in ts
                  if t.get("width") and t.get("credit")]
            print(f"  {nm:<28} n={len(ts):>4} "
                  f"win={100*sum(1 for t in ts if t['net_pnl']>0)/len(ts):>5.1f}% "
                  f"RoR={ror(ts):>+7.2f}% p05={rs[max(0,int(.05*len(rs)))]:>+7.1f} "
                  f"credit/width={sum(cw)/len(cw) if cw else 0:.3f}")
        if exp and tim:
            r = boot_diff(tim, exp)
            if r:
                print(f"  --> time-exit advantage {r[0]:+.2f}pp  "
                      f"95% CI [{r[1]:+.2f}, {r[2]:+.2f}]  p={r[3]:.4f}  "
                      f"{'SIGNIFICANT' if r[3] < 0.05 else 'not significant'}")

    # ---------- B. stop tail control -------------------------------
    print("\n" + "=" * 96)
    print("B. CREDIT-MULTIPLE STOP: tail control, matched trades")
    print("=" * 96)
    def key(t):
        return (t["symbol"], t["entry_date"][:10],
                round(t.get("credit", 0), 4))
    for tenor in sorted(pop):
        ctrl = {key(t): t for t in pop[tenor]["none"]}
        print(f"\n{tenor}   control n={len(ctrl)}")
        print(f"  {'arm':<8}{'matched':>9}{'mean RoR':>10}{'p05':>8}"
              f"{'CVaR5':>9}{'>1x credit loss':>17}")
        for arm in ("none", "0.5", "1.0", "1.5", "2.0"):
            src = {key(t): t for t in pop[tenor][arm]}
            common = sorted(set(ctrl) & set(src)) if arm != "none" else sorted(ctrl)
            v = sorted(100*src[k]["net_pnl"]/src[k]["max_loss"]
                       if arm != "none" else
                       100*ctrl[k]["net_pnl"]/ctrl[k]["max_loss"]
                       for k in common)
            if not v:
                continue
            tail = v[:max(1, len(v)//20)]
            print(f"  {arm:<8}{len(v):>9}{sum(v)/len(v):>+10.2f}"
                  f"{v[max(0,int(.05*len(v)))]:>+8.1f}"
                  f"{sum(tail)/len(tail):>+9.1f}"
                  f"{100*sum(1 for x in v if x < -50)/len(v):>16.1f}%")

    # ---------- C. what a realistic combined book looks like -------
    print("\n" + "=" * 96)
    print("C. LONG TENOR, 0.5x STOP -- per-quarter, the deployable config")
    print("=" * 96)
    for tenor in ("long 35-45 DTE, exit 15",):
        for arm in ("none", "0.5"):
            print(f"\n  {tenor}  stop={arm}")
            print(f"  {'quarter':<10}{'n':>5}{'win%':>7}{'net':>11}"
                  f"{'RoR':>9}{'worst':>9}")
            tot = 0
            for tag in TAGS:
                d = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
                ts = d.get(f"{tenor}|{arm}")
                if not ts:
                    continue
                ts = ts[0]
                net = sum(t["net_pnl"] for t in ts)
                tot += net
                w = min(100*t["net_pnl"]/t["max_loss"] for t in ts)
                print(f"  {tag:<10}{len(ts):>5}"
                      f"{100*sum(1 for t in ts if t['net_pnl']>0)/len(ts):>6.1f}%"
                      f"{net:>+11,.0f}{ror(ts):>+9.2f}{w:>+9.1f}")
            print(f"  {'TOTAL':<10}{'':>5}{'':>7}{tot:>+11,.0f}")


if __name__ == "__main__":
    main()
