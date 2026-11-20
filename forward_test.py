"""Historical descriptive forward Nasdaq returns by non-overlapping score buckets.
Not a trading forecast. Only completed forward windows included.
"""
import math
from statistics import mean, median

HORIZONS=(5,20)
BUCKETS=(('under30','0~29점',0,30),('30to49','30~49점',30,50),('50to69','50~69점',50,70),('70plus','70~100점',70,101))

def build_forward_analysis(rows,scores):
    ordered=sorted((r for r in rows if r.get('Date') and isinstance(r.get('NASDAQCOM'),(int,float)) and r['NASDAQCOM']>0),key=lambda r:r['Date'])
    lookup={r['Date']:r for r in scores if r.get('Date')}
    samples=[]
    for i,row in enumerate(ordered):
        s=lookup.get(row['Date'],{}).get('score')
        if not isinstance(s,(int,float)) or not math.isfinite(s): continue
        bucket=next((key for key,_,low,high in BUCKETS if low<=s<high),None)
        if bucket is None: continue
        rec={'date':row['Date'],'bucket':bucket,'score':round(s,1), 'split':'2020–2024' if row['Date']<'2025-01-01' else '2025+'}
        for horizon in HORIZONS:
            if i+horizon<len(ordered):
                rec[f'return_{horizon}d']=round(100*(ordered[i+horizon]['NASDAQCOM']/row['NASDAQCOM']-1),4)
            else:
                rec[f'return_{horizon}d']=None
        samples.append(rec)
    summary=[]
    for key,label,_,_ in BUCKETS:
        item={'bucket':key,'label':label,'score_days':sum(r['bucket']==key for r in samples)}
        for horizon in HORIZONS:
            ret=[r[f'return_{horizon}d'] for r in samples if r['bucket']==key and r[f'return_{horizon}d'] is not None]
            item[f'h{horizon}']={'n':len(ret),'mean':round(mean(ret),2) if ret else None,'median':round(median(ret),2) if ret else None,'win_rate':round(100*sum(x>0 for x in ret)/len(ret),1) if ret else None}
        summary.append(item)
    validation=[]
    for spl in ('2020–2024','2025+'):
        b=[]
        for key,label,_,_ in BUCKETS:
            item={'bucket':key,'label':label}
            for horizon in HORIZONS:
                # only completed forwards and no crossing 2024/25 split for training samples
                ret=[]
                for r in samples:
                    if r['split']!=spl or r['bucket']!=key or r[f'return_{horizon}d'] is None:continue
                    if spl=='2020–2024' and r['date'] >= '2024-12-01' and (ordered[next((j for j,x in enumerate(ordered) if x['Date']==r['date']),0)+horizon]['Date'] >= '2025-01-01'):continue
                    ret.append(r[f'return_{horizon}d'])
                item[f'h{horizon}']={'n':len(ret),'mean':round(mean(ret),2) if ret else None,'win_rate':round(100*sum(x>0 for x in ret)/len(ret),1) if ret else None}
            b.append(item)
        validation.append({'period':spl,'buckets':b})
    return {'validation':validation,'method':'score-v1 / Nasdaq forward returns','horizons':list(HORIZONS),'buckets':summary,'samples':samples,'overlap_warning':'Forward rolling windows overlap; observations are not independent. Results are descriptive only.','asof':ordered[-1]['Date'] if ordered else None}
