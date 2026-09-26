"""2022 out-of-sample harness.

BASE is the original 2023 screener, unchanged:
  bull put, delta 0.25 +/-0.05, R:R >= 0.20, 14-day earnings blackout,
  7-11 DTE, spread <= 10%, 7.5% per position, 1 per sector,
  exit at 80% profit target only.

Constants held across every test, per instruction: structure, delta band,
R:R gate, earnings blackout.
"""
import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor

import spec_engine as E

DBS_2022 = {q: f"/home/user/db2022/thetadata_options_{q}_2022.db"
            for q in ("q1", "q2", "q3", "q4")}

BASE = dict(
    structure="bull_put",
    short_delta=0.25, delta_tol=0.05,
    width=5.0, width_tol=5.1,
    target_dte=9, dte_tol=2,          # 7-11 DTE
    min_ivrv=0.0,
    max_rel_spread=0.10,
    min_credit=0.10,
    mid_fill_prob=1.00,               # deterministic: no seed noise
    profit_target=0.80,
    exit_days_before_expiry=0,
    hold_to_expiry=False,
    equity=50_000.0,
    max_pct_per_position=0.075,       # 7.5%
    max_per_sector=1,
    max_open=12,
    max_new_per_day=4,
    min_risk_reward=0.20,
    earnings_blackout_days=14,
    blackout_exdiv=False,
    trend_mode="s10_50",
    rank_mode="score",
)


def load():
    E.TREND.update(pickle.load(open("trend22.pkl", "rb")))
    E.INDICATORS.update(pickle.load(open("ind22.pkl", "rb")))
    E.HVIV.update(pickle.load(open("hviv22.pkl", "rb")))
    E.EVENTS.update(pickle.load(open("events.pkl", "rb")))
    E.SECTORS.update(json.load(open("sectors_2022.json")))
    # signals.pkl is 2023-only; min_ivrv=0 so it is unused, but the key must
    # exist or the IV/RV gate would reject every 2022 candidate.
    E.SIGNALS.update({k: {"ivrv": 1.0, "ts": 1.0} for k in E.TREND})


def one(args):
    label, ov = args
    load()
    kw = dict(BASE)
    kw.update(ov)
    spec = E.Spec(label=label, **kw)
    trades = []
    for db in DBS_2022.values():
        trades += E.run(db, spec)
    return label, trades


def metrics(tr, eq=50_000.0):
    if not tr:
        return dict(n=0, win=0, exp=0, net=0, pf=0, dd=0, peak=0, worst=0)
    n = len(tr)
    net = sum(t["net_pnl"] for t in tr)
    w = [t for t in tr if t["net_pnl"] > 0]
    gp = sum(t["net_pnl"] for t in w)
    gl = -sum(t["net_pnl"] for t in tr if t["net_pnl"] <= 0)
    cum = hi = dd = 0.0
    for t in sorted(tr, key=lambda x: x["exit_date"]):
        cum += t["net_pnl"]
        hi = max(hi, cum)
        dd = max(dd, hi - cum)
    ev = []
    for t in tr:
        ev.append((t["entry_date"], t["max_loss"]))
        ev.append((t["exit_date"], -t["max_loss"]))
    ev.sort()
    c = pk = 0.0
    for _, v in ev:
        c += v
        pk = max(pk, c)
    return dict(n=n, win=round(100 * len(w) / n, 1), exp=round(net / n),
                net=round(net), pf=round(gp / gl, 2) if gl > 0 else 99.0,
                dd=round(100 * dd / eq, 1), peak=round(100 * pk / eq),
                worst=round(min(t["net_pnl"] for t in tr)))


HDR = (f"{'configuration':<40}{'n':>5}{'win%':>7}{'exp':>7}"
       f"{'net':>10}{'PF':>6}{'DD%':>7}{'peak%':>7}")


def show(label, m):
    print(f"{label:<40}{m['n']:>5}{m['win']:>7}{m['exp']:>7}"
          f"{m['net']:>10,}{m['pf']:>6}{m['dd']:>7}{m['peak']:>7}", flush=True)


def run(variants, outfile, workers=2):
    out = {}
    print(HDR)
    print("-" * 89)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for label, tr in ex.map(one, variants):
            out[label] = tr
            show(label, metrics(tr))
    pickle.dump(out, open(outfile, "wb"))
    return out


T1 = [
 ("T1 baseline s10_50 (control)", {}),
 ("T1 smooth10 14d, stretch<=8%",  dict(trend_mode="smooth", trend_fast=10, min_days_above=14, max_stretch=8.0)),
 ("T1 smooth10 14d, stretch<=5%",  dict(trend_mode="smooth", trend_fast=10, min_days_above=14, max_stretch=5.0)),
 ("T1 smooth10 21d, stretch<=8%",  dict(trend_mode="smooth", trend_fast=10, min_days_above=21, max_stretch=8.0)),
 ("T1 smooth10 30d, stretch<=8%",  dict(trend_mode="smooth", trend_fast=10, min_days_above=30, max_stretch=8.0)),
 ("T1 smooth20 14d, stretch<=8%",  dict(trend_mode="smooth", trend_fast=20, min_days_above=14, max_stretch=8.0)),
 ("T1 smooth20 21d, stretch<=6%",  dict(trend_mode="smooth", trend_fast=20, min_days_above=21, max_stretch=6.0)),
 ("T1 smooth10 14d +slope<=0.3",   dict(trend_mode="smooth", trend_fast=10, min_days_above=14, max_stretch=8.0, max_stretch_slope=0.3)),
]

