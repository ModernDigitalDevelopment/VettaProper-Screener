"""What ACTUALLY separates winning configs from losing ones, across all 180."""
import pickle, glob, statistics
from collections import defaultdict
exec(open("meta.py").read().split("rows = load_all()")[0])

rows = load_all()
recs = [(f, k, stats(tr), tr) for f, k, tr in rows]
recs = [r for r in recs if r[2]["n"] >= 40]
print(f"analysing {len(recs)} configs with n>=40\n")

win = [r for r in recs if r[2]["net"] > 0]
los = [r for r in recs if r[2]["net"] <= 0]

print("=" * 90)
print("PROFITABLE vs UNPROFITABLE CONFIGS -- what distinguishes them?")
print("=" * 90)
print(f"{'metric':<28}{'profitable':>16}{'unprofitable':>16}{'separation':>14}")
print("-" * 90)
for key, lab, fmt in (("win", "win rate %", "{:.1f}"),
                      ("lw", "loss/win ratio", "{:.2f}"),
                      ("ror", "mean RoR %", "{:+.2f}"),
                      ("n", "trade count", "{:.0f}")):
    a = statistics.median(r[2][key] for r in win)
    b = statistics.median(r[2][key] for r in los)
    print(f"{lab:<28}{fmt.format(a):>16}{fmt.format(b):>16}"
          f"{fmt.format(a-b):>14}")

print()
print("=" * 90)
print("THE DECISIVE VARIABLE: loss/win ratio buckets")
print("=" * 90)
print(f"{'L/W band':<16}{'configs':>9}{'profitable':>12}{'hit rate':>11}{'med win%':>11}")
print("-" * 90)
bands = [(0, 0.8), (0.8, 1.0), (1.0, 1.5), (1.5, 2.5), (2.5, 99)]
for lo, hi in bands:
    g = [r for r in recs if lo <= r[2]["lw"] < hi]
    if not g:
        continue
    p = sum(1 for r in g if r[2]["net"] > 0)
    mw = statistics.median(r[2]["win"] for r in g)
    print(f"{lo:.1f}-{hi:<11.1f}{len(g):>9}{p:>12}{100*p/len(g):>10.0f}%{mw:>10.1f}%")

print()
print("=" * 90)
print("AND THE WIN RATE? (the metric everyone optimises)")
print("=" * 90)
print(f"{'win% band':<16}{'configs':>9}{'profitable':>12}{'hit rate':>11}{'med L/W':>11}")
print("-" * 90)
for lo, hi in [(0,45),(45,55),(55,65),(65,75),(75,101)]:
    g = [r for r in recs if lo <= r[2]["win"] < hi]
    if not g:
        continue
    p = sum(1 for r in g if r[2]["net"] > 0)
    ml = statistics.median(r[2]["lw"] for r in g)
    print(f"{lo}-{hi:<13}{len(g):>9}{p:>12}{100*p/len(g):>10.0f}%{ml:>11.2f}")
