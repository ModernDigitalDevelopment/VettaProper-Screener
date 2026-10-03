"""RE-ENTRY TIMING: the one question never tested, and it needs no new data.

Every gate tested so far was EXOGENOUS -- VVIX, A/D, SMAs, ADX. All eleven
failed. There is a twelfth class never tried: ENDOGENOUS rules, driven by the
book's own P&L path. "Stop trading after N consecutive losses, resume after a
win / after K days." That is literally the user's question -- when to get out
and when to get back in -- and it requires no external feed at all.

Why it might work when exogenous gates did not: losses in this book cluster.
If drawdowns are serially correlated, the book's own recent P&L is a regime
indicator that no external series needs to supply.

WARNING ON CIRCULARITY, stated before the results: conditioning on
`exit_reason` or on realised P&L of the SAME trade is outcome selection and
was already caught twice in this project. This test only ever uses P&L of
trades that have ALREADY CLOSED strictly before the candidate entry date, so
the rule is causally implementable. Trades are ordered by entry date and the
state machine only looks backwards.

CONTROL: a matched-fraction random null. A pause rule that skips X% of trades
must beat randomly skipping the same X%, with whole days blocked.

Uses the no-stop control arms (clean baseline, one trade population).
"""
import pickle, random, datetime as dt
from collections import defaultdict

TAGS = ["2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q2", "2023Q4"]
B = 4000
random.seed(53)


def ror(ts):
    return (100*sum(t["net_pnl"]/t["max_loss"] for t in ts)/len(ts)
            if ts else float("nan"))


def dd_of(trades):
    ev = sorted(trades, key=lambda t: t["exit_date"])
    eq = peak = dd = 0.0
    for t in ev:
        eq += t["net_pnl"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return eq, dd


def simulate(trades, rule):
    """Walk trades in ENTRY order; rule decides take/skip from closed history.

    rule(state, entry_date) -> bool (True = take the trade)
    state is updated only with trades that closed BEFORE entry_date.
    """
    ordered = sorted(trades, key=lambda t: (t["entry_date"][:10],
                                            t["symbol"]))
    closed = []                      # (exit_date, net_pnl) of taken trades
    taken, skipped = [], []
    for t in ordered:
        ed = t["entry_date"][:10]
        # realise everything that closed strictly before this entry
        hist = [c for c in closed if c[0] < ed]
        if rule(hist, ed):
            taken.append(t)
            closed.append((t["exit_date"][:10], t["net_pnl"]))
        else:
            skipped.append(t)
    return taken, skipped


# ---------------- candidate endogenous rules -------------------------
def rule_always(hist, ed):
    return True


def mk_streak(n):
    """Pause after n consecutive losing closes; resume on the next winner."""
    def r(hist, ed):
        if len(hist) < n:
            return True
        last = sorted(hist)[-n:]
        return not all(p <= 0 for _, p in last)
    return r


def mk_lastk_neg(k):
    """Pause if the sum of the last k closed trades is negative."""
    def r(hist, ed):
        if len(hist) < k:
            return True
        last = sorted(hist)[-k:]
        return sum(p for _, p in last) > 0
    return r


def mk_dd_pause(frac):
    """Pause while the book sits more than `frac` below its own equity peak."""
    def r(hist, ed):
        if not hist:
            return True
        eq = peak = 0.0
        for _, p in sorted(hist):
            eq += p
            peak = max(peak, eq)
        if peak <= 0:
            return True
        return (peak - eq) / peak < frac
    return r


def main():
    byten = defaultdict(list)
    for tag in TAGS:
        d = pickle.load(open(f"r_stop_{tag}.pkl", "rb"))
        for k, rec in d.items():
            if k.endswith("|none"):
                byten[k.split("|")[0]] += rec[0]

    RULES = [("always on (control)", rule_always),
             ("pause after 2 straight losses", mk_streak(2)),
             ("pause after 3 straight losses", mk_streak(3)),
             ("pause after 4 straight losses", mk_streak(4)),
             ("pause if last 5 closes net<0", mk_lastk_neg(5)),
             ("pause if last 10 closes net<0", mk_lastk_neg(10)),
             ("pause if last 20 closes net<0", mk_lastk_neg(20)),
             ("pause while >20% off equity peak", mk_dd_pause(0.20)),
             ("pause while >35% off equity peak", mk_dd_pause(0.35)),
             ("pause while >50% off equity peak", mk_dd_pause(0.50))]

    for tenor, trades in sorted(byten.items()):
        base_net, base_dd = dd_of(trades)
        print("\n" + "=" * 104)
        print(f"{tenor}   {len(trades)} trades, ungated "
              f"net {base_net:+,.0f}, dd {base_dd:,.0f}, "
              f"net/dd {base_net/base_dd if base_dd else 0:+.2f}")
        print("=" * 104)
        print(f"{'rule':<32}{'taken':>7}{'skip%':>7}{'net':>11}"
              f"{'dd':>10}{'net/dd':>8}{'skipRoR':>9}{'null net':>11}"
              f"{'pctile':>8}")
        days = defaultdict(list)
        for t in trades:
            days[t["entry_date"][:10]].append(t)
        alld = sorted(days)

        for name, rule in RULES:
            taken, skipped = simulate(trades, rule)
            net, d = dd_of(taken)
            frac = len(skipped)/len(trades)
            # matched-fraction random null, blocked by whole entry days
            if skipped:
                nd = len({t["entry_date"][:10] for t in skipped})
                nulls = []
                for _ in range(B):
                    sk = set(random.sample(alld, min(nd, len(alld))))
                    keep = [t for dd_ in alld if dd_ not in sk
                            for t in days[dd_]]
                    nulls.append(dd_of(keep)[0] if keep else 0.0)
                nulls.sort()
                pc = sum(1 for z in nulls if z <= net)/B
                nm = sum(nulls)/B
                print(f"{name:<32}{len(taken):>7}{100*frac:>6.0f}%"
                      f"{net:>+11,.0f}{d:>10,.0f}"
                      f"{(net/d if d else 0):>8.2f}{ror(skipped):>+9.2f}"
                      f"{nm:>+11,.0f}{pc:>8.2f}")
            else:
                print(f"{name:<32}{len(taken):>7}{0:>6.0f}%"
                      f"{net:>+11,.0f}{d:>10,.0f}"
                      f"{(net/d if d else 0):>8.2f}{'--':>9}"
                      f"{'--':>11}{'--':>8}")
        print("  skipRoR = what the SKIPPED trades would have earned")
        print("  (very negative = the rule dodged genuinely bad trades)")
        print("  pctile >0.95 = beats randomly skipping the same share")


if __name__ == "__main__":
    main()
