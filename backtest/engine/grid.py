import spec_engine as S, dbs, pickle, json, statistics, random, itertools, csv
from concurrent.futures import ProcessPoolExecutor
QS=("mar2023","q2_2023","q4_2023")
BASE=dict(structure='bull_put',short_delta=0.25,delta_tol=0.05,
          earnings_blackout_days=14,target_dte=9,dte_tol=2,
          max_rel_spread=0.10,hold_to_expiry=False)

def init():
    S.SIGNALS=pickle.load(open('signals.pkl','rb'))
    S.SECTORS=json.load(open('sectors.json'))
    S.TREND=pickle.load(open('trend2.pkl','rb'))
    S.EVENTS=pickle.load(open('events.pkl','rb'))
    S.VIX=pickle.load(open('vix.pkl','rb'))

def run_one(args):
    init()
    label,kw=args
    per={}
    for q in QS: per[q]=S.run(dbs.DBS[q],S.Spec(label=label,**{**BASE,**kw}))
    allt=sum(per.values(),[])
    if not allt: return dict(label=label,n=0,**kw)
    p=[t['net_pnl'] for t in allt]; w=[x for x in p if x>0]; l=[x for x in p if x<=0]
    eq=0;pk=0;dd=0
    for x in sorted(allt,key=lambda z:z['exit_date']):
        eq+=x['net_pnl']; pk=max(pk,eq); dd=max(dd,pk-eq)
    # peak concurrent risk
    ev=[]
    for t in allt:
        ev.append((t['entry_date'],t['max_loss'])); ev.append((t['exit_date'],-t['max_loss']))
    ev.sort(); cur=0; peak=0
    for _,m in ev:
        cur+=m; peak=max(peak,cur)
    random.seed(11)
    bs=sorted(sum(random.choice(p) for _ in range(len(p)))/len(p) for _ in range(4000))
    return dict(label=label,n=len(p),win=round(len(w)/len(p)*100,1),
        exp=round(sum(p)/len(p),2),net=round(sum(p)),
        pf=round(sum(w)/abs(sum(l)),2) if l else 999,
        dd=round(dd), dd_pct=round(dd/50000*100,1),
        peak_risk_pct=round(peak/50000*100),
        allq=all(sum(x['net_pnl'] for x in per[q])>0 for q in QS if per[q]),
        p_le0=round(sum(1 for x in bs if x<=0)/len(bs)*100,1),
        worst=round(min(p)), **kw)

jobs=[]
for tm in ('s10_50','s10_30','below50','none'):
  for rr in (0.0,0.20):
    for pct in (0.05,0.075,0.10):
      for ps in (1,2):
        for ex in ('thu','tp80','both'):
          kw=dict(trend_mode=tm,min_risk_reward=rr,max_pct_per_position=pct,max_per_sector=ps)
          if ex=='thu':   kw.update(profit_target=0.999, exit_days_before_expiry=1)
          elif ex=='tp80':kw.update(profit_target=0.80,  exit_days_before_expiry=0)
          else:           kw.update(profit_target=0.80,  exit_days_before_expiry=1)
          lbl=f"{tm}|rr{rr}|{int(pct*1000)/10:.1f}%|{ps}sec|{ex}"
          jobs.append((lbl,kw))
print(f"running {len(jobs)} configurations x 3 quarters...\n",flush=True)
res=[]
with ProcessPoolExecutor(max_workers=6) as ex:
    for i,r in enumerate(ex.map(run_one,jobs),1):
        res.append(r)
        if i%12==0: print(f"  {i}/{len(jobs)}",flush=True)
res=[r for r in res if r.get('n')]
cols=['label','n','win','exp','net','pf','dd_pct','peak_risk_pct','allq','p_le0','worst',
      'trend_mode','min_risk_reward','max_pct_per_position','max_per_sector','profit_target','exit_days_before_expiry']
with open('grid_results.csv','w',newline='') as f:
    wtr=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore'); wtr.writeheader()
    for r in sorted(res,key=lambda x:-x['exp']): wtr.writerow(r)
print(f"\nwrote grid_results.csv ({len(res)} rows)")
