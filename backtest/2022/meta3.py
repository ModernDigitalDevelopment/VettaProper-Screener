"""Is the L/W ratio causal, and what drives it? Pool trades, not configs."""
import pickle, glob, statistics
from collections import defaultdict
exec(open("meta.py").read().split("rows = load_all()")[0])

rows = load_all()
# pool every unique TRADE ever simulated, deduped
seen = {}
for f, k, tr in rows:
    for t in tr:
        key = (t["symbol"], t["entry_date"], t.get("expiration"),
               t["structure"], round(t.get("width", 0), 2),
               round(t.get("credit", 0), 3))
        if key not in seen:
            seen[key] = t
trades = list(seen.values())
print(f"pooled {len(trades):,} UNIQUE simulated trades "
      f"(from {sum(len(t) for _,_,t in rows):,} rows across 180 configs)\n")

def band(v, edges):
    for i in range(len(edges)-1):
        if edges[i] <= v < edges[i+1]:
            return f"{edges[i]}-{edges[i+1]}"
    return None

print("=" * 96)
print("WHAT DRIVES THE LOSS/WIN RATIO? per-trade, all structures pooled")
print("=" * 96)

# by delta
print("\nBy short delta at entry:")
print(f"  {'delta':<12}{'n':>7}{'win%':>8}{'avg win':>10}{'avg loss':>10}{'L/W':>7}{'mean RoR':>10}")
print("  " + "-" * 62)
for lo, hi in ((0.10,0.20),(0.20,0.25),(0.25,0.30),(0.30,0.40),(0.40,0.50),(0.50,0.70)):
    g = [t for t in trades if lo <= abs(t.get("delta_at_entry") or 0) < hi]
    if len(g) < 60: continue
    w = [t["net_pnl"] for t in g if t["net_pnl"] > 0]
    l = [t["net_pnl"] for t in g if t["net_pnl"] <= 0]
    if not w or not l: continue
    aw, al = sum(w)/len(w), abs(sum(l)/len(l))
    ror = 100*sum(t["net_pnl"]/t["max_loss"] for t in g if t.get("max_loss"))/len(g)
    print(f"  {lo:.2f}-{hi:<7.2f}{len(g):>7}{100*len(w)/len(g):>7.1f}%"
          f"{aw:>+10,.0f}{-al:>+10,.0f}{al/aw:>7.2f}{ror:>+9.1f}%")

# by exit reason -- the real lever
print("\nBy exit reason:")
print(f"  {'reason':<22}{'n':>7}{'win%':>8}{'avg win':>10}{'avg loss':>10}{'L/W':>7}{'mean RoR':>10}")
print("  " + "-" * 72)
by = defaultdict(list)
for t in trades:
    by[t.get("exit_reason") or "?"].append(t)
for r, g in sorted(by.items(), key=lambda x: -len(x[1])):
    if len(g) < 60: continue
    w = [t["net_pnl"] for t in g if t["net_pnl"] > 0]
    l = [t["net_pnl"] for t in g if t["net_pnl"] <= 0]
    if not w or not l: continue
    aw, al = sum(w)/len(w), abs(sum(l)/len(l))
    ror = 100*sum(t["net_pnl"]/t["max_loss"] for t in g if t.get("max_loss"))/len(g)
    print(f"  {r:<22}{len(g):>7}{100*len(w)/len(g):>7.1f}%"
          f"{aw:>+10,.0f}{-al:>+10,.0f}{al/aw:>7.2f}{ror:>+9.1f}%")

# by structure
print("\nBy structure:")
print(f"  {'structure':<16}{'n':>7}{'win%':>8}{'L/W':>7}{'mean RoR':>10}")
print("  " + "-" * 48)
for s in ("bull_put", "bear_call", "iron_condor"):
    g = [t for t in trades if t["structure"] == s]
    if len(g) < 60: continue
    w = [t["net_pnl"] for t in g if t["net_pnl"] > 0]
    l = [t["net_pnl"] for t in g if t["net_pnl"] <= 0]
    aw, al = sum(w)/len(w), abs(sum(l)/len(l))
    ror = 100*sum(t["net_pnl"]/t["max_loss"] for t in g if t.get("max_loss"))/len(g)
    print(f"  {s:<16}{len(g):>7}{100*len(w)/len(g):>7.1f}%{al/aw:>7.2f}{ror:>+9.1f}%")
