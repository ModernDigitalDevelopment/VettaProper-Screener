"""Tradeable test: pick the side from breadth KNOWN AT ENTRY. No hindsight.

The previous test split results by up/down month, but a month is only known to
be an up month after it ends. That makes the split diagnostic, not tradeable.

Here the rule sees only breadth as of the entry date and must commit. For every
(symbol, entry_date) where both a put and a call were available, the rule picks
one. Both arms face the identical opportunity set, so the comparison is fair.

Slot contention is deliberately excluded here: it was the mechanical failure
that sank the earlier switch, and mixing it back in would confound the signal
question with the allocator question. This measures the SIGNAL only. A rule that
cannot win here will not win with an allocator bolted on.

Benchmarks:
  always put    what the strategy did in 2022      (-$38,512 in the real book)
  always call   the inverted strategy              (+$26,168)
  perfect       picks the winning side per trade    (upper bound, not achievable)
  coin flip     seeded random side, 200 draws      (the null hypothesis)
"""
import pickle
import random
import statistics

LAGS = (0, 1, 3, 5)


def load():
    pool = pickle.load(open("pool22.pkl", "rb"))
    br = pickle.load(open("breadth22.pkl", "rb"))
    sec = __import__("json").load(open("sectors_2022.json"))
    puts = {(t["symbol"], t["entry_date"]): t for t in pool["bull_put"]}
    calls = {(t["symbol"], t["entry_date"]): t for t in pool["bear_call"]}
    return puts, calls, br, sec


def ror(t):
    return t["net_pnl"] / t["max_loss"] if t["max_loss"] else 0.0


def report(name, picks):
    if not picks:
        print(f"  {name:<34} (none)")
        return None
    n = len(picks)
    w = sum(1 for t in picks if t["net_pnl"] > 0)
    net = sum(t["net_pnl"] for t in picks)
    r = 100 * sum(ror(t) for t in picks) / n
    print(f"  {name:<34} n={n:>4} win={100*w/n:>5.1f}% "
          f"net={net:>+9,.0f} ror={r:>+6.1f}%")
    return net


def main():
    puts, calls, br, sec = load()
    both = sorted(set(puts) & set(calls))
    print(f"overlap where BOTH sides were available: {len(both)} "
          f"(of {len(puts)} puts, {len(calls)} calls)")
    print("Both arms are scored on this identical set, so the only difference")
    print("between them is the side choice.")
    print()

    dates = sorted({d for (s, d) in br if s == "MARKET"})
    di = {d: i for i, d in enumerate(dates)}

    def bval(scope, d, key, lag):
        i = di.get(d)
        if i is None or i - lag < 0:
            return None
        v = br.get((scope, dates[i - lag]))
        return v[key] if v else None

    print("=" * 78)
    print("BENCHMARKS")
    print("=" * 78)
    base_put = report("always bull put", [puts[k] for k in both])
    base_call = report("always bear call", [calls[k] for k in both])
    report("perfect hindsight (upper bound)",
           [max(puts[k], calls[k], key=lambda t: t["net_pnl"]) for k in both])

    rng = random.Random(7)
    flips = []
    for _ in range(200):
        picks = [(puts[k] if rng.random() < 0.5 else calls[k]) for k in both]
        flips.append(sum(t["net_pnl"] for t in picks))
    mu, sd = statistics.mean(flips), statistics.pstdev(flips)
    print(f"  {'coin flip (200 draws)':<34} mean={mu:>+9,.0f} sd={sd:>8,.0f}")
    print(f"  {'':<34} 5th..95th pct = {sorted(flips)[9]:>+9,.0f} .. "
          f"{sorted(flips)[189]:>+9,.0f}")
    print()

    RULES = [
        ("market 10d thrust > 50%", "MARKET", "ad_thrust10", 0.50, None),
        ("market %above50 > 50%", "MARKET", "pct_above50", 50.0, None),
        ("market McClellan > 0", "MARKET", "mcclellan", 0.0, None),
        ("market A/D line rising", "MARKET", "ad_line_rising", 0.5, None),
        ("sector 10d thrust > 50%", "SECTOR", "ad_thrust10", 0.50, None),
        ("sector %above50 > 50%", "SECTOR", "pct_above50", 50.0, None),
        ("sector thrust > market thrust", "SECTOR", "ad_thrust10", None, "MARKET"),
        ("sector %above50 > market", "SECTOR", "pct_above50", None, "MARKET"),
        ("sector McClellan > market", "SECTOR", "mcclellan", None, "MARKET"),
    ]

    print("=" * 78)
    print("BREADTH RULES -- bull put when signal is bullish, else bear call")
    print("=" * 78)
    results = {}
    for lag in LAGS:
        print(f"\n--- breadth lagged {lag} trading day(s) ---")
        for name, scope, key, thr, relto in RULES:
            picks, skipped = [], 0
            for k in both:
                sym, d = k
                sc = sec.get(sym, "UNKNOWN") if scope == "SECTOR" else "MARKET"
                v = bval(sc, d, key, lag)
                if v is None:
                    skipped += 1
                    continue
                if relto:
                    m = bval(relto, d, key, lag)
                    if m is None:
                        skipped += 1
                        continue
                    bullish = v > m
                else:
                    bullish = v > thr
                picks.append(puts[k] if bullish else calls[k])
            net = report(f"{name}", picks)
            if net is not None:
                results[(lag, name)] = net

    print()
    print("=" * 78)
    print("RANKED (all lags)")
    print("=" * 78)
    print(f"  {'rule':<34}{'lag':>5}{'net':>11}  vs always-call")
    print("  " + "-" * 64)
    for (lag, name), net in sorted(results.items(), key=lambda x: -x[1])[:12]:
        print(f"  {name:<34}{lag:>5}{net:>+11,.0f}  {net - base_call:>+10,.0f}")
    print()
    print(f"  always-call benchmark on same set: {(base_call or 0):>+,.0f}")
    print(f"  coin-flip mean:                    {mu:>+,.0f}")

    pickle.dump(results, open("breadth_trade_results.pkl", "wb"))


if __name__ == "__main__":
    main()
