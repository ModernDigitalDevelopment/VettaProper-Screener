import json, datetime as dt, time as _t, urllib.request
import pandas as pd, numpy as np

v=pd.read_csv('vvix.csv'); v['date']=pd.to_datetime(v['DATE'],format='%m/%d/%Y')
v=v.rename(columns={'VVIX':'vvix'})[['date','vvix']].sort_values('date')
v=v[v['vvix']>20].reset_index(drop=True)

def yh(sym):
    UA={'User-Agent':'Mozilla/5.0'}
    p1=int(dt.datetime(2003,1,1).timestamp()); p2=int(_t.time())
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d'
    d=json.loads(urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=30).read())
    r=d['chart']['result'][0]
    ts=r['timestamp']; cl=r['indicators']['quote'][0]['close']
    ac=r['indicators'].get('adjclose')
    ser=ac[0]['adjclose'] if (ac and ac[0] and ac[0].get('adjclose')) else cl
    idx=pd.to_datetime(ts,unit='s').tz_localize(None).normalize()
    return pd.Series(ser,index=idx,name=sym).dropna()

spx=yh('%5EGSPC'); spy=yh('SPY')
print('SPY div-adjusted:', spy is not None, '| SPX pts:', round(spx.iloc[-1],0))
mkt=spy.pct_change()

adv=pd.read_csv('NYSE_advn.csv',header=None,names=['date','adv']); adv['date']=pd.to_datetime(adv['date'],format='%Y%m%d')
dec=pd.read_csv('NYSE_decln.csv',header=None,names=['date','dec']); dec['date']=pd.to_datetime(dec['date'],format='%Y%m%d')
real=adv.merge(dec,on='date').set_index('date').sort_index()
real_line=(real['adv']-real['dec']).cumsum()
recon=pd.read_csv('ad_recon.csv'); recon['date']=pd.to_datetime(recon['date'],format='%Y%m%d'); recon=recon.set_index('date').sort_index()
ad=pd.concat([real_line, real_line.iloc[-1]+(recon['adv']-recon['dec']).cumsum()])
print(f"A/D real: {real_line.index[0].date()} -> {real_line.index[-1].date()} | recon: {recon.index[0].date()} -> {recon.index[-1].date()} (adv {recon['adv'].mean():.0f}/dec {recon['dec'].mean():.0f}/day)")

df=pd.DataFrame({'spx':spx,'ad':ad,'mkt':mkt})
df=df[~df.index.duplicated(keep='first')].sort_index().dropna(subset=['spx'])
df['vvix']=v.set_index('date')['vvix'].reindex(df.index).ffill(limit=5)
df=df.dropna(subset=['vvix']); df['mkt']=df['mkt'].fillna(0)
print('panel:',df.index[0].date(),'->',df.index[-1].date(),'|',len(df),'days | VVIX max',round(df['vvix'].max(),1),'on',df['vvix'].idxmax().date())

