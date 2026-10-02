import pickle
from collections import Counter, defaultdict
d = pickle.load(open('r_proposal.pkl','rb'))
order = ["2022Q1","2022Q2","2022Q3","2022Q4","2023Mar","2023Q2","2023Q4"]

print("THE PROPOSAL, ALL QUARTERS")
print("=" * 88)
print(f"{'quarter':<10}{'n':>5}{'win%':>7}{'net':>10}{'pf':>6}{'RoR':>8}{'L/W':>6}{'dd%':>7}")
print("-" * 88)
tot = []
for k in order:
    tr, m, ror, lw = d[k]
    tot += tr
    print(f"{k:<10}{m['n']:>5}{m['win']:>7.1f}{m['net']:>+10,.0f}{m['pf']:>6.2f}"
          f"{ror:>+7.1f}%{lw:>6.2f}{m['dd']:>6.1f}%")
w = [t['net_pnl'] for t in tot if t['net_pnl']>0]
l = [t['net_pnl'] for t in tot if t['net_pnl']<=0]
net = sum(t['net_pnl'] for t in tot)
gp, gl = sum(w), -sum(l)
ror = 100*sum(t['net_pnl']/t['max_loss'] for t in tot if t['max_loss'])/len(tot)
lw = abs(sum(l)/len(l))/(sum(w)/len(w))
print("-" * 88)
print(f"{'POOLED':<10}{len(tot):>5}{100*len(w)/len(tot):>7.1f}{net:>+10,.0f}"
      f"{gp/gl:>6.2f}{ror:>+7.1f}%{lw:>6.2f}")
print()
print(f"profitable quarters: {sum(1 for k in order if d[k][1]['net']>0)} of {len(order)}")
print()
print("WHY? The L/W ratio is 1.44 pooled -- the proposal targeted 0.9.")
print("=" * 88)
c = Counter(t['exit_reason'] for t in tot)
print("exit mix:")
for r, n in c.most_common():
    g = [t for t in tot if t['exit_reason']==r]
    rr = 100*sum(t['net_pnl']/t['max_loss'] for t in g if t['max_loss'])/len(g)
    ww = sum(1 for t in g if t['net_pnl']>0)
    print(f"  {str(r):<22}{n:>5} ({100*n/len(tot):>4.1f}%)  win {100*ww/len(g):>5.1f}%  RoR {rr:>+7.1f}%")
print()
print("EXPIRED is still 27.6% of trades despite exit_at_dte=3.")
print("Those are positions that could not be closed -- no quote on all four")
print("legs at 3, 2, 1 DTE. The mandatory exit is UNENFORCEABLE for a 4-leg")
print("structure in this data, which is exactly the risk flagged in section 7")
print("of the proposal. It is not a modelling choice; the quotes are absent.")
