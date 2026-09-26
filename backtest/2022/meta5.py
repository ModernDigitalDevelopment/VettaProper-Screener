"""Does the 'condor + delta 0.30-0.50 + EOD exit' rule hold in BOTH years
separately? Split the pooled trades by year -- no config-level cherry-picking.
"""
import pickle, glob
from collections import defaultdict
exec(open("meta.py").read().split("rows = load_all()")[0])
rows = load_all(); seen = {}
for f, k, tr in rows:
    for t in tr:
        seen.setdefault((t["symbol"], t["entry_date"], t.get("expiration"),
                         t["structure"], round(t.get("width",0),2),
                         round(t.get("credit",0),3)), t)
trades = list(seen.values())

def agg(g, minn=30):
    if len(g) < minn: return None
    w = [t["net_pnl"] for t in g if t["net_pnl"] > 0]
    l = [t["net_pnl"] for t in g if t["net_pnl"] <= 0]
    if not w or not l: return None
    aw, al = sum(w)/len(w), abs(sum(l)/len(l))
    ror = 100*sum(t["net_pnl"]/t["max_loss"] for t in g if t.get("max_loss"))/len(g)
    return len(g), 100*len(w)/len(g), al/aw, ror, sum(t["net_pnl"] for t in g)

print("=" * 98)
print("YEAR-BY-YEAR VALIDATION of the pooled finding")
print("=" * 98)
print(f"{'rule':<44}{'year':>6}{'n':>6}{'win%':>8}{'L/W':>7}{'RoR':>9}")
print("-" * 98)

rules = [
  ("condor, d0.30-0.50, EOD exit (no expiry)",
   lambda t: t["structure"]=="iron_condor"
             and 0.30 <= abs(t.get("delta_at_entry") or 0) < 0.50
             and (t.get("exit_reason") or "").startswith(("EOD_EXIT","TAKE_PROFIT","FORCE"))),
  ("condor, d0.30-0.50, held to EXPIRY",
   lambda t: t["structure"]=="iron_condor"
             and 0.30 <= abs(t.get("delta_at_entry") or 0) < 0.50
             and t.get("exit_reason")=="EXPIRED"),
  ("vertical, d0.20-0.30 (the original spec)",
   lambda t: t["structure"] in ("bull_put","bear_call")
             and 0.20 <= abs(t.get("delta_at_entry") or 0) < 0.30),
  ("vertical, d0.40-0.50",
   lambda t: t["structure"] in ("bull_put","bear_call")
             and 0.40 <= abs(t.get("delta_at_entry") or 0) < 0.50),
]
for lab, f in rules:
    for yr in ("2022", "2023"):
        g = [t for t in trades if t["entry_date"].startswith(yr) and f(t)]
        a = agg(g)
        if a:
            print(f"{lab:<44}{yr:>6}{a[0]:>6}{a[1]:>7.1f}%{a[2]:>7.2f}{a[3]:>+8.1f}%")
    print()

print("=" * 98)
print("THE CRITICAL TEST: is the condor rule positive in BOTH years?")
print("=" * 98)
f = rules[0][1]
both = True
for yr in ("2022", "2023"):
    g = [t for t in trades if t["entry_date"].startswith(yr) and f(t)]
    a = agg(g)
    if a:
        ok = a[3] > 0
        both &= ok
        print(f"  {yr}: n={a[0]:>4} win={a[1]:.1f}% L/W={a[2]:.2f} "
              f"RoR={a[3]:+.1f}%  {'PASS' if ok else 'FAIL'}")
print(f"\n  -> {'CONSISTENT ACROSS BOTH YEARS' if both else 'NOT consistent'}")
