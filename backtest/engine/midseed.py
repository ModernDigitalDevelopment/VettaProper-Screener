"""Separate fill-quality signal from RNG noise using multiple seeds."""
import json, pickle, statistics
from concurrent.futures import ProcessPoolExecutor
import spec_engine as E
from dbs import DBS
from midtest import BASE, load

def one(args):
    p,seed=args
    load()
    spec=E.Spec(label=f"p{p}s{seed}", mid_fill_prob=p, seed=seed, **BASE)
    tr=[]
    for db in DBS.values(): tr+=E.run(db,spec)
    net=sum(t['net_pnl'] for t in tr)
    w=sum(1 for t in tr if t['net_pnl']>0)
    return p,seed,len(tr),100*w/len(tr) if tr else 0,net

if __name__=="__main__":
    jobs=[(p,s) for p in (1.00,0.95,0.50,0.00) for s in (7,11,23,42,99)]
    res={}
    with ProcessPoolExecutor(max_workers=6) as ex:
        for p,s,n,win,net in ex.map(one,jobs):
            res.setdefault(p,[]).append(net)
    print("NET P&L ACROSS 5 SEEDS (isolating fill quality from RNG noise)")
    print("="*78)
    print(f"{'mid fill %':<12}{'mean':>11}{'median':>11}{'min':>11}{'max':>11}{'spread':>12}")
    print("-"*78)
    for p in sorted(res,reverse=True):
        v=res[p]
        print(f"{p*100:>7.0f}%    ${statistics.mean(v):>10,.0f}${statistics.median(v):>10,.0f}"
              f"${min(v):>10,.0f}${max(v):>10,.0f}${max(v)-min(v):>11,.0f}")
    json.dump({str(k):v for k,v in res.items()},open("midseed.json","w"),indent=1)
