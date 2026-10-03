"""Does the A/D divergence leg add anything over the VVIX percentile alone?

The signal is a conjunction: (VVIX percentile >= p) AND (unconfirmed new high).
His grid varies both legs but never tests the VVIX leg on its own, so there is
no way to tell from micro_results.csv whether the breadth half contributes.

This matters more than any parameter choice, because the A/D data is the part
he flagged as least trustworthy ("the biggest open question is the A/D data
after 2020"). If VVIX alone does the work, the fragile data dependency can be
dropped entirely.

Testable over the FULL 2006-2026 VVIX+SPY history for the VVIX-only leg (no
breadth needed), and over 2022-2024 for the conjunction.

Forward excess return = mean forward SPY return after the signal, minus the
unconditional mean over the same window. t-stat on the signal subset.
"""
import csv, datetime as dt, math, pickle
import micro_sig as M


def load():
    vv = M.load_vvix()
    spx = M.load_spx()
    d = sorted(set(vv) & set(spx))
    return vv, spx, d


def fwd(spx, dates, h):
    f = {}
    for i, d in enumerate(dates):
        if i + h < len(dates):
            f[d] = spx[dates[i + h]] / spx[d] - 1
    return f


def tstat(xs, base):
    n = len(xs)
    if n < 3:
        return float("nan")
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return (m - base) / (sd / math.sqrt(n)) if sd else float("nan")


def report(name, dates, firedays, fwds, bases):
    ev = sorted(firedays)
    row = f"{name:<30}{len(ev):>7}"
    for h in (5, 10, 20):
        xs = [fwds[h][d] for d in ev if d in fwds[h]]
        if len(xs) < 3:
            row += f"{'--':>10}{'--':>8}"
            continue
        m = sum(xs) / len(xs)
        row += f"{100*(m-bases[h]):>+10.2f}{tstat(xs, bases[h]):>8.2f}"
    print(row)


def main():
    vv, spx, dates = load()
    print(f"VVIX+SPY common window: {dates[0]} .. {dates[-1]} "
          f"({len(dates)} days)\n")
    fwds = {h: fwd(spx, dates, h) for h in (5, 10, 20)}
    bases = {h: sum(fwds[h].values()) / len(fwds[h]) for h in (5, 10, 20)}
    print("unconditional forward SPY: " +
          "  ".join(f"{h}d {100*bases[h]:+.2f}%" for h in (5, 10, 20)))
    print("\nexcess = mean fwd after signal minus unconditional\n")
    hdr = (f"{'signal':<30}{'n':>7}" +
           "".join(f"{f'exc{h}d':>10}{'t':>8}" for h in (5, 10, 20)))

    # ---- VVIX leg alone, FULL history -----------------------------------
    print("=" * 84)
    print("A. VVIX PERCENTILE ALONE -- full 2006-2026 history, no breadth")
    print("=" * 84)
    print(hdr)
    vd = sorted(vv)
    vidx = {d: i for i, d in enumerate(vd)}
    for vlook in (21, 63):
        for vpct in (0.80, 0.90):
            fireset = set()
            prev = False
            for d in dates:
                j = vidx[d]
                if j < vlook // 2:
                    continue
                win = [vv[x] for x in vd[max(0, j - vlook + 1):j + 1]]
                p = sum(1 for x in win if vv[d] >= x) / len(win)
                f = p >= vpct
                if f and not prev:          # onsets only, as micro.py does
                    fireset.add(d)
                prev = f
            report(f"VVIX {vlook}d p{int(vpct*100)} only", dates,
                   fireset, fwds, bases)

    # ---- conjunction, 2022-2024 only (breadth-limited) -------------------
    print("\n" + "=" * 84)
    print("B. VVIX + A/D DIVERGENCE -- 2022-2024 only (our breadth window)")
    print("=" * 84)
    print(hdr)
    for vlook in (21, 63):
        for vpct in (0.80, 0.90):
            for w in (5, 10):
                fire, _ = M.build(vlook, vpct, w)
                ds = sorted(fire)
                ons = {d for i, d in enumerate(ds)
                       if fire[d] and not (i and fire[ds[i-1]])}
                report(f"VVIX {vlook}d p{int(vpct*100)} + div{w}", dates,
                       ons, fwds, bases)

    # ---- VVIX leg restricted to the SAME 2022-2024 window ---------------
    print("\n" + "=" * 84)
    print("C. VVIX ALONE, restricted to 2022-2024 -- the apples-to-apples")
    print("   comparison for panel B (same window, breadth leg removed)")
    print("=" * 84)
    print(hdr)
    sub = [d for d in dates if "2022" <= d[:4] <= "2024"]
    for vlook in (21, 63):
        for vpct in (0.80, 0.90):
            fireset, prev = set(), False
            for d in sub:
                j = vidx[d]
                win = [vv[x] for x in vd[max(0, j - vlook + 1):j + 1]]
                p = sum(1 for x in win if vv[d] >= x) / len(win)
                f = p >= vpct
                if f and not prev:
                    fireset.add(d)
                prev = f
            report(f"VVIX {vlook}d p{int(vpct*100)} only (22-24)", dates,
                   fireset, fwds, bases)


if __name__ == "__main__":
    main()
