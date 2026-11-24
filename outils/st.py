import json,sys,datetime as dt,collections
sys.argv.pop(0)
for f in sys.argv:
    d=json.load(open(f)); print('==',f.split('/')[-1])
    for p in ['Marien','Quentin','Yazid']:
        days={dt.date.fromisoformat(k[:10]) for k,v in d.items() if v and v.upper()==p.upper()}|{dt.date(2027,2,4),dt.date(2027,2,16)}
        sat=[dt.date(2026,12,5)+dt.timedelta(7*i) for i in range(13)]
        free=sum(1 for s in sat if s not in days and s+dt.timedelta(1) not in days)
        nwe=sum(1 for x in days if x.weekday()>=5)
        th=[dt.date(2026,12,3)+dt.timedelta(7*i) for i in range(13)]
        lng=[t.strftime('%d/%m') for t in th if all(t+dt.timedelta(k) not in days for k in range(5)) and t+dt.timedelta(4)<=dt.date(2027,2,28)]
        print(f" {p[:3]} WE libres {free}/13 jours WE {nwe} | jeu->lun libres {len(lng)} {lng}")
