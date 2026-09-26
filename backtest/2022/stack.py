"""Stack the three findings that survived scrutiny, and ablate them.

The three, each with a mechanism that is NOT a direction bet:
  A  HV > IV            sell when realised vol is running above implied
  B  sizing             below 7.5%
  C  exit at 2 DTE      stop paying gamma into expiry

Why only these: every directional filter tested (ADX, DMI, RSI, stochastics,
sma50, nine A/D breadth measures) inverted sign between up and down months --
it was market direction wearing a costume. These three do not. They attack the
3.47x loss/win ratio, which is what actually killed 2022; the win rate held at
72.6%.

Ablation matters more than the headline. If the stack only works with all three
present, that is three-parameter fitting on a single year.

EFFICIENCY NOTE: position sizing does not change which trades are selected,
only the contract count. So each selection is backtested ONCE at 1 contract-
equivalent and re-sized in post (resize() below), turning 16 backtests into 6.
This is exact, not an approximation: contracts = floor(equity*pct / max_loss),
capped at 20, and per-contract P&L is linear.
"""
import math
import pickle

import spec_engine as E
from run2022 import BASE, DBS_2022, load, metrics

A = dict(require_hv_gt_iv=True)
A6 = dict(min_hv_minus_iv=6.0)
C = dict(exit_at_dte=2)
EQ = 50_000.0


def resize(tr, pct, eq=EQ):
    """Re-express an executed trade list at a different position size.

    Rebuilds contracts from the per-contract risk exactly as the engine does,
    then rescales net_pnl, max_loss and commission proportionally.
    """
    out = []
    for t in tr:
        if not t["contracts"]:
            continue
        ml_ct = t["max_loss"] / t["contracts"]          # per-contract risk
        if ml_ct <= 0:
            continue
        n = min(20, int(math.floor(eq * pct / ml_ct)))
        if n < 1:
            continue
        s = n / t["contracts"]
        u = dict(t)
        u["contracts"] = n
        u["net_pnl"] = t["net_pnl"] * s
        u["gross_pnl"] = t["gross_pnl"] * s
        u["commission"] = t["commission"] * s
        u["max_loss"] = ml_ct * n
        out.append(u)
    return out


def show(label, tr):
    m = metrics(tr)
    print(f"  {label:<40} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} dd={m['dd']:>6.1f}%",
          flush=True)
    return m


def lwr(tr):
    w = [t["net_pnl"] for t in tr if t["net_pnl"] > 0]
    l = [t["net_pnl"] for t in tr if t["net_pnl"] <= 0]
    if not w or not l:
        return None
    aw, al = sum(w) / len(w), abs(sum(l) / len(l))
    return aw, al, al / aw


def main():
    load()
    sels = [
        ("control (nothing)", {}),
        ("A  HV>IV", A),
        ("A6 HV-IV>=6pp", A6),
        ("C  exit 2 DTE", C),
        ("A + C", {**A, **C}),
        ("A6 + C", {**A6, **C}),
    ]

    print("=" * 96)
    print("SELECTION ABLATION  (all at 7.5% sizing, as originally run)")
    print("=" * 96)
    raw, res = {}, {}
    for lab, ov in sels:
        kw = dict(BASE)
        kw.update(ov)
        sp = E.Spec(label=lab, **kw)
        tr = []
        for db in DBS_2022.values():
            tr += E.run(db, sp)
        raw[lab] = tr
        res[lab] = show(lab, tr)

    print()
    print("=" * 96)
    print("SIZING SWEEP  (same selections, re-sized exactly -- no re-run)")
    print("=" * 96)
    sweep = {}
    for lab in ("control (nothing)", "A + C", "A6 + C"):
        for pct in (0.075, 0.05, 0.035, 0.025, 0.02, 0.015):
            k = f"{lab} @ {pct*100:.1f}%"
            sweep[k] = resize(raw[lab], pct)
            show(k, sweep[k])
        print()

    print("=" * 96)
    print("LOSS/WIN RATIO -- did we fix what actually broke 2022?")
    print("=" * 96)
    print(f"  {'config':<40}{'avg win':>10}{'avg loss':>11}{'ratio':>8}")
    print("  " + "-" * 69)
    for lab in [l for l, _ in sels]:
        r = lwr(raw[lab])
        if r:
            print(f"  {lab:<40}{r[0]:>+10,.0f}{-r[1]:>+11,.0f}{r[2]:>7.2f}x")

    pickle.dump({"raw": raw, "sweep": sweep}, open("r22_stack.pkl", "wb"))
    print("\nwrote r22_stack.pkl")


if __name__ == "__main__":
    main()
