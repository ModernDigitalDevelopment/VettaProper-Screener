"""A/D reaction-low breach as a TRADE-MANAGEMENT trigger. Q1 2022.

This tests the user's written execution protocol, which is a position-management
rule, not an entry rule:

  Monitor the A/D line daily. If it closes below its prior reaction low, close
  or adjust open bull put spreads within 1-2 sessions.
    Option A  full exit
    Option B  sell a bear call on the same expiry -> convert to iron condor

Q1 2022 has 7 breach days: 2022-02-23, 02-24, and a cluster 03-07..03-15.
Both correspond to real stress (the Russia invasion selloff and the March
follow-through), so the trigger is firing at plausible moments.

The comparison is like-for-like: one entry stream, four management policies.
Entries are IDENTICAL across all arms -- only what happens after a breach
differs. That isolates the management decision from the selection decision.

  hold        ignore breaches (control)
  exit_0      close all open bull puts on the breach day
  exit_1      close the next session (the '1-2 sessions' in the protocol)
  exit_2      close two sessions later
"""
import pickle

import spec_engine as E
from run2022 import BASE, load, metrics

Q1 = "/home/user/db2022/thetadata_options_q1_2022.db"

SPEC = dict(BASE)
SPEC.update(
    max_rel_spread=0.10,
    max_pct_per_position=0.05,
    max_per_sector=1,
    min_risk_reward=0.20,
    short_delta=0.25, delta_tol=0.05,
    earnings_blackout_days=14,
    target_dte=9, dte_tol=2,
    profit_target=0.80,
    exit_at_dte=2,
    trend_mode="s10_50",          # bull puts in an uptrend, as standardised
    structure="bull_put",
)


def breach_days():
    m = pickle.load(open("macro.pkl", "rb"))
    return sorted(d for d in m if m[d]["ad_break_low"] > 0)


def main():
    load()
    brk = set(breach_days())
    E.BREACH.clear(); E.BREACH.update(brk)
    m = pickle.load(open("macro.pkl", "rb"))
    E.SESSIONS.clear(); E.SESSIONS.extend(sorted(m))
    E._SIDX.clear()
    print(f"A/D breach days loaded: {len(brk)} across 2022-2024")
    q1b = sorted(d for d in brk if d.startswith("2022-0") and d <= "2022-03-31")
    print(f"  in Q1 2022: {q1b}")
    print()

    print("=" * 92)
    print("A/D REACTION-LOW BREACH AS AN EXIT TRIGGER -- Q1 2022 bull puts")
    print("identical entries in every arm; only post-breach handling differs")
    print("=" * 92)
    out = {}
    for lab, lag in (("hold (ignore breaches)", -1),
                     ("exit on breach day", 0),
                     ("exit +1 session", 1),
                     ("exit +2 sessions", 2)):
        kw = dict(SPEC)
        kw["breach_exit_lag"] = lag
        sp = E.Spec(label=lab, **kw)
        tr = E.run(Q1, sp)
        m = metrics(tr)
        ror = (100 * sum(t["net_pnl"] / t["max_loss"]
                         for t in tr if t["max_loss"]) / len(tr)) if tr else 0.0
        nb = sum(1 for t in tr if t["exit_reason"] == "AD_BREACH_EXIT")
        print(f"  {lab:<26} n={m['n']:>4} win={m['win']:>5.1f}% "
              f"net={m['net']:>+8,.0f} pf={m['pf']:>4.2f} ror={ror:>+6.2f}% "
              f"dd={m['dd']:>5.1f}%  breach-exits={nb}")
        out[lab] = (tr, m, ror)

    pickle.dump(out, open("r22_breach.pkl", "wb"))
    print("\nwrote r22_breach.pkl")


if __name__ == "__main__":
    main()
