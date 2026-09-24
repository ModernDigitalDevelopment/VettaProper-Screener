"""Does 100% midpoint filling change the conclusion?"""
import json, pickle
from concurrent.futures import ProcessPoolExecutor
import spec_engine as E
from dbs import DBS

BASE=dict(structure='bull_put',short_delta=0.30,delta_tol=0.20,
          trend_mode='s10_50',min_ivrv=0.0,
          earnings_blackout_days=12,blackout_exdiv=True,
          target_dte=9,dte_tol=2,max_rel_spread=0.10,
          max_pct_per_position=0.05,max_per_sector=1,max_open=12,
          max_new_per_day=4,profit_target=0.80,exit_days_before_expiry=0,
          hold_to_expiry=False,min_risk_reward=0.20,rank_mode='score')

def load():
    E.SIGNALS.update(pickle.load(open("signals.pkl","rb")))
    E.TREND.update(pickle.load(open("trend2.pkl","rb")))
    E.EVENTS.update(pickle.load(open("events.pkl","rb")))
    E.VIX.update(pickle.load(open("vix.pkl","rb")))
    E.SECTORS.update(json.load(open("sectors.json")))

def one(args):
    lab,p=args
    load()
    spec=E.Spec(label=lab, mid_fill_prob=p, **BASE)
    tr=[]
    for db in DBS.values(): tr+=E.run(db,spec)
    return lab,tr

if __name__=="__main__":
    jobs=[(f"mid={p:.2f}",p) for p in (1.00,0.95,0.80,0.50,0.00)]
    out={}
    with ProcessPoolExecutor(max_workers=5) as ex:
        for lab,tr in ex.map(one,jobs):
            out[lab]=tr
            net=sum(t['net_pnl'] for t in tr)
            w=[t for t in tr if t['net_pnl']>0]
            gp=sum(t['net_pnl'] for t in w); gl=-sum(t['net_pnl'] for t in tr if t['net_pnl']<=0)
            print(f"{lab:<10} n={len(tr):>4} win={100*len(w)/len(tr):>5.1f}% net=${net:>8,.0f} PF={gp/gl if gl>0 else 99:>5.2f}")
    pickle.dump(out,open("midfill_runs.pkl","wb"))
