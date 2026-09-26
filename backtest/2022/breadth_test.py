"""Does breadth predict which side to sell, or merely describe the past?

The trap this is built to avoid: ADX/DMI "worked" in 2022 only because they
were proxies for direction, so they would invert the moment the market did.
A usable signal must separate winners from losers WITHIN a regime, not just
label down months as down.

So every test below is run three ways:
  ALL      all 2022 trades
  DOWN     down months only
  UP       up months only  (Mar, Jul, Nov -- where puts made +$41,111)

A signal that only separates in the ALL column is direction in disguise. A
signal that separates the SAME WAY in both UP and DOWN is real information.

Signals tested, market-wide and sector-relative:
  ad_pct, ad_thrust10, mcclellan, pct_above50, ad_line_rising
  plus sector-minus-market spreads for each (the "micro" version)
"""
import pickle
from collections import defaultdict

UP_MONTHS = {"2022-03", "2022-07", "2022-11"}


def load():
    sw = pickle.load(open("r_switch_2022.pkl", "rb"))
    br = pickle.load(open("breadth22.pkl", "rb"))
    sec = __import__("json").load(open("sectors_2022.json"))
    return sw["22_put"][0], sw["22_call"][0], br, sec


def attach(trades, br, sec, label):
    """Add breadth context as of the ENTRY date. No lookahead: the entry-day
    breadth is known at the close the trade is placed on."""
    out = []
    miss = 0
    for t in trades:
        d = t["entry_date"]
        mk = br.get(("MARKET", d))
        sc = sec.get(t["symbol"], "UNKNOWN")
        sb = br.get((sc, d))
        if not mk:
            miss += 1
            continue
        r = {
            "side": label,
            "sym": t["symbol"], "date": d, "month": d[:7],
            "pnl": t["net_pnl"],
            "ror": t["net_pnl"] / t["max_loss"] if t["max_loss"] else 0.0,
            "mk_pct": mk["ad_pct"],
            "mk_thrust": mk["ad_thrust10"],
            "mk_mcc": mk["mcclellan"],
            "mk_above": mk["pct_above50"],
            "mk_rising": mk["ad_line_rising"],
        }
        if sb:
            r.update({
                "sc_thrust": sb["ad_thrust10"],
                "sc_mcc": sb["mcclellan"],
                "sc_above": sb["pct_above50"],
                # sector MINUS market: the micro signal with a macro denominator
                "rel_thrust": sb["ad_thrust10"] - mk["ad_thrust10"],
                "rel_mcc": sb["mcclellan"] - mk["mcclellan"],
                "rel_above": sb["pct_above50"] - mk["pct_above50"],
            })
        out.append(r)
    if miss:
        print(f"  ({miss} {label} trades had no breadth context)")
    return out


def agg(rows):
    if not rows:
        return None
    n = len(rows)
    w = sum(1 for r in rows if r["pnl"] > 0)
    return {
        "n": n, "win": 100 * w / n,
        "net": sum(r["pnl"] for r in rows),
        "ror": 100 * sum(r["ror"] for r in rows) / n,
    }


def subset(rows, which):
    if which == "ALL":
        return rows
    if which == "UP":
        return [r for r in rows if r["month"] in UP_MONTHS]
    return [r for r in rows if r["month"] not in UP_MONTHS]


def test(puts, calls, key, thresh, name):
    """For a given breadth threshold, compare put vs call performance above
    and below it. The question is not 'do puts do better when breadth is
    strong' -- it is whether the PUT-MINUS-CALL edge changes sign."""
    print(f"\n{name}   (threshold {thresh})")
    print(f"  {'regime':<6} {'breadth':<9} "
          f"{'put n':>6}{'put ror':>9}  {'call n':>7}{'call ror':>9}"
          f"  {'put-call':>9}")
    print("  " + "-" * 74)
    verdict = {}
    for reg in ("ALL", "DOWN", "UP"):
        p, c = subset(puts, reg), subset(calls, reg)
        for lab, f in (("strong", lambda r: r.get(key) is not None and r[key] > thresh),
                       ("weak", lambda r: r.get(key) is not None and r[key] <= thresh)):
            pa, ca = agg([r for r in p if f(r)]), agg([r for r in c if f(r)])
            if not pa or not ca or pa["n"] < 8 or ca["n"] < 8:
                print(f"  {reg:<6} {lab:<9} "
                      f"{(pa['n'] if pa else 0):>6}{'--':>9}  "
                      f"{(ca['n'] if ca else 0):>7}{'--':>9}  {'(thin)':>9}")
                continue
            edge = pa["ror"] - ca["ror"]
            verdict[(reg, lab)] = edge
            print(f"  {reg:<6} {lab:<9} "
                  f"{pa['n']:>6}{pa['ror']:>+8.1f}%  "
                  f"{ca['n']:>7}{ca['ror']:>+8.1f}%  {edge:>+8.1f}pp")
    # the discipline test: does the sign of the put-call edge agree in UP and DOWN?
    u, d = verdict.get(("UP", "strong")), verdict.get(("DOWN", "strong"))
    if u is not None and d is not None:
        ok = (u > 0) == (d > 0)
        print(f"  -> strong-breadth edge sign: UP {u:+.1f} / DOWN {d:+.1f}  "
              f"{'CONSISTENT' if ok else 'INVERTS (direction proxy)'}")
    return verdict


def main():
    puts, calls, br, sec = load()
    p = attach(puts, br, sec, "put")
    c = attach(calls, br, sec, "call")
    print(f"put trades with breadth: {len(p)}   call trades: {len(c)}")

    print("\n" + "=" * 80)
    print("MARKET-WIDE BREADTH")
    print("=" * 80)
    test(p, c, "mk_thrust", 0.50, "10-day A/D thrust (market)")
    test(p, c, "mk_above", 50.0, "% of names above own 50-day SMA (market)")
    test(p, c, "mk_mcc", 0.0, "McClellan oscillator (market)")

    print("\n" + "=" * 80)
    print("SECTOR-RELATIVE BREADTH  (the micro signal)")
    print("=" * 80)
    test(p, c, "rel_thrust", 0.0, "sector thrust MINUS market thrust")
    test(p, c, "rel_above", 0.0, "sector %above50 MINUS market %above50")
    test(p, c, "rel_mcc", 0.0, "sector McClellan MINUS market McClellan")

    pickle.dump({"put": p, "call": c}, open("breadth_ctx.pkl", "wb"))
    print("\nwrote breadth_ctx.pkl")


if __name__ == "__main__":
    main()
