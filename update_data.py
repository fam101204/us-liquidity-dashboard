#!/usr/bin/env python3
"""Refresh with official FRED and Treasury sources; never overwrite on partial failure."""
import io, json, os, sys, time
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import pandas as pd
import requests
from score_model import score_from_rows
from forward_test import build_forward_analysis

ROOT=Path(__file__).resolve().parent
DIR=ROOT/'data'; DIR.mkdir(exist_ok=True)
START=os.environ.get('START_DATE','2019-11-01')  # warmup before 2020 for 20-day scoring
FRED=['WALCL','RRPONTSYD','NASDAQCOM','WRESBAL','DGS10','BAMLH0A0HYM2']
S=requests.Session();S.headers.update({'User-Agent':'Mozilla/5.0 research-dashboard','Accept':'text/csv,application/json,*/*'})

def download(url,params=None,secs=30):
    error=None
    for i in range(3):
        try:
            r=S.get(url,params=params,timeout=(12,secs))
            r.raise_for_status(); return r
        except requests.RequestException as e:
            error=e;print('Retry',i+1, url, type(e).__name__,flush=True);time.sleep(1+i*2)
    raise RuntimeError(f'공식 데이터 조회 실패: {url}: {error}')

def fred(code):
    # FRED graph CSV endpoint is public and does not require an API key.
    r=download('https://fred.stlouisfed.org/graph/fredgraph.csv',{'id':code,'cosd':START})
    d=pd.read_csv(io.BytesIO(r.content),na_values=['.'])
    d.columns=[str(c).strip().upper() for c in d.columns]
    dcol='OBSERVATION_DATE' if 'OBSERVATION_DATE' in d else 'DATE'
    if code not in d: raise ValueError(f'{code} FRED response invalid: {list(d)}')
    d[dcol]=pd.to_datetime(d[dcol],errors='coerce');d[code]=pd.to_numeric(d[code],errors='coerce')
    out=d.dropna(subset=[dcol,code]).set_index(dcol)[code].sort_index()
    if out.empty or (pd.Timestamp.today().normalize()-out.index.max()).days>17:raise ValueError(f'{code} is stale')
    return out

def treasury():
    """Load every DTS API page, including pre-2021 Federal Reserve Account naming.
    Important: close_today_bal is empty for post-April 2022 TGA closing rows;
    the Treasury stores closing balance in open_today_bal for those rows.
    DTS values are millions of dollars.
    """
    endpoint='https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance'
    params={'filter':f'record_date:gte:{START}',
            'fields':'record_date,account_type,open_today_bal,close_today_bal',
            'page[size]':'5000','sort':'record_date'}
    allrows=[]; page=1; total_pages=1
    while page<=total_pages:
        print(f'Treasury page {page}/{total_pages}',flush=True)
        params['page[number]']=str(page)
        body=download(endpoint,params,secs=70).json()
        meta=body.get('meta',{})
        total_pages=int(meta.get('total-pages',1))
        if total_pages>100: raise ValueError('Unexpected Treasury page count')
        part=body.get('data',[])
        if not isinstance(part,list) or not part: raise ValueError(f'Empty Treasury page {page}')
        allrows.extend(part);page+=1
    d=pd.DataFrame(allrows)
    required={'record_date','account_type','open_today_bal','close_today_bal'}
    if not required.issubset(d):raise ValueError('Treasury fields missing')
    ac=d['account_type'].astype(str).str.lower()
    # Pre-Oct 2021 Federal Reserve Account; newer Treasury General Account.
    mask=ac.str.contains(r'(treasury general account|federal reserve account|\btga\b)',regex=True) & ac.str.contains('closing balance')
    d=d.loc[mask].copy()
    d['record_date']=pd.to_datetime(d['record_date'],errors='coerce')
    # DTS changed the closing-balance storage field in April 2022.
    # For a closing-balance row, use close_today_bal when present; else open_today_bal.
    close=pd.to_numeric(d['close_today_bal'],errors='coerce')
    open_=pd.to_numeric(d['open_today_bal'],errors='coerce')
    d['TGA']=close.combine_first(open_)
    d=d.dropna(subset=['record_date','TGA'])
    if d.empty: raise ValueError('No TGA closing-balance records: inspect account_type names')
    if d['record_date'].duplicated().any():
        dup=d.loc[d['record_date'].duplicated(),['record_date','account_type']]
        raise ValueError(f'Duplicate TGA dates: {dup.head().to_dict("records")}')
    t=d.set_index('record_date')['TGA'].sort_index()
    if (pd.Timestamp.today().normalize()-t.index.max()).days>10:raise ValueError('Treasury TGA stale')
    return t

