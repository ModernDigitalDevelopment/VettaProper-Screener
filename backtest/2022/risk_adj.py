"""Risk-adjusted comparison. Net P&L alone is misleading when the two
configurations run very different drawdowns.

Key question: at a position size that equalises risk, which wins?
Since sizing scales P&L linearly and does not change expectancy, scale each
config to the SAME peak drawdown and compare the resulting net.
"""
import pickle
d = pickle.load(open('r22_asym_oos.pkl', 'rb'))

rows = []
for tag, lab in (('', 'no delta cap (d~0.49)'), ('_d25', 'delta 0.20-0.30')):
    allt = []
    for q in ('q1', 'q2', 'q3', 'q4'):
        allt += d[q + tag][0]
    net = sum(t['net_pnl'] for t in allt)
    cum = hi = dd = 0.0
    for t in sorted(allt, key=lambda x: x['exit_date']):
        cum += t['net_pnl']; hi = max(hi, cum); dd = max(dd, hi - cum)
    rows.append((lab, len(allt), net, dd))

TARGET = 10_000.0     # equalise to a $10k max drawdown on $50k
print('RISK-EQUALISED COMPARISON  (both scaled to a $10,000 max drawdown)')
print('=' * 78)
print(f"{'config':<24}{'n':>5}{'raw net':>11}{'raw dd':>10}{'scale':>8}{'net @ equal risk':>18}")
print('-' * 78)
for lab, n, net, dd in rows:
    s = TARGET / dd if dd else 0
    print(f"{lab:<24}{n:>5}{net:>+11,.0f}{dd:>10,.0f}{s:>8.2f}{net*s:>+18,.0f}")
print()
print('Return per unit of drawdown (higher is better):')
for lab, n, net, dd in rows:
    print(f"  {lab:<24} {net/dd:>6.2f}")
