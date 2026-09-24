"""Full backtest with ADX/RSI gates. 100% mid fills (deterministic)."""
import json, pickle
from concurrent.futures import ProcessPoolExecutor
import spec_engine as E
from dbs import DBS
from midtest import BASE

def load():
    E.SIGNALS.update(pickle.load(open("signals.pkl","rb")))
    E.TREND.update(pickle.load(open("trend2.pkl","rb")))
    E.EVENTS.update(pickle.load(open("events.pkl","rb")))
    E.VIX.update(pickle.load(open("vix.pkl","rb")))
    E.SECTORS.update(json.load(open("sectors.json")))
    E.INDICATORS.update(pickle.load(open("indicators_slim.pkl","rb")))

def one(args):
    lab,ov=args
    load()
    kw=dict(BASE); kw.update(ov)
    spec=E.Spec(label=lab, mid_fill_prob=1.00, **kw)
    tr=[]
    for db in DBS.values(): tr+=E.run(db,spec)
    return lab,tr

def met(tr,eq=50000.0):
    if not tr: return None
    n=len(tr); net=sum(t['net_pnl'] for t in tr)
    w=[t for t in tr if t['net_pnl']>0]
    gp=sum(t['net_pnl'] for t in w); gl=-sum(t['net_pnl'] for t in tr if t['net_pnl']<=0)
    cum=hi=dd=0
    for t in sorted(tr,key=lambda x:x['exit_date']):
        cum+=t['net_pnl']; hi=max(hi,cum); dd=max(dd,hi-cum)
    ev=[]
    for t in tr: ev.append((t['entry_date'],t['max_loss'])); ev.append((t['exit_date'],-t['max_loss']))
    ev.sort(); c=pk=0
    for _,v in ev: c+=v; pk=max(pk,c)
    return dict(n=n,win=round(100*len(w)/n,1),net=round(net),pf=round(gp/gl if gl>0 else 99,2),
                dd=round(100*dd/eq,1),peak=round(100*pk/eq),worst=round(min(t['net_pnl'] for t in tr)))

VARIANTS=[
 ("baseline (SMA only)",            {}),
 ("+ADX>=20",                       dict(min_adx=20)),
 ("+RSI 60-80",                     dict(rsi_lo=60,rsi_hi=80)),
 ("+ADX>=20 +RSI 60-80",            dict(min_adx=20,rsi_lo=60,rsi_hi=80)),
 ("+ADX>=25 +RSI 60-80",            dict(min_adx=25,rsi_lo=60,rsi_hi=80)),
 ("+ADX>=30 +RSI 60-80",            dict(min_adx=30,rsi_lo=60,rsi_hi=80)),
 ("+ADX>=20 +RSI 55-80",            dict(min_adx=20,rsi_lo=55,rsi_hi=80)),
 ("+ADX>=20+RSI60-80, 2/sector",    dict(min_adx=20,rsi_lo=60,rsi_hi=80,max_per_sector=2)),
]

if __name__=="__main__":
    out={}
    print(f"{'config':<34}{'n':>5}{'win%':>7}{'net':>11}{'PF':>6}{'maxDD%':>9}{'peak%':>7}{'worst':>9}")
    print("-"*88)
    with ProcessPoolExecutor(max_workers=2) as ex:
        for lab,tr in ex.map(one,VARIANTS):
            out[lab]=tr; m=met(tr)
            print(f"{lab:<34}{m['n']:>5}{m['win']:>7}${m['net']:>10,}{m['pf']:>6}{m['dd']:>9}{m['peak']:>7}${m['worst']:>8,}")
    pickle.dump(out,open("indicator_runs.pkl","wb"))
