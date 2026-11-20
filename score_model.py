"""V3 heuristic environment score. Not a fitted or predictive model."""
import math

def score_from_rows(rows, window=20):
    """Scores using only data available at the row date. First `window` rows lack history."""
    out=[]
    def clip(v): return max(0.0,min(100.0,v))
    def pct(now,prior): return (now/prior-1)*100 if prior else None
    for i,row in enumerate(rows):
        r={"Date":row["Date"],"score":None,"net":None,"reserves":None,"rates":None,"credit":None}
        if i>=window:
            prev=rows[i-window]
            values=[row.get(k) for k in ("Net_Liquidity_USD_trillion","Bank_Reserves_USD_trillion","UST10Y_pct","HY_OAS_pct")]+[prev.get(k) for k in ("Net_Liquidity_USD_trillion","Bank_Reserves_USD_trillion","UST10Y_pct","HY_OAS_pct")]
            if all(isinstance(v,(int,float)) and math.isfinite(v) for v in values) and prev['Net_Liquidity_USD_trillion'] and prev['Bank_Reserves_USD_trillion']:
                net=pct(row['Net_Liquidity_USD_trillion'],prev['Net_Liquidity_USD_trillion'])
                reserve=pct(row['Bank_Reserves_USD_trillion'],prev['Bank_Reserves_USD_trillion'])
                rate=row['UST10Y_pct']-prev['UST10Y_pct']
                credit=row['HY_OAS_pct']-prev['HY_OAS_pct']
                r['net']=round(clip(50+25*net),1) # +/-2% => 0/100
                r['reserves']=round(clip(50+25*reserve),1) # +/-2% => 0/100
                r['rates']=round(clip(50-100*rate),1) # +/-0.5 pp => 0/100
                r['credit']=round(clip(50-125*credit),1) # +/-0.4 pp => 0/100
                r['score']=round(.30*r['net']+.25*r['reserves']+.20*r['rates']+.25*r['credit'],1)
        out.append(r)
    return out
