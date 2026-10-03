"""Stop loss at a multiple of the credit collected. Q2 2022 -- the killer quarter.

The user's rule: "get out of all bull puts if the loss hits the potential gain
mark." A credit spread's potential gain IS the credit, so that is a 1x-credit
stop: close when the unrealised loss equals the credit received, i.e. when the
debit to close reaches 2x the credit.

Why this is the most promising untested lever: every previous attempt tried to
predict WHEN to be in the market. A stop does not predict anything. It caps the
left tail directly, and the meta-analysis across 180 configs found the
loss/win ratio -- not the win rate -- was the decisive variable. A stop attacks
L/W by construction.

Tested on Q2 2022 first because that is the quarter that broke every previous
strategy: -$25,924 at 35-45 DTE, win rate 31.7%, 59% drawdown. If a stop cannot
help there it cannot help anywhere.

Both tenors are run, since the stop may interact with holding period.
"""
import json, os, pickle
import spec_engine as E
from run2022 import BASE, metrics

DB = os.environ.get("SL_DB", "/home/user/db2022/thetadata_options_q2_2022.db")
YEAR = int(os.environ.get("SL_YEAR", "2022"))
TAG = os.environ.get("SL_TAG", "2022Q2")

SPEC = dict(BASE)
SPEC.update(
    structure="bull_put", trend_mode="s10_50",
    short_delta=0.30, delta_tol=0.05,
    max_rel_spread=0.10, min_risk_reward=0.20,
    max_pct_per_position=0.05, max_per_sector=2,
    max_open=12, max_new_per_day=4,
    earnings_blackout_days=14, blackout_days_after_event=14,
    blackout_exdiv=False,
    profit_target=0.80, hold_to_expiry=False, mid_fill_prob=1.00,
)


def load():
    for d in (E.TREND, E.INDICATORS, E.HVIV, E.EVENTS, E.SECTORS,
              E.SIGNALS, E.SQUEEZE, E.GATE):
        d.clear()
    E.TREND.update(pickle.load(open(
        "trend23.pkl" if YEAR == 2023 else "trend22.pkl", "rb")))
    E.EVENTS.update(pickle.load(open("events.pkl", "rb")))
    E.SECTORS.update(json.load(open("sectors_2022.json")))
    E.SIGNALS.update({k: {"ivrv": 1.0, "ts": 1.0} for k in E.TREND})


def run(lab, **ov):
    kw = dict(SPEC); kw.update(ov)
    tr = E.run(DB, E.Spec(label=lab, **kw))
    m = metrics(tr)
    ror = (100*sum(t["net_pnl"]/t["max_loss"] for t in tr if t["max_loss"])/len(tr)) if tr else 0
    w = [t["net_pnl"] for t in tr if t["net_pnl"]>0]
    l = [t["net_pnl"] for t in tr if t["net_pnl"]<=0]
    lw = (abs(sum(l)/len(l))/(sum(w)/len(w))) if w and l else 0
    from collections import Counter
    c = Counter(t["exit_reason"] for t in tr)
    nstop = sum(v for k2, v in c.items() if str(k2).startswith("STOP"))
    print(f"  {lab:<32} n={m['n']:>4} win={m['win']:>5.1f}% "
          f"net={m['net']:>+9,.0f} pf={m['pf']:>4.2f} ror={ror:>+7.2f}% "
          f"L/W={lw:>4.2f} dd={m['dd']:>5.1f}% stops={nstop:>3}", flush=True)
    return lab, tr, m, ror, lw


def main():
    load()
    out = {}
    print("=" * 106)
    print(f"STOP LOSS AT A MULTIPLE OF CREDIT -- {TAG}")
    print("1.0x = close when the loss equals the credit (the user's rule)")
    print("=" * 106)
    for tenor, tkw in (("short 7-11 DTE, exit 2",
                        dict(target_dte=9, dte_tol=2, exit_at_dte=2)),
                       ("long 35-45 DTE, exit 15",
                        dict(target_dte=40, dte_tol=5, exit_at_dte=15))):
        print(f"\n{tenor}")
        out[f"{tenor}|none"] = run("  no stop (control)", **tkw)
        for sm in (0.5, 1.0, 1.5, 2.0):
            out[f"{tenor}|{sm}"] = run(f"  stop at {sm:g}x credit",
                                       stop_loss_mult=sm, **tkw)
    pickle.dump({k: (v[1], v[2], v[3], v[4]) for k, v in out.items()},
                open(f"r_stop_{TAG}.pkl", "wb"))
    print(f"\nwrote r_stop_{TAG}.pkl")


if __name__ == "__main__":
    main()
