import numpy as np, pandas as pd, itertools, csv, datetime as dt, json
def ref(fn): return {r['date']:float(r['dt_rel']) for r in csv.DictReader(open(fn))}
REF={'spx':ref('fib-shots/dt_dtp_spx.csv'),'iwm':ref('fib-shots/dt_dtp_iwm.csv')}
WIN={'spx':('2026-10-12','2026-10-16'),'iwm':('2026-10-12','2026-11-20')}
PV={'spx':[('2026-09-16','L'),('2026-09-22','H'),('2026-10-01','L'),('2026-10-06','H')],
    'iwm':[('2026-07-31','L'),('2026-08-14','H'),('2026-09-03','H'),('2026-09-16','H'),('2026-10-01','L'),('2026-10-06','H')]}
HOL={'2026-09-07','2026-11-26','2026-07-03'}
bd=[d for d in pd.bdate_range('2026-06-01','2026-12-31') if str(d.date()) not in HOL]
TD={str(d.date()):i for i,d in enumerate(bd)}
def tdx(s):
    d=pd.Timestamp(s)
    while str(d.date()) not in TD: d-=pd.Timedelta(days=1)
    return TD[str(d.date())]+ (0 if str(pd.Timestamp(s).date()) in TD else 0.5)
def T(s,unit): return pd.Timestamp(s).toordinal() if unit=='cal' else tdx(s)
def proj(key,c):
    pv=PV[key]; u=c['unit']; H=pv[-1]; tH=T(H[0],u); P=[]
    lows=[p for p in pv if p[1]=='L']; highs=[p for p in pv if p[1]=='H']
    for L in lows[::-1][:c['trn']]:
        for r in c['TR']: P.append((tH+r*(tH-T(L[0],u)),c['wTR']))
    n=0
    for a,b in zip(pv[::-1][1:],pv[::-1]):
        pass
    sw=[(pv[i],pv[i+1]) for i in range(len(pv)-1) if pv[i][1]=='H' and pv[i+1][1]=='L'][::-1][:c['atpn']]
    for a,b in sw:
        for r in c['ATP']: P.append((tH+r*(T(b[0],u)-T(a[0],u)),c['wATP']))
    lastL=lows[-1]; tL=T(lastL[0],u)
    for a,b in list(zip(lows,lows[1:]))[::-1][:c['ttn']]:
        for r in c['TT']: P.append((tL+r*(T(b[0],u)-T(a[0],u)),c['wTT']))
    for a,b in list(zip(highs,highs[1:]))[::-1][:c['hhn']]:
        for r in c['HH']: P.append((tH+r*(T(b[0],u)-T(a[0],u)),c['wHH']))
    return P
DAYS={k:pd.date_range(*WIN[k]) for k in WIN}
def dist(key,c):
    P=proj(key,c); days=DAYS[key]
    X=np.array([T(str(d.date()),c['unit']) if c['unit']=='cal' or d.weekday()<5 else np.nan for d in days],float)
    if not P: return {str(d.date()):0 for d in days}
    p=np.array([q for q,_ in P]); w=np.array([q for _,q in P])
    dx=X[:,None]-p[None,:]
    if c['k']=='box': K=(np.abs(dx)<=c['bw']/2+1e-9)
    elif c['k']=='tri': K=np.clip(1-np.abs(dx)/c['bw'],0,None)
    else: K=np.exp(-dx*dx/(2*c['bw']**2))
    v=np.nan_to_num((K*w).sum(1)); m=v.max() or 1
    return {str(d.date()):x/m for d,x in zip(days,v)}
def score(c):
    tot=0; det={}
    for k in REF:
        o=dist(k,c); e=np.array([o[d]-REF[k].get(d,0) for d in o])
        det[k]=(float(np.sqrt(np.mean(e*e))),float(np.abs(e).max()),max(o,key=o.get)); tot+=det[k][0]
    return tot,det
RS={'r3':[.382,.5,.618],'r5':[.382,.5,.618,1,1.618],'r7':[.382,.5,.618,.786,1,1.272,1.618],'r4':[.382,.5,.618,.786],'r8':[.236,.382,.5,.618,.786,1,1.272,1.618],'0':[]}
AS={'a3':[.618,1,1.618],'a4':[.618,1,1.272,1.618],'a5':[.382,.618,1,1.618,2.618],'a1':[1],'0':[]}
if __name__=='__main__':
    res=[]
    for unit in ['cal','td']:
     for tr,at,tt,hh in itertools.product(['r3','r4','r5','r7','r8'],['a3','a4','a5','a1','0'],['a3','a1','r5','0'],['a3','a1','r5','0']):
      for trn,atpn,ttn,hhn in itertools.product([1,2],[1,2],[1,2],[1,2,3]):
       if (tt=='0' and ttn>1) or (hh=='0' and hhn>1) or (at=='0' and atpn>1): continue
       for k,bw in [('box',1),('box',2),('box',3),('tri',1.5),('tri',2),('tri',3),('g',.7),('g',1),('g',1.5)]:
        c=dict(unit=unit,TR=RS[tr],ATP=AS[at],TT=AS.get(tt,RS.get(tt)),HH=AS.get(hh,RS.get(hh)),trn=trn,atpn=atpn,ttn=ttn,hhn=hhn,k=k,bw=bw,wTR=1,wATP=1,wTT=1,wHH=1)
        s,d=score(c); res.append((s,(unit,tr,at,tt,hh,trn,atpn,ttn,hhn,k,bw),d))
    res.sort(key=lambda r:r[0])
    for r in res[:25]: print(round(r[0],3),r[1],{k:(round(v[0],3),round(v[1],2),v[2]) for k,v in r[2].items()})
    json.dump([[r[0],r[1]] for r in res[:100]],open('fit2_top.json','w'))
