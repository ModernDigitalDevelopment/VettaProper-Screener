import pickle, statistics
from collections import defaultdict
d = pickle.load(open('r23_asym.pkl', 'rb'))

print('LIKE-FOR-LIKE: same months (Mar+Q2+Q4), same frozen spec')
print('=' * 86)
print(f"{'arm':<22}{'2022':>28}{'2023':>28}")
print('-' * 86)
for tag, lab in (('nocap', 'no delta cap'), ('d25', 'delta 0.20-0.30')):
    a, b = d[f'22_{tag}'], d[f'23_{tag}']
    print(f"{lab:<22}"
          f"{a[1]['net']:>+12,.0f} pf{a[1]['pf']:>5.2f} w{a[1]['win']:>5.1f}%"
          f"{b[1]['net']:>+12,.0f} pf{b[1]['pf']:>5.2f} w{b[1]['win']:>5.1f}%")
print()
print('THE SIDE MIX IS THE WHOLE STORY')
print('=' * 86)
for k, lab in (('22_nocap', '2022 asym'), ('23_nocap', '2023 asym'),
               ('23_put', '2023 always PUT'), ('23_call', '2023 always CALL')):
    tr = d[k][0]
    bp = [t for t in tr if t['structure'] == 'bull_put']
    bc = [t for t in tr if t['structure'] == 'bear_call']
    print(f"{lab:<20} puts n={len(bp):>4} {sum(t['net_pnl'] for t in bp):>+9,.0f}   "
          f"calls n={len(bc):>4} {sum(t['net_pnl'] for t in bc):>+9,.0f}")
print()
print('The 2023 gate put 95% of its risk on the CALL side (286 of 302) in a')
print('year when calls lost -$58,052 and puts made +$51,549. It picked')
print('almost exactly the wrong side, all year.')
print()
print('MONTHLY, 2023 asym vs always-put')
print('=' * 86)
for k, lab in (('23_nocap', 'asym'), ('23_put', 'always put')):
    mon = defaultdict(float)
    for t in d[k][0]:
        mon[t['exit_date'][:7]] += t['net_pnl']
    print(f"  {lab:<12} " + '  '.join(f"{m[5:]}:{mon[m]:>+8,.0f}" for m in sorted(mon)))
