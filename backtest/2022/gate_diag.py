import pickle
from collections import defaultdict
print('IS THE 2023 BEAR CALL ACTUALLY SAFE? Breach rate alone can mislead:')
print('a lower rate with a POSITIVE mean forward return means the market was')
print('drifting UP into the short calls - the losses are just further out.')
print('=' * 84)
for yr in (2022, 2023):
    recs = pickle.load(open(f'asym_gate_{yr}.pkl', 'rb'))
    bc = [r for r in recs if r['side'] == 'bear_call']
    print(f'\n{yr} bear calls (n={len(bc)}):')
    for th in (4, 6, 8, 10, 15):
        n = sum(1 for r in bc if r['adverse'] >= th)
        print(f'  adverse move >= {th:>2}%: {100*n/len(bc):>5.1f}%')
    up = sum(1 for r in bc if r['ret'] > 0)
    print(f'  underlying finished HIGHER: {100*up/len(bc):.1f}%  '
          f'(a short call wants this LOW)')
    # monthly breach rate
    mon = defaultdict(lambda: [0, 0])
    for r in bc:
        mon[r['date'][:7]][0] += r['breached']; mon[r['date'][:7]][1] += 1
    worst = sorted(mon.items(), key=lambda x: -x[1][0]/x[1][1])[:3]
    print('  worst months: ' + ', '.join(
        f"{m} {100*a/b:.0f}%" for m, (a, b) in worst))
