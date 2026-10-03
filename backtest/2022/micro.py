import json, datetime as dt, time as _t, urllib.request, itertools
import pandas as pd, numpy as np
v=pd.read_csv('vvix.csv'); v['date']=pd.to_datetime(v['DATE'],format='%m/%d/%Y')
v=v.rename(columns={'VVIX':'vvix'})[['date','vvix']].sort_values('date'); v=v[v['vvix']>20]
def yh(sym):
    p1=int(dt.datetime(2003,1,1).timestamp()); p2=int(_t.time())
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d'
    d=json.loads(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read())
    r=d['chart']['result'][0]; cl=r['indicators']['quote'][0]['close']; ac=r['indicators'].get('adjclose')
    ser=ac[0]['adjclose'] if (ac and ac[0] and ac[0].get('adjclose')) else cl
    return pd.Series(ser,index=pd.to_datetime(r['timestamp'],unit='s').tz_localize(None).normalize()).dropna()
spx=yh('%5EGSPC'); spy=yh('SPY')
adv=pd.read_csv('NYSE_advn.csv',header=None,names=['d','a']); dec=pd.read_csv('NYSE_decln.csv',header=None,names=['d','b'])
real=adv.merge(dec,on='d'); real['d']=pd.to_datetime(real['d'],format='%Y%m%d'); real=real.set_index('d').sort_index()
real=real[(real['a']+real['b'])>0]
rec=pd.read_csv('ad_recon.csv'); rec['date']=pd.to_datetime(rec['date'],format='%Y%m%d'); rec=rec.set_index('date')
net=pd.concat([real['a']-real['b'], rec['adv']-rec['dec']]); net=net[~net.index.duplicated(keep='first')].sort_index()
df=pd.DataFrame({'spx':spx,'mkt':spy.pct_change(),'net':net})
df=df[~df.index.duplicated()].sort_index().dropna(subset=['spx'])
df['vvix']=v.set_index('date')['vvix'].reindex(df.index).ffill(limit=5)
df=df.dropna(subset=['vvix']); df['net']=df['net'].fillna(0); df['mkt']=df['mkt'].fillna(0)
df['ad']=df['net'].cumsum()
df=df[df.index>='2007-03-01']
yrs=(df.index[-1]-df.index[0]).days/365.25
fwd={h:(df['spx'].shift(-h)/df['spx']-1) for h in [5,10,20]}
base={h:fwd[h].mean() for h in fwd}