# ---- test 2: ADX + DMI ----------------------------------------------------
T2 = [
 ("T2 control (no ADX)", {}),
 ("T2 ADX>=25", dict(min_adx=25)),
 ("T2 ADX>=30", dict(min_adx=30)),
 ("T2 ADX>=35", dict(min_adx=35)),
 ("T2 ADX>=25 +DI>-DI", dict(min_adx=25, require_di_bullish=True)),
 ("T2 ADX>=30 +DI>-DI", dict(min_adx=30, require_di_bullish=True)),
 ("T2 ADX>=35 +DI>-DI", dict(min_adx=35, require_di_bullish=True)),
]

# ---- test 3: RSI bands ----------------------------------------------------
T3 = [
 ("T3 control (no RSI)", {}),
 ("T3 RSI < 70",   dict(rsi_lo2=0.1, rsi_hi2=70)),
 ("T3 RSI 50-70",  dict(rsi_lo2=50, rsi_hi2=70)),
 ("T3 RSI 30-50",  dict(rsi_lo2=30, rsi_hi2=50)),
 ("T3 RSI < 30",   dict(rsi_lo2=0.1, rsi_hi2=30)),
]

# ---- test 4: stochastics --------------------------------------------------
T4 = [
 ("T4 control (no stoch)", {}),
 ("T4 %K < 50", dict(max_stoch_k=50)),
 ("T4 %K < 40", dict(max_stoch_k=40)),
 ("T4 %K < 30", dict(max_stoch_k=30)),
 ("T4 %K < 60", dict(max_stoch_k=60)),
]

# ---- test 5: HV vs IV -----------------------------------------------------
T5 = [
 ("T5 control (no HV/IV)", {}),
 ("T5 HV > IV",          dict(require_hv_gt_iv=True)),
 ("T5 HV-IV >= +3pp",    dict(min_hv_minus_iv=3.0)),
 ("T5 HV-IV >= +6pp",    dict(min_hv_minus_iv=6.0)),
]

# ---- test 6: DTE and exits ----------------------------------------------
T6 = [
 ("T6 control 7-11 DTE, expiry", {}),
 ("T6 12+/-2 DTE, expiry",        dict(target_dte=12, dte_tol=2)),
 ("T6 12+/-2 DTE, exit 2 DTE",    dict(target_dte=12, dte_tol=2, exit_at_dte=2)),
 ("T6 12+/-2 DTE, exit 3 DTE",    dict(target_dte=12, dte_tol=2, exit_at_dte=3)),
 ("T6 12+/-2 DTE, exit 1 DTE",    dict(target_dte=12, dte_tol=2, exit_at_dte=1)),
 ("T6 7-11 DTE, exit 2 DTE",      dict(exit_at_dte=2)),
 ("T6 7-11 DTE, exit 3 DTE",      dict(exit_at_dte=3)),
]

# ---- test 7: dynamic diversification -------------------------------------
T7 = [
 ("T7 fixed 1/sector (control)", {}),
 ("T7 fixed 2/sector",           dict(max_per_sector=2)),
 ("T7 soft +1 (top quartile)",   dict(sector_mode="soft", sector_soft_cap=1)),
 ("T7 soft +2 (top quartile)",   dict(sector_mode="soft", sector_soft_cap=2)),
 ("T7 quality +1 (gap<=0.02)",   dict(sector_mode="quality", sector_soft_cap=1, sector_quality_gap=0.02)),
 ("T7 quality +1 (gap<=0.05)",   dict(sector_mode="quality", sector_soft_cap=1, sector_quality_gap=0.05)),
 ("T7 adaptive +2 (thin days)",  dict(sector_mode="adaptive", sector_soft_cap=2)),
]


SUITES = {"t1": T1, "t2": T2, "t3": T3, "t4": T4,
          "t5": T5, "t6": T6, "t7": T7}

BASE_SUITE = [
    ("2022 BASELINE (2023 spec, unchanged)", {}),
    ("  same, 2 per sector", dict(max_per_sector=2)),
    ("  same, 5% sizing", dict(max_pct_per_position=0.05)),
    ("  same, no trend filter", dict(trend_mode="none")),
]


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "base"
    if which in SUITES:
        run(SUITES[which], f"r22_{which}.pkl")
    elif which == "base":
        run(BASE_SUITE, "r22_base.pkl")
    else:
        print(f"unknown suite {which!r}; have {list(SUITES)} + base")


if __name__ == "__main__":
    main()
