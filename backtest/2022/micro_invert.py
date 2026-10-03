"""Is the INVERSE of the micro signal a tradeable entry trigger?

The user's argument, and it is a fair one: if a signal reliably does the
opposite of what was expected, the opposite is itself information. Use it to
TURN ON bull puts rather than to turn them off.

There is real support for this in our own data. micro_overlap.py found the
long-tenor trades the gate would have BLOCKED earned +8.01 / +13.70 / +18.66%
RoR against +0.63 / +0.71 / +1.01% for the trades it kept. The signal was
picking our best days and we were proposing to skip them.

And there is a plausible mechanism, which is NOT the one the original research
proposed. A bull put is short vol and long market. The signal fires on
high-VVIX days, so it fires when premium is rich. If the subsequent move is
benign, that is the ideal setup -- fat credit, then decay. Direction need not
be predicted at all; the edge would come from the credit, not the drift.

BUT inverting a failed hypothesis is only legitimate under one condition:

  the signal must carry INFORMATION (large |t|, CONSISTENT sign across
  configurations) and merely have the sign pointed the wrong way.

If instead |t| is small and the sign flips between neighbouring configs, then
there is nothing to invert -- inverting noise yields noise, and picking the
one cell with a surprising sign is conditioning on the outcome, the same
circularity trap that has already bitten this project twice.

So this script tests the inversion three ways:

  TEST A  sign stability across ALL configs (the decisive one)
  TEST B  signal days as an ENTRY trigger vs random day SELECTION
  TEST C  within-quarter, to kill the H1-2022 composition confound
"""
import csv, datetime as dt, pickle, random, math
from collections import defaultdict
import micro_sig as M

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
ALLCFG = [(vl, vp, w) for vl in (21, 63) for vp in (0.80, 0.90)
          for w in (5, 10, 20)]
B = 5000
random.seed(29)


def ror(ts):
    return (100*sum(t["net_pnl"]/t["max_loss"] for t in ts if t["max_loss"])
            / len(ts)) if ts else float("nan")


def armed_window(fire, hold):
    """Days ON which we would now OPEN positions: the fire day's following
    `hold` sessions. Same convention as the blocking test, just inverted."""
    ds = sorted(fire)
    out = set()
    for i, d in enumerate(ds):
        if fire[d]:
            for k in range(1, hold + 1):
                if i + k < len(ds):
                    out.add(ds[i + k])
    return out


def main():
    byten = defaultdict(lambda: defaultdict(list))
    for tag in TAGS:
        dd = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        for k, rec in dd.items():
            if k.endswith("|none"):
                byten[k.split("|")[0]][tag] += rec[0]

    # ---------------- TEST A : sign stability -------------------------
    print("=" * 100)
    print("TEST A -- is the sign CONSISTENT across configs?")
    print("If the inverse is real information, most configs point the same")
    print("way. If signs are mixed, there is nothing to invert.")
    print("=" * 100)
    print(f"{'cfg':<16}{'entry days hit':>15}" +
          "".join(f"{t.split()[0]+' RoR':>14}" for t in sorted(byten)))
    signs = {tn: [] for tn in byten}
    for vl, vp, w in ALLCFG:
        fire, _ = M.build(vl, vp, w)
        arm = armed_window(fire, 5)
        row = f"{f'{vl}/{vp}/{w}':<16}"
        nhit = None
        cells = []
        for tn in sorted(byten):
            tr = [t for tag in TAGS for t in byten[tn][tag]]
            on = [t for t in tr if t["entry_date"][:10] in arm]
            off = [t for t in tr if t["entry_date"][:10] not in arm]
            if nhit is None:
                nhit = len({t["entry_date"][:10] for t in on})
            if len(on) < 3:
                cells.append(f"{'n<3':>14}")
                continue
            d = ror(on) - ror(off)
            signs[tn].append((f"{vl}/{vp}/{w}", d, len(on)))
            cells.append(f"{d:>+14.2f}")
        print(row + f"{nhit:>15}" + "".join(cells))
    print("\n  values are (signal-day RoR) minus (other-day RoR), in pp")
    for tn in sorted(signs):
        ds = signs[tn]
        if not ds:
            continue
        pos = sum(1 for _, d, _ in ds if d > 0)
        n = len(ds)
        p = 2*sum(math.comb(n, i) for i in range(max(pos, n-pos), n+1))/2**n
        print(f"  {tn:<26} positive in {pos}/{n} configs, "
              f"sign test p={min(p,1.0):.3f}  "
              f"{'CONSISTENT' if min(p,1.0) < 0.05 else 'MIXED -> nothing to invert'}")

    # ---------------- TEST B : entry trigger vs random selection ------
    print("\n" + "=" * 100)
    print("TEST B -- trade ONLY on signal days. Beat random day SELECTION?")
    print("Mean RoR of the selected subset vs 5,000 random equal-size")
    print("subsets of entry days. This is the mirror of the blocking test.")
    print("=" * 100)
    for tn in sorted(byten):
        tr = [t for tag in TAGS for t in byten[tn][tag]]
        days = defaultdict(list)
        for t in tr:
            days[t["entry_date"][:10]].append(t)
        alld = sorted(days)
        print(f"\n{tn}   {len(tr)} trades / {len(alld)} entry days, "
              f"all-days RoR {ror(tr):+.2f}%")
        print(f"  {'cfg':<14}{'days':>6}{'trades':>8}{'sel RoR':>10}"
              f"{'null mean':>11}{'null p95':>10}{'pctile':>8}")
        for vl, vp, w in ALLCFG:
            fire, _ = M.build(vl, vp, w)
            arm = armed_window(fire, 5) & set(alld)
            if len(arm) < 3:
                continue
            on = [t for d in arm for t in days[d]]
            obs = ror(on)
            k = len(arm)
            nulls = []
            for _ in range(B):
                pick = random.sample(alld, k)
                nulls.append(ror([t for d in pick for t in days[d]]))
            nulls.sort()
            pc = sum(1 for z in nulls if z <= obs)/B
            print(f"  {f'{vl}/{vp}/{w}':<14}{k:>6}{len(on):>8}{obs:>+10.2f}"
                  f"{sum(nulls)/B:>+11.2f}{nulls[int(.95*B)]:>+10.2f}"
                  f"{pc:>8.2f}")
        print("   pctile >0.95 would mean the signal picks genuinely good days")

    # ---------------- TEST C : within-quarter ------------------------
    print("\n" + "=" * 100)
    print("TEST C -- within-quarter, so H1-2022 composition cannot drive it")
    print("=" * 100)
    for tn in sorted(byten):
        print(f"\n{tn}")
        print(f"  {'cfg':<14}" + "".join(f"{t:>11}" for t in TAGS))
        for vl, vp, w in [(21, 0.80, 5), (21, 0.80, 10), (63, 0.80, 10)]:
            fire, _ = M.build(vl, vp, w)
            arm = armed_window(fire, 5)
            row = f"  {f'{vl}/{vp}/{w}':<14}"
            for tag in TAGS:
                tr = byten[tn][tag]
                on = [t for t in tr if t["entry_date"][:10] in arm]
                off = [t for t in tr if t["entry_date"][:10] not in arm]
                if len(on) < 3 or len(off) < 3:
                    row += f"{f'n={len(on)}':>11}"
                else:
                    row += f"{ror(on)-ror(off):>+11.2f}"
            print(row)
        print("   blank-ish cells = too few signal trades in that quarter")


if __name__ == "__main__":
    main()
