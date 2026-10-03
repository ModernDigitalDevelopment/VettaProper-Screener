"""VVIX LEVEL gate -- free screen, no engine run needed.

"Don't open new bull puts when VVIX > X" is a pure entry-date filter. Every
trade we already have carries its entry_date, so the gate can be simulated by
dropping trades whose entry day breached the threshold. That costs no backtest
at all, across ALL six quarters, instead of one quarter's engine time.

LIMITATION, stated up front: this measures whether the gate picks the right
DAYS. It cannot capture capacity effects -- when the gate blocks an entry, the
real engine may fill a different position later with the freed slot. That is
the MATCHED/EXTRA distinction established in the stop-loss work, where
redeployment turned out to matter. So a pass here justifies an engine run; it
does not substitute for one.

Thresholds are fixed a priori at round numbers spanning the plausible range,
not tuned. 100 is the level the user originally proposed.
"""
import csv, datetime as dt, pickle, random
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
THRESH = [90, 95, 100, 105, 110]
B = 5000
random.seed(17)


def load_vvix():
    out = {}
    for r in csv.DictReader(open("vvix_cboe.csv")):
        try:
            d = dt.datetime.strptime(r["DATE"], "%m/%d/%Y").date()
            v = float(r["VVIX"])
        except Exception:
            continue
        if v > 20:
            out[d.isoformat()] = v
    return out


def main():
    vv = load_vvix()
    byten = defaultdict(list)
    for tag in TAGS:
        d = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        for k, rec in d.items():
            if k.endswith("|none"):
                for t in rec[0]:
                    byten[k.split("|")[0]].append((tag, t))

    # ---------- 1. is VVIX even discriminating, quarter by quarter? -------
    print("=" * 100)
    print("VVIX distribution on OUR ACTUAL ENTRY DAYS, per quarter")
    print("A gate can only matter where VVIX straddles the threshold.")
    print("=" * 100)
    print(f"{'quarter':<10}{'entry days':>11}{'min':>7}{'median':>8}{'max':>7}"
          + "".join(f"{f'>{x}':>7}" for x in THRESH))
    for tag in TAGS:
        days = sorted({t["entry_date"][:10]
                       for ten in byten for (tg, t) in byten[ten] if tg == tag})
        vs = [vv[d] for d in days if d in vv]
        if not vs:
            continue
        vs_s = sorted(vs)
        row = (f"{tag:<10}{len(days):>11}{vs_s[0]:>7.0f}"
               f"{vs_s[len(vs_s)//2]:>8.0f}{vs_s[-1]:>7.0f}")
        for x in THRESH:
            row += f"{100*sum(1 for v in vs if v > x)/len(vs):>6.0f}%"
        print(row)

    # ---------- 2. does the gate pick good days or bad days? --------------
    for tenor, trades in sorted(byten.items()):
        days = defaultdict(list)
        for tg, t in trades:
            days[t["entry_date"][:10]].append(t)
        alld = sorted(d for d in days if d in vv)
        full = sum(t["net_pnl"] for d in alld for t in days[d])
        print("\n" + "=" * 100)
        print(f"{tenor}   {sum(len(days[d]) for d in alld)} trades, "
              f"{len(alld)} entry days, ungated net {full:+,.0f}")
        print("=" * 100)
        print(f"{'gate':<12}{'blk days':>9}{'blk RoR':>9}{'kept RoR':>9}"
              f"{'kept net':>12}{'null mean':>12}{'pctile':>8}")
        for x in THRESH:
            blk = [d for d in alld if vv[d] > x]
            kept = [d for d in alld if vv[d] <= x]
            if not blk or not kept:
                print(f"{f'VVIX>{x}':<12}{len(blk):>9}  (degenerate: "
                      f"blocks {'all' if not kept else 'nothing'})")
                continue

            def ror(ds):
                ts = [t for d in ds for t in days[d]]
                return (100*sum(t["net_pnl"]/t["max_loss"]
                                for t in ts if t["max_loss"])/len(ts)
                        if ts else 0.0)
            obs = sum(t["net_pnl"] for d in kept for t in days[d])
            k = len(blk)
            nulls = []
            for _ in range(B):
                skip = set(random.sample(alld, k))
                nulls.append(sum(t["net_pnl"] for d in alld if d not in skip
                                 for t in days[d]))
            nulls.sort()
            pc = sum(1 for z in nulls if z <= obs)/B
            print(f"{f'VVIX>{x}':<12}{k:>9}{ror(blk):>+9.2f}{ror(kept):>+9.2f}"
                  f"{obs:>+12,.0f}{sum(nulls)/B:>+12,.0f}{pc:>8.2f}")
        print("  pctile >0.95 = gate skipped genuinely bad days (real skill)")
        print("  pctile ~0.50 = no better than skipping random days")


if __name__ == "__main__":
    main()
