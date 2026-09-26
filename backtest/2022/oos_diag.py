import pickle, statistics
from collections import defaultdict
d = pickle.load(open('r22_asym_oos.pkl', 'rb'))

print('FULL-YEAR 2022, FROZEN SPEC')
print('=' * 84)
for tag, lab in (('', 'no delta cap'), ('_d25', 'delta 0.20-0.30')):
    allt = []
    for q in ('q1','q2','q3','q4'):
        allt += d[q + tag][0]
    w = [t['net_pnl'] for t in allt if t['net_pnl'] > 0]
    l = [t['net_pnl'] for t in allt if t['net_pnl'] <= 0]
    net = sum(t['net_pnl'] for t in allt)
    gp, gl = sum(w), -sum(l)
    # drawdown on the concatenated year
    cum = hi = dd = 0.0
    for t in sorted(allt, key=lambda x: x['exit_date']):
        cum += t['net_pnl']; hi = max(hi, cum); dd = max(dd, hi - cum)
    ror = 100*sum(t['net_pnl']/t['max_loss'] for t in allt if t['max_loss'])/len(allt)
    print(f"{lab:<18} n={len(allt):>4} win={100*len(w)/len(allt):>5.1f}% "
          f"net={net:>+9,.0f} pf={gp/gl:>4.2f} ror={ror:>+6.2f}% dd={100*dd/50000:>5.1f}%")
    print(f"{'':18} avg win {sum(w)/len(w):>+8,.0f}  avg loss {sum(l)/len(l):>+8,.0f}  "
          f"ratio {abs(sum(l)/len(l))/(sum(w)/len(w)):.2f}x")
    print(f"{'':18} quarters profitable: "
          f"{sum(1 for q in ('q1','q2','q3','q4') if sum(t['net_pnl'] for t in d[q+tag][0]) > 0)} of 4")
    print()

print('QUARTERLY CONSISTENCY -- the discriminating test')
print('=' * 84)
print(f"{'quarter':<10}{'no-cap net':>13}{'no-cap dd':>11}{'capped net':>13}{'capped dd':>11}")
print('-' * 84)
for q in ('q1','q2','q3','q4'):
    a, b = d[q][1], d[q+'_d25'][1]
    print(f"{q.upper():<10}{a['net']:>+13,.0f}{a['dd']:>10.1f}%"
          f"{b['net']:>+13,.0f}{b['dd']:>10.1f}%")

print()
print('Q4 MONTHLY BREAKDOWN -- where the rally hit')
print('=' * 84)
for tag, lab in (('', 'no-cap'), ('_d25', 'capped')):
    mon = defaultdict(float); cnt = defaultdict(int)
    for t in d['q4'+tag][0]:
        mon[t['entry_date'][:7]] += t['net_pnl']; cnt[t['entry_date'][:7]] += 1
    s = '  '.join(f"{m[5:]}: {mon[m]:>+8,.0f} (n={cnt[m]})" for m in sorted(mon))
    print(f"  {lab:<8} {s}")