def signal(vlook,vpct,w,K):
    p=df['vvix'].rolling(vlook,min_periods=vlook//2).apply(lambda x:(x[-1]>=x).mean(),raw=True)
    sh=df['spx']>=df['spx'].rolling(w).max()
    ah=df['ad']>=df['ad'].rolling(w).max()
    armed=(sh&~ah).rolling(K+1,min_periods=1).max().astype(bool)
    return (p>=vpct)&armed

def bt(sig,hold,side,cost=0.0002):
    # signal at close t -> position from t+1 for `hold` days; side -1 short, 0 flat; else long
    s=sig.values.astype(bool); pos=np.ones(len(s)); left=0
    for i in range(len(s)):
        if i>0 and s[i-1]: left=hold
        if left>0: pos[i]=side; left-=1
    pos=pd.Series(pos,index=df.index)
    r=pos*df['mkt']-pos.diff().abs().fillna(0)*cost
    eq=(1+r).cumprod(); vol=r.std()*np.sqrt(252); cagr=eq.iloc[-1]**(1/yrs)-1
    # signal-only P&L (the overlay itself): return earned on non-long days relative
    ov=((pos-1)*df['mkt']).where(pos!=1,0)
    return cagr,cagr/vol,(eq/eq.cummax()-1).min(),(pos!=1).mean(),ov.sum()

rows=[]
for vlook,vpct,w,K in itertools.product([21,63],[0.80,0.90],[5,10,20],[3]):
    sig=signal(vlook,vpct,w,K)
    ev=sig&~sig.shift(1,fill_value=False)  # signal onsets
    n=int(ev.sum())
    row=dict(vvix_look=vlook,vvix_pct=vpct,div_w=w,events=n)
    for h in [5,10,20]:
        x=fwd[h][ev].dropna()
        row[f'fwd{h}']=x.mean()-base[h]; row[f'hit{h}']=(x<0).mean()
        row[f't{h}']=(x.mean()-base[h])/(x.std()/np.sqrt(len(x))) if len(x)>2 else np.nan
    for hold in [5,10]:
        c,sh,dd,ex,ov=bt(sig,hold,-1.0); row[f'short{hold}_cagr']=c; row[f'short{hold}_sharpe']=sh; row[f'short{hold}_dd']=dd; row[f'short{hold}_ovl']=ov
        c,sh,dd,ex,ov=bt(sig,hold,0.0); row[f'flat{hold}_sharpe']=sh
    rows.append(row)
res=pd.DataFrame(rows)
bh=bt(pd.Series(False,index=df.index),5,1.0)
print(f'Window {df.index[0].date()} -> {df.index[-1].date()} | B&H CAGR {bh[0]:.2%} Sharpe {bh[1]:.3f} MaxDD {bh[2]:.1%}')
print(f'Unconditional fwd SPX: 5d {base[5]:.2%} 10d {base[10]:.2%} 20d {base[20]:.2%}')
pd.set_option('display.width',300)
print(res[['vvix_look','vvix_pct','div_w','events','fwd5','hit5','t5','fwd10','t10','fwd20','t20']].to_string(index=False,float_format=lambda x:f'{x:.3f}'))
print(res[['vvix_look','vvix_pct','div_w','short5_cagr','short5_sharpe','short5_dd','short5_ovl','short10_cagr','short10_sharpe','short10_ovl','flat5_sharpe','flat10_sharpe']].to_string(index=False,float_format=lambda x:f'{x:.3f}'))
res.to_csv('micro_results.csv',index=False)
# pre/post 2020 split for the 3 configs with most events
for _,r0 in res.sort_values('events',ascending=False).head(3).iterrows():
    sig=signal(int(r0.vvix_look),r0.vvix_pct,int(r0.div_w),3); ev=sig&~sig.shift(1,fill_value=False)
    for nm,m in [('2007-2019 real A/D',ev.index<'2020-02-14'),('2020-2026 recon A/D',ev.index>='2020-02-14')]:
        x=fwd[10][ev&m].dropna(); print(f'cfg {int(r0.vvix_look)}/{r0.vvix_pct}/{int(r0.div_w)} {nm}: n={len(x)} excess fwd10={x.mean()-base[10]:.2%} hit={(x<0).mean():.0%}')

print('\n=== robustness: 63/0.8/5 and 63/0.9/5, hold 5d ===')
for vp in [0.8,0.9]:
    sig=signal(63,vp,5,3)
    s=sig.values; pos=np.ones(len(s)); left=0
    for i in range(len(s)):
        if i>0 and s[i-1]: left=5
        if left>0: pos[i]=-1; left-=1
    pos=pd.Series(pos,index=df.index)
    ovl=((pos-1)*df['mkt'])   # extra return vs B&H from shorting (2x notional swing)
    by=ovl.groupby(ovl.index.year).sum()
    print(f'vpct {vp}: overlay excess by year (sum of daily, pp):')
    print((by*100).round(1).to_string())
    tot=by.sum(); top2=by.sort_values(ascending=False).head(2)
    print(f'total {tot*100:.1f}pp | top 2 years {list(top2.index)} = {top2.sum()*100:.1f}pp | ex-top-2 = {(tot-top2.sum())*100:.1f}pp | yrs positive {int((by>0).sum())}/{len(by)}')
    for c in [0.0002,0.0005,0.001]:
        r=pos*df['mkt']-pos.diff().abs().fillna(0)*c; eq=(1+r).cumprod()
        print(f'  cost {c*1e4:.0f}bp/side: CAGR {eq.iloc[-1]**(1/yrs)-1:.2%} Sharpe {r.mean()/r.std()*np.sqrt(252):.3f}')
    print(f'  days short: {(pos<0).mean():.1%}, trades: {int((pos.diff()<0).sum())}')