def asof(series,dates,lag=0,div=1):
    s=series.copy();s.index=s.index+pd.Timedelta(days=lag)
    return s.reindex(s.index.union(dates)).sort_index().ffill().reindex(dates)/div

def main():
    print('Fetching FRED official data',flush=True)
    f={k:fred(k) for k in FRED}
    print('Fetching US Treasury TGA',flush=True)
    t=treasury()
    dates=f['NASDAQCOM'].index[f['NASDAQCOM'].index>=pd.Timestamp('2020-01-01')]
    if len(dates)<1200:raise ValueError('Historical Nasdaq observations insufficient; expected 2020 onward')
    d=pd.DataFrame(index=dates)
    d['NASDAQCOM']=f['NASDAQCOM'].reindex(dates)
    d['Fed_USD_trillion']=asof(f['WALCL'],dates,lag=1,div=1e6)
    d['TGA_USD_trillion']=asof(t,dates,div=1e6)
    d['RRP_USD_trillion']=asof(f['RRPONTSYD'],dates,div=1e3)
    d['Bank_Reserves_USD_trillion']=asof(f['WRESBAL'],dates,lag=1,div=1e6)
    d['UST10Y_pct']=asof(f['DGS10'],dates)
    d['HY_OAS_pct']=asof(f['BAMLH0A0HYM2'],dates)
    if d.isna().any().any():raise ValueError('Series contain missing values after alignment')
    d['Net_Liquidity_USD_trillion']=d['Fed_USD_trillion']-d['TGA_USD_trillion']-d['RRP_USD_trillion']
    d['Net_Liquidity_Index_100']=100*d['Net_Liquidity_USD_trillion']/d['Net_Liquidity_USD_trillion'].iloc[0]
    d['NASDAQ_Index_100']=100*d['NASDAQCOM']/d['NASDAQCOM'].iloc[0]
    d.index.name='Date';d=d.reset_index();d['Date']=d['Date'].dt.strftime('%Y-%m-%d')
    # atomic writes only after all upstream sources pass validation
    meta={'last_refresh_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'start_date':d.iloc[0]['Date'], 'end_date':d.iloc[-1]['Date'],'asof': {k:str(v.index[-1].date()) for k,v in f.items()}|{'TGA':str(t.index[-1].date())},'source':'Official FRED & U.S. Treasury FiscalData'}
    recent=d.round(9).to_dict(orient='records')
    # Preserve and append all observations since 2020; recalculate scores and tests on entire history.
    # Scores must use preceding 20 sessions, never future observations.
    hist_file=DIR/'observation_history.json'
    old=[]
    if hist_file.exists():
        old=json.loads(hist_file.read_text(encoding='utf-8')).get('rows',[])
    elif (DIR/'latest.json').exists():
        old=json.loads((DIR/'latest.json').read_text(encoding='utf-8')).get('rows',[])
    merged={r['Date']:r for r in old if isinstance(r,dict) and 'Date' in r}
    for r in recent: merged[r['Date']]=r
    full=[merged[k] for k in sorted(merged)]
    scores=score_from_rows(full)
    forward=build_forward_analysis(full,scores)
    meta['score_version']='v1'
    payload={'meta':meta,'rows':recent,'score_history':scores,'forward_analysis':forward}
    meta['history_rows']=len(full)
    meta['historical_backfill_start']=full[0]['Date']
    meta['validation_policy']='Descriptive 2020–2024 vs 2025+ split; overlapping forward windows, NOT a proven strategy'
    payload['meta']=meta
    # Write outputs only once all input validation and scoring succeed.
    for name,obj in [('observation_history.json',{'rows':full}),('score_history.json',{'meta':{'score_version':'v1'},'rows':scores}),('forward_analysis.json',forward),('latest.json',payload)]:
        target=DIR/name;tmp=DIR/(name+'.tmp')
        tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        os.replace(tmp,target)
    print('Updated',meta['end_date'])

if __name__=='__main__':
    try:main()
    except Exception as e:print('UPDATE FAILED; existing snapshot preserved:',e,file=sys.stderr);sys.exit(1)
