"""Pool EVERY backtest result into one table and look for what we missed.

Rather than re-reading conclusions, this re-derives them from the stored trade
lists, so any claim below is recomputed from raw P&L rather than trusted.
"""
import pickle, glob, statistics
from collections import defaultdict

def load_all():
    rows = []
    for f in sorted(glob.glob("r*.pkl")):
        try:
            d = pickle.load(open(f, "rb"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            # results are stored variously as list, (list,metrics), (list,m,ror)
            tr = None
            if isinstance(v, list) and v and isinstance(v[0], dict):
                tr = v
            elif isinstance(v, tuple):
                for item in v:
                    if isinstance(item, list) and item and isinstance(item[0], dict):
                        tr = item; break
            if not tr or "net_pnl" not in tr[0]:
                continue
            rows.append((f, str(k), tr))
    return rows

def stats(tr):
    n = len(tr)
    w = [t["net_pnl"] for t in tr if t["net_pnl"] > 0]
    l = [t["net_pnl"] for t in tr if t["net_pnl"] <= 0]
    net = sum(t["net_pnl"] for t in tr)
    gp, gl = sum(w), -sum(l)
    cum = hi = dd = 0.0
    for t in sorted(tr, key=lambda x: x.get("exit_date") or ""):
        cum += t["net_pnl"]; hi = max(hi, cum); dd = max(dd, hi - cum)
    ror = (sum(t["net_pnl"]/t["max_loss"] for t in tr if t.get("max_loss"))/n) if n else 0
    yrs = {t["entry_date"][:4] for t in tr}
    return dict(n=n, win=100*len(w)/n if n else 0, net=net,
                pf=gp/gl if gl else 99, dd=dd, ror=100*ror,
                aw=sum(w)/len(w) if w else 0, al=sum(l)/len(l) if l else 0,
                lw=(abs(sum(l)/len(l))/(sum(w)/len(w))) if w and l else 0,
                year="/".join(sorted(yrs)))

rows = load_all()
print(f"pooled {len(rows)} distinct backtest configurations\n")

recs = [(f, k, stats(tr), tr) for f, k, tr in rows]

print("=" * 108)
print("EVERY PROFITABLE CONFIGURATION EVER PRODUCED, ranked by return-on-risk")
print("=" * 108)
print(f"{'config':<46}{'yr':<10}{'n':>5}{'win%':>7}{'net':>10}{'pf':>6}{'RoR':>7}{'L/W':>6}")
print("-" * 108)
pos = [r for r in recs if r[2]["net"] > 0 and r[2]["n"] >= 40]
for f, k, s, tr in sorted(pos, key=lambda r: -r[2]["ror"])[:22]:
    lab = (k[:44]) if len(k) > 44 else k
    print(f"{lab:<46}{s['year']:<10}{s['n']:>5}{s['win']:>7.1f}{s['net']:>+10,.0f}"
          f"{s['pf']:>6.2f}{s['ror']:>+6.1f}%{s['lw']:>6.2f}")
print(f"\n{len(pos)} of {len(recs)} configs were profitable with n>=40 "
      f"({100*len(pos)/len(recs):.0f}%)")
