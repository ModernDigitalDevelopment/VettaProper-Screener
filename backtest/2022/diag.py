import pickle, statistics
d = pickle.load(open('r22_asym.pkl', 'rb'))
print('WHAT "NO DELTA PARAMETER" ACTUALLY BOUGHT')
print('=' * 78)
for k, lab in (('spec', 'no delta cap'), ('d25', 'delta 0.20-0.30')):
    tr, m, ror = d[k]
    w = [t['net_pnl'] for t in tr if t['net_pnl'] > 0]
    l = [t['net_pnl'] for t in tr if t['net_pnl'] <= 0]
    aw, al = sum(w)/len(w), abs(sum(l)/len(l))
    cr = statistics.median([t['credit'] for t in tr])
    ml = statistics.median([t['max_loss']/t['contracts'] for t in tr if t['contracts']])
    dl = statistics.median([t['delta_at_entry'] for t in tr if t.get('delta_at_entry')])
    ct = statistics.median([t['contracts'] for t in tr])
    print(f"{lab:<20} n={m['n']:>4} win={m['win']:>5.1f}% net={m['net']:>+9,.0f} "
          f"pf={m['pf']:.2f} dd={m['dd']:.1f}%")
    print(f"{'':20} med delta {dl:.3f}  med credit ${cr:.2f}  "
          f"med risk/ct ${ml:.0f}  med contracts {ct:.0f}")
    print(f"{'':20} avg win {aw:>+8,.0f}  avg loss {-al:>+8,.0f}  ratio {al/aw:.2f}x")
    print()
