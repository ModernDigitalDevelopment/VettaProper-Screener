"""Monthly rolling 20%-OTM long-call hedge, using VXX as the VIX proxy.

USER'S RULE: buy a ~20% OTM call on a monthly cycle; if the underlying reaches
50% of the way to the strike, sell the hedge, re-buy a fresh 20%-OTM call and
roll on.

PROXY LIMITATION -- this is the central caveat and it cuts against the hedge:
VIX options do not exist in this dataset (0 rows for VIX / VIX1D / SPX). VXX
does (42,661 call-days with real bid/ask across 2022). But VXX is a
futures-based ETN, not the VIX index. In normal contango the front VIX futures
roll down toward spot, so VXX bleeds value continuously -- it fell from ~28 to
~14 over 2022 DESPITE a bear market. A long VXX call therefore carries a
structural headwind a real VIX call does not.

Consequence: results here are a LOWER BOUND on a true VIX-call hedge. If the
VXX version still helps, a VIX version would very likely help more. If the VXX
version loses money, that is NOT proof a VIX hedge would.

Implementation notes:
  - strike chosen as the listed strike closest to 1.20 x spot
  - the nearest expiry at least 25 days out (monthly cycle)
  - "50% of the way to the strike" = spot >= entry_spot + 0.5*(strike - entry_spot)
  - bought at the ask, sold at the bid (a hedge buyer pays the spread both ways)
  - sizing expressed as a fixed % of equity per cycle, swept
"""
import pickle
import sqlite3

DBS = [f"/home/user/db2022/thetadata_options_{q}_2022.db"
       for q in ("q1", "q2", "q3", "q4")]
EQ = 50_000.0


def load_vxx():
    """All VXX call quotes, keyed by date -> list of contracts."""
    by_date = {}
    spot = {}
    for db in DBS:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        q = """SELECT trade_date, expiration, strike, bid, ask, underlying_price
               FROM option_eod
               WHERE symbol='VXX' AND right='CALL' AND bid > 0 AND ask > 0
                     AND underlying_price > 0"""
        for r in c.execute(q):
            d = r["trade_date"]
            by_date.setdefault(d, []).append(dict(r))
            spot[d] = float(r["underlying_price"])
        c.close()
    return by_date, spot


def days_between(a, b):
    from datetime import datetime
    fa = datetime.strptime(a[:10], "%Y-%m-%d")
    fb = datetime.strptime(b[:10], "%Y-%m-%d")
    return (fb - fa).days


def run(pct_per_cycle=0.01, otm=0.20, trigger=0.50, min_dte=25, verbose=False):
    by_date, spot = load_vxx()
    dates = sorted(by_date)
    pos = None
    cash = 0.0
    log = []

    for d in dates:
        s = spot[d]
        chain = by_date[d]

        # ---- manage an open hedge ----------------------------------------
        if pos:
            live = [r for r in chain
                    if r["expiration"] == pos["exp"]
                    and abs(float(r["strike"]) - pos["strike"]) < 1e-6]
            dte = days_between(d, pos["exp"])
            if live:
                bid = float(live[0]["bid"])
                half = pos["entry_spot"] + trigger * (pos["strike"] - pos["entry_spot"])
                hit = s >= half
                if hit or dte <= 2:
                    proceeds = bid * 100 * pos["n"]
                    cash += proceeds
                    log.append({
                        "action": "SELL", "date": d, "strike": pos["strike"],
                        "exp": pos["exp"], "spot": s, "price": bid,
                        "n": pos["n"], "cash": proceeds,
                        "reason": "TRIGGER_50PCT" if hit else "NEAR_EXPIRY",
                        "pnl": proceeds - pos["cost"],
                    })
                    pos = None
            elif dte <= 0:
                pos = None          # expired worthless, cost already paid

        # ---- open a new hedge if flat ------------------------------------
        if pos is None:
            target = s * (1 + otm)
            cands = [r for r in chain if days_between(d, r["expiration"]) >= min_dte]
            if cands:
                best = min(cands, key=lambda r: (abs(float(r["strike"]) - target),
                                                 days_between(d, r["expiration"])))
                ask = float(best["ask"])
                if ask > 0:
                    budget = EQ * pct_per_cycle
                    n = int(budget // (ask * 100))
                    if n >= 1:
                        cost = ask * 100 * n
                        cash -= cost
                        pos = {"strike": float(best["strike"]),
                               "exp": best["expiration"], "n": n,
                               "cost": cost, "entry_spot": s, "entry": d}
                        log.append({
                            "action": "BUY", "date": d,
                            "strike": float(best["strike"]),
                            "exp": best["expiration"], "spot": s,
                            "price": ask, "n": n, "cash": -cost,
                            "reason": "OPEN", "pnl": 0.0,
                        })

    return cash, log


def main():
    print("=" * 92)
    print("VXX 20%-OTM ROLLING CALL HEDGE -- 2022  (proxy for a VIX call hedge)")
    print("=" * 92)
    print("CAVEAT: VXX is a futures ETN and bled from ~28 to ~14 across 2022")
    print("despite the bear market. This is a LOWER BOUND on a true VIX hedge.")
    print()
    out = {}
    print(f"  {'budget/cycle':<16}{'cycles':>8}{'net':>12}{'as % of 50k':>14}")
    print("  " + "-" * 52)
    for pct in (0.005, 0.01, 0.02, 0.03):
        cash, log = run(pct_per_cycle=pct)
        buys = sum(1 for x in log if x["action"] == "BUY")
        out[pct] = (cash, log)
        print(f"  {pct*100:>5.1f}% of equity{buys:>8}{cash:>+12,.0f}"
              f"{100*cash/EQ:>+13.1f}%")

    print()
    cash, log = out[0.01]
    sells = [x for x in log if x["action"] == "SELL"]
    trig = [x for x in sells if x["reason"] == "TRIGGER_50PCT"]
    print(f"  at 1% per cycle: {len(log)} events, {len(sells)} closes, "
          f"{len(trig)} hit the 50% trigger")
    if sells:
        wins = [x for x in sells if x["pnl"] > 0]
        print(f"  closes profitable: {len(wins)} of {len(sells)}")
        best = max(sells, key=lambda x: x["pnl"])
        print(f"  best close: {best['date']} strike {best['strike']:.0f} "
              f"pnl {best['pnl']:+,.0f} ({best['reason']})")
    print()
    print("  first 12 events:")
    for x in log[:12]:
        print(f"    {x['date']}  {x['action']:<4} K={x['strike']:>5.1f} "
              f"exp={x['exp'][:10]} spot={x['spot']:>5.2f} "
              f"px={x['price']:>5.2f} n={x['n']:>3} {x['reason']}")

    pickle.dump(out, open("r22_vxx.pkl", "wb"))
    print("\nwrote r22_vxx.pkl")


if __name__ == "__main__":
    main()