def run(pct,w,reentry,mode,K=10):
    p=df['vvix'].rolling(504,min_periods=252).apply(lambda x:(x[-1]>=x).mean(),raw=True)
    stress=p>=pct if mode!='ad_only' else pd.Series(False,index=df.index)
    sh=df['spx']>=df['spx'].rolling(w,min_periods=w//2).max()-df['spx'].max()*1e-4
    ah=df['ad']>=df['ad'].rolling(w,min_periods=w//2).max()
    armed=(sh&~ah).rolling(K+1,min_periods=1).max().astype(bool) if mode!='vvix_only' else pd.Series(True,index=df.index)
    exit_sig=armed if mode=='ad_only' else (stress if mode=='vvix_only' else stress&armed)
    in_mkt=True; states=[]
    for i in range(len(df)):
        if in_mkt and bool(exit_sig.iloc[i]): in_mkt=False
        elif not in_mkt:
            trig={'either':(p.iloc[i]<=0.5) or bool(ah.iloc[i]),'vvix':p.iloc[i]<=0.5,'ad':bool(ah.iloc[i])}[reentry]
            if trig: in_mkt=True
        states.append(1.0 if in_mkt else 0.0)
    pos=pd.Series(states,index=df.index)
    strat=pos.shift(1)*df['mkt']
    def stats(r):
        eq=(1+r).cumprod(); yrs=(r.index[-1]-r.index[0]).days/365.25
        cagr=eq.iloc[-1]**(1/yrs)-1; vol=r.std()*np.sqrt(252)
        return cagr,vol,(cagr/vol if vol>0 else 0),(eq/eq.cummax()-1).min(),eq.iloc[-1]
    s1,s2=stats(strat),stats(df['mkt'])
    return dict(mode=mode,pct=pct,w=w,reentry=reentry,cagr=s1[0],sharpe=s1[2],maxdd=s1[3],final100k=s1[4]*100,
                exposure=pos.mean(),switches=int((pos.diff().abs()>0).sum()),
                bh_cagr=s2[0],bh_sharpe=s2[2],bh_maxdd=s2[3],bh_final100k=s2[4]*100),pos,strat

rows=[]
for mode,grid in [('confluence',[(p,w,r) for p in [0.85,0.90,0.95] for w in [60,120] for r in ['either','vvix']]),
                  ('ad_only',[(0.5,w,'either') for w in [60,120]]),
                  ('vvix_only',[(p,60,r) for p in [0.85,0.90,0.95] for r in ['either','vvix']])]:
    for g in grid: rows.append(run(*g,mode=mode))
res=pd.DataFrame([r[0] for r in rows]); res.to_csv('results.csv',index=False)
pd.set_option('display.width',250)
print(res[['mode','pct','w','reentry','cagr','sharpe','maxdd','final100k','exposure','switches','bh_cagr','bh_maxdd','bh_final100k']].to_string(index=False,float_format=lambda x:f'{x:.2f}'))

best=res[res['mode']=='confluence'].sort_values('sharpe',ascending=False).iloc[0]
print('\nBEST CONFLUENCE:',best['pct'],int(best['w']),best['reentry'])
rr=[r for r in rows if r[0]['mode']=='confluence' and r[0]['pct']==best['pct'] and r[0]['w']==best['w'] and r[0]['reentry']==best['reentry']][0]
pos,strat=rr[1],rr[2]
pd.DataFrame({'pos':pos,'strat':strat,'mkt':df['mkt']}).to_csv('equity.csv')

# episodes out of market
flat=pos==0; eps=[]; start=None
for d,f in flat.items():
    if f and start is None: start=d
    if (not f) and start is not None:
        seg=df.loc[start:d,'mkt']; eps.append((start.date(),d.date(),len(seg),(1+seg).prod()-1)); start=None
if start is not None:
    seg=df.loc[start:,'mkt']; eps.append((start.date(),df.index[-1].date(),len(seg),(1+seg).prod()-1))
eps=pd.DataFrame(eps,columns=['out_start','back_in','days_flat','mkt_ret_while_flat']).sort_values('mkt_ret_while_flat')
print('\n=== de-risk episodes ==='); print(eps.to_string(index=False,float_format=lambda x:f'{x:.1%}'))
print('episodes:',len(eps),'| flat periods with positive mkt return:',int((eps['mkt_ret_while_flat']>0).sum()))

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
eqs=(1+strat).cumprod(); eqb=(1+df['mkt']).cumprod()
fig,ax=plt.subplots(figsize=(12,6))
ax.plot(eqs.index,eqs.values,lw=1.5,label=f'Confluence (VVIX p{int(best["pct"]*100)}, {int(best["w"])}d div, re-entry: {best["reentry"]})')
ax.plot(eqb.index,eqb.values,lw=1.4,alpha=0.85,label='Buy & hold SPY (total return)')
ax.set_yscale('log'); ax.legend(); ax.grid(alpha=0.3)
ax.set_title('VVIX + NYSE A/D confluence vs buy-and-hold, 2006-2026')
fig.tight_layout(); fig.savefig('equity.png',dpi=110); print('chart saved')
