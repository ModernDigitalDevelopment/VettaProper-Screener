"""Verify the two candidate drivers, controlling for confounds.

1. Is delta 0.30-0.50 better because of delta, or because those trades happen
   to be condors (which are mostly at 0.30-0.50)?
2. Is EXPIRED bad because of gamma, or because trades that reach expiry are
   the ones already losing (selection effect)?
"""
import pickle, glob, statistics
from collections import defaultdict
exec(open("meta.py").read().split("rows = load_all()")[0])
rows = load_all()
seen = {}
for f, k, tr in rows:
    for t in tr:
        key = (t["symbol"], t["entry_date"], t.get("expiration"), t["structure"],
               round(t.get("width",0),2), round(t.get("credit",0),3))
        seen.setdefault(key, t)
trades = list(seen.values())

def agg(g):
    if len(g) < 40: return None
    w = [t["net_pnl"] for t in g if t["net_pnl"] > 0]
    l = [t["net_pnl"] for t in g if t["net_pnl"] <= 0]
    if not w or not l: return None
    aw, al = sum(w)/len(w), abs(sum(l)/len(l))
    ror = 100*sum(t["net_pnl"]/t["max_loss"] for t in g if t.get("max_loss"))/len(g)
    return len(g), 100*len(w)/len(g), al/aw, ror

print("=" * 92)
print("1. DELTA effect WITHIN each structure (controls for the condor confound)")
print("=" * 92)
for s in ("bull_put", "bear_call", "iron_condor"):
    print(f"\n  {s}:")
    print(f"    {'delta':<12}{'n':>6}{'win%':>8}{'L/W':>7}{'RoR':>9}")
    for lo, hi in ((0.20,0.30),(0.30,0.40),(0.40,0.50)):
        g = [t for t in trades if t["structure"]==s
             and lo <= abs(t.get("delta_at_entry") or 0) < hi]
        a = agg(g)
        if a:
            print(f"    {lo:.2f}-{hi:<7.2f}{a[0]:>6}{a[1]:>7.1f}%{a[2]:>7.2f}{a[3]:>+8.1f}%")

print()
print("=" * 92)
print("2. EXIT effect WITHIN structure and delta band (controls for selection)")
print("=" * 92)
for s in ("bull_put", "iron_condor"):
    print(f"\n  {s}, delta 0.30-0.50:")
    print(f"    {'exit':<20}{'n':>6}{'win%':>8}{'L/W':>7}{'RoR':>9}")
    for r in ("EXPIRED", "EOD_EXIT_DTE2", "EOD_EXIT_DTE1", "TAKE_PROFIT"):
        g = [t for t in trades if t["structure"]==s
             and 0.30 <= abs(t.get("delta_at_entry") or 0) < 0.50
             and t.get("exit_reason")==r]
        a = agg(g)
        if a:
            print(f"    {r:<20}{a[0]:>6}{a[1]:>7.1f}%{a[2]:>7.2f}{a[3]:>+8.1f}%")

print()
print("=" * 92)
print("3. R:R FLOOR -- credit/risk at entry vs outcome (all structures)")
print("=" * 92)
print(f"  {'credit/risk':<14}{'n':>7}{'win%':>8}{'L/W':>7}{'RoR':>9}")
print("  " + "-" * 46)
for lo, hi in ((0.0,0.20),(0.20,0.25),(0.25,0.35),(0.35,0.50),(0.50,2.0)):
    g = [t for t in trades
         if t.get("max_loss") and t.get("contracts")
         and lo <= (t["credit"]*100)/((t["max_loss"]/t["contracts"])) < hi]
    a = agg(g)
    if a:
        print(f"  {lo:.2f}-{hi:<9.2f}{a[0]:>7}{a[1]:>7.1f}%{a[2]:>7.2f}{a[3]:>+8.1f}%")
