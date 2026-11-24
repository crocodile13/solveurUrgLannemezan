import json,sys,datetime as dt,statistics as st
from collections import Counter
D=json.load(open('slots.json')); info={dt.date.fromisoformat(k):v for k,v in D['info'].items()}
r=json.load(open(sys.argv[1])); P=['Marien','Quentin','Yazid']
FER={dt.date(2026,12,25),dt.date(2027,1,1)}
hist={'Marien':{25:'E',28:'M',29:'E'},'Quentin':{23:'M',29:'M',30:'E'},'Yazid':{25:'M',26:'M',27:'M'}}
def eur(d,s):
    w=d.weekday()
    if w==6 or d in FER: return 256.86
    if w==5: return 234.80 if s=='E' else 117.39
    return 117.39 if s=='E' else 0
days=sorted(info); one=dt.timedelta(1)
miss=[sl for sl in D['slots'] if f'{sl[0]}{sl[1]}' not in r]; print('créneaux vides',miss)
for p in P:
    sh={dt.date.fromisoformat(k[:-1]):k[-1] for k,v in r.items() if v==p}
    for d,s in hist[p].items(): sh.setdefault(dt.date(2026,11,d),s)
    ds=sorted(sh)
    viol=[d for d in ds if sh[d]=='E' and sh.get(d+one)=='M']
    w7=[d for d in ds if sum(1 for k in range(7) if d+one*k in sh)>5]
    run=[];c=0;mx=0
    for d in [dt.date(2026,11,20)+one*i for i in range(110)]:
        c=c+1 if d in sh else 0; mx=max(mx,c)
    five=sum(1 for d in ds if all(d+one*k in sh for k in range(5)) and d-one not in sh)
    busy=set(d for d in sh if d>=days[0])|{d for d in days if info[d]['full']}
    F=[];W=[];cf=cw=0
    for d in days:
        if d in busy:
            cw+=1
            if cf: F.append(cf); cf=0
        else:
            cf+=1
            if cw: W.append(cw); cw=0
    if cf: F.append(cf)
    if cw: W.append(cw)
    per={mo:sum(1 for d in sh if d.month==mo and d>=days[0]) for mo in (12,1,2)}
    e=sum(eur(d,s) for d,s in sh.items() if d>=days[0])
    print(f'{p:8} postes déc/jan/fév {per} € {e:.2f} soirs {sum(1 for d,s in sh.items() if d>=days[0] and s=="E")} | E->M {viol} | 7j>5 {w7} | max consécutif {mx} | séries5 {five}')
    print(f'          libres {dict(sorted(Counter(F).items()))} méd {st.median(F)} | travail {dict(sorted(Counter(W).items()))} méd {st.median(W)}')
