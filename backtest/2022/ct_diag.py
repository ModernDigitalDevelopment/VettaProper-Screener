import pickle
from collections import defaultdict
d = pickle.load(open('r_condor_tune.pkl', 'rb'))
g23 = pickle.load(open('r_condor_2023.pkl', 'rb'))

print('WAS 10DTE/d0.40 REALLY A WINNER IN BOTH YEARS?')
print('=' * 78)
print('The grid figures that prompted this were FULL-PERIOD:')
print('  2023 (Mar+Q2+Q4) 10DTE d0.40 block : +$61,908  pf 1.33')
print('  2022 matched      10DTE d0.40 block : +$20,488  pf 1.10')
print()
print('But Q2 in isolation, with the SAME 1/sector + 2 DTE settings:')
for y in (2022, 2023):
    t, m, r = d[f'{y}_1sec']
    print(f'  Q2 {y} 1/sector : {m["net"]:>+9,.0f}  pf {m["pf"]:.2f}  win {m["win"]:.1f}%')
print()
print('-> 2022 Q2 alone is deeply negative. The +$20,488 full-period figure')
print('   came from OTHER quarters, not Q2. A single-quarter test cannot')
print('   confirm a full-period result.')
print()
print('SQUEEZE VERDICT')
print('=' * 78)
for y in (2022, 2023):
    b, mb, _ = d[f'{y}_base']
    s, ms, _ = d[f'{y}_sq']
    print(f'  {y}: base n={mb["n"]:>4} {mb["net"]:>+9,.0f} pf {mb["pf"]:.2f}  ->  '
          f'squeeze n={ms["n"]:>3} {ms["net"]:>+9,.0f} pf {ms["pf"]:.2f}')
print()
print('  The squeeze filter LOST money in both years and cut sample size')
print('  by 38% (2022) and 75% (2023). The 6.5pp bull-put separation did')
print('  not transfer to condors.')
print()
print('CHANGES YOU ASKED FOR, isolated on Q2 2023 (the profitable quarter)')
print('=' * 78)
base = d['2023_base'][1]
for k, lab in (('2023_1sec', '1/sector instead of 2'),
               ('2023_2dte', 'exit 2 DTE instead of 1'),
               ('2023_noblk', 'no event block')):
    m = d[k][1]
    print(f'  {lab:<28} {m["net"]:>+9,.0f}  vs tuned {base["net"]:>+9,.0f}  '
          f'({m["net"]-base["net"]:>+9,.0f})')
