"""Find a signal that says when to sell puts vs sell calls.

Motivation: the 2022 out-of-sample run lost money with a 72.6% win rate. The
filters were fine; the regime was wrong. A structurally-long strategy needs to
know when to invert.

Preference is for a PER-SYMBOL signal over a market-wide one, because July and
November 2022 were both up months inside a down year — a market-level switch
would have sat out the two months that actually made money.
"""
import pickle
from collections import defaultdict

BLANK = " " * 26


def load():
    r = pickle.load(open("r22_base.pkl", "rb"))
    trades = r["2022 BASELINE (2023 spec, unchanged)"]
    trend = pickle.load(open("trend22.pkl", "rb"))
    ind = pickle.load(open("ind22.pkl", "rb"))
    return trades, trend, ind


def context(trades, trend, ind):
    spy_t = {d: v for (s, d), v in trend.items() if s == "SPY"}
    spy_i = {d: v for (s, d), v in ind.items() if s == "SPY"}
    rows = []
    for x in trades:
        d = x["entry_date"]
        sv, si = spy_t.get(d), spy_i.get(d)
        tv, iv = trend.get((x["symbol"], d)), ind.get((x["symbol"], d))
        if not (sv and si and tv and iv):
            continue
        rows.append({
            "sym": x["symbol"], "date": d,
            "pnl": x["net_pnl"],
            "ror": x["net_pnl"] / x["max_loss"] if x["max_loss"] else 0.0,
            # market context
            "spy_stretch": (sv["sma10"] - sv["sma50"]) / sv["sma50"] * 100,
            "spy_above50": 1.0 if sv["close"] > sv["sma50"] else 0.0,
            "spy_dmi": si["plus_di"] - si["minus_di"],
            "spy_adx": si["adx14"],
            "spy_rsi": si["rsi14"],
            # symbol context
            "sym_dmi": iv["plus_di"] - iv["minus_di"],
            "sym_adx": iv["adx14"],
            "sym_rsi": iv["rsi14"],
            "sym_stretch": tv["stretch10"],
            "sym_days": float(tv["days_above"]),
            "sym_stoch": iv["stoch_k"],
        })
    return rows


def stat(g):
    if len(g) < 15:
        return None
    n = len(g)
    w = sum(1 for x in g if x["pnl"] > 0)
    net = sum(x["pnl"] for x in g)
    ror = 100 * sum(x["ror"] for x in g) / n
    return (f"n={n:>3} win={100*w/n:>5.1f}% net={net:>+9,.0f} "
            f"ror={ror:>+6.1f}%")


def split(rows, name, key, thresh):
    hi = [x for x in rows if x[key] > thresh]
    lo = [x for x in rows if x[key] <= thresh]
    a, b = stat(hi), stat(lo)
    if not (a and b):
        return None
    print(f"{name:<26} >  {a}")
    print(f"{BLANK} <= {b}")
    # separation in mean return on risk
    ra = sum(x["ror"] for x in hi) / len(hi)
    rb = sum(x["ror"] for x in lo) / len(lo)
    print(f"{BLANK}    separation {100*(ra-rb):+.1f}pp")
    print()
    return abs(ra - rb)


def main():
    trades, trend, ind = load()
    rows = context(trades, trend, ind)
    print(f"{len(rows)} of {len(trades)} trades have full signal context")
    print()
    print("SIGNAL SEARCH — what separated winners from losers in 2022?")
    print("=" * 88)

    tests = [
        ("SPY 10/50 spread %", "spy_stretch", 0.0),
        ("SPY price > 50 SMA", "spy_above50", 0.5),
        ("SPY +DI - -DI", "spy_dmi", 0.0),
        ("SPY ADX", "spy_adx", 25.0),
        ("SPY RSI", "spy_rsi", 50.0),
        ("symbol +DI - -DI", "sym_dmi", 0.0),
        ("symbol ADX", "sym_adx", 25.0),
        ("symbol RSI", "sym_rsi", 50.0),
        ("symbol 10/50 stretch %", "sym_stretch", 3.0),
        ("symbol days above 50", "sym_days", 20.0),
        ("symbol stoch %K", "sym_stoch", 50.0),
    ]
    scores = {}
    for name, key, th in tests:
        s = split(rows, name, key, th)
        if s is not None:
            scores[name] = s

    print("RANKED BY SEPARATION")
    print("-" * 44)
    for k, v in sorted(scores.items(), key=lambda x: -x[1]):
        print(f"  {k:<26} {100*v:>5.1f}pp")


if __name__ == "__main__":
    main()
