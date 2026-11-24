import json,sys,datetime as dt
f=sys.argv[1]; d=json.load(open(f))
cours={dt.date(2027,2,4),dt.date(2027,2,16)}
print('==',f)
start=dt.date(2026,11,30)
for p in ['Marien','Quentin','Yazid']:
    print(p)
    for w in range(13):
        row=[]
        for k in range(7):
            day=start+dt.timedelta(7*w+k); s=day.isoformat()
            c='.'
            if (d.get(s+'M') or '').upper()==p.upper(): c='M'
            if (d.get(s+'E') or '').upper()==p.upper(): c='S'
            row.append(f"{day.day:2d}{c}")
        print('  ',' '.join(row))
